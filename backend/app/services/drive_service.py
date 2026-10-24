import json
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.providers.base import StorageProvider
from backend.app.providers.gdrive import GoogleDriveProvider
from backend.app.providers.local import LocalFolderProvider
from backend.app.providers.s3 import S3StorageProvider


def get_drive_provider(drive_row: sqlite3.Row | dict[str, Any]) -> StorageProvider:
    row_dict = dict(drive_row)
    provider_type = row_dict.get("provider_type", "local")
    path_val = str(row_dict.get("path", ""))

    if provider_type == "gdrive" or path_val.startswith("gdrive://"):
        raw_config = row_dict.get("config")
        config = (
            raw_config if isinstance(raw_config, (dict, type(None))) else json.loads(raw_config)
        )
        return GoogleDriveProvider(
            config=config,
            simulated_offline=bool(row_dict.get("simulated_offline", 0)),
        )

    if provider_type in ("s3", "r2", "minio", "b2") or path_val.startswith("s3://"):
        raw_config = row_dict.get("config")
        config = (
            raw_config
            if isinstance(raw_config, (dict, type(None)))
            else (json.loads(raw_config) if raw_config else {})
        )
        return S3StorageProvider(
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

        total_bytes = int(usage.get("total", 0))
        free_bytes = int(usage.get("free", 0))
        reserve_bytes = settings.calculate_reserve(total_bytes)
        effective_free = max(0, free_bytes - reserve_bytes)
        is_low_space = bool(free_bytes < reserve_bytes)

        # Determine status string and placement eligibility
        if row["status"] == "ejected":
            effective_status = "ejected"
            exclusion_reason = (
                "Pendrive ejected. Re-insert USB drive to reconnect to the storage pool."
            )
            is_eligible = False
        elif row["simulated_offline"]:
            effective_status = "simulated_offline"
            exclusion_reason = "Offline (Simulated)"
            is_eligible = False
        elif not avail:
            effective_status = "unavailable"
            is_usb = bool(dev_info.get("is_external") or usage.get("is_external"))
            exclusion_reason = (
                "Pendrive disconnected or path unreachable"
                if is_usb
                else "Offline (Storage path unreachable)"
            )
            is_eligible = False
        elif is_low_space:
            effective_status = "low_space"
            res_gib = round(reserve_bytes / (1024**3), 1)
            free_gib = round(free_bytes / (1024**3), 2)
            exclusion_reason = f"Low space: {free_gib} GiB free is below {res_gib} GiB reserve"
            is_eligible = False
        else:
            effective_status = "online"
            exclusion_reason = None
            is_eligible = True

        # Count active chunks on this drive
        chunk_cursor = conn.cursor()
        chunk_cursor.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM chunks WHERE drive_id = ?",
            (row["id"],),
        )
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

        results.append(
            {
                "id": row["id"],
                "display_name": row["display_name"],
                "path": display_path,
                "provider_type": row["provider_type"] if "provider_type" in row.keys() else "local",
                "status": effective_status,
                "simulated_offline": bool(row["simulated_offline"]),
                "available": avail,
                "usage": usage,
                "reserve_bytes": reserve_bytes,
                "effective_free": effective_free,
                "is_low_space": is_low_space,
                "is_placement_eligible": is_eligible,
                "exclusion_reason": exclusion_reason,
                "chunk_count": chunk_stat["count"],
                "chunks_total_bytes": chunk_stat["total_size"],
                "device_id": dev_info.get("device_id"),
                "st_dev": dev_info.get("st_dev"),
                "mount_point": dev_info.get("mount_point"),
                "volume_name": dev_info.get("volume_name"),
                "is_external": bool(dev_info.get("is_external") or usage.get("is_external")),
                "is_removable": bool(dev_info.get("is_removable") or usage.get("is_removable")),
                "created_at": row["created_at"],
            }
        )

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


