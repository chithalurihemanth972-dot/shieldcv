# SHIELD Console TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the typed `shield>` prompt with a full-screen, keyboard-first Textual console where operators pick operations, targets and options from lists, watch real engine progress, and explore findings (with image previews) in-app.

**Architecture:** A new `src/tui/` package. Pure, UI-free modules (`discovery`, `recent`, `operations`, `verdict`, `visuals`) hold all logic and are unit-tested. `operations.py` is the only module that imports the engines. Textual screens and widgets compose these. Engine runs happen in Textual thread workers. Cancellation uses a `ScanCancelled(BaseException)` raised from the progress callback, which passes through every engine's `except Exception` guard, so **no engine code changes**.

**Tech Stack:** Python 3.10, Textual 8.2.x, textual-image 0.12 (sixel / half-cell previews), Rich 15, Pillow 10.4, pytest 9.

**Spec:** `docs/superpowers/specs/2026-10-15-shield-console-tui-design.md`

## Global Constraints

- Python 3.10+; `from __future__ import annotations` at the top of every new module (house style).
- New dependencies: exactly `textual>=8.2` and `textual-image>=0.12`. Nothing else.
- 100% offline: no network calls anywhere in `src/tui/`.
- Scripted CLI unchanged: `run.py`, `src/cli.py`, all non-`start` `shield.bat` subcommands and their exit codes.
- Reports are saved as `output/reports/SHIELD-<KIND>-<YYYYmmdd-HHMMSS>.json` (KIND ∈ SCAN, AUDIT, VERIFY, DRIFT, AGENTS); the full report keeps `generate_report`'s own file.
- Nothing may print to stdout while the TUI runs; use `src.utils.logger.get_logger`.
- Every operation choice is selected, never typed (the Browse modal's optional path box is the only text entry, besides list filters).
- Minimum layout 80×24; below that a notice screen is shown.
- Run tests with `python -m pytest tests/tui -q` from `shield-cv/`. **Never** run bare `pytest tests/`: `tests/test_edge_cases.py` is a script that executes at import.
- **Deviation from spec §3 (cancellation):** the spec proposed adding `except ScanCancelled: raise` to each engine. Investigation showed no engine uses a bare `except:`, so deriving `ScanCancelled` from `BaseException` achieves the same with zero engine edits (and avoids touching files with the user's uncommitted work). Task 1 pins this with tests per engine.

## Review Focus

1. **Huge launch folder** (operator runs `shield` from `C:\` or their home): discovery must stay bounded (depth 3, ≤4000 dirs) and finish in well under a second or two. *Test: Task 2 `test_discover_is_bounded`.*
2. **Report JSON files mistaken for record chains** (`output/reports/*.json` are dicts): they must not appear in the Verify picker. *Test: Task 2 `test_records_excludes_reports_and_junk`.*
3. **Finding asset names are bare filenames**, not paths (`"alpha_bottle_1.jpg"`): previews must resolve them under the dataset root. *Test: Task 2 `test_resolve_asset_by_name`, Task 9 `test_detail_shows_image_preview`.*
4. **Two runs in the same second** must not overwrite each other's report. *Test: Task 4 `test_save_report_never_overwrites`.*
5. **A UI callback that raises** (e.g. app closing mid-run) must not kill or corrupt the run. *Test: Task 4 `test_progress_ui_errors_do_not_break_run`.*

---

## File Structure

```
shield-cv/
  requirements.txt                      MODIFY  add textual, textual-image
  shield.py                             REWRITE thin launcher -> src.tui.launch()
  shield.bat                            MODIFY  pass args to start; --flags open console; help text
  src/utils/cancel.py                   CREATE  ScanCancelled, CancelToken
  src/tui/__init__.py                   CREATE  launch(): import guard + missing-deps hint
  src/tui/__main__.py                   CREATE  python -m src.tui
  src/tui/discovery.py                  CREATE  candidates by kind, classify, asset index
  src/tui/recent.py                     CREATE  last N reports for the home panel
  src/tui/verdict.py                    CREATE  headline (verdict/tone/risk/note), details rows
  src/tui/operations.py                 CREATE  OperationSpec registry, runners, execute(), save_report()
  src/tui/visuals.py                    CREATE  pure Rich renderables: gradients, bars, gauges, logo
  src/tui/theme.py                      CREATE  palette + Textual Theme
  src/tui/system.py                     CREATE  open_path() in the OS viewer
  src/tui/app.tcss                      CREATE  all styles
  src/tui/app.py                        CREATE  ShieldApp, navigation, launchers, quit guard, main()
  src/tui/commands.py                   CREATE  command-palette provider
  src/tui/widgets/__init__.py           CREATE
  src/tui/widgets/tile.py               CREATE  home tile
  src/tui/widgets/sized.py              CREATE  Sized: width-aware renderable host
  src/tui/widgets/target_picker.py      CREATE  discovered list + filter + Browse
  src/tui/widgets/stage_progress.py     CREATE  per-stage live rows
  src/tui/widgets/findings.py           CREATE  FindingsTable, FindingDetail
  src/tui/widgets/image_preview.py      CREATE  textual-image wrapper with graceful fallback
  src/tui/screens/__init__.py           CREATE
  src/tui/screens/modals.py             CREATE  ConfirmModal, BrowseModal, HelpModal, TooSmallScreen
  src/tui/screens/splash.py             CREATE
  src/tui/screens/home.py               CREATE
  src/tui/screens/operation.py          CREATE  target + options form (also the Full Report checklist)
  src/tui/screens/run.py                CREATE  live run, cancel, error panel, retry
  src/tui/screens/results.py            CREATE  verdict, gauges, tabs, findings browser
  src/tui/screens/agents.py             CREATE  live agent cards + meeting room
  tests/tui/conftest.py                 CREATE  sys.path + shared fixtures
  tests/tui/helpers.py                  CREATE  async_test, wait_for, fake specs
  tests/tui/test_cancel.py              CREATE
  tests/tui/test_discovery.py           CREATE
  tests/tui/test_recent_verdict.py      CREATE
  tests/tui/test_operations.py          CREATE
  tests/tui/test_visuals.py             CREATE
  tests/tui/test_app_home.py            CREATE
  tests/tui/test_app_operation.py       CREATE
  tests/tui/test_app_run.py             CREATE
  tests/tui/test_app_results.py         CREATE
  tests/tui/test_app_agents.py          CREATE
  tests/tui/e2e_screens.py              CREATE  real-engine headless run + SVG screenshots (script)
```

---

### Task 1: Dependencies and cooperative cancellation

**Files:**
- Modify: `requirements.txt` (Interface section)
- Create: `src/utils/cancel.py`
- Create: `tests/tui/conftest.py`, `tests/tui/helpers.py`
- Test: `tests/tui/test_cancel.py`

**Interfaces:**
- Produces: `src.utils.cancel.ScanCancelled(BaseException)`; `CancelToken` with `.cancel()`, `.cancelled -> bool`, `.check()` (raises `ScanCancelled` when set).
- Produces (tests): `tests/tui/helpers.py` → `async_test(fn)`, `async wait_for(pilot, predicate, timeout=5.0)`, `ROOT: Path`, `DEMO: Path`.

- [ ] **Step 1: Add dependencies and install**

In `requirements.txt`, replace the Interface block:

```
# ---- Interface -----------------------------------------------------------
streamlit>=1.30           # dashboard (GUI)
rich>=13.0                # coloured CLI output
textual>=8.2              # SHIELD Console full-screen terminal UI
textual-image>=0.12       # in-terminal image previews (sixel / half-cell)
```

Run: `python -m pip install "textual>=8.2" "textual-image>=0.12"`
Expected: `Successfully installed ... textual-8.2.x ... textual-image-0.12.x` (or "already satisfied").

- [ ] **Step 2: Create test scaffolding**

`tests/tui/conftest.py`:

```python
"""Shared pytest setup for the SHIELD Console tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, Path(__file__).resolve().parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
```

`tests/tui/helpers.py`:

```python
"""Helpers for driving Textual apps from plain (non-async) pytest tests."""
from __future__ import annotations

import asyncio
import functools
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"


def async_test(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run an ``async def`` test with ``asyncio.run`` (no pytest-asyncio needed)."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


async def wait_for(pilot: Any, predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Pump the app until ``predicate()`` is true, or fail after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await pilot.pause(0.05)
        if predicate():
            return
    raise AssertionError("condition not met within %.1fs" % timeout)
```

- [ ] **Step 3: Write the failing tests**

`tests/tui/test_cancel.py`:

```python
"""ScanCancelled must stop every engine; other callback errors stay swallowed."""
from __future__ import annotations

import pytest

from helpers import DEMO
from src.utils.cancel import CancelToken, ScanCancelled


def _cancel(*_args, **_kwargs):
    raise ScanCancelled()


def test_token_lifecycle():
    token = CancelToken()
    assert not token.cancelled
    token.check()
    token.cancel()
    assert token.cancelled
    with pytest.raises(ScanCancelled):
        token.check()


def test_scan_cancelled_is_not_an_exception():
    assert issubclass(ScanCancelled, BaseException)
    assert not issubclass(ScanCancelled, Exception)


def test_data_scanner_propagates_cancel():
    from src.scanners.data_scanner import DataIntegrityEngine
    with pytest.raises(ScanCancelled):
        DataIntegrityEngine().scan(str(DEMO / "data" / "clean"), max_images=4,
                                   progress_callback=_cancel)


def test_model_auditor_propagates_cancel():
    from src.scanners.model_auditor import ModelIntegrityEngine
    with pytest.raises(ScanCancelled):
        ModelIntegrityEngine().audit(str(DEMO / "models" / "clean_model_scripted.pt"),
                                     run_neural_cleanse=False, progress_callback=_cancel)


def test_drift_detector_propagates_cancel():
    from src.scanners.drift_detector import DistributionShiftDetector
    with pytest.raises(ScanCancelled):
        DistributionShiftDetector().compare(str(DEMO / "data" / "clean"),
                                            str(DEMO / "data" / "poisoned"),
                                            max_images=4, progress_callback=_cancel)


def test_crypto_chain_propagates_cancel():
    from src.scanners.crypto_chain import InferenceProvenanceEngine
    with pytest.raises(ScanCancelled):
        InferenceProvenanceEngine().verify(str(DEMO / "records" / "clean_chain.json"),
                                           progress_callback=_cancel)


def test_agents_propagate_cancel():
    from src.agents.manager import OfficeManager
    with pytest.raises(ScanCancelled):
        OfficeManager().run(str(DEMO / "data" / "clean"), contributors=["contributor_alpha"],
                            max_images=4, parallel=False,
                            agent_progress=lambda *a: _cancel())


def test_other_callback_errors_are_still_swallowed():
    from src.scanners.crypto_chain import InferenceProvenanceEngine

    def broken(*_args):
        raise ValueError("ui exploded")

    result = InferenceProvenanceEngine().verify(str(DEMO / "records" / "clean_chain.json"),
                                                progress_callback=broken)
    assert result["num_records"] > 0
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_cancel.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'src.utils.cancel'`.

- [ ] **Step 5: Implement `src/utils/cancel.py`**

```python
"""Cooperative cancellation for long-running engine calls.

The UI cannot kill a worker thread, so it asks the engine to stop: the progress
callback raises :class:`ScanCancelled` once a :class:`CancelToken` is set, and
the run unwinds at its next progress tick.
"""

from __future__ import annotations

import threading


class ScanCancelled(BaseException):
    """Raised from a progress callback to stop an engine run.

    Derives from ``BaseException`` on purpose: every engine guards its progress
    callback and its main body with ``except Exception``, which would swallow an
    ordinary exception and let the run carry on.
    """


class CancelToken:
    """Thread-safe cancel flag shared by the UI thread and an engine worker."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; the run stops at its next progress tick."""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._event.is_set()

    def check(self) -> None:
        """Raise :class:`ScanCancelled` if cancellation has been requested."""
        if self._event.is_set():
            raise ScanCancelled()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_cancel.py -q`
Expected: `8 passed`. If `test_agents_propagate_cancel` fails, read `src/agents/manager.py:_run_serial` / `agent_scan_contributor` for an `except BaseException` and report it — do **not** edit engines without asking.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/utils/cancel.py tests/tui/conftest.py tests/tui/helpers.py tests/tui/test_cancel.py
git commit -m "feat(tui): add Textual deps and cooperative ScanCancelled"
```

---

### Task 2: Target discovery

**Files:**
- Create: `src/tui/__init__.py` (placeholder docstring only for now; `launch()` arrives in Task 6), `src/tui/discovery.py`
- Test: `tests/tui/test_discovery.py`

**Interfaces:**
- Produces: `KINDS = ("dataset", "model", "records")`; `IMAGE_EXTS: frozenset[str]`;
  `@dataclass(frozen=True) Candidate(path: Path, kind: str, label: str, detail: str)`;
  `default_roots() -> list[Path]`; `discover(kind: str, roots: Sequence[Path] | None = None, max_depth: int = 3) -> list[Candidate]`;
  `classify(path: Path) -> str | None`; `describe(path: Path, kind: str) -> str`;
  `build_asset_index(root: Path | None, cap: int = 50000) -> dict[str, Path]`;
  `resolve_asset(name: str, index: Mapping[str, Path], base: Path | None) -> Path | None`;
  `ROOT: Path` (project root).

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_discovery.py`:

```python
"""Discovery lists sensible targets and stays bounded."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.tui.discovery import (build_asset_index, classify, discover, resolve_asset)


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
    assert time.monotonic() - started < 3.0


def test_resolve_asset_by_name(tree: Path):
    root = tree / "ds_contrib"
    index = build_asset_index(root)
    hit = resolve_asset("a1.jpg", index, root)
    assert hit == root / "contributor_a" / "images" / "a1.jpg"
    assert resolve_asset("contributor_b/images/b1.png", index, root) == \
        root / "contributor_b" / "images" / "b1.png"
    assert resolve_asset("nope.jpg", index, root) is None
    assert build_asset_index(None) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_discovery.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui'`.

- [ ] **Step 3: Implement**

`src/tui/__init__.py`:

```python
"""SHIELD Console — full-screen terminal UI for SHIELD-CV."""
```

`src/tui/discovery.py`:

```python
"""Find things SHIELD can check: dataset folders, model files, record chains.

Discovery is bounded (depth and directory budget) because the operator may
launch ``shield`` from a drive root or their home folder.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence

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


def _subdirs(folder: Path) -> List[Path]:
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith("."))
    except OSError:
        return []


def _files(folder: Path) -> List[Path]:
    try:
        return sorted(p for p in folder.iterdir() if p.is_file())
    except OSError:
        return []


def _has_images(folder: Path) -> bool:
    return any(p.suffix.lower() in IMAGE_EXTS for p in _files(folder))


def is_dataset(folder: Path) -> bool:
    """A folder of images in any layout the data scanner understands."""
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
    return any(_has_images(d) for d in subdirs)


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


def _walk(folder: Path, kind: str, depth: int, budget: List[int]) -> Iterator[Path]:
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if kind == "dataset":
        if is_dataset(folder):
            yield folder
            return
    else:
        test = is_model if kind == "model" else is_records
        for path in _files(folder):
            if test(path):
                yield path
    if depth <= 0:
        return
    for child in _subdirs(folder):
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
        for path in _walk(root, kind, max_depth, budget):
            key = os.path.normcase(str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            found.append(Candidate(path=path, kind=kind, label=display_label(path),
                                   detail=describe(path, kind)))
    found.sort(key=lambda c: c.label.lower())
    return found


def build_asset_index(root: Optional[Path], cap: int = 50000) -> Dict[str, Path]:
    """Map image file name → path under ``root`` (first hit wins)."""
    index: Dict[str, Path] = {}
    if root is None or not Path(root).is_dir():
        return index
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                index.setdefault(name, Path(folder) / name)
                if len(index) >= cap:
                    return index
    return index


def resolve_asset(name: str, index: Mapping[str, Path], base: Optional[Path]) -> Optional[Path]:
    """Turn a finding's ``affected_asset`` (often a bare file name) into a real path."""
    if not name:
        return None
    candidate = Path(name)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    if base is not None and (Path(base) / candidate).is_file():
        return Path(base) / candidate
    return index.get(candidate.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_discovery.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Sanity-check against the real demo tree**

Run: `python -c "from src.tui.discovery import discover; [print(c.label, '|', c.detail) for k in ('dataset','model','records') for c in discover(k)]"`
Expected: datasets include `demo/data/poisoned | 3 contributors · … images`, `demo/data/drift/dusk`, no `contributor_alpha` rows; models list the `.pt/.onnx/.pth`; records list `clean_chain.json`, `tampered_*.json`, `validate_*.json`, **not** `ground_truth_*` or `output/reports/*`.

- [ ] **Step 6: Commit**

```bash
git add src/tui/__init__.py src/tui/discovery.py tests/tui/test_discovery.py
git commit -m "feat(tui): bounded target discovery and asset resolution"
```

---

### Task 3: Verdict headlines and recent reports

**Files:**
- Create: `src/tui/verdict.py`, `src/tui/recent.py`
- Test: `tests/tui/test_recent_verdict.py`

**Interfaces:**
- Consumes: `src.cli._assessment_failed(result) -> bool` (existing).
- Produces (`verdict.py`): `MODULE_OP: dict[str, str]`; `op_id_for(result: Mapping) -> str | None`;
  `@dataclass(frozen=True) Headline(verdict: str, tone: str, risk: float | None, note: str)` with tone ∈ {"danger","warn","ok","info"};
  `headline(op_id: str, result: Mapping) -> Headline`; `details_rows(op_id: str, result: Mapping) -> list[tuple[str, str]]`;
  `risk_tone(risk: float | None) -> str`.
- Produces (`recent.py`): `REPORTS_DIR: Path`; `@dataclass(frozen=True) RecentItem(path: Path, op_id: str, kind: str, target: str, verdict: str, tone: str, risk: float | None, modified: float)`;
  `recent_reports(n: int = 5, reports_dir: Path | None = None) -> list[RecentItem]`; `load_report(path: Path) -> dict` (raises `ValueError`); `humanize_age(seconds: float) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_recent_verdict.py`:

```python
"""Headlines read every module's verdict; recent reports tolerate junk."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.tui.recent import humanize_age, recent_reports
from src.tui.verdict import details_rows, headline, op_id_for

SCAN = {"module": "data_scanner", "target": "C:/x/demo/data/poisoned",
        "dataset": {"num_samples": 10, "root": "C:/x/demo/data/poisoned"},
        "summary": {"verdict": "COMPROMISED", "risk_score": 0.82, "total_findings": 7},
        "findings": []}
CHAIN = {"module": "crypto_chain", "target": "chain.json", "num_records": 5,
         "chain_valid": False, "first_break_index": 3, "summary": {"risk_score": 0.9}}


def test_scan_headline():
    h = headline("scan", SCAN)
    assert (h.verdict, h.tone, h.risk) == ("COMPROMISED", "danger", 0.82)
    assert "7 findings" in h.note


def test_verify_headline_uses_chain_validity():
    h = headline("verify", CHAIN)
    assert (h.verdict, h.tone) == ("BROKEN", "danger")
    assert "first break at record 3" in h.note
    assert headline("verify", {**CHAIN, "chain_valid": True}).verdict == "VALID"


def test_drift_and_agents_and_report():
    assert headline("drift", {"module": "drift_detector", "shift_type": "NATURAL_OPERATIONAL_DRIFT",
                              "risk_score": 0.2, "characterization": "dusk"}).tone == "ok"
    agents = {"module": "office_manager", "reports": [{}], "meeting": {"verdict": "SUSPICIOUS"}}
    assert headline("agents", agents).verdict == "SUSPICIOUS"
    report = {"schema_version": "1", "summary": {"verdict": "COMPROMISED", "risk_score": 0.99},
              "immunity": {"score": 12.5, "band": "COMPROMISED"}}
    h = headline("report", report)
    assert h.verdict == "COMPROMISED" and "immunity 12.5/100" in h.note


def test_failed_assessment_is_inconclusive_not_clean():
    empty = {**SCAN, "dataset": {"num_samples": 0}, "summary": {"verdict": "CLEAN"}}
    h = headline("scan", empty)
    assert (h.verdict, h.tone, h.risk) == ("INCONCLUSIVE", "warn", None)


def test_unknown_verdict_is_info():
    assert headline("scan", {**SCAN, "summary": {"verdict": "WEIRD"}}).tone == "info"


def test_op_id_for():
    assert op_id_for(SCAN) == "scan"
    assert op_id_for(CHAIN) == "verify"
    assert op_id_for({"schema_version": "1"}) == "report"
    assert op_id_for({"module": "nope"}) is None


def test_details_rows_scan():
    rows = dict(details_rows("scan", SCAN))
    assert rows["Samples"] == "10"


def _write(folder: Path, name: str, payload, mtime: float) -> Path:
    path = folder / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_recent_reports_newest_first_and_skip_junk(tmp_path: Path):
    _write(tmp_path, "SHIELD-SCAN-1.json", SCAN, 1000)
    _write(tmp_path, "SHIELD-VERIFY-2.json", CHAIN, 2000)
    _write(tmp_path, "broken.json", "{oops", 3000)
    _write(tmp_path, "list.json", [1, 2], 4000)
    items = recent_reports(5, tmp_path)
    assert [i.op_id for i in items] == ["verify", "scan"]
    assert items[0].verdict == "BROKEN" and items[0].kind == "VERIFY"
    assert items[1].target == "poisoned" and items[1].risk == 0.82
    assert len(recent_reports(1, tmp_path)) == 1


def test_recent_reports_missing_dir(tmp_path: Path):
    assert recent_reports(5, tmp_path / "nope") == []


def test_humanize_age():
    assert humanize_age(5) == "just now"
    assert humanize_age(125) == "2m ago"
    assert humanize_age(7200) == "2h ago"
    assert humanize_age(3 * 86400) == "3d ago"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_recent_verdict.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.recent'`.

- [ ] **Step 3: Implement `src/tui/verdict.py`**

```python
"""Turn any module result into one headline: verdict, tone, risk and a note."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from src.cli import _assessment_failed

MODULE_OP = {"data_scanner": "scan", "model_auditor": "audit", "crypto_chain": "verify",
             "drift_detector": "drift", "office_manager": "agents"}

TONE_BY_VERDICT = {
    "COMPROMISED": "danger", "BROKEN": "danger", "SUSPICIOUS_MANIPULATION": "danger",
    "SUSPICIOUS": "warn", "CAUTION": "warn", "MIXED_DRIFT": "warn", "MARGINAL": "warn",
    "INCONCLUSIVE": "warn", "NOT_ASSESSED": "warn",
    "CLEAN": "ok", "VALID": "ok", "NATURAL_OPERATIONAL_DRIFT": "ok",
    "NO_SIGNIFICANT_DRIFT": "ok", "HARDENED": "ok", "ADEQUATE": "ok",
}


@dataclass(frozen=True)
class Headline:
    """What the results banner shows."""

    verdict: str
    tone: str
    risk: Optional[float]
    note: str


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def risk_tone(risk: Optional[float]) -> str:
    """Colour band for a 0..1 risk score."""
    if risk is None:
        return "info"
    if risk >= 0.75:
        return "danger"
    if risk >= 0.45:
        return "warn"
    return "ok"


def op_id_for(result: Mapping[str, Any]) -> Optional[str]:
    """Which operation produced ``result``."""
    if "schema_version" in result:
        return "report"
    return MODULE_OP.get(str(result.get("module", "")))


def headline(op_id: str, result: Mapping[str, Any]) -> Headline:
    """Summarise a result for the banner. Unassessed runs are never shown as clean."""
    summary = result.get("summary") or {}
    if op_id not in ("agents", "report") and _assessment_failed(dict(result)):
        return Headline("INCONCLUSIVE", "warn", None,
                        "The target could not be fully assessed — this is not a clean result.")
    risk = _float(summary.get("risk_score", result.get("risk_score")))
    findings = int(summary.get("total_findings", len(result.get("findings") or [])) or 0)
    note = f"{findings} findings"
    if op_id == "verify":
        verdict = "VALID" if result.get("chain_valid") else "BROKEN"
        brk = result.get("first_break_index")
        note = f"{result.get('num_records', 0)} records · " + (
            f"first break at record {brk}" if brk is not None else "no breaks")
    elif op_id == "drift":
        verdict = str(result.get("shift_type") or "UNKNOWN")
        note = str(result.get("characterization") or "")
    elif op_id == "agents":
        verdict = str((result.get("meeting") or {}).get("verdict") or "UNKNOWN")
        note = f"{len(result.get('reports') or [])} agents"
    else:
        verdict = str(summary.get("verdict") or "UNKNOWN")
        if op_id == "report":
            immunity = result.get("immunity") or {}
            note = (f"immunity {float(immunity.get('score', 0.0)):.1f}/100 · "
                    f"{immunity.get('band', '?')} · {findings} findings")
    verdict = verdict.upper()
    return Headline(verdict, TONE_BY_VERDICT.get(verdict, "info"), risk, note)


def _backbone_name(backbone: Any) -> str:
    if isinstance(backbone, dict):
        return str(backbone.get("name") or backbone.get("model") or "?")
    return str(backbone or "?")


def details_rows(op_id: str, result: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """Module-specific key facts for the Details tab."""
    rows: List[Tuple[str, str]] = [("Target", str(result.get("target") or "—"))]
    if op_id == "scan":
        ds = result.get("dataset") or {}
        rows += [("Format", str(ds.get("format", "?"))), ("Samples", str(ds.get("num_samples", 0))),
                 ("Classes", str(ds.get("num_classes", 0))),
                 ("Contributors", str(len(ds.get("contributors") or []))),
                 ("Backbone", _backbone_name(result.get("backbone")))]
    elif op_id == "audit":
        model = result.get("model") or {}
        rows += [("Framework", str(model.get("framework", "?"))),
                 ("Access level", str(result.get("access_level", "?"))),
                 ("Parameters", f"{int(model.get('num_parameters') or 0):,}"),
                 ("Classes", str(model.get("num_classes", "?"))),
                 ("Weight hash", str(model.get("weight_hash") or "—")[:24]),
                 ("Confidence", f"{float(result.get('confidence', 0.0)):.2f}")]
    elif op_id == "verify":
        rows += [("Records", str(result.get("num_records", 0))),
                 ("Chain valid", "yes" if result.get("chain_valid") else "no"),
                 ("First break", str(result.get("first_break_index", "none")))]
    elif op_id == "drift":
        rows += [("Shift type", str(result.get("shift_type", "?"))),
                 ("Severity", str(result.get("severity", "?"))),
                 ("Confidence", f"{float(result.get('confidence', 0.0)):.2f}"),
                 ("Characterization", str(result.get("characterization", ""))),
                 ("Recommendation", str(result.get("recommendation", "")))]
    elif op_id == "report":
        immunity = result.get("immunity") or {}
        rows += [("Immunity", f"{float(immunity.get('score', 0.0)):.1f} / 100"),
                 ("Band", str(immunity.get("band", "?"))),
                 ("Modules", ", ".join(result.get("modules") or {})),
                 ("Schema valid", str(result.get("schema_valid"))),
                 ("Report hash", str(result.get("report_hash", ""))[:32])]
    duration = result.get("duration_seconds")
    if duration is not None:
        rows.append(("Duration", f"{float(duration):.1f}s"))
    return rows


def target_name(result: Mapping[str, Any]) -> str:
    """Short name of what was checked."""
    target = result.get("target") or result.get("root")
    if isinstance(target, str) and target:
        return Path(target).name or target
    return "all modules" if "schema_version" in result else "—"
```

- [ ] **Step 4: Implement `src/tui/recent.py`**

```python
"""The home screen's Recent results panel."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.tui.discovery import ROOT
from src.tui.verdict import headline, op_id_for, target_name

REPORTS_DIR = ROOT / "output" / "reports"
KIND_LABEL = {"scan": "SCAN", "audit": "AUDIT", "verify": "VERIFY", "drift": "DRIFT",
              "agents": "AGENTS", "report": "REPORT"}


@dataclass(frozen=True)
class RecentItem:
    """One saved report, summarised."""

    path: Path
    op_id: str
    kind: str
    target: str
    verdict: str
    tone: str
    risk: Optional[float]
    modified: float


def load_report(path: Path) -> Dict[str, Any]:
    """Read a saved report; raises ``ValueError`` if it is not a report object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable report {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"not a report object: {path}")
    return data


def recent_reports(n: int = 5, reports_dir: Optional[Path] = None) -> List[RecentItem]:
    """The ``n`` newest readable reports, newest first."""
    folder = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    try:
        files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    items: List[RecentItem] = []
    for path in files:
        if len(items) >= n:
            break
        try:
            data = load_report(path)
        except ValueError:
            continue
        op_id = op_id_for(data)
        if op_id is None:
            continue
        head = headline(op_id, data)
        items.append(RecentItem(path=path, op_id=op_id, kind=KIND_LABEL[op_id],
                                target=target_name(data), verdict=head.verdict, tone=head.tone,
                                risk=head.risk, modified=path.stat().st_mtime))
    return items


def humanize_age(seconds: float) -> str:
    """``5m ago`` style age."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def age_of(item: RecentItem) -> str:
    """Age of a recent item relative to now."""
    return humanize_age(time.time() - item.modified)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_recent_verdict.py -q`
Expected: `11 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/tui/verdict.py src/tui/recent.py tests/tui/test_recent_verdict.py
git commit -m "feat(tui): verdict headlines and recent-report summaries"
```

---

### Task 4: Operation registry and execution

**Files:**
- Create: `src/tui/operations.py`
- Test: `tests/tui/test_operations.py`

**Interfaces:**
- Consumes: `CancelToken`, `ScanCancelled` (Task 1); engines (`DataIntegrityEngine.scan`, `ModelIntegrityEngine.audit`, `InferenceProvenanceEngine.verify`, `DistributionShiftDetector.compare`, `OfficeManager.run`, `MeetingRoom.convene`, `build_threat_story`, `compute_immunity_score`, `generate_briefing`, `generate_report`).
- Produces:
  - `ProgressFn = Callable[..., None]` called as `progress(stage: str, done: int, total: int, detail: str | None = None)`.
  - `@dataclass(frozen=True) Choice(label: str, value: Any)`.
  - `@dataclass(frozen=True) OptionSpec(key: str, label: str, kind: str, default: Any = None, choices: tuple[Choice, ...] = (), target_kind: str | None = None, optional: bool = False)` — kind ∈ {"select","switch","target"}; for "target", `default` is a preferred label like `"demo/data/clean"`.
  - `@dataclass(frozen=True) OperationSpec(id, title, icon, ascii_icon, hotkey, blurb, target_kind: str | None, target_label: str, default_target: str | None, options: tuple[OptionSpec, ...], stages: tuple[tuple[str, str], ...], runner: Callable[[dict, ProgressFn], dict], report_prefix: str, self_saving: bool = False)`.
  - `@dataclass RunOutcome(result: dict, report_path: Path | None, save_error: str | None, elapsed: float)`.
  - `STAGE_LABELS: dict[str, str]`; `OPERATIONS: tuple[OperationSpec, ...]` (order: scan, audit, verify, drift, agents, report); `OPERATIONS_BY_ID: dict[str, OperationSpec]`.
  - `execute(spec, params, on_progress, token=None, reports_dir=None) -> RunOutcome` (raises `ScanCancelled` or the runner's exception).
  - `save_report(result, prefix, reports_dir=None) -> tuple[Path | None, str | None]`.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_operations.py`:

```python
"""execute() wires progress, cancellation and saving around any runner."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from src.tui.operations import (OPERATIONS, OPERATIONS_BY_ID, STAGE_LABELS, execute,
                                save_report)
from src.utils.cancel import CancelToken, ScanCancelled

RESULT = {"module": "data_scanner", "summary": {"verdict": "CLEAN"}, "findings": []}


def _spec(runner, **changes):
    return dataclasses.replace(OPERATIONS_BY_ID["scan"], runner=runner, **changes)


def test_execute_forwards_progress_and_saves(tmp_path: Path):
    seen = []

    def runner(params, progress):
        assert params == {"target": "x"}
        progress("loading", 0, 1)
        progress("embedding", 5, 10)
        return dict(RESULT)

    outcome = execute(_spec(runner), {"target": "x"}, lambda *a: seen.append(a),
                      reports_dir=tmp_path)
    assert seen == [("loading", 0, 1, None), ("embedding", 5, 10, None)]
    assert outcome.report_path.parent == tmp_path
    assert outcome.report_path.name.startswith("SHIELD-SCAN-")
    assert json.loads(outcome.report_path.read_text(encoding="utf-8")) == RESULT
    assert outcome.save_error is None and outcome.elapsed >= 0


def test_cancel_stops_the_runner(tmp_path: Path):
    token = CancelToken()
    reached = []

    def runner(params, progress):
        for i in range(100):
            progress("embedding", i, 100)
            reached.append(i)
        return dict(RESULT)

    def on_progress(stage, done, total, detail):
        if done == 2:
            token.cancel()

    with pytest.raises(ScanCancelled):
        execute(_spec(runner), {}, on_progress, token, reports_dir=tmp_path)
    assert reached == [0, 1, 2]
    assert list(tmp_path.iterdir()) == []


def test_cancel_before_start_never_calls_runner():
    token = CancelToken()
    token.cancel()
    with pytest.raises(ScanCancelled):
        execute(_spec(lambda p, g: pytest.fail("runner called")), {}, lambda *a: None, token)


def test_progress_ui_errors_do_not_break_run(tmp_path: Path):
    def runner(params, progress):
        progress("loading", 0, 1)
        return dict(RESULT)

    def exploding(*_a):
        raise RuntimeError("app is closing")

    outcome = execute(_spec(runner), {}, exploding, reports_dir=tmp_path)
    assert outcome.result == RESULT


def test_save_failure_is_reported_not_raised(tmp_path: Path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    outcome = execute(_spec(lambda p, g: dict(RESULT)), {}, lambda *a: None,
                      reports_dir=blocker / "sub")
    assert outcome.report_path is None and outcome.save_error
    assert outcome.result == RESULT


def test_save_report_never_overwrites(tmp_path: Path):
    first, _ = save_report({"a": 1}, "SCAN", tmp_path)
    second, _ = save_report({"a": 2}, "SCAN", tmp_path)
    assert first != second
    assert json.loads(first.read_text())["a"] == 1


def test_self_saving_uses_report_path(tmp_path: Path):
    target = tmp_path / "SCAN-x.json"
    spec = dataclasses.replace(OPERATIONS_BY_ID["report"],
                               runner=lambda p, g: {"report_path": str(target)})
    outcome = execute(spec, {}, lambda *a: None, reports_dir=tmp_path)
    assert outcome.report_path == target
    assert list(tmp_path.iterdir()) == []


def test_registry_is_consistent():
    assert [s.id for s in OPERATIONS] == ["scan", "audit", "verify", "drift", "agents", "report"]
    assert len({s.hotkey for s in OPERATIONS}) == len(OPERATIONS)
    for spec in OPERATIONS:
        assert spec.stages and all(label for _, label in spec.stages)
        for option in spec.options:
            if option.kind == "select":
                assert option.default in [c.value for c in option.choices]
    assert STAGE_LABELS["embedding"]


def test_full_report_needs_a_module():
    with pytest.raises(ValueError, match="at least one"):
        OPERATIONS_BY_ID["report"].runner({}, lambda *a, **k: None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_operations.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.operations'`.

- [ ] **Step 3: Implement `src/tui/operations.py`**

```python
"""Every operation the console can run, and the one place that calls the engines."""

from __future__ import annotations

import gc
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from src.tui.discovery import ROOT
from src.utils.cancel import CancelToken
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)
REPORTS_DIR = ROOT / "output" / "reports"

ProgressFn = Callable[..., None]

STAGE_LABELS: Dict[str, str] = {
    "loading": "Loading", "embedding": "ResNet-18 embeddings", "duplicates": "Copy-flood check",
    "trigger": "Backdoor-trigger check", "label_flip": "Wrong-label check",
    "ood": "Outsider check", "mislabel": "Systematic-mislabel check",
    "weights": "Weight hash + layer statistics", "neural_cleanse": "Neural Cleanse",
    "activation_clustering": "Activation clustering", "blackbox": "Behavioural fingerprint",
    "chain": "Hash links", "tamper": "Payload tamper check", "replay": "Replay / nonce check",
    "signature": "Ed25519 signatures", "pixel": "Pixel statistics",
    "features": "Feature distribution", "agents": "Contributor agents",
    "meeting": "Meeting room", "data": "Data integrity", "model": "Model audit",
    "drift": "Distribution drift", "intel": "Correlate · immunity · briefing",
}


@dataclass(frozen=True)
class Choice:
    """One entry of a select option."""

    label: str
    value: Any


@dataclass(frozen=True)
class OptionSpec:
    """A form field on the Operation screen."""

    key: str
    label: str
    kind: str
    default: Any = None
    choices: Tuple[Choice, ...] = ()
    target_kind: Optional[str] = None
    optional: bool = False


@dataclass(frozen=True)
class OperationSpec:
    """Everything the UI needs to offer and run one operation."""

    id: str
    title: str
    icon: str
    ascii_icon: str
    hotkey: str
    blurb: str
    target_kind: Optional[str]
    target_label: str
    default_target: Optional[str]
    options: Tuple[OptionSpec, ...]
    stages: Tuple[Tuple[str, str], ...]
    runner: Callable[[Dict[str, Any], ProgressFn], Dict[str, Any]]
    report_prefix: str
    self_saving: bool = False


@dataclass
class RunOutcome:
    """A finished run."""

    result: Dict[str, Any]
    report_path: Optional[Path]
    save_error: Optional[str]
    elapsed: float


def _stages(*ids: str) -> Tuple[Tuple[str, str], ...]:
    return tuple((i, STAGE_LABELS[i]) for i in ids)


def _run_scan(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.data_scanner import DataIntegrityEngine
    return DataIntegrityEngine().scan(str(params["target"]), max_images=params.get("max_images"),
                                      progress_callback=progress)


def _run_audit(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.analysis import embeddings
    from src.scanners.model_auditor import ModelIntegrityEngine
    # Free the shared ResNet-18 before Neural Cleanse, as the old console did,
    # so an 8 GB host does not run out of memory.
    embeddings._EXTRACTOR_SINGLETON = None
    gc.collect()
    reference = params.get("reference")
    return ModelIntegrityEngine().audit(
        str(params["target"]), reference_path=str(reference) if reference else None,
        run_neural_cleanse=bool(params.get("neural_cleanse", True)), progress_callback=progress)


def _run_verify(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.crypto_chain import InferenceProvenanceEngine
    return InferenceProvenanceEngine().verify(str(params["target"]), progress_callback=progress)


def _run_drift(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.scanners.drift_detector import DistributionShiftDetector
    return DistributionShiftDetector().compare(str(params["baseline"]), str(params["target"]),
                                               max_images=params.get("max_images"),
                                               progress_callback=progress)


def _run_agents(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.agents.manager import OfficeManager
    from src.agents.meeting import MeetingRoom
    office = OfficeManager().run(
        str(params["target"]),
        progress_callback=lambda name, done, total: progress("finished", done, total, name),
        agent_progress=lambda name, stage, done, total: progress(stage, done, total, name))
    progress("meeting", 0, 1)
    office["meeting"] = MeetingRoom().convene(office)
    progress("meeting", 1, 1)
    return office


def _run_report(params: Dict[str, Any], progress: ProgressFn) -> Dict[str, Any]:
    from src.intelligence.briefing import generate_briefing
    from src.intelligence.immunity import compute_immunity_score
    from src.intelligence.threat_story import build_threat_story
    from src.reporting.report_generator import generate_report

    def phase(stage_id: str) -> ProgressFn:
        def forward(stage: str, done: int, total: int, detail: Optional[str] = None) -> None:
            progress(stage_id, done, total, STAGE_LABELS.get(stage, stage))
        return forward

    wants_drift = bool(params.get("baseline") and params.get("current"))
    if not any(params.get(k) for k in ("data", "model", "records")) and not wants_drift:
        raise ValueError("Pick at least one module target for the full report.")
    modules: Dict[str, Dict[str, Any]] = {}
    target: Dict[str, Any] = {}
    if params.get("data"):
        modules["data_scanner"] = _run_scan({"target": params["data"]}, phase("data"))
        target["dataset"] = str(params["data"])
    if params.get("model"):
        modules["model_auditor"] = _run_audit(
            {"target": params["model"], "neural_cleanse": params.get("neural_cleanse", True)},
            phase("model"))
        target["model"] = str(params["model"])
    if params.get("records"):
        modules["crypto_chain"] = _run_verify({"target": params["records"]}, phase("chain"))
        target["records"] = str(params["records"])
    if wants_drift:
        modules["drift_detector"] = _run_drift(
            {"baseline": params["baseline"], "target": params["current"], "max_images": 120},
            phase("drift"))
        target["drift"] = {"baseline": str(params["baseline"]), "current": str(params["current"])}
    progress("intel", 0, 3)
    story = build_threat_story(modules)
    progress("intel", 1, 3)
    immunity = compute_immunity_score(modules, story)
    progress("intel", 2, 3)
    briefing = generate_briefing(modules, story, immunity, use_llm=False)
    report = generate_report(modules, story, immunity, briefing, target=target, persist=True)
    progress("intel", 3, 3)
    return report


_MAX_IMAGES = (Choice("All", None), Choice("100", 100), Choice("250", 250),
               Choice("500", 500), Choice("1000", 1000))

OPERATIONS: Tuple[OperationSpec, ...] = (
    OperationSpec(
        id="scan", title="Scan dataset", icon="▣", ascii_icon="[#]", hotkey="d",
        blurb="Poisoned images, flipped labels, copy floods, outsiders",
        target_kind="dataset", target_label="Dataset", default_target="demo/data/poisoned",
        options=(OptionSpec("max_images", "Max images", "select", None, _MAX_IMAGES),),
        stages=_stages("loading", "embedding", "duplicates", "trigger", "label_flip", "ood",
                       "mislabel"),
        runner=_run_scan, report_prefix="SCAN"),
    OperationSpec(
        id="audit", title="Audit model", icon="◉", ascii_icon="(o)", hotkey="m",
        blurb="Backdoors, swapped weights, odd behaviour",
        target_kind="model", target_label="Model",
        default_target="demo/models/backdoored_model_scripted.pt",
        options=(OptionSpec("reference", "Trusted reference model", "target",
                            target_kind="model", optional=True),
                 OptionSpec("neural_cleanse", "Run Neural Cleanse (slow, thorough)", "switch",
                            True)),
        stages=_stages("loading", "weights", "neural_cleanse", "activation_clustering",
                       "blackbox"),
        runner=_run_audit, report_prefix="AUDIT"),
    OperationSpec(
        id="verify", title="Verify chain", icon="⛓", ascii_icon="<=>", hotkey="v",
        blurb="Signed inference records: edits, deletions, replays",
        target_kind="records", target_label="Record chain",
        default_target="demo/records/tampered_replay.json", options=(),
        stages=_stages("chain", "tamper", "replay", "signature"),
        runner=_run_verify, report_prefix="VERIFY"),
    OperationSpec(
        id="drift", title="Drift", icon="≈", ascii_icon="~~", hotkey="f",
        blurb="Natural change or deliberate manipulation?",
        target_kind="dataset", target_label="Current corpus",
        default_target="demo/data/poisoned",
        options=(OptionSpec("baseline", "Baseline corpus", "target", "demo/data/clean",
                            target_kind="dataset"),
                 OptionSpec("max_images", "Max images", "select", 120,
                            (Choice("60", 60), Choice("120", 120), Choice("250", 250),
                             Choice("All", None)))),
        stages=_stages("loading", "pixel", "features"),
        runner=_run_drift, report_prefix="DRIFT"),
    OperationSpec(
        id="agents", title="Agents", icon="⚇", ascii_icon="&&", hotkey="a",
        blurb="One agent per contributor, in parallel",
        target_kind="dataset", target_label="Dataset root (contributor folders)",
        default_target="demo/data/poisoned", options=(),
        stages=_stages("agents", "meeting"),
        runner=_run_agents, report_prefix="AGENTS"),
    OperationSpec(
        id="report", title="Full report", icon="★", ascii_icon="(*)", hotkey="r",
        blurb="All modules, correlated, signed",
        target_kind=None, target_label="",
        default_target=None,
        options=(OptionSpec("data", "Dataset", "target", "demo/data/poisoned",
                            target_kind="dataset", optional=True),
                 OptionSpec("model", "Model", "target",
                            "demo/models/backdoored_model_scripted.pt",
                            target_kind="model", optional=True),
                 OptionSpec("records", "Record chain", "target",
                            "demo/records/tampered_replay.json",
                            target_kind="records", optional=True),
                 OptionSpec("baseline", "Drift baseline", "target", "demo/data/clean",
                            target_kind="dataset", optional=True),
                 OptionSpec("current", "Drift current", "target", "demo/data/poisoned",
                            target_kind="dataset", optional=True),
                 OptionSpec("neural_cleanse", "Run Neural Cleanse", "switch", True)),
        stages=_stages("data", "model", "chain", "drift", "intel"),
        runner=_run_report, report_prefix="REPORT", self_saving=True),
)
OPERATIONS_BY_ID: Dict[str, OperationSpec] = {spec.id: spec for spec in OPERATIONS}


def save_report(result: Dict[str, Any], prefix: str,
                reports_dir: Optional[Path] = None) -> Tuple[Optional[Path], Optional[str]]:
    """Write ``result`` as ``SHIELD-<prefix>-<timestamp>.json``; never overwrites."""
    folder = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    try:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"SHIELD-{prefix}-{stamp}.json"
        counter = 1
        while path.exists():
            path = folder / f"SHIELD-{prefix}-{stamp}-{counter}.json"
            counter += 1
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return path, None
    except OSError as exc:
        LOGGER.error("report save failed: %s", exc)
        return None, f"{type(exc).__name__}: {exc}"


def execute(spec: OperationSpec, params: Dict[str, Any],
            on_progress: Callable[[str, int, int, Optional[str]], None],
            token: Optional[CancelToken] = None,
            reports_dir: Optional[Path] = None) -> RunOutcome:
    """Run ``spec`` with live progress and cooperative cancellation, then save."""
    token = token or CancelToken()

    def progress(stage: str, done: int, total: int, detail: Optional[str] = None) -> None:
        token.check()
        try:
            on_progress(str(stage), int(done or 0), int(total or 0), detail)
        except Exception as exc:  # the UI must never break a run
            LOGGER.debug("progress display failed: %s", exc)

    token.check()
    started = time.monotonic()
    result = spec.runner(dict(params), progress)
    token.check()
    elapsed = time.monotonic() - started
    if spec.self_saving:
        raw = result.get("report_path")
        return RunOutcome(result, Path(raw) if raw else None,
                          None if raw else "the report generator did not save a file", elapsed)
    path, error = save_report(result, spec.report_prefix, reports_dir)
    return RunOutcome(result, path, error, elapsed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_operations.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/tui/operations.py tests/tui/test_operations.py
git commit -m "feat(tui): operation registry with cancellable execute() and safe saving"
```

---

### Task 5: Theme and visual renderables

**Files:**
- Create: `src/tui/theme.py`, `src/tui/visuals.py`
- Test: `tests/tui/test_visuals.py`

**Interfaces:**
- Produces (`theme.py`): `PALETTE: dict[str, str]`; `TONE_COLORS: dict[str, tuple[str, str]]` (bright, deep); `SEVERITY_COLORS: dict[str, str]`; `SEVERITY_ORDER = ("CRITICAL","HIGH","MEDIUM","LOW","INFO")`; `SHIELD_THEME: textual.theme.Theme` named `"shield"`.
- Produces (`visuals.py`): `LOGO: list[str]`; `lerp_color(a, b, t) -> str`; `gradient_text(text, start, end, bold=True) -> Text`; `logo_text(phase: float) -> Text`; `banner_text(verdict: str, tone: str, note: str, width: int) -> Text`; `bar(fraction: float, width: int, color: str) -> Text`; `risk_gauge(risk: float | None, width: int) -> Text`; `severity_bar(counts: Mapping[str, int], width: int) -> Text`; `labelled_bars(rows: Sequence[tuple[str, float, str, str]], width: int) -> Text` (label, fraction 0..1, color, value text).

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_visuals.py`:

```python
"""Visual renderables fill their width exactly and degrade on empty data."""
from __future__ import annotations

from src.tui.theme import SEVERITY_COLORS, SHIELD_THEME
from src.tui.visuals import (LOGO, banner_text, bar, gradient_text, labelled_bars, lerp_color,
                             logo_text, risk_gauge, severity_bar)


def test_lerp_color_endpoints():
    assert lerp_color("#000000", "#ffffff", 0.0) == "#000000"
    assert lerp_color("#000000", "#ffffff", 1.0) == "#ffffff"
    assert lerp_color("#000000", "#ffffff", 0.5) == "#808080"


def test_gradient_text_colours_change_across_the_text():
    text = gradient_text("SHIELD", "#22d3ee", "#a78bfa")
    assert text.plain == "SHIELD"
    styles = {str(span.style) for span in text.spans}
    assert len(styles) > 1


def test_logo_text_has_every_line():
    assert logo_text(0.3).plain.count("\n") == len(LOGO) - 1


def test_bar_is_exact_width():
    for fraction in (0.0, 0.33, 0.5, 1.0, 1.7, -1):
        assert len(bar(fraction, 20, "#ff0000").plain) == 20


def test_risk_gauge():
    assert "0.82" in risk_gauge(0.82, 40).plain
    assert "n/a" in risk_gauge(None, 40).plain


def test_banner_is_three_full_lines():
    lines = banner_text("COMPROMISED", "danger", "7 findings", 60).plain.split("\n")
    assert len(lines) == 3 and all(len(line) == 60 for line in lines)
    assert "C O M P R O M I S E D" in lines[1]


def test_severity_bar_legend_and_empty():
    plain = severity_bar({"CRITICAL": 2, "LOW": 6}, 40).plain
    assert "CRITICAL 2" in plain and "LOW 6" in plain
    assert "no findings" in severity_bar({}, 40).plain
    assert set(SEVERITY_COLORS) >= {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_labelled_bars():
    plain = labelled_bars([("contributor_alpha", 0.9, "#f00", "0.90"),
                           ("bravo", 0.1, "#0f0", "0.10")], 50).plain
    assert "contributor_alpha" in plain and "0.10" in plain
    assert labelled_bars([], 50).plain == ""


def test_theme_is_dark_and_named():
    assert SHIELD_THEME.name == "shield" and SHIELD_THEME.dark
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_visuals.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.theme'`.

- [ ] **Step 3: Implement `src/tui/theme.py`**

```python
"""Colours for the SHIELD Console."""

from __future__ import annotations

from textual.theme import Theme

PALETTE = {
    "cyan": "#22D3EE", "violet": "#A78BFA", "bg": "#0A0E14", "surface": "#111722",
    "panel": "#182030", "fg": "#E6EDF3", "muted": "#7D8590", "track": "#232B3A",
    "ok": "#3FB950", "warn": "#F0B429", "danger": "#F85149", "info": "#58A6FF",
}

TONE_COLORS = {
    "danger": ("#FF5D5D", "#7A1020"),
    "warn": ("#FFC24B", "#7A4A00"),
    "ok": ("#4ADE80", "#0F5A2E"),
    "info": ("#60A5FA", "#1E3A8A"),
}

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SEVERITY_COLORS = {"CRITICAL": "#F85149", "HIGH": "#FB8F44", "MEDIUM": "#F0B429",
                   "LOW": "#58A6FF", "INFO": "#7D8590"}

SHIELD_THEME = Theme(
    name="shield", primary=PALETTE["cyan"], secondary=PALETTE["violet"],
    accent=PALETTE["violet"], foreground=PALETTE["fg"], background=PALETTE["bg"],
    surface=PALETTE["surface"], panel=PALETTE["panel"], success=PALETTE["ok"],
    warning=PALETTE["warn"], error=PALETTE["danger"], dark=True)
```

- [ ] **Step 4: Implement `src/tui/visuals.py`**

```python
"""Pure Rich renderables for the console: gradients, bars, gauges, the logo.

Everything here is width-explicit and UI-free, so it is unit-testable.
"""

from __future__ import annotations

import math
from typing import List, Mapping, Optional, Sequence, Tuple

from rich.text import Text

from src.tui.theme import PALETTE, SEVERITY_COLORS, SEVERITY_ORDER, TONE_COLORS

LOGO: List[str] = [
    "███████╗██╗  ██╗██╗███████╗██╗     ██████╗ ",
    "██╔════╝██║  ██║██║██╔════╝██║     ██╔══██╗",
    "███████╗███████║██║█████╗  ██║     ██║  ██║",
    "╚════██║██╔══██║██║██╔══╝  ██║     ██║  ██║",
    "███████║██║  ██║██║███████╗███████╗██████╔╝",
    "╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝ ",
]
_EIGHTHS = " ▏▎▍▌▋▊▉"


def lerp_color(a: str, b: str, t: float) -> str:
    """Blend two ``#rrggbb`` colours."""
    t = min(1.0, max(0.0, t))
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def gradient_text(text: str, start: str, end: str, bold: bool = True) -> Text:
    """Colour ``text`` left-to-right from ``start`` to ``end``."""
    out = Text()
    span = max(1, len(text) - 1)
    for i, char in enumerate(text):
        out.append(char, style=f"{'bold ' if bold else ''}{lerp_color(start, end, i / span)}")
    return out


def logo_text(phase: float = 0.0) -> Text:
    """The SHIELD logo with a gradient that sweeps as ``phase`` grows."""
    width = max(len(line) for line in LOGO)
    out = Text()
    for row, line in enumerate(LOGO):
        for col, char in enumerate(line):
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * (col / width - phase) + row * 0.25)
            out.append(char, style=f"bold {lerp_color(PALETTE['cyan'], PALETTE['violet'], wave)}")
        if row < len(LOGO) - 1:
            out.append("\n")
    return out


def banner_text(verdict: str, tone: str, note: str, width: int) -> Text:
    """Three full-width lines on a gradient background, verdict letter-spaced."""
    width = max(10, width)
    bright, deep = TONE_COLORS.get(tone, TONE_COLORS["info"])
    rows = ["", " ".join(verdict.upper()), note]
    out = Text()
    for index, content in enumerate(rows):
        line = content[:width].center(width)
        for col, char in enumerate(line):
            bg = lerp_color(deep, bright, abs(col / max(1, width - 1) - 0.5) * 2 * 0.55)
            style = f"bold #FFFFFF on {bg}" if index == 1 else f"#F2F2F2 on {bg}"
            out.append(char, style=style)
        if index < len(rows) - 1:
            out.append("\n")
    return out


def bar(fraction: float, width: int, color: str) -> Text:
    """A smooth horizontal bar exactly ``width`` cells wide."""
    width = max(1, width)
    fraction = 0.0 if not fraction or fraction < 0 else min(1.0, fraction)
    eighths = int(round(fraction * width * 8))
    full, rem = divmod(eighths, 8)
    out = Text("█" * full, style=color)
    if full < width:
        out.append(_EIGHTHS[rem] if rem else " ", style=f"{color} on {PALETTE['track']}")
        out.append(" " * (width - full - 1), style=f"on {PALETTE['track']}")
    return out


def _risk_color(risk: float) -> str:
    if risk >= 0.75:
        return PALETTE["danger"]
    if risk >= 0.45:
        return PALETTE["warn"]
    return PALETTE["ok"]


def risk_gauge(risk: Optional[float], width: int) -> Text:
    """``RISK ███████▊░░░ 0.82``."""
    if risk is None:
        return Text("RISK  n/a", style=PALETTE["muted"])
    color = _risk_color(risk)
    out = Text("RISK  ", style="bold")
    out.append_text(bar(risk, max(4, width - 12), color))
    out.append(f"  {risk:.2f}", style=f"bold {color}")
    return out


def severity_bar(counts: Mapping[str, int], width: int) -> Text:
    """Stacked severity bar plus a legend line."""
    total = sum(int(counts.get(s, 0) or 0) for s in SEVERITY_ORDER)
    if total == 0:
        return Text("no findings", style=PALETTE["muted"])
    out = Text()
    used = 0
    present = [s for s in SEVERITY_ORDER if int(counts.get(s, 0) or 0) > 0]
    for index, sev in enumerate(present):
        cells = width - used if index == len(present) - 1 else \
            max(1, round(width * int(counts[sev]) / total))
        cells = max(0, min(cells, width - used))
        out.append("█" * cells, style=SEVERITY_COLORS[sev])
        used += cells
    out.append("\n")
    for sev in present:
        out.append("■ ", style=SEVERITY_COLORS[sev])
        out.append(f"{sev} {int(counts[sev])}   ")
    return out


def labelled_bars(rows: Sequence[Tuple[str, float, str, str]], width: int) -> Text:
    """One ``label  bar  value`` line per row."""
    if not rows:
        return Text("")
    label_w = min(24, max(len(r[0]) for r in rows))
    value_w = max(len(r[3]) for r in rows)
    bar_w = max(6, width - label_w - value_w - 4)
    out = Text()
    for index, (label, fraction, color, value) in enumerate(rows):
        out.append(label[:label_w].ljust(label_w) + "  ")
        out.append_text(bar(fraction, bar_w, color))
        out.append("  " + value.rjust(value_w), style=f"bold {color}")
        if index < len(rows) - 1:
            out.append("\n")
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_visuals.py -q`
Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/tui/theme.py src/tui/visuals.py tests/tui/test_visuals.py
git commit -m "feat(tui): SHIELD theme and gradient/bar/gauge renderables"
```

---

### Task 6: App shell — splash, home, modals, launch entry point

**Files:**
- Create: `src/tui/app.py`, `src/tui/app.tcss`, `src/tui/__main__.py`, `src/tui/system.py`, `src/tui/commands.py`
- Create: `src/tui/widgets/__init__.py`, `src/tui/widgets/tile.py`, `src/tui/widgets/sized.py`
- Create: `src/tui/screens/__init__.py`, `src/tui/screens/modals.py`, `src/tui/screens/splash.py`, `src/tui/screens/home.py`
- Modify: `src/tui/__init__.py` (add `launch()`), `shield.py` (replace with launcher), `shield.bat` (start passes args; `--flags` open console; help text)
- Test: `tests/tui/test_app_home.py`

**Interfaces:**
- Consumes: `OPERATIONS_BY_ID`, `OperationSpec` (Task 4); `recent_reports`, `RecentItem`, `age_of`, `load_report` (Task 3); `op_id_for` (Task 3); `logo_text`, `gradient_text` (Task 5); `SHIELD_THEME`, `TONE_COLORS`, `PALETTE` (Task 5).
- Produces:
  - `ShieldApp(splash: bool = True, discovery_roots: Sequence[Path] | None = None, reports_dir: Path | None = None, operations: Mapping[str, OperationSpec] | None = None)` with attributes `discovery_roots`, `reports_dir`, `operations`; methods `open_operation(op_id: str) -> None`, `open_report(path: Path) -> None`, `show_result(op_id: str, result: dict, report_path: Path | None, elapsed: float | None = None) -> None`, `go_home() -> None`, `action_launch(key: str) -> None`, `action_help() -> None`, `running_screen() -> Screen | None`.
  - `main(argv: Sequence[str] | None = None) -> int`; `src.tui.launch(argv=None) -> int`.
  - Screens: `SplashScreen`, `HomeScreen`, `ConfirmModal(message: str) -> ModalScreen[bool]`, `BrowseModal(kind: str) -> ModalScreen[Path | None]` (kind ∈ dataset/model/records/folder), `HelpModal`, `TooSmallScreen`.
  - Widgets: `Tile(spec, ascii_only=False)` posting `Tile.Chosen(op_id)`; `Sized(draw: Callable[[int], RenderableType])` with `.set_draw(fn)`.
  - `system.open_path(path: Path) -> str | None` (error text or None).
  - Tasks 7–10 add `OperationScreen`, `RunScreen`, `ResultsScreen`, `AgentsScreen`. `ShieldApp` imports them lazily inside `open_operation` / `start_run` / `show_result`, so this task's tests pass before those modules exist.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_app_home.py`:

```python
"""Home screen navigation, splash, recent panel, small-terminal guard."""
from __future__ import annotations

import json
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.screens.home import HomeScreen
from src.tui.screens.modals import TooSmallScreen
from src.tui.screens.splash import SplashScreen


def _app(tmp_path: Path, **kw) -> ShieldApp:
    return ShieldApp(splash=kw.pop("splash", False), discovery_roots=[tmp_path],
                     reports_dir=tmp_path / "reports", **kw)


@async_test
async def test_home_has_six_tiles_and_arrow_navigation(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        tiles = list(app.screen.query(".tile"))
        assert [t.id for t in tiles] == ["tile-scan", "tile-audit", "tile-verify",
                                         "tile-drift", "tile-agents", "tile-report"]
        assert app.focused.id == "tile-scan"
        await pilot.press("right")
        assert app.focused.id == "tile-audit"
        await pilot.press("down")
        assert app.focused.id == "tile-agents"
        await pilot.press("left", "left", "left")
        assert app.focused.id == "tile-drift"


@async_test
async def test_splash_skips_on_any_key(tmp_path):
    app = _app(tmp_path, splash=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)
        await pilot.press("x")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


@async_test
async def test_recent_panel_lists_reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "SHIELD-SCAN-1.json").write_text(json.dumps(
        {"module": "data_scanner", "target": "poisoned", "dataset": {"num_samples": 3},
         "summary": {"verdict": "COMPROMISED", "risk_score": 0.8}}), encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.screen.query_one("#recent").option_count == 1)


@async_test
async def test_small_terminal_shows_notice_and_recovers(tmp_path):
    app = _app(tmp_path, splash=True)
    async with app.run_test(size=(70, 20)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, TooSmallScreen))
        await pilot.resize_terminal(120, 36)
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


@async_test
async def test_help_modal_opens_and_closes(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        await pilot.press("question_mark")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HelpModal")
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))


def test_launch_without_tty_prints_hint(capsys, monkeypatch):
    import src.tui.app as app_module
    monkeypatch.setattr(app_module.sys.stdout, "isatty", lambda: False, raising=False)
    assert app_module.main([]) == 2
    assert "shield scan" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_app_home.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.app'`.

- [ ] **Step 3: Implement `src/tui/system.py`**

```python
"""Hand a file to the operating system's own viewer (local only)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def open_path(path: Path) -> Optional[str]:
    """Open ``path`` in the default local application; return an error or ``None``."""
    try:
        if not Path(path).exists():
            return f"not found: {path}"
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return None
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"
```

- [ ] **Step 4: Implement widgets `tile.py`, `sized.py`, `widgets/__init__.py`**

`src/tui/widgets/__init__.py`:

```python
"""Reusable SHIELD Console widgets."""
```

`src/tui/widgets/sized.py`:

```python
"""Host a renderable that needs to know its width (bars, gauges, banners)."""

from __future__ import annotations

from typing import Callable

from rich.console import RenderableType
from textual.widget import Widget


class Sized(Widget):
    """Calls ``draw(width)`` on every render."""

    DEFAULT_CSS = "Sized { height: auto; }"

    def __init__(self, draw: Callable[[int], RenderableType], **kwargs) -> None:
        super().__init__(**kwargs)
        self._draw = draw

    def set_draw(self, draw: Callable[[int], RenderableType]) -> None:
        """Replace the drawing function and repaint."""
        self._draw = draw
        self.refresh(layout=True)

    def render(self) -> RenderableType:
        return self._draw(max(10, self.size.width or 80))
```

`src/tui/widgets/tile.py`:

```python
"""A home-screen operation tile."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget

from src.tui.operations import OperationSpec
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text


class Tile(Widget, can_focus=True):
    """Focusable card that opens one operation."""

    BINDINGS = [Binding("enter", "choose", "Open", show=False)]

    class Chosen(Message):
        """The operator picked this tile."""

        def __init__(self, op_id: str) -> None:
            self.op_id = op_id
            super().__init__()

    def __init__(self, spec: OperationSpec, ascii_only: bool = False) -> None:
        super().__init__(id=f"tile-{spec.id}", classes="tile")
        self.spec = spec
        self.ascii_only = ascii_only

    def render(self) -> Text:
        icon = self.spec.ascii_icon if self.ascii_only else self.spec.icon
        out = Text()
        out.append_text(gradient_text(f"{icon}  {self.spec.title.upper()}",
                                      PALETTE["cyan"], PALETTE["violet"]))
        out.append(f"\n{self.spec.blurb}\n", style=PALETTE["muted"])
        out.append(f" {self.spec.hotkey} ", style=f"bold {PALETTE['bg']} on {PALETTE['cyan']}")
        return out

    def action_choose(self) -> None:
        self.post_message(self.Chosen(self.spec.id))

    def on_click(self) -> None:
        self.action_choose()
```

- [ ] **Step 5: Implement `src/tui/screens/modals.py`**

```python
"""Small screens: confirm, browse, help, and the too-small notice."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DirectoryTree, Input, Label, Static

from src.tui.discovery import ROOT, classify

KIND_WORDS = {"dataset": "a dataset folder", "model": "a model file (.pt/.pth/.onnx)",
              "records": "a record chain (.json/.jsonl)", "folder": "a folder"}


class ConfirmModal(ModalScreen[bool]):
    """Yes / No question."""

    BINDINGS = [Binding("y", "answer(True)", "Yes"), Binding("n", "answer(False)", "No"),
                Binding("escape", "answer(False)", "No")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm", classes="modal"):
            yield Label(self.message, id="confirm-text")
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes  y", id="yes", variant="error")
                yield Button("No  n", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class BrowseModal(ModalScreen[Optional[Path]]):
    """Pick any folder or file from a tree; validates the kind before accepting."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, kind: str, start: Optional[Path] = None) -> None:
        super().__init__()
        self.kind = kind
        self.start = start or ROOT
        self.current: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="browse", classes="modal"):
            yield Label(f"Choose {KIND_WORDS.get(self.kind, self.kind)}", classes="modal-title")
            yield Input(placeholder="Jump to a folder: paste a path and press Enter",
                        id="browse-path")
            yield DirectoryTree(str(self.start), id="browse-tree")
            yield Static("", id="browse-hint")
            with Horizontal(classes="modal-buttons"):
                yield Button("Select", id="select", variant="primary", disabled=True)
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(DirectoryTree).focus()

    def _validate(self, path: Path) -> Optional[str]:
        if self.kind == "folder":
            return None if path.is_dir() else "Pick a folder."
        found = classify(path)
        return None if found == self.kind else \
            f"{path.name} is not {KIND_WORDS.get(self.kind, self.kind)}."

    def _set_current(self, path: Path) -> None:
        self.current = path
        problem = self._validate(path)
        hint = self.query_one("#browse-hint", Static)
        hint.update(f"[red]{problem}[/red]" if problem else f"[green]✓ {path}[/green]")
        self.query_one("#select", Button).disabled = problem is not None

    def on_tree_node_highlighted(self, event: DirectoryTree.NodeHighlighted) -> None:
        data = event.node.data
        if data is not None and getattr(data, "path", None) is not None:
            self._set_current(Path(data.path))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._set_current(Path(event.path))
        if self._validate(Path(event.path)) is None:
            self.dismiss(Path(event.path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = Path(event.value.strip().strip('"').strip("'"))
        if path.is_dir():
            self.query_one(DirectoryTree).path = path
            self._set_current(path)
        elif path.is_file():
            self._set_current(path)
        else:
            self.query_one("#browse-hint", Static).update(f"[red]Not found: {path}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select" and self.current is not None:
            self.dismiss(self.current)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


HELP_KEYS = [
    ("Home", "←↑↓→ move · Enter open · d m v f a r jump to an operation"),
    ("Anywhere", "Ctrl+P command palette · ? help · q quit · Esc back"),
    ("Pick target", "↑↓ choose · / filter · Browse… any folder or file"),
    ("Operation", "Ctrl+R run"),
    ("Running", "Esc cancel (asks first)"),
    ("Error", "r retry · b back · t show traceback"),
    ("Results", "f filter severity · o open file · s saved path · e export · Esc home"),
]


class HelpModal(ModalScreen[None]):
    """Key reference."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        for where, keys in HELP_KEYS:
            table.add_row(where, keys)
        with Vertical(id="help", classes="modal"):
            yield Label("SHIELD Console — keys", classes="modal-title")
            yield Static(table)

    def action_close(self) -> None:
        self.dismiss(None)


class TooSmallScreen(Screen):
    """Shown while the terminal is below 80×24."""

    def compose(self) -> ComposeResult:
        yield Static("", id="too-small")

    def on_mount(self) -> None:
        self.update_size(self.app.size.width, self.app.size.height)

    def update_size(self, width: int, height: int) -> None:
        self.query_one("#too-small", Static).update(
            f"[bold]Enlarge the window to at least 80×24[/bold]\n[dim]now {width}×{height}[/dim]")
```

- [ ] **Step 6: Implement `src/tui/screens/splash.py`**

```python
"""One-second animated logo on launch."""

from __future__ import annotations

import time

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import Static

from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text, logo_text


class SplashScreen(Screen):
    """Gradient sweep over the logo; any key skips."""

    DURATION = 1.1

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(id="splash-logo")
            with Center():
                yield Static(id="splash-line")

    def on_mount(self) -> None:
        self._closed = False
        self._started = time.monotonic()
        self._timer = self.set_interval(1 / 24, self._tick)
        self._tick()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        phase = min(1.0, elapsed / self.DURATION)
        self.query_one("#splash-logo", Static).update(logo_text(phase))
        filled = int(phase * 24)
        line = Text("▰" * filled, style=PALETTE["cyan"])
        line.append("▱" * (24 - filled), style=PALETTE["muted"])
        line.append("  ")
        line.append_text(gradient_text("verifying integrity · offline · CPU-only",
                                       PALETTE["cyan"], PALETTE["violet"], bold=False))
        self.query_one("#splash-line", Static).update(line)
        if elapsed >= self.DURATION:
            self._close()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.app.pop_screen()
```

- [ ] **Step 7: Implement `src/tui/screens/home.py`**

```python
"""Command-center home: six tiles, recent results, launchers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, OptionList, Static
from textual.widgets.option_list import Option

from src.tui.operations import OPERATIONS
from src.tui.recent import RecentItem, age_of, recent_reports
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.visuals import gradient_text
from src.tui.widgets.tile import Tile

COLUMNS = 3


class HomeScreen(Screen):
    """Pick an operation."""

    BINDINGS = [
        Binding("left", "move(-1, 0)", show=False), Binding("right", "move(1, 0)", show=False),
        Binding("up", "move(0, -1)", show=False), Binding("down", "move(0, 1)", show=False),
        *[Binding(s.hotkey, f"app.open_operation('{s.id}')", s.title, show=False)
          for s in OPERATIONS],
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="home-header")
        with Horizontal(id="home-body"):
            with Grid(id="tiles"):
                for spec in self.app.operations.values():
                    yield Tile(spec, ascii_only=self.app.ascii_only)
            with Vertical(id="home-side"):
                yield Label("Recent results", classes="section-title")
                yield OptionList(id="recent")
                yield Label("Launch", classes="section-title")
                yield Button("↗ Dashboard", name="dashboard", classes="launcher")
                yield Button("↗ Attack Lab", name="lab", classes="launcher")
                yield Button("↗ Guided demo", name="demo", classes="launcher")
        yield Footer()

    def on_mount(self) -> None:
        self._update_header()
        self.set_interval(30, self._update_header)
        self.query(Tile).first().focus()
        self._load_recent()

    def on_screen_resume(self) -> None:
        self._load_recent()

    def _update_header(self) -> None:
        line = gradient_text("◆ SHIELD-CV · Integrity Console", PALETTE["cyan"], PALETTE["violet"])
        line.append(f"     offline ● CPU-only ● {datetime.now():%d %b %H:%M}",
                    style=PALETTE["muted"])
        self.query_one("#home-header", Static).update(line)

    @work(thread=True, exclusive=True, group="recent")
    def _load_recent(self) -> None:
        items = recent_reports(5, self.app.reports_dir)
        self.app.call_from_thread(self._show_recent, items)

    def _show_recent(self, items: List[RecentItem]) -> None:
        recent = self.query_one("#recent", OptionList)
        recent.clear_options()
        if not items:
            recent.add_option(Option(Text("No reports yet — run a check", style="dim"),
                                     id="__none__", disabled=True))
            return
        for item in items:
            label = Text()
            label.append(f"{item.kind:<7}", style="bold")
            label.append(f"{item.target[:18]:<19}")
            label.append(f" {item.verdict[:12]} ", style=f"bold #000000 on {TONE_COLORS[item.tone][0]}")
            label.append(f"  {age_of(item)}", style="dim")
            recent.add_option(Option(label, id=str(item.path)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id and event.option.id != "__none__":
            self.app.open_report(Path(event.option.id))

    def on_tile_chosen(self, message: Tile.Chosen) -> None:
        self.app.open_operation(message.op_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name:
            self.app.action_launch(event.button.name)

    def action_move(self, dx: int, dy: int) -> None:
        tiles = list(self.query(Tile))
        if self.focused not in tiles:
            tiles[0].focus()
            return
        index = tiles.index(self.focused)
        col, row = index % COLUMNS + dx, index // COLUMNS + dy
        rows = (len(tiles) + COLUMNS - 1) // COLUMNS
        col, row = max(0, min(COLUMNS - 1, col)), max(0, min(rows - 1, row))
        tiles[min(len(tiles) - 1, row * COLUMNS + col)].focus()
```

- [ ] **Step 8: Implement `src/tui/commands.py`**

```python
"""Command palette: operations, quick-start targets, recent reports, launchers."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import List, Tuple

from textual.command import Hit, Hits, Provider

from src.tui.discovery import discover
from src.tui.recent import recent_reports

QUICK = (("scan", "dataset", "Scan"), ("audit", "model", "Audit"), ("verify", "records", "Verify"))
LAUNCH = (("dashboard", "Launch Streamlit dashboard"), ("lab", "Launch Attack Lab"),
          ("demo", "Launch guided demo"))


class ShieldCommands(Provider):
    """Everything the console can do, fuzzy-searchable."""

    async def startup(self) -> None:
        roots = getattr(self.app, "discovery_roots", None)
        self._quick: List[Tuple[str, str, str]] = []
        for op_id, kind, verb in QUICK:
            found = await asyncio.to_thread(discover, kind, roots)
            self._quick += [(op_id, f"{verb} {c.label}", str(c.path)) for c in found]
        self._recent = await asyncio.to_thread(recent_reports, 5, self.app.reports_dir)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = self.app
        entries = [(f"Open: {s.title}", partial(app.open_operation, s.id), s.blurb)
                   for s in app.operations.values()]
        entries += [(text, partial(app.quick_run, op_id, path), "Run now with default options")
                    for op_id, text, path in getattr(self, "_quick", [])]
        entries += [(f"Open report: {r.kind} {r.target} {r.verdict}",
                     partial(app.open_report, r.path), str(r.path))
                    for r in getattr(self, "_recent", [])]
        entries += [(text, partial(app.action_launch, key), "Leaves the console until you exit")
                    for key, text in LAUNCH]
        for text, callback, help_text in entries:
            score = matcher.match(text)
            if score > 0:
                yield Hit(score, matcher.highlight(text), callback, help=help_text)
```

- [ ] **Step 9: Implement `src/tui/app.py`**

```python
"""SHIELD Console application."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from textual.app import App
from textual.binding import Binding
from textual.screen import Screen

try:  # must be imported before the app starts: it queries the terminal once
    import textual_image.widget  # noqa: F401
except Exception:  # pragma: no cover - preview falls back to a message
    pass

from src.tui.commands import ShieldCommands
from src.tui.discovery import ROOT
from src.tui.operations import OPERATIONS_BY_ID, OperationSpec
from src.tui.recent import load_report
from src.tui.screens.home import HomeScreen
from src.tui.screens.modals import ConfirmModal, HelpModal, TooSmallScreen
from src.tui.screens.splash import SplashScreen
from src.tui.theme import SHIELD_THEME
from src.tui.verdict import op_id_for
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)
MIN_SIZE = (80, 24)
LAUNCHERS = {
    "dashboard": ("Streamlit dashboard", [sys.executable, "-m", "streamlit", "run", "src/dashboard.py"]),
    "lab": ("Attack Lab", [sys.executable, "demo/attack_lab.py"]),
    "demo": ("Guided demo", [sys.executable, "demo/run_demo.py", "--quick"]),
}
NO_TTY_HINT = ("SHIELD Console needs an interactive terminal.\n"
               "For scripts and CI use the one-shot commands, e.g.:  shield scan <path>\n"
               "See:  shield help")


class ShieldApp(App):
    """Full-screen SHIELD-CV console."""

    CSS_PATH = "app.tcss"
    TITLE = "SHIELD-CV"
    COMMANDS = App.COMMANDS | {ShieldCommands}
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("question_mark", "help", "Help"),
                Binding("ctrl+p", "command_palette", "Palette")]

    def __init__(self, splash: bool = True, discovery_roots: Optional[Sequence[Path]] = None,
                 reports_dir: Optional[Path] = None,
                 operations: Optional[Mapping[str, OperationSpec]] = None) -> None:
        super().__init__()
        self.splash = splash
        # Set SHIELD_ASCII=1 on consoles whose font lacks the tile glyphs (▣ ◉ ⛓ ⚇).
        self.ascii_only = os.environ.get("SHIELD_ASCII") == "1"
        self.discovery_roots = list(discovery_roots) if discovery_roots is not None else None
        self.reports_dir = reports_dir
        self.operations: Mapping[str, OperationSpec] = operations or OPERATIONS_BY_ID

    # -- lifecycle ---------------------------------------------------------
    def on_mount(self) -> None:
        self.register_theme(SHIELD_THEME)
        self.theme = "shield"
        self.push_screen(HomeScreen())
        if self.splash and not self._is_small(self.size.width, self.size.height):
            self.push_screen(SplashScreen())
        self._check_size(self.size.width, self.size.height)

    def on_resize(self, event: Any) -> None:
        self._check_size(event.size.width, event.size.height)

    @staticmethod
    def _is_small(width: int, height: int) -> bool:
        return width < MIN_SIZE[0] or height < MIN_SIZE[1]

    def _check_size(self, width: int, height: int) -> None:
        small = self._is_small(width, height)
        if small and isinstance(self.screen, SplashScreen):
            self.pop_screen()
        if small and not isinstance(self.screen, TooSmallScreen):
            self.push_screen(TooSmallScreen())
        elif small:
            self.screen.update_size(width, height)
        elif isinstance(self.screen, TooSmallScreen):
            self.pop_screen()

    # -- navigation --------------------------------------------------------
    def go_home(self) -> None:
        while len(self.screen_stack) > 1 and not isinstance(self.screen, HomeScreen):
            self.pop_screen()

    def open_operation(self, op_id: str) -> None:
        from src.tui.screens.operation import OperationScreen
        self.push_screen(OperationScreen(self.operations[op_id]))

    def quick_run(self, op_id: str, target: str) -> None:
        from src.tui.screens.operation import default_params
        spec = self.operations[op_id]
        self.start_run(spec, {**default_params(spec), "target": Path(target)})

    def start_run(self, spec: OperationSpec, params: Dict[str, Any]) -> None:
        from src.tui.screens.agents import AgentsScreen
        from src.tui.screens.run import RunScreen
        self.push_screen(AgentsScreen(spec, params) if spec.id == "agents"
                         else RunScreen(spec, params))

    def show_result(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                    elapsed: Optional[float] = None, replace: bool = False) -> None:
        from src.tui.screens.agents import AgentsScreen
        from src.tui.screens.results import ResultsScreen
        screen: Screen = (AgentsScreen(self.operations["agents"], None, result=result)
                          if op_id == "agents" else
                          ResultsScreen(op_id, result, report_path, elapsed))
        if replace:
            self.switch_screen(screen)
        else:
            self.push_screen(screen)

    def open_report(self, path: Path) -> None:
        try:
            data = load_report(Path(path))
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        op_id = op_id_for(data)
        if op_id is None:
            self.notify(f"Not a SHIELD report: {Path(path).name}", severity="error")
            return
        self.show_result(op_id, data, Path(path))

    # -- actions -----------------------------------------------------------
    def action_help(self) -> None:
        if not isinstance(self.screen, HelpModal):
            self.push_screen(HelpModal())

    def running_screen(self) -> Optional[Screen]:
        for screen in self.screen_stack:
            if getattr(screen, "is_running", False):
                return screen
        return None

    @property
    def is_running(self) -> bool:
        """Whether any check is in progress."""
        return self.running_screen() is not None

    async def action_quit(self) -> None:
        running = self.running_screen()
        if running is None:
            self.exit()
            return

        def answer(stop: Optional[bool]) -> None:
            if stop:
                running.token.cancel()
                self.exit()

        self.push_screen(ConfirmModal("A check is running — stop it and quit?"), answer)

    def action_launch(self, key: str) -> None:
        title, command = LAUNCHERS[key]
        try:
            with self.suspend():
                print(f"\n  Launching {title} — press Ctrl+C to return to SHIELD Console.\n")
                try:
                    subprocess.call(command, cwd=str(ROOT))
                except KeyboardInterrupt:
                    pass
        except Exception as exc:
            LOGGER.error("launch %s failed: %s", key, exc)
            self.notify(f"Could not launch {title}: {exc}", severity="error")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the console; returns a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not sys.stdout.isatty():
        print(NO_TTY_HINT)
        return 2
    from src.utils.stdio import ensure_utf8_stdio
    ensure_utf8_stdio()
    ShieldApp(splash="--no-splash" not in args).run()
    return 0
```

- [ ] **Step 10: Implement `src/tui/__init__.py` launch, `__main__.py`, and the launcher**

Replace `src/tui/__init__.py`:

```python
"""SHIELD Console — full-screen terminal UI for SHIELD-CV."""

from __future__ import annotations

from typing import Optional, Sequence

MISSING_DEPS_HINT = """\
SHIELD Console could not start: {error}

It needs the 'textual' and 'textual-image' packages.
  Offline install:  pip install --no-index --find-links wheels/ -r requirements.txt
Scripted checks still work without them:  shield scan <path>   (see: shield help)
"""


def launch(argv: Optional[Sequence[str]] = None) -> int:
    """Start the console, or explain what is missing."""
    try:
        from src.tui.app import main
    except ImportError as exc:
        print(MISSING_DEPS_HINT.format(error=exc))
        return 2
    return main(argv)
```

`src/tui/__main__.py`:

```python
"""``python -m src.tui`` starts the SHIELD Console."""

import sys

from src.tui import launch

sys.exit(launch())
```

Replace all of `shield.py` with:

```python
#!/usr/bin/env python3
"""SHIELD-CV interactive console.

Run:  python shield.py [--no-splash]      (or just `shield`)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tui import launch  # noqa: E402

if __name__ == "__main__":
    sys.exit(launch())
```

In `shield.bat`, with the Edit tool (preserve the user's other uncommitted edits):
- change `if /i "%CMD%"=="start"      ( python shield.py & goto :eof )` → `if /i "%CMD%"=="start"      ( python shield.py %ARGS% & goto :eof )`
- after the two `--help` / `help` lines add: `if "%CMD:~0,2%"=="--" ( python shield.py %CMD% %ARGS% & goto :eof )`
- in `:help`, change `echo  shield                 Open interactive mode` → `echo  shield                 Open SHIELD Console (full-screen)` and `echo  shield start           Open interactive mode` → `echo  shield start           Open SHIELD Console ( --no-splash to skip intro )`
- in the header comment change `->  open interactive mode` lines to `-> open SHIELD Console`.

- [ ] **Step 11: Implement `src/tui/app.tcss`** (complete stylesheet for all screens, including ones added in Tasks 7–10)

```css
Screen { background: $background; }

/* -- home ---------------------------------------------------------------- */
#home-header { height: 1; padding: 0 2; margin: 1 0; }
#home-body { height: 1fr; padding: 0 1; }
#tiles { grid-size: 3; grid-gutter: 1 2; width: 3fr; height: auto; }
.tile {
    height: 7; padding: 1 2; border: round $panel-lighten-2; background: $surface;
}
.tile:focus { border: heavy $primary; background: $panel; }
.tile:hover { border: round $secondary; }
#home-side { width: 2fr; min-width: 34; padding-left: 2; }
.section-title { color: $text-muted; text-style: bold; margin: 1 0 0 0; }
#recent { height: auto; max-height: 9; border: round $panel-lighten-2; background: $surface; }
.launcher { width: 100%; margin-top: 1; }

/* -- modals --------------------------------------------------------------- */
ModalScreen { align: center middle; background: $background 70%; }
.modal { width: 72; height: auto; padding: 1 2; border: thick $primary; background: $surface; }
.modal-title { text-style: bold; color: $primary; margin-bottom: 1; }
.modal-buttons { height: auto; align-horizontal: right; margin-top: 1; }
.modal-buttons Button { margin-left: 2; }
#browse { height: 80%; }
#browse-tree { height: 1fr; border: round $panel-lighten-2; }
#browse-hint { height: 1; margin-top: 1; }
#too-small { width: 100%; height: 100%; content-align: center middle; text-align: center; }

/* -- operation form -------------------------------------------------------- */
#op-header { height: auto; padding: 1 2; }
#op-form { padding: 0 2; }
.field-label { margin-top: 1; text-style: bold; }
TargetPicker { height: auto; }
TargetPicker .picker-filter { display: none; margin-bottom: 0; }
TargetPicker.-filtering .picker-filter { display: block; }
TargetPicker OptionList { height: 10; border: round $panel-lighten-2; background: $surface; }
TargetPicker.-compact OptionList { height: 6; }
TargetPicker OptionList:focus { border: round $primary; }
.picker-hint { height: auto; color: $text-muted; }
.picker-hint.-error { color: $error; }
#op-run-row { height: auto; margin: 1 0 2 0; }
#op-run { min-width: 22; }
#op-problem { color: $warning; padding-left: 2; height: 3; content-align-vertical: middle; }

/* -- run ----------------------------------------------------------------- */
#run-header { height: auto; padding: 1 2; }
StageProgress { height: auto; padding: 0 2; }
.stage-row { height: 1; }
.stage-icon { width: 3; }
.stage-label { width: 34; }
.stage-row ProgressBar { width: 40; }
.stage-detail { width: 1fr; color: $text-muted; padding-left: 2; }
#run-status { height: 1; padding: 0 2; margin-top: 1; color: $text-muted; }
#run-log { height: 1fr; margin: 1 2; border: round $panel-lighten-2; background: $surface; }
#run-error { display: none; height: auto; margin: 0 2; padding: 1 2; border: heavy $error; }
RunScreen.-failed #run-error { display: block; }
#run-trace { display: none; color: $text-muted; }
RunScreen.-trace #run-trace { display: block; }

/* -- results ------------------------------------------------------------- */
#res-banner { height: 3; }
#res-stats { height: 1; padding: 0 2; margin-top: 1; }
#res-gauge { padding: 0 2; }
#res-tabs { height: 1fr; margin-top: 1; }
#findings-pane { height: 1fr; }
FindingsTable { width: 3fr; height: 1fr; }
FindingDetail { width: 2fr; min-width: 36; height: 1fr; padding: 0 1;
                border-left: tall $panel-lighten-2; }
ImagePreview { height: auto; }
ImagePreview Horizontal { height: auto; }
ImagePreview .preview-cell { width: 1fr; height: auto; }
ImagePreview Image { width: auto; height: 12; }
.breakdown-title { margin-top: 1; text-style: bold; color: $text-muted; }
#res-immunity { height: auto; }
#res-immunity Digits { width: auto; color: $primary; }

/* -- agents -------------------------------------------------------------- */
#agent-grid { grid-size: 3; grid-gutter: 1 2; height: auto; padding: 0 2; }
.agent-card { height: 7; padding: 0 1; border: round $panel-lighten-2; background: $surface; }
.agent-card.-finished { border: round $success; }
.agent-card.-error { border: round $error; }
#meeting { height: auto; margin: 1 2; padding: 1 2; border: round $secondary; display: none; }
AgentsScreen.-done #meeting { display: block; }
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_app_home.py -q`
Expected: `6 passed`. If a test fails on an API name (`resize_terminal`, `_bindings.bind`, `NodeHighlighted`), check the installed Textual source under `site-packages/textual/` and use the actual name — do not weaken the test's intent.

- [ ] **Step 13: Run all TUI tests**

Run: `python -m pytest tests/tui -q`
Expected: all pass.

- [ ] **Step 14: Commit**

```bash
git add src/tui shield.py shield.bat tests/tui/test_app_home.py
git commit -m "feat(tui): console shell with splash, command-center home and launcher"
```

---

### Task 7: Operation screen and target picker

**Files:**
- Create: `src/tui/widgets/target_picker.py`, `src/tui/screens/operation.py`
- Test: `tests/tui/test_app_operation.py`

**Interfaces:**
- Consumes: `discover`, `classify`, `Candidate` (Task 2); `OperationSpec`, `OptionSpec` (Task 4); `BrowseModal` (Task 6); `app.start_run(spec, params)` (Task 6).
- Produces:
  - `TargetPicker(kind: str, prefer: str | None = None, optional: bool = False, compact: bool = False, id: str | None = None)`; property `selected: Path | None`; property `loaded: bool`; posts `TargetPicker.Changed(picker, path)`.
  - `OperationScreen(spec: OperationSpec)`; methods `params() -> dict`, `problem() -> str | None`.
  - `default_params(spec: OperationSpec) -> dict` (select/switch defaults only, no targets).

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_app_operation.py`:

```python
"""Pick targets and options without typing; Run is gated on validity."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.operation import OperationScreen, default_params
from src.tui.widgets.target_picker import TargetPicker


def _dataset(root: Path, name: str) -> Path:
    folder = root / name / "contributor_a" / "images"
    folder.mkdir(parents=True)
    (folder / "a.jpg").write_bytes(b"x")
    return root / name


def _model(root: Path, name: str) -> Path:
    (root / "models").mkdir(exist_ok=True)
    path = root / "models" / name
    path.write_bytes(b"0" * 10)
    return path


def _app(tmp_path: Path, started: list) -> ShieldApp:
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    app.start_run = lambda spec, params: started.append((spec.id, params))
    return app


async def _open(pilot, app, key: str) -> OperationScreen:
    await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
    await pilot.press(key)
    await wait_for(pilot, lambda: isinstance(app.screen, OperationScreen))
    await wait_for(pilot, lambda: all(p.loaded for p in app.screen.query(TargetPicker)))
    return app.screen


@async_test
async def test_scan_form_picks_first_dataset_and_runs(tmp_path):
    a = _dataset(tmp_path, "alpha_set")
    _dataset(tmp_path, "beta_set")
    started: list = []
    app = _app(tmp_path, started)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "d")
        assert screen.query_one("#target", TargetPicker).selected == a
        assert screen.problem() is None
        await pilot.press("ctrl+r")
        await wait_for(pilot, lambda: bool(started))
        op_id, params = started[0]
        assert op_id == "scan" and params == {"target": a, "max_images": None}


@async_test
async def test_arrow_changes_selection(tmp_path):
    _dataset(tmp_path, "alpha_set")
    b = _dataset(tmp_path, "beta_set")
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "d")
        screen.query_one("#target OptionList").focus()
        await pilot.press("down")
        assert screen.query_one("#target", TargetPicker).selected == b


@async_test
async def test_no_targets_disables_run(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "m")
        assert screen.query_one("#target", TargetPicker).selected is None
        assert "Pick" in screen.problem()
        assert screen.query_one("#op-run").disabled


@async_test
async def test_audit_options_reference_optional_and_switch(tmp_path):
    m = _model(tmp_path, "suspect.pt")
    started: list = []
    app = _app(tmp_path, started)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "m")
        assert screen.params() == {"target": m, "reference": None, "neural_cleanse": True}


@async_test
async def test_report_requires_a_module_and_pairs_drift(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "r")
        assert "at least one" in screen.problem()


@async_test
async def test_escape_returns_home(tmp_path):
    app = _app(tmp_path, [])
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(pilot, app, "v")
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")


def test_default_params():
    assert default_params(OPERATIONS_BY_ID["drift"]) == {"max_images": 120}
    assert default_params(OPERATIONS_BY_ID["audit"]) == {"neural_cleanse": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_app_operation.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.screens.operation'`.

- [ ] **Step 3: Implement `src/tui/widgets/target_picker.py`**

```python
"""Choose a target from discovered candidates, a filter, or Browse…"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from src.tui.discovery import Candidate, discover, display_label, describe
from src.tui.screens.modals import KIND_WORDS, BrowseModal

NONE_ID = "__none__"
BROWSE_ID = "__browse__"


class TargetPicker(Vertical):
    """Highlighting an entry selects it; Enter on Browse… opens the tree."""

    BINDINGS = [Binding("slash", "filter", "Filter", show=False),
                Binding("escape", "clear_filter", show=False)]

    class Changed(Message):
        """The selected path changed (``None`` = nothing valid selected)."""

        def __init__(self, picker: "TargetPicker", path: Optional[Path]) -> None:
            self.picker = picker
            self.path = path
            super().__init__()

    def __init__(self, kind: str, prefer: Optional[str] = None, optional: bool = False,
                 compact: bool = False, id: Optional[str] = None) -> None:
        super().__init__(id=id, classes="-compact" if compact else "")
        self.kind = kind
        self.prefer = prefer
        self.optional = optional
        self.candidates: List[Candidate] = []
        self._shown: List[Candidate] = []
        self._selected: Optional[Path] = None
        self._loaded = False

    @property
    def selected(self) -> Optional[Path]:
        return self._selected

    @property
    def loaded(self) -> bool:
        return self._loaded

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter…", classes="picker-filter")
        yield OptionList(Option(Text(f"Looking for {KIND_WORDS[self.kind]}…", style="dim"),
                                disabled=True))
        yield Static("", classes="picker-hint")

    def on_mount(self) -> None:
        self._load()

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        found = discover(self.kind, getattr(self.app, "discovery_roots", None))
        self.app.call_from_thread(self._loaded_candidates, found)

    def _loaded_candidates(self, found: List[Candidate]) -> None:
        self.candidates = found
        self._render_options("")
        self._loaded = True
        if not found and not self.optional:
            self._hint(f"No {KIND_WORDS[self.kind]} found nearby — choose Browse… to pick one.",
                       error=False)
        # Always re-announce so the screen re-validates once every picker has loaded.
        self.post_message(self.Changed(self, self._selected))

    def _render_options(self, needle: str) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        self._shown = [c for c in self.candidates if needle.lower() in c.label.lower()]
        if self.optional:
            options.add_option(Option(Text("— none / skip —", style="dim"), id=NONE_ID))
        for index, cand in enumerate(self._shown):
            options.add_option(Option(Text.assemble((cand.label, "bold"), "   ",
                                                    (cand.detail, "dim")), id=str(index)))
        options.add_option(Option(Text("▸ Browse…", style="bold cyan"), id=BROWSE_ID))
        index = self._preferred_index()
        options.highlighted = index
        self._apply(options.get_option_at_index(index).id)

    def _preferred_index(self) -> int:
        offset = 1 if self.optional else 0
        if self._selected is not None:
            for index, cand in enumerate(self._shown):
                if cand.path == self._selected:
                    return index + offset
        if self.prefer:
            for index, cand in enumerate(self._shown):
                if cand.label == self.prefer or cand.label.endswith(self.prefer):
                    return index + offset
        if self.optional or not self._shown:
            return 0
        return offset

    def _set(self, path: Optional[Path]) -> None:
        if path != self._selected:
            self._selected = path
            self.post_message(self.Changed(self, path))

    def _hint(self, text: str, error: bool) -> None:
        hint = self.query_one(".picker-hint", Static)
        hint.update(text)
        hint.set_class(error, "-error")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._apply(event.option.id)

    def _apply(self, option_id: Optional[str]) -> None:
        """Make the option with ``option_id`` the selection."""
        if option_id == BROWSE_ID or option_id is None:
            if not self._shown and not self.optional:
                self._set(None)
            return
        if option_id == NONE_ID:
            self._set(None)
            self._hint("", error=False)
            return
        cand = self._shown[int(option_id)]
        self._set(cand.path)
        self._hint("", error=False)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id == BROWSE_ID:
            self.app.push_screen(BrowseModal(self.kind), self._browsed)

    def _browsed(self, path: Optional[Path]) -> None:
        if path is None:
            return
        cand = Candidate(path=path, kind=self.kind, label=display_label(path),
                         detail=describe(path, self.kind))
        self.candidates = [cand] + [c for c in self.candidates if c.path != path]
        self._selected = None
        self._set(path)
        self._render_options("")

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._render_options(event.value)

    def check_action(self, action: str, parameters: tuple) -> Optional[bool]:
        # Esc only clears an open filter; otherwise it must reach the screen ("back").
        if action == "clear_filter":
            return self.has_class("-filtering")
        return True

    def action_filter(self) -> None:
        self.add_class("-filtering")
        self.query_one(Input).focus()

    def action_clear_filter(self) -> None:
        if self.has_class("-filtering"):
            self.remove_class("-filtering")
            self.query_one(Input).value = ""
            self.query_one(OptionList).focus()
```

- [ ] **Step 4: Implement `src/tui/screens/operation.py`**

```python
"""Target + options form for one operation (also the Full Report checklist)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, Select, Static, Switch

from src.tui.operations import OperationSpec
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text
from src.tui.widgets.target_picker import TargetPicker


def default_params(spec: OperationSpec) -> Dict[str, Any]:
    """Default values for the non-target options of ``spec``."""
    return {o.key: o.default for o in spec.options if o.kind in ("select", "switch")}


class OperationScreen(Screen):
    """Choose what to check and how; nothing is typed."""

    BINDINGS = [Binding("escape", "back", "Back"), Binding("ctrl+r", "run", "Run")]

    def __init__(self, spec: OperationSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        head = gradient_text(f"{self.spec.icon}  {self.spec.title.upper()}",
                             PALETTE["cyan"], PALETTE["violet"])
        head.append(f"\n{self.spec.blurb}", style=PALETTE["muted"])
        yield Static(head, id="op-header")
        with VerticalScroll(id="op-form"):
            if self.spec.target_kind:
                yield Label(self.spec.target_label, classes="field-label")
                yield TargetPicker(self.spec.target_kind, prefer=self.spec.default_target,
                                   id="target")
            for option in self.spec.options:
                yield Label(option.label, classes="field-label")
                if option.kind == "target":
                    yield TargetPicker(option.target_kind or "dataset", prefer=option.default,
                                       optional=option.optional, compact=True,
                                       id=f"opt-{option.key}")
                elif option.kind == "select":
                    values = [c.value for c in option.choices]
                    yield Select([(c.label, i) for i, c in enumerate(option.choices)],
                                 value=values.index(option.default), allow_blank=False,
                                 id=f"opt-{option.key}")
                elif option.kind == "switch":
                    yield Switch(value=bool(option.default), id=f"opt-{option.key}")
            with Horizontal(id="op-run-row"):
                yield Button(f"▶  Run {self.spec.title.lower()}   ctrl+r", id="op-run",
                             variant="success", disabled=True)
                yield Static("", id="op-problem")
        yield Footer()

    def on_mount(self) -> None:
        first = self.query(TargetPicker).first(None)
        if first is not None:
            first.query_one("OptionList").focus()
        self._refresh_state()

    def params(self) -> Dict[str, Any]:
        """The run parameters currently selected."""
        params: Dict[str, Any] = {}
        if self.spec.target_kind:
            params["target"] = self.query_one("#target", TargetPicker).selected
        for option in self.spec.options:
            widget = self.query_one(f"#opt-{option.key}")
            if option.kind == "target":
                params[option.key] = widget.selected
            elif option.kind == "select":
                params[option.key] = option.choices[int(widget.value)].value
            elif option.kind == "switch":
                params[option.key] = bool(widget.value)
        return params

    def problem(self) -> Optional[str]:
        """Why Run is disabled, or ``None`` when ready."""
        if any(not p.loaded for p in self.query(TargetPicker)):
            return "Looking for targets…"
        params = self.params()
        if self.spec.target_kind and params.get("target") is None:
            return f"Pick a {self.spec.target_label.lower()} above."
        for option in self.spec.options:
            if option.kind == "target" and not option.optional and params.get(option.key) is None:
                return f"Pick a {option.label.lower()}."
        if self.spec.id == "report":
            if not any(params.get(k) for k in ("data", "model", "records", "baseline", "current")):
                return "Pick at least one module target."
            if bool(params.get("baseline")) != bool(params.get("current")):
                return "Drift needs both a baseline and a current corpus (or neither)."
        return None

    def _refresh_state(self) -> None:
        problem = self.problem()
        self.query_one("#op-run", Button).disabled = problem is not None
        self.query_one("#op-problem", Static).update(problem or "")

    def on_target_picker_changed(self, _message: TargetPicker.Changed) -> None:
        self._refresh_state()

    def on_select_changed(self, _event: Select.Changed) -> None:
        self._refresh_state()

    def on_switch_changed(self, _event: Switch.Changed) -> None:
        self._refresh_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "op-run":
            self.action_run()

    def action_run(self) -> None:
        self._refresh_state()
        if self.problem() is None:
            self.app.start_run(self.spec, self.params())

    def action_back(self) -> None:
        self.app.pop_screen()
```

> Verify while implementing: `test_escape_returns_home` proves `check_action` lets Esc fall through to the screen. If the installed Textual still swallows it, drop the picker's `escape` binding and clear the filter from `on_input_submitted`/`on_key` inside the `Input` instead.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_app_operation.py -q`
Expected: `7 passed`. (`test_report_requires_a_module_and_pairs_drift` relies on the empty tmp roots: every optional picker defaults to "— none —" only when its `prefer` label is not found; in tmp it never is.)

- [ ] **Step 6: Commit**

```bash
git add src/tui/widgets/target_picker.py src/tui/screens/operation.py tests/tui/test_app_operation.py
git commit -m "feat(tui): operation form with discovered-target picker and browse"
```

---

### Task 8: Run screen with live stages, cancel, error panel

**Files:**
- Create: `src/tui/widgets/stage_progress.py`, `src/tui/screens/run.py`
- Test: `tests/tui/test_app_run.py`

**Interfaces:**
- Consumes: `execute`, `RunOutcome`, `STAGE_LABELS` (Task 4); `CancelToken`, `ScanCancelled` (Task 1); `ConfirmModal` (Task 6); `app.show_result(op_id, result, report_path, elapsed, replace=True)` (Task 6).
- Produces:
  - `StageProgress(stages: Sequence[tuple[str, str]])`; `update_stage(stage, done, total, detail=None) -> bool`; `reset() -> None`; `finish(ok: bool) -> None`; `state(stage) -> str` ∈ {"pending","running","done","skipped","failed"}.
  - `RunScreen(spec, params)`; attributes `token: CancelToken`, `is_running: bool`, `status: str` ∈ {"running","stopping","failed","cancelled","finished"}; bindings escape/r/b/t.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_app_run.py`:

```python
"""Live stages, cancel with confirmation, error panel with retry/back."""
from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.run import RunScreen
from src.tui.widgets.stage_progress import StageProgress

RESULT = {"module": "data_scanner", "target": "x", "dataset": {"num_samples": 4},
          "summary": {"verdict": "CLEAN", "risk_score": 0.1, "total_findings": 0},
          "findings": []}


def _app(tmp_path: Path) -> ShieldApp:
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


def _spec(runner):
    return dataclasses.replace(OPERATIONS_BY_ID["scan"], runner=runner)


@async_test
async def test_stages_advance_and_results_open(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 1, 1)
        progress("embedding", 5, 10)
        gate.wait(5)
        progress("trigger", 1, 1)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        stages = app.screen.query_one(StageProgress)
        await wait_for(pilot, lambda: stages.state("embedding") == "running")
        assert stages.state("loading") == "done"
        assert stages.state("trigger") == "pending"
        gate.set()
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ResultsScreen")
        assert list((tmp_path / "r").glob("SHIELD-SCAN-*.json"))


@async_test
async def test_escape_asks_then_cancels(tmp_path):
    stopped = []

    def runner(params, progress):
        try:
            for i in range(400):
                progress("embedding", i, 400)
                time.sleep(0.01)
        except BaseException:
            stopped.append(True)
            raise
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        run_screen = app.screen
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("y")
        await wait_for(pilot, lambda: bool(stopped))
        await wait_for(pilot, lambda: app.screen is not run_screen)
        assert run_screen.status == "cancelled"
        assert not list((tmp_path / "r").glob("*.json"))


@async_test
async def test_escape_then_no_keeps_running(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 0, 1)
        gate.wait(5)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        assert app.screen.status == "running"
        gate.set()
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ResultsScreen")


@async_test
async def test_quit_during_run_asks_first(tmp_path):
    gate = threading.Event()

    def runner(params, progress):
        progress("loading", 0, 1)
        gate.wait(5)
        return dict(RESULT)

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        await pilot.press("q")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "ConfirmModal")
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen))
        assert app.is_running
        gate.set()


