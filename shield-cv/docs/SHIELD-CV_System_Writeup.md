# SHIELD-CV — System Workflow and Architecture

**Secure Holistic Integrity Evaluation Layer for Defence Computer Vision**
RoboVeda Hackathon · Defence AI track · Theme: Blockchain & Cybersecurity

---

## 1. The problem in one paragraph

A defence computer-vision system (a drone that tells vehicles apart, a checkpoint camera that spots weapons) is built from things the army did not make itself: **training photos** collected by many vendors, a **model** trained by someone else, and the **results** it produces in the field. An enemy only has to tamper with one of these. Poison a few training photos, hide a "backdoor" in the model, or edit the logs afterwards, and the system still passes every normal test while being quietly under the enemy's control. SHIELD-CV is the **inspection layer** that sits in front of all three and answers: *can we trust this data, this model and this record trail, and if not, exactly what is wrong and who did it?*

## 2. Design principles (the rules every part obeys)

| Principle | What it means in practice |
|---|---|
| **Inspect, never retrain** | SHIELD never changes a contributed model and never trains its own. It uses a *frozen* ResNet-18 as fixed "eyes", always in evaluation mode with gradients off. |
| **100% offline** | Runs air-gapped on an ordinary CPU (8 GB laptop). The only optional network call is to a local language model on loopback, and a template briefing is the accredited default. |
| **Unassessed is not clean** | If something could not be checked, SHIELD says **NOT ASSESSED**, never "clean". An unreadable dataset or model cannot pass as safe. |
| **Every finding is explainable** | Each finding carries a plain reason, numeric evidence, the threshold used, a confidence and a recommended action. |
| **Severity beats volume** | One CRITICAL finding hurts the score far more than twenty LOW ones. |
| **Tamper-evident output** | Reports are hashed; provenance records are hash-chained and signed with Ed25519; the audit log is itself hash-chained. |
| **Humans stay in charge** | Nothing is deleted automatically. A person approves or rejects, and reject is a reversible quarantine. |

## 3. Architecture at a glance

```
                          ┌──────────────────────────── INTERFACES ───────────────────────────┐
                          │  Console (full-screen)   Scripted CLI      Dashboard (browser)    │
                          │  shield                  shield scan ...   shield dashboard       │
                          │  + Backdoor demo (b)     shield review     + Attack Lab, demos    │
                          └──────────────┬────────────────────┬───────────────────┬───────────┘
                                         │                    │                   │
   ┌─────────────────────────────────────▼────────────────────▼───────────────────▼──────────┐
   │                                  ORCHESTRATION                                          │
   │   operations registry · progress + cancel · office manager (one agent per contributor)  │
   └───────┬───────────────────┬────────────────────┬────────────────────┬───────────────────┘
           │                   │                    │                    │
   ┌───────▼───────┐   ┌───────▼───────┐   ┌────────▼────────┐   ┌───────▼───────┐
   │ MODULE 1      │   │ MODULE 2      │   │ MODULE 3        │   │ MODULE 4      │
   │ DATA          │   │ MODEL         │   │ PROVENANCE      │   │ DRIFT         │
   │ integrity     │   │ integrity     │   │ chain           │   │ monitor       │
   │ (5 detectors) │   │ (backdoors)   │   │ (hash + sign)   │   │ (natural vs   │
   └───────┬───────┘   └───────┬───────┘   └────────┬────────┘   │  manipulated) │
           │                   │                    │            └───────┬───────┘
           └───────────────────┴─────────┬──────────┴────────────────────┘
                                         │   one common Finding format
                              ┌──────────▼───────────┐
                              │   INTELLIGENCE       │   threat story · immunity score · briefing
                              └──────────┬───────────┘
                              ┌──────────▼───────────┐
                              │   REPORT + AUDIT     │   signed report · SQLite audit trail
                              └──────────┬───────────┘
                              ┌──────────▼───────────┐
                              │   HUMAN REVIEW       │   approve / reject → quarantine (undoable)
                              └──────────────────────┘

   Shared foundations:  frozen ResNet-18 embeddings · robust statistics (median/MAD) ·
                        crypto (SHA-256, Merkle, Ed25519) · config/settings.yaml (all thresholds)
```

