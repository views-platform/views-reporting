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

from views_reporting._time import month_id_to_label
from views_reporting.config import get_config
from views_reporting.loaders import (
    frames_from_dataframe,
    load_predictions,
    target_frame_from_dataframe,
)
from views_reporting.mapping import MappingModule
from views_reporting.metadata.entity_metadata import metadata_snapshot_date
from views_reporting.reports import ReportModule
from views_reporting.statistics import (
    calculate_exceedance_frame,
    calculate_hdi_frame,
    calculate_map_frame,
)
from views_reporting.visualizations import HistoricalLineGraph

logger = logging.getLogger(__name__)

_LEVELS = {"cm": SpatialLevel.CM, "pgm": SpatialLevel.PGM}

# The PGM horizon steps rendered per target (#232, decided on epic #230):
# months-ahead sampled across the forecast horizon, clamped to its length.
HORIZON_STEPS = (1, 6, 12, 24, 36)


def _map_frame_from_df(map_df: pd.DataFrame, level: SpatialLevel) -> PredictionFrame:
    """Wrap ANY collapsed one-column summary DataFrame (MAP, P(any), an HDI
    bound…) as an S==1 frame — the ADR-020 seam shape every layer shares."""
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

                # Collapse samples into SUMMARY LAYERS (#233, ADR-020: the
                # tower collapses in numpy; every summary is an S==1 frame
                # through the same seam). MAP stays the headline; for PGM the
                # distribution also yields P(any violence) — the layer that
                # actually lights up the at-risk surface a zero-inflated
                # posterior's mode hides — and the upper 90%/95% HDI bounds.
                # CM renders MAP only (its line graph already carries HDI).
                stem = f"pred_{target}"
                if forecast_frame.is_sample:
                    logger.info(
                        "Collapsing S=%d samples for target %s into summary "
                        "layers (#233)...",
                        forecast_frame.sample_count,
                        target,
                    )
                    map_df = calculate_map_frame(forecast_frame, stem)
                    layers = [
                        {
                            "column": f"{stem}_map",
                            "frame": _map_frame_from_df(map_df, level),
                            "color_mode": "log_count",
                            "label": "MAP point estimate",
                        }
                    ]
                    if level == SpatialLevel.PGM:
                        p_df = calculate_exceedance_frame(forecast_frame, stem)
                        layers.append(
                            {
                                "column": f"{stem}_p_any",
                                "frame": _map_frame_from_df(p_df, level),
                                "color_mode": "unit_interval",
                                "label": "P(any violence)",
                            }
                        )
                        for alpha, tag in ((0.9, "hdi90"), (0.95, "hdi95")):
                            hdi_df = calculate_hdi_frame(
                                forecast_frame, stem, alpha=alpha
                            )
                            col = f"{stem}_{tag}_upper"
                            upper = hdi_df[[f"{stem}_hdi_upper"]].rename(
                                columns={f"{stem}_hdi_upper": col}
                            )
                            layers.append(
                                {
                                    "column": col,
                                    "frame": _map_frame_from_df(upper, level),
                                    "color_mode": "log_count",
                                    "label": f"Upper {int(alpha * 100)}% HDI",
                                }
                            )
                else:
                    layers = [
                        {
                            "column": stem,
                            "frame": forecast_frame,
                            "color_mode": "log_count",
                            "label": "Point forecast",
                        }
                    ]

                cfg = get_config()
                if level == SpatialLevel.PGM:
                    # Horizon-step strategy (#232, epic #230): month choice is
                    # EXPLICIT at the Compose boundary — never a renderer-side
                    # pick. Steps +1/+6/+12/+24/+36 (clamped to the horizon)
                    # render as scale-flat PNGs: at global scale a full-horizon
                    # interactive animation is physically over any offline byte
                    # budget (~7.2M lattice cell-frames ≈ 245 MB), while one
                    # PNG is ~300 KB. Step +1 ADDITIONALLY renders as the
                    # hover-capable raster heatmap — a single global month
                    # (~202k lattice cell-frames) fits the C-209 budget by
                    # construction. Uniform for ALL PGM runs, any size: one
                    # consistent product (CM keeps the choropleth).
                    months = sorted({int(t) for t in forecast_frame.index.time})
                    steps = [s for s in HORIZON_STEPS if s <= len(months)]
                    logger.info(
                        "PGM horizon-step render (#232/#233): %d layer(s) x "
                        "steps %s over a %d-month horizon.",
                        len(layers),
                        [f"+{s}" for s in steps],
                        len(months),
                    )
                    for layer in layers:
                        mapping_manager = MappingModule(
                            frame=layer["frame"],
                            level=level,
                            target_column=layer["column"],
                        )
                        for s in steps:
                            month = months[s - 1]
                            step_df = mapping_manager.get_subset_mapping_dataframe(
                                entity_ids=None, time_ids=[month]
                            )
                            report_manager.add_heading(
                                f"{target} — {layer['label']} — "
                                f"{month_id_to_label(month)} (step +{s})",
                                level=3,
                            )
                            if s == 1 and layer is layers[0]:
                                # Per-cell hover where it matters most: the
                                # headline layer at the operationally-relevant
                                # first step.
                                report_manager.add_html(
                                    html=mapping_manager.plot_map(
                                        mapping_dataframe=step_df,
                                        target=layer["column"],
                                        interactive=True,
                                        as_html=True,
                                        max_cells=cfg.max_map_cells,
                                        raster=True,
                                        max_raster_cell_frames=cfg.max_raster_cell_frames,
                                        color_mode=layer["color_mode"],
                                    ),
                                    height=900,
                                )
                            report_manager.add_html(
                                html=mapping_manager.plot_map(
                                    mapping_dataframe=step_df,
                                    target=layer["column"],
                                    interactive=True,
                                    as_html=True,
                                    max_cells=cfg.max_map_cells,
                                    image_fallback=True,
                                    color_mode=layer["color_mode"],
                                ),
                                # <img> embeds size to content (#234) — no
                                # dead 900px scroll box around a ~550px PNG.
                                height=None,
                            )
                else:
                    # CM: whole-horizon choropleth of the headline layer only
                    # (the CM line graph already carries HDI uncertainty).
                    mapping_manager = MappingModule(
                        frame=layers[0]["frame"],
                        level=level,
                        target_column=layers[0]["column"],
                    )
                    subset_dataframe = mapping_manager.get_subset_mapping_dataframe(
                        entity_ids=None, time_ids=None
                    )
                    report_manager.add_heading(
                        f"{target} — {layers[0]['label']}", level=3
                    )
                    report_manager.add_html(
                        html=mapping_manager.plot_map(
                            mapping_dataframe=subset_dataframe,
                            target=layers[0]["column"],
                            interactive=True,
                            as_html=True,
                            # Choropleth scale guard (ADR-016 / C-26): fail
                            # loud rather than OOM on a huge vector render.
                            max_cells=cfg.max_map_cells,
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
                    # Bundled entity-metadata snapshot date (C-22/C-112):
                    # staleness observable in every delivered artifact.
                    "metadata_snapshot": metadata_snapshot_date(),
                }
            )

            # Export report
            report_manager.export_as_html(report_path)
            return report_path

        # Create and export report
        return _create_report()
