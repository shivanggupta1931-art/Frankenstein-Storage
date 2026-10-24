"""Tests for external USB and pendrive storage integration, hot-plug detection, and parity recovery."""

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.providers.local import LocalFolderProvider
from backend.app.services import drive_service, storage_engine


def test_detect_external_usb_volumes(tmp_path: Path):
    mock_volumes = tmp_path / "Volumes"
    mock_volumes.mkdir()

    # System volumes to filter out
    (mock_volumes / "Recovery").mkdir()
    (mock_volumes / "Macintosh HD").mkdir()
    (mock_volumes / ".timemachine").mkdir()
    (mock_volumes / "GoogleDrive-test@gmail.com").mkdir()

    # Real external pendrives
    pendrive_1 = mock_volumes / "SanDisk_Ultra"
    pendrive_1.mkdir()
    pendrive_2 = mock_volumes / "Kingston_64GB"
    pendrive_2.mkdir()

    orig_stat = os.stat

    def fake_stat(p, *args, **kwargs):
        stat_res = orig_stat(p, *args, **kwargs)
        # Give pendrive directories a different device ID than root
        if "SanDisk_Ultra" in str(p) or "Kingston_64GB" in str(p):
            mock_st = MagicMock(wraps=stat_res)
            mock_st.st_dev = 54321
            return mock_st
        return stat_res

    with patch(
        "backend.app.services.drive_service.Path",
        side_effect=lambda p: mock_volumes if str(p) == "/Volumes" else Path(p),
    ):
        with patch("backend.app.services.drive_service.os.stat", side_effect=fake_stat):
            drives = drive_service.get_external_usb_drives()
            names = [d["name"] for d in drives]
            assert "USB Drive: SanDisk_Ultra" in names
            assert "USB Drive: Kingston_64GB" in names
            assert not any("Recovery" in n for n in names)
            assert not any("Macintosh HD" in n for n in names)
            assert not any("GoogleDrive" in n for n in names)

            target_paths = [d["path"] for d in drives]
            assert str(pendrive_1 / "FrankensteinStorage") in target_paths
            assert all(d["is_external"] is True for d in drives)
            assert all(d["is_removable"] is True for d in drives)


