# Prediction Data Ingestion Roadmap

**Date:** 2026-06-01
**Status:** Planning complete, execution pending
**Governing principles:** ADR-002 (topology), ADR-003 (declarations over inference), SOLID, screaming architecture

---

## Problem

views-reporting consumes prediction data only as pandas DataFrames wrapped in `CMDataset`/`PGMDataset` objects. The VIEWS pipeline is migrating from DataFrame to PredictionFrame (numpy) format for memory efficiency. Models already produce predictions in two formats — parquet (DataFrame track) and numpy (PredictionFrame track) — but views-reporting can only read the first.

Additionally, models produce both point estimates (scalar per cell) and distributional estimates (array of posterior samples per cell). The reporting pipeline must handle both, collapsing samples to point estimates (via MAP) when needed for maps and summary tables, while preserving the full distribution for uncertainty visualization (HDI bands, credible intervals).

The `ReportingStage` in pipeline-core has a hard gap: it calls `read_dataframe()` which only discovers parquet files. PredictionFrame models with `skip_predictions_delivery=True` cannot generate forecast reports.

---

## The Maturity Ladder

Five rungs, ordered from what works today to what the future requires:

### Rung 1 — Point estimates from DataFrame parquets

**Format:** `.parquet` file → `pd.DataFrame` with MultiIndex `(month_id, entity_id)`, scalar values in `pred_{target}` columns.

**Example models:** `average_cmbaseline`, `locf_cmbaseline`, `average_pgmbaseline`

**Status:** Works today. `ForecastReportTemplate.generate()` receives a DataFrame, wraps it in `CMDataset(df)`, and the pipeline proceeds. `sample_size=1`, no MAP computation needed.

**What it tests:** The simplest path — data in, report out. No uncertainty, no array cells, no format conversion.

### Rung 2 — Point estimates collapsed from sample estimates

**Format:** Same as Rung 3 (array-valued cells), but the template calls `calculate_map()` to collapse 256 samples into a single MAP estimate before rendering maps.

**Example flow:** `red_ranger` predictions → `CMDataset(df)` → `calculate_map(dataset)` → `CMDataset(map_df)` → `MappingModule.plot_map()`

**Status:** Works today. The collapse logic is inside `ForecastReportTemplate.generate()` at line 57-63.

**What it tests:** The MAP computation chain — from raw posterior samples through `PosteriorDistributionAnalyzer` to a scalar estimate suitable for choropleth maps.

### Rung 3 — Sample estimates from DataFrame parquets

**Format:** `.parquet` file → `pd.DataFrame` with array-valued cells. Each cell in `pred_{target}` contains a numpy array of shape `(sample_size,)`.

**Example models:** `red_ranger` (CM, 256 samples), `blue_ranger` (PGM, 256 samples)

**Status:** Works today. `CMDataset(df)` auto-detects `sample_size > 1` from the array lengths. `HistoricalLineGraph` renders HDI bands. `calculate_hdi()` computes credible intervals.

**What it tests:** The full probabilistic pipeline — MAP for maps, HDI for line graphs, uncertainty propagation through the template.

### Rung 4 — Point estimates from NumPy PredictionFrame

**Format:** Directory containing `y_pred.npy` (shape `(N, 1)`) + `identifiers.npz` (keys `time`, `unit`). This is `PredictionFrame.save()` output with `sample_count=1`.

**Example models:** Future baseline models after migration from DataFrame to PredictionFrame output.

**Status:** Needs a loader. views-reporting has no code path that reads `.npy` files. The conversion chain is: `PredictionFrame.load(dir)` → `PredictionFrameConverter.to_prediction_df(pf, target)` → rename index → `CMDataset(df)`. All pieces exist in pipeline-core; they need to be wired into views-reporting.

**What it tests:** The format boundary — proving that the numpy-to-DataFrame bridge works end to end without data loss or index corruption.

### Rung 5 — Sample estimates from NumPy PredictionFrame

**Format:** Directory containing `y_pred.npy` (shape `(N, S)` where S > 1) + `identifiers.npz`. Full posterior sample matrix.

**Example models:** `blue_stranger` (HydraNet, PGM, 64 samples), `lucid_dream` (synthetic PGM, 64 samples)

**Status:** Needs the same loader as Rung 4, but with `sample_count > 1`. The conversion produces array-valued cells in the DataFrame, which `CMDataset` handles natively.

**What it tests:** The full stack for the future production path — numpy storage → DataFrame conversion → MAP/HDI computation → report generation.

---

## Architecture: The Loaders Package

### Placement in the topology (ADR-002)

