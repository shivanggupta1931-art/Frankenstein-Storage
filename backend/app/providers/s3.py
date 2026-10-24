"""S3-Compatible Object Storage Provider (Cloudflare R2, AWS S3, Backblaze B2, MinIO).

Implements StorageProvider using AWS Signature Version 4 (AWS4-HMAC-SHA256) via standard Python
hashlib and httpx, with zero external AWS SDK dependencies.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any
import urllib.parse

import httpx

from backend.app.core.errors import AppError
from backend.app.providers.base import StorageProvider

HEX_UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def sign_s3_v4(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str = "auto",
    service: str = "s3",
) -> dict[str, str]:
    """Generates AWS Signature Version 4 (AWS4-HMAC-SHA256) Authorization header."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc
    path = parsed.path or "/"

    t = datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    payload_hash = hashlib.sha256(body).hexdigest()

    req_headers = {k.lower(): v for k, v in headers.items()}
    req_headers["host"] = host
    req_headers["x-amz-date"] = amz_date
    req_headers["x-amz-content-sha256"] = payload_hash

    signed_header_names = sorted(req_headers.keys())
    signed_headers_str = ";".join(signed_header_names)
    canonical_headers = "".join(f"{k}:{req_headers[k].strip()}\n" for k in signed_header_names)

    query = parsed.query or ""
    canonical_request = (
        f"{method.upper()}\n"
        f"{path}\n"
        f"{query}\n"
        f"{canonical_headers}\n"
        f"{signed_headers_str}\n"
        f"{payload_hash}"
    )
    canonical_request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()

    effective_region = region if region and region.strip() else "auto"
    credential_scope = f"{date_stamp}/{effective_region}/{service}/aws4_request"
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{canonical_request_hash}"

    k_date = hmac.new(b"AWS4" + secret_key.encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    k_region = hmac.new(k_date, effective_region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers_str}, "
        f"Signature={signature}"
    )
    req_headers["authorization"] = authorization
    return req_headers


