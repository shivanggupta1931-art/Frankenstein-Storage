import json
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.errors import AppError
from backend.app.providers.base import StorageProvider
from backend.app.providers.gdrive import GoogleDriveProvider
from backend.app.providers.local import LocalFolderProvider


def get_drive_provider(drive_row: sqlite3.Row | dict[str, Any]) -> StorageProvider:
    row_dict = dict(drive_row)
    provider_type = row_dict.get("provider_type", "local")
    path_val = str(row_dict.get("path", ""))

    if provider_type == "gdrive" or path_val.startswith("gdrive://"):
        raw_config = row_dict.get("config")
        config = raw_config if isinstance(raw_config, (dict, type(None))) else json.loads(raw_config)
        return GoogleDriveProvider(
            config=config,
            simulated_offline=bool(row_dict.get("simulated_offline", 0)),
        )

    return LocalFolderProvider(
        root_path=path_val,
        simulated_offline=bool(row_dict.get("simulated_offline", 0)),
    )


def list_drives(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, display_name, path, status, simulated_offline, provider_type, config, created_at
           FROM drives ORDER BY created_at ASC"""
    )
    rows = cursor.fetchall()

    results = []
    for row in rows:
        provider = get_drive_provider(row)
        avail = provider.check_availability()
        usage = provider.get_usage()
        dev_info = provider.get_device_info() if hasattr(provider, "get_device_info") else {}

        # Determine status string
        if row["simulated_offline"]:
            effective_status = "simulated_offline"
        elif not avail:
            effective_status = "unavailable"
        else:
            effective_status = "online"

        # Count active chunks on this drive
        chunk_cursor = conn.cursor()
        chunk_cursor.execute("SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM chunks WHERE drive_id = ?", (row["id"],))
        chunk_stat = chunk_cursor.fetchone()

        # Check for Google Drive folder URL in config
        display_path = row["path"]
        raw_config = row.get("config") if isinstance(row, dict) else row["config"]
        if raw_config:
            try:
                cfg = raw_config if isinstance(raw_config, dict) else json.loads(raw_config)
                if cfg.get("folder_url"):
                    display_path = cfg["folder_url"]
            except Exception:
                pass

        results.append({
            "id": row["id"],
            "display_name": row["display_name"],
            "path": display_path,
            "provider_type": row["provider_type"] if "provider_type" in row.keys() else "local",
            "status": effective_status,
            "simulated_offline": bool(row["simulated_offline"]),
            "available": avail,
            "usage": usage,
            "chunk_count": chunk_stat["count"],
            "chunks_total_bytes": chunk_stat["total_size"],
            "device_id": dev_info.get("device_id"),
            "st_dev": dev_info.get("st_dev"),
            "mount_point": dev_info.get("mount_point"),
            "volume_name": dev_info.get("volume_name"),
            "created_at": row["created_at"],
        })

    # Annotate shared physical devices
    device_counts: dict[str, int] = {}
    for r in results:
        dev_id = r.get("device_id")
        if dev_id:
            device_counts[dev_id] = device_counts.get(dev_id, 0) + 1

    for r in results:
        dev_id = r.get("device_id")
        if dev_id and device_counts.get(dev_id, 0) > 1:
            r["shared_device"] = True
            r["shared_device_count"] = device_counts[dev_id]
            r["shared_volume_name"] = r.get("volume_name") or "Shared Physical Volume"
        else:
            r["shared_device"] = False
            r["shared_device_count"] = 1
            r["shared_volume_name"] = r.get("volume_name")

    return results


def calculate_pooled_overview(conn: sqlite3.Connection, drives: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculates storage overview, grouping drives by physical st_dev / device_id to avoid overcounting."""
    device_capacities: dict[str, int] = {}
    device_free: dict[str, int] = {}
    device_used: dict[str, int] = {}

    for d in drives:
        if not d.get("available"):
            continue
        dev_id = d.get("device_id") or f"untracked_{d['id']}"
        usage = d.get("usage", {})
        total = int(usage.get("total", 0))
        free = int(usage.get("free", 0))
        used = int(usage.get("used", 0))

        if dev_id not in device_capacities:
            device_capacities[dev_id] = total
            device_free[dev_id] = free
            device_used[dev_id] = used
        else:
            # Multiple folders on the same volume share capacity and free space
            device_free[dev_id] = min(device_free[dev_id], free)
            device_capacities[dev_id] = max(device_capacities[dev_id], total)

    pooled_cap = sum(device_capacities.values())
    pooled_free = sum(device_free.values())
    physical_disk_used = sum(device_used.values())

    # Vault chunks stored in database
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(size), 0) AS total_chunks_bytes FROM chunks")
    vault_chunks_bytes = cursor.fetchone()["total_chunks_bytes"]

    # Pooled used is bounded by pooled capacity and represents vault data
    pooled_used = min(vault_chunks_bytes, pooled_cap)

    cursor.execute("SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM files WHERE status = 'complete'")
    file_stat = cursor.fetchone()

    online_count = sum(1 for d in drives if d.get("status") == "online")

    return {
        "pooled_capacity": pooled_cap,
        "pooled_used": pooled_used,
        "pooled_free": pooled_free,
        "vault_chunks_bytes": vault_chunks_bytes,
        "physical_disk_used": physical_disk_used,
        "physical_disk_capacity": pooled_cap,
        "physical_disk_free": pooled_free,
        "capacity_source": "Provider-reported (De-duplicated)",
        "drives_count": len(drives),
        "drives_online": online_count,
        "drives_ratio": f"{online_count} of {len(drives)}",
        "files_count": file_stat["count"],
        "files_total_bytes": file_stat["total_size"],
    }