```
Layer 0:   views-pipeline-core (CMDataset, PGMDataset, PredictionFrame)
Layer 0.5: views_reporting.loaders  ← NEW: format → Dataset bridge
Layer 1:   views_reporting.statistics, .reconciliation, .metadata, .transformations
Layer 2:   views_reporting.visualizations, .mapping
Layer 3:   views_reporting.reports, .templates
```

Loaders sit between pipeline-core's data containers and the compute layer. They produce `CMDataset`/`PGMDataset` objects that the rest of the system consumes. Nothing above Layer 0.5 knows or cares about storage format.

### Package structure

```
views_reporting/loaders/
    __init__.py                      # Public API + self-registration
    _protocol.py                     # PredictionLoader protocol
    _registry.py                     # Format → loader dispatch
    dataframe_loader.py              # Rung 1-3: parquet → Dataset
    prediction_frame_loader.py       # Rung 4-5: numpy → Dataset
```

### Design principles applied

| Principle | How it's applied |
|-----------|-----------------|
| **SRP** | Each loader handles exactly one storage format |
| **OCP** | New formats: write a loader class + `register_loader()`. No existing code modified. |
| **LSP** | All loaders conform to `PredictionLoader` protocol. Callers don't know which loader runs. |
| **ISP** | Protocol has two methods: `load_single_origin()`, `load_multi_origin()`. No bloat. |
| **DIP** | Templates depend on `load_predictions()` abstraction, never on concrete loaders. |
| **ADR-003** | Format declared in config (`prediction_format` key). Never inferred from file extensions. |
| **CCP** | Loader code changes when storage format changes — all in one package. |
| **SDP** | Loaders depend on stable pipeline-core containers. Nothing depends on loaders except templates (unstable → stable direction). |

### Public API

```python
from views_reporting.loaders import load_predictions, load_prediction_sequence

# Single origin (forecast report)
dataset = load_predictions(
    prediction_format="prediction_frame",
    path=Path("predictions_forecasting_20260601/lr_ged_sb/"),
    level="cm",
    targets=["lr_ged_sb"],
)

# Multiple origins (evaluation report)
datasets = load_prediction_sequence(
    prediction_format="dataframe",
    paths=[Path(f"predictions_calibration_*_{i:02d}.parquet") for i in range(13)],
    level="pgm",
    targets=["lr_ged_sb"],
)
```

---

## Implementation Phases

### Phase A: Golden Fixtures (Rungs 1-3)

Set up `tests/data/` with real model outputs for deterministic testing. Four models, all on calibration partition (test 445-492, 13 rolling origins):

| Fixture | Model | Level | Samples | Rung |
|---------|-------|-------|---------|------|
| CM point | average_cmbaseline | cm | 1 | 1 |
| PGM point | average_pgmbaseline | pgm | 1 | 1 |
| CM samples | red_ranger | cm | 256 | 3 |
| PGM samples | blue_ranger | pgm | 256 | 3 |

Data not committed to git — tests skip when absent. See `tests/data/README.md` for setup instructions.

### Phase B: Loaders Package

1. Protocol + registry (no I/O)
2. `DataFrameLoader` — extracts the existing pattern from `ReportingStage`
3. `PredictionFrameLoader` — new capability for numpy format
4. Unit + integration tests for both

### Phase C: Template Integration

1. `ForecastReportTemplate.generate()` accepts optional loader-based input
2. `EvaluationReportTemplate` updated for PredictionFrame prediction graphs
3. `ReportingStage` in pipeline-core passes `prediction_format` through

### Phase D: Governance

1. ADR-012: Prediction Data Ingestion — Declared Format Dispatch
2. Golden E2E tests for Rungs 4-5

---

## Fixture Data Strategy

**Development setup (current):** Data files live in `tests/data/` but are gitignored. Developers run the four models locally and copy outputs. Tests skip when data is absent.

**Production setup (future):** Fixture data accessed via Appwrite. Tests fetch from the data store if credentials are available, skip otherwise.

The test code is written to be agnostic about where the data comes from — it receives a path and checks if the expected files exist. The discovery logic can be swapped from "local directory" to "Appwrite fetch" without changing the test assertions.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| PredictionFrame → DataFrame memory explosion for large PGM | Medium | Use `mmap=True` loading; process in chunks if needed. Known acceptable cost (DataFrame path already handles this scale). |
| Index renaming errors (time→month_id, unit→entity_id) | High | Unit tests with real dataset validation. Dataset constructors provide the guard. |
| Multi-target directory discovery varies across models | Medium | Validate directory structure at load time. Fail loud with clear error (ADR-008). |
| Breaking ReportingStage interface | Low | `prediction_format` defaults to `"dataframe"` — backward compatible. |
| PGM fixture size too large for local disk | Low | PGM samples (blue_ranger) may be large but only needed for full E2E. Synthetic tests cover the same code paths at small scale. |
