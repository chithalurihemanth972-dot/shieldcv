"""A rescan must not read photos that were already quarantined."""
from __future__ import annotations

from pathlib import Path

from src.review.store import QUARANTINE_DIR
from src.tui.discovery import build_asset_index, discover
from src.utils.image_utils import list_images


def _make(root: Path) -> None:
    for sub in ("contributor_a/images", f"{QUARANTINE_DIR}/contributor_a/images"):
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / "x.jpg").write_bytes(b"x")


def test_list_images_skips_the_quarantine_folder(tmp_path: Path):
    _make(tmp_path)
    found = list_images(tmp_path)
    assert len(found) == 1 and QUARANTINE_DIR not in found[0].parts


def test_discovery_does_not_index_or_offer_the_quarantine(tmp_path: Path):
    _make(tmp_path)
    assert all(QUARANTINE_DIR not in p.parts
               for paths in build_asset_index(tmp_path).values() for p in paths)
    assert [c.path.name for c in discover("dataset", roots=[tmp_path])] == [tmp_path.name]
