"""Local folder storage provider implementing the StorageProvider interface."""

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.errors import AppError
from backend.app.providers.base import StorageProvider

HEX_UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class LocalFolderProvider(StorageProvider):
    def __init__(self, root_path: str | Path, simulated_offline: bool = False):
        self.raw_path = Path(root_path)
        self.root_path = self.raw_path.resolve()
        # For cloud-synced folders (Google Drive, OneDrive) or external removable drives (/Volumes):
        # Use visible frankenstein_storage (no leading dot) so files are fully visible in macOS Finder!
        is_visible = (
            "CloudStorage" in str(self.root_path)
            or "GoogleDrive" in str(self.root_path)
            or "My Drive" in str(self.root_path)
            or "Volumes" in str(self.root_path)
        )
        if is_visible:
            self.dot_frankenstein = (self.root_path / "frankenstein_storage").resolve()
        else:
            self.dot_frankenstein = (self.root_path / ".frankenstein").resolve()

        self.chunks_dir = (self.dot_frankenstein / "chunks").resolve()
        self.tmp_dir = (self.dot_frankenstein / "tmp").resolve()
        self.simulated_offline = bool(simulated_offline)
        
        # Verify root_path does not point inside an existing storage directory
        if ".frankenstein" in self.root_path.parts or "frankenstein_storage" in self.root_path.parts:
            raise AppError(400, "INVALID_PATH", "Drive root cannot be inside a vault storage directory")
            
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        if self.simulated_offline:
            return
        try:
            if not self.root_path.exists():
                self.root_path.mkdir(parents=True, exist_ok=True)
            self.chunks_dir.mkdir(parents=True, exist_ok=True)
            self.tmp_dir.mkdir(parents=True, exist_ok=True)

            # Auto-migrate any chunks from legacy hidden .frankenstein folder to visible frankenstein_storage
            legacy_chunks = self.root_path / ".frankenstein" / "chunks"
            if legacy_chunks.exists() and legacy_chunks.is_dir() and "Volumes" in str(self.root_path):
                try:
                    for ab_dir in legacy_chunks.iterdir():
                        if ab_dir.is_dir():
                            for cd_dir in ab_dir.iterdir():
                                if cd_dir.is_dir():
                                    for f in cd_dir.iterdir():
                                        if f.is_file() and not f.name.startswith("."):
                                            dest = self.chunks_dir / ab_dir.name / cd_dir.name / f.name
                                            dest.parent.mkdir(parents=True, exist_ok=True)
                                            if not dest.exists():
                                                f.rename(dest)
                except Exception:
                    pass

            # Write friendly info file on external pendrive volumes so users know what it is
            if "Volumes" in str(self.root_path):
                readme = self.root_path / "README_VAULT_INFO.txt"
                if not readme.exists():
                    try:
                        readme.write_text(
                            "==================================================\n"
                            "🧟 FRANKENSTEIN STORAGE VAULT\n"
                            "==================================================\n"
                            "This folder is an active drive for Frankenstein Storage.\n"
                            "Encrypted chunk files are stored in: frankenstein_storage/chunks/\n\n"
                            "To manage, preview, and download your files, use the dashboard at:\n"
                            "http://127.0.0.1:5173\n"
                            "==================================================\n"
                        )
                    except Exception:
                        pass
        except OSError:
            # Gracefully handle removable volumes that are unmounted / unplugged
            pass

    def _validate_chunk_id(self, chunk_id: str) -> None:
        if not isinstance(chunk_id, str) or not HEX_UUID_PATTERN.match(chunk_id):
            raise AppError(400, "INVALID_CHUNK_ID", f"Invalid chunk_id format: {chunk_id}")

    def _get_chunk_path(self, chunk_id: str) -> Path:
        self._validate_chunk_id(chunk_id)
        ab = chunk_id[:2]
        cd = chunk_id[2:4]
        target = (self.chunks_dir / ab / cd / chunk_id).resolve()
        
        # Check backward compatibility with legacy .frankenstein path
        if not target.exists():
            legacy_dot = (self.root_path / ".frankenstein" / "chunks" / ab / cd / chunk_id).resolve()
            if legacy_dot.exists():
                return legacy_dot

        # Guard against path traversal and symlink escapes
        try:
            target.relative_to(self.chunks_dir)
        except ValueError:
            raise AppError(400, "SECURITY_ERROR", "Path traversal or symlink escape detected")
            
        return target

    def check_availability(self) -> bool:
        if self.simulated_offline:
            return False
        try:
            path_str = str(self.root_path)
            # Robust check for removable external volumes mounted under /Volumes
            if path_str.startswith("/Volumes/"):
                parts = Path(path_str).parts
                if len(parts) >= 3:
                    vol_root = Path(parts[0]) / parts[1] / parts[2]
                    # If /Volumes/<Volume_Name> is not currently mounted or is not a directory
                    if not vol_root.exists() or not vol_root.is_dir():
                        return False

            return self.root_path.exists() and self.root_path.is_dir() and os.access(self.root_path, os.R_OK | os.W_OK)
        except Exception:
            return False

    def _get_folder_size(self, path: Path) -> int:
        """Recursively calculate the actual size in bytes of files in the folder."""
        total = 0
        if not path.exists():
            return 0
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    try:
                        if not fp.is_symlink():
                            total += fp.stat().st_size
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    def get_usage(self) -> dict[str, Any]:
        dev_info = self.get_device_info()
        is_external = bool(dev_info.get("is_external"))
        if not self.check_availability():
            return {
                "total": 0,
                "used": 0,
                "free": 0,
                "source": "External USB (Offline)" if is_external else "Provider-reported",
                "measured_used": 0,
                "available": False,
                "device_id": dev_info.get("device_id"),
                "st_dev": dev_info.get("st_dev"),
                "volume_name": dev_info.get("volume_name"),
                "is_external": is_external,
                "is_removable": bool(dev_info.get("is_removable")),
            }
        try:
            usage = shutil.disk_usage(self.root_path)
            # Calculate measured chunk usage in the vault chunks directory
            measured = 0
            if self.chunks_dir.exists():
                for root, _, files in os.walk(self.chunks_dir):
                    for f in files:
                        p = Path(root) / f
                        try:
                            if not p.is_symlink():
                                measured += p.stat().st_size
                        except OSError:
                            pass

            path_str = str(self.root_path)
            is_cloud = "CloudStorage" in path_str or "GoogleDrive" in path_str or "My Drive" in path_str

            # If this is a Google Drive desktop synced folder, reflect real Google Drive capacity (15 GiB standard free tier)
            # and calculate usage based on the real files in the selected folder, rather than the host Mac SSD.
            if is_cloud:
                gdrive_total = 15 * (1024 ** 3)  # 15 GiB standard Google Drive cloud quota
                folder_used = self._get_folder_size(self.root_path)
                real_used = max(folder_used, measured)
                real_free = max(0, gdrive_total - real_used)
                return {
                    "total": gdrive_total,
                    "used": real_used,
                    "free": real_free,
                    "source": "Google Drive Cloud (15 GiB)",
                    "measured_used": measured,
                    "available": True,
                    "device_id": "gdrive_cloud_storage",
                    "st_dev": dev_info.get("st_dev"),
                    "volume_name": "Google Drive (Cloud Synced)",
                    "is_cloud_synced": True,
                    "is_external": False,
                    "is_removable": False,
                    "host_disk_total": usage.total,
                    "host_disk_used": usage.used,
                }

            # For regular local folders or external USB on macOS
            folder_used = self._get_folder_size(self.root_path)
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "source": "External USB Storage" if is_external else "macOS Storage",
                "measured_used": measured,
                "folder_size": folder_used,
                "available": True,
                "device_id": dev_info.get("device_id"),
                "st_dev": dev_info.get("st_dev"),
                "volume_name": dev_info.get("volume_name"),
                "is_external": is_external,
                "is_removable": bool(dev_info.get("is_removable")),
            }
        except Exception as e:
            raise AppError(500, "DRIVE_ERROR", f"Failed to get drive usage: {e}")

    def get_device_info(self) -> dict[str, Any]:
        try:
            path_str = str(self.root_path)
            is_cloud = "CloudStorage" in path_str or "GoogleDrive" in path_str or "My Drive" in path_str
            if is_cloud:
                return {
                    "device_id": "gdrive_cloud_storage",
                    "st_dev": "gdrive_cloud",
                    "mount_point": str(self.root_path),
                    "volume_name": "Google Drive Cloud Storage",
                    "is_cloud_synced": True,
                    "is_external": False,
                    "is_removable": False,
                }

            is_external_usb = False
            vol_root_name = None
            if path_str.startswith("/Volumes/"):
                parts = Path(path_str).parts
                if len(parts) >= 3:
                    cand_name = parts[2]
                    # Exclude internal boot volume aliases like Macintosh HD or Recovery
                    if cand_name not in ("Macintosh HD", "Recovery") and not cand_name.startswith("."):
                        is_external_usb = True
                        vol_root_name = cand_name

            p = self.root_path
            while not p.exists() and p != p.parent:
                p = p.parent

            if not p.exists():
                if is_external_usb and vol_root_name:
                    return {
                        "device_id": f"usb_{vol_root_name}",
                        "st_dev": None,
                        "mount_point": f"/Volumes/{vol_root_name}",
                        "volume_name": f"External USB: {vol_root_name}",
                        "is_external": True,
                        "is_removable": True,
                    }
                return {
                    "device_id": None,
                    "st_dev": None,
                    "mount_point": None,
                    "volume_name": None,
                    "is_external": False,
                    "is_removable": False,
                }

            st = os.stat(p)
            dev_id = f"usb_{st.st_dev}" if is_external_usb else f"dev_{st.st_dev}"
            mount_path = p
            while mount_path.parent != mount_path:
                try:
                    parent_st = os.stat(mount_path.parent)
                    if parent_st.st_dev != st.st_dev:
                        break
                    mount_path = mount_path.parent
                except Exception:
                    break

            if is_external_usb:
                vname = f"External USB: {vol_root_name or mount_path.name}"
            else:
                vname = (
                    "Macintosh HD (APFS Volume)"
                    if "Volumes/Data" in str(mount_path) or mount_path == Path("/")
                    else f"Volume ({mount_path.name or 'Root'})"
                )

            return {
                "device_id": dev_id,
                "st_dev": st.st_dev,
                "mount_point": str(mount_path),
                "volume_name": vname,
                "is_external": is_external_usb,
                "is_removable": is_external_usb,
            }
        except Exception:
            return {
                "device_id": None,
                "st_dev": None,
                "mount_point": None,
                "volume_name": None,
                "is_external": False,
                "is_removable": False,
            }

    def put_chunk(self, chunk_id: str, data: bytes) -> None:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", "Drive is offline or unavailable")

        target_file = self._get_chunk_path(chunk_id)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Temporary file write, fsync, atomic rename
        temp_file = (self.tmp_dir / f"{uuid.uuid4().hex}.tmp").resolve()
        try:
            temp_file.relative_to(self.tmp_dir)
        except ValueError:
            raise AppError(400, "SECURITY_ERROR", "Path traversal detected in temporary file path")

        try:
            with open(temp_file, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Atomic rename
            temp_file.replace(target_file)
        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise AppError(500, "CHUNK_WRITE_FAILED", f"Failed to write chunk {chunk_id}: {e}")

    def get_chunk(self, chunk_id: str) -> bytes:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", "Drive is offline or unavailable")

        chunk_path = self._get_chunk_path(chunk_id)
        if not chunk_path.exists() or not chunk_path.is_file():
            raise AppError(404, "CHUNK_NOT_FOUND", f"Chunk {chunk_id} not found on drive")

        # Symlink escape verification on read
        if chunk_path.is_symlink():
            resolved = chunk_path.resolve()
            try:
                resolved.relative_to(self.chunks_dir)
            except ValueError:
                raise AppError(400, "SECURITY_ERROR", "Chunk is a symlink escaping storage boundary")

        try:
            with open(chunk_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise AppError(500, "CHUNK_READ_FAILED", f"Failed to read chunk {chunk_id}: {e}")

    def delete_chunk(self, chunk_id: str) -> bool:
        if not self.check_availability():
            return False
        try:
            chunk_path = self._get_chunk_path(chunk_id)
            if chunk_path.exists():
                chunk_path.unlink()
                return True
            return False
        except Exception:
            return False

    def cleanup_temp_files(self) -> int:
        """Cleans up any orphaned .tmp files in .frankenstein/tmp."""
        cleaned = 0
        if self.tmp_dir.exists():
            for f in self.tmp_dir.glob("*.tmp"):
                try:
                    f.unlink()
                    cleaned += 1
                except OSError:
                    pass
        return cleaned
