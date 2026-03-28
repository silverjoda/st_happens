"""Reset ingestion artifacts to a clean baseline with snapshot backups."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.common.settings import PROJECT_ROOT, get_database_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot and reset local ingestion DB + processed artifacts"
    )
    parser.add_argument(
        "--archive-root",
        default="data/reset_snapshots",
        help="Directory where reset snapshots are written",
    )
    parser.add_argument(
        "--processed-dir",
        default="data/processed",
        help="Processed artifacts directory to reset",
    )
    parser.add_argument(
        "--skip-snapshot",
        action="store_true",
        help="Reset without copying current DB/processed artifacts",
    )
    return parser.parse_args()


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _database_file_from_url(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise SystemExit("unsupported_database_url_for_reset")
    raw_path = url.removeprefix("sqlite:///")
    return Path(raw_path)


def _copy_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def main() -> None:
    args = parse_args()
    archive_root = _resolve_path(args.archive_root)
    processed_dir = _resolve_path(args.processed_dir)
    db_path = _database_file_from_url(get_database_url())

    snapshot_dir: Path | None = None
    if not args.skip_snapshot:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_dir = archive_root / f"reset_{timestamp}"
        snapshot_dir.mkdir(parents=True, exist_ok=False)
        _copy_if_exists(db_path, snapshot_dir / "db" / db_path.name)
        _copy_if_exists(processed_dir, snapshot_dir / "processed")

    if db_path.exists():
        db_path.unlink()

    if processed_dir.exists():
        shutil.rmtree(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    print(f"database_reset={db_path}")
    print(f"processed_dir_reset={processed_dir}")
    print(f"snapshot_dir={snapshot_dir if snapshot_dir is not None else 'none'}")


if __name__ == "__main__":
    main()
