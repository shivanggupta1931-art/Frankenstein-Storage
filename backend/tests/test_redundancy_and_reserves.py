"""Unit and integration tests for Smart Placement, Redundancy, Reserves, and Re-protection."""

import hashlib
import io
import os
from pathlib import Path
import pytest

from backend.app.core.config import settings, calculate_reserve
from backend.app.core.errors import AppError
from backend.app.services.drive_service import (
    calculate_pooled_overview,
    list_drives,
    patch_drive,
    add_drive,
)
from backend.app.services.storage_engine import (
    download_stream,
    get_available_drives_for_storage,
    get_file_chunks_map,
    pick_placement_drives,
    reprotect_all_files,
    reprotect_file,
    upload_stream,
    verify_integrity,
)


@pytest.mark.asyncio
async def test_reserve_calculation_and_low_space_exclusion(test_env):
    """Test 1: Drive past reserve is marked low space and excluded from placement."""
    conn = test_env["conn"]
    drives = list_drives(conn)
    assert len(drives) >= 3

    # Check initial status: all drives in test_env have reserve configured and are eligible
    for d in drives:
        assert d["is_placement_eligible"] is True
        assert d["is_low_space"] is False
        assert d["exclusion_reason"] is None
        assert d["reserve_bytes"] > 0

    # Test reserve function calculation rules
    # 2 GiB or 5%, capped at 50% for tiny drives
    assert calculate_reserve(100 * 1024**3) == max(settings.min_reserve_bytes, int(100 * 1024**3 * settings.min_reserve_ratio))
    assert calculate_reserve(0) == 0

    # Simulate extreme reserve requirement that exceeds available free space
    orig_reserve = settings.min_reserve_bytes
    try:
        # Set reserve to 100 TB so all drives are below reserve
        settings.min_reserve_bytes = 100 * 1024 * 1024 * 1024 * 1024
        drives_after = list_drives(conn)
        for d in drives_after:
            assert d["is_low_space"] is True
            assert d["is_placement_eligible"] is False
            assert "Low space" in (d["exclusion_reason"] or "")

        # Available drives for placement should be empty
        avail = get_available_drives_for_storage(conn)
        assert len(avail) == 0

        # Attempting upload must fail cleanly with 507 Insufficient Storage
        with pytest.raises(AppError) as exc_info:
            await upload_stream(
                conn=conn,
                stream=io.BytesIO(b"test"),
                filename="blocked.txt",
            )
        assert exc_info.value.status_code == 507
    finally:
        settings.min_reserve_bytes = orig_reserve


@pytest.mark.asyncio
async def test_small_file_mirrored_across_two_drives(test_env):
    """Test 2: Small file (< 1 MiB) stores 2 copies on different drives instead of WHOLE single copy."""
    conn = test_env["conn"]
    small_data = b"Hello, small resilient file stored on Frankenstein pool!" * 10
    expected_hash = hashlib.sha256(small_data).hexdigest()

    uploaded = await upload_stream(
        conn=conn,
        stream=io.BytesIO(small_data),
        filename="small_file.txt",
        overwrite=True,
        mode="auto",
    )

    assert uploaded["status"] == "complete"
    assert uploaded["storage_mode"] == "mirrored"
    assert uploaded["protection_status"] == "mirrored"
    assert uploaded["unprotected_reason"] is None

    chunks = get_file_chunks_map(conn, uploaded["id"])
    assert len(chunks) == 2
    # Verify both copies reside on different physical drives
    assert chunks[0]["drive_id"] != chunks[1]["drive_id"]

    # Verify download integrity
    meta, gen, tracker = download_stream(conn, uploaded["id"])
    assert b"".join(gen) == small_data
    assert tracker["was_rebuilt"] is False

    # Simulate taking Drive 0 offline: file should still download from Drive 1!
    failed_drive_id = chunks[0]["drive_id"]
    patch_drive(conn, failed_drive_id, simulated_offline=True)

    meta, gen, tracker = download_stream(conn, uploaded["id"])
    assert b"".join(gen) == small_data
    assert tracker["was_rebuilt"] is True  # Rebuilt / read from mirror copy


