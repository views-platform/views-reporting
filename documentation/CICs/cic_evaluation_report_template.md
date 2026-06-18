
# Class Intent Contract: EvaluationReportTemplate

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-06-04  
**Related ADRs:** ADR-011 (data on measurement scale)  

---

## 1. Purpose

> **What is this class for?**

EvaluationReportTemplate generates self-contained HTML evaluation reports for VIEWS forecasting models and ensembles. It retrieves evaluation metrics and metadata from a Weights & Biases run, fetches constituent-model runs for comparative metric tables, optionally renders historical-vs-predicted line graphs from on-disk predictions (parquet or numpy PredictionFrame per ADR-012), and delegates all HTML assembly to `ReportModule`.

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
- **Canonical metric selection (ADR-017).** The metric *set* shown is the **central canonical standard** in `ReportingConfig.canonical_report_metrics` (keyed by `{regression,classification}×{point,sample}`), **not** the model's own list. A model occupies a cell when its `<task>_<pred_type>_metrics` config key is present & non-empty (declared, not inferred — ADR-003); one labelled canonical table is rendered per active cell. Values come from the WandB run; a canonical metric the run lacks is shown with an explicit "not calculated — add `<metric>` to `<key>`" note (ADR-008), never dropped silently.
- **Baseline model inclusion.** Collects baseline model names from tier-specific config keys (`regression_point_baselines`, `regression_sample_baselines`, `classification_point_baselines`, `classification_sample_baselines`) and includes them in the comparative metric tables (lines 173-181).
- **Constituent model verification.** For ensemble reports, retrieves the latest WandB run for each constituent model via `get_latest_run()`, verifies partition metadata consistency across the *resolved* runs (same `level` and same partition boundaries), and raises `ValueError` on mismatch.
- **Constituent resolution — degrade-and-announce (#105, honoring the `get_latest_run` #177 contract).** A declared constituent is never silently dropped. `get_latest_run()` returning `None` (genuinely **absent** — no cloud run) records the model and **announces** it under "Model Metrics" as missing. `get_latest_run()` **raising** (a **transient** lookup failure) is **retried once**; if it still fails the model is **marked degraded** and announced distinctly (a retrieval error, not a confirmed absence). Absent and degraded models contribute no metrics row. Opt-in **strict mode** (`config["strict_constituents"] = True`) instead raises `ValueError` listing the absent/degraded models. (ADR-008 fail-loud / make-degradation-visible; replaces the prior silent `except: continue`.)
- **Metric table sorting.** Sorts combined metric DataFrames by MSLE first, then CRPS, then the first available metric (lines 265-282).
- **Prediction sample graphs (non-fatal).** `_add_prediction_sample_graphs()` is wrapped in a `try/except` at the caller (lines 297-302). A failure in graph generation does not invalidate the metrics tables already written to the report.
- **HTML export.** Delegates to `ReportModule.export_as_html()` and returns the output `Path` (lines 130-136).

---

## 4. Inputs and Assumptions

- **Constructor requires:**
  - `config` (Dict): Pipeline configuration dictionary, expected to contain metric names, baseline model names, target list, `level` (cm/pgm), and `models` (for ensembles). Optional `strict_constituents` (bool, default `False`) turns any absent/degraded constituent into a hard `ValueError` instead of a degrade-and-announce note. Typically sourced from `ModelManager(model_path).config`.
  - `model_path` (ModelPathManager): Provides `.target` ("model" or "ensemble"), `.model_name`, `.reports` (output directory), and `._get_generated_predictions_data_file_paths()` / `._get_raw_data_file_paths()`.
  - `run_type` (str): The run type string (e.g., "calibration", "testing").

- **`generate()` requires:**
  - `wandb_run` (wandb.apis.public.runs.Run): A valid WandB run object with `.summary`, `.config`, `.id`, `.url`, `.user.name`, `.user.username`.
  - `target` (str): Target variable name (e.g., "ged_sb").

- **Assumptions per ADR-011 (data on measurement scale):** The class assumes that metric values retrieved from WandB summaries are on their declared measurement scales and renders them as-is. It does not rescale, normalize, or reinterpret metric values.

- **WandB API availability.** `generate()` and `_add_report_content()` make live calls to the WandB API via `get_latest_run()` to fetch constituent model runs. Network access to WandB is required.

- **Prediction file discovery (ADR-012).** `_add_prediction_sample_graphs()` dispatches based on `config["prediction_format"]` (default: `"dataframe"`):
  - `"dataframe"`: discovers parquet files matching `predictions_{run_type}_{YYYYMMDD}_{HHMMSS}_{seq:02d}.parquet` via `_discover_parquet_origins()`.
  - `"prediction_frame"`: discovers numpy origin directories via `_discover_pf_origins()`.
  - Both formats then load each origin through the Ingestion layer via `load_predictions(prediction_format, …)` — the template never reads prediction storage directly (ADR-002 forbids Composition bypassing the format boundary; C-32). The raw *historical* series is read directly via `read_dataframe()` because it is observed data, not prediction storage, and is outside the loader surface.

- **On-disk data for graphs.** Prediction data must exist at paths discovered by the format-appropriate discovery method. Raw historical data must exist at paths returned by `model_path._get_raw_data_file_paths()` (or the first constituent model's paths for ensembles).

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
| No active metric cells (no `*_metrics` config keys) | Visible "_No metric standard active_" note added (not silent) | `_add_report_content` |
| Canonical metric absent from the run | Cell shows "not calculated — add `<metric>` to `<key>`" note (not dropped) | `_add_report_content` |
| No baseline models found in config | Warning logged; baseline rows absent | `_add_report_content`, lines 179-180 |
| Declared constituent absent (`get_latest_run` → `None`) | Warning logged; model **announced** as missing in a visible note; no metrics row (not silently dropped) | `_add_report_content` |
| Declared constituent transient failure (`get_latest_run` raises) | Retried once; on repeat failure, error logged and model **announced** as degraded; no metrics row | `_add_report_content` |
| Absent/degraded constituent **with** `strict_constituents=True` | `ValueError` raised listing the unresolved models | `_add_report_content` |
| Partition metadata mismatch across constituent models | `ValueError` raised | `_add_report_content` |
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

**`tests/test_e2e_eval_report.py`** drives `generate()` end-to-end **offline** via a
synthetic WandB-run double (`tests/_wandb_doubles.py` + `tests/data/red_ranger/wandb_run.json`),
so the full report is reproducible from the repo alone and regression-guarded:
- **Beige:** `test_single_model_eval_report_offline` — a single-model report (no `get_latest_run` calls) renders all sections (Run Summary, Task Description, Model Metrics with a rendered metric, Prediction Samples) and the sample graphs carry the 90/95/99% HDI legend selector + the hindcast caption.
- **Beige:** `test_ensemble_eval_report_offline` — an ensemble report with constituent runs supplied via a monkeypatched `get_latest_run` concatenates ensemble + constituent metric rows and lists Constituent Models.
- **Green (ADR-017):** `test_canonical_multicell_tables_and_missing_note` — a multi-cell model renders one canonical table per active cell (e.g. "Regression (point)", "Classification (point)"), drawing the metric set from `ReportingConfig` (not the model's list), and shows the "not calculated — add … to `<key>`" note for canonical metrics the run lacks. Config-map coverage in `tests/test_config.py::TestCanonicalReportMetrics`.
- **Red (C-40):** `tests/test_falsification_eval_ensemble_samples.py::test_ensemble_eval_missing_models_surfaces_skipped_samples` — a misconfigured ensemble adds a VISIBLE "Prediction samples unavailable" note instead of dropping the section silently.

> **Honesty caveat:** the synthetic run's metric *values* are illustrative; the report
> *structure* and graphs are real. The metric numbers are not from a real evaluation
> (use the pipeline `--evaluate --report` for that). `scripts/generate_demo_eval_reports.py`
> regenerates a full offline eval report for visual inspection.

Still WandB-bound for real metric values (constituent runs via `get_latest_run`); the
double mocks exactly that closed surface (`.summary/.config/.id/.url/.user`).
- **Beige:** Verify that graph generation failure does not prevent metric table export.

---

## 11. Evolution Notes

### Known Deviations

1. **Deferred imports in `_add_prediction_sample_graphs`.** Lines 315-320 use deferred imports for `re`, `CMDataset`, `PGMDataset`, `read_dataframe`, and `HistoricalLineGraph`. This is intentional: the graph section is non-fatal, and deferring these imports avoids loading heavy dependencies when graphs are not needed or when graph generation will be skipped.

2. **Hard-coded eval_types.** `self.eval_types` is set to `["time-series-wise"]` with `"step-wise"` and `"month-wise"` commented out (line 45). Only time-series-wise evaluation is currently rendered.

3. **Heavy WandB coupling.** The class makes one `get_latest_run()` API call per constituent/baseline model during `_add_report_content()`. For ensembles with many models, this creates significant network I/O and latency. There is no caching or batching.

4. **`ForecastingModelManager._resolve_evaluation_sequence_number` is a private method call.** Line 109 calls a private method on an external class to resolve the number of rolling origins. This is fragile and could break if the upstream API changes.

5. ~~Metric config key proliferation (seven config key variants merged).~~ — **RESOLVED (ADR-017).** The report no longer merges the model's seven metric-key variants; it renders the **central canonical standard** (`ReportingConfig.canonical_report_metrics`) per active cell, using the four `<task>_<pred_type>_metrics` keys only to determine cell occupancy.

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
