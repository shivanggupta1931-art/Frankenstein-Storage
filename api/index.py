import os
import sys
from pathlib import Path

# Add project root to sys.path so 'backend' can be imported anywhere
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Set serverless environment variables if not already provided
if os.getenv("VERCEL") or not os.getenv("DATABASE_PATH"):
    os.environ.setdefault("DATABASE_PATH", "/tmp/frankenstein.db")

os.environ.setdefault("ALLOW_ALL_HOSTS", "true")
os.environ.setdefault("ALLOW_ALL_ORIGINS", "true")
os.environ.setdefault("AUTH_TOKEN", "frankenstein-demo-token")

from backend.app.db.migrations import run_migrations
from backend.app.main import app

# Ensure database schema is migrated
try:
    run_migrations()
except Exception as err:
    print(f"Warning: Migrations failed on serverless startup: {err}")
