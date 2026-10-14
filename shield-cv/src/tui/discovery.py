"""Find things SHIELD can check: dataset folders, model files, record chains.

Discovery is bounded (depth and directory budget) because the operator may
launch ``shield`` from a drive root or their home folder.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]

KINDS = ("dataset", "model", "records")
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"})
MODEL_EXTS = frozenset({".pt", ".pth", ".onnx"})
RECORD_EXTS = frozenset({".json", ".jsonl"})
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", "venv",
                       "site-packages", ".mypy_cache", ".pytest_cache", "wheels"})
MAX_DIRS_VISITED = 4000
MAX_RECORD_BYTES = 20 * 1024 * 1024
IMAGE_COUNT_CAP = 20000


@dataclass(frozen=True)
class Candidate:
    """One selectable target."""

    path: Path
    kind: str
    label: str
    detail: str


def default_roots() -> List[Path]:
    """Folders searched when the caller does not supply roots."""
    roots = [ROOT / "demo", ROOT / "output"]
    caller = os.environ.get("SHIELD_CALLER_CWD")
    if caller:
        roots.append(Path(caller))
    return roots


def _scan(folder: Path) -> Tuple[List[Path], List[Path]]:
    """One ``scandir`` pass: (visible sub-folders, files), both sorted.

    ``DirEntry.is_dir`` is answered from the directory listing itself on
    Windows, so this avoids a stat call per entry.
    """
    dirs: List[Path] = []
    files: List[Path] = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        if entry.name not in SKIP_DIRS and not entry.name.startswith("."):
                            dirs.append(Path(entry.path))
                    elif entry.is_file():
                        files.append(Path(entry.path))
                except OSError:
                    continue
    except OSError:
        pass
    return sorted(dirs), sorted(files)


def _subdirs(folder: Path) -> List[Path]:
    return _scan(folder)[0]


def _files(folder: Path) -> List[Path]:
    return _scan(folder)[1]


def _has_images(folder: Path) -> bool:
    return any(p.suffix.lower() in IMAGE_EXTS for p in _files(folder))


def is_dataset(folder: Path, strict: bool = False) -> bool:
    """A folder of images in any layout the data scanner understands.

    ``strict`` drops the weakest signal (a child folder that holds images),
    which is used for search roots: ``output/`` holding an image folder is a
    place to look, not a dataset.
    """
    if not folder.is_dir():
        return False
    if (folder / "classes.txt").is_file() or (folder / "data.yaml").is_file():
        return True
    if _has_images(folder):
        return True
    subdirs = _subdirs(folder)
    if any(d.name.lower().startswith("contributor") for d in subdirs):
        return True
    if any(d.name == "images" and _has_images(d) for d in subdirs):
        return True
    return not strict and any(_has_images(d) for d in subdirs)


def is_model(path: Path) -> bool:
    """A model weights file."""
    return path.is_file() and path.suffix.lower() in MODEL_EXTS


def _record_count(path: Path) -> Optional[int]:
    """Number of inference records in ``path``, or ``None`` if it is not a chain."""
    if not path.is_file() or path.suffix.lower() not in RECORD_EXTS:
        return None
    try:
        if path.stat().st_size > MAX_RECORD_BYTES:
            return None
        with path.open("r", encoding="utf-8") as handle:
            head = handle.read(4096)
            if path.suffix.lower() == ".json" and not head.lstrip().startswith("[") \
                    and '"records"' not in head:
                return None
            text = head + handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    if path.suffix.lower() == ".jsonl":
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            first = json.loads(lines[0]) if lines else None
        except ValueError:
            return None
        return len(lines) if isinstance(first, dict) and "record_hash" in first else None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = data.get("records")
    if isinstance(data, list) and data and isinstance(data[0], dict) and "record_hash" in data[0]:
        return len(data)
    return None


def is_records(path: Path) -> bool:
    """A signed inference-record chain (JSON list or JSONL)."""
    return _record_count(path) is not None


def classify(path: Path) -> Optional[str]:
    """Return the kind of ``path`` or ``None`` when SHIELD cannot check it."""
    if is_dataset(path):
        return "dataset"
    if is_model(path):
        return "model"
    if is_records(path):
        return "records"
    return None


def _count_images(folder: Path) -> int:
    count = 0
    for _, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        count += sum(1 for name in files if os.path.splitext(name)[1].lower() in IMAGE_EXTS)
        if count >= IMAGE_COUNT_CAP:
            return IMAGE_COUNT_CAP
    return count


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def describe(path: Path, kind: str) -> str:
    """Short human detail for a candidate, e.g. ``3 contributors · 573 images``."""
    try:
        if kind == "dataset":
            images = _count_images(path)
            contributors = sum(1 for d in _subdirs(path) if d.name.lower().startswith("contributor"))
            parts = []
            if contributors:
                parts.append(f"{contributors} contributor{'s' if contributors != 1 else ''}")
            parts.append(f"{images}{'+' if images >= IMAGE_COUNT_CAP else ''} images")
            return " · ".join(parts)
        if kind == "model":
            return _human_size(path.stat().st_size)
        if kind == "records":
            count = _record_count(path)
            return f"{count} records" if count is not None else "unreadable"
    except OSError:
        return "unreadable"
    return ""


def display_label(path: Path) -> str:
    """Path relative to the project or launch folder when possible."""
    resolved = path.resolve()
    bases = [ROOT]
    caller = os.environ.get("SHIELD_CALLER_CWD")
    if caller:
        bases.append(Path(caller))
    for base in bases:
        try:
            return resolved.relative_to(base.resolve()).as_posix() or "."
        except ValueError:
            continue
    return str(resolved)


def _walk(folder: Path, kind: str, depth: int, budget: List[int],
          is_root: bool = False) -> Iterator[Path]:
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if kind == "dataset":
        if is_dataset(folder, strict=is_root):
            yield folder
            return
        subdirs = _subdirs(folder)
    else:
        subdirs, files = _scan(folder)
        test = is_model if kind == "model" else is_records
        for path in files:
            if test(path):
                yield path
    if depth <= 0:
        return
    for child in subdirs:
        yield from _walk(child, kind, depth - 1, budget)


def discover(kind: str, roots: Optional[Sequence[Path]] = None,
             max_depth: int = 3) -> List[Candidate]:
    """List checkable targets of ``kind`` under ``roots``, sorted by label."""
    if kind not in KINDS:
        raise ValueError(f"unknown target kind: {kind}")
    seen = set()
    found: List[Candidate] = []
    budget = [MAX_DIRS_VISITED]
    for root in (default_roots() if roots is None else roots):
        root = Path(root)
        if not root.is_dir():
            continue
        for path in _walk(root, kind, max_depth, budget, is_root=True):
            key = os.path.normcase(str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            found.append(Candidate(path=path, kind=kind, label=display_label(path),
                                   detail=describe(path, kind)))
    found.sort(key=lambda c: c.label.lower())
    return found


def build_asset_index(root: Optional[Path], cap: int = 50000) -> Dict[str, List[Path]]:
    """Map image file name → every path under ``root`` with that name."""
    index: Dict[str, List[Path]] = {}
    if root is None or not Path(root).is_dir():
        return index
    count = 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                index.setdefault(name, []).append(Path(folder) / name)
                count += 1
                if count >= cap:
                    return index
    return index


def resolve_assets(name: str, index: Mapping[str, List[Path]], base: Optional[Path],
                   contributor: Optional[str] = None) -> List[Path]:
    """Every file a finding's ``affected_asset`` could mean, narrowed by contributor.

    Contributors often share naming schemes (``IMG_0001.jpg``), so a bare name
    can match several files; the finding's contributor picks the right one.
    """
    if not name:
        return []
    candidate = Path(name)
    if candidate.is_absolute() and candidate.is_file():
        return [candidate]
    if base is not None and len(candidate.parts) > 1 and (Path(base) / candidate).is_file():
        return [Path(base) / candidate]
    matches = list(index.get(candidate.name, []))
    if contributor and len(matches) > 1:
        mine = [p for p in matches if contributor in p.parts]
        matches = mine or matches
    return matches


def resolve_asset(name: str, index: Mapping[str, List[Path]], base: Optional[Path],
                  contributor: Optional[str] = None) -> Optional[Path]:
    """The one file ``name`` refers to, or ``None`` if missing or ambiguous."""
    matches = resolve_assets(name, index, base, contributor)
    return matches[0] if len(matches) == 1 else None
