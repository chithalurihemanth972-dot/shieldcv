"""Approve / reject flagged photos, safely.

*Reject* never erases anything: it moves the photo (and its YOLO label file) into
``<dataset>/_quarantine/`` keeping its relative path, and writes a log entry with
a fingerprint, so *Undo* can put it back byte for byte. *Approve* only records
that a person checked the finding.

Safety rules enforced here, once, for every front-end (terminal console,
dashboard, scripted CLI):

* nothing outside the dataset folder is ever touched, and symbolic links are refused;
* a file name that matches more than one photo is refused, never guessed;
* only findings about a photo can be rejected;
* undo never overwrites a file that has since taken the original place.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from src.tui.discovery import IMAGE_EXTS, build_asset_index, resolve_assets
from src.utils.logger import get_logger

LOGGER = get_logger(__name__)
QUARANTINE_DIR = "_quarantine"
LOG_NAME = "review.json"
LOG_VERSION = 1

Finding = Mapping[str, Any]


class ReviewError(Exception):
    """A review action was refused; nothing was changed."""


def finding_key(finding: Finding) -> str:
    """A key that stays the same across re-scans (finding ids restart at FIND-001)."""
    return "|".join([str(finding.get("attack_class", "")), str(finding.get("affected_asset", "")),
                     str(finding.get("contributor") or "")])


@dataclass(frozen=True)
class Move:
    """One file to move into quarantine."""

    source: Path
    dest: Path
    kind: str  # "image" | "label"


@dataclass
class Decision:
    """What a person decided about one finding."""

    key: str
    finding_id: str
    decision: str            # "APPROVED" | "REJECTED"
    asset: str
    reason: str
    time: str
    moves: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """What a bulk reject would do (computed without changing anything)."""

    moves: List[Move] = field(default_factory=list)
    skipped: List[Tuple[Finding, str]] = field(default_factory=list)

    @property
    def files(self) -> int:
        """Number of photos that would be quarantined."""
        return sum(1 for m in self.moves if m.kind == "image")

    @property
    def labels(self) -> int:
        """Number of label files that would go with them."""
        return sum(1 for m in self.moves if m.kind == "label")


@dataclass
class BulkResult:
    """Outcome of a bulk action."""

    done: List[Decision] = field(default_factory=list)
    skipped: List[Tuple[Finding, str]] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class ReviewSession:
    """Review state for one dataset folder."""

    def __init__(self, dataset_root: Union[str, Path]) -> None:
        self.root = Path(dataset_root).resolve()
        if not self.root.is_dir():
            raise ReviewError(f"dataset folder not found: {dataset_root}")
        self.quarantine = self.root / QUARANTINE_DIR
        self.log_path = self.quarantine / LOG_NAME
        self.warnings: List[str] = []
        self._lock = threading.RLock()
        self._index: Optional[Dict[str, List[Path]]] = None
        self._data: Dict[str, Any] = self._load()

    # -- persistence -----------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        empty: Dict[str, Any] = {"version": LOG_VERSION, "decisions": {}, "history": []}
        if not self.log_path.is_file():
            return empty
        try:
            data = json.loads(self.log_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("decisions"), dict):
                raise ValueError("unexpected structure")
            data.setdefault("history", [])
            return data
        except (OSError, ValueError) as exc:
            aside = self.log_path.with_name(f"{LOG_NAME}.corrupt-{int(time.time())}")
            try:
                os.replace(self.log_path, aside)
            except OSError:
                pass
            self.warnings.append(f"The review log was unreadable ({exc}); it was set aside as "
                                 f"{aside.name} and a new one started. Quarantined files are "
                                 f"still in {QUARANTINE_DIR}/.")
            LOGGER.error("review log unreadable: %s", exc)
            return empty

    def _save(self) -> None:
        self.quarantine.mkdir(parents=True, exist_ok=True)
        temp = self.log_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        os.replace(temp, self.log_path)

    def _event(self, event: str, key: str, finding_id: str) -> None:
        self._data["history"].append({"event": event, "key": key, "finding_id": finding_id,
                                      "time": time.strftime("%Y-%m-%dT%H:%M:%S")})

    # -- status ------------------------------------------------------------------
    def status(self, finding: Finding) -> str:
        """``"APPROVED"``, ``"REJECTED"`` or ``"pending"``."""
        entry = self._data["decisions"].get(finding_key(finding))
        return str(entry["decision"]) if entry else "pending"

    def decisions(self) -> Dict[str, Decision]:
        """Every recorded decision, by finding key."""
        return {k: Decision(key=k, finding_id=str(v.get("finding_id", "")),
                            decision=str(v["decision"]), asset=str(v.get("asset", "")),
                            reason=str(v.get("reason", "")), time=str(v.get("time", "")),
                            moves=list(v.get("moves") or []), warnings=list(v.get("warnings") or []))
                for k, v in self._data["decisions"].items()}

    # -- resolving a finding to a file ---------------------------------------------
    def _asset_index(self) -> Dict[str, List[Path]]:
        if self._index is None:
            self._index = build_asset_index(self.root)
        return self._index

    def _resolve(self, finding: Finding) -> Path:
        asset = str(finding.get("affected_asset") or "")
        asset_type = finding.get("asset_type") or finding.get("affected_asset_type")
        if asset_type not in (None, "image") or Path(asset).suffix.lower() not in IMAGE_EXTS:
            raise ReviewError("this finding is not about a photo, so there is nothing to move")
        contributor = finding.get("contributor")
        matches = resolve_assets(asset, self._asset_index(), self.root,
                                 str(contributor) if contributor else None)
        matches = [m for m in matches if QUARANTINE_DIR not in m.parts]
        if not matches:
            raise ReviewError(f"photo not found in the dataset: {asset} "
                              f"(already moved or deleted?)")
        if len(matches) > 1:
            raise ReviewError(f"more than one photo is named {Path(asset).name} "
                              f"({len(matches)} files) and the finding does not say which "
                              f"contributor's it is, so nothing was moved")
        path = matches[0]
        if path.is_symlink():
            raise ReviewError(f"{path.name} is a symbolic link; refusing to move it")
        resolved = path.resolve()
        if not _inside(resolved, self.root):
            raise ReviewError(f"{asset} is outside the dataset folder; refusing to touch it")
        if not resolved.is_file():
            raise ReviewError(f"{asset} is not a regular file")
        return resolved

    def _label_for(self, image: Path) -> Optional[Path]:
        """The YOLO label file that belongs to ``image``, if there is one."""
        candidates = [image.with_suffix(".txt")]
        parts = image.parts
        if "images" in parts:
            index = len(parts) - 1 - parts[::-1].index("images")
            candidates.append(Path(*parts[:index], "labels", *parts[index + 1:]).with_suffix(".txt"))
        for label in candidates:
            if label.is_file() and not label.is_symlink() and _inside(label.resolve(), self.root):
                return label.resolve()
        return None

    def _dest(self, source: Path) -> Path:
        dest = self.quarantine / source.relative_to(self.root)
        counter = 1
        while dest.exists():
            dest = dest.with_name(f"{source.stem}.{counter}{source.suffix}")
            counter += 1
        return dest

    def plan(self, finding: Finding) -> List[Move]:
        """The moves a reject would make. Raises :class:`ReviewError` if refused."""
        if self.status(finding) == "REJECTED":
            raise ReviewError("already rejected (undo it first)")
        image = self._resolve(finding)
        moves = [Move(image, self._dest(image), "image")]
        label = self._label_for(image)
        if label is not None:
            moves.append(Move(label, self._dest(label), "label"))
        return moves

    def can_reject(self, finding: Finding) -> Tuple[bool, str]:
        """Whether Reject is available for ``finding`` and, if not, why."""
        try:
            self.plan(finding)
            return True, ""
        except ReviewError as exc:
            return False, str(exc)

    # -- actions ---------------------------------------------------------------------
    def reject(self, finding: Finding, reason: str = "") -> Decision:
        """Quarantine the flagged photo (and its label file)."""
        with self._lock:
            moves = self.plan(finding)
            hashes = {str(m.source): _sha256(m.source) for m in moves}
            done: List[Move] = []
            try:
                for move in moves:
                    move.dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(move.source, move.dest)
                    done.append(move)
                decision = Decision(
                    key=finding_key(finding), finding_id=str(finding.get("finding_id", "")),
                    decision="REJECTED", asset=str(finding.get("affected_asset", "")),
                    reason=reason or str(finding.get("reason", ""))[:200],
                    time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    moves=[{"kind": m.kind, "from": str(m.source.relative_to(self.root)),
                            "to": str(m.dest.relative_to(self.root)),
                            "sha256": hashes[str(m.source)]} for m in moves],
                    warnings=self._annotation_warnings(moves))
                self._data["decisions"][decision.key] = {
                    k: v for k, v in decision.__dict__.items() if k != "key"}
                self._event("reject", decision.key, decision.finding_id)
                self._save()
            except Exception as exc:  # put everything back; never leave a half-done move
                for move in reversed(done):
                    try:
                        os.replace(move.dest, move.source)
                    except OSError:
                        LOGGER.error("rollback failed for %s", move.source)
                self._data["decisions"].pop(finding_key(finding), None)
                raise ReviewError(f"could not quarantine {finding.get('affected_asset')}: {exc}") from exc
            self._index = None
            return decision

    def _annotation_warnings(self, moves: Sequence[Move]) -> List[str]:
        if any(m.kind == "label" for m in moves):
            return []
        has_annotations = (self.root / "annotations").is_dir() or any(
            p.suffix.lower() == ".json" for p in self.root.glob("*.json"))
        return (["This dataset uses annotation files (COCO-style); the photo's entry in the "
                 "annotation file was not edited."] if has_annotations else [])

    def approve(self, finding: Finding, note: str = "") -> Decision:
        """Record that a person checked this finding and it is fine. Touches no file."""
        with self._lock:
            if self.status(finding) == "REJECTED":
                raise ReviewError("already rejected (undo it first)")
            decision = Decision(
                key=finding_key(finding), finding_id=str(finding.get("finding_id", "")),
                decision="APPROVED", asset=str(finding.get("affected_asset", "")), reason=note,
                time=time.strftime("%Y-%m-%dT%H:%M:%S"))
            self._data["decisions"][decision.key] = {
                k: v for k, v in decision.__dict__.items() if k != "key"}
            self._event("approve", decision.key, decision.finding_id)
            self._save()
            return decision

    def undo(self, finding_or_key: Union[Finding, str]) -> Decision:
        """Put a rejected photo back, or clear an approval."""
        with self._lock:
            key = finding_or_key if isinstance(finding_or_key, str) else finding_key(finding_or_key)
            entry = self._data["decisions"].get(key)
            if not entry:
                raise ReviewError("nothing to undo for this finding")
            moves = entry.get("moves") or []
            plan = []
            for item in moves:
                source, dest = self.root / item["to"], self.root / item["from"]
                if not source.is_file():
                    raise ReviewError(f"the quarantined file is missing: {item['to']}")
                if dest.exists():
                    raise ReviewError(f"cannot restore {item['from']}: a file already exists "
                                      f"there (nothing was overwritten)")
                plan.append((source, dest))
            done: List[Tuple[Path, Path]] = []
            try:
                for source, dest in plan:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, dest)
                    done.append((source, dest))
                finding_id = str(entry.get("finding_id", ""))
                restored = Decision(key=key, finding_id=finding_id, decision=str(entry["decision"]),
                                    asset=str(entry.get("asset", "")), reason=str(entry.get("reason", "")),
                                    time=str(entry.get("time", "")), moves=list(moves))
                del self._data["decisions"][key]
                self._event("undo", key, finding_id)
                self._save()
            except Exception as exc:
                for source, dest in reversed(done):
                    try:
                        os.replace(dest, source)
                    except OSError:
                        LOGGER.error("undo rollback failed for %s", dest)
                self._data["decisions"][key] = entry
                raise ReviewError(f"could not restore: {exc}") from exc
            for source, _ in plan:  # tidy empty folders inside the quarantine
                folder = source.parent
                while folder != self.quarantine and folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    folder = folder.parent
            self._index = None
            return restored

    def undo_all(self) -> List[Decision]:
        """Restore every rejected photo (approvals are cleared too)."""
        restored: List[Decision] = []
        for key in list(self._data["decisions"]):
            try:
                restored.append(self.undo(key))
            except ReviewError as exc:
                self.warnings.append(f"{key}: {exc}")
        return restored

    # -- bulk ------------------------------------------------------------------------
    @staticmethod
    def _severity(finding: Finding) -> str:
        return str(finding.get("severity", "")).upper()

    def pending(self, findings: Iterable[Finding], severities: Sequence[str]) -> List[Finding]:
        """Undecided findings of the given severities (for bulk approve)."""
        wanted = {s.upper() for s in severities}
        return [f for f in findings if self._severity(f) in wanted and self.status(f) == "pending"]

    def select(self, findings: Iterable[Finding], severities: Sequence[str]) -> List[Finding]:
        """Undecided findings of the given severities that Reject can act on."""
        return [f for f in self.pending(findings, severities) if self.can_reject(f)[0]]

    def plan_many(self, findings: Iterable[Finding]) -> Plan:
        """What rejecting all of ``findings`` would do, without doing it."""
        plan = Plan()
        seen = set()
        for finding in findings:
            try:
                moves = self.plan(finding)
            except ReviewError as exc:
                plan.skipped.append((finding, str(exc)))
                continue
            if moves[0].source in seen:
                plan.skipped.append((finding, "same photo as an earlier finding in this batch"))
                continue
            seen.update(m.source for m in moves)
            plan.moves.extend(moves)
        return plan

    def reject_many(self, findings: Iterable[Finding], reason: str = "") -> BulkResult:
        """Reject each finding; one failure never stops the rest."""
        result = BulkResult()
        for finding in findings:
            try:
                result.done.append(self.reject(finding, reason))
            except ReviewError as exc:
                result.skipped.append((finding, str(exc)))
        return result

    def approve_many(self, findings: Iterable[Finding], note: str = "") -> BulkResult:
        """Approve each finding."""
        result = BulkResult()
        for finding in findings:
            try:
                result.done.append(self.approve(finding, note))
            except ReviewError as exc:
                result.skipped.append((finding, str(exc)))
        return result
