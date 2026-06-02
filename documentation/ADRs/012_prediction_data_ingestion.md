# ADR-012: Prediction Data Ingestion — Declared Format Dispatch

**Status:** Implemented
**Date:** 2026-06-02
**Deciders:** Simon, VIEWS platform team

---

## Context

The VIEWS pipeline is migrating from DataFrame-based prediction storage (parquet files with scalar or array-valued cells) to PredictionFrame-based storage (numpy arrays with separate identifier files). This migration is driven by memory efficiency — PredictionFrame avoids the overhead of Python list objects in DataFrame cells and supports memory-mapped loading for large spatial grids.

During the transition, both formats coexist:

- **Point-estimate models** (average baselines, stepshifter models) output parquet files containing DataFrames with scalar `pred_{target}` columns.
- **Sample-estimate models** (mixture baselines, HydraNet) output numpy directories containing `y_pred.npy` (shape `N × S`) and `identifiers.npz` (keys `time`, `unit`).

views-reporting must consume both formats and produce identical reports regardless of storage format. The format distinction is a storage concern — it must not leak into the statistical, visualization, or report-assembly layers.

### The Problem

Before this ADR, views-reporting consumed predictions only as pandas DataFrames. The `ForecastReportTemplate.generate()` method accepted a `pd.DataFrame` parameter. The `ReportingStage` in pipeline-core loaded predictions via `read_dataframe()`, which discovers parquet files only. PredictionFrame models with numpy output could not generate forecast reports.

### Related Decisions

- **ADR-003** (Authority of Declarations Over Inference): Format must be declared in the model config (`prediction_format` key), never inferred from file extensions or directory structure.
- **ADR-008** (Observability and Explicit Failure): Unknown formats raise ValueError with a list of registered formats.
- **ADR-002** (Topology): Loaders sit at Layer 0.5, between pipeline-core data containers (Layer 0) and the compute layer (Layer 1). Nothing above Layer 0.5 knows about storage format.

## Decision

Prediction data ingestion uses a **declared-format loader dispatch** via a registry pattern in `views_reporting/loaders/`.

### Core Principles

1. **Format is declared, never inferred.** The model config contains `prediction_format: "dataframe"` or `prediction_format: "prediction_frame"`. The loader reads this declaration and dispatches to the correct loader class.

2. **Two canonical formats.** The registry ships with two loaders:
   - `DataFrameLoader` — reads parquet files into `CMDataset`/`PGMDataset`
   - `PredictionFrameLoader` — reads numpy directories (`y_pred.npy` + `identifiers.npz`) into `CMDataset`/`PGMDataset` via `PredictionFrameConverter`

3. **Open for extension.** New formats are added by writing a loader class that conforms to the `PredictionLoader` protocol and calling `register_loader("format_name", LoaderClass)`. No existing code is modified.

4. **Templates are format-agnostic.** `ForecastReportTemplate` and `EvaluationReportTemplate` work with `CMDataset`/`PGMDataset` objects. They do not know or care how the data was loaded. MAP computation, HDI calculation, mapping, and visualization operate on the dataset interface, not on storage format.

5. **MAP/HDI are template operations, not format distinctions.** A sample-estimate dataset (regardless of storage format) is collapsed to point estimates via `calculate_map()` when the template needs scalars for choropleth maps. This branching is based on `dataset.sample_size`, not on `prediction_format`.

### Package Structure

```
views_reporting/loaders/
    __init__.py                      # Public API + self-registration
    _protocol.py                     # PredictionLoader protocol (typing.Protocol)
    _registry.py                     # Format → loader dispatch
    _constants.py                    # Shared DATASET_CLASSES and INDEX_NAMES
    dataframe_loader.py              # Parquet → Dataset
    prediction_frame_loader.py       # NumPy → Dataset
```

### Public API

```python
from views_reporting.loaders import load_predictions, load_prediction_sequence

dataset = load_predictions(prediction_format, path, level, targets)
datasets = load_prediction_sequence(prediction_format, paths, level, targets)
```

## Consequences

### Positive

- **PredictionFrame models can generate reports.** The reporting gap (numpy models could not produce forecast reports) is closed.
- **Format-agnostic templates.** Adding a third storage format requires zero changes to templates, statistics, or visualization code.
- **Explicit boundary.** The format conversion boundary is visible in the architecture (`loaders/` package), not hidden in inline code.

### Negative

- **PredictionFrameConverter produces unnamed indices.** `to_prediction_df()` returns a DataFrame with `index.names = [None, None]`. The PredictionFrameLoader must explicitly set index names based on the declared `level`. This is a known seam, documented and tested.
- **Two repos involved.** The loader lives in views-reporting, but the caller (`ReportingStage`) lives in pipeline-core. Full integration requires a coordinated change in pipeline-core to pass `prediction_format` through to the template.

### Neutral

- The `DataFrameLoader` is a thin wrapper around `pd.read_parquet()` + `Dataset()`. Its value is not in the code but in the dispatch contract — all loading goes through the same entry point.
