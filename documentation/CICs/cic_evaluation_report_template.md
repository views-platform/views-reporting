
# Class Intent Contract: EvaluationReportTemplate

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-31  
**Related ADRs:** ADR-011 (data on measurement scale)  

---

## 1. Purpose

> **What is this class for?**

EvaluationReportTemplate generates self-contained HTML evaluation reports for VIEWS forecasting models and ensembles. It retrieves evaluation metrics and metadata from a Weights & Biases run, fetches constituent-model runs for comparative metric tables, optionally renders historical-vs-predicted line graphs from on-disk prediction parquets, and delegates all HTML assembly to `ReportModule`.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute evaluation metrics itself; it reads pre-computed metrics from WandB run summaries.
- This class does **not** train, retrain, or modify models in any way.
- This class does **not** manage WandB authentication or project configuration; it assumes a valid `wandb.apis.public.runs.Run` object is supplied.
- This class does **not** produce PDF, DOCX, or any format other than HTML (via `ReportModule`).
- This class does **not** perform data transformation, reconciliation, or statistical computation beyond sorting metric tables.
- This class does **not** validate that WandB metrics are correct or consistent with on-disk data; it renders whatever WandB returns.

---

## 3. Responsibilities and Guarantees

- **Report structure.** Produces an HTML report with a fixed section order: heading, run summary, task description, model metrics tables, and (optionally) prediction sample graphs.
- **Run summary metadata.** Extracts run ID, owner, date, pipeline version, and (for ensembles) constituent model names from the WandB run object and `PipelineConfig.current_version` (lines 88-101).
- **Task description.** Documents the target variable, spatiotemporal resolution, evaluation scheme (Rolling-Origin Holdout), forecast lead times, rolling-origin count, context/target window configuration, and training schedule from WandB metadata (lines 103-117).
- **Metric collection.** Reads metric names from the pipeline config (supporting multiple config key variants: `regression_point_metrics`, `regression_sample_metrics`, `classification_point_metrics`, `classification_sample_metrics`, `regression_metrics`, `classification_metrics`, `metrics`) and deduplicates them (lines 71-79).
- **Baseline model inclusion.** Collects baseline model names from tier-specific config keys (`regression_point_baselines`, `regression_sample_baselines`, `classification_point_baselines`, `classification_sample_baselines`) and includes them in the comparative metric tables (lines 173-181).
- **Constituent model verification.** For ensemble reports, retrieves the latest WandB run for each constituent model via `get_latest_run()`, verifies partition metadata consistency (same `level` and same partition boundaries), and raises `ValueError` on mismatch (lines 202-224).
- **Metric table sorting.** Sorts combined metric DataFrames by MSLE first, then CRPS, then the first available metric (lines 265-282).
- **Prediction sample graphs (non-fatal).** `_add_prediction_sample_graphs()` is wrapped in a `try/except` at the caller (lines 297-302). A failure in graph generation does not invalidate the metrics tables already written to the report.
- **HTML export.** Delegates to `ReportModule.export_as_html()` and returns the output `Path` (lines 130-136).

---

## 4. Inputs and Assumptions

- **Constructor requires:**
  - `config` (Dict): Pipeline configuration dictionary, expected to contain metric names, baseline model names, target list, `level` (cm/pgm), and `models` (for ensembles). Typically sourced from `ModelManager(model_path).config`.
  - `model_path` (ModelPathManager): Provides `.target` ("model" or "ensemble"), `.model_name`, `.reports` (output directory), and `._get_generated_predictions_data_file_paths()` / `._get_raw_data_file_paths()`.
  - `run_type` (str): The run type string (e.g., "calibration", "testing").

- **`generate()` requires:**
  - `wandb_run` (wandb.apis.public.runs.Run): A valid WandB run object with `.summary`, `.config`, `.id`, `.url`, `.user.name`, `.user.username`.
  - `target` (str): Target variable name (e.g., "ged_sb").

- **Assumptions per ADR-011 (data on measurement scale):** The class assumes that metric values retrieved from WandB summaries are on their declared measurement scales and renders them as-is. It does not rescale, normalize, or reinterpret metric values.

- **WandB API availability.** `generate()` and `_add_report_content()` make live calls to the WandB API via `get_latest_run()` to fetch constituent model runs. Network access to WandB is required.

- **Prediction file naming convention.** `_add_prediction_sample_graphs()` expects filenames matching `predictions_{run_type}_{YYYYMMDD}_{HHMMSS}_{seq:02d}.parquet` (line 333). Files that do not match this pattern are silently ignored.

