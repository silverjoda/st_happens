from __future__ import annotations

from pathlib import Path

import pytest

from src.common.settings import display_card_path_for_source
from src.ingest.run_extract import _rename_images_with_score_prefixes, _resolve_worker_count


def test_rename_images_with_score_prefixes_uses_sorted_order(tmp_path: Path) -> None:
    photo_a = tmp_path / "a.jpg"
    photo_b = tmp_path / "b.png"
    photo_a.write_bytes(b"a")
    photo_b.write_bytes(b"b")

    renamed = _rename_images_with_score_prefixes([photo_a, photo_b])

    assert [path.name for path in renamed] == ["100_raw.jpg", "99.5_raw.png"]
    assert renamed[0].exists()
    assert renamed[1].exists()


def test_display_card_path_keeps_score_prefix_when_available(tmp_path: Path) -> None:
    source_path = tmp_path / "99.5_raw.jpg"
    display_path = display_card_path_for_source(source_path)

    assert display_path.name == "99.5_processed.jpg"


def test_resolve_worker_count_auto_and_validation() -> None:
    assert _resolve_worker_count(0) >= 1
    assert _resolve_worker_count(3) == 3
    with pytest.raises(SystemExit):
        _resolve_worker_count(-1)
