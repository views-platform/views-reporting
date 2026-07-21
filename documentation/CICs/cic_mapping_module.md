
# Class Intent Contract: MappingModule

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-07-21 (ADR-021 governance closeout — render strategies, colour modes, one-month image contract)
**Related ADRs:** ADR-018 (frames as the data contract), ADR-021 (image tier primary at scale; horizon-step + layer standard; layer-typed colour), ADR-016 (budgets injected at the Compose boundary), ADR-008 (fail-loud)

---

## 1. Purpose

> **What is this class for?**

MappingModule produces geographic choropleth visualizations (interactive Plotly or static Matplotlib) for VIEWS conflict-forecasting predictions at either country level (CM) or PRIO-GRID cell level (PGM). It is **frame-native** (epic #137, #138): it takes a `views_frames.PredictionFrame` + a `SpatialLevel` + a target column name, loads the appropriate shapefile, merges the prediction data with geometries and entity metadata (via the `frames_to_mapping_df` adapter — see `cic_frame_mapping_adapter.md`), and renders maps with layer-typed colour scales (log for counts, linear 0–1 for probabilities — #233). `build_mapping_dataframe` compacts VALUE columns to float32 but **never the identity columns** (`month_id`, entity ids stay integer — #234; a float month id leaked "594.0"-style labels into titles and sliders).

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform any statistical computation on the data (no aggregation, no HDI, no reconciliation).
- This class does **not** persist outputs to disk; callers are responsible for saving returned figures or HTML strings.
- This class does **not** handle non-geographic visualizations (line graphs, distributions, tables).
- This class does **not** transform or filter the underlying dataset beyond subsetting by time/entity IDs.
- This class does **not** support arbitrary shapefiles; it is hardcoded to Natural Earth country boundaries and PRIO-GRID cells bundled in `views_reporting/assets/shapefiles/`.

---

## 3. Responsibilities and Guarantees

- **Shapefile dispatch.** On construction, loads the correct shapefile based on whether `level` is `SpatialLevel.PGM` or `SpatialLevel.CM`. Raises `ValueError` on any other value.
- **Geometry preparation (lazy).** Converts geometries to EPSG:4326 (WGS84), simplifies with 0.01-degree tolerance, and caches a base GeoJSON (`_prepare_base_geojson`) — built **lazily on first choropleth render** (#125), so the PGM raster path never triggers the ~260K-polygon simplification.
- **Data-geometry merge.** `build_mapping_dataframe(frame)` calls the frame→pandas adapter `frames_to_mapping_df` (which enriches with ISO codes and country names via the index-keyed `get_isoab_for_index` / `get_name_for_index`), merges with the shapefile, drops missing geometries, and **assigns `self._mapping_dataframe`**. `get_subset_mapping_dataframe(time_ids, entity_ids)` filters the frame by a boolean mask on `frame.index.time`/`unit` then calls `build_mapping_dataframe`.
- **Missing geometry handling.** Rows with missing or empty geometries are dropped by default and logged (`__check_missing_geometries`).
- **Interactive maps.** `_plot_interactive_map()` builds an animated Plotly choropleth with time slider, play/pause buttons, hover tooltips showing original (non-log) values, and a log1p colour scale anchored from 0 to the 95th percentile of the **nonzero** values' logs (`_log_color_scale`, C-191 — zero-inflation-safe; top of the bar always labelled, "≥ N" under saturation; legend states labels are original units).
- **Interactive PGM raster (register C-26 / #125).** `_plot_interactive_raster_map()` renders the PGM lattice as a `go.Heatmap` over a **uniform 0.5° (lon, lat) lattice spanning the bounding box** (C-208: axes built only from coords-present-in-data let plotly's midpoint bricks stretch cells across lattice gaps — isolated territories like Marion Island painted their coastal neighbours over open ocean; uniform axes give every brick its true size/position, missing cells stay NaN with `hoverongaps=False`) — selected when `plot_map(raster=True)` and `level == PGM`. It embeds **no polygon GeoJSON** (payload is O(cells) scalars, not ~260K polygons), so the full grid renders within the report's byte budget; it is **faithful by construction** (one cell → one array element — no aggregation, no omission), log-coloured with a labelled colourbar (C-191: saturation anchored on the NONZERO tail — zero-inflation-safe; top of the bar always labelled, "≥ N" under saturation; legend states labels are original units), and labelled a per-cell point summary; the hover tooltip carries the **cell id (gid) + original value**. It also carries a static **coastline/border overlay** (a `go.Scattergl` `borders` trace, kept as trace 1 so animation frames still target the heatmap at trace 0) so a global value-lattice is geographically orientable (register C-205). `raster=True` is set by the forecast template for the **headline layer at step +1 only** (ADR-021) — a single month, far inside the C-209 budget by construction; size never selects the tier (the budgets are fail-loud backstops). It is ignored for CM (countries are not a lattice). (`ReportingConfig.pgm_raster` was removed under ADR-021 — the step-+1 raster is standard, not an opt-in.)
- **PGM PNG image — the scale-flat globe tier (register C-205 / epic #188; primary at scale per ADR-021).** `_plot_image_map()` renders **exactly ONE month per call** — a multi-month dataframe raises `ValueError` (ADR-008; month choice belongs at the Compose boundary, #232 — the pre-#232 silent `times[-1]` pick is gone). The single month's lattice renders as a **base64 PNG `<img>`** (matplotlib `imshow` over the same **uniform 0.5° lattice** with the extent at outer cell EDGES — C-208: imshow spreads rows evenly across the extent, so a gapped lattice misplaced every cell and desynced the coastline; `origin="lower"`, coloured per the layer's `color_mode` (below) with a labelled colourbar; **no-data/NaN cells render grey `#d9d9d9`** with a caption distinguishing no-data from zero forecast (C-190, #234); the title carries the human date + integer month id via `month_id_to_label`) — selected when `plot_map(image_fallback=True)` and `level == PGM` and `interactive=True`. Its payload is **`O(figure pixels)`**, independent of cell- and origin-count, so it renders the full global grid within the offline byte budget where the heatmap (whose animation frames are dense JSON arrays) eventually cannot. **Faithful by construction** (one cell → one pixel at its `(xcoord, ycoord)` centre: no aggregation C-189, no omission C-190 — a missing cell stays NaN/no-data, never back-filled), labelled a per-cell point summary (C-109), and carries the same coastline overlay (`_coastline_xy`, clipped to the data extent). It returns a self-contained `<img>` data-URI (offline, C-28). **Tradeoff:** a static image has **no per-cell hover** of the value — which is why the headline layer at step +1 ALSO renders as the hover heatmap (ADR-021); the PNG remains the primary product at every scale. Raises `ValueError` if `xcoord`/`ycoord` are absent.
- **Render strategies (ADR-021; ADR-016 injected).** The forecast template selects strategies at the **Compose boundary** (the Render layer never reads config): for PGM it renders **horizon steps as PNG images** (`image_fallback=True`, one month per call) plus the **raster heatmap at step +1** (`raster=True`, single month — inside the C-209 budget by construction); CM keeps the whole-horizon **choropleth**. This module keeps all three paths and their budget guards — any caller exceeding `max_cells` (choropleth) or `max_raster_cell_frames` (raster) still fails loud; the guards are backstops, no longer the tier-selection mechanism.
- **Coastline overlay source (register C-205, C-23).** `_coastline_xy()` derives a lon/lat border polyline (with `np.nan` segment separators) from the committed **Natural-Earth 110m country** shapefile (~700 KB; simplified line layer ~tens of KB) — **not** the 56 MB PRIO-GRID cell shapefile (C-23) — built lazily and cached. Used by both the raster heatmap and the PNG image; PGM-only (CM choropleths already imply coastlines via their polygons).
- **Static maps.** `_plot_static_map()` builds a single-time-period Matplotlib choropleth with log-scale normalization (`FuncNorm` using `np.log1p`/`np.expm1`).
- **Dispatch.** `plot_map()` validates the target column, dispatches to interactive or static rendering, and optionally returns HTML instead of a figure object.
- **Scale guard (fail-loud, register C-26).** `plot_map()` accepts an injected `max_cells` limit; if the number of rendered map entries (`len(mapping_dataframe)` — entities × time steps, the real size/memory driver) exceeds it, it raises a `ValueError` naming the count, the limit, and the override **before** building any Plotly/Matplotlib traces — rather than risk an out-of-memory failure or a multi-GB HTML file (the C-105/C-106 PGM-scale failure class). `max_cells` is read from `ReportingConfig.max_map_cells` at the Compose boundary (forecast template) and injected downward (ADR-016); the Render layer never reads config. `None` disables the guard. The raster path is **exempt from this choropleth `max_cells` guard** (its payload does not scale with polygon geometry — #125) but has its **own** frame-aware budget: `plot_map()` also accepts `max_raster_cell_frames` (injected from `ReportingConfig.max_raster_cell_frames`), and the raster fails loud (register C-203/C-209) if the **uniform-lattice cell-frames** (`pgm_lattice_cell_frames` — bounding-box rows × cols × time steps; each animation frame is a dense uniform-lattice array, C-208) exceed it. The quantity is the LATTICE, not `len(mapping_dataframe)`: sparse-but-spread data costs bounding-box, not data rows (C-209). Recalibrated 2026-07-15: ~34 bytes/lattice-cell-frame measured; default 2,000,000 ≈ ~70 MB. The PNG image tier is **likewise exempt** from the `max_cells` choropleth guard (its payload is O(pixels), independent of cell count). Downsampling/aggregation remains deliberately out of scope (it would change output fidelity — registered C-189/C-190); the PNG image is the delivered per-step product at every scale, with the raster as the step-+1 hover companion (ADR-021; C-205, Resolved).
- **Memory management.** Explicitly deletes intermediate DataFrames and calls `gc.collect()` after GeoJSON preparation and interactive map rendering.

---

## 4. Inputs and Assumptions

- **Constructor requires** `frame` (a `views_frames.PredictionFrame`, S == 1), `level` (`SpatialLevel.CM`/`SpatialLevel.PGM`), and `target_column` (the value column name, e.g. `pred_ged_sb_map`). An invalid `level` raises `ValueError`.
- **Shapefiles must exist** at:
  - `views_reporting/assets/shapefiles/country/ne_110m_admin_0_countries.shp` (CM level; the merge key is normalized to real ISO codes at load — C-206)
  - `views_reporting/assets/shapefiles/priogrid/priogrid_cell.shp` (PGM level)
  - Missing shapefiles cause `FileNotFoundError` from `gpd.read_file()`.
- **The frame's `SpatioTemporalIndex`** supplies the `(time, entity)` identity; the level's `index_names` name the columns of the derived mapping dataframe.
- **`views_reporting.metadata` functions** (`get_isoab_for_index`, `get_name_for_index`) must be importable (used via the `frames_to_mapping_df` adapter) and return DataFrames keyed by the `(time, entity)` MultiIndex.
- **`plot_map()`** requires `target` to be present as a column in the supplied `mapping_dataframe` (the `target_column` the module was constructed for); raises `ValueError` otherwise.
- **`plot_map()` accepts an optional `max_cells` scale limit** (injected from `ReportingConfig.max_map_cells` at the Compose boundary, ADR-016). When set and the render size (`len(mapping_dataframe)`) exceeds it, the *choropleth* render fails loud before any trace construction (C-26). `None` (the default for ad-hoc callers) disables the guard.
- **`plot_map()` accepts an optional `max_raster_cell_frames` budget** (injected from `ReportingConfig.max_raster_cell_frames`). When `raster=True` and the **uniform-lattice cell-frames** (`pgm_lattice_cell_frames`: bounding-box rows × cols × time steps — the true payload driver, C-208/C-209) exceed it, the raster fails loud — the bounded raster is not unconditionally free at globe × many-origins scale. `None` disables it.
- **`plot_map()` accepts an optional `image_fallback` flag** (default `False`; injected at the Compose boundary). When `True` and `level == PGM` and `interactive=True`, it renders the scale-flat **PNG image tier** (`_plot_image_map`, register C-205) instead of a Plotly figure — exempt from the `max_cells` choropleth guard (payload is O(pixels)). Ignored (with a warning) for non-PGM levels. Selected by the Compose boundary per ADR-021 (one PNG per horizon step).
- **`plot_map()` accepts `color_mode` (`"log_count"` default | `"unit_interval"`, #233).** Count layers (MAP, HDI bounds) keep the C-191 nonzero-anchored log scale with original-unit labels; probability layers (P(any violence)) render on a **linear 0–1 scale** (quarter ticks, probability-labelled bar) — a probability on a log-count scale misleads silently. Unknown modes raise `ValueError`; `unit_interval` on the choropleth path raises (implemented for the PGM raster/image paths only).
- **Module-level helper `pgm_lattice_cell_frames(mapping_dataframe, time_id) -> int`** is part of this module's public surface (used by the raster budget guard and the scale tests; the forecast template no longer imports it — ADR-021 removed size-driven tier selection): it returns bounding-box lattice rows × cols × distinct time steps — the raster budget quantity (C-209). Requires `xcoord`/`ycoord` columns. The private geometry/colour helpers (`_uniform_lattice`, `_lattice_indices`, `_log_color_scale`) implement the C-208 uniform lattice and the C-191 colour anchoring described in §3.
- **Static maps** require exactly one time period in the mapping dataframe; `plot_map` raises `ValueError` otherwise.

---

## 5. Outputs and Side Effects

- **`get_subset_mapping_dataframe()`** returns a `gpd.GeoDataFrame` with geometry column, ISO codes, country names, and the original target columns.
- **`plot_map(interactive=True, as_html=False)`** returns a `plotly.graph_objs.Figure`.
- **`plot_map(interactive=True, as_html=True)`** returns an HTML string containing the full Plotly figure with embedded Plotly.js.
- **`plot_map(interactive=True, image_fallback=True)`** (PGM only) returns an HTML `<img>` tag with a base64-embedded PNG — the scale-flat globe tier (C-205). This path has **no Plotly figure form**: it returns the `<img>` string regardless of `as_html` (the image is its only artifact). Set by the template for every horizon-step render (ADR-021).
- **`plot_map(interactive=False, as_html=False)`** returns a `matplotlib.figure.Figure`.
- **`plot_map(interactive=False, as_html=True)`** returns an HTML `<img>` tag with base64-embedded PNG.
- **Side effects:** Logging via the module-level `logger`. Explicit `gc.collect()` calls. Matplotlib figures are created but not closed by the caller (static maps are closed only when `as_html=True`).

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `level` is not `SpatialLevel.CM`/`PGM` | `ValueError` raised | `__init__` |
| Shapefile missing on disk | `FileNotFoundError` from `gpd.read_file` | `__get_country_shapefile` / `__get_priogrid_shapefile` |
| Target not in `dataset.targets` or `dataset.features` | `ValueError` raised | `plot_map` (target validation) |
| Render size exceeds injected `max_cells` (entities × time steps) | `ValueError` raised **before** any trace construction — an early, controlled refusal (C-26) instead of a late, uncontrolled OOM / multi-GB file. Raster + PNG-image tiers are exempt | `plot_map` (scale guard) |
| `raster=True` and the uniform-lattice cell-frames exceed `max_raster_cell_frames` | `ValueError` raised in `plot_map` BEFORE dispatch/figure construction (C-203/C-209) | `plot_map` (raster budget guard) |
| `image_fallback=True` (PGM) and `xcoord`/`ycoord` absent | `ValueError` raised — the PNG needs per-cell lattice centres | `_plot_image_map` |
| Multi-month dataframe reaches the image renderer | `ValueError` raised — month choice is a Compose-boundary decision (#232); no silent pick | `_plot_image_map` |
| Unknown `color_mode`, or `unit_interval` requested on the choropleth path | `ValueError` raised at the API boundary (#233) | `plot_map` |
| `raster=True` and `image_fallback=True` in one call | `ValueError` — mutually exclusive; setting both used to silently drop the hover heatmap | `plot_map` |
| Static plot with multiple time periods | `ValueError` raised | `plot_map` (static dispatch) |
| Target column missing or all-null (static only) | `ValueError` raised | `_plot_static_map` |
| Missing geometries after merge | Logged as warning, rows dropped silently | `__check_missing_geometries` |

The missing-geometry case is a silent data-loss scenario: rows are dropped and only logged at WARNING level. Callers receive a smaller GeoDataFrame with no programmatic signal that rows were removed.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_frames` -- `PredictionFrame`, `SpatialLevel` (data + level dispatch)
  - `views_reporting.mapping._frame_adapter` -- `frames_to_mapping_df` (the sole frame→pandas seam; see `cic_frame_mapping_adapter.md`)
  - `geopandas`, `plotly`, `matplotlib`, `numpy`, `pandas` (rendering)
- **Must not depend on:**
  - `views_reporting.statistics` (no statistical computation)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - `views_reporting.reports` (no report building)
- **Trusts:**
  - That the constructor's `PredictionFrame` is a collapsed (S == 1) frame with a well-formed `SpatioTemporalIndex` (the S > 1 case is refused at the `frames_to_mapping_df` seam — ADR-020/C-207)
  - That shapefiles bundled in `assets/shapefiles/` are correct and complete

---

## 8. Examples of Correct Usage

```python
from views_frames import SpatialLevel
from views_reporting.mapping import MappingModule

# `map_frame` is a collapsed (S == 1) views_frames.PredictionFrame
mapper = MappingModule(
    frame=map_frame, level=SpatialLevel.PGM, target_column="pred_ged_sb_map"
)

# Interactive map for multiple time steps
gdf = mapper.get_subset_mapping_dataframe(time_ids=[528, 529, 530])
html = mapper.plot_map(gdf, target="pred_ged_sb_map", interactive=True, as_html=True)

# Static map for a single time step
gdf_single = mapper.get_subset_mapping_dataframe(time_ids=528)
fig = mapper.plot_map(gdf_single, target="pred_ged_sb_map", interactive=False)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Constructing without level/target_column, or with an invalid level
mapper = MappingModule(frame=map_frame, level="country", target_column="x")  # Raises ValueError

# WRONG: Passing an UNCOLLAPSED sample frame down the render path — the
# frames_to_mapping_df seam refuses S > 1 (ADR-020/C-207); collapse with
# calculate_map_frame first

# WRONG: Static map with multiple time periods
gdf_multi = mapper.get_subset_mapping_dataframe(time_ids=[528, 529])
mapper.plot_map(gdf_multi, target='pred_ged_sb', interactive=False)  # Raises ValueError

# WRONG: Target column not present in the mapping dataframe
mapper.plot_map(gdf, target='nonexistent_column', interactive=True)  # Raises ValueError
```

---

## 10. Test Alignment

- **Green/Red:** `tests/test_mapping.py` — constructor shapefile dispatch by `SpatialLevel`; invalid-level raise; the C-26 scale guard (fires strictly above threshold, disabled by `None`).
- **Green (characterization):** `tests/test_mapping_characterization.py` drives the frame→adapter→shapefile path and pins the per-(time, entity) target values, the isoab/country_name join, and the row count — the migration behaviour proof (epic #137, #138).
- **Beige:** `tests/test_e2e_fixture.py` / `tests/test_e2e_synthetic.py` — full forecast report through real/synthetic frames.

---

## 11. Evolution Notes

### Known Deviations

1. **Silent geometry dropping.** `__check_missing_geometries()` drops rows with missing geometries and only logs a warning. There is no way for callers to detect or handle this data loss programmatically. This conflicts with a fail-loud principle.

2. ~~Unreachable `else` branch in `_prepare_base_geojson()`~~ — **RESOLVED (#138).** The dataset-type `else`/`ValueError` branch was removed when the constructor moved to `SpatialLevel` dispatch (CM/PGM exhaustive).

3. ~~`_mapping_dataframe` latent `AttributeError`~~ — **RESOLVED (#138).** `build_mapping_dataframe()` now assigns `self._mapping_dataframe` (the full-range geo-merged frame `_plot_static_map` reads for colorbar normalization). It is no longer left `None`.

4. **Name-mangled private methods.** Methods like `__get_country_shapefile`, `__check_missing_geometries` use Python's double-underscore name mangling, making subclassing and testing more difficult than necessary. (`__init_mapping_dataframe`/`__add_isoab` were replaced by `build_mapping_dataframe` + the `frames_to_mapping_df` adapter in #138.)

5. **No input validation on `time_ids`/`entity_ids` in `get_subset_mapping_dataframe()`.** Invalid IDs are passed through to `dataset.get_subset_dataframe()`, which may raise opaque errors.

### Stability

- The dual-rendering architecture (Plotly interactive / Matplotlib static) is stable.
- The shapefile loading and geometry simplification pipeline is stable.
- The log-scale coloring strategy (`np.log1p`) is stable and consistent across both renderers.

### Expected Changes

- The `_mapping_dataframe` issue (item 3 above) needs to be resolved.
- CDN-based Plotly.js dependency in HTML output may need to be reconsidered for offline use.

---

## End of Contract

This document defines the **intended meaning** of `MappingModule`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