def get_macos_storage_locations() -> list[dict[str, Any]]:
    """Detects real macOS storage targets (Macintosh HD user locations and mounted /Volumes disks)."""
    locations: list[dict[str, Any]] = []
    home = Path.home()

    # 1. Primary macOS Storage (User Documents)
    doc_pool = home / "Documents" / "FrankensteinStorage"
    try:
        usage = shutil.disk_usage(home)
        locations.append({
            "name": "Macintosh HD (Documents Pool)",
            "path": str(doc_pool),
            "total": usage.total,
            "free": usage.free,
            "used": usage.used,
            "is_external": False,
            "description": "Primary internal macOS SSD storage under ~/Documents",
        })
    except Exception:
        pass

    # 2. Secondary macOS Storage (User Downloads)
    dl_pool = home / "Downloads" / "FrankensteinStorage"
    try:
        usage = shutil.disk_usage(home)
        locations.append({
            "name": "Macintosh HD (Downloads Pool)",
            "path": str(dl_pool),
            "total": usage.total,
            "free": usage.free,
            "used": usage.used,
            "is_external": False,
            "description": "Secondary internal macOS storage under ~/Downloads",
        })
    except Exception:
        pass

    # 3. Dedicated fast pool in ~/FrankensteinDrives
    dot_pool = home / "FrankensteinDrives" / "primary_ssd"
    try:
        usage = shutil.disk_usage(home)
        locations.append({
            "name": "Macintosh HD (Fast Storage)",
            "path": str(dot_pool),
            "total": usage.total,
            "free": usage.free,
            "used": usage.used,
            "is_external": False,
            "description": "Dedicated macOS vault folder in ~/FrankensteinDrives",
        })
    except Exception:
        pass

    # 4. Mounted external volumes under /Volumes (USB drives, external SSDs, Google Drive)
    volumes_dir = Path("/Volumes")
    if volumes_dir.exists():
        for vol in volumes_dir.iterdir():
            if vol.name in ("Recovery",) or vol.name.startswith("."):
                continue
            if vol.is_symlink():
                continue
            try:
                vol_usage = shutil.disk_usage(vol)
                is_gdrive_vol = "googledrive" in vol.name.lower() or "google drive" in vol.name.lower()
                my_drive_vol = vol / "My Drive"
                target_path = my_drive_vol if my_drive_vol.exists() else vol
                sample_folder = target_path / "sample"
                final_path = sample_folder if sample_folder.exists() else (target_path / "FrankensteinVault")
                gdrive_vol_quota = 15 * (1024 ** 3) if is_gdrive_vol else vol_usage.total
                locations.append({
                    "name": f"Google Drive Desktop ({vol.name})" if is_gdrive_vol else f"External Volume: {vol.name}",
                    "path": str(final_path),
                    "total": gdrive_vol_quota,
                    "free": gdrive_vol_quota if is_gdrive_vol else vol_usage.free,
                    "used": 0 if is_gdrive_vol else vol_usage.used,
                    "is_external": not is_gdrive_vol,
                    "is_cloud_synced": is_gdrive_vol,
                    "description": "Auto-syncs chunks directly to Google Drive in real-time" if is_gdrive_vol else f"Physical external USB / SSD disk at /Volumes/{vol.name}",
                })
            except Exception:
                continue

    # 5. Cloud Storage providers (Google Drive for Desktop in ~/Library/CloudStorage)
    cloud_storage = home / "Library" / "CloudStorage"
    if cloud_storage.exists():
        try:
            for item in cloud_storage.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    try:
                        c_usage = shutil.disk_usage(item)
                        is_gdrive = "googledrive" in item.name.lower()
                        my_drive = item / "My Drive"
                        target_dir = my_drive if my_drive.exists() else item
                        sample_dir = target_dir / "sample"
                        final_dir = sample_dir if sample_dir.exists() else (target_dir / "FrankensteinStorage")
                        gdrive_quota = 15 * (1024 ** 3) if is_gdrive else c_usage.total
                        locations.append({
                            "name": f"Google Drive (Desktop Synced: {item.name})" if is_gdrive else f"Cloud Storage: {item.name}",
                            "path": str(final_dir),
                            "total": gdrive_quota,
                            "free": gdrive_quota if is_gdrive else c_usage.free,
                            "used": 0 if is_gdrive else c_usage.used,
                            "is_external": False,
                            "is_cloud_synced": True,
                            "description": "Auto-syncs to 15 GiB Google Drive cloud in real-time" if is_gdrive else f"Synced cloud folder via {item.name}",
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    return locations


def add_drive(
    conn: sqlite3.Connection,
    path_str: str,
    display_name: str,
    provider_type: str = "local",
    config: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    if not display_name or not display_name.strip():
        raise AppError(400, "INVALID_NAME", "Drive display name cannot be empty")

    clean_name = display_name.strip()
    drive_id = uuid.uuid4().hex
    raw_path = path_str.strip() if path_str else ""

    # Auto-detect Google Drive URL if user pasted a drive.google.com link
    is_gdrive_url = bool(
        raw_path
        and (
            "drive.google.com" in raw_path
            or raw_path.startswith("http://")
            or raw_path.startswith("https://")
            or raw_path.startswith("gdrive://")
        )
    )

    if provider_type == "gdrive" or is_gdrive_url:
        config_obj = config if isinstance(config, dict) else (json.loads(config) if config else {})
        
        # Extract folder ID from URL (e.g. /folders/<id>)
        folder_match = re.search(r"/folders/([a-zA-Z0-9_-]+)", raw_path)
        folder_id = folder_match.group(1) if folder_match else config_obj.get("folder_id")

        if folder_id:
            config_obj["folder_id"] = folder_id
            clean_path = f"gdrive://{folder_id}"
        elif raw_path and not raw_path.startswith("http"):
            clean_path = raw_path
        else:
            clean_path = f"gdrive://{clean_name.replace(' ', '_')}"

        if raw_path and ("drive.google.com" in raw_path or raw_path.startswith("http")):
            config_obj["folder_url"] = raw_path

        if "auth_type" not in config_obj:
            config_obj["auth_type"] = "demo_mock"
        if "folder_name" not in config_obj:
            config_obj["folder_name"] = clean_name

        # Validate gdrive provider availability
        provider = GoogleDriveProvider(config=config_obj, simulated_offline=False)
        if not provider.check_availability():
            raise AppError(400, "DRIVE_NOT_ACCESSIBLE", "Google Drive authentication failed or unreachable. Check credentials/token.")

        config_json = json.dumps(config_obj)

        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drives WHERE path = ?", (clean_path,))
        if cursor.fetchone():
            raise AppError(409, "DRIVE_EXISTS", f"Drive '{clean_name}' ({clean_path}) is already registered")

        conn.execute(
            """INSERT INTO drives (id, display_name, path, status, simulated_offline, provider_type, config)
               VALUES (?, ?, ?, 'online', 0, 'gdrive', ?)""",
            (drive_id, clean_name, clean_path, config_json),
        )

        conn.execute(
            "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
            ("ADD_DRIVE", f"Added Google Drive {clean_name} ({clean_path})", "SUCCESS"),
        )

        return {
            "id": drive_id,
            "display_name": clean_name,
            "path": config_obj.get("folder_url", clean_path),
            "provider_type": "gdrive",
            "status": "online",
            "simulated_offline": False,
        }

    # Local folder provider
    if not raw_path:
        raise AppError(400, "INVALID_PATH", "Drive path cannot be empty")

    clean_path = str(Path(raw_path).resolve())

    # Reject path if already registered
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM drives WHERE path = ?", (clean_path,))
    if cursor.fetchone():
        raise AppError(409, "DRIVE_EXISTS", f"Drive path '{clean_path}' is already registered")

    provider = LocalFolderProvider(root_path=clean_path, simulated_offline=False)
    if not provider.check_availability():
        raise AppError(400, "DRIVE_NOT_ACCESSIBLE", f"Directory '{clean_path}' cannot be created or accessed")

    conn.execute(
        """INSERT INTO drives (id, display_name, path, status, simulated_offline, provider_type, config)
           VALUES (?, ?, ?, 'online', 0, 'local', NULL)""",
        (drive_id, clean_name, clean_path),
    )

    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        ("ADD_DRIVE", f"Added local drive {clean_name} at {clean_path}", "SUCCESS"),
    )

    return {
        "id": drive_id,
        "display_name": clean_name,
        "path": clean_path,
        "provider_type": "local",
        "status": "online",
        "simulated_offline": False,
    }


def patch_drive(
    conn: sqlite3.Connection,
    drive_id: str,
    simulated_offline: bool | None = None,
    display_name: str | None = None,
    path: str | None = None,
    provider_type: str | None = None,
    config: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives WHERE id = ?", (drive_id,))
    row = cursor.fetchone()
    if not row:
        raise AppError(404, "DRIVE_NOT_FOUND", f"Drive with id '{drive_id}' not found")

    new_sim = row["simulated_offline"] if simulated_offline is None else (1 if simulated_offline else 0)
    new_name = row["display_name"] if display_name is None else display_name.strip()
    new_path = row["path"] if path is None else path.strip()
    new_provider = row["provider_type"] if provider_type is None else provider_type.strip()
    
    if config is not None:
        new_config = json.dumps(config) if isinstance(config, dict) else config
    else:
        new_config = row["config"]

    conn.execute(
        "UPDATE drives SET simulated_offline = ?, display_name = ?, path = ?, provider_type = ?, config = ? WHERE id = ?",
        (new_sim, new_name, new_path, new_provider, new_config, drive_id),
    )

    status_desc = "simulated_offline" if new_sim else "online"
    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        ("PATCH_DRIVE", f"Updated drive {drive_id} (name='{new_name}', path='{new_path}', simulated_offline={bool(new_sim)})", "SUCCESS"),
    )

    return {
        "id": drive_id,
        "display_name": new_name,
        "path": new_path,
        "provider_type": new_provider,
        "status": status_desc,
        "simulated_offline": bool(new_sim),
    }


def delete_drive(conn: sqlite3.Connection, drive_id: str) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT id, display_name FROM drives WHERE id = ?", (drive_id,))
    row = cursor.fetchone()
    if not row:
        raise AppError(404, "DRIVE_NOT_FOUND", f"Drive with id '{drive_id}' not found")

    # Check if drive holds active chunks
    cursor.execute("SELECT COUNT(*) AS count FROM chunks WHERE drive_id = ?", (drive_id,))
    count = cursor.fetchone()["count"]
    if count > 0:
        raise AppError(
            400,
            "DRIVE_HAS_CHUNKS",
            f"Cannot delete drive '{row['display_name']}': it holds {count} active chunks",
            details={"chunk_count": count},
        )

    conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))
    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        ("DELETE_DRIVE", f"Deleted drive {row['display_name']} ({drive_id})", "SUCCESS"),
    )