@async_test
async def test_error_panel_retry_and_back(tmp_path):
    calls = []

    def runner(params, progress):
        calls.append(1)
        progress("loading", 0, 1)
        raise RuntimeError("disk on fire")

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        app.start_run(_spec(runner), {"target": tmp_path})
        await wait_for(pilot, lambda: isinstance(app.screen, RunScreen)
                       and app.screen.status == "failed")
        screen = app.screen
        assert "RuntimeError: disk on fire" in str(screen.query_one("#run-error-text").content)
        assert screen.query_one(StageProgress).state("loading") == "failed"
        await pilot.press("r")
        await wait_for(pilot, lambda: len(calls) == 2 and screen.status == "failed")
        await pilot.press("b")
        await wait_for(pilot, lambda: app.screen is not screen)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_app_run.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.screens.run'`.

- [ ] **Step 3: Implement `src/tui/widgets/stage_progress.py`**

```python
"""One live row per engine stage."""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import ProgressBar, Static

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ICONS = {"pending": "[dim]·[/dim]", "done": "[green]✓[/green]", "skipped": "[dim]–[/dim]",
         "failed": "[red]✗[/red]"}


class StageProgress(Vertical):
    """Stages turn running → done in order; unreported ones end as skipped."""

    def __init__(self, stages: Sequence[Tuple[str, str]]) -> None:
        super().__init__()
        self.stages = list(stages)
        self._states: Dict[str, str] = {sid: "pending" for sid, _ in self.stages}
        self._frame = 0

    def compose(self) -> ComposeResult:
        for sid, label in self.stages:
            with Horizontal(classes="stage-row", id=f"stage-{sid}"):
                yield Static(ICONS["pending"], classes="stage-icon")
                yield Static(label, classes="stage-label")
                yield ProgressBar(total=None, show_eta=False, show_percentage=True)
                yield Static("", classes="stage-detail")

    def on_mount(self) -> None:
        self.set_interval(0.1, self._spin)

    def state(self, stage: str) -> str:
        return self._states.get(stage, "unknown")

    def _row(self, stage: str) -> Horizontal:
        return self.query_one(f"#stage-{stage}", Horizontal)

    def _set_state(self, stage: str, state: str) -> None:
        self._states[stage] = state
        row = self._row(stage)
        if state in ICONS:
            row.query_one(".stage-icon", Static).update(ICONS[state])
        bar = row.query_one(ProgressBar)
        if state == "done":
            bar.update(total=bar.total or 1, progress=bar.total or 1)

    def update_stage(self, stage: str, done: int, total: int,
                     detail: Optional[str] = None) -> bool:
        """Advance to ``stage``; returns ``False`` for stages this run does not track."""
        if stage not in self._states:
            return False
        order = [sid for sid, _ in self.stages]
        for earlier in order[:order.index(stage)]:
            if self._states[earlier] in ("pending", "running"):
                self._set_state(earlier, "done" if self._states[earlier] == "running" else "skipped")
        row = self._row(stage)
        self._states[stage] = "running"
        if total > 0:
            row.query_one(ProgressBar).update(total=total, progress=min(done, total))
        if detail:
            row.query_one(".stage-detail", Static).update(detail)
        if total > 0 and done >= total:
            self._set_state(stage, "done")
        return True

    def reset(self) -> None:
        """Back to all-pending, for a retry."""
        for sid, _ in self.stages:
            self._states[sid] = "pending"
            row = self._row(sid)
            row.query_one(".stage-icon", Static).update(ICONS["pending"])
            row.query_one(ProgressBar).update(total=None, progress=0)
            row.query_one(".stage-detail", Static).update("")

    def finish(self, ok: bool) -> None:
        """Close out every row at the end of a run."""
        for sid, state in list(self._states.items()):
            if state == "running":
                self._set_state(sid, "done" if ok else "failed")
            elif state == "pending":
                self._set_state(sid, "skipped")

    def _spin(self) -> None:
        self._frame = (self._frame + 1) % len(SPINNER)
        for sid, state in self._states.items():
            if state == "running":
                self._row(sid).query_one(".stage-icon", Static).update(
                    f"[cyan]{SPINNER[self._frame]}[/cyan]")
```

