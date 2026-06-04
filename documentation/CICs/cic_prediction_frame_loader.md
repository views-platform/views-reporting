
# Class Intent Contract: PredictionFrameLoader

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-04
**Related ADRs:** ADR-002 (Topology — Ingestion is Layer 2), ADR-003 (Declarations over inference), ADR-006 (Intent Contracts), ADR-008 (Observability), ADR-009 (Boundary Contracts — §1a), ADR-012 (Prediction Data Ingestion)

---

## 1. Purpose

> Load one rolling-origin's predictions from the **numpy PredictionFrame** storage format into a `CMDataset` or `PGMDataset`.

`PredictionFrameLoader` is the Ingestion-layer (Layer 2) adapter for the numpy format produced by sample-estimate models (mixture baselines, HydraNet). It reads `PredictionFrame` directories via pipeline-core's `PredictionFrameConverter` and produces the same dataset containers the rest of views-reporting consumes, so nothing above the Ingestion layer knows the predictions came from numpy.

Source: `views_reporting/loaders/prediction_frame_loader.py`.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** infer the storage format — the caller declares `prediction_frame` explicitly (ADR-003); this loader is only reached via the registry for that declared format.
- Does **not** read parquet — that is `DataFrameLoader`'s responsibility.
- Does **not** compute statistics, collapse samples to MAP, render, or assemble reports.
- Does **not** define or own the `PredictionFrame` format or the `CMDataset`/`PGMDataset` schema (owned by pipeline-core).
- Does **not** discover which origins/paths exist — the caller supplies the path(s).

---

## 3. Responsibilities and Guarantees

- **Format conversion.** For each target in `targets`, loads `{path}/{target}/` as a `PredictionFrame` (`PredictionFrame.load`) and converts it to a DataFrame via `PredictionFrameConverter().to_prediction_df(pf, target)`.
- **Multi-target merge.** Joins per-target DataFrames on the shared index into one DataFrame.
- **Index-naming invariant (critical).** `to_prediction_df` returns a MultiIndex with **unnamed levels (`[None, None]`)**. The loader sets the names via `merged.index.set_names(INDEX_NAMES[level])` before constructing the dataset. This guarantees `cm` → `["month_id", "country_id"]` and `pgm` → `["month_id", "priogrid_id"]`. This repair is the single most important guarantee of this class: without it the dataset constructor would reject the frame or mislabel axes.
- **Typed return.** Returns a `CMDataset` (level `cm`) or `PGMDataset` (level `pgm`); `load_multi_origin` returns a list, one per path, in input order.
- **Fail-loud on unknown level.** A `level` not in `{cm, pgm}` raises `ValueError` before any I/O.

---

## 4. Inputs and Assumptions

- **`load_single_origin(path, level, targets)`** / **`load_multi_origin(paths, level, targets)`**:
  - `path` — a rolling-origin directory containing one subdirectory per target, each holding `y_pred.npy` + `identifiers.npz` (the `PredictionFrame.save` layout).
  - `level` — `"cm"` or `"pgm"`; must be in `DATASET_CLASSES`.
  - `targets` — non-empty list of target names; each must have a `{path}/{target}/` subdirectory.
- Assumes `PredictionFrameConverter.to_prediction_df` emits an unnamed `[None, None]` MultiIndex (the ADR-009 §1a boundary contract). If pipeline-core changes that output, this loader's `set_names` mislabels axes — a silent-corruption seam (register C-30).
- Assumes all targets share an identical index so the join aligns.

---

## 5. Outputs and Side Effects

- **Output:** a `CMDataset`/`PGMDataset` (or a list thereof). Deterministic given the files on disk.
- **Side effects:** filesystem reads only (numpy `.npy`/`.npz`). No writes, no network, no logging, no global state mutation.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `level` not in `{cm, pgm}` | `ValueError` (lists valid levels) | `prediction_frame_loader.py`, level guard |
| Missing `{path}/{target}/`, `y_pred.npy`, or `identifiers.npz` | Raises from `PredictionFrame.load` | per-target load loop |
| **Empty `targets` list** | `dfs` is empty → join/`set_names` fails. **No explicit guard** — currently fails with an opaque error rather than a declared one. Documented limitation. | per-target loop |
| Converter emits a named/reordered index | **Not detected** — `set_names` silently overwrites; values may mis-align. Tracked as register C-30. | `set_names` step |
| Dataset constructor rejects the frame | Raises from `CMDataset`/`PGMDataset` | final construction |

Must never fail silently: unknown level and dataset-construction errors are loud. The two known soft spots (empty `targets`, converter-index drift) are documented above and tracked.

---

## 7. Boundaries and Interactions

- **Depends on (Foundation, Layer 1):** `CMDataset`, `PGMDataset` from `views_pipeline_core.data.handlers`.
- **Depends on (sanctioned manager coupling, ADR-009 §1a):** `PredictionFrame` (`views_pipeline_core.data.prediction_frame`) and `PredictionFrameConverter` (`views_pipeline_core.managers.prediction.prediction_frame_converter`). This is the one allowed exception to "Foundation = containers only" (ADR-002).
- **Depends on (internal):** `views_reporting.loaders._constants` (`DATASET_CLASSES`, `INDEX_NAMES`).
- **Must not depend on:** Computation (statistics, reconciliation, transformations), Rendering (visualizations, mapping), or Composition (reports, templates) — Layers 3–5.
- **Trusts:** that `PredictionFrameConverter` honors the ADR-009 §1a output contract; treats the `PredictionFrame` internals as opaque.

---

## 8. Examples of Correct Usage

```python
from views_reporting.loaders import load_predictions

# Single origin, CM level, one target
ds = load_predictions(
    prediction_format="prediction_frame",
    path=origin_dir,                      # contains lr_ged_sb/y_pred.npy + identifiers.npz
    level="cm",
    targets=["lr_ged_sb"],
)
assert ds.dataframe.index.names == ["month_id", "country_id"]
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
# WRONG: empty targets — no explicit guard; fails with an opaque join error
# rather than a declared ValueError (see Failure Modes).
PredictionFrameLoader().load_single_origin(origin_dir, "cm", targets=[])
```

---

## 10. Test Alignment

- **Green:** `tests/test_loaders.py::TestPredictionFrameLoader` — single-origin load yields the right dataset type and `sample_size`; index names are exactly `["month_id", "country_id"]` (the invariant); multi-origin returns one dataset per path.
- **Beige:** `tests/test_e2e_fixture.py` — real red_ranger fixtures (256 samples) loaded end-to-end into a forecast report.
- **Red:** unknown-level `ValueError`; missing-directory raise. **Gap:** no test yet pins the empty-`targets` failure or the converter-index-drift seam — add when C-30 is addressed.
- Invariant tests must protect: index-naming repair, typed return, fail-loud on unknown level.

---

## 11. Evolution Notes

- The numpy PredictionFrame format is the pipeline's forward direction (ADR-012); this loader's importance grows as models migrate off parquet.
- If `PredictionFrameConverter` ever emits a named index, remove the `set_names` repair and update ADR-009 §1a + this contract together.
- An explicit empty-`targets` guard (declared `ValueError`) is a likely near-term hardening.

---

## End of Contract

This document defines the **intended meaning** of `PredictionFrameLoader`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
