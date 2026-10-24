import io
import os

import pytest

from backend.app.core.config import settings
from backend.app.services.drive_service import (
    calculate_pooled_overview,
    list_drives,
    patch_drive,
)
from backend.app.services.storage_engine import (
    download_stream,
    get_file_chunks_map,
    reprotect_file,
    upload_stream,
)


@pytest.mark.asyncio
async def test_full_placement_and_redundancy_suite(test_env):
    conn = test_env["conn"]
    drive1 = test_env["drives"][0]
    drive2 = test_env["drives"][1]
    drive3 = test_env["drives"][2]

    # --- TEST 1: 3+ Drives with Large File (>= 1 MiB) -> Rotating XOR Parity
    # 1.25 MiB payload
    large_data = os.urandom(1024 * 1024 + 256 * 1024)
    file_large = await upload_stream(
        conn, stream=io.BytesIO(large_data), filename="large_video.mp4", mode="auto"
    )
    assert file_large["protection_status"] == "parity"
    assert file_large["protection_label"] == "Parity-protected"
    assert file_large["unprotected_reason"] is None

    # Verify chunks placement:
    chunks = get_file_chunks_map(conn, file_large["id"])
    assert len(chunks) > 0
    # Chunks within each stripe must be on distinct drives and parity separate from data
    stripes = {}
    for c in chunks:
        stripes.setdefault(c["stripe_index"], []).append(c)

    for s_idx, s_chunks in stripes.items():
        d_ids = [c["drive_id"] for c in s_chunks]
        assert len(d_ids) == len(set(d_ids)), (
            f"Stripe {s_idx} chunks must be on distinct drives: {d_ids}"
        )
        parity_chunks = [c for c in s_chunks if c["is_parity"]]
        data_chunks = [c for c in s_chunks if not c["is_parity"]]
        for p in parity_chunks:
            assert p["drive_id"] not in [d["drive_id"] for d in data_chunks]

    # Download & verify integrity matches byte-for-byte
    file_meta, dl_stream, ctx = download_stream(conn, file_large["id"])
    dl_bytes = b"".join(dl_stream)
    assert dl_bytes == large_data
    assert ctx["was_rebuilt"] is False

    # --- TEST 2: Small File (< 1 MiB) with 3 drives -> Mirrored across 2 distinct drives
    small_data = b"Small file content with high value" * 50
    file_small = await upload_stream(
        conn, stream=io.BytesIO(small_data), filename="notes.txt", mode="auto"
    )
    assert file_small["protection_status"] == "mirrored"
    assert file_small["protection_label"] == "Mirrored (2x)"
    sm_chunks = get_file_chunks_map(conn, file_small["id"])
    assert len(sm_chunks) == 2, "Small file with 2+ drives must have 2 mirrored copies"
    assert sm_chunks[0]["drive_id"] != sm_chunks[1]["drive_id"], (
        "Mirrored copies must be on distinct drives"
    )

    # Download small file
    _, dl_sm_stream, sm_rebuilt = download_stream(conn, file_small["id"])
    assert b"".join(dl_sm_stream) == small_data

    # --- TEST 3: 2-Drives Pool -> All Files Mirrored & Survives 1 Drive Offline
    # Simulate drive 3 offline
    patch_drive(conn, drive3["id"], simulated_offline=True)

    file_2d = await upload_stream(
        conn,
        stream=io.BytesIO(b"Document content under 2 drives pool" * 100),
        filename="two_drives_document.pdf",
        mode="auto",
    )
    assert file_2d["protection_status"] == "mirrored"
    assert file_2d["protection_label"] == "Mirrored (2x)"
    chunks_2d = get_file_chunks_map(conn, file_2d["id"])
    assert len(chunks_2d) == 2
    assert set([c["drive_id"] for c in chunks_2d]) == {drive1["id"], drive2["id"]}

    # Take Drive 1 offline too -> now only Drive 2 is online with copy 1!
    patch_drive(conn, drive1["id"], simulated_offline=True)
    _, dl_survived, ctx_2d = download_stream(conn, file_2d["id"])
    assert b"".join(dl_survived) == b"Document content under 2 drives pool" * 100
    assert ctx_2d["was_rebuilt"] is True, (
        "Should have been retrieved from mirror replica with was_rebuilt=True"
    )

    # Bring drives back online
    patch_drive(conn, drive1["id"], simulated_offline=False)
    patch_drive(conn, drive3["id"], simulated_offline=False)

    # --- TEST 4: Low Space Exclusion
    orig_reserve = settings.min_reserve_bytes
    try:
        # Set reserve higher than available space to simulate low space
        settings.min_reserve_bytes = 500 * 1024 * 1024 * 1024 * 1024  # 500 TiB
        d_list = list_drives(conn)
        for d in d_list:
            assert d["is_low_space"] is True
            assert d["is_placement_eligible"] is False
            assert "Low space" in d["exclusion_reason"]
    finally:
        settings.min_reserve_bytes = orig_reserve

    # --- TEST 5: Re-protect Unprotected File
    # Manually upload a legacy "whole" file on drive 1
    unprot_data = b"Legacy single-drive data" * 200
    patch_drive(conn, drive2["id"], simulated_offline=True)
    patch_drive(conn, drive3["id"], simulated_offline=True)
    file_unprot = await upload_stream(
        conn, stream=io.BytesIO(unprot_data), filename="single_drive.dat", mode="whole"
    )
    assert file_unprot["protection_status"] == "unprotected"
    assert "Only 1 drive available" in file_unprot["unprotected_reason"]

    # Bring drive 2 & 3 back online
    patch_drive(conn, drive2["id"], simulated_offline=False)
    patch_drive(conn, drive3["id"], simulated_offline=False)

    # Re-protect this file
    reprot_res = reprotect_file(conn, file_unprot["id"])
    assert reprot_res["status"] == "reprotected"
    assert reprot_res["protection_status"] in ("parity", "mirrored")

    # Verify content preserved
    _, dl_reprot, _ = download_stream(conn, file_unprot["id"])
    assert b"".join(dl_reprot) == unprot_data

    # --- TEST 6: Honest Capacity Numbers
    drives = list_drives(conn)
    overview = calculate_pooled_overview(conn, drives)
    assert "raw_capacity" in overview
    assert "usable_capacity" in overview
    assert "free_usable_space" in overview
    assert overview["raw_capacity"] >= overview["usable_capacity"]
    assert overview["usable_capacity"] >= overview["free_usable_space"]
    assert overview["redundancy_mode"] == "parity"
    assert "raw_capacity_description" in overview
    assert "usable_capacity_description" in overview
    assert "free_usable_space_description" in overview