## 4. End-to-end workflow

1. **Collect.** The operator points SHIELD at what arrived: a dataset folder (YOLO or COCO), a model file (`.pt`, `.onnx`), a records file (signed inference log), and optionally a baseline dataset.
2. **Scan each part.** The four modules run (each shows real progress and can be cancelled), and each produces findings in the *same* format.
3. **Compare contributors.** For datasets, one agent scans each vendor's folder separately, then a "meeting room" compares them.
4. **Correlate.** The intelligence layer connects findings across modules into a story and computes one 0–100 trust score.
5. **Report.** A signed report is written, with a coverage statement saying what was and was not checked.
6. **Review.** A person looks at each flagged photo, then **Approves** it or **Rejects** it. Rejected photos move into a quarantine folder.
7. **Rescan.** The dataset (now without the quarantined photos) is scanned again, and the risk drops. Undo can restore anything.

## 5. The components

### 5.1 Module 1 — Data integrity (are the training photos poisoned?)

A frozen ResNet-18 turns every photo into 512 numbers (its "fingerprint"). Five detectors then look for different kinds of poisoning:

| Attack | What it is | How it is detected |
|---|---|---|
| **Trigger injection** | A hidden mark (patch) pasted on photos to plant a backdoor | Three methods vote: FFT high-frequency energy, 16×16 block variance and gradient anomalies, and SVD spectral signatures (modified Z-score > 2.0) |
| **Label flipping** | Photos given the wrong label | Distance from the class centroid (> mean + 2σ) plus nearest-neighbour vote |
| **Near-duplicate flooding** | Many copies of a photo to bias training | Perceptual hash, Hamming distance < 5, union-find clustering, confirmed with SSIM |
| **Out-of-distribution** | Photos that do not belong | Mahalanobis distance and an energy score |
| **Systematic mislabelling** | A whole group of photos mislabelled | Confident-learning idea using nearest-centroid soft labels (no retraining) |

All statistics use **median/MAD instead of mean/standard deviation**, because a poisoned dataset drags ordinary averages toward the attacker.

**Contributor risk.** Photo-level findings are rolled up into a risk score per vendor, which is what actually drives a procurement decision.

**Agents and the meeting room.** Each vendor's folder gets its own agent (a thread sharing one loaded backbone), so a vendor who poisons heavily cannot pull the shared baseline toward themselves. The **meeting room** then compares the agents' reports, looking for: one vendor standing far above the rest, several vendors attacking the *same* class (strong evidence of coordination), a nominally trusted source behaving worse than an unverified one, and models that disagree on the same inputs.

### 5.2 Module 2 — Model integrity (is the model backdoored?)

The auditor first works out **how much access it has**, and only runs what that supports. It states the rest as *not available*.

| Access | What it can run |
|---|---|
| **White-box** (weights readable) | Weight hash (substitution check), per-layer statistics, **Neural Cleanse**, activation clustering, behavioural fingerprint |
| **Grey-box** (weights, no runnable graph) | The above except behavioural probing |
| **Black-box** (prediction API only) | Behaviour compared with a reference model (> 5 % mismatch), output-confidence shape |

*Neural Cleanse* searches, for every class, for the smallest change that forces every input into that class. A backdoored class is reachable through the attacker's tiny trigger, so its change is an outlier (MAD anomaly index > 2.0). It needs only forward passes and gradients on the input; the model's weights are never updated.

### 5.3 Module 3 — Inference provenance (can the results be trusted afterwards?)

Every inference is stored as a record containing hashes of the input image, the model weights, the configuration and the output, plus a nanosecond timestamp, a sequence number, a 256-bit nonce, the hash of the previous record (the **chain**) and an **Ed25519 signature**. Four independent checks exist because tampering fails in different ways:

