"""Tests 1, 2, 3, 4, 5, 7, 8: Storage engine, crypto, parity, failure recovery, and restart."""

import hashlib
import io
import os
from pathlib import Path

import pytest

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.crypto.cipher import decrypt_chunk
from backend.app.crypto.key_manager import key_manager
from backend.app.services.drive_service import patch_drive
from backend.app.services.storage_engine import (
    download_stream,
    upload_stream,
    verify_integrity,
)


@pytest.mark.asyncio
async def test_round_trip_various_payload_sizes(test_env):
    """Test 1: Chunk, encrypt, reassemble round trip: empty, 1 byte, exactly one stripe, multi-MB."""
    conn = test_env["conn"]
    chunk_size = settings.chunk_size_bytes

    payloads = {
        "empty.bin": b"",
        "single_byte.bin": b"Z",
        "one_stripe.bin": os.urandom(2 * chunk_size),
        "multi_stripe.bin": os.urandom(5 * chunk_size + 1234),
    }

    for filename, data in payloads.items():
        stream = io.BytesIO(data)
        uploaded = await upload_stream(conn, stream, filename, folder="/", overwrite=True)
        assert uploaded["status"] == "complete"
        assert uploaded["size"] == len(data)
        assert uploaded["sha256"] == hashlib.sha256(data).hexdigest()

        # Download and verify
        meta, gen, _ = download_stream(conn, uploaded["id"])
        downloaded_bytes = b"".join(gen)
        assert downloaded_bytes == data
        assert hashlib.sha256(downloaded_bytes).hexdigest() == uploaded["sha256"]


def test_wrong_password_and_tampered_ciphertext(test_env):
    """Test 2: Wrong password rejected; tampered ciphertext detected."""
    conn = test_env["conn"]

    # 1. Wrong password rejected
    with pytest.raises(AppError) as exc_info:
        key_manager.initialize_or_unlock("completely-wrong-password", conn)
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_PASSWORD"

    # Restore correct key
    key_manager.initialize_or_unlock(test_env["password"], conn)
    key = key_manager.get_key()

    # 2. Tampered ciphertext detected
    valid_payload = b"Hello Frankenstein Storage Vault!"
    from backend.app.crypto.cipher import encrypt_chunk
    enc_chunk = bytearray(encrypt_chunk(valid_payload, key))

    # Flip one byte in the ciphertext portion (after 12-byte nonce)
    enc_chunk[15] ^= 0xFF

    with pytest.raises(AppError) as exc_info:
        decrypt_chunk(bytes(enc_chunk), key)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "CIPHERTEXT_TAMPERED"


@pytest.mark.asyncio
async def test_single_drive_offline_recovery(test_env):
    """Test 3: For each single drive offline, download is byte-identical (hash match)."""
    conn = test_env["conn"]
    data = os.urandom(settings.chunk_size_bytes * 3 + 456)
    expected_hash = hashlib.sha256(data).hexdigest()

    uploaded = await upload_stream(conn, io.BytesIO(data), "redundant_test.dat", overwrite=True)
    file_id = uploaded["id"]

    drives = test_env["drives"]
    assert len(drives) == 3

    # Test taking each drive offline one by one
    for target_drive in drives:
        # Take this drive offline
        patch_drive(conn, target_drive["id"], simulated_offline=True)

        meta, gen, was_rebuilt = download_stream(conn, file_id)
        downloaded = b"".join(gen)
        assert downloaded == data
        assert hashlib.sha256(downloaded).hexdigest() == expected_hash

        # Bring drive back online
        patch_drive(conn, target_drive["id"], simulated_offline=False)


@pytest.mark.asyncio
async def test_two_drives_offline_fails_with_503(test_env):
    """Test 4: Two drives offline: clear 503, no partial or corrupt file returned."""
    conn = test_env["conn"]
    data = os.urandom(settings.chunk_size_bytes * 2)

    uploaded = await upload_stream(conn, io.BytesIO(data), "fail_test.dat", overwrite=True)
    file_id = uploaded["id"]

    drives = test_env["drives"]
    # Take two drives offline simultaneously
    patch_drive(conn, drives[0]["id"], simulated_offline=True)
    patch_drive(conn, drives[1]["id"], simulated_offline=True)

    with pytest.raises(AppError) as exc_info:
        meta, gen, _ = download_stream(conn, file_id)
        # Consuming generator triggers stripe read
        b"".join(gen)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "PARITY_RECOVERY_FAILED"

    # Restore drives
    patch_drive(conn, drives[0]["id"], simulated_offline=False)
    patch_drive(conn, drives[1]["id"], simulated_offline=False)