@pytest.mark.asyncio
async def test_two_drives_pool_always_mirrors(test_env):
    """Test 3: With only 2 online drives, all files are mirrored and survive drive failure."""
    conn = test_env["conn"]
    drives = test_env["drives"]

    # Take Drive 3 offline so exactly 2 drives are available
    patch_drive(conn, drives[2]["id"], simulated_offline=True)
    avail = get_available_drives_for_storage(conn)
    assert len(avail) == 2

    # Upload multi-chunk file (e.g. 3 chunks = 3 * 64 KB = 192 KB)
    chunk_size = settings.chunk_size_bytes
    data = os.urandom(chunk_size * 3)
    expected_hash = hashlib.sha256(data).hexdigest()

    uploaded = await upload_stream(
        conn=conn,
        stream=io.BytesIO(data),
        filename="two_drive_mirror.bin",
        overwrite=True,
        mode="auto",
    )

    assert uploaded["status"] == "complete"
    assert uploaded["storage_mode"] == "mirrored"
    assert uploaded["protection_status"] == "mirrored"

    chunks = get_file_chunks_map(conn, uploaded["id"])
    # 3 chunks * 2 copies = 6 chunk records total
    assert len(chunks) == 6

    # Verify each stripe has 2 copies on 2 distinct drives
    stripes = {}
    for c in chunks:
        stripes.setdefault(c["stripe_index"], []).append(c)
    assert len(stripes) == 3
    for s_idx, s_chunks in stripes.items():
        assert len(s_chunks) == 2
        assert s_chunks[0]["drive_id"] != s_chunks[1]["drive_id"]

    # Take Drive 1 offline (now only Drive 2 remains online)
    patch_drive(conn, drives[0]["id"], simulated_offline=True)

    # Download must succeed by recovering all chunks from mirror copies
    meta, gen, tracker = download_stream(conn, uploaded["id"])
    downloaded = b"".join(gen)
    assert downloaded == data
    assert hashlib.sha256(downloaded).hexdigest() == expected_hash
    assert tracker["was_rebuilt"] is True


@pytest.mark.asyncio
async def test_reprotect_and_reprotect_all_action(test_env):
    """Test 4: Unprotected file can be re-protected without corrupting data."""
    conn = test_env["conn"]
    drives = test_env["drives"]

    # Upload a file in explicit whole (unprotected) mode
    data = b"Unprotected single drive file that needs re-protection! " * 50
    expected_hash = hashlib.sha256(data).hexdigest()

    uploaded = await upload_stream(
        conn=conn,
        stream=io.BytesIO(data),
        filename="unprotected_doc.txt",
        overwrite=True,
        mode="whole",
    )
    assert uploaded["storage_mode"] == "whole"
    assert uploaded["protection_status"] == "unprotected"

    # Re-protect single file
    rep = reprotect_file(conn, uploaded["id"])
    assert rep["status"] == "reprotected"
    assert rep["protection_status"] in ("parity", "mirrored")

    # Verify data integrity is 100% preserved
    meta, gen, tracker = download_stream(conn, uploaded["id"])
    assert b"".join(gen) == data
    assert meta["sha256"] == expected_hash

    # Re-protect all
    summary = reprotect_all_files(conn)
    assert summary["status"] == "completed"
    assert summary["failed"] == 0


def test_honest_capacity_metrics(test_env):
    """Test 5: Overview reports raw_capacity, usable_capacity, and free_usable_space honestly."""
    conn = test_env["conn"]
    drives = list_drives(conn)
    overview = calculate_pooled_overview(conn, drives)

    # Check presence of the three honest figures
    assert "raw_capacity" in overview
    assert "usable_capacity" in overview
    assert "free_usable_space" in overview
    assert overview["raw_capacity"] > 0
    assert overview["usable_capacity"] > 0

    # Descriptions
    assert "raw_capacity_description" in overview
    assert "usable_capacity_description" in overview
    assert "free_usable_space_description" in overview

    # Redundancy state
    assert overview["redundancy_mode"] in ("parity", "mirrored", "unprotected")
    assert overview["drives_eligible"] == len(drives)
