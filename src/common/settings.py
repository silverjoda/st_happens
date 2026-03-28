"""Application settings and path helpers."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_database_url() -> str:
    """Return the configured SQLite database URL."""
    configured = os.getenv("SHIP_HAPPENS_DB_URL")
    if configured:
        return configured
    default_db_path = PROJECT_ROOT / "data" / "ship_happens.db"
    return f"sqlite:///{default_db_path}"


def ensure_runtime_directories() -> None:
    """Create runtime directories required by the project."""
    (PROJECT_ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