@pytest.mark.asyncio
async def test_external_drives_http_endpoint(test_env):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.session_token}"}

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        res = await client.get("/api/v1/system/external-drives", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "external_drives" in data
        assert isinstance(data["external_drives"], list)


def test_local_provider_usb_plug_unplug_lifecycle(tmp_path: Path):
    # Simulated unmounted USB volume
    provider = LocalFolderProvider(root_path=Path("/Volumes/LexarUSB_Test/FrankensteinStorage"))

    # Device info detects external USB volume properties
    dev_info = provider.get_device_info()
    assert dev_info["is_external"] is True
    assert dev_info["is_removable"] is True
    assert dev_info["volume_name"] == "External USB: LexarUSB_Test"
    assert dev_info["device_id"].startswith("usb_")

    # When volume is unplugged (not mounted on disk)
    assert provider.check_availability() is False
    usage_offline = provider.get_usage()
    assert usage_offline["available"] is False
    assert usage_offline["is_external"] is True
    assert usage_offline["source"] == "External USB (Offline)"
    assert usage_offline["total"] == 0

    # When volume is plugged in (simulated with mock or existing folder)
    sim_vol = tmp_path / "MountedUSB"
    sim_storage = sim_vol / "FrankensteinStorage"
    sim_storage.mkdir(parents=True)
    mounted_provider = LocalFolderProvider(root_path=sim_storage)
    assert mounted_provider.check_availability() is True
    assert mounted_provider.get_usage()["available"] is True


@pytest.mark.asyncio
async def test_hybrid_pool_with_external_usb_and_parity_rebuild(test_env, tmp_path: Path):
    conn = test_env["conn"]

    # Clear existing test fixture drives to test dedicated USB pool
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM files")
    conn.execute("DELETE FROM drives")
    conn.commit()

    # 1. Add Local Drive 1
    d1_path = tmp_path / "LocalDrive1"
    drive_service.add_drive(conn, str(d1_path), "Internal SSD Part 1", provider_type="local")

    # 2. Add Local Drive 2
    d2_path = tmp_path / "LocalDrive2"
    drive_service.add_drive(conn, str(d2_path), "Internal SSD Part 2", provider_type="local")

    # 3. Add External USB Pendrive
    usb_path = tmp_path / "USB_Pendrive"
    d_usb = drive_service.add_drive(
        conn, str(usb_path), "USB Flash Drive (SanDisk)", provider_type="local"
    )

    # Ensure drives are online
    drives = drive_service.list_drives(conn)
    assert len(drives) == 3

    # Upload a 150 KiB file (using 64KB chunks in test_env, generates 2 data chunks + 1 parity chunk)
    sample_data = os.urandom(150 * 1024)
    upload_res = await storage_engine.upload_stream(
        conn=conn,
        stream=io.BytesIO(sample_data),
        filename="usb_parity_vault_test.bin",
        mode="chunked_parity",
    )
    assert upload_res["status"] == "complete"
    assert upload_res["protection_status"] == "parity"

    # Verify chunks are placed across drives, including the USB drive
    cursor = conn.cursor()
    cursor.execute(
        "SELECT drive_id, chunk_id, is_parity FROM chunks WHERE file_id = ?", (upload_res["id"],)
    )
    chunks = cursor.fetchall()
    assert len(chunks) == 6  # 3 chunks per stripe * 2 stripes (4 data chunks + 2 parity chunks)
    drive_ids_used = {c["drive_id"] for c in chunks}
    assert d_usb["id"] in drive_ids_used, "External USB drive was selected in stripe placement"

    # Download and verify clean SHA-256 with all drives online
    meta, gen, tracker = storage_engine.download_stream(conn, upload_res["id"])
    downloaded = b"".join(list(gen))
    assert downloaded == sample_data
    assert tracker["was_rebuilt"] is False

    # Simulate detaching / unplugging the pendrive
    drive_service.patch_drive(conn, d_usb["id"], simulated_offline=True)

    # Download file in degraded mode: chunk on pendrive is reconstructed on-the-fly via XOR parity!
    meta_deg, gen_deg, tracker_deg = storage_engine.download_stream(conn, upload_res["id"])
    downloaded_deg = b"".join(list(gen_deg))
    assert downloaded_deg == sample_data
    assert tracker_deg["was_rebuilt"] is True


def test_external_drive_flat_chunk_structure_and_manifest(tmp_path: Path):
    usb_root = tmp_path / "Volumes" / "MyPendrive" / "FrankensteinStorage"
    provider = LocalFolderProvider(root_path=usb_root)

    chunk_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    test_data = b"Encrypted chunk payload for USB flat test"
    provider.put_chunk(chunk_id, test_data)

    # 1. Verify chunk is stored flat directly in chunks/<chunk_id>, NOT in chunks/a1/b2/
    expected_flat_chunk = usb_root / "frankenstein_storage" / "chunks" / chunk_id
    assert expected_flat_chunk.exists(), "Chunk is stored directly in flat chunks folder"
    assert not (usb_root / "frankenstein_storage" / "chunks" / "a1").exists(), (
        "No nested a1 folder created"
    )

    # 2. Verify chunk can be read back cleanly
    retrieved = provider.get_chunk(chunk_id)
    assert retrieved == test_data

    # 3. Verify VAULT_MANIFEST.txt is created and contains chunk details
    manifest_file = usb_root / "VAULT_MANIFEST.txt"
    assert manifest_file.exists()
    content = manifest_file.read_text(encoding="utf-8")
    assert "FRANKENSTEIN STORAGE — EXTERNAL DRIVE MANIFEST" in content
    assert chunk_id in content
    assert str(len(test_data)) in content

    # 4. Verify deleting chunk updates manifest
    deleted = provider.delete_chunk(chunk_id)
    assert deleted is True
    assert not expected_flat_chunk.exists()
    content_after = manifest_file.read_text(encoding="utf-8")
    assert chunk_id not in content_after
    assert "Total Chunks Stored : 0" in content_after


def test_auto_migration_nested_chunks_to_flat_structure(tmp_path: Path):
    usb_root = tmp_path / "Volumes" / "Sandisk" / "FrankensteinStorage"
    visible_chunks = usb_root / "frankenstein_storage" / "chunks"
    legacy_chunks = usb_root / ".frankenstein" / "chunks"

    # Pre-populate nested chunk 1 in visible folder (chunks/5e/38/<id>)
    c1_id = "5e38bebb042445bb91079b09ce4e959e"
    c1_path = visible_chunks / "5e" / "38" / c1_id
    c1_path.parent.mkdir(parents=True)
    c1_path.write_bytes(b"chunk 1 data")

    # Pre-populate nested chunk 2 in legacy hidden folder (.frankenstein/chunks/49/0d/<id>)
    c2_id = "490da59054b24fc5954818c7ca792d50"
    c2_path = legacy_chunks / "49" / "0d" / c2_id
    c2_path.parent.mkdir(parents=True)
    c2_path.write_bytes(b"chunk 2 data")

    # Instantiate provider - this should auto-migrate all nested chunks to flat structure
    provider = LocalFolderProvider(root_path=usb_root)

    # 1. Verify chunks now exist flat
    flat1 = visible_chunks / c1_id
    flat2 = visible_chunks / c2_id
    assert flat1.exists()
    assert flat2.exists()

    # 2. Verify nested folders are cleaned up
    assert not (visible_chunks / "5e").exists(), "Empty 5e subfolder cleaned up"
    assert not (usb_root / ".frankenstein").exists(), "Empty legacy .frankenstein cleaned up"

    # 3. Verify get_chunk works for both
    assert provider.get_chunk(c1_id) == b"chunk 1 data"
    assert provider.get_chunk(c2_id) == b"chunk 2 data"

    # 4. Verify manifest lists both migrated chunks
    manifest_content = (usb_root / "VAULT_MANIFEST.txt").read_text(encoding="utf-8")
    assert c1_id in manifest_content
    assert c2_id in manifest_content
    assert "Total Chunks Stored : 2" in manifest_content


@pytest.mark.asyncio
async def test_safe_eject_external_usb_drive(test_env, tmp_path: Path):
    conn = test_env["conn"]

    # 1. Setup internal SSD drive
    d_int_path = tmp_path / "SSD"
    d_int = drive_service.add_drive(conn, str(d_int_path), "Internal SSD", provider_type="local")

    # 2. Setup external USB drive under /Volumes/
    d_usb_path = tmp_path / "Volumes" / "LexarUSB" / "FrankensteinStorage"
    d_usb = drive_service.add_drive(
        conn, str(d_usb_path), "Lexar USB Flash Drive", provider_type="local"
    )
    conn.commit()

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.session_token}"}
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # Rejection test: attempting to eject internal SSD should fail with 400
        res_fail = await ac.post(f"/api/v1/drives/{d_int['id']}/eject", headers=headers)
        assert res_fail.status_code == 400
        assert res_fail.json()["error"]["code"] == "NOT_AN_EXTERNAL_DRIVE"

        # Success test: eject external USB pendrive
        res_ok = await ac.post(f"/api/v1/drives/{d_usb['id']}/eject", headers=headers)
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["status"] == "ejected"
        assert body["volume_name"] == "LexarUSB"
        assert "safely unmounted" in body["message"]

    # Verify drive status in database and list_drives
    drives = drive_service.list_drives(conn)
    usb_found = next(d for d in drives if d["id"] == d_usb["id"])
    assert usb_found["status"] == "ejected"
    assert "Pendrive ejected" in usb_found["exclusion_reason"]
    assert usb_found["is_placement_eligible"] is False

    # Verify operation log entry
    cursor = conn.cursor()
    cursor.execute(
        "SELECT operation, details, status FROM operation_log WHERE operation = 'EJECT_DRIVE'"
    )
    op = cursor.fetchone()
    assert op is not None
    assert op["status"] == "SUCCESS"
    assert "LexarUSB" in op["details"]


