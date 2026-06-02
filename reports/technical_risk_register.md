# Technical Risk Register

**Last updated:** 2026-06-02
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 29 concerns (21 resolved, 8 open) + 5 disagreements (2 resolved)

---

## Tier Definitions

| Tier | Severity | Criteria |
|------|----------|----------|
| 1 | Critical | Silent data corruption or model output incorrectness. No error signal. Requires immediate attention. |
| 2 | High | Structural fragility that will cause failures under realistic change scenarios. Clear trigger exists. |
| 3 | Medium | Maintainability or coupling issues that increase cost of change. Multiple developers affected. |
| 4 | Low | Code quality observations. Single-developer scope. No correctness or reliability impact. |

---

## Open Concerns

### C-22: VIEWSER runtime dependency for entity metadata

| Field | Value |
|-------|-------|
| ID | C-22 |
| Tier | 2 |
| Source | external-review (datafactory migration assessment) |
| Trigger | When VIEWSER is retired/decommissioned, or when a report is generated in an environment without VIEWSER DB access (no SSH/VPN to the PRIO PostgreSQL) |
| Location | `views_reporting/metadata/entity_metadata.py:45` (pg_metadata Queryset), `:335` (country_metadata Queryset) |
| Narrative | `entity_metadata.py` issues live `Queryset(...).publish().fetch()` calls to VIEWSER at runtime to obtain lat/lon, gwcode, isoab, isonum, country name, capname/caplat/caplong, row/col, in_africa/in_me. Every one of these fields is static geographic reference data, derivable from the PRIO-GRID definition or available as a datafactory feature. This is the last significant VIEWSER runtime dependency in the visualization chain. When VIEWSER is retired (the same retirement driving the UNFAO migration), report generation breaks. Remediation: replace the Querysets with a bundled static lookup table (~2 MB parquet: pgid → lat/lon/row/col/iso3/name/gwcode) or a datafactory-sourced feature requested via `load_dataset()`. Subtlety: mapping joins on `isoab` (ISO alpha-3) against the Natural Earth shapefile `ADM0_A3` field; the factory provides `iso3_code` from GAUL — verify these are identical values before swapping. Tracked as GitHub issue #70. Note the metadata module splits by consumer: display-label functions (`get_isoab`, `get_name`) serve mapping/visualization and stay in this repo; spatial-mapping functions (`build_country_to_grids_cache`, `get_subset_by_country_id`) serve reconciliation and would leave with it (see C-24 cross-ref). |
| Cross-refs | GitHub #70 (viewser tracking); C-24 (reconciliation placement affects which metadata functions stay) |

### C-23: 56 MB PRIO-GRID shapefile committed directly to git (not LFS)

