"""Database migrations runner using numbered SQL files."""

import re
from pathlib import Path

from backend.app.db.connection import get_db

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def get_available_migrations(migrations_dir: Path | None = None) -> list[tuple[int, Path]]:
    target_dir = migrations_dir or MIGRATIONS_DIR
    if not target_dir.exists():
        return []

    migrations: list[tuple[int, Path]] = []
    pattern = re.compile(r"^(\d+)_.*\.sql$")
    for file in sorted(target_dir.glob("*.sql")):
        match = pattern.match(file.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, file))

    return sorted(migrations, key=lambda x: x[0])


def run_migrations(db_path: Path | None = None, migrations_dir: Path | None = None) -> int:
    applied_count = 0
    with get_db(db_path) as conn:
        # Ensure schema_version table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor = conn.execute("SELECT version FROM schema_version")
        applied_versions = {row["version"] for row in cursor.fetchall()}

        available = get_available_migrations(migrations_dir)
        for version, path in available:
            if version not in applied_versions:
                sql_content = path.read_text(encoding="utf-8")
                conn.executescript(sql_content)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                applied_count += 1

    return applied_count