- [ ] **Step 4: Implement `src/tui/screens/run.py`**

```python
"""Live run: real stage progress, Esc to cancel, error panel with retry."""

from __future__ import annotations

import time
import traceback
from typing import Any, Dict, Optional

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

from src.tui.operations import STAGE_LABELS, OperationSpec, RunOutcome, execute
from src.tui.screens.modals import ConfirmModal
from src.tui.theme import PALETTE
from src.tui.visuals import gradient_text
from src.tui.widgets.stage_progress import StageProgress
from src.utils.cancel import CancelToken, ScanCancelled


class RunScreen(Screen):
    """Runs one operation in a thread worker and shows what it is really doing."""

    BINDINGS = [Binding("escape", "cancel", "Cancel / back"),
                Binding("r", "retry", "Retry", show=False),
                Binding("b", "back", "Back", show=False),
                Binding("t", "toggle_trace", "Traceback", show=False)]

    def __init__(self, spec: OperationSpec, params: Dict[str, Any]) -> None:
        super().__init__()
        self.spec = spec
        self.params = params
        self.token = CancelToken()
        self.status = "running"
        self._started = time.monotonic()
        self._last: Optional[tuple] = None

    @property
    def is_running(self) -> bool:
        return self.status in ("running", "stopping")

    def compose(self) -> ComposeResult:
        target = self.params.get("target") or "all selected modules"
        head = gradient_text(f"{self.spec.icon}  {self.spec.title.upper()}",
                             PALETTE["cyan"], PALETTE["violet"])
        head.append(f"   {target}", style=PALETTE["muted"])
        yield Static(head, id="run-header")
        yield StageProgress(self.spec.stages)
        yield Static("", id="run-status")
        with Vertical(id="run-error"):
            yield Static("", id="run-error-text")
            yield Static("", id="run-trace")
        yield RichLog(id="run-log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.25, self._tick)
        self._start()

    # -- worker ------------------------------------------------------------
    def _start(self) -> None:
        self.token = CancelToken()
        self.status = "running"
        self._started = time.monotonic()
        self.remove_class("-failed")
        self.remove_class("-trace")
        self.query_one(RichLog).write(f"[dim]{time.strftime('%H:%M:%S')}[/dim]  started")
        self._work()

    @work(thread=True, exclusive=True, group="engine")
    def _work(self) -> None:
        try:
            outcome = execute(self.spec, self.params, self._progress_from_thread, self.token,
                              getattr(self.app, "reports_dir", None))
        except ScanCancelled:
            self.app.call_from_thread(self._cancelled)
        except Exception as exc:  # shown in the error panel, never crashes the app
            self.app.call_from_thread(self._failed, exc, traceback.format_exc())
        else:
            self.app.call_from_thread(self._finished, outcome)

    def _progress_from_thread(self, stage: str, done: int, total: int,
                              detail: Optional[str]) -> None:
        self.app.call_from_thread(self._progress, stage, done, total, detail)

    # -- UI updates (main thread) -------------------------------------------
    def _progress(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        self.query_one(StageProgress).update_stage(stage, done, total, detail)
        if self._last is None or self._last[0] != stage:
            label = STAGE_LABELS.get(stage, stage)
            self.query_one(RichLog).write(
                f"[dim]{time.strftime('%H:%M:%S')}[/dim]  {escape(label)}"
                + (f" [dim]· {escape(detail)}[/dim]" if detail else ""))
        self._last = (stage, done, total, time.monotonic())

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        text = {"running": f"Elapsed {elapsed:5.1f}s",
                "stopping": "Stopping at the next checkpoint…",
                "failed": "Stopped with an error — r retry · b back · t traceback",
                "cancelled": "Cancelled.", "finished": "Done."}[self.status]
        if self.status == "running" and self._last and self._last[2] > 1 and self._last[1] > 0:
            stage, done, total, _ = self._last
            rate = done / max(1e-6, elapsed)
            text += f"   ≈ {max(0.0, (total - done) / rate):.0f}s left in this stage"
        self.query_one("#run-status", Static).update(text)

    def _finished(self, outcome: RunOutcome) -> None:
        self.status = "finished"
        self.query_one(StageProgress).finish(ok=True)
        if outcome.save_error:
            self.app.notify(f"Report not saved: {outcome.save_error}", severity="error",
                            timeout=8)
        self.app.show_result(self.spec.id, outcome.result, outcome.report_path,
                             outcome.elapsed, replace=True)

    def _cancelled(self) -> None:
        self.status = "cancelled"
        self.query_one(StageProgress).finish(ok=False)
        self.app.notify("Check cancelled — nothing was saved.")
        self.app.pop_screen()

    def _failed(self, exc: Exception, trace: str) -> None:
        self.status = "failed"
        self.query_one(StageProgress).finish(ok=False)
        self.query_one("#run-error-text", Static).update(
            f"[bold red]The check stopped with an error. Nothing was saved.[/bold red]\n"
            f"{escape(type(exc).__name__)}: {escape(str(exc))}\n"
            f"[dim]r retry · b back · t show traceback[/dim]")
        self.query_one("#run-trace", Static).update(escape(trace))
        self.add_class("-failed")

    # -- actions -----------------------------------------------------------
    def action_cancel(self) -> None:
        if self.status == "running":
            self.app.push_screen(ConfirmModal("Stop this check? Partial results are discarded."),
                                 self._confirm_cancel)
        elif self.status in ("failed", "cancelled"):
            self.action_back()

    def _confirm_cancel(self, stop: Optional[bool]) -> None:
        if stop and self.status == "running":
            self.status = "stopping"
            self.token.cancel()

    def action_retry(self) -> None:
        if self.status == "failed":
            self.query_one(StageProgress).reset()
            self._last = None
            self._start()

    def action_back(self) -> None:
        if not self.is_running:
            self.app.pop_screen()

    def action_toggle_trace(self) -> None:
        if self.status == "failed":
            self.toggle_class("-trace")
```

