
# Class Intent Contract: EvaluationReportTemplate

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-06-26  
**Related ADRs:** ADR-011 (data on measurement scale), ADR-018 (Render From Given Data — the inversion below), ADR-012 (injected-adapter pattern). See also `cic_evaluation_source.md` (register C-108 / #173).  

---

## 1. Purpose

> **What is this class for?**

EvaluationReportTemplate **renders** self-contained HTML evaluation reports for VIEWS forecasting models and ensembles from an **injected `EvaluationSource`** — a typed `MetricFrame` per model (ADR-018 / C-108) — rather than acquiring metrics itself at render time. It assembles the comparative metric tables, optionally renders historical-vs-predicted line graphs from on-disk predictions (parquet or numpy PredictionFrame per ADR-012), and delegates all HTML assembly to `ReportModule`. WandB is no longer touched by this class: the interim `WandbEvaluationSource` adapter wraps the scrape behind the `EvaluationSource` interface (deleted in B2 / #218).

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute evaluation metrics itself; it renders metrics received from the injected `EvaluationSource` (a `MetricFrame`).
- This class does **not** train, retrain, or modify models in any way.
- This class does **not** acquire its own inputs at render time (ADR-018): it neither calls WandB nor resolves runs — the (interim) `WandbEvaluationSource` adapter does, behind the port. It assumes an injected `EvaluationSource` (or, transitionally, a `wandb_run` it wraps into one).
- This class does **not** produce PDF, DOCX, or any format other than HTML (via `ReportModule`).
- This class does **not** perform data transformation, reconciliation, or statistical computation beyond sorting metric tables.
- This class does **not** validate that the metrics are correct or consistent with on-disk data; it renders the `MetricFrame` it is given.

---

## 3. Responsibilities and Guarantees

- **Report structure.** Produces an HTML report with a fixed section order: heading, run summary, task description, model metrics tables, and (optionally) prediction sample graphs.
- **Run summary metadata.** Renders run ID, owner, date, data/scoring-code version (when present), and (for ensembles) constituent model names from `source.provenance()` (an `EvaluationProvenance`, None-omitted) and `PipelineConfig.current_version`. The interim `WandbEvaluationSource` supplies the clickable WandB `run_url` + owner; the durable `MetricFrameFileSource` omits them (renders `run_id` as plain text + the richer frame provenance).
- **Task description.** Documents the target variable, spatiotemporal resolution, evaluation scheme (Rolling-Origin Holdout), forecast lead times, rolling-origin count, context/target window configuration, and training schedule — sourced from the model **config** (experimental-design parameters, not metrics). Run-resolved partition windows absent from config degrade to `N/A` on the inverted path.
- **Canonical metric selection (ADR-017).** The metric *set* shown is the **central canonical standard** in `ReportingConfig.canonical_report_metrics` (keyed by `{regression,classification}×{point,sample}`), **not** the model's own list. A model occupies a cell when its `<task>_<pred_type>_metrics` config key is present & non-empty (declared, not inferred — ADR-003); one labelled canonical table is rendered per active cell. Values come from each model's `MetricFrame` via `mean_metric_value` (the `group_id="mean"` row); a canonical metric the frame lacks (absent row or NaN) is shown with an explicit "not calculated — add `<metric>` to `<key>`" note (ADR-008), never dropped silently. **C-116:** more than one matching mean row raises `AmbiguousMetric` and renders a visible "ambiguous — multiple matching keys" cell rather than a silently-picked value. (The interim `WandbEvaluationSource` preserves this by emitting one frame row per matching summary key — colliding keys stay distinguishable.)
- **Baseline model inclusion.** Collects baseline model names from tier-specific config keys (`regression_point_baselines`, `regression_sample_baselines`, `classification_point_baselines`, `classification_sample_baselines`) and includes them in the comparative metric tables (lines 173-181).
- **Constituent model verification.** For ensemble reports, the template asks `source.metric_frame(model)` for each declared constituent and verifies `level`/`partition` consistency across the resolved frames (via `unique_axis_value` over the frame axes), raising `ValueError` on mismatch (C-48 — a single ensemble row must not mix constituents from different levels/partitions).
- **Metric-aware run selection (#116 / C-48) — now behind the source.** The metric-aware selection (pick the newest run that actually *carries* the canonical metrics, not the newest-*created* run — fixing the 22/25 production blanking) lives in the interim `WandbEvaluationSource` (which wraps the `evaluation_run_resolver` seam), **not** in this template. The template only consumes `source.metric_frame(model)`. The selection logic and the resolver are **deleted in Phase 3 / B2 (C-108)** once pipeline-core persists frames and injects a `MetricFrameFileSource`; the same-partition stale-relog limitation is closed then (C-110, gated on #220 provenance).
- **Constituent resolution — degrade-and-announce (#105, honoring the #177 contract).** A declared constituent is never silently dropped. The source reporting **ABSENT** (`metric_frame(model)` returns `None`) records the model and **announces** it under "Model Metrics" as missing. A `metric_frame` call that **raises** (a **transient** failure) is **retried once**; if it still fails the model is **marked degraded** and announced distinctly (a retrieval error, not a confirmed absence). Absent and degraded models contribute no metrics row. Opt-in **strict mode** (`config["strict_constituents"] = True`) instead raises `ValueError` listing the absent/degraded models. (ADR-008 fail-loud / make-degradation-visible.) The subject model is always rendered (an absent subject shows "not calculated" cells).
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

- **WandB API availability.** `_add_report_content()` makes live calls to the WandB API via the `evaluation_run_resolver` seam (`wandb.Api().runs(...)`) to enumerate and select constituent model runs. Network access to WandB is required.

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
- **WandB API calls.** `_add_report_content()` enumerates a model's runs (one `wandb.Api().runs(...)` query per constituent/baseline model, via the `evaluation_run_resolver` seam) to select the metric-bearing one. These are read-only API calls.
- **Logging.** Logs info, warning, and error messages throughout. Warnings for missing metrics, missing prediction files, missing targets in data. Errors for partition metadata mismatches and graph generation failures.
- **No state mutation** on the WandB run, config, or model_path objects.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `model_path.target` not "model" or "ensemble" | `ValueError` raised | `generate`, line 125 |
| No active metric cells (no `*_metrics` config keys) | Visible "_No metric standard active_" note added (not silent) | `_add_report_content` |
| Canonical metric absent from the run | Cell shows "not calculated — add `<metric>` to `<key>`" note (not dropped) | `_add_report_content` |
| Canonical metric **ambiguous** (>1 run-summary key segment-matches the token) | `search_for_item_name` raises (default `on_ambiguous="raise"`); the value site catches it and the cell shows a visible **"ambiguous — multiple matching keys"** note — never a silently-picked (possibly-wrong) number, and the report still generates (C-116 / ADR-008) | `_canonical_row` |
| No baseline models found in config | Warning logged; baseline rows absent | `_add_report_content`, lines 179-180 |
| Declared constituent absent (resolver finds no run, or no run carries the canonical metrics for the target) | Warning logged; model **announced** as missing in a visible note; no metrics row (not silently dropped) | `_add_report_content` |
| Declared constituent transient failure (run resolution raises) | Retried once; on repeat failure, error logged and model **announced** as degraded; no metrics row | `_add_report_content` |
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
  - `views_pipeline_core.modules.wandb` -- `format_evaluation_dict`, `format_metadata_dict`, `timestamp_to_date` (constituent run *selection* moved to the `evaluation_run_resolver` seam — #116)
  - `views_reporting.templates.reports.evaluation_run_resolver` -- `resolve_constituent_run`, `Resolution` (interim metric-aware selection seam, deleted in Phase 3 / C-108)
  - `views_pipeline_core.data.handlers` -- `CMDataset`, `PGMDataset` (deferred import, lines 317-318)
  - `views_reporting.visualizations.HistoricalLineGraph` (deferred import, line 320)
  - `wandb` -- WandB API client (runtime dependency)
  - `pandas` -- DataFrame operations
- **Must not depend on:**
  - `views_reporting.mapping` (no geographic rendering)
  - `views_reporting.reconciliation` (no reconciliation logic)
- **Trusts:**
  - That WandB run summaries contain correctly formatted evaluation metrics
  - That `format_evaluation_dict` and `format_metadata_dict` normalize WandB data reliably
  - That the `evaluation_run_resolver` seam selects the newest metric-bearing run for a model/run_type/target (metric-aware, #116) — superseding the prior trust that `get_latest_run` returned the correct run
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
- **Beige:** `test_single_model_eval_report_offline` — a single-model report (no constituent run-resolution calls) renders all sections (Run Summary, Task Description, Model Metrics with a rendered metric, Prediction Samples) and the sample graphs carry the 90/95/99% HDI legend selector + the hindcast caption.
- **Beige:** `test_ensemble_eval_report_offline` — an ensemble report with constituent runs supplied via a monkeypatched `evaluation_run_resolver.list_runs` concatenates ensemble + constituent metric rows and lists Constituent Models.
- **Green (ADR-017):** `test_canonical_multicell_tables_and_missing_note` — a multi-cell model renders one canonical table per active cell (e.g. "Regression (point)", "Classification (point)"), drawing the metric set from `ReportingConfig` (not the model's list), and shows the "not calculated — add … to `<key>`" note for canonical metrics the run lacks. Config-map coverage in `tests/test_config.py::TestCanonicalReportMetrics`.
- **Red (C-40):** `tests/test_falsification_eval_ensemble_samples.py::test_ensemble_eval_missing_models_surfaces_skipped_samples` — a misconfigured ensemble adds a VISIBLE "Prediction samples unavailable" note instead of dropping the section silently.

> **Honesty caveat:** the synthetic run's metric *values* are illustrative; the report
> *structure* and graphs are real. The metric numbers are not from a real evaluation
> (use the pipeline `--evaluate --report` for that). `scripts/generate_demo_eval_reports.py`
> regenerates a full offline eval report for visual inspection.

Still WandB-bound for real metric values (constituent runs via the `evaluation_run_resolver` seam); the
double mocks exactly that closed surface (`.summary/.config/.id/.url/.user`).
- **Beige:** Verify that graph generation failure does not prevent metric table export.

---

## 11. Evolution Notes

### Known Deviations

1. **Deferred imports in `_add_prediction_sample_graphs`.** Lines 315-320 use deferred imports for `re`, `CMDataset`, `PGMDataset`, `read_dataframe`, and `HistoricalLineGraph`. This is intentional: the graph section is non-fatal, and deferring these imports avoids loading heavy dependencies when graphs are not needed or when graph generation will be skipped.

2. **Hard-coded eval_types.** `self.eval_types` is set to `["time-series-wise"]` with `"step-wise"` and `"month-wise"` commented out (line 45). Only time-series-wise evaluation is currently rendered.

3. **Heavy WandB coupling.** The class makes one run-enumeration (`wandb.Api().runs(...)`, via the `evaluation_run_resolver` seam) per constituent/baseline model during `_add_report_content()`. For ensembles with many models, this creates significant network I/O and latency. There is no caching or batching. (Dissolved in Phase 3 / C-108 when the seam is replaced by an injected `MetricFrame` source.)

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
