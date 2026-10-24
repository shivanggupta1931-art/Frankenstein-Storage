"""Step 3 Verification: Degraded mode and recovery.

Tests the actual storage path with three local folder drives:
1. 30 MiB file with rotating XOR parity:
   - Takes each drive offline in turn (Drive 1, Drive 2, Drive 3), downloads, and verifies SHA-256 match.
   - Deletes chunks from disk to simulate disk data loss, runs Heal, verifies regenerated chunks and returns to Healthy.
   - Takes 2 drives offline simultaneously, confirms app rejects with 503 FILE_UNRECOVERABLE and returns zero corrupted data.
2. Mirrored file (2-drive redundancy):
   - Takes 1 drive offline, downloads and verifies SHA-256.
   - Takes 2 drives offline, verifies 503 unrecoverable error.
3. Tiny file (< 1 MiB):
   - Confirms mirrored protection.
   - Survives 1 drive offline, verifies SHA-256 match.
   - Rejects with unrecoverable when both replica drives are offline.
"""

import hashlib
import io
import os
import shutil
import tempfile

import pytest

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.crypto.key_manager import key_manager
from backend.app.db.connection import create_connection
from backend.app.db.migrations import run_migrations
from backend.app.providers.local import LocalFolderProvider
from backend.app.services.drive_service import add_drive, patch_drive
from backend.app.services.storage_engine import (
    download_stream,
    get_file_chunks_map,
    heal_pool,
    upload_stream,
    verify_integrity,
)