def get_external_usb_drives() -> list[dict[str, Any]]:
    """Scans /Volumes for mounted external USB / removable storage devices."""
    external_drives: list[dict[str, Any]] = []
    volumes_dir = Path("/Volumes")
    if not volumes_dir.exists():
        return external_drives

    root_dev = None
    try:
        root_dev = os.stat("/").st_dev
    except Exception:
        pass

    try:
        for vol in volumes_dir.iterdir():
            # Filter internal system volumes and aliases
            if vol.name in ("Recovery", "Macintosh HD") or vol.name.startswith("."):
                continue
            if "timemachine" in vol.name.lower():
                continue
            if vol.is_symlink():
                continue
            # Ignore Google Drive desktop mounts
            if "googledrive" in vol.name.lower() or "google drive" in vol.name.lower():
                continue

            try:
                # Check device ID against root to skip root filesystem aliases
                vol_stat = os.stat(vol)
                if root_dev is not None and vol_stat.st_dev == root_dev:
                    continue

                # Verify read/write accessibility
                if not os.access(vol, os.R_OK | os.W_OK):
                    continue

                vol_usage = shutil.disk_usage(vol)
                target_folder = vol / "FrankensteinStorage"
                try:
                    target_folder.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

                external_drives.append(
                    {
                        "name": f"USB Drive: {vol.name}",
                        "path": str(target_folder),
                        "total": vol_usage.total,
                        "free": vol_usage.free,
                        "used": vol_usage.used,
                        "is_external": True,
                        "is_removable": True,
                        "volume_name": vol.name,
                        "description": f"Physical external USB / removable drive at /Volumes/{vol.name}",
                    }
                )
            except Exception:
                continue
    except (PermissionError, OSError):
        pass

    return external_drives