| Field | Value |
|-------|-------|
| ID | C-23 |
| Tier | 3 |
| Source | external-review (datafactory migration assessment) |
| Trigger | When a new developer or CI runner clones the repo, or when the repo is mirrored/forked — every clone pulls 56 MB of binary geodata regardless of whether priogrid maps are ever rendered |
| Location | `views_reporting/assets/shapefiles/priogrid/priogrid_cell.shp` (34 MB), `.dbf` (20 MB) |
| Narrative | The PRIO-GRID cell polygon shapefile (~260K polygons) is committed as raw binary to git (`git check-attr` confirms `filter: unspecified` — not LFS). views-postprocessing carries the same file via git-lfs (~35 MB). The polygons are genuinely needed for choropleth cell rendering, so the file is correct for the job — but it does not belong in raw git history. Remediation: git-lfs (matches views-postprocessing's approach, simplest) or download-on-first-use from a shared asset store. The country shapefile (Natural Earth 110m, ~700 KB) is small enough to leave as-is. |
| Cross-refs | — |

### C-24: torch (~2 GB) dependency coupled to reconciliation living in a reporting repo

| Field | Value |
|-------|-------|
| ID | C-24 |
| Tier | 3 |
| Source | external-review (datafactory migration assessment) |
| Trigger | When `pip install views-reporting` is run in any environment that only needs reports/maps (not reconciliation) — it pulls PyTorch (~2 GB) for proportional scaling math that is, at core, per-country divide-by-sum then multiply-by-total |
| Location | `views_reporting/statistics/statistics.py:439` (ForecastReconciler, torch device), `views_reporting/reconciliation/reconciliation.py`, `views_reporting/reconciliation/dataset_export.py` |
| Narrative | `ForecastReconciler` uses torch (GPU-capable) for proportional reconciliation. The dependency is heavy relative to the arithmetic it performs. The external review flags this but defers it; the resolution is not standalone tuning — it is the reconciliation-placement question. torch lives in views-reporting *only because reconciliation lives here*. If reconciliation moves to views-postprocessing (GitHub #72 / views-postprocessing#3), torch leaves views-reporting entirely and this concern dissolves. Do not optimize the torch path in place; resolve via the reconciliation move. |
| Cross-refs | GitHub #72 (reconciliation → views-postprocessing); D-08, D-09 (reconciliation design debates) |

### C-25: DatasetTransformationModule is 1,501 lines of legacy with zero live consumers

| Field | Value |
|-------|-------|
| ID | C-25 |
| Tier | 4 |
| Source | external-review (datafactory migration assessment) + consumer verification |
| Trigger | When a developer next opens `transformations.py` to modify or extend it, or when auditing the polars dependency — they will spend effort understanding 1,501 lines of log-transform machinery that nothing calls |
| Location | `views_reporting/transformations/transformations.py` (1,501 LOC) |
| Narrative | `DatasetTransformationModule` manages ln/lx/lr log-transform lifecycle with column-name tracking. It is labelled legacy per ADR-011 (this repo expects original-scale data; transform inference was retired). Consumer check confirms **zero live callers**: the only references are its own `__init__.py` re-export and the pipeline-core forwarding shim — no production code in either repo invokes it. It is also the sole consumer of the `polars` dependency (the external review's separate "polars in one module" observation rides on this entry — kill the module and polars goes with it). Candidate for outright deletion rather than maintenance. Before deleting: confirm no downstream model repo imports it via the pipeline-core shim, then remove the module, the shim, and the polars dependency together. |
| Cross-refs | ADR-011 (data on original measurement scale); C-10 (retired prefix convention) |

### C-26: No scale guard — full global PGM rendering may OOM or produce multi-GB reports

| Field | Value |
|-------|-------|
| ID | C-26 |
| Tier | 2 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When a forecast report is generated for a full global PRIO-GRID-month model (all ~260K cells, multi-target, multi-origin) rather than the Africa+Middle East subset, or when a PGM evaluation report renders many origins |
| Location | `views_reporting/mapping/mapping.py` (no entity-count guard before building Plotly traces); demonstrated: a single-origin PGM demo report is already ~86 MB |
| Narrative | The original extraction from pipeline-core was driven in part by PGM-scale rendering failures (172K Plotly traces, multi-GB HTML, OOM — tracked as C-105/C-106 in pipeline-core, never migrated here). `mapping.py` renders one polygon per cell with no cap, pagination, downsampling, or streaming. The demo PGM report (~13K cells, one origin) is already 86 MB; a full global grid (~260K cells) across multiple origins/targets would multiply this. No guard, no warning, no documented limit. This is the exact failure class the extraction was meant to make addressable — but the fix was never implemented, only relocated. Fails loud (OOM/browser hang) or degrades (unusable file size), not silent. Remediation: entity-count guard with explicit failure or downsampling path; possibly static raster tiles for large grids instead of per-cell vector polygons. |
| Cross-refs | Extraction postmortem (C-105/C-106 in pipeline-core); C-23 (the 56 MB shapefile feeds this render path) |

### C-27: WandB is a hard runtime dependency for evaluation reports

| Field | Value |
|-------|-------|
| ID | C-27 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When an evaluation report is requested in an environment without WandB access (CI, offline, air-gapped), or for a model whose WandB run is missing/expired/deleted |
| Location | `views_reporting/templates/reports/evaluation.py:50` (`generate(self, wandb_run, target)` requires a live `wandb.apis.public.runs.Run`); `:17` imports `get_latest_run` |
| Narrative | `EvaluationReportTemplate.generate()` requires a live WandB run object; all metrics and run metadata are read from `wandb_run.summary`/`wandb_run.config`. There is no local-metrics fallback — evaluation reports cannot be produced without WandB connectivity and an existing run. This is the same class of runtime-external-service coupling as C-22 (VIEWSER), but distinct: VIEWSER serves static geographic data that is replaceable with a bundled table, whereas WandB is the actual source of the evaluation metrics, so the coupling is more inherent and has no trivial local substitute. Lower severity than C-22 for that reason — it is working-as-designed availability coupling, not removable fragility — but it should be documented so report generation in restricted environments is known to be impossible without WandB. Fails loud. |
| Cross-refs | C-22 (parallel runtime-external-service dependency — VIEWSER) |

### C-28: Rendered reports depend on external CDNs (Tailwind, Plotly) at view time

| Field | Value |
|-------|-------|
| ID | C-28 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When a generated HTML report is opened in an air-gapped, offline, or CDN-blocked environment (e.g., a partner organization's restricted network) |
| Location | `views_reporting/reports/styles/tailwind.py:7` (`https://cdn.tailwindcss.com`); `views_reporting/reports/report.py:183` (`https://cdn.plot.ly/plotly-latest.min.js`) |
| Narrative | Exported reports pull Tailwind CSS and Plotly JS from public CDNs at view time rather than bundling them. A report opened without internet (or behind a CDN-blocking firewall) loses all styling and all interactive maps/graphs — it degrades to an unstyled, non-interactive page. For an internal preview this is acceptable; for a partner deliverable (e.g., UN FAO, who may view in restricted environments) it is a real robustness gap. Also a soft supply-chain consideration: `plotly-latest` is unpinned, so a future Plotly release could change rendering behavior of already-delivered reports. Fails visibly, not silently. Remediation: vendor/inline the JS+CSS into the exported HTML, or pin versions and document the online requirement. Borderline Tier 3/4 — elevated to 3 by the partner-delivery context. |
| Cross-refs | — |

### C-29: No verification that values rendered in reports match source predictions

| Field | Value |
|-------|-------|
| ID | C-29 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When a future change to the load → MAP-collapse → shapefile-join → choropleth chain silently misaligns a value with its entity (e.g., an index/merge bug maps country A's forecast onto country B) |
| Location | `views_reporting/templates/reports/forecast.py` (load → `calculate_map` → `MappingModule` join → render chain); no test asserts render-output values equal source-prediction values |
| Narrative | The test suite proves the pipeline does not crash and produces well-formed HTML, but nothing asserts that the value drawn on a given cell/country equals the corresponding source prediction after the MAP collapse and the shapefile join. The mapping join drops rows with unmatchable geometries (observed: 26 small island states dropped, 936 rows) — a silent reduction that a fidelity check would surface. A merge or index bug in this chain would be a silent-corruption path (wrong number shown for the right place, or right number on the wrong place) with no error signal. Currently an assurance gap, not a known defect — hence Tier 3, not Tier 1. **Elevate to Tier 1 if any render≠source divergence is ever observed.** Remediation: a fidelity test that round-trips a known fixture value from input through to the rendered GeoDataFrame and asserts equality per entity. |
| Cross-refs | C-11 (silent HDI degradation — prior silent-rendering class); C-01 (silent MAP corruption — prior silent-compute class) |

---

## Disagreements

### D-06: Private import vs. public API for single-cell statistical helpers — RESOLVED

| Field | Value |
|-------|-------|
| ID | D-06 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (promote to public API) vs. **Martin/Ousterhout** (use dataset-level API) vs. **Hickey** (receive pre-computed data) |
| Resolution | Resolved — adopted Feathers' approach. Promoted `calculate_single_hdi` and `compute_single_map` to public API (removed underscore prefix, added to `statistics/__init__.py`). `distributions.py` now imports from the public package path. |

---

### D-07: Should PlotDistribution compute its own statistics or receive pre-computed data?

| Field | Value |
|-------|-------|
| ID | D-07 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Hickey** (PlotDistribution should only render — computation is a separate concern) vs. **Beck** (current design is the simplest thing that works — 3 lines of computation inside the renderer is fine) vs. **Ousterhout** (dataset_statistics should provide a visualization-preparation function) |
| Resolution | Unresolved — depends on whether computation-free rendering is a real use case |

---

### D-08: Should reconciliation workers receive DataFrames or pre-extracted tensors?

| Field | Value |
|-------|-------|
| ID | D-08 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Kleppmann** (extract tensors in main process, send only tensors — eliminates dataset reconstruction and pipeline-core imports in workers) vs. **Beck** (current design works and is tested — pre-extraction adds complexity to main loop) vs. **Feathers** (current design is untestable without pipeline-core — moving extraction out improves testability) |
| Resolution | Unresolved — partially derisked by C-10 resolution (transform detection removed), but worker still reconstructs datasets. **Deferred pending GitHub #72: this debate relocates to views-postprocessing if reconciliation moves there (see C-24, cluster B).** |

---

### D-09: Should reconcile() return a value or mutate in-place?

| Field | Value |
|-------|-------|
| ID | D-09 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (return new DataFrame, don't mutate — makes partial failure recoverable) vs. **Nygard** (mutation is existing contract — but add partial-failure signal to return) vs. **Hickey** (mutation is place-oriented anti-pattern — return a value, let caller decide) |
| Resolution | Unresolved — current API does both (mutates AND returns), which is the worst option; should commit to one. **Deferred pending GitHub #72: this debate relocates to views-postprocessing if reconciliation moves there (see C-24, cluster B).** |

---

### D-10: Is ADR-011 correctly classified as project-specific? — RESOLVED

| Field | Value |
|-------|-------|
| ID | D-10 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Hickey** (constitutional-level impact) vs. **Beck** (should be ADR-003 amendment) vs. **Martin** (distinction holds) |
| Resolution | Resolved — ADR-001 updated to mark Data Transformation as Legacy per ADR-011 (commit c4c99e9). Pragmatic path taken. |

---

## Resolved Concerns

### C-21: Domain acronyms unexpanded in README — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-21 |
| Resolved | 2026-06-01 |
| Resolution | Expanded MAP, HDI, PRIO-GRID (with link), and viewser (with link) on first use in README. ADR expanded on first use. |

---

### C-20: Zero module-level docstrings across the entire codebase — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-20 |
| Resolved | 2026-06-01 |
| Resolution | Added module docstrings to all 10 `__init__.py` files (including top-level) and all 14 core `.py` files. 24 falsification test stubs converted from xfail to passing. |

---

### C-19: ReportModule heading/paragraph text not HTML-escaped — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-19 |
| Resolved | 2026-05-31 |
| Resolution | Added `escape(text)` to `add_heading()`, `add_paragraph()`, `add_image()` (caption), and `add_footer()`. Added XSS regression tests. |

---

### C-18: No CI configuration — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-18 |
| Resolved | 2026-05-31 |
| Resolution | Created `.github/workflows/ci.yml` with ruff + pytest on push to development and PR to main. |

---

### C-17: README stale and inadequate — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-17 |
| Resolved | 2026-05-31 |
| Resolution | Rewrote README with architecture table, test instructions, governance pointers, and ADR highlights. Removed "Under construction" status. |

---

### C-16: ForecastReconciler sum constraint fails on all-negative grids — RESOLVED (accepted)

| Field | Value |
|-------|-------|
| ID | C-16 |
| Tier | 4 |
| Source | falsification-audit (2026-05-31) |
| Trigger | When a model or experiment produces all-negative grid forecasts (e.g., residuals, rate-of-change predictions) and passes them through `ReconciliationModule.reconcile()` |
| Location | `views_reporting/statistics/statistics.py:520` |

Accepted as documented limitation. Added "Assumes non-negative grid values; all-negative grids produce all-zero output" to `reconcile_forecast()` docstring. CIC already documents the non-negative assumption (Section 4). xfail test stub preserved as regression guard.

---

### C-13: Cross-module private import — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-13 |
| Resolved | 2026-05-31 |
| Resolution | Promoted `_calculate_single_hdi` and `_compute_single_map` to public API (removed underscore prefix). Added re-exports to `statistics/__init__.py`. `distributions.py` now imports via public package path. Per D-06 resolution. |

---

### C-11: Silent HDI degradation — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-11 |
| Resolved | 2026-05-31 |
| Resolution | Modified fallback trace name to include "(HDI unavailable)" when HDI computation fails. Users now see a visible indicator instead of a clean graph that implies model confidence. |

---

### C-09: Template classes lack CICs — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-09 |
| Resolved | 2026-05-31 |
| Resolution | Wrote CICs for `EvaluationReportTemplate` and `ForecastReportTemplate`. Updated CIC README with both entries. 10 CICs now cover all non-trivial classes per ADR-006. |

---

### C-14: WandB alerts ignore wandb_notifications flag — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-14 |
| Resolved | 2026-05-31 |
| Resolution | Added `notifications_enabled=self._wandb_notifications` to failure alert (line 256) and completion alert (line 286) in `reconciliation.py`. All three `send_alert` calls now consistently respect the flag. |

---

### C-15: Dead self._reconciler instance — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-15 |
| Resolved | 2026-05-31 |
| Resolution | Deleted `self._reconciler = ForecastReconciler(device=self._device)` from `__init__`. Each worker creates its own instance; the module-level instance was never used. |

---

### C-03: Test coverage — RESOLVED (accepted)

| Field | Value |
|-------|-------|
| ID | C-03 |
| Resolved | 2026-05-31 |
| Resolution | Accepted as ongoing improvement. All 8 CIC classes have test coverage (158 tests). Remaining depth gaps tracked incrementally on GitHub issue #2. Not a blocking risk. |

---

### C-12: Redundant pre-sort and misleading alpha — RESOLVED (accepted)

| Field | Value |
|-------|-------|
| ID | C-12 |
| Resolved | 2026-05-31 |
| Resolution | Accepted as code quality backlog item. Redundant pre-sort and misleading alpha parameter have no correctness impact. May be cleaned up when `calculate_map()` is next modified. |

---

### C-10: Transform-detection logic assumes retired prefix convention — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-10 |
| Resolved | 2026-05-31 |
| Resolution | Deleted `ln`/`lx` prefix-sniffing branches from `to_reconciler()` and `reconcile_pg_dataset()` in `dataset_export.py` per ADR-011. Removed unused `numpy` import. Data now passes through on original measurement scale without inference. |

---

### C-08: Unused templates package — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-08 |
| Resolved | 2026-05-29 |
| Resolution | Templates populated with `EvaluationReportTemplate` and `ForecastReportTemplate` in the PR 6 companion commit. |

---

### C-07: Duplicate search_for_item_name functions — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-07 |
| Resolved | 2026-05-29 |
| Resolution | Deleted `search_for_item_name2`. Updated caller to use `search_for_item_name`. |

---

### C-06: ForecastReconciler accepts dead optimization parameters — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-06 |
| Resolved | 2026-05-29 |
| Resolution | Removed `lr`, `max_iters`, `tol` from entire reconciliation chain. |

---

### C-05: HistoricalLineGraph crashes in forecast-only mode — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-05 |
| Resolved | 2026-05-29 |
| Resolution | Added `_resolved_time_id` property. Replaced 6 unguarded accesses. Deleted dead `_get_plot_data()`. |

---

### C-04: undo_all_transformations() hardcodes lx offset — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-04 |
| Resolved | 2026-05-29 |
| Resolution | Added `_lookup_lx_offset()` to read offset from `transformation_history`. |

---

### C-02: Wrong sign in lx untransform — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-02 |
| Resolved | 2026-05-29 |
| Resolution | Fixed `np.exp(100)` → `np.exp(-100)` before initial commit. |

---

### C-01: Thread-unsafe PosteriorDistributionAnalyzer singleton — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-01 |
| Resolved | 2026-05-29 |
| Resolution | Refactored `_compute_summary()` to pure function. Deleted singleton. Per-call instantiation. |

---

## Register Conventions

Concerns are registered via the `register-risk` skill and curated via the `review-rr` skill.

- **C-xx:** Concern entries (technical risks, code quality issues, architectural debt)
- **D-xx:** Disagreement entries (unresolved debates between expert perspectives)

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