@pytest.mark.asyncio
async def test_disk_corruption_and_parity_rebuild(test_env):
    """Test 5: Flip one byte on disk: verify reports corrupt and download still rebuilds from parity."""
    conn = test_env["conn"]
    data = os.urandom(settings.chunk_size_bytes * 2)
    expected_hash = hashlib.sha256(data).hexdigest()

    uploaded = await upload_stream(conn, io.BytesIO(data), "corrupt_test.dat", overwrite=True)
    file_id = uploaded["id"]

    # Find first chunk on disk
    cursor = conn.cursor()
    cursor.execute("SELECT c.chunk_id, d.path FROM chunks c JOIN drives d ON c.drive_id = d.id WHERE c.file_id = ? LIMIT 1", (file_id,))
    row = cursor.fetchone()
    chunk_file = (test_env["tmp_path"] / "drives" / Path(row["path"]).name / ".frankenstein" / "chunks" / row["chunk_id"][:2] / row["chunk_id"][2:4] / row["chunk_id"])

    assert chunk_file.exists()
    content = bytearray(chunk_file.read_bytes())
    content[-1] ^= 0x01  # Flip one byte on disk
    chunk_file.write_bytes(content)

    # 1. Verify reports corrupt
    report = verify_integrity(conn, file_id=file_id)
    assert report["corrupted_chunks"] >= 1
    assert report["status"] in ("degraded", "corrupt")

    # 2. Download still successfully rebuilds from parity
    meta, gen, tracker = download_stream(conn, file_id)
    downloaded = b"".join(gen)
    assert tracker["was_rebuilt"] is True
    assert downloaded == data
    assert hashlib.sha256(downloaded).hexdigest() == expected_hash


@pytest.mark.asyncio
async def test_upload_midstream_failure_leaves_no_debris(test_env):
    """Test 7: Upload failure mid-stream leaves no complete file and no temp debris."""
    conn = test_env["conn"]

    class FailingStream:
        def __init__(self):
            self.bytes_sent = 0

        def read(self, size):
            if self.bytes_sent > settings.chunk_size_bytes:
                raise RuntimeError("Network cable cut during upload!")
            self.bytes_sent += size
            return b"A" * size

    with pytest.raises(AppError):
        await upload_stream(conn, FailingStream(), "failing.dat", overwrite=True)

    # Check database: no complete file
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM files WHERE name = 'failing.dat'")
    rows = cursor.fetchall()
    assert all(r["status"] != "complete" for r in rows)

    # Check disks: no orphaned temp files
    for d_path in test_env["drive_paths"]:
        tmp_dir = d_path / ".frankenstein" / "tmp"
        if tmp_dir.exists():
            assert list(tmp_dir.glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_restart_new_app_instance(test_env):
    """Test 8: Restart (new app instance, same DB): files still download."""
    conn = test_env["conn"]
    data = os.urandom(settings.chunk_size_bytes * 3)
    uploaded = await upload_stream(conn, io.BytesIO(data), "restart_test.dat", overwrite=True)
    file_id = uploaded["id"]

    # Simulate shutdown: lock vault and close connection
    key_manager.lock()
    assert not key_manager.is_unlocked()

    # Simulate new app instance opening the same SQLite file
    from backend.app.db.connection import create_connection
    new_conn = create_connection(test_env["db_file"])
    try:
        # Unlock vault with password
        key_manager.initialize_or_unlock(test_env["password"], new_conn)
        assert key_manager.is_unlocked()

        # Download file
        meta, gen, _ = download_stream(new_conn, file_id)
        downloaded = b"".join(gen)
        assert downloaded == data
        assert hashlib.sha256(downloaded).hexdigest() == uploaded["sha256"]
    finally:
        new_conn.close()