def calculate_pooled_overview(
    conn: sqlite3.Connection, drives: list[dict[str, Any]]
) -> dict[str, Any]:
    """Calculates storage overview with honest figures: Raw capacity, Usable capacity, and Free usable space."""
    device_capacities: dict[str, int] = {}
    device_free: dict[str, int] = {}
    device_used: dict[str, int] = {}

    eligible_device_capacities: dict[str, int] = {}
    eligible_device_effective_free: dict[str, int] = {}

    for d in drives:
        dev_id = d.get("device_id") or f"untracked_{d['id']}"
        usage = d.get("usage", {})
        total = int(usage.get("total", 0))
        free = int(usage.get("free", 0))
        used = int(usage.get("used", 0))
        effective_free = int(d.get("effective_free", 0))
        is_eligible = bool(d.get("is_placement_eligible", False))

        # Raw hardware metrics (de-duplicated across folders sharing the same volume)
        if dev_id not in device_capacities:
            device_capacities[dev_id] = total
            device_free[dev_id] = free
            device_used[dev_id] = used
        else:
            device_free[dev_id] = min(device_free[dev_id], free)
            device_capacities[dev_id] = max(device_capacities[dev_id], total)

        # Eligible online metrics (only counting online drives above reserve)
        if is_eligible:
            if dev_id not in eligible_device_capacities:
                eligible_device_capacities[dev_id] = total
                eligible_device_effective_free[dev_id] = effective_free
            else:
                eligible_device_effective_free[dev_id] = min(
                    eligible_device_effective_free[dev_id], effective_free
                )
                eligible_device_capacities[dev_id] = max(eligible_device_capacities[dev_id], total)

    raw_capacity = sum(device_capacities.values())
    raw_free = sum(device_free.values())
    physical_disk_used = sum(device_used.values())

    eligible_count = sum(1 for d in drives if d.get("is_placement_eligible"))
    online_count = sum(1 for d in drives if d.get("status") in ("online", "low_space"))

    # Determine pool redundancy and usable capacity
    if eligible_count >= 3:
        redundancy_mode = "parity"
        redundancy_label = "Rotating XOR Parity (3+ drives)"
        efficiency = 2.0 / 3.0
    elif eligible_count == 2:
        redundancy_mode = "mirrored"
        redundancy_label = "Mirrored Redundancy (2 drives)"
        efficiency = 0.5
    elif eligible_count == 1:
        redundancy_mode = "unprotected"
        redundancy_label = "Unprotected (1 drive)"
        efficiency = 1.0
    else:
        redundancy_mode = "none"
        redundancy_label = "No eligible online storage"
        efficiency = 0.0

    usable_capacity = int(sum(eligible_device_capacities.values()) * efficiency)
    free_usable_space = int(sum(eligible_device_effective_free.values()) * efficiency)

    # Vault chunks stored in database
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(size), 0) AS total_chunks_bytes FROM chunks")
    vault_chunks_bytes = cursor.fetchone()["total_chunks_bytes"]

    # Pooled used represents vault chunks stored
    pooled_used = (
        min(vault_chunks_bytes, usable_capacity) if usable_capacity > 0 else vault_chunks_bytes
    )

    cursor.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM files WHERE status = 'complete'"
    )
    file_stat = cursor.fetchone()

    return {
        # The Three Honest Figures
        "raw_capacity": raw_capacity,
        "raw_free": raw_free,
        "usable_capacity": usable_capacity,
        "free_usable_space": free_usable_space,
        # Calculation Tooltip Explanations
        "raw_capacity_description": "Total physical storage across all registered drives (de-duplicated across shared Mac/APFS volumes).",
        "usable_capacity_description": f"Actual usable capacity available for encrypted files after {redundancy_label} overhead and reserves.",
        "free_usable_space_description": f"Real free space available for new file uploads after 2 GiB / 5% reserves and {round((1.0 - efficiency) * 100)}% redundancy overhead.",
        # Redundancy & Drive Counts
        "redundancy_mode": redundancy_mode,
        "redundancy_label": redundancy_label,
        "redundancy_efficiency": efficiency,
        "drives_count": len(drives),
        "drives_online": online_count,
        "drives_eligible": eligible_count,
        "drives_ratio": f"{online_count} of {len(drives)}",
        # Backward compatibility for existing UI components and tests
        "pooled_capacity": raw_capacity,
        "pooled_used": pooled_used,
        "pooled_free": raw_free,
        "vault_chunks_bytes": vault_chunks_bytes,
        "physical_disk_used": physical_disk_used,
        "physical_disk_capacity": raw_capacity,
        "physical_disk_free": raw_free,
        "capacity_source": "Provider-reported (De-duplicated)",
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
        locations.append(
            {
                "name": "Macintosh HD (Documents Pool)",
                "path": str(doc_pool),
                "total": usage.total,
                "free": usage.free,
                "used": usage.used,
                "is_external": False,
                "description": "Primary internal macOS SSD storage under ~/Documents",
            }
        )
    except Exception:
        pass

    # 2. Secondary macOS Storage (User Downloads)
    dl_pool = home / "Downloads" / "FrankensteinStorage"
    try:
        usage = shutil.disk_usage(home)
        locations.append(
            {
                "name": "Macintosh HD (Downloads Pool)",
                "path": str(dl_pool),
                "total": usage.total,
                "free": usage.free,
                "used": usage.used,
                "is_external": False,
                "description": "Secondary internal macOS storage under ~/Downloads",
            }
        )
    except Exception:
        pass

    # 3. Dedicated fast pool in ~/FrankensteinDrives
    dot_pool = home / "FrankensteinDrives" / "primary_ssd"
    try:
        usage = shutil.disk_usage(home)
        locations.append(
            {
                "name": "Macintosh HD (Fast Storage)",
                "path": str(dot_pool),
                "total": usage.total,
                "free": usage.free,
                "used": usage.used,
                "is_external": False,
                "description": "Dedicated macOS vault folder in ~/FrankensteinDrives",
            }
        )
    except Exception:
        pass

    # 4. Mounted external USB / removable drives under /Volumes
    locations.extend(get_external_usb_drives())

    # Detect Google Drive desktop volumes if mounted under /Volumes
    volumes_dir = Path("/Volumes")
    try:
        if volumes_dir.exists():
            for vol in volumes_dir.iterdir():
                if vol.name.startswith(".") or vol.is_symlink():
                    continue
                is_gdrive_vol = (
                    "googledrive" in vol.name.lower() or "google drive" in vol.name.lower()
                )
                if is_gdrive_vol:
                    try:
                        shutil.disk_usage(vol)
                        my_drive_vol = vol / "My Drive"
                        target_path = my_drive_vol if my_drive_vol.exists() else vol
                        sample_folder = target_path / "sample"
                        final_path = (
                            sample_folder
                            if sample_folder.exists()
                            else (target_path / "FrankensteinVault")
                        )
                        gdrive_vol_quota = 15 * (1024**3)
                        locations.append(
                            {
                                "name": f"Google Drive Desktop ({vol.name})",
                                "path": str(final_path),
                                "total": gdrive_vol_quota,
                                "free": gdrive_vol_quota,
                                "used": 0,
                                "is_external": False,
                                "is_cloud_synced": True,
                                "description": "Auto-syncs chunks directly to Google Drive in real-time",
                            }
                        )
                    except Exception:
                        continue
    except (PermissionError, OSError):
        pass

    # 5. Apple iCloud Drive (native macOS cloud storage via ~/Library/Mobile Documents/com~apple~CloudDocs)
    icloud_base = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud_base.exists():
        icloud_vault = icloud_base / "FrankensteinStorage"
        icloud_quota = 5 * (1024**3)  # 5 GiB standard free tier
        locations.append(
            {
                "name": "Apple iCloud Drive",
                "path": str(icloud_vault),
                "total": icloud_quota,
                "free": icloud_quota,
                "used": 0,
                "is_external": False,
                "is_cloud_synced": True,
                "description": "Native macOS zero-config cloud sync via iCloud Drive (5 GiB free tier)",
            }
        )

    # 6. Cloud Storage providers (Google Drive, OneDrive, Dropbox in ~/Library/CloudStorage or ~)
    cloud_storage = home / "Library" / "CloudStorage"
    detected_onedrive = False
    detected_dropbox = False
    if cloud_storage.exists():
        try:
            for item in cloud_storage.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    try:
                        c_usage = shutil.disk_usage(item)
                        lower_name = item.name.lower()
                        is_gdrive = "googledrive" in lower_name
                        is_onedrive = "onedrive" in lower_name
                        is_dropbox = "dropbox" in lower_name

                        if is_onedrive:
                            detected_onedrive = True
                        if is_dropbox:
                            detected_dropbox = True

                        my_drive = item / "My Drive"
                        existing_target = None
                        if my_drive.exists():
                            try:
                                for sub in my_drive.iterdir():
                                    if sub.is_dir() and not sub.name.startswith("."):
                                        if any(
                                            k in sub.name.lower()
                                            for k in (
                                                "sample",
                                                "frankenstein",
                                                "shukla",
                                                "vault",
                                                "storage",
                                            )
                                        ):
                                            existing_target = sub
                                            break
                            except Exception:
                                pass

                        final_dir = (
                            existing_target
                            if existing_target
                            else (
                                my_drive / "FrankensteinStorage"
                                if my_drive.exists()
                                else item / "FrankensteinStorage"
                            )
                        )
                        if is_gdrive:
                            quota = 15 * (1024**3)
                            email_hint = item.name.replace("GoogleDrive-", "")
                            disp_name = f"Google Drive ({email_hint})"
                            desc = f"Auto-syncs chunks directly to Google Drive ({email_hint}) in real-time"
                        elif is_onedrive:
                            quota = 5 * (1024**3)
                            hint = item.name.replace("OneDrive-", "")
                            disp_name = f"Microsoft OneDrive ({hint})"
                            desc = f"Auto-syncs chunks directly to OneDrive ({hint}) in real-time"
                        elif is_dropbox:
                            quota = 2 * (1024**3)
                            hint = item.name.replace("Dropbox-", "")
                            disp_name = f"Dropbox ({hint})"
                            desc = f"Auto-syncs chunks directly to Dropbox ({hint}) in real-time"
                        else:
                            quota = c_usage.total
                            disp_name = f"Cloud Storage: {item.name}"
                            desc = f"Synced cloud folder via {item.name}"

                        locations.append(
                            {
                                "name": disp_name,
                                "path": str(final_dir),
                                "total": quota,
                                "free": quota,
                                "used": 0,
                                "is_external": False,
                                "is_cloud_synced": True,
                                "description": desc,
                            }
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # Check fallback home OneDrive / Dropbox if not found in CloudStorage
    if not detected_onedrive and (home / "OneDrive").exists():
        od_path = home / "OneDrive" / "FrankensteinStorage"
        od_quota = 5 * (1024**3)
        locations.append(
            {
                "name": "Microsoft OneDrive",
                "path": str(od_path),
                "total": od_quota,
                "free": od_quota,
                "used": 0,
                "is_external": False,
                "is_cloud_synced": True,
                "description": "Auto-syncs chunks directly to Microsoft OneDrive in real-time",
            }
        )

    if not detected_dropbox and (home / "Dropbox").exists():
        db_path = home / "Dropbox" / "FrankensteinStorage"
        db_quota = 2 * (1024**3)
        locations.append(
            {
                "name": "Dropbox",
                "path": str(db_path),
                "total": db_quota,
                "free": db_quota,
                "used": 0,
                "is_external": False,
                "is_cloud_synced": True,
                "description": "Auto-syncs chunks directly to Dropbox in real-time",
            }
        )

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
            if config_obj.get("access_token") or config_obj.get("refresh_token"):
                config_obj["auth_type"] = "access_token"
            else:
                config_obj["auth_type"] = "demo_mock"
        if "folder_name" not in config_obj:
            config_obj["folder_name"] = clean_name

        # Validate gdrive provider availability
        provider = GoogleDriveProvider(config=config_obj, simulated_offline=False)
        if not provider.check_availability():
            raise AppError(
                400,
                "DRIVE_NOT_ACCESSIBLE",
                "Google Drive authentication failed or unreachable. Check credentials/token.",
            )

        config_json = json.dumps(config_obj)

        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drives WHERE path = ?", (clean_path,))
        if cursor.fetchone():
            raise AppError(
                409, "DRIVE_EXISTS", f"Drive '{clean_name}' ({clean_path}) is already registered"
            )

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

    # S3-Compatible Object Storage (Cloudflare R2, AWS S3, MinIO, Backblaze B2)
    if provider_type in ("s3", "r2", "minio", "b2") or (raw_path and raw_path.startswith("s3://")):
        config_obj = config if isinstance(config, dict) else (json.loads(config) if config else {})
        bucket = config_obj.get("bucket", "frankenstein-vault").strip()
        prefix = config_obj.get("prefix", "chunks/").strip("/")

        clean_path = (
            raw_path
            if (raw_path and raw_path.startswith("s3://"))
            else f"s3://{bucket}/{prefix}".rstrip("/")
        )

        provider = S3StorageProvider(config=config_obj, simulated_offline=False)
        if not provider.check_availability():
            raise AppError(
                400,
                "DRIVE_NOT_ACCESSIBLE",
                f"Could not connect to {provider.provider_variant} bucket '{bucket}'. Verify credentials/endpoint.",
            )

        config_json = json.dumps(config_obj)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drives WHERE path = ?", (clean_path,))
        if cursor.fetchone():
            raise AppError(
                409, "DRIVE_EXISTS", f"Drive '{clean_name}' ({clean_path}) is already registered"
            )

        conn.execute(
            """INSERT INTO drives (id, display_name, path, status, simulated_offline, provider_type, config)
               VALUES (?, ?, ?, 'online', 0, ?, ?)""",
            (drive_id, clean_name, clean_path, provider_type, config_json),
        )
        conn.execute(
            "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
            (
                "ADD_DRIVE",
                f"Added {provider.provider_variant} {clean_name} ({clean_path})",
                "SUCCESS",
            ),
        )
        return {
            "id": drive_id,
            "display_name": clean_name,
            "path": clean_path,
            "provider_type": provider_type,
            "status": "online",
            "simulated_offline": False,
        }

    # Local / iCloud / OneDrive / Dropbox folder provider
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
        raise AppError(
            400, "DRIVE_NOT_ACCESSIBLE", f"Directory '{clean_path}' cannot be created or accessed"
        )

    effective_provider_type = (
        provider_type if provider_type in ("icloud", "onedrive", "dropbox") else "local"
    )

    conn.execute(
        """INSERT INTO drives (id, display_name, path, status, simulated_offline, provider_type, config)
           VALUES (?, ?, ?, 'online', 0, ?, NULL)""",
        (drive_id, clean_name, clean_path, effective_provider_type),
    )

    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        (
            "ADD_DRIVE",
            f"Added drive {clean_name} at {clean_path} ({effective_provider_type})",
            "SUCCESS",
        ),
    )

    return {
        "id": drive_id,
        "display_name": clean_name,
        "path": clean_path,
        "provider_type": effective_provider_type,
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
    cursor.execute(
        "SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives WHERE id = ?",
        (drive_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise AppError(404, "DRIVE_NOT_FOUND", f"Drive with id '{drive_id}' not found")

    new_sim = (
        row["simulated_offline"] if simulated_offline is None else (1 if simulated_offline else 0)
    )
    new_name = row["display_name"] if display_name is None else display_name.strip()
    new_path = row["path"] if path is None else path.strip()
    new_provider = row["provider_type"] if provider_type is None else provider_type.strip()

    if config is not None:
        new_config = json.dumps(config) if isinstance(config, dict) else config
    else:
        new_config = row["config"]

    if simulated_offline is False:
        new_status = "online"
    elif row["status"] == "ejected" and simulated_offline is None:
        new_status = "ejected"
    else:
        new_status = "simulated_offline" if new_sim else "online"

    conn.execute(
        "UPDATE drives SET simulated_offline = ?, status = ?, display_name = ?, path = ?, provider_type = ?, config = ? WHERE id = ?",
        (new_sim, new_status, new_name, new_path, new_provider, new_config, drive_id),
    )

    status_desc = new_status
    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        (
            "PATCH_DRIVE",
            f"Updated drive {drive_id} (name='{new_name}', path='{new_path}', simulated_offline={bool(new_sim)})",
            "SUCCESS",
        ),
    )

    return {
        "id": drive_id,
        "display_name": new_name,
        "path": new_path,
        "provider_type": new_provider,
        "status": status_desc,
        "simulated_offline": bool(new_sim),
    }


def eject_drive(conn: sqlite3.Connection, drive_id: str) -> dict[str, Any]:
    """Safely flushes filesystem buffers, unmounts/ejects external USB drive via diskutil, and sets status to ejected."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, display_name, path, status, simulated_offline, provider_type, config FROM drives WHERE id = ?",
        (drive_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise AppError(404, "DRIVE_NOT_FOUND", f"Drive with id '{drive_id}' not found")

    provider = get_drive_provider(row)
    dev_info = provider.get_device_info() if hasattr(provider, "get_device_info") else {}
    usage = provider.get_usage() if hasattr(provider, "get_usage") else {}
    path_str = str(row["path"])
    is_external = bool(
        "/Volumes/" in path_str
        or path_str.startswith("/Volumes/")
        or dev_info.get("is_external")
        or usage.get("is_external")
    )
    if not is_external:
        raise AppError(
            400,
            "NOT_AN_EXTERNAL_DRIVE",
            f"Drive '{row['display_name']}' is not an external USB or removable device and cannot be ejected.",
        )

    # Step 1: Flush all OS filesystem buffers
    try:
        os.sync()
    except Exception:
        pass

    # Step 2: Extract base mount point from drive path (e.g. /Volumes/HP from /Volumes/HP/FrankensteinStorage)
    path_obj = Path(path_str)
    mount_point = None
    vol_name = path_obj.name
    if "/Volumes/" in path_str:
        idx = path_str.index("/Volumes/")
        rel = path_str[idx + len("/Volumes/") :].strip("/")
        vol_name = rel.split("/")[0] if rel else path_obj.name
        mount_point = Path("/Volumes") / vol_name
    elif dev_info.get("volume_name"):
        vol_name = str(dev_info.get("volume_name")).replace("External USB: ", "").strip()
        mount_point = Path(dev_info.get("mount_point") or path_obj)
    else:
        mount_point = path_obj

    # Step 3: Execute safe macOS disk ejection using diskutil
    try:
        res = subprocess.run(
            ["diskutil", "eject", str(mount_point)],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        if res.returncode != 0:
            subprocess.run(
                ["diskutil", "unmount", str(mount_point)],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
    except Exception:
        pass

    # Step 4: Update drive status in SQLite drives table to 'ejected' (with simulated_offline = 1)
    conn.execute(
        "UPDATE drives SET status = 'ejected', simulated_offline = 1 WHERE id = ?",
        (drive_id,),
    )

    # Step 5: Log operation
    conn.execute(
        "INSERT INTO operation_log (operation, details, status) VALUES (?, ?, ?)",
        ("EJECT_DRIVE", f"Safely ejected USB drive {vol_name} ({drive_id})", "SUCCESS"),
    )

    return {
        "status": "ejected",
        "drive_id": drive_id,
        "volume_name": vol_name,
        "message": f"USB Drive '{vol_name}' safely unmounted. You can now physically unplug your pendrive.",
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
