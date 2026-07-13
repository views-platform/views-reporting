
# Class Intent Contract: frames_to_mapping_df (frame → mapping adapter)

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-002 (Topology — Rendering edge), ADR-006 (Intent Contracts), ADR-018 (frames as the data contract)

---

> **Scope note.** This contract covers a single module-level function,
> `frames_to_mapping_df`, in `views_reporting/mapping/_frame_adapter.py`. It is
> the **sole** `views_frames.PredictionFrame` → pandas seam on the mapping path
> (epic #137, #138). It is included because it is the architectural chokepoint
> the heavy geopandas/Plotly mapping logic sits behind.

---

## 1. Purpose

> Convert a single (collapsed) `PredictionFrame` into the flat
> `[time_id, entity_id, target_column, isoab, country_name]` DataFrame that
> `MappingModule` merges with the shapefile.

It reproduces, frame-side, exactly what `MappingModule.__add_isoab` used to build
from a pipeline-core dataset: the value column plus the ISO code and country-name
join columns, keyed on the level's `(time, entity)` identifiers.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** merge geometry / read shapefiles — `MappingModule` owns that.
- Does **not** compute MAP/HDI or collapse samples — it reads `frame.values[:, 0]`
  and **enforces** S == 1 (register C-207, ADR-020): a sample frame raises
  `ValueError` naming `calculate_map_frame` as the remedy. Pre-guard, an
  uncollapsed frame silently rendered posterior draw #0 (probe-confirmed).
- Does **not** fetch metadata itself — it delegates to the index-keyed accessors
  `get_isoab_for_index` / `get_name_for_index` (which own the viewser fetch).
- Does **not** filter rows — subsetting is `MappingModule.get_subset_mapping_dataframe`'s job.

---

## 3. Responsibilities and Guarantees

- **Flat table from the frame index.** Builds the base DataFrame from
  `frame.index.time` / `frame.index.unit` per-row (so a sparse grid is preserved,
  no from-product densification) and `frame.values[:, 0]` as `target_column`,
  cast to float32.
- **Metadata join.** Left-joins `isoab` (via `get_isoab_for_index`) and
  `country_name` (via `get_name_for_index(..., with_id=True)`, renamed from
  `name`) on `[time_id, entity_id]`. Left join preserves all frame rows.
- **Level-keyed naming.** Uses `level.index_names` for the time/entity column
  names (`month_id` + `country_id`/`priogrid_id`).

---

## 4. Inputs and Assumptions

- `frame` — a `views_frames.PredictionFrame`, S == 1 (point estimate / MAP) — **enforced guarantee**, not an expectation: S > 1 raises (C-207, ADR-020).
- `target_column` — the value column name (e.g. `pred_ged_sb_map`).
- `level` — `SpatialLevel.CM` or `SpatialLevel.PGM`.
- Assumes `frame.index` has unique `(time, entity)` rows so the metadata join is 1:1.

---

## 5. Outputs and Side Effects

- **Output:** a flat `pd.DataFrame` with columns
  `[time_id, entity_id, target_column, isoab, country_name]`. Deterministic given
  the frame and the (cached) metadata.
- **Side effects:** none beyond the first viewser metadata fetch performed inside
  the index accessors (memoised level-keyed cache).

---

## 6. Failure Modes and Loudness

| Condition | Behavior |
|---|---|
| Metadata accessor cannot reach viewser | Raises from `get_*_for_index` (loud) |
| Frame value array not 2-D / empty | Raises from numpy indexing (loud) |
| Missing entities in metadata | Left join yields NaN isoab/country_name (downstream geometry drop) |

---

## 7. Boundaries and Interactions

- **Depends on:** `views_frames` (`PredictionFrame`, `SpatialLevel`),
  `views_reporting.metadata` (`get_isoab_for_index`, `get_name_for_index`),
  `numpy`, `pandas`.
- **Consumed by:** `MappingModule.build_mapping_dataframe`.
- **Must not depend on:** pipeline-core datasets, Computation, Composition.

---

## 8. Examples of Correct Usage

```python
from views_frames import SpatialLevel
from views_reporting.mapping._frame_adapter import frames_to_mapping_df

flat = frames_to_mapping_df(map_frame, "pred_ged_sb_map", SpatialLevel.CM)
assert {"month_id", "country_id", "pred_ged_sb_map", "isoab", "country_name"} <= set(flat.columns)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: passing a multi-sample frame — raises ValueError (C-207, ADR-020;
# pre-guard it silently read column 0 = posterior draw #0). Collapse first:
# calculate_map_frame(sample_frame, target).
frames_to_mapping_df(sample_frame, "pred_ged_sb", SpatialLevel.CM)
```

---

## 10. Test Alignment

- **Green (characterization):** `tests/test_mapping_characterization.py` drives
  the full frame→adapter→shapefile path and pins the per-(time, entity) target
  values + isoab/country_name join + row count (the migration behaviour proof).
- **Green:** `tests/test_statistics.py::TestFrameMapHdiSparseGrid` pins per-row
  (sparse) index reassembly upstream of this adapter.

---

## 11. Evolution Notes

- This is the one place the mapping path touches pandas/geopandas (ADR-018
  array-authoritative / pandas-at-the-edge). New geo-renderers should consume the
  same flat shape so the seam stays single.

---

## End of Contract

This document defines the **intended meaning** of `frames_to_mapping_df`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