class S3StorageProvider(StorageProvider):
    """Stores encrypted chunks on S3-compatible cloud storage (Cloudflare R2, AWS S3, MinIO, Backblaze B2)."""

    def __init__(
        self,
        config: dict[str, Any] | str | None = None,
        simulated_offline: bool = False,
    ):
        if isinstance(config, str):
            try:
                self.config = json.loads(config)
            except Exception:
                self.config = {}
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = {}

        self.simulated_offline = bool(simulated_offline)
        self.endpoint_url: str = str(self.config.get("endpoint_url", "")).rstrip("/")
        self.bucket: str = str(self.config.get("bucket", "frankenstein-vault")).strip()
        self.access_key_id: str = str(self.config.get("access_key_id", "")).strip()
        self.secret_access_key: str = str(self.config.get("secret_access_key", "")).strip()
        self.region: str = str(self.config.get("region", "auto")).strip() or "auto"
        self.prefix: str = str(self.config.get("prefix", "chunks/")).strip("/")
        if self.prefix:
            self.prefix = f"{self.prefix}/"

        # Determine cloud provider variant for human-friendly reporting
        ep_lower = self.endpoint_url.lower()
        if "r2.cloudflarestorage.com" in ep_lower:
            self.provider_variant = "Cloudflare R2"
        elif "amazonaws.com" in ep_lower:
            self.provider_variant = "AWS S3"
        elif "backblazeb2.com" in ep_lower:
            self.provider_variant = "Backblaze B2"
        elif "localhost" in ep_lower or "127.0.0.1" in ep_lower or "minio" in ep_lower:
            self.provider_variant = "MinIO Object Storage"
        else:
            self.provider_variant = "S3-Compatible Object Storage"

        # Check if running in mock/demo mode (for unit tests or without real cloud credentials)
        is_mock_key = (
            not self.access_key_id
            or not self.secret_access_key
            or self.access_key_id.startswith("mock_")
            or self.access_key_id.startswith("demo_")
            or "test" in self.access_key_id.lower()
        )
        self.is_mock = is_mock_key or not self.endpoint_url

        # Mock fallback local folder
        home = Path(os.path.expanduser("~"))
        self.mock_dir = home / ".frankenstein_s3_mock" / self.bucket / self.prefix
        if self.is_mock:
            self.mock_dir.mkdir(parents=True, exist_ok=True)

        self._chunk_sizes: dict[str, int] = {}
        if self.is_mock and self.mock_dir.exists():
            for f in self.mock_dir.glob("*"):
                if f.is_file() and not f.name.startswith("."):
                    self._chunk_sizes[f.name] = f.stat().st_size

    def _get_object_url(self, chunk_id: str) -> str:
        key = f"{self.prefix}{chunk_id}"
        # If endpoint already has bucket in URL or path-style:
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"

    def check_availability(self) -> bool:
        if self.simulated_offline:
            return False
        if self.is_mock:
            return True

        # Perform HEAD probe on S3 bucket
        probe_url = f"{self.endpoint_url}/{self.bucket}"
        try:
            signed_headers = sign_s3_v4(
                method="HEAD",
                url=probe_url,
                headers={},
                body=b"",
                access_key=self.access_key_id,
                secret_key=self.secret_access_key,
                region=self.region,
            )
            with httpx.Client(timeout=4.0) as client:
                res = client.head(probe_url, headers=signed_headers)
                return res.status_code in (200, 403, 404)
        except Exception:
            return False

    def put_chunk(self, chunk_id: str, data: bytes) -> None:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", f"{self.provider_variant} is offline or unavailable")

        if not HEX_UUID_PATTERN.match(chunk_id):
            raise AppError(400, "INVALID_CHUNK_ID", f"Invalid chunk_id format: {chunk_id}")

        if self.is_mock:
            self.mock_dir.mkdir(parents=True, exist_ok=True)
            chunk_file = self.mock_dir / chunk_id
            chunk_file.write_bytes(data)
            self._chunk_sizes[chunk_id] = len(data)
            return

        obj_url = self._get_object_url(chunk_id)
        signed_headers = sign_s3_v4(
            method="PUT",
            url=obj_url,
            headers={"content-type": "application/octet-stream"},
            body=data,
            access_key=self.access_key_id,
            secret_key=self.secret_access_key,
            region=self.region,
        )

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.put(obj_url, headers=signed_headers, content=data)
                if res.status_code not in (200, 201):
                    raise AppError(500, "S3_UPLOAD_FAILED", f"S3 PUT chunk failed with status {res.status_code}: {res.text[:200]}")
                self._chunk_sizes[chunk_id] = len(data)
        except AppError:
            raise
        except Exception as e:
            raise AppError(500, "S3_WRITE_FAILED", f"Failed to upload chunk to {self.provider_variant}: {e}")

    def get_chunk(self, chunk_id: str) -> bytes:
        if not self.check_availability():
            raise AppError(503, "DRIVE_UNAVAILABLE", f"{self.provider_variant} is offline or unavailable")

        if not HEX_UUID_PATTERN.match(chunk_id):
            raise AppError(400, "INVALID_CHUNK_ID", f"Invalid chunk_id format: {chunk_id}")

        if self.is_mock:
            chunk_file = self.mock_dir / chunk_id
            if not chunk_file.exists():
                raise AppError(404, "CHUNK_NOT_FOUND", f"Chunk {chunk_id} not found in {self.provider_variant}")
            return chunk_file.read_bytes()

        obj_url = self._get_object_url(chunk_id)
        signed_headers = sign_s3_v4(
            method="GET",
            url=obj_url,
            headers={},
            body=b"",
            access_key=self.access_key_id,
            secret_key=self.secret_access_key,
            region=self.region,
        )

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(obj_url, headers=signed_headers)
                if res.status_code == 404:
                    raise AppError(404, "CHUNK_NOT_FOUND", f"Chunk {chunk_id} not found in {self.provider_variant}")
                if res.status_code != 200:
                    raise AppError(500, "S3_DOWNLOAD_FAILED", f"S3 GET chunk failed with status {res.status_code}")
                return res.content
        except AppError:
            raise
        except Exception as e:
            raise AppError(500, "S3_READ_FAILED", f"Failed to read chunk from {self.provider_variant}: {e}")

    def delete_chunk(self, chunk_id: str) -> bool:
        if not self.check_availability():
            return False

        if not HEX_UUID_PATTERN.match(chunk_id):
            return False

        if self.is_mock:
            chunk_file = self.mock_dir / chunk_id
            if chunk_file.exists():
                try:
                    chunk_file.unlink()
                    self._chunk_sizes.pop(chunk_id, None)
                    return True
                except OSError:
                    return False
            return False

        obj_url = self._get_object_url(chunk_id)
        signed_headers = sign_s3_v4(
            method="DELETE",
            url=obj_url,
            headers={},
            body=b"",
            access_key=self.access_key_id,
            secret_key=self.secret_access_key,
            region=self.region,
        )

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.delete(obj_url, headers=signed_headers)
                if res.status_code in (200, 204):
                    self._chunk_sizes.pop(chunk_id, None)
                    return True
                return False
        except Exception:
            return False

    def get_usage(self) -> dict[str, Any]:
        """Returns storage metrics for the S3 bucket."""
        # Standard cloud tier baseline: 10 GiB free tier (R2 has 10 GiB free storage)
        quota_total = 10 * (1024 ** 3)
        used_bytes = sum(self._chunk_sizes.values())
        free_bytes = max(0, quota_total - used_bytes)

        dev_info = self.get_device_info()
        return {
            "total": quota_total,
            "used": used_bytes,
            "free": free_bytes,
            "source": f"{self.provider_variant} ({self.bucket})",
            "available": self.check_availability(),
            "device_id": dev_info.get("device_id"),
            "st_dev": dev_info.get("st_dev"),
            "volume_name": dev_info.get("volume_name"),
            "is_cloud_synced": True,
            "is_external": False,
            "is_removable": False,
        }

    def get_device_info(self) -> dict[str, Any]:
        host = urllib.parse.urlsplit(self.endpoint_url).netloc or "s3.amazonaws.com"
        clean_host = host.replace(":", "_").replace(".", "_")
        dev_id = f"s3_{clean_host}_{self.bucket}"
        return {
            "device_id": dev_id,
            "st_dev": f"s3_{self.bucket}",
            "mount_point": f"s3://{self.bucket}/{self.prefix}",
            "volume_name": f"{self.provider_variant}: {self.bucket}",
            "is_cloud_synced": True,
            "is_external": False,
            "is_removable": False,
        }
