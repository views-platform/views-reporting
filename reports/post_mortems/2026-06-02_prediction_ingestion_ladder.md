# Post-Mortem: Prediction Data Ingestion Ladder

**Date:** 2026-06-02
**Period:** 2026-06-01 to 2026-06-02 (2 days)
**Author:** Simon + Claude Code
**Scope:** End-to-end testing, loaders package, template integration, fixture data, ADR-012

---

## 1. Executive Summary

views-reporting was extracted from pipeline-core a week earlier with 161 unit tests proving individual components work. But nobody had tested whether the full pipeline — from prediction data through statistics, mapping, visualization, to an HTML report — actually produced a working report. The answer was: "I have no idea if it works."

This effort set out to answer that question. It progressed from synthetic E2E tests through real fixture data from four baseline models to a complete format-agnostic loader layer, and culminated in generating real forecast and evaluation reports from both parquet and numpy prediction formats.

**Final state:** 229 tests, loaders package with declared-format dispatch, real reports generated from 4 models across both CM and PGM levels, both point and 256-sample estimates.

---

## 2. What Was Done

### Phase A — Can we generate a report at all?

Built synthetic E2E tests using fabricated DataFrames to prove the integration seams work:
- `calculate_map()` → `ReportModule` → HTML export
- `ForecastReportTemplate.generate()` full pipeline (maps + line graphs)
- `HistoricalLineGraph` → Plotly HTML → embedded in report

**Key finding:** Fake ISO codes crash `MappingModule` — it silently drops rows with unmatchable geometries, then crashes on the empty result. Tests must use real ISO codes from the bundled shapefile.

### Phase B — Real data fixtures

Ran four models on the calibration partition (train 121-444, test 445-492, 13 rolling origins each):

| Model | Level | Format | Samples | Size |
|-------|-------|--------|---------|------|
| average_cmbaseline | cm | parquet DataFrame | 1 (point) | 196 KB |
| average_pgmbaseline | pgm | parquet DataFrame | 1 (point) | 20 MB |
| red_ranger | cm | numpy PredictionFrame | 256 | 89 MB |
| blue_ranger | pgm | numpy PredictionFrame | 256 | 6 GB (not in repo) |

**Key finding:** Both ranger models produce **numpy PredictionFrame** natively, not parquets with array-valued cells. The parquet-with-arrays format (originally envisioned as "Rung 3") was a transitional chimera the pipeline already moved past. This collapsed the planned 5-rung ladder to 2 real formats.

### Phase C — Loaders package

Built `views_reporting/loaders/` with SOLID registry-based format dispatch:
- `_protocol.py` — `PredictionLoader` protocol
- `_registry.py` — format → loader dispatch (fail-loud on unknown format)
- `_constants.py` — shared `DATASET_CLASSES` and `INDEX_NAMES`
- `dataframe_loader.py` — parquet → `CMDataset`/`PGMDataset`
- `prediction_frame_loader.py` — numpy → `CMDataset`/`PGMDataset`
- Public API: `load_predictions()`, `load_prediction_sequence()`

**Key finding:** `PredictionFrameConverter.to_prediction_df()` returns a DataFrame with `index.names = [None, None]`. The loader must explicitly `set_names(["month_id", "country_id"])` — a seam that would have caused silent failures if not caught during testing.

### Phase D — Template integration

Modified both report templates to accept loader-based input:
- `ForecastReportTemplate.generate()` — new `prediction_format` + `prediction_path` parameters as alternative to `forecast_dataframe`
- `EvaluationReportTemplate._add_prediction_sample_graphs()` — format-aware discovery and loading
- Input validation: both inputs raises, neither raises, path without format raises

Wrote ADR-012 documenting the declared-format dispatch decision.

### Phase E — Real reports

Generated 8 real reports (4 forecast + 4 evaluation) from the fixture models:
- Forecast reports with interactive Plotly choropleth maps, time sliders, and historical overlay line graphs
- Evaluation reports with WandB metric tables and run metadata
- CM reports: 12-13 MB with 165 country polygons
- PGM reports: 86 MB with ~13,000 grid cell polygons

---

## 3. Why It Was Done

The extraction postmortem noted that views-reporting had "excellent governance" (12 ADRs, 10 CICs, 161 tests) but no proof that the actual reporting pipeline worked end to end. The tests proved individual components (PDA, ForecastReconciler, ReportModule, MappingModule) work in isolation. Nothing tested whether they work together.

Additionally, the pipeline is migrating from DataFrame to PredictionFrame storage. views-reporting could only read parquets. Models producing numpy predictions (the future default) could not generate reports.

---

## 4. How It Was Done

### Approach: Scaffold → Real Data → Formalize

1. **Synthetic tests first** — proved integration seams work with fabricated data, no external dependencies
2. **Real fixture data** — ran actual models, copied outputs, proved the pipeline works on production-shaped data
3. **Formalized into loaders** — extracted the proven loading patterns into a proper package with protocol, registry, and tests
4. **Wired into templates** — made the templates format-agnostic via the loaders
5. **Generated real reports** — validated visually that the output is correct