@pytest.fixture
def step3_real_env():
    temp_dir = tempfile.mkdtemp(prefix="frankenstein_step3_")
    db_file = os.path.join(temp_dir, "step3_vault.db")
    run_migrations(db_path=db_file)
    conn = create_connection(db_file)

    # Master password & unlock
    key_manager.lock()
    key_manager.initialize_or_unlock("MasterKey123!Secure", conn)

    # Use 1 MiB chunk size for realistic multi-chunk parity stripes
    orig_chunk = settings.chunk_size_bytes
    orig_reserve = settings.min_reserve_bytes
    orig_ratio = settings.min_reserve_ratio

    settings.chunk_size_bytes = 1024 * 1024  # 1 MiB chunks
    settings.min_reserve_bytes = 1024 * 1024  # 1 MiB reserve in test isolation
    settings.min_reserve_ratio = 0.0001

    d1_path = os.path.join(temp_dir, "drive_alpha")
    d2_path = os.path.join(temp_dir, "drive_beta")
    d3_path = os.path.join(temp_dir, "drive_gamma")
    os.makedirs(d1_path)
    os.makedirs(d2_path)
    os.makedirs(d3_path)

    d1 = add_drive(conn, d1_path, "Drive Alpha", "local")
    d2 = add_drive(conn, d2_path, "Drive Beta", "local")
    d3 = add_drive(conn, d3_path, "Drive Gamma", "local")
    conn.commit()

    yield {
        "conn": conn,
        "temp_dir": temp_dir,
        "drives": [d1, d2, d3],
        "paths": [d1_path, d2_path, d3_path],
    }

    settings.chunk_size_bytes = orig_chunk
    settings.min_reserve_bytes = orig_reserve
    settings.min_reserve_ratio = orig_ratio
    conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_30mb_parity_file_survives_each_drive_offline_and_heals(step3_real_env):
    conn = step3_real_env["conn"]
    drives = step3_real_env["drives"]
    d1, d2, d3 = drives[0], drives[1], drives[2]

    # Generate real 30 MiB payload (30 * 1024 * 1024 bytes)
    # With 1 MiB chunk size: 30 data chunks + 15 parity chunks = 45 chunks (15 stripes of 3)
    payload_30mb = os.urandom(30 * 1024 * 1024)
    expected_hash = hashlib.sha256(payload_30mb).hexdigest()

    file_rec = await upload_stream(
        conn,
        stream=io.BytesIO(payload_30mb),
        filename="big_dataset_30mb.dat",
        mode="auto",
    )

    assert file_rec["protection_status"] == "parity"
    assert file_rec["size"] == 30 * 1024 * 1024
    assert file_rec["sha256"] == expected_hash

    # Confirm all 3 drives received chunks
    chunks = get_file_chunks_map(conn, file_rec["id"])
    assert len(chunks) == 45, f"Expected 45 chunks (30 data + 15 parity), got {len(chunks)}"
    chunks_by_drive = {}
    for c in chunks:
        chunks_by_drive.setdefault(c["drive_id"], []).append(c)
    assert set(chunks_by_drive.keys()) == {d1["id"], d2["id"], d3["id"]}

    # --- SUBTEST 1: Take Drive 1 (Alpha) offline, download, verify SHA-256
    patch_drive(conn, d1["id"], simulated_offline=True)
    meta, stream, ctx = download_stream(conn, file_rec["id"])
    dl_bytes = b"".join(stream)
    assert hashlib.sha256(dl_bytes).hexdigest() == expected_hash
    assert ctx["was_rebuilt"] is True, "Must report rebuilt from parity"
    patch_drive(conn, d1["id"], simulated_offline=False)

    # --- SUBTEST 2: Take Drive 2 (Beta) offline, download, verify SHA-256
    patch_drive(conn, d2["id"], simulated_offline=True)
    meta, stream, ctx = download_stream(conn, file_rec["id"])
    dl_bytes = b"".join(stream)
    assert hashlib.sha256(dl_bytes).hexdigest() == expected_hash
    assert ctx["was_rebuilt"] is True, "Must report rebuilt from parity"
    patch_drive(conn, d2["id"], simulated_offline=False)

    # --- SUBTEST 3: Take Drive 3 (Gamma) offline, download, verify SHA-256
    patch_drive(conn, d3["id"], simulated_offline=True)
    meta, stream, ctx = download_stream(conn, file_rec["id"])
    dl_bytes = b"".join(stream)
    assert hashlib.sha256(dl_bytes).hexdigest() == expected_hash
    assert ctx["was_rebuilt"] is True, "Must report rebuilt from parity"
    patch_drive(conn, d3["id"], simulated_offline=False)

    # --- SUBTEST 4: Test Heal after real chunk deletion from disk
    # Delete all chunk files belonging to Drive 1 from disk using provider
    d1_provider = LocalFolderProvider(d1["path"])
    d1_chunks = chunks_by_drive[d1["id"]]
    for c in d1_chunks:
        d1_provider.delete_chunk(c["chunk_id"])

    # Verify that integrity check detects degraded system
    integrity_before = verify_integrity(conn, file_rec["id"])
    assert integrity_before["status"] == "degraded"

    # Run Heal action
    heal_result = heal_pool(conn)
    assert heal_result["status"] == "healed"
    assert heal_result["files_healed"] >= 1
    assert heal_result["chunks_rebuilt"] == len(d1_chunks)

    # Verify every deleted chunk was reconstructed onto Drive 1 with correct hash
    for c in d1_chunks:
        restored_bytes = d1_provider.get_chunk(c["chunk_id"])
        assert hashlib.sha256(restored_bytes).hexdigest() == c["sha256"]

    # Integrity should now be 100% Healthy
    integrity_after = verify_integrity(conn, file_rec["id"])
    assert integrity_after["status"] == "healthy"

    # --- SUBTEST 5: Two drives offline -> App must say unrecoverable and return zero corrupted data
    patch_drive(conn, d1["id"], simulated_offline=True)
    patch_drive(conn, d2["id"], simulated_offline=True)

    with pytest.raises(AppError) as exc_info:
        _, stream, _ = download_stream(conn, file_rec["id"])
        _ = b"".join(stream)  # Should fail immediately on unrecoverable stripe

    assert exc_info.value.status_code == 503
    assert "unrecoverable" in exc_info.value.message.lower()
    assert "2 or more drives are offline" in exc_info.value.message

    patch_drive(conn, d1["id"], simulated_offline=False)
    patch_drive(conn, d2["id"], simulated_offline=False)


