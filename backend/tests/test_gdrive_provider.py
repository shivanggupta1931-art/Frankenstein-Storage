"""Tests for GoogleDriveProvider and Hybrid Cloud-Local storage pooling with XOR parity."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.providers.gdrive import GoogleDriveProvider
from backend.app.services import drive_service, storage_engine


@pytest.fixture
def mock_gdrive_http():
    """Mocks Google Drive REST API HTTP client calls."""
    storage_chunks: dict[str, bytes] = {}

    def mock_send(request, **kw):
        import urllib.parse

        url = urllib.parse.unquote(str(request.url))
        method = request.method

        if "about" in url:
            return Response(
                200,
                json={
                    "storageQuota": {
                        "limit": "107374182400",
                        "usage": "1073741824",
                        "usageInDrive": "536870912",
                    },
                    "user": {"emailAddress": "testuser@iitr.ac.in"},
                },
            )

        if "upload/drive/v3/files" in url:
            content = request.content
            # Extract boundary
            lines = content.split(b"\r\n")
            meta_json = {}
            for i, line in enumerate(lines):
                if line.startswith(b"{") and line.endswith(b"}"):
                    import json

                    meta_json = json.loads(line.decode())
                    break

            chunk_id = meta_json.get("name", "chunk1")
            # Raw data is between headers and closing boundary
            data_start = (
                content.find(b"\r\n\r\n", content.find(b"Content-Type: application/octet-stream"))
                + 4
            )
            data_end = content.rfind(b"\r\n--FrankensteinUploadBoundary--")
            chunk_data = content[data_start:data_end]
            storage_chunks[chunk_id] = chunk_data
            return Response(200, json={"id": f"file-{chunk_id}", "name": chunk_id})

        is_media = "alt=media" in url or (
            hasattr(request, "params") and getattr(request, "params", {}).get("alt") == "media"
        )
        if "drive/v3/files" in url and method == "GET":
            if is_media:
                file_id = url.split("/files/")[1].split("?")[0]
                chunk_id = file_id.replace("file-", "")
                if chunk_id in storage_chunks:
                    return Response(200, content=storage_chunks[chunk_id])
                return Response(404, json={"error": "Not Found"})

            if "q=" in url:
                # Query file or folder
                if "mimeType = 'application/vnd.google-apps.folder'" in url:
                    return Response(
                        200,
                        json={"files": [{"id": "vault-folder-123", "name": "FrankensteinVault"}]},
                    )
                # Search chunk
                for cid in storage_chunks:
                    if f"name = '{cid}'" in url:
                        return Response(200, json={"files": [{"id": f"file-{cid}", "name": cid}]})
                return Response(200, json={"files": []})

        if "drive/v3/files" in url and method == "POST":
            return Response(201, json={"id": "vault-folder-123", "name": "FrankensteinVault"})

        if "drive/v3/files" in url and method == "DELETE":
            file_id = url.split("/files/")[1]
            chunk_id = file_id.replace("file-", "")
            storage_chunks.pop(chunk_id, None)
            return Response(204)

        return Response(200, json={"files": []})

    with patch("httpx.Client") as mock_client:
        instance = MagicMock()
        instance.__enter__.return_value = instance
        instance.__exit__.return_value = False

        instance.get.side_effect = lambda url, **kw: mock_send(
            MagicMock(method="GET", url=url, **kw)
        )
        instance.post.side_effect = lambda url, **kw: mock_send(
            MagicMock(method="POST", url=url, **kw)
        )
        instance.patch.side_effect = lambda url, **kw: mock_send(
            MagicMock(method="PATCH", url=url, **kw)
        )
        instance.delete.side_effect = lambda url, **kw: mock_send(
            MagicMock(method="DELETE", url=url, **kw)
        )
        mock_client.return_value = instance
        yield mock_client


def test_gdrive_provider_basic_crud_and_usage(mock_gdrive_http):
    provider = GoogleDriveProvider(
        config={"access_token": "ya29.real-test-token", "folder_name": "IITR_Vault"},
        simulated_offline=False,
    )

    assert provider.check_availability() is True
    usage = provider.get_usage()
    assert usage["available"] is True
    assert usage["total"] == 107374182400
    assert "testuser@iitr.ac.in" in usage["source"]

    chunk_id = "0123456789abcdef0123456789abcdef"
    payload = b"encrypted-gdrive-chunk-data"

    provider.put_chunk(chunk_id, payload)
    retrieved = provider.get_chunk(chunk_id)
    assert retrieved == payload

    assert provider.delete_chunk(chunk_id) is True


def test_hybrid_pool_gdrive_and_local_drives_upload_and_parity_rebuild(test_env, mock_gdrive_http):
    conn = test_env["conn"]

    # Add Google Drive (IITR Google Drive)
    d_gdrive = drive_service.add_drive(
        conn,
        path_str="gdrive://IITR_Google_Drive",
        display_name="IITR Google Drive",
        provider_type="gdrive",
        config={"access_token": "ya29.real-test-token", "folder_name": "IITR_Storage_Vault"},
    )

    assert d_gdrive["provider_type"] == "gdrive"

    # List drives and verify all 4 are available
    drives = drive_service.list_drives(conn)
    assert len(drives) >= 3
    assert any(d["provider_type"] == "gdrive" for d in drives)

    # Upload file across hybrid pool (2 data chunks + 1 parity per stripe)
    sample_data = b"IITR Hybrid Cloud Storage Demonstration with Rotating XOR Parity! " * 2000

    async def stream_gen():
        chunk_size = 16 * 1024
        for i in range(0, len(sample_data), chunk_size):
            yield sample_data[i : i + chunk_size]

    import asyncio

    upload_res = asyncio.run(
        storage_engine.upload_stream(
            conn=conn,
            stream=stream_gen(),
            filename="hybrid_demo.txt",
            mode="chunked_parity",
        )
    )

    assert upload_res["status"] == "complete"
    assert upload_res["size"] == len(sample_data)

    # Test downloading with all drives online
    meta, gen, tracker = storage_engine.download_stream(conn, upload_res["id"])
    downloaded_data = b"".join(list(gen))
    assert downloaded_data == sample_data

    # Simulate Google Drive OFFLINE
    drive_service.patch_drive(conn, d_gdrive["id"], simulated_offline=True)

    # Download file again: any chunks on Google Drive are reconstructed on-the-fly via XOR parity!
    meta2, gen2, tracker2 = storage_engine.download_stream(conn, upload_res["id"])
    rebuilt_data = b"".join(list(gen2))
    assert rebuilt_data == sample_data


@pytest.mark.asyncio
async def test_add_gdrive_via_http_api(test_env, mock_gdrive_http):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {settings.session_token}"}

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        res = await client.post(
            "/api/v1/drives",
            headers=headers,
            json={
                "display_name": "IITR Cloud Vault",
                "provider_type": "gdrive",
                "config": {"access_token": "ya29.test-access-token"},
            },
        )
        assert res.status_code == 200
        drive_data = res.json()
        assert drive_data["display_name"] == "IITR Cloud Vault"
        assert drive_data["provider_type"] == "gdrive"


def test_gdrive_provider_resolves_local_folder_by_id_and_migrates_chunks(tmp_path):
    local_cs = tmp_path / "CloudStorage" / "GoogleDrive-user@gmail.com" / "My Drive"
    local_cs.mkdir(parents=True)
    real_target_folder = local_cs / "real_synced_folder_123"
    real_target_folder.mkdir()

    old_custom_folder = local_cs / "CustomFolderName"
    old_custom_folder.mkdir()
    (old_custom_folder / "testchunk1").write_bytes(b"chunk-data-1")

    with patch.object(GoogleDriveProvider, "_detect_local_gdrive_desktop", return_value=local_cs):
        with patch.object(
            GoogleDriveProvider, "_find_folder_by_gdrive_id", return_value=real_target_folder
        ):
            provider = GoogleDriveProvider(
                config={
                    "folder_id": "target_folder_id_xyz",
                    "folder_name": "CustomFolderName",
                    "auth_type": "demo_mock",
                }
            )
            assert provider.mock_dir == real_target_folder
            assert (real_target_folder / "testchunk1").exists()
            assert (real_target_folder / "testchunk1").read_bytes() == b"chunk-data-1"
            assert not (old_custom_folder / "testchunk1").exists()
