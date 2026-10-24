"""Configuration settings for Frankenstein Storage backend."""

import os
import secrets
from pathlib import Path

# Pure python configuration without unnecessary external dependencies


class Settings:
    def __init__(self):
        # Auto-load .env if present
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8765"))
        
        db_path_env = os.getenv("DATABASE_PATH", "frankenstein.db")
        self.database_path: Path = Path(db_path_env).resolve()
        
        self.chunk_size_bytes: int = int(os.getenv("CHUNK_SIZE_BYTES", str(1024 * 1024)))
        self.min_drives: int = int(os.getenv("MIN_DRIVES", "3"))
        self.smart_upload_threshold_bytes: int = int(os.getenv("SMART_UPLOAD_THRESHOLD_BYTES", str(1024 * 1024)))
        
        # Drive safety reserve constraints (default: keep at least 2 GiB or 5% free, whichever is larger)
        self.min_reserve_bytes: int = int(os.getenv("MIN_RESERVE_BYTES", str(2 * 1024 * 1024 * 1024)))
        self.min_reserve_ratio: float = float(os.getenv("MIN_RESERVE_RATIO", "0.05"))

        # Security constraints
        self.allowed_hosts = {
            "127.0.0.1",
            "localhost",
            f"127.0.0.1:{self.port}",
            f"localhost:{self.port}",
        }
        self.allowed_origins = {
            os.getenv("VITE_DEV_ORIGIN", "http://127.0.0.1:5173"),
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:5175",
            "http://localhost:5175",
            f"http://127.0.0.1:{self.port}",
            f"http://localhost:{self.port}",
        }
        
        # Session token
        token_env = os.getenv("AUTH_TOKEN")
        if token_env and token_env.strip():
            self.session_token: str = token_env.strip()
            self.is_ephemeral_token: bool = False
        else:
            self.session_token: str = secrets.token_urlsafe(32)
            self.is_ephemeral_token: bool = True

    def calculate_reserve(self, total_bytes: int) -> int:
        if total_bytes <= 0:
            return 0
        ratio_bytes = int(total_bytes * self.min_reserve_ratio)
        raw_reserve = max(self.min_reserve_bytes, ratio_bytes)
        # Cap at 50% for very small test/virtual drives
        return min(raw_reserve, int(total_bytes * 0.5))


settings = Settings()


def calculate_reserve(total_bytes: int) -> int:
    return settings.calculate_reserve(total_bytes)
