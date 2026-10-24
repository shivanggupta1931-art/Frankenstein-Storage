"""Test configuration and fixtures for Frankenstein Storage."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.crypto.key_manager import key_manager
from backend.app.db.connection import create_connection
from backend.app.db.migrations import run_migrations
from backend.app.main import app
from backend.app.services.drive_service import add_drive

TEST_PASSWORD = "test-master-password-12345"


@pytest.fixture
def test_env(tmp_path: Path):
    """Sets up an isolated test environment with temporary database and 3 drives."""
    db_file = tmp_path / "test_frankenstein.db"
    settings.database_path = db_file
    
    # Configure 64KB chunk size for faster tests (or default 1MB)
    orig_chunk_size = settings.chunk_size_bytes
    settings.chunk_size_bytes = 64 * 1024  # 64 KB chunks for snappy test execution

    orig_reserve_bytes = settings.min_reserve_bytes
    orig_reserve_ratio = settings.min_reserve_ratio
    settings.min_reserve_bytes = 1024 * 1024  # 1 MB in tests
    settings.min_reserve_ratio = 0.0001

    # Run migrations
    run_migrations(db_path=db_file)

    # Initialize 3 test drives
    drives_dir = tmp_path / "drives"
    d1 = drives_dir / "drive1"
    d2 = drives_dir / "drive2"
    d3 = drives_dir / "drive3"
    d1.mkdir(parents=True)
    d2.mkdir(parents=True)
    d3.mkdir(parents=True)

    conn = create_connection(db_file)
    try:
        # Unlock vault
        key_manager.lock()
        key_manager.initialize_or_unlock(TEST_PASSWORD, conn)

        # Register drives
        drive1 = add_drive(conn, str(d1), "Test Drive 1")
        drive2 = add_drive(conn, str(d2), "Test Drive 2")
        drive3 = add_drive(conn, str(d3), "Test Drive 3")
        conn.commit()

        yield {
            "tmp_path": tmp_path,
            "db_file": db_file,
            "conn": conn,
            "drive_paths": [d1, d2, d3],
            "drives": [drive1, drive2, drive3],
            "password": TEST_PASSWORD,
        }
    finally:
        key_manager.lock()
        settings.chunk_size_bytes = orig_chunk_size
        settings.min_reserve_bytes = orig_reserve_bytes
        settings.min_reserve_ratio = orig_reserve_ratio
        conn.close()


@pytest.fixture
async def async_client(test_env):
    """Async HTTP client targeting FastAPI with valid authorization and loopback headers."""
    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {settings.session_token}",
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:5173",
    }
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8765", headers=headers) as client:
        yield client
