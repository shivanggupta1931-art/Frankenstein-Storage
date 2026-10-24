"""Tests for Smart Upload Decisions: modes, preferences, migrations, and fault tolerance."""

import hashlib
import io
import os

import pytest

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.services.drive_service import patch_drive
from backend.app.services.storage_engine import (
    download_stream,
    upload_stream,
    verify_integrity,
)


@pytest.mark.asyncio
async def test_migration_and_upload_preferences_api(async_client, test_env):
    """Tests 1, 3, 4, 12: Migration 0002, default preference, saving, retrieving, updating, and clearing preference."""
    # 1. First-time check: default should have no saved preference
    res = await async_client.get("/api/v1/settings/preferences")
    assert res.status_code == 200
    data = res.json()
    assert data["preferred_mode"] is None
    assert data["threshold_bytes"] == settings.smart_upload_threshold_bytes

    # 2. Save preference for 'whole' mode
    res = await async_client.put("/api/v1/settings/preferences", json={"preferred_mode": "whole"})
    assert res.status_code == 200
    assert res.json()["preferred_mode"] == "whole"

    # 3. Retrieve saved preference
    res = await async_client.get("/api/v1/settings/preferences")
    assert res.status_code == 200
    assert res.json()["preferred_mode"] == "whole"

    # 4. Update preference to 'chunked_parity'
    res = await async_client.put(
        "/api/v1/settings/preferences", json={"preferred_mode": "chunked_parity"}
    )
    assert res.status_code == 200
    assert res.json()["preferred_mode"] == "chunked_parity"

    # 5. Clear saved preference (set to None)
    res = await async_client.put("/api/v1/settings/preferences", json={"preferred_mode": None})
    assert res.status_code == 200
    assert res.json()["preferred_mode"] is None

    # Verify cleared in DB
    res = await async_client.get("/api/v1/settings/preferences")
    assert res.json()["preferred_mode"] is None


