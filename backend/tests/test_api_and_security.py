"""Test 6 and API integration tests: security, token auth, host/origin checks, path traversal, symlink escape."""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.main import app
from backend.app.providers.local import LocalFolderProvider


def test_path_traversal_and_symlink_escape_rejected(tmp_path: Path):
    """Test 6 (part 1): Path traversal and symlink escape rejected."""
    drive_root = tmp_path / "test_drive"
    drive_root.mkdir()
    provider = LocalFolderProvider(drive_root)

    # 1. Invalid chunk ID with traversal characters
    with pytest.raises(AppError) as exc:
        provider.put_chunk("../../../etc/passwd", b"bad_data")
    assert exc.value.status_code == 400

    with pytest.raises(AppError) as exc:
        provider.get_chunk("../../../evil")
    assert exc.value.status_code == 400

    # 2. Symlink escape check
    outside_file = tmp_path / "outside_target.txt"
    outside_file.write_text("secret outside data")

    # Attempt to put symlink inside chunks directory pointing outside
    fake_chunk_id = "0123456789abcdef0123456789abcdef"
    chunk_dir = drive_root / ".frankenstein" / "chunks" / "01" / "23"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    symlink_target = chunk_dir / fake_chunk_id

    try:
        os.symlink(outside_file, symlink_target)
        # Getting the chunk should reject symlink escape
        with pytest.raises(AppError) as exc:
            provider.get_chunk(fake_chunk_id)
        assert exc.value.status_code == 400
        assert exc.value.code == "SECURITY_ERROR"
    except OSError:
        # Some systems or non-admin Windows restrict symlinks
        pass


@pytest.mark.asyncio
async def test_auth_token_enforcement(test_env):
    """Test 6 (part 2): Missing or wrong Bearer token returns 401."""
    transport = ASGITransport(app=app)

    # Missing token
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        res = await client.get("/api/v1/overview")
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "UNAUTHORIZED"

    # Invalid token
    bad_headers = {"Authorization": "Bearer totally-fake-token-999"}
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765", headers=bad_headers) as client:
        res = await client.get("/api/v1/overview")
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == "UNAUTHORIZED"

    # Health endpoint does not require auth
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_host_and_origin_validation(test_env):
    """Test 6 (part 3): Bad Host or Origin returns 403."""
    transport = ASGITransport(app=app)
    valid_token_header = {"Authorization": f"Bearer {settings.session_token}"}

    # Bad Host header
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8765",
        headers={**valid_token_header, "Host": "attacker.evil.com"},
    ) as client:
        res = await client.get("/api/v1/overview")
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    # Bad Origin header
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8765",
        headers={**valid_token_header, "Host": "127.0.0.1:8765", "Origin": "http://evil-site.com"},
    ) as client:
        res = await client.get("/api/v1/overview")
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    # Dynamic loopback origin on fallback port 5174 (e.g. Vite fallback port)
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8765",
        headers={**valid_token_header, "Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:5174"},
    ) as client:
        res = await client.get("/api/v1/overview")
        assert res.status_code == 200
        assert res.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5174"

    # Preflight OPTIONS for port 5174
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8765",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:5174"},
    ) as client:
        res = await client.options("/api/v1/overview")
        assert res.status_code == 204
        assert res.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5174"


