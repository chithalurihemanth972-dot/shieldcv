# SHIELD Console — full-screen terminal UI

Date: 2026-10-15
Status: approved in conversation, awaiting written-spec review

## 1. Intent

**Who:** defence operators who run SHIELD-CV checks every day on an air-gapped
Windows host.

**Problem today:** `shield` opens a typed `shield>` prompt. Paths are asked with
bare `input()` and no hints, the "Step N/8 OK" lines are printed before the
work runs (they are not real progress), and results are long plain tables that
cannot be explored afterwards.

**Outcome:** typing `shield` opens a full-screen, keyboard-first console where
every choice is *selected*, not typed: operations, targets, options. Progress is
real, the verdict is obvious at a glance, and every finding can be inspected —
including a picture of the flagged image — without leaving the terminal.

**Success criteria**

1. An operator can scan, audit, verify, drift-check, run agents and build the
   full report without typing a path or an option value.
2. Every progress bar is driven by the engine's own `(stage, done, total)`
   callback; nothing reports "done" before it is.
3. A running check can be cancelled with Esc.
4. A finding's reason, evidence, disposition and image are viewable in-app.
5. The scripted CLI (`shield scan <path> --json …`, all argparse subcommands,
   exit codes) behaves exactly as before.
6. 100% offline; new dependencies are pure-Python wheels.

**Non-goals:** a History screen (dropped — the home screen's Recent panel
covers it), changes to detection logic, replacing the Streamlit dashboard,
the Attack Lab or the demo scripts.

## 2. Screens

```
┌ ◆ SHIELD-CV · Integrity Console ─────────────── offline ● CPU ● 14:02 ┐
│ ╔═══════════╗ ╔═══════════╗ ╔═══════════╗                             │
│ ║ ▣ SCAN    ║ ║ ◉ AUDIT   ║ ║ ⛓ VERIFY  ║    Recent results            │
│ ║ dataset   ║ ║ model     ║ ║ chain     ║    poisoned   COMPROMISED 0.82│
│ ╚═══════════╝ ╚═══════════╝ ╚═══════════╝    clean_chain VALID      1h  │
│ ╔═══════════╗ ╔═══════════╗ ╔═══════════╗    tampered_* BROKEN     3h   │
│ ║ ≈ DRIFT   ║ ║ ⚇ AGENTS  ║ ║ ★ REPORT  ║                             │
│ ╚═══════════╝ ╚═══════════╝ ╚═══════════╝    ↗ Dashboard  ↗ Attack Lab │
└────────────────────────────────────────────────────────────────────────┘
 ←↑↓→ move  ⏎ open  d m v f a r jump  ctrl+p palette  ? help  q quit
```

| Screen | Contents |
|---|---|
| **Splash** | ~1 s SHIELD logo with a cyan→violet gradient sweep and a "scanning" line. Any key skips; `--no-splash` disables; auto-skipped below 80×24. |
| **Home** | 3×2 grid of tiles — Scan (`d`), Audit (`m`), Verify (`v`), Drift (`f`), Agents (`a`), Full Report (`r`); arrow keys or hotkey. **Recent results** panel: last 5 reports from `output/reports` with verdict chip, risk and age; Enter opens its Results screen. Launcher links for Dashboard, Attack Lab and Demo hand off to their existing scripts. |
| **Operation** | Target picker (auto-discovered candidates of the right kind with metadata, filter with `/`, plus **Browse…** directory tree) and options as selects/toggles — never free text. Run button disabled until the target is valid. Esc returns home. |
| **Run** | One row per real engine stage, each with its own bar, spinner→✓, elapsed and ETA; log tail beneath. Esc → confirm → cancel. |
| **Results** | Gradient verdict banner, risk gauge, stacked severity bar, per-contributor heat bars, per-detector score bars; findings table (sort, filter by severity / attack class); **Finding detail** pane: reason, evidence key-values, disposition, affected files, in-terminal **image preview** (duplicate clusters show members side by side), `o` opens the file in the system viewer; Contributors tab; `s` shows saved path, `e` exports. |
| **Agents** | Grid of live agent cards (stage, progress), then the meeting-room narrative, recommendations and office verdict. |
| **Full Report** | Checklist of the four modules, each with a target picker (demo defaults pre-selected); combined Run screen; then immunity score gauge, band, and the commander's briefing. |

Operation → options:

| Operation | Target kind | Options |
|---|---|---|
| Scan dataset | dataset folder | Max images: **all** / 100 / 250 / 500 / 1000 |
| Audit model | `.pt` `.pth` `.onnx` | Reference model (**none** / discovered models), Run Neural Cleanse (**on**/off) |
| Verify chain | `.json` `.jsonl` records | — |
| Drift | two dataset folders (baseline, current) | Max images: 60 / **120** / 250 / all |
| Agents | dataset root with contributor folders | — |
| Full report | one target per module, each skippable | Neural Cleanse on/off |

## 3. Architecture

New package `src/tui/`:

| Unit | Responsibility | Depends on |
|---|---|---|
| `discovery.py` | `discover(kind, roots) -> list[Candidate]`: candidate targets by kind with metadata (image count, contributor count, size, record count). Pure functions; roots are `demo/`, `output/`, and `SHIELD_CALLER_CWD`. | filesystem |
| `operations.py` | `OperationSpec` per operation: id, title, icon, hotkey, target kinds, option fields, expected stages, `run(params, on_progress, cancel) -> RunOutcome(result, report_path)`. The **only** module that imports engines. Saves reports as `output/reports/SHIELD-<KIND>-<timestamp>.json`, matching today's naming. | scanners, agents, intelligence, reporting |
| `recent.py` | `recent_reports(n) -> list[RecentItem]` (name, kind, verdict, risk, age, path); tolerates corrupt files. | filesystem |
| `widgets/` | `Tile`, `TargetPicker`, `StageProgress`, `VerdictBanner`, `RiskGauge`, `SeverityBar`, `HeatBars`, `FindingsTable`, `FindingDetail`, `ImagePreview` | Textual, textual-image |
| `screens/` | `Splash`, `Home`, `Operation`, `Run`, `Results`, `Agents`, `FullReport` | widgets, operations |
| `app.py`, `theme.tcss`, `__main__.py` | `ShieldApp`: bindings, theme, command palette provider (operations × discovered targets, "open last report") | screens |

**Run flow:** Operation screen builds `params` → pushes Run screen → Run starts a
Textual thread worker calling `spec.run()` → engine callback marshals to the UI
via `call_from_thread` and updates `StageProgress` → on completion the report is
saved and Results is pushed with the result dict.

**Cancellation:** add `src/utils/cancel.py` with `class ScanCancelled(Exception)`.
Each engine progress wrapper currently swallows every callback exception; add
one `except ScanCancelled: raise` clause before the existing `except Exception`
in `data_scanner`, `model_auditor`, `drift_detector` and `crypto_chain` (and in
`agents/manager` where its callbacks are wrapped). The UI's callback raises
`ScanCancelled` once the cancel flag is set, so the run stops at the next
progress tick. No detection logic changes.

**Entry points**

- `shield` / `shield start` → `python -m src.tui` (`shield.py` becomes a thin
  launcher calling `src.tui.app.main`).
- All other `shield.bat` subcommands and `run.py` / `src/cli.py` are unchanged.
- If `textual` cannot be imported or stdout is not a TTY, print a one-paragraph
  hint (install command for the offline wheel bundle, and `shield scan <path>`
  as the scripted alternative) and exit with code 2.
- The old prompt loop in `shield.py` is removed.

**Dependencies** (`requirements.txt`, Interface section): `textual>=8.2`,
`textual-image>=0.12` (sixel in Windows Terminal, half-block fallback
elsewhere; uses the existing Pillow).

## 4. Errors and edge cases

| Situation | Behaviour |
|---|---|
| Engine raises | Failed stage turns red; error panel with exception type + message, traceback folded (`t` expands); **Retry** / **Back**. App never exits to shell. |
| Engine returns an assessment-failed result | Amber **INCONCLUSIVE** banner plus the engine's limitations, never a misleading CLEAN. Uses the same rule as `src/cli.py:_assessment_failed`. |
| Discovery finds nothing | Picker states where it looked; **Browse…** is first. |
| Wrong kind picked in Browse | Inline red hint; Run disabled. |
| Image preview fails / unsupported | `[preview unavailable: <reason>]` + path; detail pane still renders. |
| Terminal < 80×24 | Centred "enlarge to at least 80×24" notice; splash skipped; layout reflows. |
| `q` during a run | Confirm "A scan is running — stop and quit?". |
| Report save fails | Toast with reason; results stay; `e` exports elsewhere. |
| Windows console | `ensure_utf8_stdio()`; ASCII fallbacks for tile glyphs. |
| Logging | Existing file logger only; nothing writes to stdout while the TUI runs. |

## 5. Testing

- **Unit (pytest, `tests/tui/`):** `discovery` on temp trees (dataset, model,
  records, empty, junk); `recent` on sample and corrupt reports; `operations`
  with fake engines — option mapping, report saving, cancel stops the run.
- **Engine cancel clause:** per engine, a callback raising `ScanCancelled`
  propagates; any other callback exception is still swallowed.
- **UI (Textual `App.run_test()` pilot):** splash skip; home navigation by
  arrows and hotkeys; pick → run (fake engine) → Results shows correct verdict
  and finding count; finding detail opens; Esc cancel; engine error panel;
  small-terminal notice.
- **Regression:** `tests/test_edge_cases.py`, `demo/validate_phase2.py`, and the
  argparse CLI exit codes unchanged.
- **Real end-to-end:** launch the app against `demo/data/poisoned`,
  `demo/models/backdoored_model_scripted.pt`, `demo/records/tampered_replay.json`
  and capture Textual SVG screenshots for sign-off.
