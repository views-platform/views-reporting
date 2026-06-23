
# Class Intent Contract: DataFrameLoader

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-002 (Topology — Ingestion is Layer 2), ADR-003 (Declarations over inference), ADR-006 (Intent Contracts), ADR-012 (Prediction Data Ingestion), ADR-018 (frames as the data contract)

---

## 1. Purpose

> Load one rolling-origin's predictions from the **parquet DataFrame** storage format into per-target `views_frames.PredictionFrame`s.

`DataFrameLoader` is the Ingestion-layer (Layer 2) adapter for the parquet format produced by point-estimate models (the average/locf baselines). It reads the parquet and builds one `PredictionFrame` per requested target via the shared `frames_from_dataframe` helper (epic #137, #138).

It also hosts the in-memory DataFrame → frame helpers **`frames_from_dataframe(df, level, targets)`** and **`target_frame_from_dataframe(df, level, target)`** the report templates use to convert pre-loaded forecast/historical DataFrames into frames.

Source: `views_reporting/loaders/dataframe_loader.py`.

> **Triviality note.** This class is close to trivial — a `pd.read_parquet` plus a dataset constructor, with no domain logic or invariant beyond the level guard. A CIC is provided for full ingestion-surface coverage (per the 2026-06-04 decision on issue #77), not because the class is independently complex. The value of the Ingestion layer lives in the dispatch contract (`cic_loader_protocol_and_registry.md`) and in `PredictionFrameLoader`, not here.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** infer the storage format — reached only when the caller declares `dataframe` (ADR-003).
- Does **not** read numpy PredictionFrame directories — that is `PredictionFrameLoader`.
- Does **not** validate the DataFrame's structure (index names, columns, cell shapes) — that is delegated to the `CMDataset`/`PGMDataset` constructor.
- Does **not** compute, render, or assemble anything.

---

## 3. Responsibilities and Guarantees

- **Read + construct.** `pd.read_parquet(path)` then `frames_from_dataframe(df, level, targets)` → `dict[target -> PredictionFrame]`.
- **Per-target frames.** For each requested target, the `pred_{target}` column's cells (scalar point estimates → S == 1, or sample arrays → S == sample_count) are stacked into an `(N, S)` frame on a per-row `(time, entity)` index read **positionally** (level 0 time, level 1 entity — so a PGM parquet named `priogrid_gid` still loads).
- **Fail-loud on unknown level.** `level` not in `{cm, pgm}` (the `LEVELS` table) raises `ValueError` before reading.
- **Fail-loud on no predictions.** When **none** of the requested `pred_{target}` columns are present, `frames_from_dataframe` raises `ValueError` ("No usable prediction columns…"). The evaluation template's C-32 graceful per-sequence skip depends on this contract.
- **Typed return.** `dict[str, PredictionFrame]`; `load_multi_origin` returns one dict per path, in order.

---

## 4. Inputs and Assumptions

- `path` — a parquet file whose contents satisfy the `CMDataset`/`PGMDataset` constructor (correct MultiIndex, `pred_{target}` columns).
- `level` — `"cm"` or `"pgm"`.
- `targets` — accepted for interface symmetry with `PredictionFrameLoader` but **not used** by this loader (the parquet already contains its columns).
- Assumes the parquet is well-formed; structural validation is the dataset constructor's job.

---

## 5. Outputs and Side Effects

- **Output:** a `CMDataset`/`PGMDataset` (or list). Deterministic given the file.
- **Side effects:** a single parquet read. No writes, network, logging, or global state.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `level` not in `{cm, pgm}` | `ValueError` (lists valid levels) | `dataframe_loader.py`, level guard |
| Missing/unreadable parquet | Raises from `pd.read_parquet` (`FileNotFoundError`/`OSError`) | read step |
| No `pred_{target}` columns present | `ValueError` ("No usable prediction columns…") | `frames_from_dataframe` |
| Value array not coercible to float32 `(N, S)` | Raises from the `PredictionFrame` constructor | construction step |

Nothing fails silently: the level guard, the no-predictions guard, and the frame constructor's own validation are all loud.

---

## 7. Boundaries and Interactions

- **Depends on:** `views_frames` (`PredictionFrame`, `TargetFrame`, `SpatialLevel`, `SpatioTemporalIndex`); `pandas`, `numpy`.
- **Depends on (internal):** `views_reporting.loaders._constants.LEVELS`.
- **Must not depend on:** Computation, Rendering, or Composition (Layers 3–5).
- **Trusts:** the parquet's MultiIndex is time-first.

---

## 8. Examples of Correct Usage

```python
from views_reporting.loaders import load_predictions

frames = load_predictions(
    prediction_format="dataframe",
    path=Path("predictions_calibration_..._00.parquet"),
    level="cm",
    targets=["lr_ged_sb"],
)
assert frames["lr_ged_sb"].sample_count == 1   # point-estimate parquet
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: declaring "dataframe" for a numpy PredictionFrame directory.
# DataFrameLoader will try to read a directory as parquet and fail.
load_predictions("dataframe", origin_dir, "cm", ["lr_ged_sb"])
```

```python
# WRONG: relying on DataFrameLoader to validate columns/index. It does not;
# malformed frames surface as errors from the dataset constructor, not here.
```

---

## 10. Test Alignment

- **Green:** `tests/test_loaders.py::TestDataFrameLoader` — CM and PGM parquet → per-target `PredictionFrame`, `sample_count == 1`, multi-origin returns 13 dicts.
- **Red:** unknown-level `ValueError`; missing-file raise; a parquet/df with no `pred_*` columns raises `ValueError` (`test_parquet_without_prediction_columns_raises`, `test_frames_from_dataframe_no_pred_columns_raises`) — pins the error contract the evaluation template's C-32 graceful skip relies on.
- **Beige:** `tests/test_e2e_fixture.py` — real average_cmbaseline / average_pgmbaseline parquet fixtures end-to-end.

---

## 11. Evolution Notes

- As models migrate to PredictionFrame output (ADR-012), parquet-format predictions become legacy; this loader stays only as long as parquet predictions exist.

---

## End of Contract

This document defines the **intended meaning** of `DataFrameLoader`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
