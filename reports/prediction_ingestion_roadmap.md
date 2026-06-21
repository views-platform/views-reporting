# Prediction Data Ingestion Roadmap

**Date:** 2026-06-01
**Revised:** 2026-06-02
**Status:** Planning complete, fixture data populated, execution pending
**Governing principles:** ADR-002 (topology), ADR-003 (declarations over inference), SOLID, screaming architecture

---

## Problem

views-reporting consumes prediction data only as pandas DataFrames wrapped in `CMDataset`/`PGMDataset` objects. The VIEWS pipeline is migrating from DataFrame to PredictionFrame (numpy) format for memory efficiency. Models already produce predictions in two formats — parquet (DataFrame track) and numpy (PredictionFrame track) — but views-reporting can only read the first.

Additionally, models produce both point estimates (scalar per cell) and distributional estimates (array of posterior samples per cell). The reporting pipeline must handle both, collapsing samples to point estimates (via MAP) when needed for maps and summary tables, while preserving the full distribution for uncertainty visualization (HDI bands, credible intervals).

The `ReportingStage` in pipeline-core has a hard gap: it calls `read_dataframe()` which only discovers parquet files. PredictionFrame models with `skip_predictions_delivery=True` cannot generate forecast reports.

---

## The Two Real Formats

### Original five-rung ladder (superseded)

The initial investigation identified five rungs: (1) parquet scalars, (2) parquet scalars collapsed from samples, (3) parquet with array-valued cells, (4) numpy scalars, (5) numpy sample matrix. After running all four fixture models, we discovered that both ranger baselines (`red_ranger`, `blue_ranger`) now produce **numpy PredictionFrame format natively**, not parquets with array cells.

This means Rung 3 (parquet with array-valued cells) was a transitional format — a chimera that shoehorned sample estimates into a DataFrame container. The pipeline has already moved past it. Rung 2 (MAP collapse) is not a separate format — it's an operation the template performs on sample data when it needs a scalar for a choropleth map. Rung 4 (numpy with S=1) is just Rung 5 after `PredictionFrame.collapse()`.

### Simplified to two formats

| Format | What it is | Example models | Template behavior |
|--------|-----------|----------------|------------------|
| **Parquet → DataFrame** | Point estimates. Scalars in `pred_{target}` columns. | `average_cmbaseline`, `average_pgmbaseline`, `locf_*` | Render directly — no MAP, no HDI |
| **NumPy → PredictionFrame** | Sample estimates. `y_pred.npy` shape `(N, S)` + `identifiers.npz`. | `red_ranger`, `blue_ranger`, `blue_stranger` | MAP for maps, HDI for line graphs |

Two formats. Two loaders. No intermediate chimeras.

The MAP collapse (samples → point estimate) is a **template operation**, not a format. The template checks `dataset.sample_size` and branches: if 1, render directly; if >1, call `calculate_map()` first. This logic already works and doesn't change.

### Why we dropped the intermediate rungs

**Rung 2 (MAP collapse):** Not a format — it's what `ForecastReportTemplate.generate()` does internally at line 57-63 when `sample_size > 1`. No loader involved.

**Rung 3 (parquet with array cells):** Transitional. When we ran `red_ranger` and `blue_ranger` in June 2026, both produced numpy PredictionFrame output. The older parquet-with-arrays format (from May 2026 runs) exists on disk but represents the outgoing track. Building loader and test infrastructure for a retiring format is wasted effort.

**Rung 4 (numpy S=1):** Just Rung 5 with `sample_count=1`. The PredictionFrameLoader handles both — the dataset constructor auto-detects `sample_size` from the array shape.

---

## Fixture Data

Four models, all on calibration partition (train 121-444, test 445-492, 13 rolling origins):

| Fixture | Model | Level | Format | Samples | Size | In repo? |
|---------|-------|-------|--------|---------|------|----------|
| CM point | average_cmbaseline | cm | parquet (DataFrame) | 1 | 196 KB | Yes |
| PGM point | average_pgmbaseline | pgm | parquet (DataFrame) | 1 | 20 MB | Yes |
| CM samples | red_ranger | cm | numpy (PredictionFrame) | 256 | 89 MB | Yes |
| PGM samples | blue_ranger | pgm | numpy (PredictionFrame) | 256 | 6 GB | No — discovered from views-models |

Data files are gitignored. Tests skip when absent. See `tests/data/README.md` for setup instructions.

---

## Architecture: The Loaders Package

### Placement in the topology (ADR-002)

