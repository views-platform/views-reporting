
# Class Intent Contract: ForecastReportTemplate

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-07-18 (governance-drift round; frames-native rewrite)
**Related ADRs:** ADR-003 (declarations over inference), ADR-008 (fail-loud), ADR-011 (data on measurement scale), ADR-012 (prediction ingestion), ADR-016 (config injected at the Compose boundary), ADR-018 (render from given data + the render-ladder addendum), ADR-019 (tower estimators), ADR-020 (sample boundary)

---

## 1. Purpose

> **What is this class for?**

ForecastReportTemplate is the Layer-5 **Composition** class for forecast reports: it turns given
prediction data into a self-contained, offline HTML artifact — one interactive geographic map per
target (via the three-tier PGM render ladder) and, for country-level (CM) data, historical-vs-
forecast line graphs with HDI bands. It accepts predictions either as a pre-loaded DataFrame or
as a declared-format path dispatched through the loaders package (ADR-012), and it is the ONLY
place on the forecast path that reads `ReportingConfig` (ADR-016): every budget and level is
decided here and injected downward into size-agnostic Render-layer classes.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** compute evaluation metrics (use `EvaluationReportTemplate`).
- Does **not** contact any service at render time — no WandB, no viewser, no network (ADR-018).
- Does **not** load from disk when given a DataFrame; with `prediction_path` it delegates to
  `views_reporting.loaders.load_predictions()` (ADR-012).
- Does **not** pass raw posterior samples to the Render layer: sample frames are collapsed to a
  point summary (tower MAP) at this boundary before any pandas seam (ADR-020).
- Does **not** produce anything but HTML (via `ReportModule`); does not train, calibrate, or
  reconcile; does not validate forecast correctness beyond the ingestion conformance gate.

---

## 3. Responsibilities and Guarantees

- **Ingestion.** Predictions become conformance-gated `views_frames.PredictionFrame`s: either
  `frames_from_dataframe(forecast_dataframe, level, targets)` or
  `load_predictions(prediction_format, prediction_path, level, targets)` (ADR-012/ADR-009 §1b).
- **Sample collapse (ADR-019/ADR-020).** When a target's frame `is_sample`, it is collapsed via
  `calculate_map_frame` (the views-frames tower) and re-wrapped as an S == 1 frame
  (`_map_frame_from_df`) before `MappingModule` sees it. The MAP column is `pred_{target}_map`.
- **The render-strategy ladder (ADR-018 addendum; register C-26/C-205/C-208/C-209).** For PGM,
  the tier is chosen HERE from the size of the given data and injected into `plot_map`:
  choropleth (small grids + all CM) → bounded raster heatmap (PGM past
  `ReportingConfig.max_map_cells`; hover-capable, primary) → scale-flat PNG image
  (`image_fallback=True`, PGM past `ReportingConfig.max_raster_cell_frames`). The heatmap→PNG
  quantity is `pgm_lattice_cell_frames(subset, time_id)` — the UNIFORM bounding-box lattice ×
  time-frames, the true raster payload driver (C-209) — falling back to `len(subset)` only when
  coord columns are absent (the raster path then fails loud on the missing coords itself). Each
  escalation is logged. Injected to `plot_map`: `max_cells`, `raster`, `max_raster_cell_frames`,
  `image_fallback`.
- **Historical overlay (CM only).** Gated on `level == SpatialLevel.CM`: renders
  `HistoricalLineGraph.plot_predictions_vs_historical` with `alpha=config.default_hdi_level`,
  `hdi_levels=config.hdi_levels`, and `run_type` (partition caption). PGM has no line graphs.
- **Provenance footer (register C-34/C-112).** Always stamps model/target/run_type/level/targets/
  prediction_path and **`metadata_snapshot`** (the bundled entity-metadata snapshot date via
  `metadata_snapshot_date()`) so staleness is observable in every artifact.
- **HTML export.** Delegates to `ReportModule.export_as_html()`; returns the output `Path`.
- **Closure pattern.** The core logic lives in a nested `_create_report()` inside `generate()` —
  a structural choice, not accidental.

---

## 4. Inputs and Assumptions

- **Constructor:** `config` (Dict with `"level"` ∈ {"cm","pgm"} and `"targets"` list),
  `model_path` (`ModelPathManager`: `.target`, `.model_name`, `.reports`), `run_type` (str).
- **`generate()` (exactly one prediction source, ADR-003):** `forecast_dataframe` XOR
  (`prediction_format` + `prediction_path`); both → `ValueError`; neither → `ValueError`;
  `prediction_path` without `prediction_format` → `ValueError`. Optional
  `historical_dataframe` feeds the CM overlay's historical side.
- **ADR-011:** values are on their declared measurement scale and rendered as-is; the tower MAP
  preserves scale.
- Ingested frames must pass the loaders' conformance gate (`assert_conformant`, pinned
  `CONFORMANCE_FLOOR`); a wholly-NaN values axis fails loud there (C-111 values-half).

---

## 5. Outputs and Side Effects

