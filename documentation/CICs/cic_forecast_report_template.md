
# Class Intent Contract: ForecastReportTemplate

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-31  
**Related ADRs:** ADR-011 (data on measurement scale)  

---

## 1. Purpose

> **What is this class for?**

ForecastReportTemplate generates self-contained HTML forecast reports for VIEWS forecasting models and ensembles. It renders interactive geographic maps for each target variable and, for country-level (CM) datasets, overlays historical-vs-predicted line graphs. It accepts predictions either as pre-loaded DataFrames or as declared-format paths via the loaders package (ADR-012).

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute evaluation metrics; it renders forecasts, not evaluations. Use `EvaluationReportTemplate` for evaluation reports.
- This class does **not** interact with WandB or any external experiment tracking service.
- This class does **not** perform data loading from disk when given a DataFrame. When given a `prediction_path`, it delegates loading to `views_reporting.loaders.load_predictions()` (ADR-012).
- This class does **not** produce PDF, DOCX, or any format other than HTML (via `ReportModule`).
- This class does **not** perform model training, calibration, or reconciliation.
- This class does **not** validate forecast correctness; it renders whatever DataFrames are passed to it.

---

## 3. Responsibilities and Guarantees

- **Report structure.** Produces an HTML report with: a heading, a "Maps" section with one interactive geographic map per target variable, and (for CM datasets) a "Historical vs Forecasted" section with line graphs.
- **MAP computation for probabilistic forecasts.** When the forecast dataset's `sample_size > 1`, computes Maximum A Posteriori estimates via `calculate_map()` before rendering maps (lines 54-61). The MAP column is named `{target}_map`.
- **Geographic map rendering.** Uses `MappingModule` to extract a subset DataFrame and render an interactive Plotly map for each target's `pred_{target}` column (lines 64-81).
- **Historical-vs-forecast overlay.** For `_CDataset` instances (country-level: `CMDataset`), renders a `HistoricalLineGraph` overlay when `historical_dataframe` is provided (lines 82-99).
- **HTML export.** Delegates to `ReportModule.export_as_html()` and returns the output `Path` (lines 107-108).
- **Closure pattern.** The core logic is in a nested `_create_report()` function (lines 37-108) that captures `dataset_cls` from the enclosing scope. This is a structural choice, not accidental.

---

## 4. Inputs and Assumptions

- **Constructor requires:**
  - `config` (Dict): Pipeline configuration dictionary. Must contain `"level"` (either `"cm"` or `"pgm"`) and `"targets"` (list of target variable names, e.g., `["ged_sb"]`).
  - `model_path` (ModelPathManager): Provides `.target`, `.model_name`, and `.reports` (output directory).
  - `run_type` (str): The run type string (e.g., "forecasting").

- **`generate()` accepts predictions in one of two ways (ADR-012):**
  - `forecast_dataframe` (pd.DataFrame, optional): A pre-loaded DataFrame containing prediction columns named `pred_{target}`.
  - `prediction_format` (str, optional) + `prediction_path` (Path, optional): A declared format and path for loader dispatch. The template calls `load_predictions()` internally.
  - Providing both `forecast_dataframe` and `prediction_path` raises `ValueError` (ADR-003).
  - Providing neither raises `ValueError`.
  - `historical_dataframe` (pd.DataFrame, optional): Historical observation columns. Required for the historical-vs-forecast line graph section. Defaults to `None`.

- **Assumptions per ADR-011 (data on measurement scale):** The class assumes that forecast values in the DataFrame are on their declared measurement scales and renders them as-is. MAP computation preserves the measurement scale of the input predictions.

- **`config["level"]` must be `"cm"` or `"pgm"`.** Any other value raises `ValueError` (lines 111-114).

- **`config["targets"]` must be present and non-empty.** The class iterates over it unconditionally (line 49). A missing or empty `targets` key will produce a report with no maps.

- **Forecast DataFrame must be compatible** with the dataset class (`CMDataset` or `PGMDataset`) constructor. The DataFrame must have the correct multi-index structure (time_id, entity_id).

---

## 5. Outputs and Side Effects

- **Return value.** `generate()` returns a `Path` to the exported HTML file, located at `self.model_path.reports / f"report_{generate_model_file_name(...)}.html"`.
- **File I/O.** Writes one HTML file via `ReportModule.export_as_html()`.
- **Progress bar.** Displays a `tqdm` progress bar during map generation (line 49).
- **Logging.** Logs info messages for probabilistic forecasts and CM-level graph generation.
- **No state mutation** on the input DataFrames, config, or model_path objects.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `config["level"]` not "cm" or "pgm" | `ValueError` raised | `generate`, lines 111-114 |
| `config["targets"]` missing | `KeyError` raised | `_create_report`, line 49 |
| `forecast_dataframe` incompatible with dataset class | Exception from dataset constructor | `_create_report`, line 39 |
| `historical_dataframe` is `None` for CM dataset | Line graph section skipped (no error -- `historical_dataframe` is checked implicitly by `dataset_cls` constructor for the historical side) | `_create_report`, lines 87-89 |
| `MappingModule` or `HistoricalLineGraph` raises | Unhandled -- propagates to caller | `_create_report` |