@pytest.mark.asyncio
async def test_safe_eject_parity_recovery_fault_tolerance(test_env, tmp_path: Path):
    conn = test_env["conn"]

    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM files")
    conn.execute("DELETE FROM drives")
    conn.commit()

    # 1. Add 2 internal SSD drives
    drive_service.add_drive(conn, str(tmp_path / "SSD1"), "SSD 1", provider_type="local")
    drive_service.add_drive(conn, str(tmp_path / "SSD2"), "SSD 2", provider_type="local")

    # 2. Add 1 external USB pendrive
    usb_path = tmp_path / "Volumes" / "SamsungBar" / "FrankensteinStorage"
    d_usb = drive_service.add_drive(conn, str(usb_path), "Samsung Bar USB", provider_type="local")

    # Upload file with XOR parity striped across the drives
    sample_data = os.urandom(120 * 1024)
    uploaded = await storage_engine.upload_stream(
        conn=conn,
        stream=io.BytesIO(sample_data),
        filename="eject_resilience_test.bin",
        mode="chunked_parity",
    )
    assert uploaded["protection_status"] == "parity"

    # Verify chunks exist on the USB drive
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS count FROM chunks WHERE file_id = ? AND drive_id = ?",
        (uploaded["id"], d_usb["id"]),
    )
    assert cursor.fetchone()["count"] > 0

    # Safely eject the USB pendrive
    eject_res = drive_service.eject_drive(conn, d_usb["id"])
    assert eject_res["status"] == "ejected"
    assert eject_res["volume_name"] == "SamsungBar"

    # Seamless XOR parity reconstruction on retrieve_file
    meta, retrieved_data = storage_engine.retrieve_file(conn, uploaded["id"])
    assert retrieved_data == sample_data

    # Verify download_stream indicates parity reconstruction
    meta, gen, tracker = storage_engine.download_stream(conn, uploaded["id"])
    streamed = b"".join(list(gen))
    assert streamed == sample_data
    assert tracker["was_rebuilt"] is True