- [ ] **Step 5: Add a temporary `ResultsScreen` placeholder only if Task 9 is not yet merged**

`test_stages_advance_and_results_open` needs `ResultsScreen`. If implementing tasks strictly in order, create `src/tui/screens/results.py` now with:

```python
"""Results screen (full version in Task 9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class ResultsScreen(Screen):
    def __init__(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                 elapsed: Optional[float] = None) -> None:
        super().__init__()
        self.op_id, self.result, self.report_path, self.elapsed = op_id, result, report_path, elapsed

    def compose(self) -> ComposeResult:
        yield Static(str(self.result.get("summary")))
```

and a minimal `src/tui/screens/agents.py` with `class AgentsScreen(Screen): def __init__(self, spec, params, result=None): super().__init__()`. Both are fully replaced in Tasks 9 and 10.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_app_run.py -q`
Expected: `5 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/tui/widgets/stage_progress.py src/tui/screens/run.py src/tui/screens/results.py src/tui/screens/agents.py tests/tui/test_app_run.py
git commit -m "feat(tui): live run screen with real stages, cancel and error retry"
```

---

### Task 9: Results screen — verdict, breakdown, findings browser, image previews

**Files:**
- Create: `src/tui/widgets/image_preview.py`, `src/tui/widgets/findings.py`
- Replace: `src/tui/screens/results.py`
- Test: `tests/tui/test_app_results.py`

**Interfaces:**
- Consumes: `headline`, `details_rows`, `risk_tone`, `target_name` (Task 3); `banner_text`, `risk_gauge`, `severity_bar`, `labelled_bars` (Task 5); `TONE_COLORS`, `SEVERITY_COLORS`, `SEVERITY_ORDER`, `PALETTE` (Task 5); `build_asset_index`, `resolve_asset`, `IMAGE_EXTS` (Task 2); `save_report` (Task 4); `BrowseModal` (Task 6); `open_path` (Task 6); `Sized` (Task 6).
- Produces:
  - `ImagePreview()`; `show(paths: Sequence[Path]) -> None`; attribute `shown_paths: list[Path]`; attribute `messages: list[str]` (fallback texts shown).
  - `FindingsTable()` (DataTable); `load(findings: Sequence[dict]) -> None`; `set_filter(severity: str | None) -> None`; `current() -> dict | None`; posts `FindingsTable.Focused(finding)`.
  - `FindingDetail()`; `show(finding: dict | None, assets: Sequence[Path]) -> None`.
  - `ResultsScreen(op_id, result, report_path, elapsed=None)`; attributes `head: Headline`, `severity_filter: str | None`.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_app_results.py`:

```python
"""Results: verdict banner, findings table, detail with image, filters, export."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.screens.results import ResultsScreen
from src.tui.widgets.findings import FindingDetail, FindingsTable
from src.tui.widgets.image_preview import ImagePreview


def _result(dataset_root: Path) -> dict:
    return {
        "module": "data_scanner", "target": str(dataset_root),
        "dataset": {"num_samples": 2, "root": str(dataset_root), "format": "yolo"},
        "summary": {"verdict": "COMPROMISED", "risk_score": 0.82, "total_findings": 2,
                    "by_severity": {"CRITICAL": 1, "LOW": 1},
                    "by_attack_class": {"TRIGGER_INJECTION": 1, "LABEL_FLIPPING": 1}},
        "contributor_risk": {"contributor_a": {"risk": 0.9, "findings": 2}},
        "findings": [
            {"finding_id": "FIND-001", "severity": "LOW", "attack_class": "LABEL_FLIPPING",
             "affected_asset": "missing.jpg", "confidence": 0.3, "reason": "low one",
             "evidence": {"k": 1}, "recommended_disposition": "ACCEPT"},
            {"finding_id": "FIND-002", "severity": "CRITICAL", "attack_class": "TRIGGER_INJECTION",
             "affected_asset": "a1.png", "confidence": 0.97, "reason": "bright patch bottom-right",
             "evidence": {"patch_energy": 9.1, "member_files": ["a1.png"]},
             "recommended_disposition": "QUARANTINE"},
        ],
        "limitations": ["demo limitation"],
    }


def _dataset(tmp_path: Path) -> Path:
    folder = tmp_path / "ds" / "contributor_a" / "images"
    folder.mkdir(parents=True)
    Image.new("RGB", (32, 32), (200, 30, 30)).save(folder / "a1.png")
    return tmp_path / "ds"


async def _open(pilot, app, result, report_path=None) -> ResultsScreen:
    await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
    app.show_result("scan", result, report_path, 3.2)
    await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
    return app.screen


def _app(tmp_path):
    return ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")


@async_test
async def test_banner_and_table_sorted_by_severity(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        assert screen.head.verdict == "COMPROMISED"
        table = screen.query_one(FindingsTable)
        assert table.row_count == 2
        assert table.current()["finding_id"] == "FIND-002"


@async_test
async def test_detail_shows_reason_and_image_preview(tmp_path):
    root = _dataset(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(root))
        detail = screen.query_one(FindingDetail)
        preview = screen.query_one(ImagePreview)
        await wait_for(pilot, lambda: preview.shown_paths or preview.messages)
        assert "bright patch bottom-right" in detail.text
        assert preview.shown_paths == [root / "contributor_a" / "images" / "a1.png"] \
            or any("preview unavailable" in m for m in preview.messages)


@async_test
async def test_missing_asset_does_not_break_detail(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        table = screen.query_one(FindingsTable)
        table.focus()
        await pilot.press("down")
        await wait_for(pilot, lambda: "low one" in screen.query_one(FindingDetail).text)


@async_test
async def test_severity_filter_cycles(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, _result(_dataset(tmp_path)))
        table = screen.query_one(FindingsTable)
        expected = [("CRITICAL", 1), ("HIGH", 0), ("MEDIUM", 0), ("LOW", 1), (None, 2)]
        for severity, rows in expected:
            await pilot.press("f")
            assert (screen.severity_filter, table.row_count) == (severity, rows)


@async_test
async def test_inconclusive_banner(tmp_path):
    result = _result(_dataset(tmp_path))
    result["dataset"]["num_samples"] = 0
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        screen = await _open(pilot, app, result)
        assert screen.head.verdict == "INCONCLUSIVE"


@async_test
async def test_escape_goes_home(tmp_path):
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await _open(pilot, app, _result(_dataset(tmp_path)))
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")


@async_test
async def test_report_result_has_briefing_tab(tmp_path):
    report = {"schema_version": "1", "summary": {"verdict": "COMPROMISED", "risk_score": 0.99,
                                                 "by_severity": {"HIGH": 1}},
              "findings": [], "modules": {"data_scanner": {}},
              "immunity": {"score": 12.5, "band": "COMPROMISED",
                           "components": {"data": {"label": "Data", "score": 20.0}}},
              "briefing": {"text": "Quarantine contributor alpha."},
              "threat_story": {"stories": [{"title": "Coordinated attack", "pattern": "X"}]}}
    app = _app(tmp_path)
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
        app.show_result("report", report, None)
        await wait_for(pilot, lambda: isinstance(app.screen, ResultsScreen))
        assert app.screen.query_one("#tab-briefing") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_app_results.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'src.tui.widgets.findings'`.

