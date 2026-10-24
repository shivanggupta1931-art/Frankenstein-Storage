"""Local folder storage provider implementing the StorageProvider interface."""

from datetime import datetime, timezone
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
        if self._is_external_or_visible():
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

    def _is_external_or_visible(self) -> bool:
        path_str = str(self.root_path)
        return (
            "CloudStorage" in path_str
            or "GoogleDrive" in path_str
            or "My Drive" in path_str
            or "Volumes" in path_str
            or "Mobile Documents" in path_str
            or "com~apple~CloudDocs" in path_str
            or "iCloud Drive" in path_str
            or "OneDrive" in path_str
            or "Dropbox" in path_str
        )

    def _is_external_usb(self) -> bool:
        return "Volumes" in str(self.root_path)

    def _ensure_dirs(self) -> None:
        if self.simulated_offline:
            return
        try:
            if not self.root_path.exists():
                self.root_path.mkdir(parents=True, exist_ok=True)
            self.chunks_dir.mkdir(parents=True, exist_ok=True)
            self.tmp_dir.mkdir(parents=True, exist_ok=True)

            if self._is_external_or_visible():
                # 1. Auto-flatten any nested chunks in self.chunks_dir (chunks/ab/cd/<chunk_id> -> chunks/<chunk_id>)
                try:
                    for ab_dir in list(self.chunks_dir.iterdir()):
                        if ab_dir.is_dir() and len(ab_dir.name) == 2 and not ab_dir.name.startswith("."):
                            for cd_dir in list(ab_dir.iterdir()):
                                if cd_dir.is_dir() and len(cd_dir.name) == 2 and not cd_dir.name.startswith("."):
                                    for f in list(cd_dir.iterdir()):
                                        if f.is_file() and not f.name.startswith(".") and HEX_UUID_PATTERN.match(f.name):
                                            dest = self.chunks_dir / f.name
                                            if not dest.exists():
                                                f.rename(dest)
                                            else:
                                                f.unlink()
                                        elif f.is_file() and (f.name.startswith("._") or f.name == ".DS_Store"):
                                            try:
                                                f.unlink()
                                            except OSError:
                                                pass
                                    try:
                                        cd_dir.rmdir()
                                    except OSError:
                                        pass
                                elif cd_dir.is_file() and (cd_dir.name.startswith("._") or cd_dir.name == ".DS_Store"):
                                    try:
                                        cd_dir.unlink()
                                    except OSError:
                                        pass
                            try:
                                ab_dir.rmdir()
                            except OSError:
                                pass
                        elif ab_dir.is_file() and (ab_dir.name.startswith("._") or ab_dir.name == ".DS_Store"):
                            try:
                                ab_dir.unlink()
                            except OSError:
                                pass
                except Exception:
                    pass

                # 2. Auto-migrate legacy hidden .frankenstein directory (flat or nested) into visible flat chunks
                legacy_dot_dir = self.root_path / ".frankenstein"
                if legacy_dot_dir.exists() and legacy_dot_dir.is_dir():
                    try:
                        for root, dirs, files in os.walk(str(legacy_dot_dir), topdown=False):
                            for fname in files:
                                if not fname.startswith(".") and HEX_UUID_PATTERN.match(fname):
                                    src = Path(root) / fname
                                    dest = self.chunks_dir / fname
                                    if not dest.exists():
                                        shutil.move(str(src), str(dest))
                                    else:
                                        src.unlink()
                                elif fname.startswith("._") or fname == ".DS_Store":
                                    try:
                                        (Path(root) / fname).unlink()
                                    except OSError:
                                        pass
                            for dname in dirs:
                                try:
                                    (Path(root) / dname).rmdir()
                                except OSError:
                                    pass
                        try:
                            shutil.rmtree(str(legacy_dot_dir), ignore_errors=True)
                        except Exception:
                            pass
                    except Exception:
                        pass

            if self._is_external_usb():
                # 3. Write friendly info file & updated manifest for external USB drives
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

                self._update_manifest()
        except OSError:
            # Gracefully handle removable volumes that are unmounted / unplugged
            pass

    def _update_manifest(self) -> None:
        """Generates or updates a human-readable VAULT_MANIFEST.txt file for external drives."""
        if not self._is_external_usb() or self.simulated_offline:
            return
        try:
            if not self.chunks_dir.exists():
                return
            
            chunk_files = [
                f for f in self.chunks_dir.iterdir()
                if f.is_file() and not f.name.startswith(".") and HEX_UUID_PATTERN.match(f.name)
            ]
            chunk_files.sort(key=lambda x: x.name)
            
            total_bytes = sum(f.stat().st_size for f in chunk_files)
            dev_info = self.get_device_info()
            vol_name = dev_info.get("volume_name") or self.root_path.name
            
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            
            lines = [
                "=" * 80,
                "🧟 FRANKENSTEIN STORAGE — EXTERNAL DRIVE MANIFEST",
                "=" * 80,
                f"Drive / Volume   : {vol_name}",
                f"Storage Path     : {self.root_path}",
                f"Status           : ONLINE & ACTIVE",
                f"Encryption       : AES-256-GCM (Zero-Knowledge Authenticated)",
                f"Redundancy       : Striped XOR Parity & Cross-Drive Mirroring",
                f"Last Updated     : {now_str}",
                "-" * 80,
                "STORED ENCRYPTED CHUNKS DIRECTORY:",
                f"  frankenstein_storage/chunks/ (flat directory structure)",
                "",
                "Summary:",
                f"  Total Chunks Stored : {len(chunk_files)}",
                f"  Total Encrypted Data: {total_bytes:,} bytes ({total_bytes / (1024 * 1024):.2f} MiB)",
                "-" * 80,
                f"{'#':<4} {'Chunk ID':<36} {'Size (Bytes)':<16} {'Last Modified (UTC)'}",
                "-" * 80,
            ]
            
            for idx, cf in enumerate(chunk_files, 1):
                st = cf.stat()
                mtime_str = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"{idx:<4} {cf.name:<36} {st.st_size:<16,} {mtime_str}")
                
            lines.extend([
                "=" * 80,
                "⚠️ NOTICE:",
                "Do not edit or delete these encrypted chunk files directly.",
                "To unlock, preview, or restore files, access the Frankenstein dashboard at:",
                "http://127.0.0.1:5173",
                "=" * 80,
                "",
            ])
            
            content = "\n".join(lines)
            
            manifest_root = self.root_path / "VAULT_MANIFEST.txt"
            manifest_root.write_text(content, encoding="utf-8")
            
            manifest_dot = self.dot_frankenstein / "VAULT_MANIFEST.txt"
            if manifest_dot != manifest_root:
                manifest_dot.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _validate_chunk_id(self, chunk_id: str) -> None:
        if not isinstance(chunk_id, str) or not HEX_UUID_PATTERN.match(chunk_id):
            raise AppError(400, "INVALID_CHUNK_ID", f"Invalid chunk_id format: {chunk_id}")

    def _get_chunk_path(self, chunk_id: str) -> Path:
        self._validate_chunk_id(chunk_id)
        
        # On external USB drives or visible storage folders:
        # Chunks are stored directly in chunks/<chunk_id> for flat macOS Finder visibility!
        if self._is_external_or_visible():
            flat_target = (self.chunks_dir / chunk_id).resolve()
            if flat_target.exists():
                return flat_target
                
            # Backward compatibility: check legacy nested chunks/ab/cd/<chunk_id>
            ab = chunk_id[:2]
            cd = chunk_id[2:4]
            nested_target = (self.chunks_dir / ab / cd / chunk_id).resolve()
            if nested_target.exists():
                return nested_target

            # Check legacy hidden .frankenstein directory
            legacy_dot = (self.root_path / ".frankenstein" / "chunks" / ab / cd / chunk_id).resolve()
            if legacy_dot.exists():
                return legacy_dot
            legacy_dot_flat = (self.root_path / ".frankenstein" / "chunks" / chunk_id).resolve()
            if legacy_dot_flat.exists():
                return legacy_dot_flat

            # Target for new chunk writes on external drive is flat
            try:
                flat_target.relative_to(self.chunks_dir)
            except ValueError:
                raise AppError(400, "SECURITY_ERROR", "Path traversal or symlink escape detected")
            return flat_target

        # For internal drives: check flat first in case migrated, else standard nested ab/cd/<chunk_id>
        flat_candidate = (self.chunks_dir / chunk_id).resolve()
        if flat_candidate.exists():
            return flat_candidate

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
            is_icloud = "Mobile Documents" in path_str or "com~apple~CloudDocs" in path_str or "iCloud Drive" in path_str
            is_onedrive = "OneDrive" in path_str
            is_dropbox = "Dropbox" in path_str
            is_gdrive = "GoogleDrive" in path_str or "My Drive" in path_str or ("CloudStorage" in path_str and not is_onedrive and not is_dropbox)
            is_cloud = is_icloud or is_onedrive or is_dropbox or is_gdrive

            # If this is a cloud-synced folder, reflect realistic cloud tier quota
            # and calculate usage based on real files in the selected folder, rather than the host Mac SSD.
            if is_cloud:
                folder_used = self._get_folder_size(self.root_path)
                real_used = max(folder_used, measured)
                if is_icloud:
                    cloud_total = 5 * (1024 ** 3)
                    cloud_source = "Apple iCloud Drive (5 GiB)"
                    cloud_vol = "Apple iCloud Drive (Cloud Synced)"
                    cloud_dev_id = "icloud_drive_cloud_storage"
                elif is_onedrive:
                    cloud_total = 5 * (1024 ** 3)
                    cloud_source = "Microsoft OneDrive (5 GiB)"
                    cloud_vol = "Microsoft OneDrive (Cloud Synced)"
                    cloud_dev_id = "onedrive_cloud_storage"
                elif is_dropbox:
                    cloud_total = 2 * (1024 ** 3)
                    cloud_source = "Dropbox Cloud (2 GiB)"
                    cloud_vol = "Dropbox (Cloud Synced)"
                    cloud_dev_id = "dropbox_cloud_storage"
                else:
                    cloud_total = 15 * (1024 ** 3)
                    cloud_source = "Google Drive Cloud (15 GiB)"
                    cloud_vol = "Google Drive (Cloud Synced)"
                    cloud_dev_id = "gdrive_cloud_storage"

                real_free = max(0, cloud_total - real_used)
                return {
                    "total": cloud_total,
                    "used": real_used,
                    "free": real_free,
                    "source": cloud_source,
                    "measured_used": measured,
                    "available": True,
                    "device_id": cloud_dev_id,
                    "st_dev": dev_info.get("st_dev"),
                    "volume_name": cloud_vol,
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
            is_icloud = "Mobile Documents" in path_str or "com~apple~CloudDocs" in path_str or "iCloud Drive" in path_str
            is_onedrive = "OneDrive" in path_str
            is_dropbox = "Dropbox" in path_str
            is_gdrive = "GoogleDrive" in path_str or "My Drive" in path_str or ("CloudStorage" in path_str and not is_onedrive and not is_dropbox)

            if is_icloud:
                return {
                    "device_id": "icloud_drive_cloud_storage",
                    "st_dev": "icloud_cloud",
                    "mount_point": str(self.root_path),
                    "volume_name": "Apple iCloud Drive Cloud Storage",
                    "is_cloud_synced": True,
                    "is_external": False,
                    "is_removable": False,
                }
            if is_onedrive:
                return {
                    "device_id": "onedrive_cloud_storage",
                    "st_dev": "onedrive_cloud",
                    "mount_point": str(self.root_path),
                    "volume_name": "Microsoft OneDrive Cloud Storage",
                    "is_cloud_synced": True,
                    "is_external": False,
                    "is_removable": False,
                }
            if is_dropbox:
                return {
                    "device_id": "dropbox_cloud_storage",
                    "st_dev": "dropbox_cloud",
                    "mount_point": str(self.root_path),
                    "volume_name": "Dropbox Cloud Storage",
                    "is_cloud_synced": True,
                    "is_external": False,
                    "is_removable": False,
                }
            if is_gdrive:
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
            self._update_manifest()
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
                self._update_manifest()
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