@pytest.mark.asyncio
async def test_backend_rejection_of_unsupported_storage_modes(async_client, test_env):
    """Test 6: Backend rejection of unsupported storage modes."""
    # Invalid mode in preferences
    res = await async_client.put(
        "/api/v1/settings/preferences", json={"preferred_mode": "invalid_mode_xyz"}
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_STORAGE_MODE"

    # Invalid mode in file upload
    res = await async_client.post(
        "/api/v1/files/upload?name=bad_mode.txt&mode=super_compression",
        content=b"sample payload",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_STORAGE_MODE"


@pytest.mark.asyncio
async def test_whole_object_encryption_decryption_and_integrity(test_env):
    """Test 7, 13: Whole-object encryption, decryption, downloading, and integrity verification."""
    conn = test_env["conn"]
    payload = b"Small whole-object encrypted content without parity overhead! " * 20
    expected_hash = hashlib.sha256(payload).hexdigest()

    # Upload in whole mode
    uploaded = await upload_stream(
        conn=conn,
        stream=io.BytesIO(payload),
        filename="whole_test.txt",
        folder="/",
        overwrite=True,
        mode="whole",
    )
    assert uploaded["status"] == "complete"
    assert uploaded["storage_mode"] == "whole"
    assert uploaded["size"] == len(payload)
    assert uploaded["sha256"] == expected_hash
    assert uploaded["stripes"] == 0

    # Verify chunks table has exactly 1 chunk (no parity chunks)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_parity, stripe_index, position FROM chunks WHERE file_id = ?", (uploaded["id"],)
    )
    chunks = cursor.fetchall()
    assert len(chunks) == 1
    assert chunks[0]["is_parity"] == 0
    assert chunks[0]["stripe_index"] == 0

    # Download whole object
    meta, gen, tracker = download_stream(conn, uploaded["id"])
    downloaded = b"".join(gen)
    assert downloaded == payload
    assert hashlib.sha256(downloaded).hexdigest() == expected_hash
    assert tracker["was_rebuilt"] is False

    # Integrity verification
    report = verify_integrity(conn, file_id=uploaded["id"])
    assert report["status"] == "healthy"
    assert report["files"][0]["state"] == "healthy"


@pytest.mark.asyncio
async def test_whole_mode_vs_chunked_parity_offline_behavior(test_env):
    """Tests 8, 9: Simulated drive failure on chunked mode recovers, while whole mode reports drive unavailable."""
    conn = test_env["conn"]
    chunk_size = settings.chunk_size_bytes

    # 1. Upload file in whole mode
    whole_data = b"Whole mode payload data"
    whole_file = await upload_stream(
        conn=conn,
        stream=io.BytesIO(whole_data),
        filename="whole_file.txt",
        overwrite=True,
        mode="whole",
    )

    # 2. Upload file in chunked parity mode
    chunked_data = os.urandom(chunk_size * 2)
    chunked_file = await upload_stream(
        conn=conn,
        stream=io.BytesIO(chunked_data),
        filename="chunked_file.bin",
        overwrite=True,
        mode="chunked_parity",
    )

    # Find which drive holds the whole file's chunk
    cursor = conn.cursor()
    cursor.execute("SELECT drive_id FROM chunks WHERE file_id = ?", (whole_file["id"],))
    whole_drive_id = cursor.fetchone()["drive_id"]

    # Take that drive offline
    patch_drive(conn, whole_drive_id, simulated_offline=True)

    # Whole mode download should fail with 503 because it has no parity redundancy
    with pytest.raises(AppError) as exc_info:
        meta, gen, _ = download_stream(conn, whole_file["id"])
        b"".join(gen)
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "DRIVE_UNAVAILABLE"

    # Integrity check reports whole file as corrupt/unrecoverable when its drive is offline
    report = verify_integrity(conn, file_id=whole_file["id"])
    assert report["files"][0]["state"] == "corrupt"

    # Chunked parity file should STILL download and recover from parity successfully
    meta, gen, tracker = download_stream(conn, chunked_file["id"])
    downloaded_chunked = b"".join(gen)
    assert downloaded_chunked == chunked_data
    assert tracker["was_rebuilt"] is True

    # Restore drive
    patch_drive(conn, whole_drive_id, simulated_offline=False)

    # Now whole mode downloads cleanly again
    meta, gen, _ = download_stream(conn, whole_file["id"])
    assert b"".join(gen) == whole_data


@pytest.mark.asyncio
async def test_insufficient_drives_guard_per_mode(test_env):
    """Test mode-specific drive requirements: chunked requires 3 drives, whole requires 1."""
    conn = test_env["conn"]
    drives = test_env["drives"]

    # Take Drive 2 offline (leaves 2 drives online)
    patch_drive(conn, drives[2]["id"], simulated_offline=True)

    # Chunked parity upload must be rejected because < 3 drives are available
    with pytest.raises(AppError) as exc_info:
        await upload_stream(
            conn=conn,
            stream=io.BytesIO(b"data"),
            filename="insufficient.txt",
            overwrite=True,
            mode="chunked_parity",
        )
    assert exc_info.value.status_code == 507
    assert exc_info.value.code == "INSUFFICIENT_STORAGE"

    # Whole mode upload still succeeds because 2 drives are available (>= 1 required)
    uploaded = await upload_stream(
        conn=conn,
        stream=io.BytesIO(b"whole mode succeeds with 2 drives"),
        filename="whole_success.txt",
        overwrite=True,
        mode="whole",
    )
    assert uploaded["status"] == "complete"
    assert uploaded["storage_mode"] == "whole"

    # Restore drive
    patch_drive(conn, drives[2]["id"], simulated_offline=False)


@pytest.mark.asyncio
async def test_both_modes_http_upload_download(async_client, test_env):
    """Test 13, 14: End-to-end HTTP upload and download of both modes."""
    # 1. Whole mode upload via HTTP
    data_whole = b"HTTP whole object upload content! " * 10
    res_whole = await async_client.post(
        "/api/v1/files/upload?name=http_whole.txt&mode=whole&overwrite=true",
        content=data_whole,
    )
    assert res_whole.status_code == 200
    info_whole = res_whole.json()
    assert info_whole["storage_mode"] == "whole"

    # 2. Chunked parity mode upload via HTTP
    data_chunked = b"HTTP chunked parity upload content! " * 50
    res_chunked = await async_client.post(
        "/api/v1/files/upload?name=http_chunked.txt&mode=chunked_parity&overwrite=true",
        content=data_chunked,
    )
    assert res_chunked.status_code == 200
    info_chunked = res_chunked.json()
    assert info_chunked["storage_mode"] == "chunked_parity"

    # 3. GET /api/v1/files returns both files with their respective storage_mode
    res_files = await async_client.get("/api/v1/files")
    assert res_files.status_code == 200
    files = res_files.json()
    found_whole = next(f for f in files if f["id"] == info_whole["id"])
    found_chunked = next(f for f in files if f["id"] == info_chunked["id"])
    assert found_whole["storage_mode"] == "whole"
    assert found_whole["health"] == "Healthy"
    assert found_chunked["storage_mode"] == "chunked_parity"
    assert found_chunked["health"] == "Healthy"

    # 4. Download both via HTTP
    down_whole = await async_client.get(f"/api/v1/files/{info_whole['id']}/download")
    assert down_whole.status_code == 200
    assert down_whole.content == data_whole

    down_chunked = await async_client.get(f"/api/v1/files/{info_chunked['id']}/download")
    assert down_chunked.status_code == 200
    assert down_chunked.content == data_chunked
