import hashlib
import io
import os
from pathlib import Path

import pytest

from backend.app.providers.local import LocalFolderProvider
from backend.app.providers.s3 import S3StorageProvider, sign_s3_v4
from backend.app.services.drive_service import (
    add_drive,
    get_macos_storage_locations,
    patch_drive,
)
from backend.app.services.storage_engine import (
    download_stream,
    heal_pool,
    upload_stream,
    verify_integrity,
)


def test_s3_signer_v4_generation():
    headers = {"content-type": "application/octet-stream"}
    body = b"hello s3 storage"
    signed = sign_s3_v4(
        method="PUT",
        url="https://demo-account.r2.cloudflarestorage.com/my-bucket/chunks/12345",
        headers=headers,
        body=body,
        access_key="mock_access_key",
        secret_key="mock_secret_key",
        region="auto",
    )
    assert "authorization" in signed
    assert "AWS4-HMAC-SHA256" in signed["authorization"]
    assert "Credential=mock_access_key" in signed["authorization"]
    assert "x-amz-content-sha256" in signed
    assert signed["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert signed["host"] == "demo-account.r2.cloudflarestorage.com"


def test_s3_storage_provider_mock_crud(tmp_path, monkeypatch):
    mock_home = tmp_path / "user_home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))

    config = {
        "endpoint_url": "https://account123.r2.cloudflarestorage.com",
        "bucket": "test-vault",
        "access_key_id": "mock_r2_key",
        "secret_access_key": "mock_r2_secret",
        "region": "auto",
        "prefix": "vault_chunks/",
    }
    provider = S3StorageProvider(config=config)

    assert provider.provider_variant == "Cloudflare R2"
    assert provider.is_mock is True
    assert provider.check_availability() is True

    chunk_id = "0123456789abcdef0123456789abcdef"
    chunk_data = b"Encrypted chunk data for Cloudflare R2"

    provider.put_chunk(chunk_id, chunk_data)

    retrieved = provider.get_chunk(chunk_id)
    assert retrieved == chunk_data

    usage = provider.get_usage()
    assert usage["total"] == 10 * (1024**3)
    assert usage["used"] == len(chunk_data)
    assert usage["is_cloud_synced"] is True
    assert "Cloudflare R2" in usage["source"]

    dev_info = provider.get_device_info()
    assert dev_info["is_cloud_synced"] is True
    assert "Cloudflare R2" in dev_info["volume_name"]

    assert provider.delete_chunk(chunk_id) is True
    assert provider.delete_chunk(chunk_id) is False


def test_icloud_onedrive_dropbox_detection_and_quota(tmp_path):
    # 1. Test Apple iCloud Drive folder
    icloud_folder = tmp_path / "Mobile Documents" / "com~apple~CloudDocs" / "FrankensteinStorage"
    icloud_folder.mkdir(parents=True)
    provider_icloud = LocalFolderProvider(root_path=str(icloud_folder))

    info_icloud = provider_icloud.get_device_info()
    assert info_icloud["is_cloud_synced"] is True
    assert info_icloud["device_id"] == "icloud_drive_cloud_storage"
    assert "Apple iCloud Drive" in info_icloud["volume_name"]

    usage_icloud = provider_icloud.get_usage()
    assert usage_icloud["total"] == 5 * (1024**3)  # 5 GiB iCloud quota
    assert "Apple iCloud Drive (5 GiB)" in usage_icloud["source"]

    # 2. Test Microsoft OneDrive folder
    onedrive_folder = tmp_path / "CloudStorage" / "OneDrive-Personal" / "FrankensteinStorage"
    onedrive_folder.mkdir(parents=True)
    provider_onedrive = LocalFolderProvider(root_path=str(onedrive_folder))

    info_od = provider_onedrive.get_device_info()
    assert info_od["is_cloud_synced"] is True
    assert info_od["device_id"] == "onedrive_cloud_storage"
    assert "Microsoft OneDrive" in info_od["volume_name"]

    usage_od = provider_onedrive.get_usage()
    assert usage_od["total"] == 5 * (1024**3)  # 5 GiB OneDrive quota
    assert "Microsoft OneDrive (5 GiB)" in usage_od["source"]

    # 3. Test Dropbox folder
    dropbox_folder = tmp_path / "CloudStorage" / "Dropbox" / "FrankensteinStorage"
    dropbox_folder.mkdir(parents=True)
    provider_db = LocalFolderProvider(root_path=str(dropbox_folder))

    info_db = provider_db.get_device_info()
    assert info_db["is_cloud_synced"] is True
    assert info_db["device_id"] == "dropbox_cloud_storage"
    assert "Dropbox" in info_db["volume_name"]

    usage_db = provider_db.get_usage()
    assert usage_db["total"] == 2 * (1024**3)  # 2 GiB Dropbox quota
    assert "Dropbox Cloud (2 GiB)" in usage_db["source"]


def test_macos_storage_locations_detection(tmp_path, monkeypatch):
    """Test get_macos_storage_locations returns iCloud Drive, OneDrive, and Dropbox when present."""
    fake_home = tmp_path / "mock_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Create fake iCloud Drive and CloudStorage
    icloud_docs = fake_home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    icloud_docs.mkdir(parents=True)

    onedrive_dir = fake_home / "Library" / "CloudStorage" / "OneDrive-Personal"
    onedrive_dir.mkdir(parents=True)

    dropbox_dir = fake_home / "Library" / "CloudStorage" / "Dropbox-Team"
    dropbox_dir.mkdir(parents=True)

    locs = get_macos_storage_locations()
    loc_names = [loc["name"] for loc in locs]

    assert any("Apple iCloud Drive" in n for n in loc_names)
    assert any("Microsoft OneDrive" in n for n in loc_names)
    assert any("Dropbox" in n for n in loc_names)


@pytest.mark.asyncio
async def test_add_s3_and_cloud_drives_via_api(async_client, test_env, tmp_path):
    # 1. Add Cloudflare R2 drive
    r2_payload = {
        "display_name": "Cloudflare R2 Secondary",
        "provider_type": "r2",
        "path": "s3://my-r2-vault/chunks",
        "config": {
            "endpoint_url": "https://account123.r2.cloudflarestorage.com",
            "bucket": "my-r2-vault",
            "access_key_id": "mock_r2_id",
            "secret_access_key": "mock_r2_secret",
            "region": "auto",
        },
    }
    res = await async_client.post("/api/v1/drives", json=r2_payload)
    assert res.status_code == 200, res.text
    r2_data = res.json()
    assert r2_data["provider_type"] == "r2"

    # 2. Add Apple iCloud Drive
    icloud_path = tmp_path / "Mobile Documents" / "com~apple~CloudDocs" / "FrankensteinStorage"
    icloud_path.mkdir(parents=True)
    icloud_payload = {
        "display_name": "Apple iCloud Drive",
        "provider_type": "icloud",
        "path": str(icloud_path),
    }
    res = await async_client.post("/api/v1/drives", json=icloud_payload)
    assert res.status_code == 200, res.text
    icloud_data = res.json()
    assert icloud_data["provider_type"] == "icloud"

    # 3. Verify drives appear in /api/v1/drives list
    res = await async_client.get("/api/v1/drives")
    assert res.status_code == 200
    drives = res.json()
    r2_drive = next(d for d in drives if d["provider_type"] == "r2")
    ic_drive = next(d for d in drives if d["provider_type"] == "icloud")

    assert r2_drive["usage"]["is_cloud_synced"] is True
    assert ic_drive["usage"]["is_cloud_synced"] is True


@pytest.mark.asyncio
async def test_hybrid_pool_local_icloud_r2_usb_with_parity_recovery(
    test_env, tmp_path, monkeypatch
):
    """Verifies striped upload & XOR parity rebuild across a hybrid pool:
    Drive 1: Local SSD
    Drive 2: Apple iCloud Drive
    Drive 3: Cloudflare R2 / S3
    Drive 4: External USB Pendrive
    """
    conn = test_env["conn"]
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))

    # Clean existing test drives to test our dedicated 4-provider hybrid pool
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM files")
    conn.execute("DELETE FROM drives")
    conn.commit()

    # Setup 4 distinct storage targets
    d1_path = tmp_path / "local_ssd"
    d1_path.mkdir()

    d2_path = tmp_path / "Mobile Documents" / "com~apple~CloudDocs" / "FrankensteinStorage"
    d2_path.mkdir(parents=True)

    d4_path = tmp_path / "Volumes" / "CORSAIR_USB" / "FrankensteinStorage"
    d4_path.mkdir(parents=True)

    add_drive(conn, str(d1_path), "Macintosh SSD", provider_type="local")
    add_drive(conn, str(d2_path), "Apple iCloud Drive", provider_type="icloud")
    d3 = add_drive(
        conn,
        "s3://r2-vault/chunks",
        "Cloudflare R2 Bucket",
        provider_type="r2",
        config={
            "endpoint_url": "https://account123.r2.cloudflarestorage.com",
            "bucket": "r2-vault",
            "access_key_id": "mock_key",
            "secret_access_key": "mock_secret",
        },
    )
    add_drive(conn, str(d4_path), "Corsair USB Pendrive", provider_type="local")
    conn.commit()

    # Upload a 150 KB test file across the 4-drive hybrid pool
    test_data = os.urandom(150 * 1024)
    stream = io.BytesIO(test_data)
    uploaded = await upload_stream(conn, stream, "hybrid_cloud_doc.bin", folder="/", overwrite=True)
    file_id = uploaded["id"]

    # Confirm multiple drives received chunks
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT drive_id FROM chunks WHERE file_id = ?", (file_id,))
    placed_drive_ids = {row["drive_id"] for row in cursor.fetchall()}
    assert len(placed_drive_ids) >= 3

    # Find chunk placed on R2
    cursor.execute(
        "SELECT chunk_id FROM chunks WHERE file_id = ? AND drive_id = ?", (file_id, d3["id"])
    )
    r2_chunk_rows = cursor.fetchall()
    assert len(r2_chunk_rows) >= 1

    # Simulate Cloudflare R2 going offline
    patch_drive(conn, d3["id"], simulated_offline=True)
    conn.commit()

    # Verify integrity shows degraded
    rep = verify_integrity(conn, file_id)
    assert rep["status"] == "degraded"

    # Download file while R2 is offline — XOR parity reconstruction must succeed with exact SHA-256!
    meta, gen, _ = download_stream(conn, file_id)
    downloaded_bytes = b"".join(gen)
    assert downloaded_bytes == test_data
    assert hashlib.sha256(downloaded_bytes).hexdigest() == uploaded["sha256"]

    # Bring R2 back online, delete one chunk from R2 mock storage to simulate data loss, and heal pool
    patch_drive(conn, d3["id"], simulated_offline=False)
    conn.commit()

    # Delete the R2 chunk to force heal_pool to reconstruct it
    r2_prov = S3StorageProvider(
        config={
            "endpoint_url": "https://account123.r2.cloudflarestorage.com",
            "bucket": "r2-vault",
            "access_key_id": "mock_key",
            "secret_access_key": "mock_secret",
        }
    )
    r2_prov.delete_chunk(r2_chunk_rows[0]["chunk_id"])

    heal_res = heal_pool(conn)
    assert heal_res["chunks_rebuilt"] >= 1
    assert heal_res["status"] in ("healthy", "healed")

    # File should now be healthy again
    rep_healed = verify_integrity(conn, file_id)
    assert rep_healed["status"] == "healthy"
