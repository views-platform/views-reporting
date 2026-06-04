"""ForecastReportTemplate: generates HTML forecast reports from DataFrames without external service dependencies."""

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import tqdm
from views_pipeline_core.data.handlers import (
    CMDataset,
    PGMDataset,
    _CDataset,
)
from views_pipeline_core.files.utils import generate_model_file_name
from views_pipeline_core.managers.model import ModelPathManager

from views_reporting.loaders import load_predictions
from views_reporting.mapping import MappingModule
from views_reporting.reports import ReportModule
from views_reporting.statistics import calculate_map
from views_reporting.visualizations import HistoricalLineGraph

logger = logging.getLogger(__name__)


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
        dataset_classes = {"cm": CMDataset, "pgm": PGMDataset}

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
                forecast_dataset = load_predictions(
                    prediction_format,
                    prediction_path,
                    self.config["level"],
                    self.config["targets"],
                )
            elif forecast_dataframe is not None:
                forecast_dataset = dataset_cls(forecast_dataframe)
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

            for target in tqdm.tqdm(
                self.config["targets"], desc="Generating forecast maps"
            ):
                original_target = target
                # Handle uncertainty
                if forecast_dataset.sample_size > 1:
                    logger.info(
                        f"Sample size of {forecast_dataset.sample_size} for target {target} found. Calculating MAP..."
                    )
                    forecast_dataset_map = type(forecast_dataset)(
                        calculate_map(forecast_dataset, features=[f"pred_{target}"])
                    )
                    target = f"{target}_map"

                # Common steps
                mapping_manager = MappingModule(
                    forecast_dataset_map
                    if forecast_dataset.sample_size > 1
                    else forecast_dataset
                )
                subset_dataframe = mapping_manager.get_subset_mapping_dataframe(
                    entity_ids=None, time_ids=None
                )
                report_manager.add_heading(f"Forecast for {target}", level=3)
                report_manager.add_html(
                    html=mapping_manager.plot_map(
                        mapping_dataframe=subset_dataframe,
                        target=f"pred_{target}",
                        interactive=True,
                        as_html=True,
                    ),
                    height=900,
                )
                if isinstance(forecast_dataset, _CDataset):
                    logger.info(
                        "Generating historical vs forecast graphs for CM dataset"
                    )
                    report_manager.add_heading("Historical vs Forecasted", level=2)
                    historical_dataset = dataset_cls(
                        historical_dataframe, targets=self.config["targets"]
                    )
                    historical_line_graph = HistoricalLineGraph(
                        historical_dataset=historical_dataset,
                        forecast_dataset=forecast_dataset,
                    )
                    report_manager.add_html(
                        html=historical_line_graph.plot_predictions_vs_historical(
                            targets=[original_target],
                            as_html=True,
                            alpha=0.9,
                            run_type=self.run_type,
                        ),
                        height=700,
                    )
            # Generate report path
            report_path = (
                self.model_path.reports
                / f"report_{generate_model_file_name(run_type=self.run_type, file_extension='')}.html"
            )

            # Export report
            report_manager.export_as_html(report_path)
            return report_path

        try:
            # Get appropriate dataset class
            dataset_cls = dataset_classes[self.config["level"]]
        except KeyError:
            raise ValueError(f"Invalid level: {self.config['level']}")

        # Create and export report
        return _create_report()
