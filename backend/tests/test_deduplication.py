"""Unit and integration tests for physical filesystem de-duplication in Frankenstein Storage."""

import os
from pathlib import Path

import pytest

from backend.app.providers.local import LocalFolderProvider
from backend.app.services.drive_service import calculate_pooled_overview, list_drives


def test_local_provider_device_info(tmp_path: Path):
    """Test that LocalFolderProvider accurately reports st_dev and device_id."""
    p1 = tmp_path / "folder_a"
    p1.mkdir()
    provider = LocalFolderProvider(p1)

    dev_info = provider.get_device_info()
    assert dev_info["device_id"] is not None
    assert dev_info["st_dev"] == os.stat(p1).st_dev
    assert dev_info["device_id"] == f"dev_{os.stat(p1).st_dev}"

    usage = provider.get_usage()
    assert usage["device_id"] == dev_info["device_id"]
    assert usage["st_dev"] == dev_info["st_dev"]


def test_calculate_pooled_overview_deduplicates_same_volume(test_env):
    """Test that multiple drives sharing the same physical st_dev do not multiply capacity."""
    conn = test_env["conn"]

    # In test_env, drive1, drive2, drive3 are subdirectories in tmp_path (same filesystem)
    drives = list_drives(conn)
    assert len(drives) >= 3

    # All 3 drives in test_env share the same physical volume
    for d in drives:
        assert d["shared_device"] is True
        assert d["shared_device_count"] >= 3
        assert "Volume" in (d.get("shared_volume_name") or "")

    overview = calculate_pooled_overview(conn, drives)
    single_drive_cap = drives[0]["usage"]["total"]

    # Pooled capacity should equal single physical capacity, NOT 3x
    assert overview["pooled_capacity"] == single_drive_cap
    assert abs(overview["pooled_free"] - drives[0]["usage"]["free"]) < 50 * 1024 * 1024
    assert overview["capacity_source"] == "Provider-reported (De-duplicated)"
    assert overview["drives_count"] == len(drives)


def test_calculate_pooled_overview_sums_distinct_devices(test_env):
    """Test that drives with distinct device_ids have their capacities summed."""
    conn = test_env["conn"]

    mock_drives = [
        {
            "id": "drive_local_1",
            "available": True,
            "status": "online",
            "device_id": "dev_1001",
            "usage": {"total": 100_000_000_000, "free": 20_000_000_000, "used": 80_000_000_000},
        },
        {
            "id": "drive_local_2_shared",
            "available": True,
            "status": "online",
            "device_id": "dev_1001",  # Same volume as drive 1
            "usage": {"total": 100_000_000_000, "free": 20_000_000_000, "used": 80_000_000_000},
        },
        {
            "id": "drive_usb_external",
            "available": True,
            "status": "online",
            "device_id": "dev_2002",  # Distinct physical disk
            "usage": {"total": 50_000_000_000, "free": 45_000_000_000, "used": 5_000_000_000},
        },
        {
            "id": "drive_gdrive_cloud",
            "available": True,
            "status": "online",
            "device_id": "gdrive_cloud_vault",  # Cloud quota
            "usage": {"total": 15_000_000_000, "free": 10_000_000_000, "used": 5_000_000_000},
        },
    ]

    overview = calculate_pooled_overview(conn, mock_drives)

    # Capacity should be: 100 GB (counted once for dev_1001) + 50 GB (dev_2002) + 15 GB (cloud) = 165 GB
    expected_cap = 100_000_000_000 + 50_000_000_000 + 15_000_000_000
    assert overview["pooled_capacity"] == expected_cap

    expected_free = 20_000_000_000 + 45_000_000_000 + 10_000_000_000
    assert overview["pooled_free"] == expected_free

    # Host physical disk usage should be sum of unique disks (80 GB + 5 GB + 5 GB = 90 GB)
    assert overview["physical_disk_used"] == (80_000_000_000 + 5_000_000_000 + 5_000_000_000)


@pytest.mark.asyncio
async def test_overview_http_endpoint_returns_deduplicated_metrics(async_client):
    """Test that GET /api/v1/overview returns vault_chunks_bytes and de-duplicated capacity."""
    res = await async_client.get("/api/v1/overview")
    assert res.status_code == 200
    data = res.json()

    assert "pooled_capacity" in data
    assert "pooled_used" in data
    assert "pooled_free" in data
    assert "vault_chunks_bytes" in data
    assert "physical_disk_used" in data
    assert "drives_count" in data
    assert data["capacity_source"] == "Provider-reported (De-duplicated)"

    # pooled_used must equal vault_chunks_bytes (bounded by capacity)
    assert data["pooled_used"] == data["vault_chunks_bytes"]


def test_gdrive_desktop_synced_folder_reporting(tmp_path: Path):
    """Test that Google Drive Desktop cloud paths report 15 GiB quota and actual folder size."""
    # Create simulated CloudStorage/GoogleDrive directory
    gdrive_dir = tmp_path / "CloudStorage" / "GoogleDrive-user@example.com" / "My Drive" / "sample"
    gdrive_dir.mkdir(parents=True)

    # Write a test file of 128 KB
    test_file = gdrive_dir / "test_doc.bin"
    test_file.write_bytes(b"A" * (128 * 1024))

    provider = LocalFolderProvider(gdrive_dir)
    assert provider._get_folder_size(gdrive_dir) == 128 * 1024

    dev_info = provider.get_device_info()
    assert dev_info["device_id"] == "gdrive_cloud_storage"
    assert dev_info["is_cloud_synced"] is True

    usage = provider.get_usage()
    expected_total = 15 * (1024**3)
    assert usage["total"] == expected_total
    assert usage["used"] == 128 * 1024
    assert usage["free"] == expected_total - (128 * 1024)
    assert usage["source"] == "Google Drive Cloud (15 GiB)"
    assert usage["device_id"] == "gdrive_cloud_storage"
    assert usage["is_cloud_synced"] is True