@pytest.mark.asyncio
async def test_mirrored_file_survives_one_offline_and_fails_on_two(step3_real_env):
    conn = step3_real_env["conn"]

    # Explicit mirrored file (2 MiB)
    mirror_data = os.urandom(2 * 1024 * 1024)
    expected_hash = hashlib.sha256(mirror_data).hexdigest()

    file_rec = await upload_stream(
        conn,
        stream=io.BytesIO(mirror_data),
        filename="mirrored_archive.tar",
        mode="mirrored",
    )
    assert file_rec["protection_status"] == "mirrored"

    chunks = get_file_chunks_map(conn, file_rec["id"])
    stripes = {}
    for c in chunks:
        stripes.setdefault(c["stripe_index"], []).append(c)

    # Determine which two drives hold stripe 0
    s0_drives = [c["drive_id"] for c in stripes[0]]
    assert len(s0_drives) == 2
    active_d1, active_d2 = s0_drives[0], s0_drives[1]

    # Take first mirror drive offline -> downloads successfully from second drive
    patch_drive(conn, active_d1, simulated_offline=True)
    meta, stream, ctx = download_stream(conn, file_rec["id"])
    dl_bytes = b"".join(stream)
    assert hashlib.sha256(dl_bytes).hexdigest() == expected_hash
    assert ctx["was_rebuilt"] is True

    # Take second mirror drive offline as well -> unrecoverable 503
    patch_drive(conn, active_d2, simulated_offline=True)
    with pytest.raises(AppError) as exc_info:
        _, stream, _ = download_stream(conn, file_rec["id"])
        _ = b"".join(stream)

    assert exc_info.value.status_code == 503
    assert "unrecoverable" in exc_info.value.message.lower()
    assert "both mirrored drives are offline" in exc_info.value.message

    # Bring both back and heal
    patch_drive(conn, active_d1, simulated_offline=False)
    patch_drive(conn, active_d2, simulated_offline=False)
    heal_res = heal_pool(conn)
    assert heal_res["status"] in ("healthy", "healed")


@pytest.mark.asyncio
async def test_tiny_file_mirroring_and_offline_behavior(step3_real_env):
    conn = step3_real_env["conn"]

    # Tiny file < 1 MiB (e.g. 128 KiB)
    tiny_data = os.urandom(128 * 1024)
    expected_hash = hashlib.sha256(tiny_data).hexdigest()

    file_rec = await upload_stream(
        conn,
        stream=io.BytesIO(tiny_data),
        filename="config.json",
        mode="auto",
    )
    # Tiny file with 3 drives online should automatically be mirrored
    assert file_rec["protection_status"] == "mirrored"
    assert file_rec["protection_label"] == "Mirrored (2x)"

    chunks = get_file_chunks_map(conn, file_rec["id"])
    assert len(chunks) == 2
    d_a, d_b = chunks[0]["drive_id"], chunks[1]["drive_id"]
    assert d_a != d_b

    # Take drive A offline -> successfully downloads from drive B
    patch_drive(conn, d_a, simulated_offline=True)
    _, stream, ctx = download_stream(conn, file_rec["id"])
    assert hashlib.sha256(b"".join(stream)).hexdigest() == expected_hash

    # Take drive B offline too -> fails with 503 unrecoverable
    patch_drive(conn, d_b, simulated_offline=True)
    with pytest.raises(AppError) as exc_info:
        _, stream, _ = download_stream(conn, file_rec["id"])
        _ = b"".join(stream)
    assert exc_info.value.status_code == 503
    assert "unrecoverable" in exc_info.value.message.lower()

    # Restore drives
    patch_drive(conn, d_a, simulated_offline=False)
    patch_drive(conn, d_b, simulated_offline=False)