- [ ] **Step 3: Implement `src/tui/widgets/image_preview.py`**

```python
"""Show flagged images inside the terminal, or say why not."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from rich.markup import escape
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

try:
    from PIL import Image as PILImage
    from textual_image.widget import Image as TerminalImage
    _IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - environment dependent
    PILImage = None  # type: ignore[assignment]
    TerminalImage = None  # type: ignore[assignment]
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

MAX_IMAGES = 3


class ImagePreview(Vertical):
    """Up to three images side by side, each with its file name."""

    def __init__(self) -> None:
        super().__init__()
        self.shown_paths: List[Path] = []
        self.messages: List[str] = []

    def show(self, paths: Sequence[Path]) -> None:
        """Replace the preview with ``paths`` (empty hides it)."""
        self.remove_children()
        self.shown_paths, self.messages = [], []
        if not paths:
            return
        row = Horizontal()
        self.mount(row)
        for path in list(paths)[:MAX_IMAGES]:
            cell = Vertical(classes="preview-cell")
            row.mount(cell)
            problem = self._problem(path)
            if problem:
                text = f"[preview unavailable: {problem}]"
                self.messages.append(text)
                cell.mount(Static(f"[dim]{escape(text)}\n{escape(str(path))}[/dim]"))
                continue
            try:
                cell.mount(TerminalImage(str(path)))
                self.shown_paths.append(Path(path))
            except Exception as exc:
                text = f"[preview unavailable: {type(exc).__name__}: {exc}]"
                self.messages.append(text)
                cell.mount(Static(f"[dim]{escape(text)}[/dim]"))
                continue
            cell.mount(Static(f"[dim]{escape(Path(path).name)}[/dim]"))

    @staticmethod
    def _problem(path: Path) -> str:
        if TerminalImage is None or PILImage is None:
            return f"textual-image not available ({_IMPORT_ERROR})"
        if not Path(path).is_file():
            return "file not found"
        try:
            with PILImage.open(path) as image:
                image.verify()
        except Exception as exc:
            return f"unreadable image ({type(exc).__name__})"
        return ""
```

