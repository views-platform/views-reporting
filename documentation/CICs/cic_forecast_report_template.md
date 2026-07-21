
# Class Intent Contract: ForecastReportTemplate

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-07-18 (governance-drift round; frames-native rewrite)
**Related ADRs:** ADR-003 (declarations over inference), ADR-008 (fail-loud), ADR-011 (data on measurement scale), ADR-012 (prediction ingestion), ADR-016 (config injected at the Compose boundary), ADR-018 (render from given data + the render-ladder addendum), ADR-019 (tower estimators), ADR-020 (sample boundary), ADR-021 (global PGM image tier primary; layer + horizon-step standard)

---

## 1. Purpose

> **What is this class for?**

ForecastReportTemplate is the Layer-5 **Composition** class for forecast reports: it turns given
prediction data into a self-contained, offline HTML artifact — one interactive geographic map per
target (PGM: horizon-step PNGs + a hover heatmap at step +1, per summary layer — ADR-021; CM: whole-horizon choropleth) and, for country-level (CM) data, historical-vs-
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

- **Ingestion — STREAMING (ADR-012/ADR-009 §1b; C-212).** Path inputs stream one target at a
  time via `iter_predictions(prediction_format, prediction_path, level, targets)`: each
  target's samples are collapsed to ALL its summary layers and released before the next
  target loads, so peak memory is ~one target's samples (the S=1000 discipline, #235).
  DataFrame inputs use `frames_from_dataframe` (the caller's df already holds every target).
  Targets absent from the source are warned about after the stream completes.
- **Summary-layer collapse (ADR-019/ADR-020/ADR-021; #233).** When a target's frame
  `is_sample`, it collapses into S == 1 layer frames through `_map_frame_from_df`: **MAP**
  (`calculate_map_frame`, headline) and — PGM only — **P(any violence)**
  (`calculate_exceedance_frame`) plus the **upper 90%/95% HDI bounds** (`calculate_hdi_frame`,
  upper column). Columns: `pred_{target}_map`, `_p_any`, `_hdi90_upper`, `_hdi95_upper`;
  headings use human layer labels. CM renders MAP only (its line graph carries HDI).
- **The render strategy (ADR-021; register C-26/C-205/C-208/C-209).** PGM renders **horizon
  steps** +1/+6/+12/+24/+36 (clamped to the horizon) — month choice is explicit HERE via
  `get_subset_mapping_dataframe(time_ids=[month])`, one month per render: each step as a PNG
  (`image_fallback=True`, content-sized embed) per layer, and the headline layer at step +1
  additionally as the hover heatmap (`raster=True`; a single global month fits the C-209
  budget by construction). CM keeps the whole-horizon choropleth. Budgets stay injected to
  `plot_map` (`max_cells`, `max_raster_cell_frames`) as fail-loud backstops; each layer's
  `color_mode` is injected per its quantity (probability layers: `unit_interval`).
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
- `tqdm` progress bar over streamed targets; info logs for the layer collapse and the step/layer render plan.
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
| PGM choropleth over `max_cells`; raster lattice over `max_raster_cell_frames` at the guard | `ValueError` from `plot_map` (ADR-008) — backstop budgets; the ADR-021 strategy stays inside them by construction | `MappingModule.plot_map` |
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

Directly exercised by: `tests/test_forecast_raster_select.py` (the ADR-021 strategy: step/layer
call pattern, colour-mode routing, human headings, CM unchanged), `tests/test_memory_bounds.py`
(the C-212 collapse bound), `tests/test_loaders.py` (streaming laziness),
`tests/test_exceedance.py` (the P(any) laws), `tests/test_e2e_synthetic.py` +
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
- The `generate()` signature, the XOR input contract, and the ADR-021 step/layer strategy are
  stable contracts. Ladder budgets are `ReportingConfig` fields (recalibration is a config
  change, not a template change).

### Expected Changes
- ~~Global-coverage data will re-exercise the ladder's PNG tier end-to-end~~ — **DONE (epic #230):** the image tier is the primary PGM product (ADR-021), exercised on the real global ensemble (currently canary-pinned
  at synthetic scale).

---

## End of Contract

This document defines the **intended meaning** of `ForecastReportTemplate`.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