```
Foundation  (Layer 1): views-pipeline-core containers (CMDataset, PGMDataset, PredictionFrame)
Ingestion   (Layer 2): views_reporting.loaders  ← format → Dataset bridge
Computation (Layer 3): views_reporting.statistics, .reconciliation, .metadata
Rendering   (Layer 4): views_reporting.visualizations, .mapping
Composition (Layer 5): views_reporting.reports, .templates
```

> The five-layer topology above was ratified in ADR-002 (#76); the loaders package is the dedicated **Ingestion layer (Layer 2)**. This supersedes the original roadmap's "Layer 0.5" framing.

### Package structure

```
views_reporting/loaders/
    __init__.py                      # Public API + self-registration
    _protocol.py                     # PredictionLoader protocol
    _registry.py                     # Format → loader dispatch
    dataframe_loader.py              # Parquet → Dataset
    prediction_frame_loader.py       # NumPy → Dataset
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

### Public API

```python
from views_reporting.loaders import load_predictions, load_prediction_sequence

# Single origin (forecast report)
dataset = load_predictions(
    prediction_format="prediction_frame",
    path=Path("predictions_calibration/origin_0/lr_ged_sb/"),
    level="cm",
    targets=["lr_ged_sb"],
)

# Multiple origins (evaluation report)
datasets = load_prediction_sequence(
    prediction_format="dataframe",
    paths=[Path(f"predictions_calibration_{ts}_{i:02d}.parquet") for i in range(13)],
    level="pgm",
    targets=["lr_ged_sb"],
)
```

---

## Implementation Phases

### Phase A: Golden Fixtures and E2E Tests

Set up `tests/data/` with real model outputs. Write E2E tests that exercise the full pipeline against both formats. Tests skip when data absent.

### Phase B: Loaders Package

1. Protocol + registry (no I/O)
2. `DataFrameLoader` — extracts existing pattern from `ReportingStage`
3. `PredictionFrameLoader` — new capability for numpy format
4. Unit + integration tests for both

### Phase C: Template Integration

1. `ForecastReportTemplate.generate()` accepts optional loader-based input
2. `EvaluationReportTemplate` updated for PredictionFrame prediction graphs
3. `ReportingStage` in pipeline-core passes `prediction_format` through

### Phase D: Governance

1. ADR-012: Prediction Data Ingestion — Declared Format Dispatch
2. Full E2E tests for both formats with real data

---

## GitHub Issues

| Issue | Title | Phase | Status |
|-------|-------|-------|--------|
| #52 | Set up test fixtures directory structure and manifest format | A | Open |
| #53 | Copy CM point-estimate baseline fixtures (average_cmbaseline) | A | Done (data copied) |
| #54 | Copy PGM point-estimate baseline fixtures (average_pgmbaseline) | A | Done (data copied) |
| #55 | Copy CM sample-estimate baseline fixtures (red_ranger) | A | Done (numpy, 89 MB) |
| #56 | Copy PGM sample-estimate baseline fixtures (blue_ranger) | A | Done (numpy, 6 GB, views-models only) |
| #57 | Write golden E2E tests for both formats using fixture data | A | Open |
| #58 | Create loaders/ package with protocol and registry | B | Open |
| #59 | Implement DataFrameLoader | B | Open |
| #60 | Implement PredictionFrameLoader | B | Open |
| #61 | Unit and integration tests for both loaders | B | Open |
| #62 | Integrate loaders into ForecastReportTemplate | C | Open |
| #63 | Integrate loaders into EvaluationReportTemplate | C | Open |
| #64 | Update ReportingStage in pipeline-core to pass prediction_format | C | Open |
| #65 | Write ADR-012: Prediction Data Ingestion | D | Open |
| #66 | Full E2E tests for both formats with real data | D | Open |

Issues #53-#56 (Rung 3 parquet fixtures) were originally scoped for parquet-with-arrays but the actual model outputs are numpy PredictionFrame. The issues were fulfilled with the correct format — this is documented in each model's `manifest.json`.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| PredictionFrame → DataFrame memory explosion for large PGM | Medium | Use `mmap=True` loading; blue_ranger fixture at 6 GB stays in views-models, not copied |
| Index renaming errors (time→month_id, unit→entity_id) | High | Unit tests with real dataset validation. Dataset constructors provide the guard. |
| Multi-target directory discovery varies across models | Medium | Validate directory structure at load time. Fail loud with clear error (ADR-008). |
| Breaking ReportingStage interface | Low | `prediction_format` defaults to `"dataframe"` — backward compatible. |
