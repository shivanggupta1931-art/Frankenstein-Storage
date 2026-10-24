"""API endpoints for Frankenstein Storage."""

import mimetypes
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.crypto.key_manager import key_manager
from backend.app.db.connection import create_connection, get_db
from backend.app.services import drive_service, storage_engine

router = APIRouter(prefix="/api/v1")


class UnlockRequest(BaseModel):
    password: str = Field(..., min_length=1)


class AddDriveRequest(BaseModel):
    path: str | None = None
    display_name: str = Field(..., min_length=1)
    provider_type: str = Field("local")
    config: dict[str, Any] | None = None


class PatchDriveRequest(BaseModel):
    simulated_offline: bool | None = None
    display_name: str | None = None
    path: str | None = None
    provider_type: str | None = None
    config: dict[str, Any] | None = None


class VerifyRequest(BaseModel):
    file_id: str | None = None
    all: bool | None = True


@router.get("/health")
def get_health():
    return {
        "status": "ok",
        "unlocked": key_manager.is_unlocked(),
    }


@router.post("/unlock")
def unlock_vault(req: UnlockRequest):
    with get_db() as conn:
        key_manager.initialize_or_unlock(req.password, conn)
        conn.execute(
            "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
            ("UNLOCK_VAULT", "Vault unlocked successfully", "SUCCESS"),
        )
    return {
        "status": "unlocked",
        "message": "Vault successfully unlocked",
    }


@router.post("/lock")
def lock_vault():
    key_manager.lock()
    return {
        "status": "locked",
        "message": "Vault successfully locked",
    }


@router.get("/overview")
def get_overview():
    with get_db() as conn:
        drives = drive_service.list_drives(conn)
        overview = drive_service.calculate_pooled_overview(conn, drives)
        overview["vault_unlocked"] = key_manager.is_unlocked()
        return overview


@router.get("/drives")
def get_drives():
    with get_db() as conn:
        return drive_service.list_drives(conn)


@router.post("/drives")
def create_drive(req: AddDriveRequest):
    with get_db() as conn:
        path_str = req.path or ""
        return drive_service.add_drive(
            conn,
            path_str,
            req.display_name,
            provider_type=req.provider_type,
            config=req.config,
        )


@router.patch("/drives/{drive_id}")
def update_drive(drive_id: str, req: PatchDriveRequest):
    with get_db() as conn:
        return drive_service.patch_drive(
            conn,
            drive_id,
            simulated_offline=req.simulated_offline,
            display_name=req.display_name,
            path=req.path,
            provider_type=req.provider_type,
            config=req.config,
        )


@router.delete("/drives/{drive_id}")
def remove_drive(drive_id: str):
    with get_db() as conn:
        drive_service.delete_drive(conn, drive_id)
        return {"status": "deleted", "drive_id": drive_id}


@router.get("/system/macos-storage")
def get_macos_storage():
    return {
        "locations": drive_service.get_macos_storage_locations(),
    }


@router.post("/system/setup-real-drives")
def setup_real_drives():
    with get_db() as conn:
        home = Path.home()
        created = []
        locs = [
            ("Macintosh HD (Documents Pool)", str(home / "Documents" / "FrankensteinStorage")),
            ("Macintosh HD (Downloads Pool)", str(home / "Downloads" / "FrankensteinStorage")),
            ("Macintosh HD (Local Fast SSD)", str(home / ".frankenstein" / "storage" / "primary_ssd")),
        ]
        for name, p in locs:
            try:
                d = drive_service.add_drive(conn, p, name, provider_type="local")
                created.append(d)
            except AppError:
                pass
        return {"status": "ok", "drives_created": created}


class PreferenceUpdateRequest(BaseModel):
    preferred_mode: str | None = None


@router.get("/settings/preferences")
def get_upload_preferences():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT preferred_mode FROM upload_preferences WHERE user_id = 'default'")
        row = cursor.fetchone()
        preferred = row["preferred_mode"] if row else None
        return {
            "preferred_mode": preferred,
            "threshold_bytes": settings.smart_upload_threshold_bytes,
        }


