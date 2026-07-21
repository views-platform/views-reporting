"""Choropleth map generation at country and PRIO-GRID resolution."""

import base64
import gc
import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Union

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from views_frames import PredictionFrame, SpatialLevel

from views_reporting._time import month_id_to_label
from views_reporting.mapping._frame_adapter import frames_to_mapping_df

# PRIO-GRID resolution: cells are 0.5° squares. The render lattice must be
# UNIFORM at this spacing (register C-208): plotly heatmaps place brick edges
# at midpoints between neighbouring coordinates and matplotlib imshow spreads
# rows evenly across the extent, so a coords-present-in-data-only lattice
# stretches/misplaces cells across gaps (isolated territories — Marion Island,
# Cape Verde). Coords are dyadic (….25/….75), so index arithmetic is exact.
_PGM_CELL_DEG = 0.5


def _uniform_lattice(coords: "np.ndarray") -> "np.ndarray":
    """A uniform 0.5°-spaced axis spanning the coords' extent (C-208)."""
    lo = float(np.min(coords))
    n = int(round((float(np.max(coords)) - lo) / _PGM_CELL_DEG)) + 1
    return lo + np.arange(n, dtype=np.float64) * _PGM_CELL_DEG


def _lattice_indices(coords: "np.ndarray", axis: "np.ndarray") -> "np.ndarray":
    """Positions of coords on the uniform axis — index arithmetic, not float
    membership (falsify F1: exact here because the grid is dyadic, but rounding
    is the robust contract)."""
    return np.rint((np.asarray(coords, dtype=np.float64) - axis[0]) / _PGM_CELL_DEG).astype(int)


