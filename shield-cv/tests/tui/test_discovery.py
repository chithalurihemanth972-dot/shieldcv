"""Discovery lists sensible targets and stays bounded."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.tui.discovery import (build_asset_index, classify, discover, resolve_asset,
                                resolve_assets)


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    _touch(tmp_path / "ds_contrib" / "contributor_a" / "images" / "a1.jpg")
    _touch(tmp_path / "ds_contrib" / "contributor_b" / "images" / "b1.png")
    _touch(tmp_path / "ds_classes" / "cat" / "1.jpg")
    _touch(tmp_path / "nested" / "deeper" / "classes_root" / "tank" / "x.jpg")
    _touch(tmp_path / "models" / "m.pt", b"0" * 2048)
    _touch(tmp_path / "models" / "notes.txt")
    _touch(tmp_path / "rec" / "chain.json",
           json.dumps([{"record_hash": "a"}, {"record_hash": "b"}, {"record_hash": "c"}]).encode())
    _touch(tmp_path / "rec" / "stream.jsonl",
           b'{"record_hash": "a"}\n{"record_hash": "b"}\n')
    _touch(tmp_path / "rec" / "report.json", json.dumps({"module": "data_scanner"}).encode())
    _touch(tmp_path / "rec" / "bad.json", b"{not json")
    _touch(tmp_path / ".git" / "hidden.pt")
    _touch(tmp_path / "__pycache__" / "cached.pt")
    (tmp_path / "empty").mkdir()
    return tmp_path


def test_datasets_list_roots_not_subfolders(tree: Path):
    names = {c.path.name for c in discover("dataset", roots=[tree])}
    assert names == {"ds_contrib", "ds_classes", "classes_root"}


def test_search_root_is_not_a_dataset_just_because_children_hold_images(tmp_path: Path):
    _touch(tmp_path / "proj" / "sheets" / "a.jpg")
    _touch(tmp_path / "proj" / "lab" / "b.jpg")
    names = {c.path.name for c in discover("dataset", roots=[tmp_path / "proj"])}
    assert names == {"sheets", "lab"}


def test_search_root_with_dataset_markers_is_listed(tmp_path: Path):
    _touch(tmp_path / "ds" / "contributor_a" / "images" / "a.jpg")
    assert [c.path.name for c in discover("dataset", roots=[tmp_path / "ds"])] == ["ds"]


def test_dataset_detail_counts_contributors_and_images(tree: Path):
    found = {c.path.name: c for c in discover("dataset", roots=[tree])}
    assert found["ds_contrib"].detail == "2 contributors · 2 images"
    assert found["ds_classes"].detail == "1 images"


def test_models_skip_hidden_and_cache_dirs(tree: Path):
    found = discover("model", roots=[tree])
    assert [c.path.name for c in found] == ["m.pt"]
    assert found[0].detail == "2.0 KB"


def test_records_excludes_reports_and_junk(tree: Path):
    found = {c.path.name: c for c in discover("records", roots=[tree])}
    assert set(found) == {"chain.json", "stream.jsonl"}
    assert found["chain.json"].detail == "3 records"
    assert found["stream.jsonl"].detail == "2 records"


def test_classify(tree: Path):
    assert classify(tree / "ds_contrib") == "dataset"
    assert classify(tree / "models" / "m.pt") == "model"
    assert classify(tree / "rec" / "chain.json") == "records"
    assert classify(tree / "rec" / "report.json") is None
    assert classify(tree / "empty") is None
    assert classify(tree / "missing") is None


def test_unknown_kind_raises(tree: Path):
    with pytest.raises(ValueError):
        discover("spreadsheet", roots=[tree])


def test_duplicate_roots_are_deduplicated(tree: Path):
    found = discover("model", roots=[tree, tree / "models"])
    assert len(found) == 1


def test_discover_is_bounded(tmp_path: Path):
    for i in range(60):
        for j in range(60):
            (tmp_path / f"d{i}" / f"e{j}").mkdir(parents=True)
    started = time.monotonic()
    discover("model", roots=[tmp_path])
    assert time.monotonic() - started < 1.5


def test_resolve_asset_by_name(tree: Path):
    root = tree / "ds_contrib"
    index = build_asset_index(root)
    hit = resolve_asset("a1.jpg", index, root)
    assert hit == root / "contributor_a" / "images" / "a1.jpg"
    assert resolve_asset("contributor_b/images/b1.png", index, root) == \
        root / "contributor_b" / "images" / "b1.png"
    assert resolve_asset("nope.jpg", index, root) is None
    assert build_asset_index(None) == {}


def test_same_file_name_in_two_contributors_resolves_by_contributor(tmp_path: Path):
    root = tmp_path / "ds"
    a = _touch(root / "contributor_a" / "images" / "IMG_0001.jpg")
    b = _touch(root / "contributor_b" / "images" / "IMG_0001.jpg")
    index = build_asset_index(root)
    assert resolve_asset("IMG_0001.jpg", index, root, contributor="contributor_b") == b
    assert resolve_asset("IMG_0001.jpg", index, root, contributor="contributor_a") == a
    assert resolve_asset("IMG_0001.jpg", index, root) is None  # ambiguous: never guess
    assert sorted(resolve_assets("IMG_0001.jpg", index, root)) == sorted([a, b])