- **Chain integrity:** were records inserted, deleted or reordered?
- **Tamper detection:** was a field edited afterwards?
- **Replay detection:** was an old valid record re-submitted?
- **Signature check:** was it produced by the holder of the key? (A tamperer who recomputes the hashes still fails here.)

A **Merkle tree** lets an analyst prove "this record was in the batch" with a handful of hashes. Keys are stored locally with owner-only permissions.

### 5.4 Module 4 — Drift (did the data change naturally, or was it manipulated?)

Compares a baseline dataset with current data and decides *why* it moved: **natural operational drift** (new season, new sensor, where brightness, warmth and sharpness move together, so recalibrate) versus **suspicious manipulation** (feature change with no matching pixel-level explanation, collapsed variance, or a change concentrated in a few samples, so investigate).

### 5.5 Intelligence layer

- **Threat story.** Looks across all modules for structure no single module can see: a poisoned dataset, a backdoored model and a tampered record that all point at the *same target class* are one campaign; several vendors using the same attack parameters suggest collusion; provenance tampering clustered with other findings suggests a cover-up.
- **Adversarial Immunity Score (0–100).** A weighted score over four pillars (data, model, provenance, drift), turned into a band: **HARDENED / ADEQUATE / MARGINAL / COMPROMISED**. A pillar that was never assessed is flagged and caps the overall confidence, so an unchecked pipeline can never score 100.
- **Commander's briefing.** A short prose summary an officer can read in under a minute. A local language model is used if present; otherwise a deterministic template produces a complete briefing on its own.

### 5.6 Findings, reports and the audit trail

Every detector emits the same **Finding**: id, attack class, affected asset, severity (CRITICAL / HIGH / MEDIUM / LOW / INFO), confidence, reason, evidence, and a recommended disposition (**QUARANTINE** at confidence ≥ 0.80, **REVIEW** at ≥ 0.50, otherwise **ACCEPT**). The report generator assembles one authoritative report with a **coverage statement** (what was *and was not* assessed), aggregated limitations, a schema validation, and a SHA-256 report hash. Scans, findings and contributor risk are stored in SQLite (`shield.db`) using parameterised queries only, with an **append-only audit log whose rows are hash-chained**, so a silent edit or deletion is detectable.

### 5.7 Human review: Approve and Reject (new)

For each flagged photo a person chooses:

- **Approve** records "checked, fine". The photo is not touched.
- **Reject** moves the photo (and its YOLO label file) into `<dataset>/_quarantine/`, keeping its folder path, and logs a fingerprint. **Undo** restores it byte for byte. Rejecting a photo marks *every* finding about it as rejected, because several detectors often flag the same image.

Safety rules are enforced once, in one core module, for all three interfaces: nothing outside the dataset folder is touched, symbolic links are refused, a file name that matches more than one photo is refused instead of guessed, only findings about photos can be rejected, and Undo never overwrites a file. Later scans **ignore** the quarantine folder.

### 5.8 Interfaces

| Interface | Command | What it is for |
|---|---|---|
| **Console** (full-screen) | `shield` | Daily operator use: home screen with tiles, pick targets from lists (no typing paths), live per-stage progress, Esc to cancel, a results screen with a verdict banner, a findings browser with the flagged image shown in the terminal, and keys `a` approve, `x` reject, `u` undo, `b` bulk review |
| **Scripted CLI** | `shield scan`, `audit`, `verify`, `drift`, `report`, `agents`, `review` | Automation and CI, with exit codes. `shield review` is a dry run unless `--yes` |
| **Dashboard** | `shield dashboard` | Browser view for presentations: Attack Lab (judges poison an image live), Backdoor story, data/model/crypto/drift/threat-story tabs, and the Approve / Reject panel |
| **Backdoor demo** | `b` in the console | A five-step plain-language story for non-technical audiences (see below) |

