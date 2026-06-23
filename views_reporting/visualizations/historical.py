"""Plotly time series with HDI bands and forecast cutoff markers.

Frame-native (epic #137, #138): consumes ``views_frames.TargetFrame`` (observed
history) and ``views_frames.PredictionFrame`` (forecast samples) rather than
pipeline-core datasets. CM/PGM only (year-level CY/PGY dropped — dead on the
report path).
"""

import logging
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from views_frames import PredictionFrame, SpatialLevel, TargetFrame

from views_reporting.metadata import get_name_for_index
from views_reporting.statistics import calculate_hdi_frame, calculate_map_frame

logger = logging.getLogger(__name__)


class HistoricalLineGraph:
    def __init__(
        self,
        historical_frame: Optional[TargetFrame] = None,
        forecast_frame: Optional[PredictionFrame] = None,
        level: SpatialLevel = SpatialLevel.CM,
    ):
        """
        Initialize the visualization with historical and/or forecast frames.

        Args:
            historical_frame: Observed history (``TargetFrame``) or None.
            forecast_frame: Forecast samples (``PredictionFrame``) or None.
            level: ``SpatialLevel.CM`` or ``SpatialLevel.PGM``.
        """
        if historical_frame is None and forecast_frame is None:
            raise ValueError("At least one frame must be provided")

        self.historical_frame = historical_frame
        self.forecast_frame = forecast_frame
        self._level = level
        self._time_id, self._entity_id = level.index_names

    @property
    def _resolved_time_id(self):
        return self._time_id

    # ── frame helpers ────────────────────────────────────────────────────

    def _entity_values(self, frame) -> np.ndarray:
        return np.unique(np.asarray(frame.index.unit))

    def _all_entity_values(self) -> List[int]:
        ids: List[int] = []
        if self.historical_frame is not None:
            ids.extend(self._entity_values(self.historical_frame).tolist())
        if self.forecast_frame is not None:
            ids.extend(self._entity_values(self.forecast_frame).tolist())
        return list(set(ids))

    def _entity_mask(self, frame, entity_id: int) -> np.ndarray:
        return np.asarray(frame.index.unit) == entity_id

    def plot_predictions_vs_historical(
        self,
        entity_ids: Union[int, List[int]] = None,
        interactive: bool = True,
        alpha: float = 0.9,
        targets: Optional[List[str]] = None,
        as_html: bool = False,
        run_type: Optional[str] = None,
        hdi_levels: Optional[List[float]] = None,
    ):
        # `alpha` is the default (initially-visible) HDI level; `hdi_levels` (if
        # given) is the full set of credible levels rendered as legend-selectable
        # bands. Both are injected from config at the Compose layer (ADR-016).
        if targets is None:
            raise RuntimeError(
                "targets must be provided (frames are single-target)"
            )

        # Log warnings for missing frames
        if self.historical_frame is None:
            logger.warning("Historical frame is missing - showing only forecast data")
        if self.forecast_frame is None:
            logger.warning("Forecast frame is missing - showing only historical data")

        # Determine the cutoff line + annotation if both frames are available.
        # Data-driven, no run_type needed: if every predicted month falls within
        # observed history, this is a HINDCAST (e.g. a calibration rolling-origin
        # evaluation) — mark the forecast LAUNCH (first predicted month) and add a
        # caption, so predictions sitting over observed data don't read as "a
        # forecast in the past". Otherwise it is a true forecast and the line marks
        # the observed/forecast boundary (last observed month).
        vline = None
        cutoff_label = "Forecast Start"
        caption = None
        if self.historical_frame is not None and self.forecast_frame is not None:
            obs_max = int(np.max(self.historical_frame.index.time))
            pred_min = int(np.min(self.forecast_frame.index.time))
            pred_max = int(np.max(self.forecast_frame.index.time))
            # Authoritative partition name (run_type: calibration/validation/
            # forecasting), passed down from the report template, shown verbatim.
            partition = f"{run_type.capitalize()} partition — " if run_type else ""
            tid = self._resolved_time_id
            if pred_max <= obs_max:
                vline = pred_min
                cutoff_label = "Forecast launched (hindcast)"
                caption = (
                    f"{partition}hindcast: forecast launched at {tid} "
                    f"{int(pred_min)}, shown against the observed values it is "
                    f"scored against — not a future forecast."
                )
            else:
                vline = obs_max
                if run_type:
                    caption = (
                        f"{partition}out-of-sample forecast beyond the last "
                        f"observed {tid} ({int(obs_max)})."
                    )

        html_plots = []

        # Normalize and validate entity IDs
        if entity_ids is None:
            entity_ids = self._all_entity_values()
        else:
            entity_ids = self._validate_entity_ids(entity_ids)

        # Handle empty entity list
        if not entity_ids:
            logger.error("No valid entities found to plot")
            return None

        for target in targets:
            # Determine if we should calculate HDI/MAP (only for sample forecasts)
            hdi = False
            map_df = None
            if self.forecast_frame is not None and self.forecast_frame.is_sample:
                hdi = True
                forecast_target = f"pred_{target}"
                try:
                    map_df = calculate_map_frame(self.forecast_frame, forecast_target)
                except Exception as e:
                    logger.error(
                        f"Failed to calculate MAP for {forecast_target}: {str(e)}"
                    )
                    map_df = None

            if not interactive:
                raise NotImplementedError("Static plots are not supported")

            plot_result = self._plot_interactive(
                entity_ids=entity_ids,
                target=target,
                alpha=alpha,
                vline=vline,
                hdi=hdi,
                as_html=as_html,
                map_df=map_df,
                cutoff_label=cutoff_label,
                caption=caption,
                hdi_levels=hdi_levels,
            )
            if as_html:
                html_plots.append(plot_result)
            else:
                plot_result.show()

        return "\n".join(html_plots) if as_html else None

    def _hist_df(self, entity_id: int, target: str) -> Optional[pd.DataFrame]:
        if self.historical_frame is None:
            return None
        mask = self._entity_mask(self.historical_frame, entity_id)
        if not mask.any():
            logger.warning(
                f"Entity {entity_id} not found in historical frame"
            )
            return None
        sub = self.historical_frame.select(mask)
        return pd.DataFrame(
            {
                self._time_id: np.asarray(sub.index.time),
                target: np.asarray(sub.values[:, 0], dtype=float),
            }
        )

    def _pred_df(self, entity_id: int, target: str) -> Optional[pd.DataFrame]:
        if self.forecast_frame is None:
            return None
        forecast_target = f"pred_{target}"
        mask = self._entity_mask(self.forecast_frame, entity_id)
        if not mask.any():
            logger.warning(
                f"Entity {entity_id} not found in forecast frame"
            )
            return None
        sub = self.forecast_frame.select(mask)
        # Point forecast line uses the first sample column (S == 1 for point
        # estimates; for sample forecasts this path is only the HDI fallback).
        return pd.DataFrame(
            {
                self._time_id: np.asarray(sub.index.time),
                forecast_target: np.asarray(sub.values[:, 0], dtype=float),
            }
        )

    def _plot_interactive(
        self,
        entity_ids: List[int],
        target: str,
        alpha: float,
        vline: Optional[int],
        hdi: bool,
        as_html: bool = False,
        map_df: Optional[pd.DataFrame] = None,
        cutoff_label: str = "Forecast Start",
        caption: Optional[str] = None,
        hdi_levels: Optional[List[float]] = None,
    ):
        fig = go.Figure()
        traces = []
        # trace_tags[i] = (entity_id, level) for trace i, where `level` is the HDI
        # credible level for a band trace or None for a level-independent trace
        # (historical / MAP / forecast). The entity dropdown and the per-level
        # legend toggling are both built by MATCHING these tags — never by index
        # arithmetic — so the figure stays correct even when entities contribute
        # different numbers of traces (CIC Deviation #5) or different levels.
        trace_tags: List[Tuple[int, Optional[float]]] = []
        entity_name_map = self._get_entity_name_map()

        # Levels to render as selectable bands; `alpha` is the default (initially
        # visible) level. Falls back to the single default when none are given.
        levels = list(hdi_levels) if hdi_levels else [alpha]
        default_level = alpha

        for idx, entity_id in enumerate(entity_ids):
            color = self._generate_entity_color(idx)
            entity_label = self._get_entity_label(entity_id, entity_name_map)

            hist_df = self._hist_df(entity_id, target)
            pred_df = self._pred_df(entity_id, target)

            # Add historical trace if available (level-independent)
            if hist_df is not None:
                traces.append(
                    self._create_historical_trace(hist_df, target, entity_label, idx)
                )
                trace_tags.append((entity_id, None))

            # Add forecast traces if available
            if pred_df is not None:
                if hdi:
                    added_levels = []
                    for level in levels:
                        try:
                            hdi_df = self._get_hdi_data(entity_id, target, level)
                        except Exception as e:
                            logger.error(
                                f"Failed to get HDI data for entity {entity_id} "
                                f"at level {level}: {str(e)}"
                            )
                            continue
                        band = self._create_hdi_traces(
                            hdi_df, target, color, idx, entity_id,
                            level, default_level,
                        )
                        traces.extend(band)
                        trace_tags.extend([(entity_id, level)] * len(band))
                        added_levels.append(level)

                    if added_levels:
                        # MAP trace (level-independent), added once per entity.
                        if map_df is not None:
                            try:
                                map_series = map_df.xs(
                                    entity_id, level=self._entity_id
                                )[f"pred_{target}_map"]
                                traces.append(
                                    go.Scatter(
                                        x=map_series.index,
                                        y=map_series.values,
                                        mode="lines",
                                        name=f"{entity_label} (MAP)",
                                        line=dict(color=color, width=2, dash="dash"),
                                        visible=idx == 0,
                                    )
                                )
                                trace_tags.append((entity_id, None))
                            except KeyError:
                                logger.warning(
                                    f"MAP data not found for entity {entity_id}"
                                )
                    else:
                        # Every level failed: show a single forecast line and
                        # signal the degradation (C-11) instead of a blank band.
                        traces.append(
                            self._create_forecast_trace(
                                pred_df, target,
                                f"{entity_label} (HDI unavailable)",
                                color, idx,
                            )
                        )
                        trace_tags.append((entity_id, None))
                else:
                    traces.append(
                        self._create_forecast_trace(
                            pred_df, target, entity_label, color, idx
                        )
                    )
                    trace_tags.append((entity_id, None))

        # Create dropdown buttons only if we have multiple entities
        buttons = []
        if len(entity_ids) > 1:
            buttons = self._create_dropdown_buttons(
                entity_ids, entity_name_map, trace_tags, default_level
            )

        # Configure figure
        fig.add_traces(traces)
        if vline is not None:
            self._add_cutoff_line(fig, vline, cutoff_label)
        if buttons:
            self._configure_dropdown(fig, buttons)
        self._format_interactive_plot(fig, target, caption=caption)
        return fig.to_html(full_html=False) if as_html else fig

    def _validate_entity_ids(self, entity_ids: Union[int, List[int]]) -> List[int]:
        """Normalize entity IDs to list and validate against available frames"""
        if isinstance(entity_ids, int):
            entity_ids = [entity_ids]

        hist_ids = (
            set(self._entity_values(self.historical_frame).tolist())
            if self.historical_frame is not None
            else None
        )
        fc_ids = (
            set(self._entity_values(self.forecast_frame).tolist())
            if self.forecast_frame is not None
            else None
        )

        valid_ids = []
        for eid in entity_ids:
            valid = True
            if hist_ids is not None and eid not in hist_ids:
                logger.warning(f"Entity {eid} not found in historical frame")
                valid = False
            if fc_ids is not None and eid not in fc_ids:
                logger.warning(f"Entity {eid} not found in forecast frame")
                valid = False
            if valid:
                valid_ids.append(eid)

        if not valid_ids:
            raise ValueError("No valid entities found in either frame")
        return valid_ids

    def _get_entity_name_map(self) -> Optional[Dict[int, str]]:
        try:
            frame = (
                self.forecast_frame
                if self.forecast_frame is not None
                else self.historical_frame
            )
            if frame is None:
                return None
            index = pd.MultiIndex.from_arrays(
                [np.asarray(frame.index.time), np.asarray(frame.index.unit)],
                names=[self._time_id, self._entity_id],
            )
            name_df = get_name_for_index(index, self._level, with_id=True)
            # name_df is indexed by the frame's (time, entity) MultiIndex;
            # collapse to one name per entity.
            flat = name_df.reset_index()
            return (
                flat.drop_duplicates(subset=[self._entity_id])
                .set_index(self._entity_id)["name"]
                .to_dict()
            )
        except Exception as e:
            logger.warning(f"Could not retrieve entity names: {e}")
        return None

    def _generate_entity_color(self, entity_index: int) -> str:
        hue = (entity_index * 40) % 360
        return f"hsl({hue}, 50%, 50%)"

    def _get_entity_label(
        self, entity_id: int, name_map: Optional[Dict[int, str]]
    ) -> str:
        if name_map is None:
            return f"Entity {entity_id}"
        return name_map.get(entity_id, f"Entity {entity_id}")

    def _get_hdi_data(self, entity_id: int, target: str, alpha: float) -> pd.DataFrame:
        if self.forecast_frame is None:
            raise RuntimeError("Forecast frame is required for HDI calculation")

        mask = self._entity_mask(self.forecast_frame, entity_id)
        sub = self.forecast_frame.select(mask)
        return calculate_hdi_frame(
            sub, f"pred_{target}", alpha=alpha
        ).reset_index()

    def _create_historical_trace(
        self, hist_df: pd.DataFrame, target: str, label: str, idx: int
    ) -> go.Scatter:
        return go.Scatter(
            x=hist_df[self._resolved_time_id],
            y=hist_df[target],
            mode="lines+markers",
            name=f"{label} (Historical)",
            line=dict(color="grey", width=1.5),
            marker=dict(size=4),
            visible=idx == 0,
        )

    def _create_forecast_trace(
        self, pred_df: pd.DataFrame, target: str, label: str, color: str, idx: int
    ) -> go.Scatter:
        return go.Scatter(
            x=pred_df[self._resolved_time_id],
            y=pred_df[f"pred_{target}"],
            mode="lines+markers",
            name=f"{label} (Forecast)",
            line=dict(color=color, width=1.5),
            marker=dict(size=4),
            visible=idx == 0,
        )

    def _create_hdi_traces(
        self,
        hdi_df: pd.DataFrame,
        target: str,
        color: str,
        idx: int,
        entity_id: int,
        level: float,
        default_level: float,
    ) -> List[go.Scatter]:
        hue = (idx * 40) % 360
        time_col = self._resolved_time_id
        pct = f"{level * 100:.0f}%"  # credible level, e.g. "90%" (visible to reader)
        # One legend entry per (entity, level). The three band traces share a
        # legendgroup so a single legend click toggles the whole band; grouping
        # per-ENTITY (not just per-level) stops a click on the visible entity's
        # band from also flipping a hidden entity's same-level band.
        group = f"hdi-{entity_id}-{level}"
        # Initial visibility: only the first entity shows; within it the default
        # level is on and the others start collapsed to a clickable legend entry
        # ("legendonly"). Dropdown buttons recompute this per selected entity.
        if idx != 0:
            visible = False
        elif level == default_level:
            visible = True
        else:
            visible = "legendonly"
        lower = go.Scatter(
            x=hdi_df[time_col],
            y=hdi_df[f"pred_{target}_hdi_lower"],
            mode="lines",
            name=f"{pct} HDI",
            legendgroup=group,
            showlegend=False,
            line=dict(color=color, width=1),
            visible=visible,
        )
        upper = go.Scatter(
            x=hdi_df[time_col],
            y=hdi_df[f"pred_{target}_hdi_upper"],
            mode="lines",
            name=f"{pct} HDI",
            legendgroup=group,
            showlegend=False,
            line=dict(color=color, width=1),
            visible=visible,
        )
        fill = go.Scatter(
            x=hdi_df[time_col].tolist()
            + hdi_df[time_col].tolist()[::-1],
            y=hdi_df[f"pred_{target}_hdi_upper"].tolist()
            + hdi_df[f"pred_{target}_hdi_lower"].tolist()[::-1],
            fill="toself",
            fillcolor=f"hsla({hue}, 50%, 50%, 0.2)",
            line=dict(color="rgba(255,255,255,0)"),
            name=f"{pct} HDI",
            legendgroup=group,
            showlegend=True,  # the single legend entry for this band
            hoverinfo="skip",
            visible=visible,
        )
        return [lower, upper, fill]

    def _create_dropdown_buttons(
        self,
        entity_ids: List[int],
        name_map: Optional[Dict[int, str]],
        trace_tags: List[Tuple[int, Optional[float]]],
        default_level: float,
    ) -> List[dict]:
        buttons = []
        for entity_id in entity_ids:
            label = self._get_entity_label(entity_id, name_map)
            # Tag-based, three-state visibility (robust to entities having
            # different trace counts, unlike index arithmetic): for the selected
            # entity show its level-independent + default-level traces, collapse
            # its other levels to clickable legend entries ("legendonly"), and
            # hide every other entity's traces.
            visibility = []
            for owner, level in trace_tags:
                if owner != entity_id:
                    visibility.append(False)
                elif level is None or level == default_level:
                    visibility.append(True)
                else:
                    visibility.append("legendonly")
            buttons.append(
                dict(
                    label=label,
                    method="update",
                    # Only toggle trace visibility. Do NOT relayout the title here:
                    # the title carries the persistent hindcast/partition caption,
                    # and a per-button title update would wipe it on country change
                    # (the dropdown widget + legend already show the selected entity).
                    args=[{"visible": visibility}],
                )
            )
        return buttons

    def _configure_dropdown(self, fig: go.Figure, buttons: List[dict]):
        fig.update_layout(
            updatemenus=[
                dict(
                    buttons=buttons,
                    direction="down",
                    showactive=True,
                    x=1.05,
                    xanchor="left",
                    y=1.1,
                    yanchor="top",
                )
            ],
            margin=dict(r=150),
        )

    def _add_cutoff_line(
        self, fig: go.Figure, vline: int, label: str = "Forecast Start"
    ):
        fig.add_vline(
            x=vline,
            line=dict(color="black", dash="dot", width=1),
            annotation_text=label,
            annotation_position="top right",
        )

    def _format_interactive_plot(
        self, fig: go.Figure, target: str, caption: Optional[str] = None
    ):
        time_id = self._resolved_time_id
        fig.update_layout(
            # Caption (e.g. the hindcast explanation) sits in the title slot so it
            # is always visible and never collides with the bottom rangeslider.
            title=dict(
                text=caption or "",
                font=dict(size=12, color="#555"),
                x=0.0,
                xanchor="left",
            ),
            xaxis_title=f"Time Period ({time_id})",
            yaxis_title=f"{target}",
            legend_title="Series",
            hovermode="x unified",
            template="plotly_white",
            height=600,
            margin=dict(t=80, b=80),
            xaxis=dict(
                showgrid=True,
                gridcolor="lightgray",
                tickangle=-45,
                rangeslider=dict(visible=True),
            ),
            yaxis=dict(showgrid=True, gridcolor="lightgray"),
        )
