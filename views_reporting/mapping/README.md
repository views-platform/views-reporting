# Mapping (views-reporting, Layer 4 — Rendering)

Geographic rendering for `views_frames.PredictionFrame` data at CM (country)
and PGM (PRIO-GRID) resolution.

> **The contracts live in the CICs, not here** — this README is a signpost only
> (parallel API docs drift; see register C-210). Authoritative:
> `documentation/CICs/cic_mapping_module.md` and
> `documentation/CICs/cic_frame_mapping_adapter.md`.

## What renders

`MappingModule(frame, level, target_column)` — constructed with a **collapsed
(S == 1)** frame — renders via `plot_map(...)` one of three tiers, chosen at the
Compose boundary (the forecast template) and injected down (ADR-016/018):

1. **Choropleth** (vector polygons) — small PGM grids + all CM. Guarded by
   `max_cells` (C-26).
2. **Raster heatmap** (`go.Heatmap` on the **uniform 0.5° lattice**, C-208) —
   hover carries value + cell id; coastline overlay (C-205); budget keyed to
   `pgm_lattice_cell_frames` — bounding-box lattice × time-frames (C-209).
3. **PNG image** (`image_fallback=True`) — the scale-flat globe tier, O(pixels).

Colour on all tiers: log1p-scaled, anchored on the **nonzero** tail with the
top of the bar always labelled (C-191).

## The seam

`frames_to_mapping_df(frame, target_column, level)` is the **sole**
frame→pandas crossing on the mapping path; it **refuses S > 1** (ADR-020,
C-207) — collapse with `calculate_map_frame` first. Identity columns
(`isoab`, `country_name`) come from the bundled metadata accessors (C-22).

Tests: `tests/test_mapping*.py`, `tests/test_global_scale.py`,
`tests/test_sample_scale.py`, `tests/test_falsify_uniform_lattice_fix.py`,
`tests/test_colorbar_anchor.py`.