Unlike `EvaluationReportTemplate`, this class does **not** wrap any section in a try/except. All failures propagate directly to the caller. There is no non-fatal subsystem.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_reporting.reports.ReportModule` -- HTML assembly and export
  - `views_reporting.mapping.MappingModule` -- geographic map rendering
  - `views_reporting.visualizations.HistoricalLineGraph` -- historical-vs-forecast line graphs
  - `views_reporting.statistics.calculate_map` -- MAP computation for probabilistic forecasts
  - `views_pipeline_core.data.handlers` -- `CMDataset`, `PGMDataset`, `_CDataset` (dataset types and type checking)
  - `views_pipeline_core.files.utils` -- `generate_model_file_name` (report filename generation)
  - `views_pipeline_core.managers.model` -- `ModelPathManager`
  - `pandas` -- DataFrame operations
  - `tqdm` -- progress bar
- **Must not depend on:**
  - `wandb` or any external experiment tracking service
  - `views_reporting.reconciliation` (no reconciliation logic)
- **Trusts:**
  - That `MappingModule.plot_map()` produces valid HTML for the given DataFrame and target
  - That `calculate_map()` returns a DataFrame with correctly named MAP columns
  - That `HistoricalLineGraph.plot_predictions_vs_historical()` produces valid HTML
  - That dataset classes correctly parse the input DataFrames

---

## 8. Examples of Correct Usage

```python
import pandas as pd
from views_pipeline_core.managers.model import ModelPathManager
from views_reporting.templates.reports.forecast import ForecastReportTemplate

model_path = ModelPathManager("my_model")
config = {
    "level": "cm",
    "targets": ["ged_sb"],
}

template = ForecastReportTemplate(
    config=config,
    model_path=model_path,
    run_type="forecasting",
)

# With both forecast and historical data
report_path = template.generate(
    forecast_dataframe=forecast_df,
    historical_dataframe=historical_df,
)

# Forecast only (no historical overlay)
report_path = template.generate(
    forecast_dataframe=forecast_df,
)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Invalid level
config = {"level": "cy", "targets": ["ged_sb"]}
template = ForecastReportTemplate(config=config, model_path=model_path, run_type="forecasting")
template.generate(forecast_df)  # Raises ValueError

# WRONG: Missing targets key in config
config = {"level": "cm"}
template = ForecastReportTemplate(config=config, model_path=model_path, run_type="forecasting")
template.generate(forecast_df)  # Raises KeyError

# WRONG: Using this class for evaluation reports
# This class renders forecasts (maps + line graphs), not evaluation metrics.
# Use EvaluationReportTemplate for evaluation reports with WandB metrics.

# WRONG: Expecting non-fatal graph generation (as in EvaluationReportTemplate)
# All failures in ForecastReportTemplate propagate to the caller.
# There is no try/except wrapping any section.
```

---

## 10. Test Alignment

**No dedicated tests exist for ForecastReportTemplate in this repository.** The test suite covers the components it depends on (`ReportModule`, `MappingModule`, `HistoricalLineGraph`, `calculate_map`) but not the template itself.

Testing this class is more feasible than `EvaluationReportTemplate` because it has no external service dependencies (no WandB). It operates on in-memory DataFrames.

Tests that should exist:
- **Green:** Verify that `generate()` produces an HTML file at the expected path given fixture DataFrames.
- **Red:** Verify `ValueError` when `config["level"]` is invalid.
- **Red:** Verify `KeyError` when `config["targets"]` is missing.
- **Beige:** Verify full report workflow with CM-level data, confirming map section and historical-vs-forecast section are both present.
- **Beige:** Verify PGM-level report omits the historical-vs-forecast section (no `_CDataset` type check match).
- **Beige:** Verify probabilistic forecast (sample_size > 1) triggers MAP computation and uses MAP column in map rendering.

---

## 11. Evolution Notes

### Known Deviations

1. **Closure pattern for `_create_report()`.** The core report-building logic lives in a nested function (lines 37-108) rather than being a method on the class. This captures `dataset_cls` from the enclosing scope of `generate()`. The pattern works but makes the class harder to subclass or extend.

2. **Asymmetric error handling vs. `EvaluationReportTemplate`.** `EvaluationReportTemplate` wraps its graph section in try/except to make it non-fatal. `ForecastReportTemplate` does not -- any failure in map or graph generation propagates immediately. This asymmetry is not documented in the code and may surprise callers expecting uniform behavior.

3. **`_CDataset` type check for historical graphs.** The historical-vs-forecast section is gated on `isinstance(forecast_dataset, _CDataset)` (line 82), which means it only renders for country-level datasets (`CMDataset`, `CYDataset`). PGM-level datasets never get line graphs, even if historical data is provided.

4. **MAP variable shadowing.** When `sample_size > 1`, the local `target` variable is reassigned from `target` to `f"{target}_map"` (line 61), and `original_target` preserves the original value (line 53). This shadowing within the loop body is functional but easy to misread.

5. **`tqdm` progress bar in a library class.** The progress bar (line 49) is appropriate for CLI usage but may produce unwanted output when this class is used in automated pipelines or notebooks.

### Stability

- The report structure (heading, maps, optional historical overlay) is stable.
- The MAP computation trigger (`sample_size > 1`) is stable.
- The dataset class dispatch (`CMDataset` vs `PGMDataset`) is stable.

### Expected Changes

- Support for additional dataset levels (e.g., `cy`, `pgy`) would require extending `dataset_classes` (line 35) and potentially the `_CDataset` type check.
- The closure pattern could be refactored to a standard method if subclassing is needed.

---

## End of Contract

This document defines the **intended meaning** of `ForecastReportTemplate`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