**The Backdoor demo.** Step 1 explains a backdoored model as a student secretly taught one cheating rule. Steps 2–3 show **real held-out photos** run through a safe model and a backdoored model: both answer correctly normally (94 % and 81 %), but when a small pink sticker is added the backdoored model is hijacked to the attacker's answer ("backpack") **69 %** of the time versus **3 %** for the safe model. Step 4 gives the drone example. Step 5 runs the **real audit** on the lab models and explains the verdict in plain words.

## 6. How the code is organised

```
shield-cv/
  src/
    scanners/      the 4 modules: data_scanner, model_auditor, crypto_chain, drift_detector, trigger_detector
    analysis/      embeddings (frozen ResNet-18), spectral, frequency, outlier, statistics, neural_cleanse
    agents/        agent (per contributor), manager (one agent per vendor), meeting (cross-vendor)
    intelligence/  threat_story, immunity (AIS score), briefing
    reporting/     schema (Finding), report_generator (signed report)
    crypto/        hashing (SHA-256), chain, merkle, signing (Ed25519)
    loaders/       YOLO, COCO, record and model loaders
    review/        store (approve/reject/undo core), cli, dashboard_panel
    tui/           the full-screen console: app, screens, widgets, operations, discovery, backdoor demo
    database.py    SQLite + hash-chained audit log        config.py   settings loader
    dashboard.py   Streamlit dashboard                    cli.py      scripted commands
  attacks/         attack generators used for demos and tests (trigger, label flip, duplicates, backdoor, tamper)
  config/          settings.yaml (every threshold and path), thresholds.yaml, contributors.yaml
  demo/            demo datasets, models (stripe lab pair + real-photo pair), record chains, Attack Lab, validators
  tests/           console, review and edge-case suites
```

## 7. Verified results

| Check | Result |
|---|---|
| Poisoned demo dataset scan | **COMPROMISED**, risk 0.97 (20 findings in a 100-image sample) |
| Provenance chain with a replayed record | **BROKEN** (risk 0.91) |
| Lab backdoored model | **BACKDOOR FOUND**, with the attacker's chosen class flagged; the clean twin is **CLEAN** |
| Review on a real scan (copy of the poisoned set) | Rejecting the CRITICAL + HIGH photos took 284 → 256 photos; the rescan fell from 71 to **36 findings**, verdict **COMPROMISED → SUSPICIOUS**; Undo restored every photo identical to the original |
| Original validation suite | 23 of 23 checks pass; edge-case sweep 0 failures |
| New console and review tests | 166 pass |

## 8. Honest limitations

- **The model audit is reliable on the lab models but not yet on photo-trained models.** In our test on real-photo models with a planted backdoor, the audit raised a false alarm on the clean model in most runs and found the real trigger in only one of three runs. Improving this is the main next step. Because of it, the demo's inspection step uses the lab models and says so on screen.
- The demo photo models share the frozen ResNet-18 and differ in a small trained head; the backdoor there is data poisoning with a visible pink sticker, which is a simplified but realistic attack.
- Rejecting photos in **COCO-style datasets** moves the photo but does not edit the annotation file (a warning is shown).
- Reject is quarantine, not permanent deletion; purging the quarantine folder is a manual decision.
- The backdoored lab model is not perfect on normal pictures (about 80 % right), and the demo shows the real figures.

## 9. Running it

```
shield                       open the full-screen console   (b = backdoor demo)
shield scan <folder|model|records.json>
shield agents <dataset-root>      one agent per contributor + meeting room
shield report all            all four modules + correlated, signed report
shield review <report.json> --reject critical,high            (dry run)
shield review <report.json> --reject critical,high --yes      (apply)
shield review <report.json> --undo
shield dashboard             browser dashboard (Attack Lab, demos, review panel)
python demo/build_photo_models.py     rebuild the real-photo demo models
```

---

*One-sentence summary: SHIELD-CV inspects the three things a defence vision system depends on (its training data, its model, its record trail) without ever changing them, explains every problem it finds in plain evidence, and lets a human safely remove the poisoned photos and prove the result.*