- [ ] **Step 4: Implement `src/tui/widgets/findings.py`**

```python
"""Findings table and the detail pane beside it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from src.tui.theme import SEVERITY_COLORS, SEVERITY_ORDER
from src.tui.widgets.image_preview import ImagePreview

_RANK = {sev: i for i, sev in enumerate(SEVERITY_ORDER)}


def sort_key(finding: Dict[str, Any]) -> tuple:
    """Most severe first, then most confident."""
    return (_RANK.get(str(finding.get("severity", "")).upper(), 99),
            -float(finding.get("confidence", 0.0) or 0.0))


class FindingsTable(DataTable):
    """Sortable, filterable list of findings."""

    class Focused(Message):
        """A finding is highlighted."""

        def __init__(self, finding: Optional[Dict[str, Any]]) -> None:
            self.finding = finding
            super().__init__()

    def __init__(self) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True)
        self._all: List[Dict[str, Any]] = []
        self._rows: List[Dict[str, Any]] = []

    def load(self, findings: Sequence[Dict[str, Any]]) -> None:
        if not self.columns:
            self.add_columns("Severity", "ID", "Attack class", "Asset", "Conf", "Action")
        self._all = sorted((dict(f) for f in findings), key=sort_key)
        self.set_filter(None)

    def set_filter(self, severity: Optional[str]) -> None:
        self.clear()
        self._rows = [f for f in self._all
                      if severity is None or str(f.get("severity", "")).upper() == severity]
        for index, f in enumerate(self._rows):
            sev = str(f.get("severity", "")).upper()
            self.add_row(Text(f" {sev} ", style=f"bold #000000 on {SEVERITY_COLORS.get(sev, '#7D8590')}"),
                         str(f.get("finding_id", "")), str(f.get("attack_class", "")),
                         Path(str(f.get("affected_asset", ""))).name[:28],
                         f"{float(f.get('confidence', 0.0) or 0.0):.2f}",
                         str(f.get("recommended_disposition") or f.get("disposition") or ""),
                         key=str(index))
        self.post_message(self.Focused(self.current()))

    def current(self) -> Optional[Dict[str, Any]]:
        if not self._rows:
            return None
        return self._rows[min(max(self.cursor_row, 0), len(self._rows) - 1)]

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self.post_message(self.Focused(self.current()))


class FindingDetail(VerticalScroll):
    """Reason, evidence, disposition and image preview for one finding."""

    def __init__(self) -> None:
        super().__init__()
        self.text = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="detail-body")
        yield ImagePreview()

    def show(self, finding: Optional[Dict[str, Any]], assets: Sequence[Path]) -> None:
        body = self.query_one("#detail-body", Static)
        if finding is None:
            self.text = "No findings to show."
            body.update(f"[dim]{self.text}[/dim]")
            self.query_one(ImagePreview).show([])
            return
        sev = str(finding.get("severity", "")).upper()
        reason = str(finding.get("reason", ""))
        lines = [f"[bold #000000 on {SEVERITY_COLORS.get(sev, '#7D8590')}] {sev} [/] "
                 f"[bold]{escape(str(finding.get('finding_id', '')))}[/bold]  "
                 f"{escape(str(finding.get('attack_class', '')))}",
                 "", escape(reason), "",
                 f"[bold]Action:[/bold] {escape(str(finding.get('recommended_disposition') or finding.get('disposition') or '—'))}"
                 f"   [bold]Confidence:[/bold] {float(finding.get('confidence', 0.0) or 0.0):.2f}",
                 f"[bold]Asset:[/bold] {escape(str(finding.get('affected_asset', '')))}"]
        self.text = "\n".join([str(finding.get("finding_id", "")), reason])
        parts = [Text.from_markup("\n".join(lines) + "\n")]
        evidence = finding.get("evidence") or {}
        if evidence:
            table = Table(box=None, show_header=False, padding=(0, 1), title="Evidence",
                          title_justify="left", title_style="bold")
            table.add_column(style="cyan", no_wrap=True)
            table.add_column()
            for key, value in evidence.items():
                shown = (", ".join(map(str, value[:6])) + (" …" if len(value) > 6 else "")
                         if isinstance(value, list) else str(value))
                table.add_row(str(key), escape(shown[:160]))
            parts.append(table)
        body.update(Group(*parts))
        self.query_one(ImagePreview).show(list(assets))
```

- [ ] **Step 5: Replace `src/tui/screens/results.py`**

```python
"""Verdict, gauges, breakdown and a findings browser with image previews."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.markup import escape
from rich.table import Table
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Digits, Footer, Label, Static, TabbedContent, TabPane

from src.tui.discovery import IMAGE_EXTS, build_asset_index, resolve_asset
from src.tui.operations import save_report
from src.tui.screens.modals import BrowseModal
from src.tui.system import open_path
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.verdict import details_rows, headline, risk_tone, target_name
from src.tui.visuals import banner_text, labelled_bars, risk_gauge, severity_bar
from src.tui.widgets.findings import FindingDetail, FindingsTable
from src.tui.widgets.sized import Sized

FILTER_CYCLE = (None, "CRITICAL", "HIGH", "MEDIUM", "LOW")
PREFIX = {"scan": "SCAN", "audit": "AUDIT", "verify": "VERIFY", "drift": "DRIFT",
          "report": "REPORT"}


class ResultsScreen(Screen):
    """Everything one run found."""

    BINDINGS = [Binding("escape", "home", "Home"), Binding("f", "filter", "Filter severity"),
                Binding("o", "open_asset", "Open file"), Binding("s", "saved", "Saved path"),
                Binding("e", "export", "Export")]

    def __init__(self, op_id: str, result: Dict[str, Any], report_path: Optional[Path],
                 elapsed: Optional[float] = None) -> None:
        super().__init__()
        self.op_id = op_id
        self.result = result
        self.report_path = report_path
        self.elapsed = elapsed
        self.head = headline(op_id, result)
        self.severity_filter: Optional[str] = None
        self._index: Dict[str, Path] = {}
        self._base = self._dataset_root()

    def _dataset_root(self) -> Optional[Path]:
        raw = (self.result.get("dataset") or {}).get("root") or self.result.get("target")
        if isinstance(raw, str) and raw and Path(raw).is_dir():
            return Path(raw)
        return None

    # -- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        head = self.head
        yield Sized(lambda w: banner_text(head.verdict, head.tone, head.note, w), id="res-banner")
        summary = self.result.get("summary") or {}
        stats = [f"[bold]{escape(target_name(self.result))}[/bold]",
                 f"{len(self.result.get('findings') or [])} findings"]
        if self.elapsed is not None:
            stats.append(f"{self.elapsed:.1f}s")
        if self.report_path:
            stats.append(f"[dim]saved {escape(self.report_path.name)}[/dim]")
        yield Static("   ·   ".join(stats), id="res-stats")
        yield Sized(lambda w: risk_gauge(head.risk, min(w, 90)), id="res-gauge")
        with TabbedContent(id="res-tabs"):
            with TabPane("Findings", id="tab-findings"):
                with Horizontal(id="findings-pane"):
                    yield FindingsTable()
                    yield FindingDetail()
            with TabPane("Breakdown", id="tab-breakdown"):
                with VerticalScroll():
                    yield Label("Severity", classes="breakdown-title")
                    yield Sized(lambda w: severity_bar(summary.get("by_severity") or {},
                                                       min(w, 100)))
                    yield Label("Attack classes", classes="breakdown-title")
                    yield Sized(lambda w: labelled_bars(self._class_rows(), min(w, 100)))
                    if self.result.get("contributor_risk"):
                        yield Label("Contributor risk", classes="breakdown-title")
                        yield Sized(lambda w: labelled_bars(self._contributor_rows(), min(w, 100)))
                    if (self.result.get("immunity") or {}).get("components"):
                        yield Label("Immunity pillars", classes="breakdown-title")
                        yield Sized(lambda w: labelled_bars(self._pillar_rows(), min(w, 100)))
            with TabPane("Details", id="tab-details"):
                with VerticalScroll():
                    yield Static(self._details_table())
            if self.op_id == "report":
                with TabPane("Briefing", id="tab-briefing"):
                    with VerticalScroll(id="res-immunity"):
                        immunity = self.result.get("immunity") or {}
                        yield Label("Adversarial immunity score", classes="breakdown-title")
                        yield Digits(f"{float(immunity.get('score', 0.0)):.1f}")
                        yield Static(f"[bold]{escape(str(immunity.get('band', '?')))}[/bold]")
                        yield Label("Commander's briefing", classes="breakdown-title")
                        yield Static(escape(str((self.result.get("briefing") or {}).get("text", ""))))
                        stories = (self.result.get("threat_story") or {}).get("stories") or []
                        if stories:
                            yield Label("Threat narratives", classes="breakdown-title")
                            yield Static("\n".join(f"→ {escape(str(s.get('title', '')))}"
                                                   for s in stories))
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(FindingsTable).load(self.result.get("findings") or [])
        self.query_one(FindingsTable).focus()
        self._build_index()

    # -- data helpers --------------------------------------------------------
    def _class_rows(self) -> List[tuple]:
        counts = (self.result.get("summary") or {}).get("by_attack_class") or {}
        top = max([int(v) for v in counts.values()] or [1])
        return [(name, int(n) / top, PALETTE["violet"], str(n))
                for name, n in sorted(counts.items(), key=lambda kv: -int(kv[1]))]

    def _contributor_rows(self) -> List[tuple]:
        rows = []
        for name, entry in sorted((self.result.get("contributor_risk") or {}).items(),
                                  key=lambda kv: -float(kv[1].get("risk", 0.0))):
            risk = float(entry.get("risk", 0.0))
            rows.append((name, risk, TONE_COLORS[risk_tone(risk)][0], f"{risk:.2f}"))
        return rows

    def _pillar_rows(self) -> List[tuple]:
        rows = []
        for key, comp in ((self.result.get("immunity") or {}).get("components") or {}).items():
            score = float(comp.get("score", 0.0))
            tone = "danger" if score < 50 else "warn" if score < 70 else "ok"
            rows.append((str(comp.get("label", key)), score / 100, TONE_COLORS[tone][0],
                         f"{score:.0f}"))
        return rows

    def _details_table(self) -> Table:
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        for key, value in details_rows(self.op_id, self.result):
            table.add_row(key, escape(value))
        for limitation in self.result.get("limitations") or []:
            table.add_row("[yellow]Limitation[/yellow]", escape(str(limitation)))
        return table

    @work(thread=True, exclusive=True, group="assets")
    def _build_index(self) -> None:
        index = build_asset_index(self._base)
        self.app.call_from_thread(self._index_ready, index)

    def _index_ready(self, index: Dict[str, Path]) -> None:
        self._index = index
        self._show_detail(self.query_one(FindingsTable).current())

    def _assets(self, finding: Optional[Dict[str, Any]]) -> List[Path]:
        if not finding:
            return []
        names = [str(finding.get("affected_asset") or "")]
        names += [str(n) for n in (finding.get("evidence") or {}).get("member_files") or []]
        paths: List[Path] = []
        for name in names:
            if Path(name).suffix.lower() not in IMAGE_EXTS:
                continue
            hit = resolve_asset(name, self._index, self._base)
            if hit is not None and hit not in paths:
                paths.append(hit)
        return paths[:3]

    def _show_detail(self, finding: Optional[Dict[str, Any]]) -> None:
        self.query_one(FindingDetail).show(finding, self._assets(finding))

    def on_findings_table_focused(self, message: FindingsTable.Focused) -> None:
        self._show_detail(message.finding)

    # -- actions -----------------------------------------------------------
    def action_home(self) -> None:
        self.app.go_home()

    def action_filter(self) -> None:
        index = FILTER_CYCLE.index(self.severity_filter)
        self.severity_filter = FILTER_CYCLE[(index + 1) % len(FILTER_CYCLE)]
        self.query_one(FindingsTable).set_filter(self.severity_filter)
        self.notify(f"Showing {self.severity_filter or 'all'} findings", timeout=2)

    def action_open_asset(self) -> None:
        assets = self._assets(self.query_one(FindingsTable).current())
        target = assets[0] if assets else self.report_path
        if target is None:
            self.notify("Nothing to open for this finding.", severity="warning")
            return
        error = open_path(target)
        if error:
            self.notify(error, severity="error")

    def action_saved(self) -> None:
        if self.report_path:
            self.notify(f"Saved: {self.report_path}", timeout=8)
        else:
            self.notify("This result was not saved — press e to export it.", severity="warning")

    def action_export(self) -> None:
        def chosen(folder: Optional[Path]) -> None:
            if folder is None:
                return
            path, error = save_report(self.result, PREFIX.get(self.op_id, "RESULT"), folder)
            if error:
                self.notify(f"Export failed: {error}", severity="error")
            else:
                self.notify(f"Exported: {path}", timeout=8)
        self.app.push_screen(BrowseModal("folder"), chosen)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_app_results.py -q`