@router.put("/settings/preferences")
def update_upload_preferences(req: PreferenceUpdateRequest):
    if req.preferred_mode is not None and req.preferred_mode not in ("whole", "chunked_parity"):
        raise AppError(
            400,
            "INVALID_STORAGE_MODE",
            f"Invalid preferred_mode: '{req.preferred_mode}'. Must be 'whole', 'chunked_parity', or null.",
        )
    with get_db() as conn:
        conn.execute(
            """INSERT INTO upload_preferences (user_id, preferred_mode, updated_at)
               VALUES ('default', ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET preferred_mode = excluded.preferred_mode, updated_at = CURRENT_TIMESTAMP""",
            (req.preferred_mode,),
        )
        return {
            "status": "updated",
            "preferred_mode": req.preferred_mode,
            "threshold_bytes": settings.smart_upload_threshold_bytes,
        }


@router.get("/files")
def get_files(
    sort_by: str = Query("created_at", pattern="^(created_at|size|name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    valid_sorts = {"created_at": "created_at", "size": "size", "name": "name"}
    col = valid_sorts.get(sort_by, "created_at")
    dir_str = "ASC" if order.lower() == "asc" else "DESC"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""SELECT id, name, folder, size, sha256, storage_mode, protection_status, unprotected_reason, status, created_at, updated_at
               FROM files ORDER BY {col} {dir_str}"""
        )
        files = [dict(row) for row in cursor.fetchall()]

        # Include chunk summary and status
        for f in files:
            chunks = storage_engine.get_file_chunks_map(conn, f["id"])
            f["chunks"] = chunks
            f["total_chunks"] = len(chunks)

            # Determine protection status and badge label
            p_status = f.get("protection_status")
            if not p_status:
                if f.get("storage_mode") == "chunked_parity":
                    p_status = "parity"
                elif f.get("storage_mode") == "mirrored":
                    p_status = "mirrored"
                else:
                    p_status = "unprotected"
            f["protection_status"] = p_status

            if p_status == "parity":
                f["protection_label"] = "Parity-protected"
            elif p_status == "mirrored":
                f["protection_label"] = "Mirrored"
            else:
                f["protection_label"] = "Unprotected (single drive)"
                if not f.get("unprotected_reason"):
                    f["unprotected_reason"] = "Stored on a single drive without redundancy"

            if f.get("storage_mode") == "whole":
                is_offline = any(c["drive_offline"] for c in chunks)
                f["health"] = "Unavailable" if is_offline else "Healthy"
            elif f.get("storage_mode") == "mirrored":
                stripes: dict[int, list[dict[str, Any]]] = {}
                for c in chunks:
                    stripes.setdefault(c["stripe_index"], []).append(c)

                degraded = False
                unavailable = False
                for s_idx, s_chunks in stripes.items():
                    offline_count = sum(1 for c in s_chunks if c["drive_offline"])
                    if offline_count == 1:
                        degraded = True
                    elif offline_count >= 2:
                        unavailable = True

                if unavailable:
                    f["health"] = "Unavailable"
                elif degraded:
                    f["health"] = "Degraded, still readable"
                else:
                    f["health"] = "Healthy"
            else:
                # Chunked parity mode
                stripes: dict[int, list[dict[str, Any]]] = {}
                for c in chunks:
                    stripes.setdefault(c["stripe_index"], []).append(c)
                
                degraded = False
                unavailable = False
                for s_idx, s_chunks in stripes.items():
                    offline_count = sum(1 for c in s_chunks if c["drive_offline"])
                    if offline_count == 1:
                        degraded = True
                    elif offline_count >= 2:
                        unavailable = True

                if unavailable:
                    f["health"] = "Unavailable"
                elif degraded:
                    f["health"] = "Degraded, still readable"
                else:
                    f["health"] = "Healthy"

        return files


@router.post("/files/upload")
async def upload_file(
    request: Request,
    name: str = Query(..., description="File name"),
    folder: str = Query("/", description="Logical folder"),
    overwrite: bool = Query(False, description="Overwrite if exists"),
    mode: str = Query("auto", description="Storage mode: auto, chunked_parity, mirrored, or whole"),
):
    valid_modes = ("auto", "chunked_parity", "mirrored", "whole")
    if mode not in valid_modes:
        raise AppError(
            400,
            "INVALID_STORAGE_MODE",
            f"Unsupported storage mode: '{mode}'. Allowed modes are {', '.join(valid_modes)}.",
        )
    with get_db() as conn:
        result = await storage_engine.upload_stream(
            conn=conn,
            stream=request.stream(),
            filename=name,
            folder=folder,
            overwrite=overwrite,
            mode=mode,
        )
        return result


@router.get("/files/{file_id}/download")
def download_file(file_id: str):
    conn = create_connection()
    try:
        meta, generator, _tracker = storage_engine.download_stream(conn, file_id)
        
        def cleanup_generator():
            try:
                yield from generator
            finally:
                conn.close()

        import urllib.parse
        ascii_filename = meta["name"].encode("ascii", "replace").decode().replace("?", "_")
        encoded_filename = urllib.parse.quote(meta["name"])
        headers = {
            "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}',
            "Content-Length": str(meta["size"]),
            "X-File-SHA256": meta["sha256"],
            "X-Rebuilt-From-Parity": "true" if _tracker.get("was_rebuilt") else "false",
        }
        return StreamingResponse(
            cleanup_generator(),
            media_type="application/octet-stream",
            headers=headers,
        )
    except Exception:
        conn.close()
        raise


@router.get("/files/{file_id}/preview")
def preview_file(file_id: str):
    """Retrieves and decrypts file chunks, returning content inline for in-app browser preview."""
    with get_db() as conn:
        meta, content = storage_engine.retrieve_file(conn, file_id)

    mime_type, _ = mimetypes.guess_type(meta["name"])
    if not mime_type:
        mime_type = "application/octet-stream"

    ascii_filename = meta["name"].encode("ascii", "replace").decode().replace("?", "_")
    encoded_filename = urllib.parse.quote(meta["name"])
    headers = {
        "Content-Disposition": f'inline; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}',
        "Content-Length": str(len(content)),
        "Accept-Ranges": "bytes",
    }
    return Response(
        content=content,
        media_type=mime_type,
        headers=headers,
    )


@router.get("/files/{file_id}/chunks")
def get_file_chunks(file_id: str):
    with get_db() as conn:
        return storage_engine.get_file_chunks_map(conn, file_id)


@router.delete("/files/{file_id}")
def delete_file_endpoint(file_id: str):
    with get_db() as conn:
        storage_engine.delete_file(conn, file_id)
        return {"status": "deleted", "file_id": file_id}


@router.post("/files/{file_id}/reprotect")
def reprotect_file_endpoint(file_id: str):
    with get_db() as conn:
        return storage_engine.reprotect_file(conn, file_id)


@router.post("/files/reprotect-all")
def reprotect_all_files_endpoint():
    with get_db() as conn:
        return storage_engine.reprotect_all_files(conn)


@router.post("/integrity/verify")
def verify_system_integrity(req: VerifyRequest):
    with get_db() as conn:
        target_file_id = None if req.all else req.file_id
        return storage_engine.verify_integrity(conn, target_file_id)


@router.post("/heal")
def heal_storage_pool():
    """Regenerates missing chunks from XOR parity or mirror replicas to return files to Healthy status."""
    with get_db() as conn:
        return storage_engine.heal_pool(conn)


@router.get("/activity")
def get_activity_log():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, operation, details, status, created_at FROM operation_log ORDER BY id DESC LIMIT 50")
        return [dict(row) for row in cursor.fetchall()]