- Returns the `Path` `model_path.reports / f"report_{generate_model_file_name(...)}.html"`;
  writes that one file. Fully offline artifact (C-28).
- `tqdm` progress bar over targets; info logs for sample collapse and each ladder escalation.
- No mutation of inputs, config, or model_path.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `config["level"]` not "cm"/"pgm" | `ValueError` | `generate` (level resolution) |
| Both / neither prediction sources; path without format | `ValueError` (ADR-003) | `_create_report` input dispatch |
| `config["targets"]` missing | `KeyError` | target iteration |
| Target absent from the loaded frames | Warning logged, map skipped (visible degradation) | `_create_report` target loop |
| Ingested frame fails conformance / wholly-NaN values | `ValueError` from the loaders' gate | `loaders/_constants.assert_conformant` |
| PGM choropleth over `max_cells`; raster lattice over `max_raster_cell_frames` at the guard | `ValueError` from `plot_map` (ADR-008) — the ladder normally escalates first | `MappingModule.plot_map` |
| `MappingModule`/`HistoricalLineGraph` raise otherwise | Unhandled — propagates | `_create_report` |

Unlike `EvaluationReportTemplate`, **nothing here is wrapped in try/except** — failures
propagate. There is no non-fatal subsystem.

---

## 7. Boundaries and Interactions

- **Depends on:** `views_reporting.loaders` (`frames_from_dataframe`, `load_predictions`,
  `target_frame_from_dataframe`), `views_reporting.statistics.calculate_map_frame` (tower),
  `views_reporting.mapping` (`MappingModule`, `pgm_lattice_cell_frames`),
  `views_reporting.visualizations.HistoricalLineGraph`, `views_reporting.reports.ReportModule`,
  `views_reporting.metadata.entity_metadata.metadata_snapshot_date`,
  `views_reporting.config.get_config` (the Compose-boundary read, ADR-016),
  `views_frames` (`PredictionFrame`, `SpatialLevel`, `SpatioTemporalIndex`),
  `views_pipeline_core.files.utils.generate_model_file_name`,
  `views_pipeline_core.managers.model.ModelPathManager` (public surfaces only), `pandas`, `tqdm`.
- **Must not depend on:** any service reached at render time (ADR-018); pipeline-core private
  dataset internals (C-114, grep-guarded); `wandb`/`viewser`.
- **Trusts:** `plot_map` renders faithfully within its guards; `calculate_map_frame` returns the
  tower point summary; the loaders' conformance gate has run.

---

## 8. Examples of Correct Usage

```python
from views_pipeline_core.managers.model import ModelPathManager
from views_reporting.templates.reports.forecast import ForecastReportTemplate

template = ForecastReportTemplate(
    config={"level": "cm", "targets": ["ged_sb"]},
    model_path=ModelPathManager("my_model"),
    run_type="forecasting",
)

# pre-loaded DataFrame (samples allowed — collapsed at this boundary)
report_path = template.generate(
    forecast_dataframe=forecast_df, historical_dataframe=historical_df
)

# declared-format path (ADR-012 loader dispatch)
report_path = template.generate(
    prediction_format="prediction_frame", prediction_path=origin_dir
)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: both prediction sources — ValueError (ADR-003)
template.generate(forecast_dataframe=df, prediction_path=p, prediction_format="dataframe")

# WRONG: invalid level — ValueError at generate()
ForecastReportTemplate(config={"level": "cy", "targets": ["ged_sb"]}, ...)

# WRONG: bypassing this boundary and handing a raw S>1 frame straight to
# MappingModule/frames_to_mapping_df — the seam refuses (ADR-020, C-207).
# Collapse happens HERE, via calculate_map_frame.
```

---

## 10. Test Alignment

Directly exercised by: `tests/test_forecast_raster_select.py` (the full ladder: tier selection,
escalation logging, lattice quantity), `tests/test_e2e_synthetic.py` +
`tests/test_e2e_fixture.py` + `tests/test_e2e_golden.py` (end-to-end generation incl. the
provenance footer and `metadata_snapshot`), `tests/test_falsify_uniform_lattice_fix.py` and
`tests/test_sample_scale.py` (the guards this template's decisions feed). Component behaviour
(maps, graphs, tower) is covered in the component suites.

---

## 11. Evolution Notes

### Known Deviations
1. **Closure pattern** for `_create_report()` — stands; makes subclassing awkward.
2. **Asymmetric error handling vs. `EvaluationReportTemplate`** — deliberate: forecast rendering
   has no sanctioned degraded mode beyond the per-target skip; eval degrades visibly per section.
3. **`tqdm` in a library class** — CLI-appropriate; noisy in pipelines/notebooks.

### Stability
- The `generate()` signature, the XOR input contract, and the ladder decision quantities are
  stable contracts. Ladder budgets are `ReportingConfig` fields (recalibration is a config
  change, not a template change).

### Expected Changes
- Global-coverage data will re-exercise the ladder's PNG tier end-to-end (currently canary-pinned
  at synthetic scale).

---

## End of Contract

This document defines the **intended meaning** of `ForecastReportTemplate`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