@pytest.mark.asyncio
async def test_api_upload_download_http_flow(async_client):
    """Integration test: upload file via HTTP raw stream and download via HTTP."""
    test_data = b"Streaming HTTP file test payload! " * 500

    # Upload
    upload_res = await async_client.post(
        "/api/v1/files/upload?name=http_test.txt&overwrite=true",
        content=test_data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert upload_res.status_code == 200
    file_info = upload_res.json()
    assert file_info["status"] == "complete"
    assert file_info["size"] == len(test_data)
    file_id = file_info["id"]

    # Overview check
    overview_res = await async_client.get("/api/v1/overview")
    assert overview_res.status_code == 200
    assert overview_res.json()["files_count"] >= 1

    # Chunk map check: small files (< 1 MiB) are mirrored across 2 distinct drives
    chunks_res = await async_client.get(f"/api/v1/files/{file_id}/chunks")
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()
    assert len(chunks) >= 2
    assert chunks[0]["drive_id"] != chunks[1]["drive_id"]

    # Download
    download_res = await async_client.get(f"/api/v1/files/{file_id}/download")
    assert download_res.status_code == 200
    assert download_res.content == test_data

    # Activity log
    activity_res = await async_client.get("/api/v1/activity")
    assert activity_res.status_code == 200
    assert len(activity_res.json()) > 0

    # Preview endpoint check
    preview_res = await async_client.get(f"/api/v1/files/{file_id}/preview")
    assert preview_res.status_code == 200
    assert preview_res.content == test_data
    assert "inline;" in preview_res.headers.get("content-disposition", "")
    assert "http_test.txt" in preview_res.headers.get("content-disposition", "")
    assert preview_res.headers.get("content-type", "").startswith("text/plain")


@pytest.mark.asyncio
async def test_file_preview_token_query_param(async_client):
    """Test that file preview authenticates via ?token= query parameter."""
    test_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    upload_res = await async_client.post(
        "/api/v1/files/upload?name=sample_chart.png&overwrite=true",
        content=test_img,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert upload_res.status_code == 200
    file_id = upload_res.json()["id"]

    # Request without Authorization header but with ?token= query parameter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Without token -> 401
        res_no_auth = await client.get(f"/api/v1/files/{file_id}/preview")
        assert res_no_auth.status_code == 401

        # With query param token -> 200 OK and image/png
        res_token = await client.get(f"/api/v1/files/{file_id}/preview?token={settings.session_token}")
        assert res_token.status_code == 200
        assert res_token.content == test_img
        assert res_token.headers.get("content-type") == "image/png"
        assert "inline;" in res_token.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_get_files_sorting_options(async_client):
    """Test that GET /api/v1/files correctly sorts by size, date, and name."""
    # Upload 2 files with distinct sizes and names
    await async_client.post(
        "/api/v1/files/upload?name=alpha_small.txt&overwrite=true",
        content=b"small",
        headers={"Content-Type": "application/octet-stream"},
    )
    await async_client.post(
        "/api/v1/files/upload?name=beta_large.txt&overwrite=true",
        content=b"large" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )

    # Sort by size desc (largest first)
    res_size_desc = await async_client.get("/api/v1/files?sort_by=size&order=desc")
    assert res_size_desc.status_code == 200
    files_size_desc = res_size_desc.json()
    sizes = [f["size"] for f in files_size_desc]
    assert sizes == sorted(sizes, reverse=True)

    # Sort by size asc (smallest first)
    res_size_asc = await async_client.get("/api/v1/files?sort_by=size&order=asc")
    assert res_size_asc.status_code == 200
    files_size_asc = res_size_asc.json()
    sizes_asc = [f["size"] for f in files_size_asc]
    assert sizes_asc == sorted(sizes_asc)

    # Sort by name asc
    res_name_asc = await async_client.get("/api/v1/files?sort_by=name&order=asc")
    assert res_name_asc.status_code == 200
    files_name_asc = res_name_asc.json()
    names = [f["name"] for f in files_name_asc]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_locked_vault_blocks_all_operations(test_env, async_client):
    """When vault is locked, all operations are rejected with 403 VAULT_LOCKED and overview is sanitized."""
    from backend.app.crypto.key_manager import key_manager

    # 1. Lock vault
    key_manager.lock()
    assert not key_manager.is_unlocked()

    # Health returns unlocked=False
    res_health = await async_client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["unlocked"] is False

    # Overview returns sanitized locked response
    res_ov = await async_client.get("/api/v1/overview")
    assert res_ov.status_code == 200
    ov_data = res_ov.json()
    assert ov_data["vault_unlocked"] is False
    assert ov_data["pool_health"] == "locked"
    assert ov_data["total_bytes"] == 0

    # Drives listing blocked
    res_drives = await async_client.get("/api/v1/drives")
    assert res_drives.status_code == 403
    assert res_drives.json()["error"]["code"] == "VAULT_LOCKED"

    # Files listing blocked
    res_files = await async_client.get("/api/v1/files")
    assert res_files.status_code == 403
    assert res_files.json()["error"]["code"] == "VAULT_LOCKED"

    # Drive creation blocked
    res_add = await async_client.post("/api/v1/drives", json={"display_name": "HackDrive"})
    assert res_add.status_code == 403
    assert res_add.json()["error"]["code"] == "VAULT_LOCKED"

    # Heal blocked
    res_heal = await async_client.post("/api/v1/heal")
    assert res_heal.status_code == 403
    assert res_heal.json()["error"]["code"] == "VAULT_LOCKED"

    # Activity blocked
    res_act = await async_client.get("/api/v1/activity")
    assert res_act.status_code == 403
    assert res_act.json()["error"]["code"] == "VAULT_LOCKED"

    # 2. Unlock vault with password restores full access
    res_unlock = await async_client.post("/api/v1/unlock", json={"password": test_env["password"]})
    assert res_unlock.status_code == 200
    assert key_manager.is_unlocked()

    res_files_after = await async_client.get("/api/v1/files")
    assert res_files_after.status_code == 200