- **On-disk data for graphs.** Prediction parquets must exist at paths returned by `model_path._get_generated_predictions_data_file_paths()`. Raw historical data must exist at paths returned by `model_path._get_raw_data_file_paths()` (or the first constituent model's paths for ensembles).

- **`model_path.target` must be "model" or "ensemble".** Any other value raises `ValueError` (lines 120-127).

---

## 5. Outputs and Side Effects

- **Return value.** `generate()` returns a `Path` to the exported HTML file, located at `self.model_path.reports / f"report_{generate_model_file_name(...)}__{target}.html"`.
- **File I/O.** Writes one HTML file via `ReportModule.export_as_html()`.
- **WandB API calls.** `_add_report_content()` issues one `get_latest_run()` call per constituent/baseline model. These are read-only API calls.
- **Logging.** Logs info, warning, and error messages throughout. Warnings for missing metrics, missing prediction files, missing targets in data. Errors for partition metadata mismatches and graph generation failures.
- **No state mutation** on the WandB run, config, or model_path objects.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `model_path.target` not "model" or "ensemble" | `ValueError` raised | `generate`, line 125 |
| No metrics found in config | Warning logged; metric tables will be empty | `generate`, lines 80-81 |
| No baseline models found in config | Warning logged; baseline rows absent | `_add_report_content`, lines 179-180 |
| WandB run retrieval fails for a constituent model | Warning logged, model skipped | `_add_report_content`, lines 196-199 |
| Partition metadata mismatch across constituent models | `ValueError` raised | `_add_report_content`, lines 213-224 |
| Level-of-analysis mismatch across constituent models | `ValueError` raised | `_add_report_content`, line 215 |
| No metrics found for an eval type | Warning logged, table omitted | `_add_report_content`, lines 288-290 |
| Any error in `_add_report_content` (except graph section) | Logged and re-raised | `_add_report_content`, lines 291-293 |
| Graph generation fails (`_add_prediction_sample_graphs`) | Warning logged, graphs omitted, report still valid | `_add_report_content`, lines 297-302 |
| No prediction files on disk | Warning logged, graphs skipped | `_add_prediction_sample_graphs`, lines 327-328 |
| No sequenced prediction files match pattern | Warning logged, graphs skipped | `_add_prediction_sample_graphs`, lines 341-343 |
| Target column missing from historical data | Warning logged, graphs skipped | `_add_prediction_sample_graphs`, lines 379-383 |
| Unknown level for dataset class resolution | Warning logged, graphs skipped | `_add_prediction_sample_graphs`, lines 390-393 |
| Prediction column missing from a sequence file | Warning logged, that sequence skipped | `_add_prediction_sample_graphs`, lines 408-412 |
| Individual sequence graph rendering fails | Warning logged, that sequence skipped | `_add_prediction_sample_graphs`, lines 427-432 |

The prediction-sample-graph subsystem is explicitly designed to be non-fatal. The metric tables section is strict and re-raises exceptions.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_reporting.reports.ReportModule` -- HTML assembly and export
  - `views_reporting.reports.utils` -- `filter_metrics_by_eval_type_and_metrics`, `search_for_item_name`
  - `views_pipeline_core.configs.pipeline.PipelineConfig` -- `.current_version` for report content
  - `views_pipeline_core.files.utils` -- `generate_model_file_name`, `read_dataframe`
  - `views_pipeline_core.managers.model` -- `ForecastingModelManager._resolve_evaluation_sequence_number`, `ModelPathManager`
  - `views_pipeline_core.modules.wandb` -- `format_evaluation_dict`, `format_metadata_dict`, `get_latest_run`, `timestamp_to_date`
  - `views_pipeline_core.data.handlers` -- `CMDataset`, `PGMDataset` (deferred import, lines 317-318)
  - `views_reporting.visualizations.HistoricalLineGraph` (deferred import, line 320)
  - `wandb` -- WandB API client (runtime dependency)
  - `pandas` -- DataFrame operations
- **Must not depend on:**
  - `views_reporting.mapping` (no geographic rendering)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - `views_reporting.transformations` (no data transformation)
- **Trusts:**
  - That WandB run summaries contain correctly formatted evaluation metrics
  - That `format_evaluation_dict` and `format_metadata_dict` normalize WandB data reliably
  - That `get_latest_run` returns the correct latest run for a given model/run_type combination
  - That `ModelPathManager` provides correct file paths for predictions and raw data

---

## 8. Examples of Correct Usage

```python
from views_pipeline_core.managers.model import ModelPathManager
from views_pipeline_core.modules.wandb import get_latest_run
from views_reporting.templates.reports.evaluation import EvaluationReportTemplate

model_path = ModelPathManager("my_ensemble")
config = {
    "models": ["model_a", "model_b"],
    "level": "cm",
    "targets": ["ged_sb"],
    "regression_point_metrics": ["MSE", "MSLE"],
    "regression_point_baselines": ["baseline_model"],
}

template = EvaluationReportTemplate(
    config=config,
    model_path=model_path,
    run_type="calibration",
)

wandb_run = get_latest_run(
    entity="views_pipeline",
    model_name="my_ensemble",
    run_type="calibration",
)
report_path = template.generate(wandb_run=wandb_run, target="ged_sb")
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Passing an invalid target type
model_path = ModelPathManager("some_model")
model_path.target = "unknown"  # Not "model" or "ensemble"
template = EvaluationReportTemplate(config={}, model_path=model_path, run_type="calibration")
template.generate(wandb_run, "ged_sb")  # Raises ValueError

# WRONG: Passing a raw WandB API response dict instead of a Run object
template.generate(wandb_run={"summary": {...}}, target="ged_sb")
# Will crash on attribute access (.summary, .config, .id, .url, .user)

# WRONG: Expecting reports without WandB network access
# The class makes live API calls to WandB for constituent model runs.
# Offline execution will fail in _add_report_content.

# WRONG: Using this class for forecast reports (no evaluation data)
# Use ForecastReportTemplate instead.
```

---

## 10. Test Alignment

**No dedicated tests exist for EvaluationReportTemplate in this repository.** The test suite (`tests/`) contains tests for `ReportModule`, `HistoricalLineGraph`, and other components, but not for the report templates.

Testing this class is difficult because:
- It requires live WandB API access for constituent model runs.
- It requires on-disk prediction parquets for graph generation.
- It depends heavily on `views_pipeline_core` managers and configuration.

Tests that should exist:
- **Green:** Verify that `generate()` produces an HTML file at the expected path given mocked WandB data.
- **Red:** Verify `ValueError` when `model_path.target` is invalid.
- **Red:** Verify `ValueError` on partition metadata mismatch between constituent models.
- **Beige:** Verify full report workflow with mocked WandB API and fixture DataFrames, confirming section order and metric table content.
- **Beige:** Verify that graph generation failure does not prevent metric table export.

---

## 11. Evolution Notes

### Known Deviations

1. **Deferred imports in `_add_prediction_sample_graphs`.** Lines 315-320 use deferred imports for `re`, `CMDataset`, `PGMDataset`, `read_dataframe`, and `HistoricalLineGraph`. This is intentional: the graph section is non-fatal, and deferring these imports avoids loading heavy dependencies when graphs are not needed or when graph generation will be skipped.

2. **Hard-coded eval_types.** `self.eval_types` is set to `["time-series-wise"]` with `"step-wise"` and `"month-wise"` commented out (line 45). Only time-series-wise evaluation is currently rendered.

3. **Heavy WandB coupling.** The class makes one `get_latest_run()` API call per constituent/baseline model during `_add_report_content()`. For ensembles with many models, this creates significant network I/O and latency. There is no caching or batching.

4. **`ForecastingModelManager._resolve_evaluation_sequence_number` is a private method call.** Line 109 calls a private method on an external class to resolve the number of rolling origins. This is fragile and could break if the upstream API changes.

5. **Metric config key proliferation.** Lines 71-79 check seven different config key variants for metric names. This reflects an evolving config schema in `views-pipeline-core` and is a source of maintenance burden.

6. **Ensemble path workaround for historical data.** Lines 360-370 work around the fact that `EnsemblePathManager` has no `data_raw` by falling back to the first constituent model's `ModelPathManager`. This is a known architectural gap.

### Stability

- The report structure (heading, run summary, task description, metrics, graphs) is stable.
- The WandB integration pattern (format dicts, get latest runs, verify partitions) is stable.
- The non-fatal graph subsystem pattern is a deliberate design choice and is stable.

### Expected Changes

- Additional eval types (`step-wise`, `month-wise`) may be enabled.
- WandB dependency could be replaced or abstracted if the pipeline moves to a different experiment tracker.
- Metric config key consolidation in `views-pipeline-core` would simplify lines 71-79.

---

## End of Contract

This document defines the **intended meaning** of `EvaluationReportTemplate`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
