# Technical Risk Register

**Last updated:** 2026-06-06
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 42 concerns (27 resolved, 15 open) + 5 disagreements (2 resolved)

---

## Tier Definitions

| Tier | Severity | Criteria |
|------|----------|----------|
| 1 | Critical | Silent data corruption or model output incorrectness. No error signal. Requires immediate attention. |
| 2 | High | Structural fragility that will cause failures under realistic change scenarios. Clear trigger exists. |
| 3 | Medium | Maintainability or coupling issues that increase cost of change. Multiple developers affected. |
| 4 | Low | Code quality observations. Single-developer scope. No correctness or reliability impact. |

---

## Causal Clusters

Root causes shared by multiple concerns. Resolving the root tends to dissolve or relocate the members. Use this as the strategic map; individual entries carry the detail.

| Cluster | Root cause | Members | Status |
|---------|-----------|---------|--------|
| **A — External runtime dependencies** | Report generation/viewing needs external services with no offline/bundled fallback | C-22 (VIEWSER), C-27 (WandB), C-28 (CDN) | Open — gates air-gapped / partner (UN FAO) delivery |
| **B — Reconciliation placement** | Reconciliation lives in a *reporting* repo but likely belongs in views-postprocessing | C-24 (torch), C-33 (determinism), D-08, D-09 | Blocked on GitHub #72 / views-postprocessing#3 |
| **C — PRIO-GRID scale discipline** | Repo handles ~260K-cell geodata without size discipline, at rest and at render | C-23 (shapefile in git), C-26 (render OOM) | Open — C-26 is the operational risk |
| **D — Ingestion-layer boundary** | loaders/ crossed the pipeline-core boundary ahead of governance | C-30, C-31, C-32 | Resolved (PR #82) |
| **E — Legacy transform machinery** | Log-transform inference retired (ADR-011); machinery remains | C-25 (+ resolved C-10, C-04, C-02) | Open tail — gates polars removal |
| **F — Fidelity / numerical assurance** | The compute (MAP/HDI) and load → join → render chain have no value-correctness or value-equality guard | C-29 (render fidelity), C-35 (stat-method correctness) (+ resolved C-01, C-11) | Open — highest latent severity |

C-34 (report provenance) is standalone — no shared root cause with the clusters above.

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
| Trigger | When clone time or CI-checkout time becomes a measured bottleneck, or when migrating the asset-storage strategy (e.g., to git-lfs or a remote asset store) — every clone today pulls 56 MB of binary geodata regardless of whether priogrid maps are ever rendered |
| Location | `views_reporting/assets/shapefiles/priogrid/priogrid_cell.shp` (34 MB), `.dbf` (20 MB) |
| Narrative | The PRIO-GRID cell polygon shapefile (~260K polygons) is committed as raw binary to git (`git check-attr` confirms `filter: unspecified` — not LFS). views-postprocessing carries the same file via git-lfs (~35 MB). The polygons are genuinely needed for choropleth cell rendering, so the file is correct for the job — but it does not belong in raw git history. Remediation: git-lfs (matches views-postprocessing's approach, simplest) or download-on-first-use from a shared asset store. The country shapefile (Natural Earth 110m, ~700 KB) is small enough to leave as-is. |
| Cross-refs | — |

### C-24: torch (~2 GB) dependency coupled to reconciliation living in a reporting repo

| Field | Value |
|-------|-------|
| ID | C-24 |
| Tier | 3 |
| Source | external-review (datafactory migration assessment) |
| Trigger | When packaging views-reporting for a lightweight or reports-only deployment, or when the ~2 GB PyTorch install becomes a measured constraint in a reports-only environment — torch is pulled for proportional scaling math that is, at core, per-country divide-by-sum then multiply-by-total |
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
| Trigger | When the MAP-collapse, shapefile-join, or index-handling code in the load → render chain is next modified — an index/merge bug there would silently map country A's forecast onto country B |
| Location | `views_reporting/templates/reports/forecast.py` (load → `calculate_map` → `MappingModule` join → render chain); no test asserts render-output values equal source-prediction values |
| Narrative | The test suite proves the pipeline does not crash and produces well-formed HTML, but nothing asserts that the value drawn on a given cell/country equals the corresponding source prediction after the MAP collapse and the shapefile join. The mapping join drops rows with unmatchable geometries (observed: 26 small island states dropped, 936 rows) — a silent reduction that a fidelity check would surface. A merge or index bug in this chain would be a silent-corruption path (wrong number shown for the right place, or right number on the wrong place) with no error signal. Currently an assurance gap, not a known defect — hence Tier 3, not Tier 1. **Elevate to Tier 1 if any render≠source divergence is ever observed.** Remediation: a fidelity test that round-trips a known fixture value from input through to the rendered GeoDataFrame and asserts equality per entity. |
| Cross-refs | C-11 (silent HDI degradation — prior silent-rendering class); C-01 (silent MAP corruption — prior silent-compute class) |

### C-33: Determinism of parallel reconciliation output is unverified

| Field | Value |
|-------|-------|
| ID | C-33 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Trigger | When a delivered forecast must be reproduced exactly (audit, re-delivery, regression baseline) and parallel reconciliation output is found to vary run-to-run, or when debugging a reconciliation discrepancy |
| Location | `views_reporting/reconciliation/reconciliation.py` (ProcessPoolExecutor parallel execution); `views_reporting/statistics/statistics.py` (`ForecastReconciler`) |
| Narrative | Reconciliation runs across worker processes via `ProcessPoolExecutor`. Nothing in the register or test suite asserts that the assembled output is deterministic — independent of worker completion order, process count, or unseeded RNG in torch/numpy. For a forecasting *deliverable*, run-to-run variation (or worse, completion-order-dependent value assignment) would be a reproducibility/traceability failure. This is an assurance gap, not a demonstrated defect — if a concrete order- or seed-dependent value path is found, it becomes a silent-corruption concern (elevate toward Tier 1/2). Remediation: a determinism test (same input → byte-identical reconciled output across repeated runs and worker counts); confirm results are assembled by input key, not completion order, and that any RNG is seeded. Note: this concern relocates with reconciliation if it moves to views-postprocessing. |
| Cross-refs | Cluster B (reconciliation placement); C-24 (torch/placement), D-08 (worker data shape), D-09 (return vs mutate); GitHub #72 (relocates if reconciliation moves) |

### C-34: Reports carry no provenance — no model-run / data-version / code-revision stamp

| Field | Value |
|-------|-------|
| ID | C-34 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Trigger | When a partner (e.g., UN FAO) or an auditor needs to trace a delivered report back to the exact model run, data version, and code revision that produced it |
| Location | `views_reporting/reports/report.py` (`ReportModule` assembly/export); `views_reporting/templates/reports/` (templates) |
| Narrative | Generated reports embed no provenance metadata: which WandB run / model, which prediction files and data version, which views-reporting code revision (git SHA), and when. For an internal preview this is fine; for an external forecasting deliverable it is an auditability and traceability gap — two reports with the same styling are indistinguishable as to source. No correctness impact, hence Tier 3 (not a silent-corruption class), elevated above Tier 4 by the partner-delivery and audit context (parallel reasoning to C-28). Remediation: a footer/metadata block stamping model id(s), run id(s), prediction-source paths, package version, and generation timestamp. Standalone — not part of a cluster. |
| Cross-refs | C-28 (partner-delivery robustness context); C-27 (WandB is the run-metadata source) |

### C-35: MAP/HDI correctness on pathological posteriors is unguarded

| Field | Value |
|-------|-------|
| ID | C-35 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Trigger | When a model produces a multimodal, degenerate (constant), or near-all-zero posterior and its MAP/HDI is rendered without anyone validating the estimate against the distribution shape |
| Location | `views_reporting/statistics/statistics.py` (`PosteriorDistributionAnalyzer` — MAP via histogram density peak; HDI via shortest-interval on sorted samples) |
| Narrative | Prior statistics concerns covered thread-safety (C-01) and silent HDI *degradation signalling* (C-11), but not the *numerical correctness* of MAP/HDI on edge-shaped posteriors. The histogram-density-peak MAP picks a single mode on a bimodal posterior (potentially a misleading point estimate); degenerate/constant samples collapse the histogram; near-all-zero samples can make the peak unstable. These produce plausible-but-wrong-looking estimates with no error signal — the same silent-compute class as C-29, hence the matching calibration: Tier 3 as an assurance gap, **elevate to Tier 1 if a concrete wrong-estimate case is demonstrated**. Remediation: red-team tests over pathological sample distributions (multimodal, constant, all-zero, single-sample) asserting MAP/HDI behave sensibly or fail loud; document the single-mode MAP assumption. |
| Cross-refs | Cluster F (fidelity/numerical assurance); C-29 (sibling assurance gap — render fidelity); C-11 (silent HDI degradation, resolved); C-12 (calculate_map pre-sort/alpha, resolved-accepted) |

### C-36: Installable surface is bounded to Python 3.11 + Linux/macOS by upstream transitive pins

| Field | Value |
|-------|-------|
| ID | C-36 |
| Tier | 2 |
| Source | falsify (hatchling+uv migration audit, 2026-06-04) |
| Trigger | When the platform or users adopt Python 3.12+ (3.11 is already not the newest), or when a Windows install is attempted — `pip`/`uv install views-reporting` fails |
| Location | `pyproject.toml` (`requires-python = ">=3.11,<3.12"`, `[tool.uv] environments = linux/darwin`); root cause upstream: `views-pipeline-core 2.3.0 → ingester3 2.1.1 → levenshtein 0.20.9`, and `viewser 6.6.4 → docker → pywin32` |
| Narrative | Empirically (falsify probes), views-reporting only **installs on Python 3.11** and only **resolves on Linux/macOS**, both forced by upstream transitive pins it does not control. `levenshtein 0.20.9` (pulled via `views-pipeline-core → ingester3`, independent of the now-removed direct `views-transformation-library` dep) has no wheel and fails to build on 3.12 **and** 3.13; the `viewser → docker → pywin32` chain breaks universal Windows resolution. Failures are **loud** (pip refuses install / build error), not silent — hence Tier 2, not Tier 1. The constraint is bounded honestly via `requires-python<3.12` and uv environment scoping (ADR-014), but it caps the package's reach and **will block adoption when the ecosystem moves past 3.11**. Remediation is upstream: pipeline-core/ingester3 must update the `levenshtein` pin (and ideally drop the `pytest<9` runtime pin uv also surfaced), and viewser must shed the docker/pywin32 dependency (ties to the viewser retirement, C-22). views-reporting can widen `requires-python` and platform scope once upstream updates. |
| Cross-refs | C-22 (viewser retirement — the docker/pywin32 chain rides on viewser; GitHub #70); C-24 (heavy upstream dependency surface); ADR-014 (build tooling; supersedes ADR-013); Cluster A (external/upstream dependency coupling) |

### C-38: CM line-graph HTML grows with the number of embedded HDI levels

| Field | Value |
|-------|-------|
| ID | C-38 |
| Tier | 3 |
| Source | review-diff / size measurement (#90–#91 HDI level selector, 2026-06-05) |
| Trigger | When a CM **sample** model's forecast/evaluation report is rendered for many entities × multiple HDI levels — particularly a full-country CM run (~190 countries) with more than the default three levels, or many rolling-origin sample graphs in one report |
| Location | `views_reporting/visualizations/historical.py` — multi-level HDI rendering embeds 3 band traces per (entity, level), and each entity dropdown button carries a visibility array of length = total traces, so the embedded payload grows ~O(entities² × levels × 3) |
| Narrative | The legend-selectable multi-level HDI feature (#90) embeds **all** levels for **all** entities in the static HTML (no server to recompute on click). Empirically, the red_ranger CM sample report (~191 countries, 3 levels) is **15.6 MB vs 13.4 MB single-level — +2.2 MB / +16%**; the growth comes both from the tripled band traces and, more steeply, from the entity dropdown's per-button visibility arrays (length = total traces × number of entity buttons). This is **bounded and fails loud** (a larger file, never silent corruption), so it is Tier 3, **not** the OOM-class PGM render risk. **Scope is CM line graphs only: the heavy PGM choropleth path is explicitly unaffected** — the historical line graph is gated on `isinstance(forecast_dataset, _CDataset)` (CM) in `templates/reports/forecast.py`, so the ~90 MB PGM report (C-26) does not carry HDI bands. The #89 tag-based visibility refactor *reduced* adjacent fragility (resolved CIC Deviation #5). Remediation if it grows: cap the entity count / levels for the line graph, lazily embed non-default levels, or switch to a server/■recompute control for very large CM runs. |
| Cross-refs | C-26 (sibling render-size risk on the **PGM map** path — different mechanism, unaffected here); Cluster C (scale discipline); ADR-016 (levels are config-bounded via `ReportingConfig.hdi_levels`); CIC Deviation #5 (resolved, #89) |

### C-39: Entity-metadata accessor surface has no direct in-repo tests

| Field | Value |
|-------|-------|
| ID | C-39 |
| Tier | 4 |
| Source | repo-assimilation (2026-06-05) |
| Trigger | When `metadata/entity_metadata.py` accessors are refactored, or when VIEWSER's queryset return shape/column names change upstream — a signature/semantics regression would surface only at live report-generation time, not in CI |
| Location | `views_reporting/metadata/entity_metadata.py` (30+ accessors — `get_isoab`, `get_name`, `get_pg_lat_lon`, `build_c_metadata_cache`, `build_pg_metadata_cache`, `get_subset_by_country_id`, …); no dedicated file in `tests/` exercises them (only indirectly, via mocks, in `test_mapping.py` / `test_reconciliation_module.py`) |
| Narrative | The metadata module is the widest untested public surface in the repo. Its functions are mocked in the mapping/reconciliation tests but never exercised against a recorded/known VIEWSER response, so a regression in an accessor (renamed column, changed return shape, off-by-one in row/col, isoab vs iso3 mismatch) would not be caught by CI — it would appear as a wrong label/join at live report time. This is an **assurance gap, not a known defect**: no current incorrectness is demonstrated, the runtime path works, and the values are static reference data — hence Tier 4. Distinct from C-22, which concerns the *runtime dependency* on VIEWSER (report breaks if VIEWSER is unreachable); this concerns the *absence of regression coverage* for the accessors regardless of availability. Remediation: contract tests over a recorded/mocked VIEWSER fixture asserting each accessor's column names and return shape (and the isoab↔ADM0_A3 join key noted in C-22). Naturally addressed if the C-22 remediation swaps the Querysets for a bundled static lookup (which would be directly testable). |
| Cross-refs | C-22 (same module — runtime dependency vs. this test-coverage gap; the C-22 static-lookup remediation would make these accessors testable); C-29 (sibling assurance gap — render fidelity) |

### C-41: Canonical report-metric names can drift from the evaluator's emitted tokens

| Field | Value |
|-------|-------|
| ID | C-41 |
| Tier | 3 |
| Source | expert-design / ADR-017 (canonical evaluation-report metrics, 2026-06-06) |
| Trigger | When `views_evaluation` (or a model config) renames, adds, or re-tokenises a metric (e.g. changes how a metric key is spelled in the WandB run summary) without a matching update to `ReportingConfig.canonical_report_metrics` |
| Location | `views_reporting/config/_reporting.py` (`canonical_report_metrics`) vs the metric tokens emitted into the WandB run summary by `views_evaluation`; matched via `reports/utils.py:search_for_item_name` (segment match on `[eval_type, metric, target, "mean"]`) |
| Narrative | ADR-017 makes the report attempt a central canonical metric set and pull values from the run by token-matching the metric name. If a canonical name no longer matches the evaluator's emitted token, the metric will **always** render as "not calculated" even though it *was* computed — a plausible-but-misleading report (the failure is visible as a note, not silent corruption, hence Tier 3 not Tier 1). This is a cross-repo coupling: the canonical names in views-reporting must track the metric naming in views_evaluation / model configs. Mitigation: keep canonical names identical to the model-config metric names (which drive the evaluator); a contract test comparing the canonical map against a known real run's summary tokens would catch drift early. The "not calculated" note bounds the damage to confusion, not wrong numbers. |
| Cross-refs | ADR-017; C-27 (WandB coupling — surrounding eval-report dependency); C-39 (sibling assurance/coverage gap) |

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
| Resolution | Unresolved — partially derisked by C-10 resolution (transform detection removed), but worker still reconstructs datasets. **Deferred pending GitHub #72: this debate relocates to views-postprocessing if reconciliation moves there (see C-24; Cluster B — reconciliation placement).** |

---

### D-09: Should reconcile() return a value or mutate in-place?

| Field | Value |
|-------|-------|
| ID | D-09 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (return new DataFrame, don't mutate — makes partial failure recoverable) vs. **Nygard** (mutation is existing contract — but add partial-failure signal to return) vs. **Hickey** (mutation is place-oriented anti-pattern — return a value, let caller decide) |
| Resolution | Unresolved — current API does both (mutates AND returns), which is the worst option; should commit to one. **Deferred pending GitHub #72: this debate relocates to views-postprocessing if reconciliation moves there (see C-24; Cluster B — reconciliation placement).** |

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

### C-42: Canonical report-metric lists were unconfirmed placeholders — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-42 |
| Tier | 3 |
| Source | ADR-017 implementation (2026-06-07) |
| Resolved | 2026-06-07 |
| Resolution | The placeholder lists were replaced with **real `views_evaluation` metric tokens** (from its `metric_catalog.py` METRIC_CATALOG / METRIC_MEMBERSHIP) reconciled against the **ADR-029** ensemble-governance protocol. Final map: reg-point `(MSLE, MSE, MCR_point, y_hat_bar)`; reg-sample `(CRPS, MIS, Ignorance, MCR_sample, y_hat_bar)`; class-point `(AP, Brier_cls_point)`; class-sample `(Brier_cls_sample, CRPS, twCRPS)` (the full *implemented* classification membership — the catalog has no more). The synthetic fixture now uses the real `{eval_type}/{target}/{metric}_mean` key format. **Residuals (deliberate, documented, not placeholders):** (a) conservativeness shows MCR (interpretable calibration ratio) **and** keeps `y_hat_bar` until HH confirms; (b) ensemble **diversity** (ADR-029 Rule 2) is omitted because its evaluator metric `SD` is `implemented=False` upstream — a `views_evaluation`-owned gap, intentionally not chased here. |
| Location | `views_reporting/config/_reporting.py` (`_CANONICAL_REPORT_METRICS`) |
| Cross-refs | C-41 (ongoing canonical-name↔token drift — same map, different lifecycle, still open); ADR-017; ADR-029 (governance protocol, source of the regression standard) |

### C-40: Evaluation report silently omitted the Prediction-Samples section — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-40 |
| Tier | 3 |
| Source | falsify (2026-06-06; "current setup produces reports like the Downloads artifact") |
| Resolved | 2026-06-06 |
| Resolution | `_add_prediction_sample_graphs` now emits a VISIBLE "Prediction Samples" heading + an italic "_Prediction samples unavailable: <reason>_" note on every skip path (no prediction files, ensemble missing `models`, no raw data, target absent, unknown level) and in the section's outer exception handler — instead of returning with only a `logger.warning`. A partial evaluation report is now self-evidently incomplete. Enforced by `tests/test_falsification_eval_ensemble_samples.py::test_ensemble_eval_missing_models_surfaces_skipped_samples`; the ensemble path of the offline e2e (`tests/test_e2e_eval_report.py`) also exercises the note. |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_prediction_sample_graphs` skip paths + the `_add_report_content` sample-graphs wrapper) |
| Narrative | Original concern: the Prediction-Samples section (home of the legend-selectable HDI graphs) was dropped with only a `logger.warning`, so a degraded eval report read as complete. Same *make-degradation-visible* class as C-11 (trace-level) but at the report-section level. Now made visible. |
| Cross-refs | C-11 (sibling make-degradation-visible pattern, resolved); C-27 (WandB coupling — eval-report robustness); C-34 (report completeness signalling) |

### C-37: Forecast/hindcast cutoff line labelled "Forecast Start" even for hindcasts — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-37 |
| Tier | 3 |
| Source | visual inspection + persona-critique (2026-06-04) |
| Resolved | 2026-06-04 |
| Trigger | When a calibration/evaluation report is generated (predictions are a held-out rolling-origin hindcast that overlays observed history) and the chart is read by anyone — internal or partner |
| Location | `views_reporting/visualizations/historical.py` (`plot_predictions_vs_historical` cutoff logic; `_add_cutoff_line`; `_format_interactive_plot`) |
| Narrative | `HistoricalLineGraph` drew the cutoff line at `max(observed)` and hard-labelled it "Forecast Start". In a calibration run the predictions are at their true held-out test-window months (verified faithful — `month_id`s match `identifiers.npz['time']` exactly, no offset), which lie *inside* observed history, so they rendered to the **left** of "Forecast Start" — reading as "a forecast in the past." Not a data bug; a labeling/semantics gap, and it affected ALL calibration runs (same code in the forecast template, evaluation sample-graphs, and the pipeline), not just demo HTMLs. A persona panel (UX, forecasting methodologist, partner reviewer, maintainer, rolling-origin scout) converged on a launch-line framing. |
| Resolution | Made the cutoff **data-driven and mode-aware** (no `run_type` plumbing needed): if `max(predicted) <= max(observed)` it is a hindcast → line at the first predicted month (forecast launch), label "Forecast launched (hindcast)", plus a caption ("Hindcast: forecast launched at month X, shown against the observed values it is scored against — not a future forecast"); otherwise a true forecast → line at last observed month, "Forecast Start" (unchanged default). Guarded by `tests/test_historical_line_graph.py::TestHindcastCutoffAnnotation`; CIC `cic_historical_line_graph.md` updated (Deviation #7). |
| Cross-refs | Cluster F (fidelity/numerical assurance); C-29 (render fidelity — adjacent); the persona-critique decision (launch-line over a shaded band) |

---

### C-32: Evaluation template read parquet predictions directly, bypassing the Ingestion layer — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-32 |
| Tier | 3 |
| Source | review (expert code review of governance-drift changeset, 2026-06-04) |
| Resolved | 2026-06-04 |
| Trigger | When a new prediction storage format is registered, or the parquet read path changes — the direct `read_dataframe` call bypassed the loader registry and would not pick up the change; also any audit of ADR-002 conformance |
| Location | `views_reporting/templates/reports/evaluation.py:397` (the `else: pred_df = read_dataframe(pred_path)` branch in `_add_prediction_sample_graphs`) |
| Narrative | The #76 ADR-002 change added a Forbidden Pattern: Computation/Rendering/Composition reading prediction storage directly instead of through the Ingestion layer (bypassing the format boundary). `_add_prediction_sample_graphs` complied for the `prediction_frame` format (called `load_predictions`) but read the `dataframe` (parquet) format directly via `read_dataframe`, bypassing `DataFrameLoader`/the registry — a contract-vs-code drift introduced by the very changeset that wrote the rule. The asymmetry meant any new storage format added to the registry would be invisible to this code path. Distinct from C-30 (the converter manager boundary) and C-31 (Protocol typing). |
| Resolution | Routed the parquet branch through `load_predictions("dataframe", pred_path, level, [target])`. The original pre-construction skip is preserved across both failure modes: a frame with no usable prediction columns makes the dataset constructor fail loud (`ValueError: Targets must be specified for non-prediction dataframes`), caught locally and converted to a clear per-sequence skip; a frame that has predictions but not this target is skipped via the post-load `pred_col not in forecast_dataset.dataframe.columns` check. Behavior-preserving — `DataFrameLoader` constructs an identical dataset (`pd.read_parquet` → `DATASET_CLASSES[level](df)`). The historical/raw read at `:360` is left as a direct `read_dataframe` — it reads observed data, not prediction storage, so the ADR-002 rule does not cover it. Verified: ruff clean, full suite green. |
| Cross-refs | ADR-002 (#76, the rule this restores conformance to); C-30, C-31 (same governance-drift changeset) |

---

### C-30: PredictionFrameConverter manager coupling was an undocumented boundary contract — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-30 |
| Tier | 3 |
| Source | expert-code-review (2026-06-04) |
| Resolved | 2026-06-04 |
| Trigger | When pipeline-core refactors `PredictionFrameConverter` or `PredictionFrame`, or changes the `to_prediction_df` output (e.g., starts naming index levels) |
| Location | `views_reporting/loaders/prediction_frame_loader.py:10` (imports `PredictionFrameConverter` from `views_pipeline_core.managers.prediction`); `:40` (the `set_names` index repair) |
| Narrative | The Ingestion layer depends on a pipeline-core **manager** (`PredictionFrameConverter`), not just a data container. ADR-002's Foundation layer sanctions depending only on pipeline-core *containers*; the Ingestion-layer dependency on a manager is the one sanctioned exception. After #76, ADR-002 stated this coupling "is a boundary contract governed by ADR-009" — but ADR-009 did not yet contain it, leaving a dangling promise. The contract surface includes `to_prediction_df(pf, target)` returning a MultiIndex with **unnamed `[None, None]` levels** that the loader must `set_names()`; if that output contract changes silently, the loader mis-aligns. A second behavioral dependency on this boundary: the dataset constructor signals "no usable prediction columns" as `ValueError`, which `EvaluationReportTemplate` (via C-32) catches to skip unusable sequences gracefully. |
| Resolution | ADR-009 §1a now documents the Ingestion ↔ pipeline-core prediction-manager boundary contract (sanctioned manager imports, the unnamed-`[None, None]`-index handshake, the `ValueError` "no usable predictions" signal, invariants, and failure semantics). Merged in PR #82 (#80, commit `1b5c1f3`). The `ValueError` dependency is guarded by `tests/test_loaders.py::test_parquet_without_prediction_columns_raises`. Cluster D. |
| Cross-refs | GitHub #80 (remediation, merged); ADR-002 (Layer 2, #76); ADR-012 (the documented seam); ADR-009 §1a; C-31, C-32 (Cluster D) |

---

### C-31: PredictionLoader protocol returned `Any`, leaving the loader contract type-unenforced — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-31 |
| Tier | 4 |
| Source | expert-code-review (2026-06-04) |
| Resolved | 2026-06-04 |
| Trigger | When a second loader consumer is added in a higher layer and relies on the return type, or a static type check is run against loader call sites |
| Location | `views_reporting/loaders/_protocol.py` (formerly `-> Any` / `-> list[Any]`) |
| Narrative | The `PredictionLoader` Protocol declared `Any` returns "to avoid coupling the protocol to concrete types," leaving the loader contract unenforced by the type system (defeating the LSP/ISP value of the Protocol). Both concrete loaders already annotated `Union[CMDataset, PGMDataset]`; only the abstraction was loose. |
| Resolution | Typed the Protocol returns as `Union[CMDataset, PGMDataset]` / `list[Union[CMDataset, PGMDataset]]`, importing the containers under `TYPE_CHECKING` to keep the protocol module import-light. Merged in PR #82 (#81, commit `6547bce`). Documented in `cic_loader_protocol_and_registry.md`. Cluster D. |
| Cross-refs | GitHub #81 (remediation, merged); C-30, C-32 (Cluster D); #77 (loader CIC documents the typed contract) |

---

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
