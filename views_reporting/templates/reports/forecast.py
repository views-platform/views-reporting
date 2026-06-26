"""ForecastReportTemplate: generates HTML forecast reports from DataFrames without external service dependencies."""

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import tqdm
from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex
from views_pipeline_core.files.utils import generate_model_file_name
from views_pipeline_core.managers.model import ModelPathManager

from views_reporting.config import get_config
from views_reporting.loaders import (
    frames_from_dataframe,
    load_predictions,
    target_frame_from_dataframe,
)
from views_reporting.mapping import MappingModule
from views_reporting.reports import ReportModule
from views_reporting.statistics import calculate_map_frame
from views_reporting.visualizations import HistoricalLineGraph

logger = logging.getLogger(__name__)

_LEVELS = {"cm": SpatialLevel.CM, "pgm": SpatialLevel.PGM}


def _map_frame_from_df(map_df: pd.DataFrame, level: SpatialLevel) -> PredictionFrame:
    """Wrap a collapsed MAP DataFrame (one value column) as an S==1 frame."""
    time_name, entity_name = level.index_names
    col = map_df.columns[0]
    index = SpatioTemporalIndex(
        time=map_df.index.get_level_values(time_name).to_numpy(dtype=np.int64),
        unit=map_df.index.get_level_values(entity_name).to_numpy(dtype=np.int64),
        level=level,
    )
    values = map_df[col].to_numpy(dtype=np.float32).reshape(-1, 1)
    return PredictionFrame(values, index)


class ForecastReportTemplate:
    def __init__(self, config: Dict, model_path: ModelPathManager, run_type: str):
        self.config = config
        self.model_path = model_path
        self.run_type = run_type

    def generate(
        self,
        forecast_dataframe: Optional[pd.DataFrame] = None,
        historical_dataframe: Optional[pd.DataFrame] = None,
        prediction_format: Optional[str] = None,
        prediction_path: Optional[Path] = None,
    ) -> Path:
        """Generate a forecast report.

        Accepts predictions either as a pre-loaded DataFrame or as a
        declared-format path for loader dispatch (ADR-012). Provide
        exactly one of forecast_dataframe or prediction_path.
        """
        level_str = self.config["level"]
        try:
            level = _LEVELS[level_str]
        except KeyError:
            raise ValueError(f"Invalid level: {level_str}")

        targets = self.config["targets"]

        def _create_report() -> Path:
            """Helper function to create and export report."""
            if prediction_path is not None and forecast_dataframe is not None:
                raise ValueError(
                    "Provide either forecast_dataframe or prediction_path, not both (ADR-003)"
                )
            if prediction_path is not None:
                if prediction_format is None:
                    raise ValueError(
                        "prediction_format is required when using prediction_path"
                    )
                forecast_frames = load_predictions(
                    prediction_format,
                    prediction_path,
                    level_str,
                    targets,
                )
            elif forecast_dataframe is not None:
                forecast_frames = frames_from_dataframe(
                    forecast_dataframe, level_str, targets
                )
            else:
                raise ValueError(
                    "Provide either forecast_dataframe or prediction_path"
                )

            report_manager = ReportModule()
            # Build report content
            report_manager.add_heading(
                f"Forecast report for {self.model_path.target} {self.model_path.model_name}",
                level=1,
            )
            report_manager.add_heading("Maps", level=2)

            for target in tqdm.tqdm(targets, desc="Generating forecast maps"):
                if target not in forecast_frames:
                    logger.warning(
                        f"No frame for target '{target}' — skipping map."
                    )
                    continue
                forecast_frame = forecast_frames[target]

                # Handle uncertainty: collapse sample forecasts to a MAP frame.
                if forecast_frame.is_sample:
                    logger.info(
                        f"Sample size of {forecast_frame.sample_count} for "
                        f"target {target} found. Calculating MAP..."
                    )
                    map_df = calculate_map_frame(forecast_frame, f"pred_{target}")
                    map_frame = _map_frame_from_df(map_df, level)
                    map_column = f"pred_{target}_map"
                else:
                    map_frame = forecast_frame
                    map_column = f"pred_{target}"

                # Common steps
                mapping_manager = MappingModule(
                    frame=map_frame,
                    level=level,
                    target_column=map_column,
                )
                subset_dataframe = mapping_manager.get_subset_mapping_dataframe(
                    entity_ids=None, time_ids=None
                )
                report_manager.add_heading(f"Forecast for {map_column}", level=3)
                report_manager.add_html(
                    html=mapping_manager.plot_map(
                        mapping_dataframe=subset_dataframe,
                        target=map_column,
                        interactive=True,
                        as_html=True,
                        # Scale guard injected from config (ADR-016 / C-26): the
                        # Render layer fails loud rather than OOM on a huge PGM grid.
                        max_cells=get_config().max_map_cells,
                    ),
                    height=900,
                )
                if level == SpatialLevel.CM:
                    logger.info(
                        "Generating historical vs forecast graphs for CM dataset"
                    )
                    report_manager.add_heading("Historical vs Forecasted", level=2)
                    historical_frame = (
                        target_frame_from_dataframe(
                            historical_dataframe, level_str, target
                        )
                        if historical_dataframe is not None
                        else None
                    )
                    historical_line_graph = HistoricalLineGraph(
                        historical_frame=historical_frame,
                        forecast_frame=forecast_frame,
                        level=level,
                    )
                    report_manager.add_html(
                        html=historical_line_graph.plot_predictions_vs_historical(
                            targets=[target],
                            as_html=True,
                            alpha=get_config().default_hdi_level,
                            hdi_levels=get_config().hdi_levels,
                            run_type=self.run_type,
                        ),
                        height=700,
                    )
            # Generate report path
            report_path = (
                self.model_path.reports
                / f"report_{generate_model_file_name(run_type=self.run_type, file_extension='')}.html"
            )

            # Provenance footer (C-34): stamp model/run/source identity so a
            # delivered forecast report is self-identifying. None values are
            # omitted by add_footer/export_as_html.
            report_manager.add_footer(
                provenance={
                    "model": self.model_path.model_name,
                    "target": self.model_path.target,
                    "run_type": self.run_type,
                    "level": level_str,
                    "targets": ", ".join(targets),
                    "prediction_path": str(prediction_path)
                    if prediction_path is not None
                    else None,
                }
            )

            # Export report
            report_manager.export_as_html(report_path)
            return report_path

        # Create and export report
        return _create_report()
