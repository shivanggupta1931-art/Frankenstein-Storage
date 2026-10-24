"""Frankenstein Storage Engine: streaming chunking, AES-GCM, rotating XOR parity, placement, and recovery."""

import hashlib
import io
import sqlite3
import uuid
from collections.abc import Generator
from typing import Any

from backend.app.core.config import calculate_reserve, settings
from backend.app.core.errors import AppError
from backend.app.core.validation import validate_filename
from backend.app.crypto.cipher import decrypt_chunk, encrypt_chunk
from backend.app.crypto.key_manager import key_manager
from backend.app.providers.base import StorageProvider
from backend.app.redundancy.parity import (
    compute_xor_parity,
    get_stripe_layout,
    rebuild_missing_chunk,
)
from backend.app.services.drive_service import get_drive_provider


def pick_placement_drives(
    available_drives: list[dict[str, Any]],
    count: int,
    stripe_index: int = 0,
) -> list[dict[str, Any]]:
    """Selects `count` distinct placement-eligible drives for a stripe or chunk.
    
    Rules:
    - Never places two chunks of the same stripe on the same drive (strictly distinct drive IDs).
    - Excludes drives below reserve or offline (already filtered in available_drives).
    - Balances chunk distribution across available drives weighted by free space and rotating offset.
    - If drives belong to distinct physical filesystems (device_id), prioritizes selecting drives on distinct devices.
    """
    n = len(available_drives)
    if n < count:
        raise AppError(507, "INSUFFICIENT_STORAGE", f"Need at least {count} eligible drives, found {n}")
    
    if n == count:
        return list(available_drives)

    # Rotate candidate start position based on stripe_index to evenly distribute load
    offset = (stripe_index * count) % n
    rotated = available_drives[offset:] + available_drives[:offset]

    # Pick count drives with priority for distinct physical devices if available
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_devices: set[Any] = set()

    # Pass 1: pick drives on distinct physical devices
    for d in rotated:
        dev_id = d.get("device_id")
        if d["id"] not in seen_ids:
            if dev_id is not None and dev_id in seen_devices:
                continue
            selected.append(d)
            seen_ids.add(d["id"])
            if dev_id is not None:
                seen_devices.add(dev_id)
            if len(selected) == count:
                return selected

    # Pass 2: fill remaining slots with any distinct drives
    for d in rotated:
        if d["id"] not in seen_ids:
            selected.append(d)
            seen_ids.add(d["id"])
            if len(selected) == count:
                return selected

    return selected[:count]


def pick_stripe_drives(available_drives: list[dict[str, Any]], stripe_index: int) -> list[dict[str, Any]]:
    """Selects 3 distinct drives for a stripe with rotating placement."""
    return pick_placement_drives(available_drives, 3, stripe_index)


