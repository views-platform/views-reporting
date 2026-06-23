
# Class Intent Contract: PredictionFrameLoader

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-002 (Topology — Ingestion is Layer 2), ADR-003 (Declarations over inference), ADR-006 (Intent Contracts), ADR-008 (Observability), ADR-012 (Prediction Data Ingestion), ADR-018 (frames as the data contract)

---

## 1. Purpose

> Load one rolling-origin's predictions from the **numpy PredictionFrame** storage format into per-target `views_frames.PredictionFrame`s.

`PredictionFrameLoader` is the Ingestion-layer (Layer 2) adapter for the numpy format produced by sample-estimate models (mixture baselines, HydraNet). It **constructs** a `views_frames.PredictionFrame` directly from the raw on-disk arrays (epic #137, #138) — no pipeline-core dataset, no `PredictionFrameConverter`.

Source: `views_reporting/loaders/prediction_frame_loader.py`.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** infer the storage format — the caller declares `prediction_frame` explicitly (ADR-003); this loader is only reached via the registry for that declared format.
- Does **not** read parquet — that is `DataFrameLoader`'s responsibility.
- Does **not** compute statistics, collapse samples to MAP, render, or assemble reports.
- Does **not** define or own the `PredictionFrame` format (owned by `views_frames`).
- Does **not** call `views_frames.PredictionFrame.load` — that expects a different on-disk layout (`values.npy` + `header.json`); this loader reads the pipeline-core layout (`y_pred.npy` + `identifiers.npz`) and constructs the frame directly.
- Does **not** discover which origins/paths exist — the caller supplies the path(s).

---

## 3. Responsibilities and Guarantees

- **Direct frame construction.** For each target in `targets`, loads `{path}/{target}/y_pred.npy` (an `(N, S)` float32 array) and `{path}/{target}/identifiers.npz` (integer `time` + `unit`), and constructs `PredictionFrame(y_pred, SpatioTemporalIndex(time, unit, level))`.
- **Per-target frames.** Returns `dict[target -> PredictionFrame]`; each frame is single-target by the `views_frames` contract.
- **Level → SpatialLevel.** The declared `level` (`cm`/`pgm`) maps to `SpatialLevel.CM`/`SpatialLevel.PGM`, which carries the time-first index names — no separate naming repair step is needed (the former `set_names`/`INDEX_NAMES` repair is gone).
- **Typed return.** `dict[str, PredictionFrame]`; `load_multi_origin` returns a list, one dict per path, in input order.
- **Fail-loud on unknown level.** A `level` not in `{cm, pgm}` raises `ValueError` before any I/O.

---

## 4. Inputs and Assumptions

- **`load_single_origin(path, level, targets)`** / **`load_multi_origin(paths, level, targets)`**:
  - `path` — a rolling-origin directory containing one subdirectory per target, each holding `y_pred.npy` (`(N, S)` float32) + `identifiers.npz` (`time`, `unit` int arrays).
  - `level` — `"cm"` or `"pgm"`; must be in `LEVELS`.
  - `targets` — non-empty list of target names; each must have a `{path}/{target}/` subdirectory.
- Assumes `identifiers.npz` holds `time` and `unit` arrays aligned row-for-row with `y_pred.npy` (verified against the red_ranger fixture).

---

## 5. Outputs and Side Effects

- **Output:** a `CMDataset`/`PGMDataset` (or a list thereof). Deterministic given the files on disk.
- **Side effects:** filesystem reads only (numpy `.npy`/`.npz`). No writes, no network, no logging, no global state mutation.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `level` not in `{cm, pgm}` | `ValueError` (lists valid levels) | `prediction_frame_loader.py`, level guard |
| Missing `{path}/{target}/`, `y_pred.npy`, or `identifiers.npz` | Raises from `np.load` (`FileNotFoundError`) | per-target load loop |
| **Empty `targets` list** | Returns an empty dict (no frames). | per-target loop |
| `y_pred`/`identifiers` row counts disagree | Raises from the `PredictionFrame` / `SpatioTemporalIndex` constructor (row-count validation) | construction |

Must never fail silently: unknown level, missing files, and frame-construction errors are all loud. The former converter-index-drift seam (register C-30) is **eliminated** — there is no index repair step.

---

## 7. Boundaries and Interactions

- **Depends on:** `views_frames` (`PredictionFrame`, `SpatioTemporalIndex`); `numpy`.
- **Depends on (internal):** `views_reporting.loaders._constants` (`LEVELS`).
- **Must not depend on:** Computation (statistics, reconciliation), Rendering (visualizations, mapping), or Composition (reports, templates) — Layers 3–5.
- **Trusts:** that the on-disk `y_pred.npy` + `identifiers.npz` layout matches the pipeline-core writer (the format boundary the frame round-trip is pinned against).

---

## 8. Examples of Correct Usage

```python
from views_frames import SpatialLevel
from views_reporting.loaders import load_predictions

# Single origin, CM level, one target
frames = load_predictions(
    prediction_format="prediction_frame",
    path=origin_dir,                      # contains lr_ged_sb/y_pred.npy + identifiers.npz
    level="cm",
    targets=["lr_ged_sb"],
)
assert frames["lr_ged_sb"].index.level == SpatialLevel.CM
```

```python
from views_reporting.loaders import load_prediction_sequence

datasets = load_prediction_sequence(
    prediction_format="prediction_frame",
    paths=[d for d in sorted(run_dir.glob("origin_*"))],
    level="pgm",
    targets=["lr_ged_sb"],
)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: pointing at a parquet file — this loader reads PredictionFrame
# directories, not parquet. Declare "dataframe" and use DataFrameLoader.
load_predictions("prediction_frame", Path("preds.parquet"), "cm", ["lr_ged_sb"])
```

```python
# WRONG: empty targets — returns an empty dict (no frames to render).
PredictionFrameLoader().load_single_origin(origin_dir, "cm", targets=[])
```

---

## 10. Test Alignment

- **Green:** `tests/test_loaders.py::TestPredictionFrameLoader` — single-origin load yields per-target `PredictionFrame`s with the right `sample_count`; the frame index level is `SpatialLevel.CM` with time-first `index_names`; multi-origin returns one dict per path.
- **Beige:** `tests/test_e2e_fixture.py` — real red_ranger fixtures (256 samples) loaded end-to-end into a forecast report (frame path).
- **Red:** unknown-level `ValueError`; missing-directory `FileNotFoundError`.
- Invariant tests must protect: direct frame construction (no converter), typed dict return, fail-loud on unknown level.

---

## 11. Evolution Notes

- The numpy PredictionFrame format is the pipeline's forward direction (ADR-012); this loader's importance grows as models migrate off parquet.
- Conformance (#140): once `assert_frame_contract` runs at ingestion, the constructed frames should be validated here against `CONFORMANCE_FLOOR`.
- If the on-disk layout ever converges with `views_frames.PredictionFrame.save`/`load`, the direct-construction path can be replaced by `PredictionFrame.load`.

---

## End of Contract

This document defines the **intended meaning** of `PredictionFrameLoader`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
