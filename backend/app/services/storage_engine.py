"""Frankenstein Storage Engine: streaming chunking, AES-GCM, rotating XOR parity, placement, and recovery."""

import hashlib
import io
import sqlite3
import uuid
from collections.abc import Generator
from typing import Any

from backend.app.core.config import settings
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


def pick_stripe_drives(available_drives: list[dict[str, Any]], stripe_index: int) -> list[dict[str, Any]]:
    """Selects 3 distinct drives for a stripe with rotating placement."""
    n = len(available_drives)
    if n < 3:
        raise AppError(507, "INSUFFICIENT_STORAGE", f"Need at least 3 available drives, found {n}")
    
    offset = (stripe_index * 3) % n
    rotated = available_drives[offset:] + available_drives[:offset]
    return rotated[:3]


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
            if usage["free"] >= settings.chunk_size_bytes:
                available.append({
                    "id": row["id"],
                    "display_name": row["display_name"],
                    "path": row["path"],
                    "provider": provider,
                    "free": usage["free"],
                })

    return available


async def read_stream_chunk(stream: Any, size: int, buffer: bytearray) -> bytes:
    if hasattr(stream, "read"):
        return stream.read(size)
    
    while len(buffer) < size:
        try:
            chunk = await stream.__anext__()
            if not chunk:
                break
            buffer.extend(chunk)
        except StopAsyncIteration:
            break
    data = bytes(buffer[:size])
    del buffer[:size]
    return data


async def upload_stream(
    conn: sqlite3.Connection,
    stream: io.BufferedReader | Any,
    filename: str,
    folder: str = "/",
    overwrite: bool = False,
    mode: str = "chunked_parity",
) -> dict[str, Any]:
    """Uploads a file stream in chunks with encryption and rotating XOR parity, or as a single encrypted object."""
    if mode not in ("whole", "chunked_parity"):
        raise AppError(
            400,
            "INVALID_STORAGE_MODE",
            f"Unsupported storage mode: '{mode}'. Allowed modes are 'whole' and 'chunked_parity'.",
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
    if mode == "chunked_parity" and len(available_drives) < settings.min_drives:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            f"At least {settings.min_drives} enabled, available drives with sufficient space are required for chunked parity storage (found {len(available_drives)})",
        )
    elif mode == "whole" and len(available_drives) < 1:
        raise AppError(
            507,
            "INSUFFICIENT_STORAGE",
            "At least 1 enabled, available drive with sufficient space is required for whole-object storage",
        )

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
        if mode == "whole":
            # Select available drive with maximum free space
            selected_drive = max(available_drives, key=lambda d: d["free"])
            whole_data = bytearray()
            while True:
                block = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
                if not block:
                    break
                whole_data.extend(block)
                whole_hasher.update(block)

            total_file_size = len(whole_data)
            final_sha256 = whole_hasher.hexdigest()

            # Encrypt whole object directly with AES-256-GCM
            enc_payload = encrypt_chunk(bytes(whole_data), key)
            chunk_uuid = uuid.uuid4().hex
            chunk_hash = hashlib.sha256(enc_payload).hexdigest()

            selected_drive["provider"].put_chunk(chunk_uuid, enc_payload)
            written_chunks.append((selected_drive["provider"], chunk_uuid))

            conn.execute(
                """INSERT INTO chunks (id, file_id, stripe_index, position, is_parity, drive_id, chunk_id, sha256, size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex,
                    file_id,
                    0,
                    0,
                    0,
                    selected_drive["id"],
                    chunk_uuid,
                    chunk_hash,
                    len(enc_payload),
                ),
            )

            conn.execute(
                "UPDATE files SET size = ?, sha256 = ?, storage_mode = ?, status = 'complete', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (total_file_size, final_sha256, mode, file_id),
            )
            conn.execute(
                "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
                ("UPLOAD_FILE", f"Uploaded file {valid_name} ({total_file_size} bytes, mode: whole)", "SUCCESS"),
            )
            conn.commit()

            return {
                "id": file_id,
                "name": valid_name,
                "folder": folder,
                "size": total_file_size,
                "sha256": final_sha256,
                "storage_mode": "whole",
                "status": "complete",
                "stripes": 0,
            }
        while True:
            # Read first chunk of stripe (up to chunk_size)
            data0 = await read_stream_chunk(stream, settings.chunk_size_bytes, async_buffer)
            if not data0:
                if stripe_index == 0:
                    # Empty file (0 bytes): create 1 stripe of zero-filled chunks
                    data0 = b""
                    data1 = b""
                else:
                    # File finished on stripe boundary
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

            # Pad chunks to full chunk_size_bytes
            padded0 = data0.ljust(settings.chunk_size_bytes, b"\x00")
            padded1 = data1.ljust(settings.chunk_size_bytes, b"\x00")

            # Encrypt chunks
            enc0 = encrypt_chunk(padded0, key)
            enc1 = encrypt_chunk(padded1, key)

            # Compute XOR parity across encrypted chunks
            enc_parity = compute_xor_parity(enc0, enc1)

            # Stripe layout and drive assignment
            layout = get_stripe_layout(stripe_index)
            stripe_drives = pick_stripe_drives(available_drives, stripe_index)

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
                # File EOF reached
                break

        final_sha256 = whole_hasher.hexdigest()
        conn.execute(
            "UPDATE files SET size = ?, sha256 = ?, storage_mode = 'chunked_parity', status = 'complete', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (total_file_size, final_sha256, file_id),
        )
        conn.execute(
            "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
            ("UPLOAD_FILE", f"Uploaded file {valid_name} ({total_file_size} bytes, {stripe_index} stripes, mode: chunked_parity)", "SUCCESS"),
        )
        conn.commit()

        return {
            "id": file_id,
            "name": valid_name,
            "folder": folder,
            "size": total_file_size,
            "sha256": final_sha256,
            "storage_mode": "chunked_parity",
            "status": "complete",
            "stripes": stripe_index,
        }

    except Exception as e:
        conn.rollback()
        # Clean up any chunks written to disk
        for prov, cid in written_chunks:
            try:
                prov.delete_chunk(cid)
            except Exception:
                pass

        # Mark file as failed
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
                    f"Stripe {s_idx} unrecoverable: {len(missing_or_corrupt_positions)} chunks unavailable ({'; '.join(failure_reasons)})",
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