def _log_color_scale(values: "np.ndarray") -> tuple[float, list, list]:
    """Colour anchoring + original-unit ticks for zero-inflated, heavy-tailed
    forecasts (register C-191). Colour is log1p-scaled from 0. The saturation
    point (cmax) is the 95th percentile of the **nonzero** values' logs —
    anchoring on all values degenerates to 0 when ≥95% of cells are zero (the
    norm for PGM), silently handing the range to the backend's auto-scale.
    Ticks are original-unit labels at log positions, and the TOP of the bar is
    always labelled: the final tick sits at cmax, reading "≥ N" when values
    saturate above it — the darkest colours are never an unlabelled zone.

    Returns ``(cmax_log, tick_positions_log, tick_labels)``; use ``cmin=0``.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    pos = v[v > 0]
    if pos.size == 0:
        cmax = float(np.log1p(1.0))
    else:
        cmax = max(float(np.quantile(np.log1p(pos), 0.95)), float(np.log1p(1.0)))
    sat = float(np.expm1(cmax))
    cand = [1, 2, 5, 10, 25, 50, 100, 250, 500,
            1000, 2500, 5000, 10000, 25000, 50000, 100000]
    ticks = [0] + [c for c in cand if c < sat * 0.9]
    tick_log = [float(np.log1p(t)) for t in ticks]
    tick_text = [str(t) for t in ticks]
    vmax_data = float(v.max()) if v.size else 0.0
    top_label = f"≥ {sat:.0f}" if vmax_data > sat * 1.05 else f"{sat:.0f}"
    tick_log.append(cmax)
    tick_text.append(top_label)
    return cmax, tick_log, tick_text


# Colourbar title stating WHICH part is log-scaled — an unqualified
# "(log scale)" invites reading the original-unit labels as log units (C-191).
_COLORBAR_TITLE = "value<br>(labels: original units;<br>colour: log-scaled)"

# Colour modes (#233): zero-inflated COUNT layers (MAP, HDI bounds) use the
# nonzero-anchored log scale above; PROBABILITY layers (P(any violence), a
# 0-1 quantity) must NOT — they get a plain linear 0-1 scale. Validated at
# the plot_map boundary (ADR-008).
_COLOR_MODES = ("log_count", "unit_interval")

_PROB_COLORBAR_TITLE = "probability<br>(linear 0–1 scale)"

# No-data grey (#234, C-190): NaN cells must be visually distinct from the
# palest OrRd of a zero forecast — omission must never read as "no risk".
_NO_DATA_GREY = "#d9d9d9"


def _unit_interval_scale() -> tuple[float, list, list]:
    """Linear 0–1 colour scale for probability layers: cmax=1, quarter ticks."""
    ticks = [0.0, 0.25, 0.5, 0.75, 1.0]
    return 1.0, ticks, [f"{t:g}" for t in ticks]


def pgm_lattice_cell_frames(mapping_dataframe: pd.DataFrame, time_id: str) -> int:
    """Rows × cols × frames of the UNIFORM render lattice — the true raster
    payload driver (register C-209). Replaces ``len(mapping_dataframe)`` as the
    budget quantity: the dense z spans the bounding box, so sparse-but-spread
    data costs bounding-box, not data-rows."""
    x = mapping_dataframe["xcoord"].to_numpy(dtype=np.float64)
    y = mapping_dataframe["ycoord"].to_numpy(dtype=np.float64)
    n_lon = int(round((x.max() - x.min()) / _PGM_CELL_DEG)) + 1
    n_lat = int(round((y.max() - y.min()) / _PGM_CELL_DEG)) + 1
    return n_lat * n_lon * int(mapping_dataframe[time_id].nunique())

logger = logging.getLogger(__name__)


class MappingModule:
    """
    Geographic visualization module for VIEWS prediction frames.

    Provides interactive and static choropleth mapping for both country-level
    (CM) and priogrid-level (PGM) ``views_frames.PredictionFrame`` data with
    automatic shapefile handling and optimized rendering.
    """
    _COUNTRY_HOVER_COLS = ["country_name"]
    _PRIOGRID_HOVER_COLS = [
        "gid",
        "row",
        "col",
        "country_name",
        "isoab",
        "xcoord",
        "ycoord",
    ]

    def __init__(
        self,
        frame: PredictionFrame,
        level: SpatialLevel,
        target_column: str,
    ):
        """
        Initialize mapping module with a PredictionFrame and load shapefiles.

        Args:
            frame: The (collapsed, S == 1) ``views_frames.PredictionFrame`` to
                visualize. ``frame.values[:, 0]`` is the rendered value.
            level: ``SpatialLevel.CM`` (country) or ``SpatialLevel.PGM`` (grid).
            target_column: The name of the value column to render
                (e.g. ``pred_ged_sb_map``).

        Raises:
            ValueError: If ``level`` is not CM or PGM.
            FileNotFoundError: If required shapefile is missing.
        """
        self._frame = frame
        self._level = level
        self._target_column = target_column
        self._time_id, self._entity_id = level.index_names

        if level == SpatialLevel.PGM:
            self._world = self.__get_priogrid_shapefile()
            self._location_col = "gid"
            self._featureidkey = "properties.gid"
            # Get all available priogrid attributes (excluding geometry)
            self._priogrid_attributes = [
                col for col in self._world.columns if col != "geometry"
            ]
            self._hover_columns = self._PRIOGRID_HOVER_COLS
        elif level == SpatialLevel.CM:
            self._world = self.__get_country_shapefile()
            self._location_col = "ADM0_A3"
            self._featureidkey = "properties.ADM0_A3"
            # Get all available country attributes (excluding geometry)
            self._country_attributes = [
                col for col in self._world.columns if col != "geometry"
            ]
            self._hover_columns = self._COUNTRY_HOVER_COLS
        else:
            raise ValueError("Invalid level. Must be SpatialLevel.CM or PGM.")

        self._mapping_dataframe = None
        # Built lazily on first choropleth render (the only consumer). The PGM raster
        # path (C-26/#125) never triggers it, so a large-grid raster render avoids the
        # ~260K-polygon simplification entirely.
        self._base_geojson = None
        # Lazy coastline/border overlay for the PGM raster + PNG paths (register C-205).
        self._coastline_cache = None

    def _coastline_xy(self):
        """Lon/lat polyline of national borders/coastlines for the PGM raster + PNG
        overlay (register C-205) — so a global value-lattice is geographically
        orientable. Derived from the committed Natural-Earth 110m **country** shapefile
        (~700 KB on disk; the simplified line layer is ~tens of KB) — NOT the 56 MB
        PRIO-GRID cell shapefile (C-23). Returned as ``(x, y)`` arrays with ``np.nan``
        separators between segments (one polyline for Plotly/matplotlib). Built lazily +
        cached; PGM-only (CM choropleths already imply coastlines via their polygons)."""
        if self._coastline_cache is not None:
            return self._coastline_cache
        path = (
            Path(__file__).parent.parent
            / "assets"
            / "shapefiles"
            / "country"
            / "ne_110m_admin_0_countries.shp"
        )
        world = gpd.read_file(path).to_crs(epsg=4326)
        boundary = world.geometry.boundary.simplify(0.2, preserve_topology=False)
        xs: list = []
        ys: list = []
        for geom in boundary:
            if geom is None or geom.is_empty:
                continue
            parts = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
            for line in parts:
                x, y = line.xy
                xs.extend(x)
                xs.append(np.nan)
                ys.extend(y)
                ys.append(np.nan)
        self._coastline_cache = (
            np.asarray(xs, dtype=np.float64),
            np.asarray(ys, dtype=np.float64),
        )
        return self._coastline_cache

    def _prepare_base_geojson(self):
        """
        Create optimized GeoJSON representation for efficient map rendering.

        Converts shapefile to WGS84 projection, retains only essential properties,
        and simplifies geometries to reduce file size while preserving topology.

        Internal Use:
            Called by __init__() during module initialization.

        Note:
            - Converts to EPSG:4326 (WGS84) for web compatibility
            - Simplifies geometries with 0.01 degree tolerance
            - Memory freed immediately after processing
        """
        base_gdf = self._world.to_crs(epsg=4326).copy()

        # Keep only essential properties to reduce size
        if self._level == SpatialLevel.PGM:
            base_gdf = base_gdf[["gid", "geometry"]]
        else:
            # For country frames, keep ADM0_A3 (which matches isoab) and geometry
            base_gdf = base_gdf[["ADM0_A3", "geometry"]]

        # Simplify geometries to reduce file size
        base_gdf["geometry"] = base_gdf.geometry.simplify(
            tolerance=0.01, preserve_topology=True
        )

        self._base_geojson = base_gdf.__geo_interface__

        # Free memory
        del base_gdf
        gc.collect()

    def __get_country_shapefile(self):
        """
        Load Natural Earth country boundaries shapefile.

        Internal Use:
            Called by __init__() for country-level datasets.

        Returns:
            geopandas.GeoDataFrame: Country boundaries with attributes:
                - ADM0_A3: ISO 3-letter country code
                - geometry: Country polygon/multipolygon
                - Additional Natural Earth attributes

        Raises:
            FileNotFoundError: If shapefile doesn't exist at expected path
            OSError: If shapefile cannot be read

        Note:
            - Uses Natural Earth 1:110m resolution (simplified)
            - Suitable for global-scale visualization
            - Path: assets/shapefiles/country/ne_110m_admin_0_countries.shp
        """
        path = (
            Path(__file__).parent.parent
            / "assets"
            / "shapefiles"
            / "country"
            / "ne_110m_admin_0_countries.shp"
        )
        world = gpd.read_file(path)
        # Normalize the merge key to real ISO alpha-3 codes (register C-206):
        # Natural Earth's ADM0_A3 carries NE-internal codes for a few
        # territories — notably South Sudan "SDS" vs ISO "SSD" — so the isoab
        # merge silently dropped those countries from CM maps. Prefer ISO_A3_EH
        # where it is a real code; keep ADM0_A3 for the "-99" disputed
        # territories (N. Cyprus, Somaliland, Kosovo — no VIEWS isoab exists
        # for them anyway).
        if "ISO_A3_EH" in world.columns:
            iso_eh = world["ISO_A3_EH"]
            world["ADM0_A3"] = world["ADM0_A3"].where(iso_eh == "-99", iso_eh)

        return world

    def __get_priogrid_shapefile(self):
        """
        Load PRIO-GRID cell boundaries shapefile.

        Internal Use:
            Called by __init__() for priogrid-level datasets.

        Returns:
            geopandas.GeoDataFrame: Grid cell boundaries with attributes:
                - gid: Grid cell identifier
                - row, col: Grid coordinates
                - geometry: Cell polygon (0.5° × 0.5°)
                - Additional PRIO-GRID attributes

        Raises:
            FileNotFoundError: If shapefile doesn't exist at expected path
            OSError: If shapefile cannot be read

        Note:
            - PRIO-GRID cells are 0.5° × 0.5° (~55km at equator)
            - Global coverage with ~260,000 cells
            - Path: assets/shapefiles/priogrid/priogrid_cell.shp
        """
        path = (
            Path(__file__).parent.parent
            / "assets"
            / "shapefiles"
            / "priogrid"
            / "priogrid_cell.shp"
        )
        return gpd.read_file(path)

    def __check_missing_geometries(
        self, mapping_dataframe: pd.DataFrame, drop_missing_geometries: bool = True
    ):
        """
        Validate geometries and optionally remove invalid rows.

        Identifies rows with missing or empty geometries and either removes them
        or logs warnings about their presence.

        Internal Use:
            Called by __init_mapping_dataframe() during data preparation.

        Args:
            mapping_dataframe: GeoDataFrame to validate
            drop_missing_geometries: If True, removes rows with invalid geometries.
                If False, only logs warnings.

        Returns:
            pd.DataFrame: Cleaned GeoDataFrame (or original if drop=False)

        Note:
            - Logs unique ISO codes for missing geometries
            - Reports number of dropped rows and their IDs
            - Missing geometries typically indicate:
              - Data outside shapefile coverage
              - Mismatched entity IDs
              - Corrupt geometry data
        """
        missing = mapping_dataframe[
            mapping_dataframe.geometry.is_empty | mapping_dataframe.geometry.isna()
        ]
        if not missing.empty:
            logger.warning(f"Missing geometries for: {missing['isoab'].unique()}")
        if drop_missing_geometries:
            initial_count = len(mapping_dataframe)
            cleaned_gdf = mapping_dataframe[
                (~mapping_dataframe.geometry.is_empty)
                & (~mapping_dataframe.geometry.isna())
            ].copy()

            dropped_count = initial_count - len(cleaned_gdf)
            if dropped_count > 0:
                logger.warning(
                    f"Dropped {dropped_count} rows with missing geometries. "
                    f"Remaining: {len(cleaned_gdf)} rows. "
                    f"Missing IDs: "
                    f"{mapping_dataframe[self._entity_id][mapping_dataframe.geometry.isna()].unique().tolist()}"
                )
            return cleaned_gdf
        return mapping_dataframe

    def build_mapping_dataframe(
        self, frame: PredictionFrame
    ) -> gpd.GeoDataFrame:
        """
        Build a visualization-ready GeoDataFrame from a PredictionFrame.

        Calls the frame→pandas adapter (which adds isoab + country_name via the
        index-keyed metadata accessors), then merges with the shapefile and
        drops rows with missing geometries. **Assigns** ``self._mapping_dataframe``
        (the full-range frame used by the static-map colorbar — resolves the
        former Deviation #3 latent ``AttributeError``).

        Returns:
            gpd.GeoDataFrame with the target column, geometry, isoab,
            country_name, and shapefile attributes.
        """
        flat = frames_to_mapping_df(frame, self._target_column, self._level)

        # Compact VALUE columns to float32 — but never the identity columns
        # (#234): a float32 month_id/entity id leaks "594.0"-style labels into
        # titles and animation sliders and costs integer-exactness for ids.
        numeric_cols = flat.select_dtypes(include=np.number).columns
        value_cols = [
            c for c in numeric_cols if c not in (self._time_id, self._entity_id)
        ]
        flat[value_cols] = flat[value_cols].astype(np.float32)

        if self._level == SpatialLevel.CM:
            flat = flat.merge(
                self._world,
                left_on="isoab",
                right_on="ADM0_A3",
                how="left",
            )
            merged_gdf = self.__check_missing_geometries(
                gpd.GeoDataFrame(flat, geometry="geometry", crs=self._world.crs)
            )
        else:
            flat = flat.merge(
                self._world,
                left_on=self._entity_id,
                right_on="gid",
                how="left",
            )
            merged_gdf = self.__check_missing_geometries(
                gpd.GeoDataFrame(flat, geometry="geometry", crs=self._world.crs)
            )

        self._mapping_dataframe = merged_gdf
        return merged_gdf

    def get_subset_mapping_dataframe(
        self,
        time_ids: Optional[Union[int, List[int]]] = None,
        entity_ids: Optional[Union[int, List[int]]] = None,
    ) -> pd.DataFrame:
        """
        Extract a geographically-enabled subset of the frame for visualization.

        Filters the frame's rows by ``time_ids``/``entity_ids`` (a boolean mask
        on ``frame.index.time``/``unit``), then builds the shapefile-merged
        GeoDataFrame.

        Args:
            time_ids: Time period(s) to include (int, list, or None for all).
            entity_ids: Entity id(s) to include (int, list, or None for all).

        Returns:
            gpd.GeoDataFrame ready for mapping (target column, geometry, isoab,
            country_name, shapefile attributes).
        """
        mask = np.ones(self._frame.n_rows, dtype=bool)
        if time_ids is not None:
            wanted = [time_ids] if isinstance(time_ids, int) else list(time_ids)
            mask &= np.isin(self._frame.index.time, wanted)
        if entity_ids is not None:
            wanted = (
                [entity_ids] if isinstance(entity_ids, int) else list(entity_ids)
            )
            mask &= np.isin(self._frame.index.unit, wanted)

        subset = self._frame if mask.all() else self._frame.select(mask)
        return self.build_mapping_dataframe(subset)

    def _plot_interactive_map(self, mapping_dataframe: gpd.GeoDataFrame, target: str):
        """
        Generate animated Plotly choropleth with temporal controls.

        Creates interactive web-based map with play/pause controls, time slider,
        and hover tooltips showing location details and values.

        Internal Use:
            Called by plot_map() when interactive=True.

        Args:
            mapping_dataframe: GeoDataFrame with data to visualize
            target: Column name to visualize on the map

        Returns:
            plotly.graph_objs._figure.Figure: Interactive Plotly figure with:
                - Animated time slider
                - Play/pause buttons
                - Hover tooltips with metadata
                - Color scale based on 50th-95th quantiles

        Note:
            - Optimizes memory by using float32 and pivot tables
            - Color scale fixed globally across all frames
            - Hover shows location ID, metadata, time, and value
            - Animation duration: 500ms per frame
            - Typical render time: 2-10 seconds for full dataset
        """
        # Build the base GeoJSON lazily — this is the choropleth path's only consumer
        # (the PGM raster path skips it; see _plot_interactive_raster_map).
        if self._base_geojson is None:
            self._prepare_base_geojson()

        # Create pivot table for efficient data storage
        all_locations = mapping_dataframe[self._location_col].unique()
        all_times = sorted(mapping_dataframe[self._time_id].unique())

        # Create pivot table
        pivot_df = mapping_dataframe.pivot_table(
            index=self._location_col,
            columns=self._time_id,
            values=target,
            aggfunc="first",
        ).reindex(all_locations)

        # Convert to float32 to save memory
        z_data = pivot_df[all_times].astype(np.float32).values

        # Precompute fixed properties for hover data
        fixed_props = mapping_dataframe.drop_duplicates(self._location_col).set_index(
            self._location_col
        )

        exclude_cols = ["geometry", self._time_id, self._entity_id, target]
        hover_columns = [
            col
            for col in self._hover_columns
            if col in fixed_props.columns and col not in exclude_cols
        ]

        # Determine location label based on level
        location_label = "gid" if self._level == SpatialLevel.PGM else "ADM0_A3"

        # Log-scale z for color; original values stored in customdata for hover display
        z_data_color = np.log1p(np.clip(z_data, 0, None)).astype(np.float32)

        # Prepare base customdata (fixed properties)
        # customdata layout: [loc, *hover_cols, time, original_z]
        base_customdata = []
        for loc_idx, loc in enumerate(all_locations):
            row_data = [loc]  # Add location ID as first element
            # Add all hover columns (excluding target)
            for attr in hover_columns:
                if attr in fixed_props.columns:
                    row_data.append(fixed_props.loc[loc, attr])
                else:
                    row_data.append(None)
            row_data.append(all_times[0])  # Add time
            row_data.append(round(float(z_data[loc_idx, 0]), 2))  # original value for hover
            base_customdata.append(row_data)

        # Create hovertemplate — show original (non-log) value via customdata
        hover_attrs = "<br>".join(
            [
                f"<b>{attr}</b>: %{{customdata[{i+1}]}}"
                for i, attr in enumerate(hover_columns)
            ]
        )
        _orig_z_idx = len(hover_columns) + 2
        hovertemplate = (
            f"<b>{location_label}</b>: %{{customdata[0]}}<br>"
            + hover_attrs
            + f"<br>{self._time_id}: %{{customdata[{len(hover_columns)+1}]}}"
            + f"<br>{target}: %{{customdata[{_orig_z_idx}]}}<extra></extra>"
        )

        # Colour anchoring + original-unit ticks (C-191): nonzero-anchored,
        # top-of-bar always labelled — see _log_color_scale.
        z_min = 0.0
        z_max, _tick_log, _tick_text = _log_color_scale(z_data)

        # Create figure with graph objects for better control
        fig = go.Figure(
            data=go.Choropleth(
                geojson=self._base_geojson,
                locations=all_locations,
                z=z_data_color[:, 0],  # First time step (log-scaled for color)
                featureidkey=self._featureidkey,
                customdata=base_customdata,
                hovertemplate=hovertemplate,
                marker_line_width=0.5,
                coloraxis="coloraxis",
            )
        )

        # Prepare frames with time-specific data
        frames = []
        for i, time in enumerate(all_times[1:], start=1):
            # Prepare customdata for this frame — same layout: [loc, *hover_cols, time, original_z]
            frame_customdata = []
            for loc_idx, loc in enumerate(all_locations):
                row_data = [loc]  # Add location ID as first element
                # Add all hover columns
                for attr in hover_columns:
                    if attr in fixed_props.columns:
                        row_data.append(fixed_props.loc[loc, attr])
                    else:
                        row_data.append(None)
                row_data.append(time)  # Add time
                row_data.append(round(float(z_data[loc_idx, i]), 2))  # original value for hover
                frame_customdata.append(row_data)

            frame_hover_attrs = "<br>".join(
                [
                    f"<b>{attr}</b>: %{{customdata[{i+1}]}}"
                    for i, attr in enumerate(hover_columns)
                ]
            )
            frame_hovertemplate = (
                f"<b>{location_label}</b>: %{{customdata[0]}}<br>"
                + frame_hover_attrs
                + f"<br>{self._time_id}: %{{customdata[{len(hover_columns)+1}]}}"
                + f"<br>{target}: %{{customdata[{_orig_z_idx}]}}<extra></extra>"
            )

            frames.append(
                go.Frame(
                    data=[
                        go.Choropleth(
                            z=z_data_color[:, i],  # log-scaled for color
                            customdata=frame_customdata,
                            hovertemplate=frame_hovertemplate,
                        )
                    ],
                    name=str(time),
                )
            )

        # Animation chrome ONLY when there is something to animate (#258):
        # a single-month figure is a static map with hover.
        if len(all_times) > 1:
            fig.frames = frames

            # Add play button and slider
            fig.update_layout(
                updatemenus=[
                    {
                        "type": "buttons",
                        "buttons": [
                            {
                                "args": [
                                    None,
                                    {
                                        "frame": {"duration": 500, "redraw": True},
                                        "fromcurrent": True,
                                        "transition": {"duration": 300},
                                    },
                                ],
                                "label": "Play",
                                "method": "animate",
                            },
                            {
                                "args": [
                                    [None],
                                    {
                                        "frame": {"duration": 0, "redraw": True},
                                        "mode": "immediate",
                                        "transition": {"duration": 0},
                                    },
                                ],
                                "label": "Pause",
                                "method": "animate",
                            },
                        ],
                        "direction": "left",
                        "pad": {"r": 10, "t": 87},
                        "showactive": False,
                        "x": 0.1,
                        "xanchor": "right",
                        "y": 0,
                        "yanchor": "top",
                    }
                ],
                sliders=[
                    {
                        "active": 0,
                        "yanchor": "top",
                        "xanchor": "left",
                        "currentvalue": {
                            "font": {"size": 14},
                            "prefix": f"{self._time_id}: ",
                            "visible": True,
                            "xanchor": "right",
                        },
                        "transition": {"duration": 300, "easing": "cubic-in-out"},
                        "pad": {"b": 10, "t": 50},
                        "len": 0.9,
                        "x": 0.1,
                        "y": 0,
                        "steps": [
                            {
                                "args": [
                                    [str(time)],
                                    {
                                        "frame": {"duration": 300, "redraw": True},
                                        "mode": "immediate",
                                    },
                                ],
                                "label": str(time),
                                "method": "animate",
                            }
                            for time in all_times
                        ],
                    }
                ],
            )

        # Layout adjustments with increased padding
        fig.update_layout(
            height=900,
            autosize=True,
            margin={"r": 20, "t": 60, "l": 20, "b": 60},  # Increased padding
            coloraxis=dict(
                colorscale="OrRd",
                cmin=z_min,
                cmax=z_max,
                colorbar=dict(
                    tickvals=_tick_log,
                    ticktext=_tick_text,
                    title=_COLORBAR_TITLE,
                ),
            ),
            annotations=[
                dict(
                    x=0.5,
                    y=-0.15,
                    showarrow=False,
                    text="",
                    xref="paper",
                    yref="paper",
                )
            ],
        )

        fig.update_geos(
            fitbounds="locations",
            visible=False,
            showcountries=True,
            countrycolor="rgba(100,100,100,0.3)",
            countrywidth=0.3,
            showlakes=True,
            showocean=False,
            showsubunits=True,
            subunitcolor="rgba(200,200,200,0.2)",
            subunitwidth=0.05,
        )

        # Free memory
        del pivot_df, z_data, z_data_color, fixed_props, base_customdata
        gc.collect()

        return fig

    def _plot_interactive_raster_map(
        self,
        mapping_dataframe: gpd.GeoDataFrame,
        target: str,
        color_mode: str = "log_count",
    ):
        """Render the PGM lattice as a ``go.Heatmap`` over (lon, lat) — the
        storage-viable large-grid path (register C-26 / #125).

        PRIO-GRID is a regular 0.5° raster, so each cell maps to a (``xcoord``,
        ``ycoord``) grid position and values become a dense 2-D array (missing cells
        → NaN → blank). The figure carries O(cells) scalars per time step instead of
        the ~260K polygon geometries a ``go.Choropleth`` embeds, so the full global
        grid is renderable without OOM and within the report's byte budget — and the
        ~260K-polygon GeoJSON is never built (it stays lazy). Colour is log-scaled
        (zero-inflated heavy-tailed counts — C-191) with a labelled original-scale
        colourbar; the map is a per-cell **point summary** (``tower_point``), labelled
        as such (C-109). Faithful by construction: one cell → one array element, no
        aggregation (C-189) and no omission (C-190).
        """
        all_times = sorted(mapping_dataframe[self._time_id].unique())
        fixed = mapping_dataframe.drop_duplicates(self._location_col).set_index(
            self._location_col
        )
        if "xcoord" not in fixed.columns or "ycoord" not in fixed.columns:
            raise ValueError(
                "Raster render requires per-cell 'xcoord'/'ycoord' (PRIO-GRID cell "
                "centres); not present in the mapping dataframe."
            )

        # UNIFORM lon/lat axes spanning the extent (PRIO-GRID 0.5° grid — C-208):
        # axes built from coords-present-in-data stretch cells across lattice
        # gaps (plotly midpoint bricks), painting isolated territories' coastal
        # neighbours over open ocean. Uniform axes give every brick its true
        # 0.5° size and position; missing cells stay NaN (transparent).
        lons = _uniform_lattice(fixed["xcoord"].to_numpy())
        lats = _uniform_lattice(fixed["ycoord"].to_numpy())

        # Values: locations × times, then scattered into the dense (lat, lon) grid.
        pivot = mapping_dataframe.pivot_table(
            index=self._location_col,
            columns=self._time_id,
            values=target,
            aggfunc="first",
        ).reindex(fixed.index)
        z_loc = pivot[all_times].astype(np.float32).values  # [n_loc, n_time]
        li = _lattice_indices(fixed["ycoord"].to_numpy(), lats)
        ci = _lattice_indices(fixed["xcoord"].to_numpy(), lons)

        def _grid(t_idx: int) -> np.ndarray:
            g = np.full((len(lats), len(lons)), np.nan, dtype=np.float32)
            g[li, ci] = z_loc[:, t_idx]
            return g

        if color_mode == "unit_interval":
            # Probability layer (#233): colour IS the value — no log transform.
            def _logc(g: np.ndarray) -> np.ndarray:
                return np.clip(g, 0, 1).astype(np.float32)
        else:
            def _logc(g: np.ndarray) -> np.ndarray:
                return np.log1p(np.clip(g, 0, None)).astype(np.float32)

        # Cell id (PRIO-GRID gid) per lattice position — time-invariant; carried in
        # customdata so hover shows the cell id alongside the original value.
        gid_grid = np.full((len(lats), len(lons)), np.nan, dtype=np.float64)
        gid_grid[li, ci] = np.asarray(fixed.index, dtype=np.float64)

        def _customdata(t_idx: int) -> np.ndarray:
            # stacked per cell: [..., 0] = original (non-log) value, [..., 1] = gid
            return np.dstack([_grid(t_idx), gid_grid])

        # Colour anchoring + ticks: counts get the nonzero-anchored log scale
        # (C-191); probabilities get linear 0-1 (#233).
        z_min = 0.0
        if color_mode == "unit_interval":
            z_max, _tick_log, _tick_text = _unit_interval_scale()
            _cbar_title = _PROB_COLORBAR_TITLE
        else:
            z_max, _tick_log, _tick_text = _log_color_scale(z_loc)
            _cbar_title = _COLORBAR_TITLE

        grid0 = _grid(0)
        fig = go.Figure(
            data=go.Heatmap(
                z=_logc(grid0),
                x=lons,
                y=lats,
                customdata=_customdata(0),  # [value, gid] per cell for hover
                coloraxis="coloraxis",
                # NaN filler cells (ocean, post-C-208 most of the lattice) offer
                # no hover popup (falsify F4).
                hoverongaps=False,
                hovertemplate=(
                    "cell %{customdata[1]:.0f} · lon %{x}, lat %{y}<br>"
                    f"{target}: %{{customdata[0]:.2f}}<extra></extra>"
                ),
            )
        )
        # Coastline/border reference overlay (register C-205) so the lattice is
        # geographically orientable; static trace 1 (animation frames update
        # trace 0). SVG `Scatter`, NOT `Scattergl` (#258): plotly renders WebGL
        # beneath the SVG layer, so gl borders vanish under land-covering cells.
        _cx, _cy = self._coastline_xy()
        fig.add_trace(
            go.Scatter(
                x=_cx,
                y=_cy,
                mode="lines",
                line={"color": "rgba(0,0,0,0.35)", "width": 0.5},
                hoverinfo="skip",
                showlegend=False,
                name="borders",
            )
        )
        # Animation chrome ONLY when there is something to animate (#258):
        # a single-month step figure is a static map with hover — a dead
        # Play/Pause and a one-step slider are misleading UI.
        if len(all_times) > 1:
            fig.frames = [
                go.Frame(
                    data=[go.Heatmap(z=_logc(_grid(i)), customdata=_customdata(i))],
                    name=str(time),
                )
                for i, time in enumerate(all_times[1:], start=1)
            ]

            # Play/pause + slider (inline; the choropleth path keeps its own copy).
            fig.update_layout(
                updatemenus=[
                    {
                        "type": "buttons",
                        "buttons": [
                            {
                                "args": [
                                    None,
                                    {
                                        "frame": {"duration": 500, "redraw": True},
                                        "fromcurrent": True,
                                        "transition": {"duration": 300},
                                    },
                                ],
                                "label": "Play",
                                "method": "animate",
                            },
                            {
                                "args": [
                                    [None],
                                    {
                                        "frame": {"duration": 0, "redraw": True},
                                        "mode": "immediate",
                                        "transition": {"duration": 0},
                                    },
                                ],
                                "label": "Pause",
                                "method": "animate",
                            },
                        ],
                        "direction": "left",
                        "pad": {"r": 10, "t": 87},
                        "showactive": False,
                        "x": 0.1,
                        "xanchor": "right",
                        "y": 0,
                        "yanchor": "top",
                    }
                ],
                sliders=[
                    {
                        "active": 0,
                        "yanchor": "top",
                        "xanchor": "left",
                        "currentvalue": {
                            "font": {"size": 14},
                            "prefix": f"{self._time_id}: ",
                            "visible": True,
                            "xanchor": "right",
                        },
                        "transition": {"duration": 300, "easing": "cubic-in-out"},
                        "pad": {"b": 10, "t": 50},
                        "len": 0.9,
                        "x": 0.1,
                        "y": 0,
                        "steps": [
                            {
                                "args": [
                                    [str(time)],
                                    {
                                        "frame": {"duration": 300, "redraw": True},
                                        "mode": "immediate",
                                    },
                                ],
                                "label": str(time),
                                "method": "animate",
                            }
                            for time in all_times
                        ],
                    }
                ],
            )

        fig.update_layout(
            height=900,
            autosize=True,
            margin={"r": 20, "t": 60, "l": 20, "b": 60},
            # Clip the (global) coastline overlay to the data extent.
            xaxis=dict(
                title="Longitude",
                constrain="domain",
                range=[float(lons.min()), float(lons.max())],
            ),
            # Equirectangular aspect (1 lon unit == 1 lat unit on screen).
            # constrain='domain' (#258): satisfy aspect by SHRINKING the plot
            # area, never by stretching latitude past +/-90 into grey bands.
            yaxis=dict(
                title="Latitude",
                scaleanchor="x",
                scaleratio=1,
                constrain="domain",
                range=[float(lats.min()), float(lats.max())],
            ),
            # NaN bricks are transparent — a grey plot background makes
            # no-data read grey, distinct from zero-forecast cream (#234).
            plot_bgcolor=_NO_DATA_GREY,
            coloraxis=dict(
                colorscale="OrRd",
                cmin=z_min,
                cmax=z_max,
                colorbar=dict(
                    tickvals=_tick_log,
                    ticktext=_tick_text,
                    title=_cbar_title,
                ),
            ),
            annotations=[
                dict(
                    x=0.5,
                    y=-0.12,
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    text=(
                        "Per-cell summary raster of the PRIO-GRID lattice; "
                        "grey background = no data / outside coverage."
                    ),
                )
            ],
        )

        gc.collect()
        return fig

    def _plot_image_map(
        self,
        mapping_dataframe: gpd.GeoDataFrame,
        target: str,
        color_mode: str = "log_count",
    ) -> str:
        """Render the PGM lattice as a base64 **PNG image** — the scale-flat globe path
        (epic #188, register C-205). A binary bitmap is ``O(pixels)``, independent of
        cell-count and origin-count, so it renders the full global grid within the
        offline byte budget where the ``go.Heatmap`` (whose animation frames are dense
        JSON arrays) cannot. Returns a self-contained ``<img>`` data-URI (no external
        refs — offline, C-28), embeddable via ``ReportModule.add_html`` exactly like the
        static-map path.

        Renders exactly ONE month per call — month choice belongs at the Compose
        boundary (#232); a multi-month dataframe here raises rather than silently
        picking one (the pre-#232 behavior rendered only ``times[-1]``, the furthest
        and most uncertain step of the horizon). Faithful by construction —
        one cell → one pixel: no aggregation (C-189), no omission (C-190). Colour is log-
        scaled with a labelled original-scale colourbar (C-191), mirroring the heatmap.
        **Tradeoff:** a static image has no per-cell hover of the value — that is why the
        interactive heatmap stays primary wherever it fits the budget (epic #188).
        """
        times = sorted(mapping_dataframe[self._time_id].unique())
        if len(times) != 1:
            raise ValueError(
                f"Image render expects exactly one {self._time_id} per call; "
                f"got {len(times)} ({[int(t) for t in times[:5]]}...). Subset "
                "per month at the Compose boundary (#232) — no silent month "
                "picking."
            )
        the_month = int(times[0])
        frame_df = mapping_dataframe[mapping_dataframe[self._time_id] == times[0]]
        fixed = frame_df.drop_duplicates(self._location_col).set_index(self._location_col)
        if "xcoord" not in fixed.columns or "ycoord" not in fixed.columns:
            raise ValueError(
                "Image render requires per-cell 'xcoord'/'ycoord' (PRIO-GRID cell "
                "centres); not present in the mapping dataframe."
            )

        # UNIFORM lattice (C-208): imshow spreads the row array EVENLY across the
        # extent, so a coords-present-in-data-only z misplaces EVERY cell when
        # the lattice has gaps (isolated territories) and desyncs the coastline
        # overlay. Uniform axes + index arithmetic give true positions.
        lons = _uniform_lattice(fixed["xcoord"].to_numpy())
        lats = _uniform_lattice(fixed["ycoord"].to_numpy())
        z = np.full((len(lats), len(lons)), np.nan, dtype=np.float32)
        z[
            _lattice_indices(fixed["ycoord"].to_numpy(), lats),
            _lattice_indices(fixed["xcoord"].to_numpy(), lons),
        ] = fixed[target].to_numpy(dtype=np.float32)

        if color_mode == "unit_interval":
            # Probability layer (#233): colour IS the value — linear 0-1.
            zshow = np.clip(z, 0, 1)
            vmax, tick_log, tick_text = _unit_interval_scale()
            cbar_label = f"{target} (probability, linear 0-1 scale)"
        else:
            # Colour anchoring + original-unit ticks (C-191): nonzero-anchored,
            # top-of-bar always labelled — see _log_color_scale (shared with the
            # heatmap/choropleth so all tiers read identically).
            zshow = np.log1p(np.clip(z, 0, None))
            vmax, tick_log, tick_text = _log_color_scale(fixed[target].to_numpy())
            cbar_label = f"{target} (labels: original units; colour: log-scaled)"

        fig, ax = plt.subplots(figsize=(12, 6))
        # No-data cells (NaN — ocean/outside coverage) render GREY, visually
        # distinct from the palest OrRd of a ZERO forecast (#234, C-190:
        # omission must not read as "no risk").
        cmap = plt.get_cmap("OrRd").copy()
        cmap.set_bad(_NO_DATA_GREY)
        # Extent = OUTER CELL EDGES (centre ± half a cell), so each 0.5° cell
        # pixel sits at its true coordinates and the coastline overlay aligns
        # exactly (C-208; the old centre-to-centre extent shifted everything by
        # half a cell even on gap-free lattices).
        half = _PGM_CELL_DEG / 2
        extent = [
            float(lons[0]) - half, float(lons[-1]) + half,
            float(lats[0]) - half, float(lats[-1]) + half,
        ]
        im = ax.imshow(
            zshow,
            origin="lower",
            extent=extent,
            cmap=cmap,
            vmin=0.0,
            vmax=vmax,
            aspect="equal",
            interpolation="nearest",
        )
        # Coastline/border reference overlay (register C-205), clipped to the data
        # extent so the (global) borders frame only the rendered region.
        cx, cy = self._coastline_xy()
        ax.plot(cx, cy, color="black", linewidth=0.3, alpha=0.4)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])

        cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
        cbar.set_ticks(tick_log)
        cbar.set_ticklabels(tick_text)
        cbar.set_label(cbar_label)
        ax.set_xlabel(
            "Longitude\n(grey = no data / outside coverage; palest = zero forecast)"
        )
        ax.set_ylabel("Latitude")
        # PGM time is always month_id; show the human date beside the raw id
        # (int — never the float32-cast "594.0" form, #232/#234).
        when = (
            f"{month_id_to_label(the_month)} — {self._time_id} {the_month}"
            if self._time_id == "month_id"
            else f"{self._time_id} {the_month}"
        )
        ax.set_title(f"{target} — per-cell point summary ({when})")

        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
        plt.close(fig)
        gc.collect()
        buf.seek(0)
        img = base64.b64encode(buf.getvalue()).decode("utf-8")
        return (
            f'<img src="data:image/png;base64,{img}" '
            f'alt="{target} PRIO-GRID point summary ({when})" '
            'style="width:100%;height:auto;">'
        )

    def _plot_static_map(
        self, mapping_dataframe: gpd.GeoDataFrame, target: str, time_unit: int
    ):
        """
        Generate static matplotlib choropleth for single time period.

        Creates publication-quality static map with customizable styling and
        color scale for a single snapshot in time.

        Internal Use:
            Called by plot_map() when interactive=False.

        Args:
            mapping_dataframe: GeoDataFrame with data to visualize
            target: Column name to visualize on the map
            time_unit: Time period identifier for title

        Returns:
            matplotlib.figure.Figure: Matplotlib figure object with:
                - Choropleth with OrRd color scheme
                - Color scale: 50th-95th quantile
                - Black boundaries (0.3pt width)
                - Horizontal colorbar with label
                - Axis labels (Longitude, Latitude)

        Raises:
            ValueError: If target column not found or contains only null values

        Note:
            - Figure size: 15" × 10"
            - Suitable for publication and reports
            - Color range optimized to highlight variation
            - Edge color: #404040 (dark gray)
            - Alpha: 0.9 for slight transparency
        """
        from matplotlib.colors import FuncNorm

        if target not in mapping_dataframe.columns:
            raise ValueError(f"Target column '{target}' not found")
        if mapping_dataframe[target].isnull().all():
            raise ValueError(f"No valid values for target '{target}'")

        _vmin = max(float(mapping_dataframe[target].quantile(0.5)), 0.0)
        _vmax = float(mapping_dataframe[target].quantile(0.95))
        _log_norm = FuncNorm((np.log1p, np.expm1), vmin=_vmin, vmax=_vmax)

        fig, ax = plt.subplots(1, 1, figsize=(15, 10))
        mapping_dataframe.boundary.plot(ax=ax, linewidth=0.3, color="black")

        mapping_dataframe.plot(
            column=target,
            ax=ax,
            legend=True,
            cmap="OrRd",
            norm=_log_norm,
            linewidth=0.1,
            edgecolor="#404040",
            alpha=0.9,
        )

        plt.title(f"{target} for {self._time_id} {int(time_unit)}", fontsize=15)
        plt.xlabel("Longitude", fontsize=12)
        plt.ylabel("Latitude", fontsize=12)

        _vmin_full = max(float(self._mapping_dataframe[target].min()), 0.0)
        _vmax_full = float(self._mapping_dataframe[target].max())
        sm = plt.cm.ScalarMappable(
            cmap="OrRd",
            norm=FuncNorm((np.log1p, np.expm1), vmin=_vmin_full, vmax=_vmax_full),
        )
        sm._A = []

        cbar = fig.colorbar(
            sm, ax=ax, orientation="horizontal", fraction=0.036, pad=0.1
        )
        cbar.set_label(f"{target}", fontsize=12)

        return fig

    def plot_map(
        self,
        mapping_dataframe: pd.DataFrame,
        target: str,
        interactive: bool = False,
        as_html: bool = False,
        max_cells: int | None = None,
        raster: bool = False,
        max_raster_cell_frames: int | None = None,
        image_fallback: bool = False,
        color_mode: str = "log_count",
    ):
        """
        Generate choropleth map visualization for specified target variable.

        Creates either interactive (Plotly) or static (Matplotlib) map showing
        geographic distribution of values. Supports temporal animation and
        HTML export.

        Args:
            mapping_dataframe: GeoDataFrame from get_subset_mapping_dataframe()
            target: Variable to visualize. Must be in dataset's targets or features.
            interactive: If True, creates animated Plotly map with controls.
                If False, creates static Matplotlib plot. Default: False
            as_html: If True, returns HTML string instead of figure object.
                Useful for embedding in reports. Default: False
            max_cells: Scale guard (register C-26). If set and the number of
                rendered map entries (``len(mapping_dataframe)`` — entities × time
                steps, the real size/memory driver) exceeds it, fail loud BEFORE
                building any Plotly/Matplotlib traces rather than risk an
                out-of-memory failure or a multi-GB file. ``None`` disables the
                guard. Injected from ``ReportingConfig.max_map_cells`` at the
                Compose boundary (ADR-016); the Render layer never reads config.
                Default: None
            raster: Render a PGM grid as a bounded ``go.Heatmap`` over the lattice
                (pixels, no polygon geometry) instead of a vector choropleth — the
                storage-viable large-grid path (C-26 / #125). Only applies to PGM +
                interactive; ignored (with a warning) for CM. Default: False
            max_raster_cell_frames: Budget guard for the raster path (C-26 / C-203).
                If set and the rendered cell-frames (cells × time steps) exceed it,
                fail loud before building the figure (the dense per-frame arrays would
                make the offline HTML too large). Injected from
                ``ReportingConfig.max_raster_cell_frames``. ``None`` disables it.
                Default: None

        Returns:
            Union[str, matplotlib.figure.Figure, plotly.graph_objs.Figure]:
                - If as_html=True: HTML string for web embedding
                - If as_html=False and interactive=True: Plotly Figure
                - If as_html=False and interactive=False: Matplotlib Figure

        Raises:
            ValueError: If target not in dataset's targets or features
            ValueError: If static plot requested with multiple time periods
            ValueError: If max_cells is set and the render size exceeds it (C-26)

        Example:
            >>> # Interactive map for report
            >>> mapper = MappingModule(dataset)
            >>> gdf = mapper.get_subset_mapping_dataframe(time_ids=[520, 521, 522])
            >>> html = mapper.plot_map(
            ...     gdf,
            ...     target='pred_ged_sb',
            ...     interactive=True,
            ...     as_html=True
            ... )
            >>> with open('map.html', 'w') as f:
            ...     f.write(html)

            >>> # Static map for publication
            >>> gdf_single = mapper.get_subset_mapping_dataframe(time_ids=520)
            >>> fig = mapper.plot_map(gdf_single, 'pred_ged_sb', interactive=False)
            >>> fig.savefig('conflict_map.png', dpi=300)

        Note:
            - Interactive maps require single target across multiple times
            - Static maps require single time period
            - HTML output includes Plotly.js (works offline)
            - Array values automatically extracted if single-element
            - Memory optimized for large datasets (float32, garbage collection)
        """
        # The valid value column is the one this module was constructed for
        # (threaded from the caller); validate against the mapping dataframe.
        if target not in mapping_dataframe.columns:
            raise ValueError(
                f"Target '{target}' not found in the mapping dataframe. "
                f"Expected '{self._target_column}'."
            )

        # Choose the large-render strategy. The PGM raster path (C-26/#125) embeds no
        # polygon geometry — its payload is O(cells) scalars, not ~260K polygons — so
        # it is the declared opt-in for large grids and is exempt from the cell-count
        # guard below. CM is not a lattice, so `raster` only applies to PGM.
        use_raster = bool(raster) and self._level == SpatialLevel.PGM and interactive
        # Render-strategy ladder (epic globe-readiness): choropleth → heatmap → PNG.
        # The PNG image tier (declared at the Compose boundary, ADR-016) is the
        # scale-flat globe fallback; like the raster it is PGM + interactive only.
        use_image = bool(image_fallback) and self._level == SpatialLevel.PGM and interactive
        if raster and image_fallback:
            raise ValueError(
                "raster and image_fallback are mutually exclusive per call — "
                "the ADR-021 template renders them as SEPARATE step-+1 calls; "
                "setting both would silently drop the hover heatmap (ADR-008)."
            )
        if color_mode not in _COLOR_MODES:
            raise ValueError(
                f"Unknown color_mode {color_mode!r}; expected one of {_COLOR_MODES}."
            )
        if color_mode != "log_count" and not (use_raster or use_image):
            raise ValueError(
                "color_mode is implemented for the PGM raster/image paths only "
                "(#233); the choropleth path renders count layers."
            )
        if (raster or image_fallback) and self._level != SpatialLevel.PGM:
            logger.warning(
                "raster/image_fallback ignored for non-PGM level (countries are not a "
                "regular lattice); using the choropleth path."
            )

        # Scale guard (register C-26, ADR-008 fail-loud): refuse to render an
        # unreasonably large *vector choropleth* — turning a late, uncontrolled OOM /
        # multi-GB HTML file into an early, actionable refusal. The count is rendered
        # entries (entities × time steps) — the actual size/memory driver — checked
        # BEFORE any trace construction. `max_cells` is injected from ReportingConfig
        # at the Compose boundary (ADR-016); None disables the guard (e.g. small CM
        # maps). The raster path is exempt (its payload does not scale with polygon
        # geometry — that is the whole point of #125). The PNG image tier is likewise
        # exempt (its payload is O(pixels), independent of cell count).
        if max_cells is not None and not use_raster and not use_image:
            n_cells = len(mapping_dataframe)
            if n_cells > max_cells:
                raise ValueError(
                    f"Map render aborted: {n_cells:,} cells to render exceeds the "
                    f"max_map_cells limit of {max_cells:,} (register C-26). A render "
                    "this large risks an out-of-memory failure or a multi-GB HTML "
                    "file (≈86 MB at ~13k cells, single origin; the full global "
                    "PRIO-GRID grid is ~260k cells). Subset the data (fewer entities "
                    "and/or time steps), raise ReportingConfig.max_map_cells, or pass "
                    "raster=True to render the PGM grid as a bounded heatmap (#125)."
                )

        # Raster budget guard (register C-26 / C-203 / C-209, ADR-008 fail-loud):
        # the raster embeds no polygon geometry, but each animation frame is a
        # dense UNIFORM-lattice array (C-208), so the payload driver is the
        # bounding-box lattice — rows × cols × time-frames — NOT the number of
        # data rows (C-209: sparse-but-spread data costs bounding-box; a guard on
        # len(mapping_dataframe) passes while the z explodes). Injected from
        # ReportingConfig.max_raster_cell_frames at the Compose boundary
        # (ADR-016); None disables it.
        if use_raster and max_raster_cell_frames is not None:
            if {"xcoord", "ycoord"} <= set(mapping_dataframe.columns):
                n_cell_frames = pgm_lattice_cell_frames(
                    mapping_dataframe, self._time_id
                )
            else:
                # No coords: the raster path itself raises just below; this
                # pre-check quantity is moot but must not crash first.
                n_cell_frames = len(mapping_dataframe)
            if n_cell_frames > max_raster_cell_frames:
                raise ValueError(
                    f"Raster render aborted: {n_cell_frames:,} lattice cell-frames "
                    f"(bounding-box rows × cols × time steps) exceeds the "
                    f"max_raster_cell_frames limit of {max_raster_cell_frames:,} "
                    "(register C-26 / C-203 / C-209). Each animation frame is a "
                    "dense uniform-lattice array, so the offline HTML would be too "
                    "large. Reduce the number of rolling origins / time steps, "
                    "raise ReportingConfig.max_raster_cell_frames, or use the PNG "
                    "image fallback."
                )

        mapping_dataframe[target] = mapping_dataframe[target].apply(
            lambda x: x[0] if isinstance(x, np.ndarray) and len(x) == 1 else x
        )

        if interactive:
            if use_image:
                # PNG image tier (globe-scale fallback): a self-contained base64 <img>,
                # not a Plotly figure — always returned as HTML (its only artifact).
                return self._plot_image_map(
                    mapping_dataframe, target, color_mode=color_mode
                )
            fig = (
                self._plot_interactive_raster_map(
                    mapping_dataframe, target, color_mode=color_mode
                )
                if use_raster
                else self._plot_interactive_map(mapping_dataframe, target)
            )
            if as_html:
                html_str = fig.to_html(
                    full_html=True,
                    # The ReportModule inlines the SINGLE plotly.js copy
                    # (#258, C-28 offline) — figures ship without their own.
                    include_plotlyjs=False,
                    default_height=900,
                    div_id=f"map-container-{uuid.uuid4().hex}",
                )
                # Free memory after generating HTML
                del fig
                gc.collect()
                return html_str
            else:
                return fig
        else:
            time_units = mapping_dataframe[self._time_id].dropna().unique()
            if len(time_units) > 1:
                raise ValueError("Static plots require single time unit")
            fig = self._plot_static_map(mapping_dataframe, target, time_units[0])
            if as_html:
                buf = BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
                plt.close(fig)
                buf.seek(0)
                img_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                return f'<img src="data:image/png;base64,{img_str}">'
            else:
                return fig