Expected: `7 passed`.

- [ ] **Step 7: Run all TUI tests**

Run: `python -m pytest tests/tui -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/tui/widgets/image_preview.py src/tui/widgets/findings.py src/tui/screens/results.py tests/tui/test_app_results.py
git commit -m "feat(tui): results screen with verdict banner, breakdown and findings browser"
```

---

### Task 10: Agents screen

**Files:**
- Replace: `src/tui/screens/agents.py`
- Test: `tests/tui/test_app_agents.py`

**Interfaces:**
- Consumes: `execute`, `OperationSpec` (Task 4); `STAGE_LABELS`; `headline`, `risk_tone` (Task 3); `banner_text`, `bar` (Task 5); `Sized` (Task 6); `ConfirmModal` (Task 6); `CancelToken`, `ScanCancelled` (Task 1). Engine progress for agents arrives as `progress(stage, done, total, contributor)`; `stage == "finished"` marks an agent done; `stage == "meeting"` has `detail=None`.
- Produces: `AgentsScreen(spec: OperationSpec, params: dict | None, result: dict | None = None)` with `token`, `is_running`, `status` (as RunScreen), `cards: dict[str, AgentCard]`; `AgentCard(contributor: str, agent_id: str)` with `update_stage(stage, done, total)`, `finish(report: dict | None)`.

- [ ] **Step 1: Write the failing tests**

`tests/tui/test_app_agents.py`:

```python
"""Agent cards fill live, then the meeting verdict appears; reopen from a saved report."""
from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

from helpers import async_test, wait_for
from src.tui.app import ShieldApp
from src.tui.operations import OPERATIONS_BY_ID
from src.tui.screens.agents import AgentsScreen

OFFICE = {"module": "office_manager", "agents": 2, "mode": "thread", "errors": [],
          "reports": [{"agent_id": "AGENT-01", "contributor": "contributor_a", "risk_score": 0.9,
                       "num_samples": 10, "num_findings": 4, "verdict": "COMPROMISED"},
                      {"agent_id": "AGENT-02", "contributor": "contributor_b", "risk_score": 0.1,
                       "num_samples": 12, "num_findings": 0, "verdict": "CLEAN"}],
          "meeting": {"verdict": "SUSPICIOUS", "narrative": "Alpha stands out.",
                      "recommendations": ["Quarantine contributor_a"]}}


def _dataset(tmp_path: Path) -> Path:
    for name in ("contributor_a", "contributor_b"):
        folder = tmp_path / "ds" / name / "images"
        folder.mkdir(parents=True)
        (folder / "x.jpg").write_bytes(b"x")
    return tmp_path / "ds"


@async_test
async def test_live_cards_then_meeting(tmp_path):
    root = _dataset(tmp_path)
    gate = threading.Event()

    def runner(params, progress):
        progress("embedding", 3, 10, "contributor_a")
        progress("trigger", 1, 2, "contributor_b")
        gate.wait(5)
        progress("finished", 1, 2, "contributor_a")
        progress("finished", 2, 2, "contributor_b")
        progress("meeting", 1, 1)
        return dict(OFFICE)

    spec = dataclasses.replace(OPERATIONS_BY_ID["agents"], runner=runner)
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    async with app.run_test(size=(140, 44)) as pilot:
        app.start_run(spec, {"target": root})
        await wait_for(pilot, lambda: isinstance(app.screen, AgentsScreen))
        screen = app.screen
        await wait_for(pilot, lambda: "contributor_a" in screen.cards
                       and "ResNet-18" in screen.cards["contributor_a"].stage_text)
        gate.set()
        await wait_for(pilot, lambda: screen.status == "finished")
        assert screen.has_class("-done")
        assert "Alpha stands out." in screen.meeting_text
        assert screen.cards["contributor_a"].has_class("-finished")
        assert list((tmp_path / "r").glob("SHIELD-AGENTS-*.json"))


@async_test
async def test_static_from_saved_result(tmp_path):
    app = ShieldApp(splash=False, discovery_roots=[tmp_path], reports_dir=tmp_path / "r")
    async with app.run_test(size=(140, 44)) as pilot:
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
        app.show_result("agents", dict(OFFICE), None)
        await wait_for(pilot, lambda: isinstance(app.screen, AgentsScreen))
        assert set(app.screen.cards) == {"contributor_a", "contributor_b"}
        assert app.screen.status == "finished"
        await pilot.press("escape")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "HomeScreen")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tui/test_app_agents.py -q`
Expected: FAIL (placeholder `AgentsScreen` has no `cards`).

- [ ] **Step 3: Replace `src/tui/screens/agents.py`**

```python
"""One live card per contributor agent, then the meeting room's verdict."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from src.tui.operations import STAGE_LABELS, OperationSpec, RunOutcome, execute
from src.tui.screens.modals import ConfirmModal
from src.tui.theme import PALETTE, TONE_COLORS
from src.tui.verdict import headline, risk_tone
from src.tui.visuals import banner_text, bar, gradient_text
from src.tui.widgets.sized import Sized
from src.utils.cancel import CancelToken, ScanCancelled


class AgentCard(Static):
    """One contributor agent."""

    def __init__(self, contributor: str, agent_id: str) -> None:
        super().__init__(classes="agent-card")
        self.contributor = contributor
        self.agent_id = agent_id
        self.stage_text = "waiting"
        self.fraction = 0.0
        self.report: Optional[Dict[str, Any]] = None

    def on_mount(self) -> None:
        self._paint()

    def update_stage(self, stage: str, done: int, total: int) -> None:
        self.stage_text = STAGE_LABELS.get(stage, stage)
        self.fraction = done / total if total else 0.0
        self._paint()

    def finish(self, report: Optional[Dict[str, Any]]) -> None:
        self.report = report
        self.stage_text = "finished"
        self.fraction = 1.0
        status = str((report or {}).get("status", "")).upper()
        self.set_class(status == "ERROR", "-error")
        self.set_class(status != "ERROR", "-finished")
        self._paint()

    def _paint(self) -> None:
        width = max(16, (self.size.width or 34) - 4)
        out = Text()
        out.append(f"{self.agent_id}  ", style=f"bold {PALETTE['cyan']}")
        out.append(self.contributor + "\n", style="bold")
        if self.report is None:
            out.append(f"{self.stage_text}\n", style=PALETTE["warn"])
            out.append_text(bar(self.fraction, width, PALETTE["cyan"]))
        else:
            risk = float(self.report.get("risk_score", 0.0) or 0.0)
            color = TONE_COLORS[risk_tone(risk)][0]
            out.append(f"{self.report.get('verdict', '?')}  ", style=f"bold {color}")
            out.append(f"{self.report.get('num_findings', 0)} findings · "
                       f"{self.report.get('num_samples', 0)} images\n", style=PALETTE["muted"])
            out.append_text(bar(risk, width - 6, color))
            out.append(f"  {risk:.2f}", style=f"bold {color}")
        self.update(out)


class AgentsScreen(Screen):
    """Live agent board (or a saved one) plus the meeting room."""

    BINDINGS = [Binding("escape", "cancel", "Cancel / home")]

    def __init__(self, spec: OperationSpec, params: Optional[Dict[str, Any]],
                 result: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.spec = spec
        self.params = params or {}
        self.result = result
        self.token = CancelToken()
        self.status = "finished" if result is not None else "running"
        self.cards: Dict[str, AgentCard] = {}
        self.meeting_text = ""

    @property
    def is_running(self) -> bool:
        return self.status in ("running", "stopping")

    def compose(self) -> ComposeResult:
        head = gradient_text("⚇  CONTRIBUTOR AGENTS", PALETTE["cyan"], PALETTE["violet"])
        head.append(f"   {self.params.get('target') or (self.result or {}).get('root', '')}",
                    style=PALETTE["muted"])
        yield Static(head, id="run-header")
        with VerticalScroll():
            yield Grid(id="agent-grid")
            yield Static("", id="run-status")
            with Vertical(id="meeting"):
                yield Sized(lambda w: Text(""), id="meeting-banner")
                yield Static("", id="meeting-text")
        yield Footer()

    def on_mount(self) -> None:
        if self.result is not None:
            self._show_final(self.result)
            return
        self.query_one("#run-status", Static).update("Agents starting…")
        self._discover_cards()
        self._work()

    def _card(self, contributor: str) -> AgentCard:
        if contributor not in self.cards:
            card = AgentCard(contributor, f"AGENT-{len(self.cards) + 1:02d}")
            self.cards[contributor] = card
            self.query_one("#agent-grid", Grid).mount(card)
        return self.cards[contributor]

    def _discover_cards(self) -> None:
        target = self.params.get("target")
        if not target:
            return
        try:
            from src.agents.manager import OfficeManager
            for task in OfficeManager().discover(Path(target)):
                self._card(str(task["contributor"]))
        except Exception:  # cards are also created lazily from progress events
            pass

    @work(thread=True, exclusive=True, group="engine")
    def _work(self) -> None:
        try:
            outcome = execute(self.spec, self.params, self._from_thread, self.token,
                              getattr(self.app, "reports_dir", None))
        except ScanCancelled:
            self.app.call_from_thread(self._cancelled)
        except Exception as exc:
            self.app.call_from_thread(self._failed, f"{type(exc).__name__}: {exc}",
                                      traceback.format_exc())
        else:
            self.app.call_from_thread(self._finished, outcome)

    def _from_thread(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        self.app.call_from_thread(self._progress, stage, done, total, detail)

    def _progress(self, stage: str, done: int, total: int, detail: Optional[str]) -> None:
        if stage == "meeting":
            self.query_one("#run-status", Static).update("Meeting room: agents compare notes…")
            return
        if not detail:
            return
        card = self._card(detail)
        if stage == "finished":
            card.update_stage("finished", 1, 1)
        else:
            card.update_stage(stage, done, total)
        running = sum(1 for c in self.cards.values() if c.stage_text != "finished")
        self.query_one("#run-status", Static).update(
            f"{len(self.cards)} agents · {running} still working")

    def _finished(self, outcome: RunOutcome) -> None:
        self.result = outcome.result
        if outcome.save_error:
            self.app.notify(f"Report not saved: {outcome.save_error}", severity="error")
        self._show_final(outcome.result)

    def _show_final(self, office: Dict[str, Any]) -> None:
        self.status = "finished"
        for report in office.get("reports") or []:
            self._card(str(report.get("contributor", "?"))).finish(report)
        meeting = office.get("meeting") or {}
        head = headline("agents", office)
        self.query_one("#meeting-banner", Sized).set_draw(
            lambda w: banner_text(head.verdict, head.tone, "office verdict", w))
        lines = [escape(str(meeting.get("narrative", "")))]
        lines += [f"[bold]→ {escape(str(r))}[/bold]" for r in meeting.get("recommendations") or []]
        lines += [f"[red]! {escape(str(e))}[/red]" for e in office.get("errors") or []]
        self.meeting_text = "\n".join(lines)
        self.query_one("#meeting-text", Static).update(self.meeting_text)
        self.query_one("#run-status", Static).update(
            f"{office.get('agents', len(self.cards))} agents · {office.get('mode', '?')} mode · "
            f"{float(office.get('duration_seconds', 0.0)):.1f}s   [dim]Esc home[/dim]")
        self.add_class("-done")

    def _cancelled(self) -> None:
        self.status = "cancelled"
        self.app.notify("Agents cancelled — nothing was saved.")
        self.app.pop_screen()

    def _failed(self, message: str, trace: str) -> None:
        self.status = "failed"
        self.query_one("#run-status", Static).update(
            f"[bold red]Agents stopped with an error:[/bold red] {escape(message)}   "
            f"[dim]Esc back[/dim]")

    def action_cancel(self) -> None:
        if self.status == "running":
            self.app.push_screen(ConfirmModal("Stop all agents? Partial results are discarded."),
                                 self._confirm)
        elif self.status == "finished":
            self.app.go_home()
        elif self.status in ("failed", "cancelled"):
            self.app.pop_screen()

    def _confirm(self, stop: Optional[bool]) -> None:
        if stop and self.status == "running":
            self.status = "stopping"
            self.query_one("#run-status", Static).update("Stopping at the next checkpoint…")
            self.token.cancel()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/tui/test_app_agents.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Run all TUI tests**

Run: `python -m pytest tests/tui -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/tui/screens/agents.py tests/tui/test_app_agents.py
git commit -m "feat(tui): live agent board with meeting-room verdict"
```

---

### Task 11: Regression check, real end-to-end run, screenshots

**Files:**
- Create: `tests/tui/e2e_screens.py`
- Modify: none (fix-forward only if a check fails)

**Interfaces:**
- Consumes: `ShieldApp` (Task 6), real `OPERATIONS_BY_ID` (Task 4), screens from Tasks 7–10.
- Produces: SVG screenshots in `output/tui_screens/` (git-ignored by being under `output/`).

- [ ] **Step 1: Write the end-to-end script**

`tests/tui/e2e_screens.py`:

```python
"""Drive the real console headless against demo data and save SVG screenshots.

Run:  python tests/tui/e2e_screens.py
Not collected by pytest (no test_ prefix): it runs real engines and takes minutes.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.tui.app import ShieldApp  # noqa: E402
from src.tui.operations import OPERATIONS_BY_ID  # noqa: E402
from src.tui.screens.results import ResultsScreen  # noqa: E402

OUT = ROOT / "output" / "tui_screens"
JOBS = [
    ("scan", {"target": ROOT / "demo/data/poisoned", "max_images": 100}),
    ("audit", {"target": ROOT / "demo/models/backdoored_model_scripted.pt", "reference": None,
               "neural_cleanse": True}),
    ("verify", {"target": ROOT / "demo/records/tampered_replay.json"}),
]


async def wait(pilot, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await pilot.pause(0.2)
        if predicate():
            return True
    return False


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = ShieldApp(splash=False)
    failures = 0
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause(0.5)
        app.save_screenshot(path=str(OUT), filename="01-home.svg")
        for index, (op_id, params) in enumerate(JOBS, start=2):
            started = time.monotonic()
            app.start_run(OPERATIONS_BY_ID[op_id], params)
            await pilot.pause(2.0)
            app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-running.svg")
            ok = await wait(pilot, lambda: isinstance(app.screen, ResultsScreen), 900)
            took = time.monotonic() - started
            if not ok:
                failures += 1
                print(f"FAIL {op_id}: no results after {took:.0f}s (screen={type(app.screen).__name__})")
                app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-FAILED.svg")
                app.go_home()
                continue
            await pilot.pause(1.0)
            head = app.screen.head
            print(f"ok   {op_id}: {head.verdict} risk={head.risk} in {took:.0f}s")
            app.save_screenshot(path=str(OUT), filename=f"{index:02d}-{op_id}-results.svg")
            app.go_home()
            await pilot.pause(0.5)
    print(f"screenshots: {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Run the end-to-end script**

Run: `python tests/tui/e2e_screens.py` (timeout 30 min)
Expected: three `ok` lines — scan `COMPROMISED`/`SUSPICIOUS`/`CAUTION` (anything but INCONCLUSIVE), audit `COMPROMISED` or `SUSPICIOUS` for the backdoored model, verify `BROKEN` for `tampered_replay.json`; SVGs written to `output/tui_screens/`. If a verdict looks wrong, compare with `python run.py scan <same target>` — the TUI must match the CLI, not the other way round.

- [ ] **Step 3: Regression — scripted CLI and existing suites unchanged**

Run each and record exit codes:
```
python run.py scan demo/records/clean_chain.json ; echo "exit=$?"      # expect exit=0
python run.py scan demo/records/tampered_replay.json ; echo "exit=$?"  # expect exit 1 or 2 (non-zero, same as before this branch)
python tests/test_edge_cases.py                                         # expect no FAIL lines
python demo/validate_phase2.py                                          # expect same pass summary as on main
python -m pytest tests/tui -q                                           # expect all pass
```
To compare with `main`, run the two `run.py` commands once on `git stash`-free `main` in a worktree first if any exit code is in doubt.

- [ ] **Step 4: Manual smoke in a real terminal (record what you see)**

Run: `python shield.py` in Windows Terminal at ≥ 120×36. Check: splash animates ~1s; arrows move between tiles; `d` opens Scan with `demo/data/poisoned` preselected; Ctrl+R runs; stage rows animate; results banner is coloured; a TRIGGER_INJECTION finding shows its image (sixel in Windows Terminal; half-blocks elsewhere); `Ctrl+P` shows "Scan demo/data/…" entries; `q` quits. Then `python shield.py --no-splash` and `shield` from another folder.

- [ ] **Step 5: Commit**

```bash
git add tests/tui/e2e_screens.py
git commit -m "test(tui): headless end-to-end run against demo data with screenshots"
```