def startup_cleanup(conn: sqlite3.Connection) -> None:
    """Marks incomplete uploads as failed, cleans up partial chunks and orphaned temp files."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM files WHERE status != 'complete'")
    incomplete_files = cursor.fetchall()

    for file_row in incomplete_files:
        fid = file_row["id"]
        # Find chunks
        cursor.execute("SELECT drive_id, chunk_id FROM chunks WHERE file_id = ?", (fid,))
        chunks = cursor.fetchall()
        for chunk in chunks:
            # Try to delete chunk from disk or cloud
            cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives WHERE id = ?", (chunk["drive_id"],))
            drive_row = cursor.fetchone()
            if drive_row:
                prov = get_drive_provider(drive_row)
                prov.delete_chunk(chunk["chunk_id"])
        
        conn.execute("UPDATE files SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (fid,))

    # Clean orphaned temp files in all drives
    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
    for d in cursor.fetchall():
        prov = get_drive_provider(d)
        prov.cleanup_temp_files()
    
    conn.commit()


def get_available_drives_for_storage(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives WHERE status = 'online' AND simulated_offline = 0")
    rows = cursor.fetchall()

    available = []
    for row in rows:
        provider = get_drive_provider(row)
        if provider.check_availability():
            usage = provider.get_usage()
            total = usage.get("total", 0)
            free = usage.get("free", 0)
            reserve = calculate_reserve(total)
            effective_free = max(0, free - reserve)
            if effective_free >= settings.chunk_size_bytes:
                available.append({
                    "id": row["id"],
                    "display_name": row["display_name"],
                    "path": row["path"],
                    "provider": provider,
                    "free": free,
                    "total": total,
                    "reserve": reserve,
                    "effective_free": effective_free,
                    "device_id": usage.get("dev_id"),
                })

    available.sort(key=lambda d: d["effective_free"], reverse=True)
    return available


async def read_stream_chunk(stream: Any, size: int, buffer: bytearray) -> bytes:
    result = bytearray()
    if buffer:
        take = min(len(buffer), size)
        result.extend(buffer[:take])
        del buffer[:take]
        size -= take
        if size == 0:
            return bytes(result)

    if hasattr(stream, "read"):
        block = stream.read(size)
        if block:
            result.extend(block)
        return bytes(result)
    
    while len(buffer) < size:
        try:
            chunk = await stream.__anext__()
            if not chunk:
                break
            buffer.extend(chunk)
        except StopAsyncIteration:
            break

    take = min(len(buffer), size)
    result.extend(buffer[:take])
    del buffer[:take]
    return bytes(result)


async def upload_stream(
    conn: sqlite3.Connection,
    stream: io.BufferedReader | Any,
    filename: str,
    folder: str = "/",
    overwrite: bool = False,
    mode: str = "auto",
) -> dict[str, Any]:
    """Uploads a file stream with encryption, automated smart placement, and redundancy."""
    valid_modes = ("auto", "chunked_parity", "mirrored", "whole")
    if mode not in valid_modes:
        raise AppError(
            400,
            "INVALID_STORAGE_MODE",
            f"Unsupported storage mode: '{mode}'. Allowed modes are {', '.join(valid_modes)}.",
        )

    # Ensure vault is unlocked
    key = key_manager.get_key()
    valid_name = validate_filename(filename)

    # Check existing file
    cursor = conn.cursor()
    cursor.execute("SELECT id, status FROM files WHERE folder = ? AND name = ?", (folder, valid_name))
    existing = cursor.fetchone()

    if existing:
        if existing["status"] == "complete" and not overwrite:
            raise AppError(409, "FILE_ALREADY_EXISTS", f"File '{valid_name}' already exists in '{folder}'")
        else:
            # Delete old file
            delete_file(conn, existing["id"])

    available_drives = get_available_drives_for_storage(conn)
    if not available_drives:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            "No enabled storage drives are online with free space above the reserve threshold.",
        )

    # Enforce strict drive constraints when specific mode is requested
    if mode == "chunked_parity" and len(available_drives) < settings.min_drives:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            f"At least {settings.min_drives} enabled, available drives with sufficient space are required for chunked parity storage (found {len(available_drives)})",
        )
    elif mode == "mirrored" and len(available_drives) < 2:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            f"At least 2 enabled, available drives with sufficient space are required for mirrored storage (found {len(available_drives)})",
        )
    elif mode == "whole" and len(available_drives) < 1:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            "At least 1 enabled, available drive with sufficient space is required for whole-object storage",
        )

    # Temporary insert to claim file record
    file_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO files (id, name, folder, size, sha256, storage_mode, status) VALUES (?, ?, ?, 0, '', ?, 'uploading')",
        (file_id, valid_name, folder, mode),
    )
    conn.commit()

    written_chunks: list[tuple[StorageProvider, str]] = []
    whole_hasher = hashlib.sha256()
    total_file_size = 0
    stripe_index = 0
    async_buffer = bytearray()

    try:
        # Read initial block to determine file scale and EOF
        initial_block = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
        
        # Check if more bytes exist
        if not initial_block:
            has_more = False
        elif len(initial_block) < settings.chunk_size_bytes:
            has_more = False
        else:
            peek = await read_stream_chunk(stream, 1, async_buffer)
            if peek:
                has_more = True
                async_buffer = bytearray(peek) + async_buffer
            else:
                has_more = False

        # Prepend initial_block back into buffer so all modes stream uniformly
        if initial_block:
            async_buffer = bytearray(initial_block) + async_buffer

        # Decide effective storage mode and protection status
        if mode == "whole":
            effective_mode = "whole"
            protection_status = "unprotected"
            unprotected_reason = "Single-drive storage requested" if len(available_drives) > 1 else "Only 1 drive available in pool"
        elif mode == "chunked_parity":
            effective_mode = "chunked_parity"
            protection_status = "parity"
            unprotected_reason = None
        elif mode == "mirrored":
            effective_mode = "mirrored"
            protection_status = "mirrored"
            unprotected_reason = None
        elif not has_more and len(available_drives) >= 2:
            # Auto mode on small file (< 1 MiB): store 2 copies on different drives
            effective_mode = "mirrored"
            protection_status = "mirrored"
            unprotected_reason = None
        elif len(available_drives) >= 3:
            effective_mode = "chunked_parity"
            protection_status = "parity"
            unprotected_reason = None
        elif len(available_drives) == 2:
            effective_mode = "mirrored"
            protection_status = "mirrored"
            unprotected_reason = None
        else:
            effective_mode = "whole"
            protection_status = "unprotected"
            unprotected_reason = "Only 1 drive available in pool (2+ required for redundancy)"

        # --- EXECUTE STORAGE BY MODE ---
        if effective_mode == "whole":
            selected_drive = max(available_drives, key=lambda d: d["effective_free"])
            whole_data = bytearray()
            while True:
                block = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
                if not block:
                    break
                whole_data.extend(block)
                whole_hasher.update(block)

            total_file_size = len(whole_data)
            final_sha256 = whole_hasher.hexdigest()

            enc_payload = encrypt_chunk(bytes(whole_data), key)
            chunk_uuid = uuid.uuid4().hex
            chunk_hash = hashlib.sha256(enc_payload).hexdigest()

            selected_drive["provider"].put_chunk(chunk_uuid, enc_payload)
            written_chunks.append((selected_drive["provider"], chunk_uuid))

            conn.execute(
                """INSERT INTO chunks (id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size)
                   VALUES (?, ?, 0, 0, 0, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    file_id,
                    selected_drive["id"],
                    chunk_uuid,
                    chunk_hash,
                    len(enc_payload),
                ),
            )

        elif effective_mode == "mirrored":
            # Store 2 mirrored copies per chunk across 2 distinct drives
            while True:
                curr_block = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
                if not curr_block:
                    break
                whole_hasher.update(curr_block)
                total_file_size += len(curr_block)

                enc_payload = encrypt_chunk(curr_block, key)
                chunk_hash = hashlib.sha256(enc_payload).hexdigest()
                stripe_drives = pick_placement_drives(available_drives, 2, stripe_index)

                for pos, drive in enumerate(stripe_drives):
                    chunk_uuid = uuid.uuid4().hex
                    drive["provider"].put_chunk(chunk_uuid, enc_payload)
                    written_chunks.append((drive["provider"], chunk_uuid))

                    conn.execute(
                        """INSERT INTO chunks (id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size)
                           VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                        (
                            uuid.uuid4().hex,
                            file_id,
                            stripe_index,
                            pos,
                            drive["id"],
                            chunk_uuid,
                            chunk_hash,
                            len(enc_payload),
                        ),
                    )

                stripe_index += 1

            final_sha256 = whole_hasher.hexdigest()

        else:
            # effective_mode == "chunked_parity"
            while True:
                data0 = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
                if not data0:
                    if stripe_index == 0:
                        data0 = b""
                        data1 = b""
                    else:
                        break
                else:
                    whole_hasher.update(data0)
                    total_file_size += len(data0)

                    if len(data0) < settings.chunk_size_bytes:
                        data1 = b""
                    else:
                        data1 = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
                        if data1:
                            whole_hasher.update(data1)
                            total_file_size += len(data1)
                        else:
                            data1 = b""

                padded0 = data0.ljust(settings.chunk_size_bytes, b"\x00")
                padded1 = data1.ljust(settings.chunk_size_bytes, b"\x00")

                enc0 = encrypt_chunk(padded0, key)
                enc1 = encrypt_chunk(padded1, key)
                enc_parity = compute_xor_parity(enc0, enc1)

                layout = get_stripe_layout(stripe_index)
                stripe_drives = pick_placement_drives(available_drives, 3, stripe_index)

                slots = {
                    layout["data0"]: (enc0, False),
                    layout["data1"]: (enc1, False),
                    layout["parity"]: (enc_parity, True),
                }

                for slot_pos in (0, 1, 2):
                    chunk_bytes, is_parity = slots[slot_pos]
                    drive = stripe_drives[slot_pos]
                    chunk_uuid = uuid.uuid4().hex
                    chunk_hash = hashlib.sha256(chunk_bytes).hexdigest()

                    drive["provider"].put_chunk(chunk_uuid, chunk_bytes)
                    written_chunks.append((drive["provider"], chunk_uuid))

                    conn.execute(
                        """INSERT INTO chunks (id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            uuid.uuid4().hex,
                            file_id,
                            stripe_index,
                            slot_pos,
                            1 if is_parity else 0,
                            drive["id"],
                            chunk_uuid,
                            chunk_hash,
                            len(chunk_bytes),
                        ),
                    )

                stripe_index += 1
                if len(data0) < settings.chunk_size_bytes or len(data1) < settings.chunk_size_bytes:
                    break

            final_sha256 = whole_hasher.hexdigest()

        # Update file record with true protection status and metadata
        conn.execute(
            """UPDATE files
               SET size = ?, sha256 = ?, storage_mode = ?, protection_status = ?, unprotected_reason = ?, status = 'complete', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (total_file_size, final_sha256, effective_mode, protection_status, unprotected_reason, file_id),
        )
        conn.execute(
            "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
            (
                "UPLOAD_FILE",
                f"Uploaded file {valid_name} ({total_file_size} bytes, mode: {effective_mode}, protection: {protection_status})",
                "SUCCESS",
            ),
        )
        conn.commit()

        protection_label = (
            "Parity-protected"
            if protection_status == "parity"
            else ("Mirrored (2x)" if protection_status == "mirrored" else "Unprotected (single drive)")
        )
        return {
            "id": file_id,
            "name": valid_name,
            "folder": folder,
            "size": total_file_size,
            "sha256": final_sha256,
            "storage_mode": effective_mode,
            "protection_status": protection_status,
            "protection_label": protection_label,
            "unprotected_reason": unprotected_reason,
            "status": "complete",
            "stripes": stripe_index,
        }

    except Exception as e:
        conn.rollback()
        for prov, cid in written_chunks:
            try:
                prov.delete_chunk(cid)
            except Exception:
                pass

        try:
            conn.execute("UPDATE files SET status = 'failed' WHERE id = ?", (file_id,))
            conn.commit()
        except Exception:
            pass

        if isinstance(e, AppError):
            raise e
        raise AppError(500, "UPLOAD_FAILED", f"File upload failed: {e}")


def download_stream(conn: sqlite3.Connection, file_id: str) -> tuple[dict[str, Any], Generator[bytes, None, None], bool]:
    """Streams file download, recovering missing/corrupted chunks using rotating XOR parity.
    
    Returns (file_metadata, generator, was_rebuilt_from_parity).
    """
    key = key_manager.get_key()

    cursor = conn.cursor()
    cursor.execute("SELECT id, name, folder, size, sha256, storage_mode, status FROM files WHERE id = ?", (file_id,))
    file_row = cursor.fetchone()
    if not file_row:
        raise AppError(404, "FILE_NOT_FOUND", f"File with id '{file_id}' not found")
    if file_row["status"] != "complete":
        raise AppError(400, "FILE_INCOMPLETE", f"File '{file_row['name']}' is not in complete status (status: {file_row['status']})")

    # Fetch all chunks
    cursor.execute(
        """SELECT id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size
           FROM chunks WHERE file_id = ? ORDER BY stripe_index ASC, position ASC""",
        (file_id,),
    )
    all_chunks = cursor.fetchall()

    # Pre-cache drive providers
    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
    drive_cache = {d["id"]: d for d in cursor.fetchall()}

    file_metadata = dict(file_row)
    rebuilt_flags = {"was_rebuilt": False}

    def generator() -> Generator[bytes, None, None]:
        if file_metadata.get("storage_mode") == "whole":
            if not all_chunks:
                raise AppError(500, "CORRUPT_METADATA", "No chunk records found for whole encrypted object")
            chunk_rec = all_chunks[0]
            drive_info = drive_cache.get(chunk_rec["drive_id"])
            if not drive_info:
                raise AppError(503, "DRIVE_UNAVAILABLE", "Drive for whole encrypted object is missing from database")
            provider = get_drive_provider(drive_info)
            if not provider.check_availability():
                raise AppError(503, "DRIVE_UNAVAILABLE", f"Storage drive '{drive_info['display_name']}' is offline/unavailable. Whole-object mode has no parity redundancy.")
            try:
                raw_chunk = provider.get_chunk(chunk_rec["chunk_id"])
            except Exception as e:
                raise AppError(500, "CHUNK_READ_FAILED", f"Failed to read whole encrypted object: {e}")
            if hashlib.sha256(raw_chunk).hexdigest() != chunk_rec["sha256"]:
                raise AppError(400, "INTEGRITY_MISMATCH", f"Chunk SHA-256 hash mismatch on drive '{drive_info['display_name']}'")
            plain = decrypt_chunk(raw_chunk, key)
            if hashlib.sha256(plain).hexdigest() != file_metadata["sha256"]:
                raise AppError(400, "INTEGRITY_MISMATCH", "Plaintext hash mismatch after decryption")
            yield plain
            return

        if file_metadata.get("storage_mode") == "mirrored":
            stripes_map: dict[int, list[sqlite3.Row]] = {}
            for c in all_chunks:
                stripes_map.setdefault(c["stripe_index"], []).append(c)

            bytes_emitted = 0
            total_target_size = file_metadata["size"]
            hasher = hashlib.sha256()

            for s_idx in sorted(stripes_map.keys()):
                stripe_chunks = stripes_map[s_idx]
                chunks_by_pos = {c["position"]: c for c in stripe_chunks}

                raw_enc = None
                failure_reasons = []

                # Try position 0 first, then position 1
                for pos in (0, 1):
                    if pos not in chunks_by_pos:
                        continue
                    c_rec = chunks_by_pos[pos]
                    d_info = drive_cache.get(c_rec["drive_id"])
                    if not d_info:
                        failure_reasons.append(f"Drive {c_rec['drive_id']} missing from DB")
                        continue
                    provider = get_drive_provider(d_info)
                    if not provider.check_availability():
                        failure_reasons.append(f"Drive '{d_info['display_name']}' is offline/unavailable")
                        continue
                    try:
                        chunk_bytes = provider.get_chunk(c_rec["chunk_id"])
                        if hashlib.sha256(chunk_bytes).hexdigest() != c_rec["sha256"]:
                            failure_reasons.append(f"Drive '{d_info['display_name']}' chunk hash mismatch")
                            continue
                        raw_enc = chunk_bytes
                        if pos != 0:
                            rebuilt_flags["was_rebuilt"] = True
                        break
                    except Exception as e:
                        failure_reasons.append(f"Drive '{d_info['display_name']}' read error: {e}")

                if raw_enc is None:
                    raise AppError(
                        503,
                        "FILE_UNRECOVERABLE",
                        f"File '{file_metadata['name']}' is unrecoverable: both mirrored drives are offline ({'; '.join(failure_reasons)}). Data cannot be reconstructed.",
                        details={"stripe_index": s_idx, "failures": failure_reasons},
                    )

                plain = decrypt_chunk(raw_enc, key)
                remaining = total_target_size - bytes_emitted
                if remaining <= 0:
                    break
                elif len(plain) > remaining:
                    output_chunk = plain[:remaining]
                else:
                    output_chunk = plain

                bytes_emitted += len(output_chunk)
                hasher.update(output_chunk)
                yield output_chunk

            if hasher.hexdigest() != file_metadata["sha256"]:
                raise AppError(400, "INTEGRITY_MISMATCH", "Plaintext hash mismatch after decryption")
            return

        # Chunked parity mode
        # Group chunks by stripe_index
        stripes_map: dict[int, list[sqlite3.Row]] = {}
        for c in all_chunks:
            stripes_map.setdefault(c["stripe_index"], []).append(c)

        bytes_emitted = 0
        total_target_size = file_metadata["size"]
        hasher = hashlib.sha256()

        for s_idx in sorted(stripes_map.keys()):
            stripe_chunks = stripes_map[s_idx]
            if len(stripe_chunks) != 3:
                raise AppError(500, "CORRUPT_METADATA", f"Stripe {s_idx} does not have exactly 3 chunks")

            # Sort chunks by slot position (0, 1, 2)
            stripe_chunks_by_pos = {c["position"]: c for c in stripe_chunks}
            
            loaded_data: dict[int, bytes] = {}
            missing_or_corrupt_positions: list[int] = []
            failure_reasons: list[str] = []

            for pos in (0, 1, 2):
                chunk_rec = stripe_chunks_by_pos[pos]
                drive_info = drive_cache.get(chunk_rec["drive_id"])
                
                if not drive_info:
                    missing_or_corrupt_positions.append(pos)
                    failure_reasons.append(f"Drive {chunk_rec['drive_id']} missing from DB")
                    continue

                provider = get_drive_provider(drive_info)
                if not provider.check_availability():
                    missing_or_corrupt_positions.append(pos)
                    failure_reasons.append(f"Drive '{drive_info['display_name']}' is offline/unavailable")
                    continue

                try:
                    raw_chunk = provider.get_chunk(chunk_rec["chunk_id"])
                    actual_sha256 = hashlib.sha256(raw_chunk).hexdigest()
                    if actual_sha256 != chunk_rec["sha256"]:
                        missing_or_corrupt_positions.append(pos)
                        failure_reasons.append(f"Drive '{drive_info['display_name']}' chunk hash mismatch (disk corruption)")
                        continue
                    loaded_data[pos] = raw_chunk
                except Exception as e:
                    missing_or_corrupt_positions.append(pos)
                    failure_reasons.append(f"Drive '{drive_info['display_name']}' read error: {e}")

            # Check availability count
            if len(missing_or_corrupt_positions) >= 2:
                raise AppError(
                    503,
                    "PARITY_RECOVERY_FAILED",
                    f"File '{file_metadata['name']}' is unrecoverable: 2 or more drives are offline ({'; '.join(failure_reasons)}). XOR parity can only reconstruct a single missing drive.",
                    details={"stripe_index": s_idx, "failures": failure_reasons},
                )

            if len(missing_or_corrupt_positions) == 1:
                rebuilt_flags["was_rebuilt"] = True
                missing_pos = missing_or_corrupt_positions[0]
                present_positions = [p for p in (0, 1, 2) if p != missing_pos]
                chunk_a = loaded_data[present_positions[0]]
                chunk_b = loaded_data[present_positions[1]]

                # XOR parity recovery
                rebuilt_chunk = rebuild_missing_chunk(chunk_a, chunk_b)
                expected_sha256 = stripe_chunks_by_pos[missing_pos]["sha256"]
                actual_rebuilt_sha256 = hashlib.sha256(rebuilt_chunk).hexdigest()

                if actual_rebuilt_sha256 != expected_sha256:
                    raise AppError(400, "INTEGRITY_MISMATCH", f"Rebuilt chunk hash mismatch in stripe {s_idx}")

                loaded_data[missing_pos] = rebuilt_chunk

            # Decrypt data chunks
            layout = get_stripe_layout(s_idx)
            enc_data0 = loaded_data[layout["data0"]]
            enc_data1 = loaded_data[layout["data1"]]

            plain0 = decrypt_chunk(enc_data0, key)
            plain1 = decrypt_chunk(enc_data1, key)
            combined_stripe_plain = plain0 + plain1

            # Truncate padding to match remaining file size
            remaining = total_target_size - bytes_emitted
            if remaining <= 0:
                break
            elif len(combined_stripe_plain) > remaining:
                output_chunk = combined_stripe_plain[:remaining]
            else:
                output_chunk = combined_stripe_plain

            bytes_emitted += len(output_chunk)
            hasher.update(output_chunk)
            yield output_chunk

        # Verify plaintext hash
        if hasher.hexdigest() != file_metadata["sha256"]:
            raise AppError(400, "INTEGRITY_MISMATCH", "Plaintext hash mismatch after reassembly")

    return file_metadata, generator(), rebuilt_flags


def retrieve_file(conn: sqlite3.Connection, file_id: str) -> tuple[dict[str, Any], bytes]:
    """Retrieves and decrypts complete file into memory, applying XOR parity reconstruction if drives are offline.

    Returns (file_metadata, file_bytes).
    """
    meta, generator, _tracker = download_stream(conn, file_id)
    chunks = list(generator)
    content = b"".join(chunks)
    return meta, content



def delete_file(conn: sqlite3.Connection, file_id: str) -> None:
    """Deletes a file and all its chunks from the storage drives."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM files WHERE id = ?", (file_id,))
    f_row = cursor.fetchone()
    if not f_row:
        raise AppError(404, "FILE_NOT_FOUND", f"File '{file_id}' not found")

    # Fetch chunks
    cursor.execute("SELECT drive_id, chunk_id FROM chunks WHERE file_id = ?", (file_id,))
    chunks = cursor.fetchall()

    # Pre-cache drives
    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
    drive_cache = {d["id"]: d for d in cursor.fetchall()}

    for c in chunks:
        d_info = drive_cache.get(c["drive_id"])
        if d_info:
            prov = get_drive_provider(d_info)
            prov.delete_chunk(c["chunk_id"])

    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        ("DELETE_FILE", f"Deleted file {f_row['name']} ({file_id})", "SUCCESS"),
    )
    conn.commit()


