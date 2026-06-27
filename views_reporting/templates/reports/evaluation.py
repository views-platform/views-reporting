"""EvaluationReportTemplate: renders HTML evaluation reports from an injected
EvaluationSource (a typed MetricFrame per model), not from a render-time WandB scrape
(ADR-018 / C-108). The eval path touches no WandB — pipeline-core's reporting stage
injects a MetricFrameFileSource over the persisted evaluation-of-record."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from views_pipeline_core.configs.pipeline import PipelineConfig
from views_pipeline_core.files.utils import (
    generate_model_file_name,
)
from views_pipeline_core.managers.model import ForecastingModelManager, ModelPathManager

from views_reporting.config import get_config
from views_reporting.reports import (
    ReportModule,
    search_for_item_name,
)
from views_reporting.sources import (
    AmbiguousMetric,
    EvaluationSource,
    mean_metric_value,
    unique_axis_value,
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

    def generate(self, source: EvaluationSource, target: str) -> Path:
        """Render an evaluation report from an injected ``EvaluationSource`` (ADR-018).

        The report depends on the source's *interface*, never on where the metrics
        come from — it renders purely from the given data. pipeline-core's reporting
        stage constructs a ``MetricFrameFileSource`` over the persisted per-target
        MetricFrame and passes it here (C-108).

        Args:
            source: The injected evaluation source (a MetricFrame per model).
            target: The target variable to report on.

        Returns:
            Path: The exported HTML report.

        Raises:
            ValueError: if ``target`` is missing, or if the model target type is not
                'model' or 'ensemble'.
        """
        if target is None:
            raise ValueError("target is required.")
        if source is None:
            raise ValueError("generate() requires an EvaluationSource.")
        if self.model_path.target not in ("model", "ensemble"):
            raise ValueError(
                f"Invalid target type: {self.model_path.target}. Expected 'model' or 'ensemble'."
            )

        prov = source.provenance()

        report_manager = ReportModule()
        report_manager.add_heading(
            f"Evaluation report for {self.model_path.target} {self.model_path.model_name}",
            level=1,
        )
        report_manager.add_heading("Run Summary", level=2)
        run_id_line = (
            f"[{prov.run_id}]({prov.run_url})" if prov.run_url else prov.run_id
        )
        markdown_text = f"**Run ID**: {run_id_line}  \n"
        if prov.owner:
            markdown_text += f"**Owner**: {prov.owner}  \n"
        markdown_text += f"**Run Date**: {prov.run_date or 'N/A'}  \n"
        if self.model_path.target == "ensemble":
            markdown_text += (
                f"**Constituent Models**: {self.config.get('models', None)}  \n"
            )
        if prov.data_version:
            markdown_text += f"**Data Version**: {prov.data_version}  \n"
        if prov.scoring_code_version:
            markdown_text += f"**Scoring Code Version**: {prov.scoring_code_version}  \n"
        markdown_text += f"**Pipeline Version**: {PipelineConfig.current_version}"
        report_manager.add_markdown(markdown_text=markdown_text)

        # Task Description — experimental-design parameters, sourced from the model
        # config (not the metrics). Run-resolved partitions absent from config degrade
        # to N/A on the inverted path (#219 can pass them through later if needed).
        steps = self.config.get("steps", [None, None]) or [None, None]
        partition = self.config.get(
            self.run_type, {"train": [None, None], "test": [None, None]}
        )
        task_definition_md = (
            f"- **Target Variable**: {target}\n"
            f"- **Spatiotemporal Resolution**: {self.config.get('level', 'N/A')}\n"
            f"- **Evaluation Scheme**: `Rolling-Origin Holdout`\n"
            f"    - **Minimum forecast lead time**: {steps[0]}\n"
            f"    - **Maximum forecast lead time**: {steps[-1]}\n"
            f"    - **Number of Rolling Origins**: {ForecastingModelManager._resolve_evaluation_sequence_number(str(self.config.get('eval_type', 'standard')).lower())}\n"
            f"    - **Context Window Origin**: {partition.get('train', [None])[0]}\n"
            f"    - **Context Window Schedule**: Fixed-origin, Expanding\n"
            f"    - **Target Window Schedule**: Rolling-origin, Fixed-length\n"
            f"    - **Target Window First Origin**: {partition.get('test', [None])[0]}\n"
            f"    - **Training Schedule**: Frozen trained model artifact\n"
        )
        report_manager.add_heading("Task Description", level=2)
        report_manager.add_markdown(markdown_text=task_definition_md)

        self._add_report_content(report_manager, source, target)

        # Provenance footer (C-34): stamp model/run/source identity so a delivered eval
        # report is self-identifying. None values are omitted by add_footer.
        provenance = {
            "model": self.model_path.model_name,
            "target": self.model_path.target,
            "run_type": self.run_type,
            "eval_target": target,
            "level": self.config.get("level", None),
            "run_id": prov.run_id,
            "run_url": prov.run_url,
            "owner": prov.owner,
            "data_version": prov.data_version,
            "scoring_code_version": prov.scoring_code_version,
        }
        if self.model_path.target == "ensemble":
            constituents = self.config.get("models", None)
            if constituents:
                provenance["constituent_models"] = ", ".join(constituents)
        report_manager.add_footer(provenance=provenance)

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
        source: EvaluationSource,
        target_identifier: str,
    ) -> None:
        """Render the Model Metrics section from the injected ``EvaluationSource``.

        For the subject model and each declared constituent it asks the source for a
        ``MetricFrame`` and renders the central canonical metrics per active cell
        (ADR-017). Constituents that resolve to ``None`` (absent) or raise even after a
        retry (degraded) are made VISIBLE rather than dropped (#105/#177); the subject
        is always rendered (an absent subject shows "not calculated" cells). Then it
        verifies cross-constituent ``level``/``partition`` consistency and appends the
        non-fatal prediction-sample graphs.

        Args:
            report_manager: The report manager to add content to.
            source: The injected evaluation source (a MetricFrame per model).
            target_identifier: The target variable.

        Raises:
            ValueError: on cross-constituent metadata mismatch, or when
                ``strict_constituents`` and any constituent is absent/degraded.
        """
        subject = self.model_path.model_name
        constituents = self.config.get(
            "models", []
        )  # only populated for ensemble runs

        # Baseline model names from all tier-specific config keys.
        baseline_models = list(dict.fromkeys(
            self.config.get("regression_point_baselines", []) +
            self.config.get("regression_sample_baselines", []) +
            self.config.get("classification_point_baselines", []) +
            self.config.get("classification_sample_baselines", [])
        ))
        if not baseline_models:
            logger.warning("No baseline models found in config. Baseline rows will be absent from the report.")
        constituents = sorted(set(constituents).union(baseline_models) - {subject})
        logger.info(f"Constituent models to render: {constituents}")

        # Active {task}×{pred_type} metric cells (ADR-017) and the canonical metrics
        # rendered per cell.
        cell_keys = {
            ("regression", "point"): "regression_point_metrics",
            ("regression", "sample"): "regression_sample_metrics",
            ("classification", "point"): "classification_point_metrics",
            ("classification", "sample"): "classification_sample_metrics",
        }
        active_cells = [c for c, k in cell_keys.items() if self.config.get(k)]
        canonical_cfg = get_config()

        def _resolve(model: str) -> Tuple[Optional["object"], str]:
            """(frame|None, 'resolved'|'absent'|'degraded'). ``None`` from the source
            is absent; a raise is transient → retry once → degraded (#105/#177)."""
            try:
                frame = source.metric_frame(model)
            except Exception as e:
                logger.warning(
                    f"Transient error resolving '{model}': {e}. Retrying once...",
                    exc_info=False,
                )
                try:
                    frame = source.metric_frame(model)
                except Exception as e2:
                    logger.error(
                        f"Resolution for '{model}' failed after retry: {e2}. "
                        "Marking degraded."
                    )
                    return None, "degraded"
            return (frame, "resolved") if frame is not None else (None, "absent")

        # The subject is always rendered; absent/degraded tracking is for declared
        # constituents (the #105 degrade-and-announce surface).
        subject_frame, _ = _resolve(subject)
        resolved: List[Tuple[str, "object"]] = []
        absent_models: list = []
        degraded_models: list = []
        for model in constituents:
            frame, status = _resolve(model)
            if status == "resolved":
                resolved.append((model, frame))
            elif status == "absent":
                logger.warning(
                    f"No evaluation found for declared constituent '{model}'; "
                    "marking as missing (absent)."
                )
                absent_models.append(model)
            else:
                degraded_models.append(model)

        strict_constituents = bool(self.config.get("strict_constituents", False))
        if strict_constituents and (absent_models or degraded_models):
            raise ValueError(
                "strict_constituents: declared constituents did not resolve — "
                f"absent={sorted(absent_models)}, degraded={sorted(degraded_models)}"
            )

        try:
            # Cross-constituent consistency: a single ensemble table must not mix
            # evaluations from different levels/partitions (C-48). The MetricFrame
            # carries both as axes; require one distinct value across the subject and
            # the resolved constituent frames. The subject is included because the old
            # check seeded its level baseline from the subject run (None-safe: an
            # absent subject_frame has n_rows 0 and is skipped).
            self._verify_frame_consistency(subject_frame, [f for _, f in resolved])

            # Canonical Model Metrics (ADR-017): render the CENTRAL canonical metric
            # standard per active cell — not each model's own list.
            report_manager.add_heading("Model Metrics", level=2)
            report_manager.add_markdown(
                markdown_text=f"More information about the following models can be found [here]({self.views_models_url})\n"
            )

            # Degrade-and-announce (#105/#177): declared constituents that did not
            # resolve are made VISIBLE here, absent vs degraded distinctly.
            if absent_models:
                report_manager.add_markdown(
                    "> ⚠️ **Declared constituent(s) with no evaluation found "
                    "(absent):** "
                    + ", ".join(f"`{m}`" for m in sorted(absent_models))
                    + ". These models are part of the declared ensemble but have no "
                    "resolvable evaluation, so they contribute no metrics row below."
                )
            if degraded_models:
                report_manager.add_markdown(
                    "> ⚠️ **Constituent(s) whose evaluation could not be retrieved "
                    "(degraded — transient failure):** "
                    + ", ".join(f"`{m}`" for m in sorted(degraded_models))
                    + ". Their metrics are temporarily unavailable; this is a "
                    "retrieval error, not a confirmed absence."
                )

            if not active_cells:
                report_manager.add_markdown(
                    "_No metric standard active: the model config declares no "
                    "`*_point_metrics` / `*_sample_metrics`._"
                )

            def _canonical_row(frame, model_name, task, pred_type, eval_type):
                cfg_key = f"{task}_{pred_type}_metrics"
                canonical = canonical_cfg.canonical_metrics(task, pred_type)
                row = {}
                for metric in canonical:
                    note = f"not calculated — add '{metric}' to {cfg_key}"
                    if frame is None:
                        row[metric] = note
                        continue
                    try:
                        value = mean_metric_value(
                            frame,
                            eval_type=eval_type,
                            target=target_identifier,
                            metric=metric,
                        )
                    except AmbiguousMetric:
                        # >1 mean row matches — a wrong number would otherwise be
                        # surfaced silently (register C-116). Render a visible
                        # "ambiguous" note instead of guessing (ADR-008 / C-40).
                        logger.warning(
                            f"Ambiguous metric match for '{metric}' "
                            f"(target={target_identifier}, eval_type={eval_type}); "
                            "rendering 'ambiguous'."
                        )
                        row[metric] = "ambiguous — multiple matching keys"
                        continue
                    row[metric] = value if value is not None else note
                return pd.DataFrame([row], columns=list(canonical), index=[model_name])

            def _maybe_sort(dataframe):
                # Sort by MSLE, then CRPS, then the first fully-numeric column.
                # Skip if the chosen column has any "not calculated" note (non-numeric).
                preferred = [
                    search_for_item_name(
                        dataframe.columns.tolist(), [c], on_ambiguous="first"
                    )
                    for c in ("MSLE", "CRPS")
                ]
                for col in [c for c in preferred if c] + list(dataframe.columns):
                    if pd.to_numeric(dataframe[col], errors="coerce").notna().all():
                        return dataframe.sort_values(by=col, ascending=True)
                return dataframe

            for eval_type in self.eval_types:
                for task, pred_type in active_cells:
                    rows = [
                        _canonical_row(
                            subject_frame, subject, task, pred_type, eval_type
                        )
                    ]
                    for model, frame in resolved:
                        rows.append(
                            _canonical_row(frame, model, task, pred_type, eval_type)
                        )
                    metric_dataframe = pd.concat(rows, axis=0)
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

    @staticmethod
    def _verify_frame_consistency(subject_frame, constituent_frames) -> None:
        """A single ensemble table must not mix evaluations from different levels or
        partitions (C-48). Each MetricFrame carries ``level``/``partition`` as axes.
        Mirrors the pre-inversion guard's scope: **level** is required uniform across
        the subject *and* the constituents (the old check seeded its level baseline
        from the subject run); **partition** is required uniform across the
        constituents (the old check seeded partition from the first constituent, not
        the subject — an ensemble subject's partition representation may differ).

        Raises ``ValueError`` on a mismatch (loud, never a silently-mixed table)."""

        def _distinct(frames, axis):
            return {
                unique_axis_value(f, axis)
                for f in frames
                if getattr(f, "n_rows", 0)
            }

        levels = _distinct([subject_frame, *constituent_frames], "level")
        if len(levels) > 1:
            raise ValueError(
                f"level metadata mismatch between models: "
                f"{sorted(str(v) for v in levels)}"
            )
        partitions = _distinct(constituent_frames, "partition")
        if len(partitions) > 1:
            raise ValueError(
                f"partition metadata mismatch between constituent models: "
                f"{sorted(str(v) for v in partitions)}"
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
