"""Google Drive storage provider communicating directly with Google Drive API v3."""

import json
import time
from typing import Any

import httpx

from backend.app.core.errors import AppError
from backend.app.providers.base import StorageProvider

GDRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GDRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleDriveProvider(StorageProvider):
    """Stores encrypted chunks as real files inside a real Google Drive folder."""

    def __init__(
        self,
        config: dict[str, Any] | str | None = None,
        simulated_offline: bool = False,
    ):
        if isinstance(config, str):
            try:
                self.config = json.loads(config)
            except Exception:
                self.config = {"access_token": config}
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = {}

        self.simulated_offline = bool(simulated_offline)
        self.access_token: str | None = self.config.get("access_token")
        self.refresh_token: str | None = self.config.get("refresh_token")
        self.client_id: str | None = self.config.get("client_id")
        self.client_secret: str | None = self.config.get("client_secret")
        self.folder_id: str | None = self.config.get("folder_id")
        self.folder_name: str = self.config.get("folder_name", "FrankensteinVault")
        self.token_expiry: float = float(self.config.get("token_expiry", 0))

        # In-memory mapping from chunk_id -> google_drive_file_id
        self._chunk_cache: dict[str, str] = {}

    def _refresh_access_token_if_needed(self) -> None:
        now = time.time()
        # If token is valid for at least 60 more seconds, reuse it
        if self.access_token and (self.token_expiry == 0 or now < (self.token_expiry - 60)):
            return

        if not self.refresh_token or not self.client_id or not self.client_secret:
            if not self.access_token:
                raise AppError(401, "GDRIVE_UNAUTHORIZED", "Google Drive access token missing or expired without refresh token")
            return

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    self.access_token = data["access_token"]
                    expires_in = data.get("expires_in", 3600)
                    self.token_expiry = now + expires_in
                else:
                    raise AppError(401, "GDRIVE_AUTH_FAILED", f"Failed to refresh Google Drive token: {res.text}")
        except Exception as e:
            if isinstance(e, AppError):
                raise e
            raise AppError(503, "GDRIVE_UNAVAILABLE", f"Network error during Google Drive token refresh: {e}")

    def _get_headers(self) -> dict[str, str]:
        self._refresh_access_token_if_needed()
        return {
            "Authorization": f"Bearer {self.access_token}",
        }

    def check_availability(self) -> bool:
        if self.simulated_offline:
            return False

        if not self.access_token and not self.refresh_token:
            return False

        try:
            headers = self._get_headers()
            with httpx.Client(timeout=6.0) as client:
                res = client.get(
                    f"{GDRIVE_API_BASE}/about",
                    headers=headers,
                    params={"fields": "user"},
                )
                return res.status_code == 200
        except Exception:
            return False

    def get_usage(self) -> dict[str, Any]:
        if not self.check_availability():
            return {
                "total": 0,
                "used": 0,
                "free": 0,
                "source": "Google Drive (Offline)",
                "measured_used": 0,
                "available": False,
            }

        try:
            headers = self._get_headers()
            with httpx.Client(timeout=8.0) as client:
                res = client.get(
                    f"{GDRIVE_API_BASE}/about",
                    headers=headers,
                    params={"fields": "storageQuota,user"},
                )
                if res.status_code != 200:
                    raise AppError(503, "GDRIVE_API_ERROR", f"Failed to fetch Google Drive storage quota: {res.text}")

                data = res.json()
                quota = data.get("storageQuota", {})
                user = data.get("user", {})
                email = user.get("emailAddress", "Google Drive")

                # Limit in bytes (or 15 GiB if unlimited/unspecified)
                limit_str = quota.get("limit")
                limit = int(limit_str) if limit_str else (15 * 1024 * 1024 * 1024)
                usage = int(quota.get("usage", 0))
                usage_in_drive = int(quota.get("usageInDrive", 0))

                return {
                    "total": limit,
                    "used": usage,
                    "free": max(0, limit - usage),
                    "source": f"Google Drive ({email})",
                    "measured_used": usage_in_drive,
                    "available": True,
                    "device_id": f"gdrive_{self.folder_id or self.folder_name}",
                    "volume_name": f"Google Drive ({email})",
                }
        except Exception as e:
            if isinstance(e, AppError):
                raise e
            raise AppError(500, "GDRIVE_ERROR", f"Error checking Google Drive usage: {e}")

    def get_device_info(self) -> dict[str, Any]:
        return {
            "device_id": f"gdrive_{self.folder_id or self.folder_name}",
            "st_dev": None,
            "mount_point": None,
            "volume_name": f"Google Drive Cloud ({self.folder_name})",
        }

    def _ensure_vault_folder(self) -> str:
        if self.folder_id:
            return self.folder_id

        headers = self._get_headers()
        with httpx.Client(timeout=10.0) as client:
            # Query if folder already exists
            query = f"name = '{self.folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            res = client.get(
                f"{GDRIVE_API_BASE}/files",
                headers=headers,
                params={"q": query, "fields": "files(id, name)"},
            )
            if res.status_code == 200:
                files = res.json().get("files", [])
                if files:
                    self.folder_id = files[0]["id"]
                    return self.folder_id

            # Create folder if not found
            create_res = client.post(
                f"{GDRIVE_API_BASE}/files",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "name": self.folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
            if create_res.status_code in (200, 201):
                self.folder_id = create_res.json()["id"]
                return self.folder_id

            raise AppError(500, "GDRIVE_FOLDER_ERROR", f"Failed to create Google Drive vault folder: {create_res.text}")

    def _find_chunk_file_id(self, chunk_id: str) -> str | None:
        if chunk_id in self._chunk_cache:
            return self._chunk_cache[chunk_id]

        folder_id = self._ensure_vault_folder()
        headers = self._get_headers()

        with httpx.Client(timeout=10.0) as client:
            query = f"name = '{chunk_id}' and '{folder_id}' in parents and trashed = false"
            res = client.get(
                f"{GDRIVE_API_BASE}/files",
                headers=headers,
                params={"q": query, "fields": "files(id, name)"},
            )
            if res.status_code == 200:
                files = res.json().get("files", [])
                if files:
                    file_id = files[0]["id"]
                    self._chunk_cache[chunk_id] = file_id
                    return file_id

        return None

    def put_chunk(self, chunk_id: str, data: bytes) -> None:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", "Google Drive is offline or unavailable")

        folder_id = self._ensure_vault_folder()
        headers = self._get_headers()

        existing_file_id = self._find_chunk_file_id(chunk_id)

        try:
            with httpx.Client(timeout=60.0) as client:
                if existing_file_id:
                    upload_res = client.patch(
                        f"{GDRIVE_UPLOAD_BASE}/files/{existing_file_id}?uploadType=media",
                        headers={**headers, "Content-Type": "application/octet-stream"},
                        content=data,
                    )
                else:
                    metadata = {
                        "name": chunk_id,
                        "parents": [folder_id],
                        "mimeType": "application/octet-stream",
                    }
                    boundary = "FrankensteinUploadBoundary"
                    body = (
                        f"--{boundary}\r\n"
                        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                        f"{json.dumps(metadata)}\r\n"
                        f"--{boundary}\r\n"
                        f"Content-Type: application/octet-stream\r\n\r\n"
                    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

                    upload_res = client.post(
                        f"{GDRIVE_UPLOAD_BASE}/files?uploadType=multipart",
                        headers={
                            **headers,
                            "Content-Type": f"multipart/related; boundary={boundary}",
                        },
                        content=body,
                    )

                if upload_res.status_code not in (200, 201):
                    raise AppError(500, "CHUNK_WRITE_FAILED", f"Google Drive failed to store chunk {chunk_id}: {upload_res.text}")

                uploaded_id = upload_res.json()["id"]
                self._chunk_cache[chunk_id] = uploaded_id
        except Exception as e:
            if isinstance(e, AppError):
                raise e
            raise AppError(500, "CHUNK_WRITE_FAILED", f"Network error writing chunk to Google Drive: {e}")

    def get_chunk(self, chunk_id: str) -> bytes:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", "Google Drive is offline or unavailable")

        file_id = self._find_chunk_file_id(chunk_id)
        if not file_id:
            raise AppError(404, "CHUNK_NOT_FOUND", f"Chunk {chunk_id} not found in Google Drive folder")

        headers = self._get_headers()
        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.get(
                    f"{GDRIVE_API_BASE}/files/{file_id}",
                    headers=headers,
                    params={"alt": "media"},
                )
                if res.status_code == 200:
                    return res.content
                elif res.status_code == 404:
                    self._chunk_cache.pop(chunk_id, None)
                    raise AppError(404, "CHUNK_NOT_FOUND", f"Chunk {chunk_id} not found on Google Drive")
                else:
                    raise AppError(500, "CHUNK_READ_FAILED", f"Google Drive read failed for chunk {chunk_id}: {res.text}")
        except Exception as e:
            if isinstance(e, AppError):
                raise e
            raise AppError(500, "CHUNK_READ_FAILED", f"Network error reading chunk from Google Drive: {e}")

    def delete_chunk(self, chunk_id: str) -> bool:
        if not self.check_availability():
            return False

        file_id = self._find_chunk_file_id(chunk_id)
        if not file_id:
            return False

        headers = self._get_headers()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.delete(
                    f"{GDRIVE_API_BASE}/files/{file_id}",
                    headers=headers,
                )
                self._chunk_cache.pop(chunk_id, None)
                return res.status_code in (200, 204)
        except Exception:
            return False

    def cleanup_temp_files(self) -> int:
        return 0