def get_file_chunks_map(conn: sqlite3.Connection, file_id: str) -> list[dict[str, Any]]:
    """Returns chunk placement map for the given file."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM files WHERE id = ?", (file_id,))
    if not cursor.fetchone():
        raise AppError(404, "FILE_NOT_FOUND", f"File '{file_id}' not found")

    cursor.execute(
        """SELECT c.id, c.file_id, c.stripe_index, c.position, c.is_parity, c.drive_id,
                  c.chunk_id, c.sha256, c.size, d.display_name, d.status, d.simulated_offline
           FROM chunks c
           JOIN drives d ON c.drive_id = d.id
           WHERE c.file_id = ?
           ORDER BY c.stripe_index ASC, c.position ASC""",
        (file_id,),
    )
    
    chunks = []
    for r in cursor.fetchall():
        is_offline = bool(r["simulated_offline"]) or r["status"] != "online"
        chunks.append({
            "id": r["id"],
            "stripe_index": r["stripe_index"],
            "position": r["position"],
            "is_parity": bool(r["is_parity"]),
            "drive_id": r["drive_id"],
            "drive_name": r["display_name"],
            "chunk_id": r["chunk_id"],
            "sha256": r["sha256"],
            "size": r["size"],
            "drive_offline": is_offline,
        })
    return chunks


def verify_integrity(conn: sqlite3.Connection, file_id: str | None = None) -> dict[str, Any]:
    """Verifies chunk integrity across drives.
    
    Reports healthy, degraded (rebuildable via parity), or corrupt files.
    """
    cursor = conn.cursor()
    if file_id:
        cursor.execute("SELECT id, name, size, sha256, storage_mode FROM files WHERE id = ?", (file_id,))
    else:
        cursor.execute("SELECT id, name, size, sha256, storage_mode FROM files WHERE status = 'complete'")
    files = cursor.fetchall()

    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
    drive_cache = {d["id"]: d for d in cursor.fetchall()}

    total_files = len(files)
    total_chunks = 0
    corrupted_chunks_count = 0
    file_reports = []

    for f in files:
        cursor.execute(
            """SELECT stripe_index, position, is_parity, drive_id, chunk_id, sha256, size
               FROM chunks WHERE file_id = ? ORDER BY stripe_index ASC, position ASC""",
            (f["id"],),
        )
        chunks = cursor.fetchall()
        total_chunks += len(chunks)

        file_degraded = False
        file_corrupted = False
        stripe_issues = []

        if f["storage_mode"] == "whole":
            # Whole mode: single chunk, no parity
            if not chunks:
                file_corrupted = True
                stripe_issues.append({"stripe_index": 0, "state": "unrecoverable", "failures": 1})
            else:
                c = chunks[0]
                d = drive_cache.get(c["drive_id"])
                if not d:
                    file_corrupted = True
                    corrupted_chunks_count += 1
                    stripe_issues.append({"stripe_index": 0, "state": "unrecoverable", "failures": 1})
                else:
                    prov = get_drive_provider(d)
                    if not prov.check_availability():
                        file_corrupted = True
                        corrupted_chunks_count += 1
                        stripe_issues.append({"stripe_index": 0, "state": "unrecoverable", "failures": 1})
                    else:
                        try:
                            raw = prov.get_chunk(c["chunk_id"])
                            if hashlib.sha256(raw).hexdigest() != c["sha256"]:
                                file_corrupted = True
                                corrupted_chunks_count += 1
                                stripe_issues.append({"stripe_index": 0, "state": "unrecoverable", "failures": 1})
                        except Exception:
                            file_corrupted = True
                            corrupted_chunks_count += 1
                            stripe_issues.append({"stripe_index": 0, "state": "unrecoverable", "failures": 1})

            overall_state = "corrupt" if file_corrupted else "healthy"
        else:
            stripes: dict[int, list[sqlite3.Row]] = {}
            for c in chunks:
                stripes.setdefault(c["stripe_index"], []).append(c)

            for s_idx, s_chunks in stripes.items():
                stripe_failures = 0
                for c in s_chunks:
                    d = drive_cache.get(c["drive_id"])
                    if not d:
                        stripe_failures += 1
                        corrupted_chunks_count += 1
                        continue
                    prov = get_drive_provider(d)
                    if not prov.check_availability():
                        stripe_failures += 1
                        corrupted_chunks_count += 1
                        continue
                    try:
                        raw = prov.get_chunk(c["chunk_id"])
                        if hashlib.sha256(raw).hexdigest() != c["sha256"]:
                            stripe_failures += 1
                            corrupted_chunks_count += 1
                    except Exception:
                        stripe_failures += 1
                        corrupted_chunks_count += 1

                if stripe_failures == 1:
                    file_degraded = True
                    stripe_issues.append({"stripe_index": s_idx, "state": "rebuildable", "failures": 1})
                elif stripe_failures >= 2:
                    file_corrupted = True
                    stripe_issues.append({"stripe_index": s_idx, "state": "unrecoverable", "failures": stripe_failures})

            if file_corrupted:
                overall_state = "corrupt"
            elif file_degraded:
                overall_state = "rebuildable"
            else:
                overall_state = "healthy"

        file_reports.append({
            "file_id": f["id"],
            "name": f["name"],
            "state": overall_state,
            "stripe_issues": stripe_issues,
        })

    overall_system = "healthy"
    if any(r["state"] == "corrupt" for r in file_reports):
        overall_system = "corrupt"
    elif any(r["state"] == "rebuildable" for r in file_reports):
        overall_system = "degraded"

    return {
        "status": overall_system,
        "files_checked": total_files,
        "chunks_checked": total_chunks,
        "corrupted_chunks": corrupted_chunks_count,
        "files": file_reports,
    }


def heal_pool(conn: sqlite3.Connection, target_file_id: str | None = None) -> dict[str, Any]:
    """Rebuilds and regenerates missing or corrupted chunks across all drives or a specific file.
    
    For parity files: XOR parity is used to regenerate missing chunks onto online drives.
    For mirrored files: the healthy replica is copied to restore the missing mirror copy.
    Returns a comprehensive heal report with pass/fail counts and list of restored chunks.
    """
    cursor = conn.cursor()

    if target_file_id:
        cursor.execute("SELECT id, name, size, sha256, storage_mode FROM files WHERE id = ? AND status = 'complete'", (target_file_id,))
    else:
        cursor.execute("SELECT id, name, size, sha256, storage_mode FROM files WHERE status = 'complete'")
    files = cursor.fetchall()

    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
    drive_cache = {d["id"]: d for d in cursor.fetchall()}

    files_checked = len(files)
    files_healed = 0
    chunks_rebuilt = 0
    unrecoverable_files: list[str] = []
    healed_files_details: list[dict[str, Any]] = []

    for f in files:
        f_id = f["id"]
        f_name = f["name"]
        mode = f["storage_mode"]
        cursor.execute(
            """SELECT stripe_index, position, is_parity, drive_id, chunk_id, sha256, size
               FROM chunks WHERE file_id = ? ORDER BY stripe_index ASC, position ASC""",
            (f_id,),
        )
        chunks = cursor.fetchall()

        file_rebuilt_count = 0
        file_unrecoverable = False

        if mode == "whole":
            # Whole mode has no redundancy to heal from
            continue

        elif mode == "mirrored":
            stripes: dict[int, list[sqlite3.Row]] = {}
            for c in chunks:
                stripes.setdefault(c["stripe_index"], []).append(c)

            for s_idx, s_chunks in stripes.items():
                if len(s_chunks) < 2:
                    continue
                # Check status of each copy
                chunk_status = []
                for c in s_chunks:
                    d_info = drive_cache.get(c["drive_id"])
                    is_ok = False
                    raw_bytes = None
                    if d_info:
                        prov = get_drive_provider(d_info)
                        if prov.check_availability():
                            try:
                                b = prov.get_chunk(c["chunk_id"])
                                if hashlib.sha256(b).hexdigest() == c["sha256"]:
                                    is_ok = True
                                    raw_bytes = b
                            except Exception:
                                is_ok = False
                    chunk_status.append({"chunk": c, "drive": d_info, "is_ok": is_ok, "data": raw_bytes})

                ok_chunks = [cs for cs in chunk_status if cs["is_ok"]]
                bad_chunks = [cs for cs in chunk_status if not cs["is_ok"]]

                if len(ok_chunks) == 0:
                    file_unrecoverable = True
                elif len(bad_chunks) > 0:
                    # We can heal the bad chunks if their target drives are online!
                    source_data = ok_chunks[0]["data"]
                    for bad in bad_chunks:
                        d_info = bad["drive"]
                        c_rec = bad["chunk"]
                        if d_info:
                            prov = get_drive_provider(d_info)
                            if prov.check_availability():
                                try:
                                    prov.put_chunk(c_rec["chunk_id"], source_data)
                                    chunks_rebuilt += 1
                                    file_rebuilt_count += 1
                                except Exception:
                                    pass

        else:
            # Parity mode
            stripes: dict[int, list[sqlite3.Row]] = {}
            for c in chunks:
                stripes.setdefault(c["stripe_index"], []).append(c)

            for s_idx, s_chunks in stripes.items():
                if len(s_chunks) != 3:
                    continue
                stripe_by_pos = {c["position"]: c for c in s_chunks}
                loaded_chunks: dict[int, bytes] = {}
                missing_positions: list[int] = []

                for pos in (0, 1, 2):
                    c_rec = stripe_by_pos[pos]
                    d_info = drive_cache.get(c_rec["drive_id"])
                    is_ok = False
                    if d_info:
                        prov = get_drive_provider(d_info)
                        if prov.check_availability():
                            try:
                                b = prov.get_chunk(c_rec["chunk_id"])
                                if hashlib.sha256(b).hexdigest() == c_rec["sha256"]:
                                    loaded_chunks[pos] = b
                                    is_ok = True
                            except Exception:
                                is_ok = False
                    if not is_ok:
                        missing_positions.append(pos)

                if len(missing_positions) >= 2:
                    file_unrecoverable = True
                elif len(missing_positions) == 1:
                    # 1 missing, 2 present -> heal via XOR!
                    m_pos = missing_positions[0]
                    other_positions = [p for p in (0, 1, 2) if p != m_pos]
                    c_a = loaded_chunks[other_positions[0]]
                    c_b = loaded_chunks[other_positions[1]]
                    rebuilt = rebuild_missing_chunk(c_a, c_b)
                    target_rec = stripe_by_pos[m_pos]
                    target_d = drive_cache.get(target_rec["drive_id"])
                    if target_d:
                        target_prov = get_drive_provider(target_d)
                        if target_prov.check_availability():
                            if hashlib.sha256(rebuilt).hexdigest() == target_rec["sha256"]:
                                target_prov.put_chunk(target_rec["chunk_id"], rebuilt)
                                chunks_rebuilt += 1
                                file_rebuilt_count += 1

        if file_unrecoverable:
            unrecoverable_files.append(f_name)
        elif file_rebuilt_count > 0:
            files_healed += 1
            healed_files_details.append({
                "file_id": f_id,
                "name": f_name,
                "chunks_rebuilt": file_rebuilt_count,
            })

    status = "healthy"
    if unrecoverable_files:
        status = "unrecoverable"
    elif files_healed > 0:
        status = "healed"

    return {
        "status": status,
        "files_checked": files_checked,
        "files_healed": files_healed,
        "chunks_rebuilt": chunks_rebuilt,
        "unrecoverable_files": unrecoverable_files,
        "healed_files": healed_files_details,
    }


def reprotect_file(conn: sqlite3.Connection, file_id: str) -> dict[str, Any]:
    """Re-protects an existing file by upgrading it to mirrored or parity redundancy."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, folder, size, sha256, storage_mode, status, protection_status FROM files WHERE id = ?",
        (file_id,),
    )
    file_row = cursor.fetchone()
    if not file_row:
        raise AppError(404, "FILE_NOT_FOUND", f"File '{file_id}' not found")
    if file_row["status"] != "complete":
        raise AppError(400, "FILE_INCOMPLETE", f"File '{file_row['name']}' is not in complete status")

    # Read and decrypt the original file safely into memory
    meta, content = retrieve_file(conn, file_id)

    # Check available drives
    available = get_available_drives_for_storage(conn)
    if len(available) < 2:
        raise AppError(
            400,
            "INSUFFICIENT_DRIVES_FOR_PROTECTION",
            f"Cannot re-protect: need at least 2 online drives with space above reserve (found {len(available)})",
        )

    # Determine best protection target
    if len(available) >= 3 and len(content) >= settings.chunk_size_bytes:
        new_mode = "chunked_parity"
        new_protection = "parity"
    else:
        new_mode = "mirrored"
        new_protection = "mirrored"

    # If already in the target mode, skip
    if file_row["storage_mode"] == new_mode and file_row["protection_status"] == new_protection:
        return {
            "id": file_id,
            "name": file_row["name"],
            "status": "already_protected",
            "storage_mode": new_mode,
            "protection_status": new_protection,
        }

    key = key_manager.get_key()
    written_chunks: list[tuple[StorageProvider, str]] = []
    new_chunks_records = []

    try:
        stripe_index = 0
        if new_mode == "mirrored":
            if len(content) <= settings.chunk_size_bytes:
                enc_payload = encrypt_chunk(content, key)
                stripe_drives = pick_placement_drives(available, 2, 0)
                chunk_hash = hashlib.sha256(enc_payload).hexdigest()
                for pos, d in enumerate(stripe_drives):
                    cid = uuid.uuid4().hex
                    d["provider"].put_chunk(cid, enc_payload)
                    written_chunks.append((d["provider"], cid))
                    new_chunks_records.append((
                        uuid.uuid4().hex, file_id, 0, pos, 0, d["id"], cid, chunk_hash, len(enc_payload)
                    ))
            else:
                offset = 0
                while offset < len(content):
                    chunk_slice = content[offset:offset + settings.chunk_size_bytes]
                    offset += len(chunk_slice)
                    enc_payload = encrypt_chunk(chunk_slice, key)
                    stripe_drives = pick_placement_drives(available, 2, stripe_index)
                    chunk_hash = hashlib.sha256(enc_payload).hexdigest()
                    for pos, d in enumerate(stripe_drives):
                        cid = uuid.uuid4().hex
                        d["provider"].put_chunk(cid, enc_payload)
                        written_chunks.append((d["provider"], cid))
                        new_chunks_records.append((
                            uuid.uuid4().hex, file_id, stripe_index, pos, 0, d["id"], cid, chunk_hash, len(enc_payload)
                        ))
                    stripe_index += 1
        elif new_mode == "chunked_parity":
            offset = 0
            while offset < len(content):
                data0 = content[offset:offset + settings.chunk_size_bytes]
                offset += len(data0)
                if len(data0) < settings.chunk_size_bytes:
                    data1 = b""
                else:
                    data1 = content[offset:offset + settings.chunk_size_bytes]
                    offset += len(data1)
                
                padded0 = data0.ljust(settings.chunk_size_bytes, b"\x00")
                padded1 = data1.ljust(settings.chunk_size_bytes, b"\x00")
                enc0 = encrypt_chunk(padded0, key)
                enc1 = encrypt_chunk(padded1, key)
                enc_parity = compute_xor_parity(enc0, enc1)

                layout = get_stripe_layout(stripe_index)
                stripe_drives = pick_placement_drives(available, 3, stripe_index)
                slots = {
                    layout["data0"]: (enc0, False),
                    layout["data1"]: (enc1, False),
                    layout["parity"]: (enc_parity, True),
                }
                for slot_pos in (0, 1, 2):
                    cbytes, is_par = slots[slot_pos]
                    d = stripe_drives[slot_pos]
                    cid = uuid.uuid4().hex
                    chash = hashlib.sha256(cbytes).hexdigest()
                    d["provider"].put_chunk(cid, cbytes)
                    written_chunks.append((d["provider"], cid))
                    new_chunks_records.append((
                        uuid.uuid4().hex, file_id, stripe_index, slot_pos, 1 if is_par else 0, d["id"], cid, chash, len(cbytes)
                    ))
                stripe_index += 1

        # Delete old chunks from providers and DB
        cursor.execute("SELECT drive_id, chunk_id FROM chunks WHERE file_id = ?", (file_id,))
        old_chunks = cursor.fetchall()
        cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives")
        drive_cache = {d["id"]: d for d in cursor.fetchall()}
        for oc in old_chunks:
            d_info = drive_cache.get(oc["drive_id"])
            if d_info:
                try:
                    prov = get_drive_provider(d_info)
                    prov.delete_chunk(oc["chunk_id"])
                except Exception:
                    pass

        cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))

        cursor.executemany(
            """INSERT INTO chunks (id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            new_chunks_records,
        )

        cursor.execute(
            """UPDATE files
               SET storage_mode = ?, protection_status = ?, unprotected_reason = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (new_mode, new_protection, file_id),
        )
        conn.commit()
        return {
            "id": file_id,
            "name": file_row["name"],
            "status": "reprotected",
            "previous_mode": file_row["storage_mode"],
            "new_mode": new_mode,
            "protection_status": new_protection,
        }
    except Exception as e:
        conn.rollback()
        for prov, cid in written_chunks:
            try:
                prov.delete_chunk(cid)
            except Exception:
                pass
        raise e


def reprotect_all_files(conn: sqlite3.Connection) -> dict[str, Any]:
    """Finds all unprotected or single-drive files and upgrades them to mirrored or parity redundancy."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, storage_mode, protection_status FROM files WHERE status = 'complete'")
    all_files = cursor.fetchall()
    
    reprotected = 0
    skipped = 0
    failed = 0
    details = []

    for f in all_files:
        fid = f["id"]
        p_status = f["protection_status"]
        if p_status == "parity":
            skipped += 1
            continue
        try:
            res = reprotect_file(conn, fid)
            if res.get("status") == "reprotected":
                reprotected += 1
                details.append({"id": fid, "name": f["name"], "result": "reprotected", "new_mode": res.get("new_mode")})
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            details.append({"id": fid, "name": f["name"], "result": "failed", "error": str(e)})

    return {
        "status": "completed",
        "total_files": len(all_files),
        "reprotected": reprotected,
        "skipped": skipped,
        "failed": failed,
        "details": details,
    }