This order was critical. Writing the loaders first (without proven patterns to extract) would have been speculative architecture. Writing the tests against real data first, then extracting the patterns, produced a loaders package that is provably correct.

### Test-driven throughout

Every phase was gated by passing tests:
- Synthetic E2E tests before fixture data
- Fixture E2E tests before loaders
- Loader unit tests before template integration
- Template integration tests before the final merge

### Issue tracking

15 GitHub issues (#52-#66) organized by phase. Each issue had clear acceptance criteria. Issues were closed as the work landed, with comments documenting any scope changes (e.g., the 5-rung → 2-format simplification).

---

## 5. What Worked

### The "try it with real data" instinct

The user's question — "I have no idea if it works. How do I check?" — was the most valuable input of the entire effort. Answering it with real data, not more unit tests, revealed integration issues that no amount of component testing would have found.

### Simplification from 5 rungs to 2 formats

The initial plan had 5 rungs. Running the actual models revealed that the pipeline had already moved past the intermediate format (parquet with array cells). Dropping 3 rungs saved significant wasted effort and produced a cleaner architecture.

### WET-before-DRY for loaders

The loading logic was first inlined in test helpers (`_load_parquet_origin()`, `_load_pf_origin()`), proven correct against real data, then extracted into the loaders package. The extraction was mechanical — no guessing about what the API should look like.

### Fixture data strategy

Not committing the data to git but providing a `tests/data/README.md` with exact copy instructions struck the right balance. Tests skip when data is absent (CI), run when present (developer machines). No bloated repo, no CI brittleness.

---

## 6. What Didn't Work

### Initial mock-heavy approach

The first report attempt used mocked `get_isoab()` and `get_name()` with fake ISO codes (`X01`, `X02`). The report rendered but looked completely wrong — only 10 countries colored, the rest blank. The mocks were correct for unit testing but produced misleading visual output. Generating real reports required real viewser metadata.

### PGM fixture size

blue_ranger's prediction data is 6 GB (13,110 grid cells × 256 samples × 13 origins × float32). Too large to copy into the repo. Tests for PGM sample estimates discover the data from views-models instead. This creates an asymmetry: CM sample tests are self-contained, PGM sample tests depend on views-models being present.

### PR scope drift

PR #67 started as "docs: prediction ingestion roadmap and issue backlog" (planning only) but grew to include the full loaders package, fixture E2E tests, and template integration. The PR title and body had to be updated mid-flight. Starting with a planning PR and pivoting to implementation on the same branch made the commit history coherent but the PR description stale.

---

## 7. Lessons Learned

### Visual validation matters

229 passing tests and a clean lint run don't prove the reports look right. Opening the HTML in a browser and seeing the choropleth map with real country boundaries, the time slider working, and the line graphs showing actual conflict data — that's the real test. The test suite proves the pipeline doesn't crash. Visual inspection proves it produces something useful.

### viewser is a hidden dependency

The metadata layer (`entity_metadata.py`) makes network calls to the VIEWSER database for static geographic data (ISO codes, country names, grid coordinates). This makes report generation impossible without network access. Issue #70 tracks this — the data could be bundled locally.

### Format migration is further along than expected

Both ranger models already produce numpy PredictionFrame natively. The transition period where both formats coexist is happening now. The loaders package arrived just in time — without it, no PredictionFrame model could generate a report through the pipeline.

### The loader protocol paid for itself immediately

When building the template integration, having `load_predictions(format, path, level, targets)` as a single entry point meant the template code doesn't branch on format at all — it calls one function and gets a Dataset back. The format dispatch is invisible to the consumer. This is exactly what DIP is for.

---

## 8. Impact Assessment

### By the numbers

| Metric | Before | After |
|--------|--------|-------|
| Tests | 194 | 229 |
| E2E tests | 0 | 18 (5 synthetic + 13 fixture) |
| Loader tests | 0 | 20 |
| Source LOC | ~7,300 | ~7,600 |
| Test LOC | ~2,600 | ~3,400 |
| Subpackages | 9 | 10 (added loaders/) |
| ADRs | 12 | 13 (added ADR-012) |
| Prediction formats supported | 1 (parquet) | 2 (parquet + numpy) |
| Real reports generated | 0 | 8 (4 forecast + 4 evaluation) |

### Confidence level

Before this effort: "I have no idea if it works."
After: Real reports from 4 models, both spatial levels, both estimation types, generated and visually validated.

### Open items

| Item | Status |
|------|--------|
| #64 | ReportingStage update in pipeline-core — cross-repo, message sent, approach confirmed |
| #70 | viewser dependency tracking — documented, not yet acted on |
| PGM fixture size | blue_ranger data stays in views-models (6 GB) |
| Evaluation report prediction graphs | Not rendered in demo (need ModelPathManager pointing to real prediction files) |
