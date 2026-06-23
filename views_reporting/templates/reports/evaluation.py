"""EvaluationReportTemplate: generates HTML evaluation reports with metrics, sample graphs, and WandB integration."""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd
import wandb
from views_pipeline_core.configs.pipeline import PipelineConfig
from views_pipeline_core.files.utils import (
    generate_model_file_name,
)
from views_pipeline_core.managers.model import ForecastingModelManager, ModelPathManager
from views_pipeline_core.modules.wandb import (
    format_evaluation_dict,
    format_metadata_dict,
    timestamp_to_date,
)

from views_reporting.config import get_config
from views_reporting.reports import (
    ReportModule,
    search_for_item_name,
)
from views_reporting.templates.reports.evaluation_run_resolver import (
    Resolution,
    resolve_constituent_run,
)

logger = logging.getLogger(__name__)


class EvaluationReportTemplate:
    def __init__(self, config: Dict, model_path: ModelPathManager, run_type: str):
        """
        Initializes the evaluation report class with model/ensemble configuration, model path manager, and run type.

        Args:
            config (Dict): Configuration dictionary containing evaluation parameters. You will find this in `ModelManager(model_path).config`.
            model_path (ModelPathManager): Manager object for handling model paths.
            run_type (str): Type of run.

        Attributes:
            eval_types (tuple): Types of evaluation supported ('time-series-wise', 'step-wise', 'month-wise').
            baseline_models (list): List of baseline model names used for comparison.
        """
        self.config = config
        self.model_path = model_path
        self.run_type = run_type
        self.eval_types = ["time-series-wise"] # "step-wise", "month-wise"
        self.views_models_url = "https://github.com/views-platform/views-models"

    def generate(self, wandb_run: "wandb.apis.public.runs.Run", target: str) -> Path:
        """
        Generate an evaluation report based on the provided Weights & Biases run and target variable.

        This method compiles metadata, evaluation metrics, and run details into a structured report,
        including task description and summary information. The report is exported as an HTML file
        to a designated path.

        Args:
            wandb_run (wandb.apis.public.runs.Run): The Weights & Biases run object containing summary and config data.
            target (str): The name of the target variable for which the evaluation report is generated.

        Returns:
            Path: The file path to the generated HTML evaluation report.

        Raises:
            ValueError: If the model target type is not 'model' or 'ensemble'.
        """
        """Generate an evaluation report based on the evaluation DataFrame."""
        evaluation_dict = format_evaluation_dict(dict(wandb_run.summary))
        metadata_dict = format_metadata_dict(dict(wandb_run.config))

        report_manager = ReportModule()
        report_manager.add_heading(
            f"Evaluation report for {self.model_path.target} {self.model_path.model_name}",
            level=1,
        )
        _timestamp = dict(wandb_run.summary).get("_timestamp", None)
        run_date_str = f"{timestamp_to_date(_timestamp)}" if _timestamp else "N/A"
        report_manager.add_heading("Run Summary", level=2)
        markdown_text = (
            f"**Run ID**: [{wandb_run.id}]({wandb_run.url}) (links to WandB run) \n"
            f"**Owner**: {wandb_run.user.name} ({wandb_run.user.username})  \n"
            f"**Run Date**: {run_date_str}  \n"
        )
        if self.model_path.target == "ensemble":
            markdown_text += (
                f"**Constituent Models**: {metadata_dict.get('models', None)}  \n"
            )
        markdown_text += f"**Pipeline Version**: {PipelineConfig.current_version}"
        report_manager.add_markdown(markdown_text=markdown_text)

        task_definition_md = (
            f"- **Target Variable**: {target}\n"
            f"- **Spatiotemporal Resolution**: {metadata_dict.get('level', 'N/A')}\n"
            f"- **Evaluation Scheme**: `Rolling-Origin Holdout`\n"
            f"    - **Minimum forecast lead time**: {metadata_dict.get('steps', [None, None])[0]}\n"
            f"    - **Maximum forecast lead time**: {metadata_dict.get('steps', [None, None])[-1]}\n"
            f"    - **Number of Rolling Origins**: {ForecastingModelManager._resolve_evaluation_sequence_number(str(metadata_dict.get('eval_type', 'standard')).lower())}\n"
            f"    - **Context Window Origin**: {metadata_dict.get(self.run_type, {'train': [None, None], 'test': [None, None]}).get('train')[0]}\n"
            f"    - **Context Window Schedule**: Fixed-origin, Expanding\n"
            f"    - **Target Window Schedule**: Rolling-origin, Fixed-length\n"
            f"    - **Target Window First Origin**: {metadata_dict.get(self.run_type, {'train': [None, None], 'test': [None, None]}).get('test')[0]}\n"
            f"    - **Training Schedule**: Frozen trained model artifact\n"
        )
        report_manager.add_heading("Task Description", level=2)
        report_manager.add_markdown(markdown_text=task_definition_md)

        # Model-specific report content
        if self.model_path.target in ("model", "ensemble"):
            self._add_report_content(
                report_manager, metadata_dict, evaluation_dict, target
            )
        else:
            raise ValueError(
                f"Invalid target type: {self.model_path.target}. Expected 'model' or 'ensemble'."
            )

        # Generate report path
        report_path = (
            self.model_path.reports
            / f"report_{generate_model_file_name(run_type=self.run_type, file_extension='')}_{target}.html"
        )
        report_manager.export_as_html(report_path)
        logger.info(f"Exported report to {report_path}")
        return report_path

    def _add_report_content(
        self,
        report_manager: ReportModule,
        metadata_dict: Dict,
        evaluation_dict: Dict,
        target_identifier: str,
    ) -> None:
        """
        Adds content to the evaluation report.

        This method populates the evaluation report with metrics and metadata for ensemble and single model runs. It performs the following steps:
        1. Retrieves the list of models involved in the ensemble, including any baseline models.
        2. Gathers the latest calibration run for each constituent model.
        3. Verifies that the partition metadata (e.g., calibration, validation, forecasting) is consistent across all constituent models.
        4. For each evaluation type, collects and combines metrics from both the ensemble and its constituent models.
        5. Sorts the combined metrics by the specified metric and adds them as tables to the report.

        Args:
            report_manager (ReportModule): The report manager instance used to add content to the report.
            metadata_dict (Dict): Metadata dictionary for the ensemble run.
            evaluation_dict (Dict): Evaluation results dictionary for the ensemble run.
            target_identifier (str): Identifier for the target variable.

        Raises:
            ValueError: If partition metadata is inconsistent across constituent models.
            Exception: If any other error occurs during report generation, it is logged and re-raised.
        """
        models = self.config.get(
            "models", []
        )  # will only be populated for ensemble runs
        # models.append(self.model_path.model_name)

        # Collect baseline model names from all tier-specific keys in the pipeline config.
        baseline_models = list(dict.fromkeys(
            self.config.get("regression_point_baselines", []) +
            self.config.get("regression_sample_baselines", []) +
            self.config.get("classification_point_baselines", []) +
            self.config.get("classification_sample_baselines", [])
        ))
        if not baseline_models:
            logger.warning("No baseline models found in config. Baseline rows will be absent from the report.")
        models = list(set(models).union(baseline_models))
        logger.info(f"Models to search for: {models}")
        verified_partition_dict = None
        verified_level = metadata_dict.get("level", None)

        # Active {task}×{pred_type} metric cells (ADR-017) and the union of their
        # canonical metrics — computed once and reused: it scopes metric-aware run
        # selection below (#116) and drives the metric tables further down.
        cell_keys = {
            ("regression", "point"): "regression_point_metrics",
            ("regression", "sample"): "regression_sample_metrics",
            ("classification", "point"): "classification_point_metrics",
            ("classification", "sample"): "classification_sample_metrics",
        }
        active_cells = [c for c, k in cell_keys.items() if self.config.get(k)]
        canonical_cfg = get_config()
        expected_metrics = {
            metric
            for cell in active_cells
            for metric in canonical_cfg.canonical_metrics(*cell)
        }
        eval_type_for_selection = (
            self.eval_types[0] if self.eval_types else "time-series-wise"
        )

        # Resolve each declared constituent's evaluation run — metric-aware (#116,
        # C-48): pick the newest run that actually carries this target's canonical
        # metrics, not merely the newest-*created* run (which may be a non-eval run
        # lacking them). Honors the #105/#177 contract:
        #   * ABSENT (no run, or no metric-bearing run) -> surface as missing.
        #   * raise -> TRANSIENT: the lookup hiccupped (network/API); retry once,
        #              then mark the model DEGRADED rather than dropping it silently.
        # Opt-in strict mode (`strict_constituents`) turns absent/degraded into a hard
        # failure. Selection lives in the interim `evaluation_run_resolver` seam, which
        # Phase 3 replaces with an injected MetricFrame source (C-108).
        strict_constituents = bool(self.config.get("strict_constituents", False))
        constituent_model_runs = []
        absent_models: list = []
        degraded_models: list = []
        for model in models:
            try:
                resolution = resolve_constituent_run(
                    model=model,
                    run_type=self.run_type,
                    target=target_identifier,
                    eval_type=eval_type_for_selection,
                    canonical_metrics=expected_metrics,
                )
            except Exception as e:
                # Transient per the contract: a raise means the lookup failed, not
                # that the model is absent. Retry once before degrading.
                logger.warning(
                    f"Transient error resolving run for '{model}': {e}. Retrying once...",
                    exc_info=False,
                )
                try:
                    resolution = resolve_constituent_run(
                        model=model,
                        run_type=self.run_type,
                        target=target_identifier,
                        eval_type=eval_type_for_selection,
                        canonical_metrics=expected_metrics,
                    )
                except Exception as e2:
                    logger.error(
                        f"Run resolution for '{model}' failed after retry: {e2}. "
                        "Marking constituent as degraded."
                    )
                    degraded_models.append(model)
                    continue
            if resolution.status is Resolution.RESOLVED:
                constituent_model_runs.append(resolution.run)
            else:
                logger.warning(
                    f"No evaluation run with the canonical metrics found for declared "
                    f"constituent '{model}' ({resolution.detail}); marking as missing "
                    "(absent)."
                )
                absent_models.append(model)

        if strict_constituents and (absent_models or degraded_models):
            raise ValueError(
                "strict_constituents: declared constituents did not resolve — "
                f"absent={sorted(absent_models)}, degraded={sorted(degraded_models)}"
            )

        # Verify partition metadata consistency
        try:
            for model_run in constituent_model_runs:
                temp_metadata_dict = format_metadata_dict(dict(model_run.config))
                partition_metadata_dict = {
                    k: v
                    for k, v in temp_metadata_dict.items()
                    if k.lower() == self.run_type.lower()
                }
                if verified_level is None:
                    verified_level = temp_metadata_dict.get("level", None)
                elif verified_level != temp_metadata_dict.get("level", None):
                    raise ValueError(
                        f"LoA metadata mismatch between models: Offending model: {temp_metadata_dict.get('name', 'N/A')}. Expected level: {verified_level}, found: {temp_metadata_dict.get('level', 'N/A')}"
                    )
                model_name = temp_metadata_dict.get("name", "N/A")
                if verified_partition_dict is None:
                    verified_partition_dict = partition_metadata_dict
                elif verified_partition_dict != partition_metadata_dict:
                    logger.error("Partition metadata mismatch: %s vs %s", verified_partition_dict, partition_metadata_dict)
                    raise ValueError(
                        f"Partition metadata mismatch between models: Offending model: {model_name}"
                    )

            # Canonical Model Metrics (ADR-017): the report shows the CENTRAL
            # canonical metric standard per active cell — NOT the model's own
            # metric list. A model occupies a {task}x{point,sample} cell when its
            # `<task>_<pred_type>_metrics` config key is non-empty; for each active
            # cell we render the canonical metrics, pulling values from the run and
            # noting any the run lacks (with the exact key to set).
            report_manager.add_heading("Model Metrics", level=2)
            report_manager.add_markdown(
                markdown_text=f"More information about the following models can be found [here]({self.views_models_url})\n"
            )

            # Degrade-and-announce (#105): declared constituents that did not
            # resolve are made VISIBLE here rather than silently dropped. Absent
            # (None) and degraded (transient/raised) are surfaced distinctly, per
            # the #177 contract, so a partial ensemble table is self-evidently partial.
            if absent_models:
                report_manager.add_markdown(
                    "> ⚠️ **Declared constituent(s) with no evaluation run found "
                    "(absent):** "
                    + ", ".join(f"`{m}`" for m in sorted(absent_models))
                    + ". These models are part of the declared ensemble but have no "
                    "resolvable run, so they contribute no metrics row below."
                )
            if degraded_models:
                report_manager.add_markdown(
                    "> ⚠️ **Constituent(s) whose run could not be retrieved "
                    "(degraded — transient failure):** "
                    + ", ".join(f"`{m}`" for m in sorted(degraded_models))
                    + ". Their metrics are temporarily unavailable; this is a "
                    "retrieval error, not a confirmed absence."
                )

            # `active_cells` / `canonical_cfg` were computed above (they also scope
            # metric-aware run selection); here we only announce when none are active.
            if not active_cells:
                report_manager.add_markdown(
                    "_No metric standard active: the model config declares no "
                    "`*_point_metrics` / `*_sample_metrics`._"
                )

            def _canonical_row(eval_dict, model_name, task, pred_type, eval_type):
                cfg_key = f"{task}_{pred_type}_metrics"
                canonical = canonical_cfg.canonical_metrics(task, pred_type)
                row = {}
                for metric in canonical:
                    found = search_for_item_name(
                        searchspace=list(eval_dict.keys()),
                        keywords=[eval_type, metric, target_identifier, "mean"],
                    )
                    row[metric] = (
                        eval_dict[found]
                        if found
                        else f"not calculated — add '{metric}' to {cfg_key}"
                    )
                return pd.DataFrame([row], columns=list(canonical), index=[model_name])

            def _maybe_sort(dataframe):
                # Sort by MSLE, then CRPS, then the first fully-numeric column.
                # Skip if the chosen column has any "not calculated" note (non-numeric).
                preferred = [
                    search_for_item_name(dataframe.columns.tolist(), [c])
                    for c in ("MSLE", "CRPS")
                ]
                for col in [c for c in preferred if c] + list(dataframe.columns):
                    if pd.to_numeric(dataframe[col], errors="coerce").notna().all():
                        return dataframe.sort_values(by=col, ascending=True)
                return dataframe

            for eval_type in self.eval_types:
                for task, pred_type in active_cells:
                    metric_dataframe = _canonical_row(
                        evaluation_dict,
                        metadata_dict.get("name", None),
                        task, pred_type, eval_type,
                    )
                    for model_run in constituent_model_runs:
                        c_eval = format_evaluation_dict(dict(model_run.summary))
                        c_meta = format_metadata_dict(dict(model_run.config))
                        metric_dataframe = pd.concat(
                            [
                                metric_dataframe,
                                _canonical_row(
                                    c_eval, c_meta.get("name", None),
                                    task, pred_type, eval_type,
                                ),
                            ],
                            axis=0,
                        )
                    report_manager.add_table(
                        data=_maybe_sort(metric_dataframe),
                        header=(
                            f"{eval_type.replace('-', ' ').title()} — "
                            f"{task.title()} ({pred_type})"
                        ),
                    )
        except Exception as e:
            logger.error(f"Error generating ensemble report: {e}", exc_info=True)
            raise

        # Prediction sample graphs — non-fatal: a failure here does not
        # invalidate the metrics tables already written above.
        try:
            self._add_prediction_sample_graphs(report_manager, target_identifier)
        except Exception as e:
            logger.warning(
                f"Could not generate prediction sample graphs: {e}", exc_info=True
            )
            # Surface the failure in the report (C-40) rather than silently
            # dropping the section.
            report_manager.add_heading("Prediction Samples", level=2)
            report_manager.add_markdown(
                f"_Prediction samples unavailable: {e}._"
            )

    def _add_prediction_sample_graphs(
        self,
        report_manager: "ReportModule",
        target_identifier: str,
    ) -> None:
        """Add historical vs. predicted line graphs for first, middle, and last
        rolling-origin sequences of the most recent prediction run.

        Sequence indices are computed dynamically from however many sequence
        files exist on disk — no fixed numbers assumed.
        """

        from views_frames import SpatialLevel
        from views_pipeline_core.files.utils import read_dataframe

        from views_reporting.loaders import (
            load_predictions,
            target_frame_from_dataframe,
        )
        from views_reporting.visualizations import HistoricalLineGraph

        prediction_format = self.config.get("prediction_format", "dataframe")
        _levels = {"cm": SpatialLevel.CM, "pgm": SpatialLevel.PGM}

        def _note_unavailable(reason: str) -> None:
            # Make a skipped section VISIBLE in the report (C-40): a partial eval
            # report must not read as complete. Emits the heading + an explicit
            # reason rather than returning with only a log line.
            report_manager.add_heading("Prediction Samples", level=2)
            report_manager.add_markdown(
                f"_Prediction samples unavailable: {reason}._"
            )

        # ── 1. Collect all sequenced prediction files ─────────────────
        if prediction_format == "prediction_frame":
            latest_files = self._discover_pf_origins()
        else:
            latest_files = self._discover_parquet_origins()

        if not latest_files:
            logger.warning("No prediction files found — skipping prediction sample graphs.")
            _note_unavailable("no prediction files found")
            return

        n = len(latest_files)

        # ── 3. Pick first, middle, last (deduplicated) ────────────────
        indices = sorted({0, n // 2, n - 1})
        selected = [latest_files[i] for i in indices]

        # ── 4. Load historical data ────────────────────────────────────
        # EnsemblePathManager has no data_raw; use the first constituent model instead.
        if self.model_path.target == "ensemble":
            from views_pipeline_core.data.model_path import ModelPathManager
            constituent_models = self.config.get("models", [])
            if not constituent_models:
                logger.warning(
                    "Ensemble config has no 'models' list — skipping prediction sample graphs."
                )
                _note_unavailable("ensemble config has no constituent 'models' list")
                return
            data_path_manager = ModelPathManager(constituent_models[0])
        else:
            data_path_manager = self.model_path

        raw_paths = data_path_manager._get_raw_data_file_paths(self.run_type)
        if not raw_paths:
            logger.warning("No raw data files found — skipping prediction sample graphs.")
            _note_unavailable("no historical raw-data files found")
            return
        historical_df = read_dataframe(raw_paths[0])

        if target_identifier not in historical_df.columns:
            logger.warning(
                f"Target '{target_identifier}' not found in historical data — "
                "skipping prediction sample graphs."
            )
            _note_unavailable(
                f"target '{target_identifier}' not present in the historical data"
            )
            return

        # ── 5. Resolve SpatialLevel from config level ─────────────────
        # Fail-loud on a missing/unknown level rather than silently defaulting to
        # 'cm' (C-45): a PGM model with no/typo'd `level` would otherwise pick the
        # wrong level and mis-render. Non-fatal section (C-40) → surface a
        # visible skip, not a hard raise.
        level = self.config.get("level")
        spatial_level = _levels.get(level)
        if spatial_level is None:
            reason = (
                "missing 'level' in config"
                if level is None
                else f"unknown spatiotemporal level '{level}'"
            )
            logger.warning(f"Prediction sample graphs skipped — {reason}.")
            _note_unavailable(reason)
            return

        historical_frame = target_frame_from_dataframe(
            historical_df, level, target_identifier
        )

        # ── 6. Render one graph per selected sequence ─────────────────
        report_manager.add_heading("Prediction Samples", level=2)
        report_manager.add_markdown(
            "Historical vs. predicted values for the **first**, **middle**, and "
            "**last** rolling-origin sequences"
        )

        # `level` was resolved + validated above (no silent default).
        for seq_num, pred_path in selected:
            try:
                if prediction_format == "prediction_frame":
                    forecast_frames = load_predictions(
                        "prediction_frame", pred_path, level, [target_identifier]
                    )
                else:
                    # Route the parquet read through the Ingestion layer rather
                    # than reading prediction storage directly (ADR-002 forbids
                    # Composition bypassing the format boundary; C-32).
                    try:
                        forecast_frames = load_predictions(
                            "dataframe", pred_path, level, [target_identifier]
                        )
                    except ValueError:
                        # The frame loader fails loud when a parquet carries no
                        # usable prediction columns; treat that as a graceful
                        # per-sequence skip rather than a caught render error.
                        # This relies on the loader signalling that case as
                        # ValueError (frames_from_dataframe); test_loaders guards it.
                        logger.warning(
                            f"No usable predictions in {pred_path.name} — skipping sequence {seq_num}."
                        )
                        continue
                # Skip gracefully if this specific target is absent.
                if target_identifier not in forecast_frames:
                    logger.warning(
                        f"Target '{target_identifier}' not in {pred_path.name} — "
                        f"skipping sequence {seq_num}."
                    )
                    continue
                graph = HistoricalLineGraph(
                    historical_frame=historical_frame,
                    forecast_frame=forecast_frames[target_identifier],
                    level=spatial_level,
                )
                report_manager.add_heading(f"Sequence {seq_num}", level=3)
                report_manager.add_html(
                    html=graph.plot_predictions_vs_historical(
                        targets=[target_identifier],
                        as_html=True,
                        alpha=get_config().default_hdi_level,
                        hdi_levels=get_config().hdi_levels,
                        run_type=self.run_type,
                    ),
                    height=700,
                )
            except Exception as e:
                logger.warning(
                    f"Could not render graph for sequence {seq_num} "
                    f"({pred_path.name}): {e}",
                    exc_info=True,
                )

    def _discover_parquet_origins(self):
        """Discover sequenced parquet prediction files, return latest run."""
        import re

        all_pred_paths = self.model_path._get_generated_predictions_data_file_paths(
            self.run_type
        )
        if not all_pred_paths:
            return []

        seq_pattern = re.compile(r"^predictions_[^_]+_(\d{8}_\d{6})_(\d+)$")
        seq_files: list[tuple[str, int, "Path"]] = []
        for path in all_pred_paths:
            m = seq_pattern.match(path.stem)
            if m:
                seq_files.append((m.group(1), int(m.group(2)), path))

        if not seq_files:
            return []

        latest_ts = max(ts for ts, _, _ in seq_files)
        return sorted(
            [(seq, p) for ts, seq, p in seq_files if ts == latest_ts],
            key=lambda x: x[0],
        )

    def _discover_pf_origins(self):
        """Discover PredictionFrame origin directories, return latest run."""
        try:
            pf_paths = self.model_path._get_generated_pf_prediction_paths(
                self.run_type
            )
        except AttributeError:
            logger.warning(
                "ModelPathManager does not support _get_generated_pf_prediction_paths — "
                "skipping PredictionFrame discovery."
            )
            return []

        if not pf_paths:
            return []

        origin_dirs = sorted(
            [d for d in pf_paths[0].iterdir() if d.is_dir() and d.name.startswith("origin_")],
            key=lambda d: int(d.name.split("_")[1]),
        )
        return [(int(d.name.split("_")[1]), d) for d in origin_dirs]
