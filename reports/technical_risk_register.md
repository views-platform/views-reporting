# Technical Risk Register

**Last updated:** 2026-06-22
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 60 concerns (33 resolved, 27 open) + 5 disagreements (2 resolved)

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
| **A — External runtime dependencies** | **C-108 root: reporting *acquires/classifies* inputs at render time instead of *receiving* them through an injected contract.** Report generation/viewing needs external services with no offline/bundled fallback | **C-108 (root)**, C-22 (VIEWSER), C-27 (WandB), C-44 ✓ (deps now declared — #120), C-46 (tests mock the fetch), C-48 (reads cloud metric replica — confirmed instance / #105/#106/#177 saga), C-110 (interim-fix mis-selection risk), C-114 (imports pipeline-core *private* dataset internals — compile-time coupling, same views-frames-inversion remediation) | Open — gates air-gapped / partner (UN FAO) delivery; dissolved by the views-frames inversion |
| **B — Reconciliation placement** | Reconciliation lives in a *reporting* repo but likely belongs in views-postprocessing | C-24 (torch), C-33 (determinism), D-08, D-09 | Blocked on GitHub #72 / views-postprocessing#3 |
| **C — PRIO-GRID scale discipline** | Repo handles ~260K-cell geodata without size discipline, at rest and at render | C-23 (shapefile in git), C-26 (render OOM) | Open — C-26 is the operational risk |
| **D — Ingestion-layer boundary** | loaders/ crossed the pipeline-core boundary ahead of governance | C-30, C-31, C-32 | Resolved (PR #82) |
| **E — Legacy transform machinery** | RESOLVED (2026-06-20, #119) — `DatasetTransformationModule` removed + direct `polars` declaration dropped (polars stays transitive via pipeline-core) | C-25 ✓ (+ resolved C-10, C-04, C-02) | ✓ Resolved |
| **F — Value-correctness & contract assurance** | The load → compute → render → reconcile chain is tested for shape / does-not-crash, not for value equality, contract conformance, or input completeness | C-29 (render fidelity), C-35 (MAP/HDI correctness), C-39 (metadata accessors untested), C-41 (canonical-token contract test), C-116 (multi-match → silent wrong metric value), C-111 (input completeness), C-113 (actuals provenance), C-112 (bundled-data staleness — forward, pairs with C-22), C-33 (completeness/determinism guard — assurance aspect; placement stays Cluster B) (+ resolved C-01, C-11) | Open — highest latent severity; mostly "write the missing correctness/contract test" (an assurance sprint) |
| **G — Partner-deliverable readiness** | Reports are built for internal preview, not yet hardened as a standalone, traceable, decision-appropriate *partner artifact* | C-28 (offline / self-contained), C-34 (provenance / auditability), C-109 (decision-appropriate uncertainty) | Open — the roadmap's partner-delivery track (Sprint-2 stories C/D + Phase 4) |

C-34 (provenance) and C-28 (offline) now anchor **Cluster G** (partner-deliverable readiness) rather than standing alone; the C-108 inversion does not fix C-28 (the exported HTML's view-time CDN dependency), which is why C-28 moved out of Cluster A.

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
| Trigger | When migrating asset storage to git-lfs / a remote asset store, **or** when a fresh clone / CI-checkout time is next profiled — every clone today pulls 56 MB of binary geodata regardless of whether priogrid maps are ever rendered |
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

### C-26: No scale guard — full global PGM rendering may OOM or produce multi-GB reports

| Field | Value |
|-------|-------|
| ID | C-26 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When a forecast report is generated for a full global PRIO-GRID-month model (all ~260K cells, multi-target, multi-origin) rather than the Africa+Middle East subset, or when a PGM evaluation report renders many origins |
| Location | `views_reporting/mapping/mapping.py` (no entity-count guard before building Plotly traces); demonstrated: a single-origin PGM demo report is already ~86 MB |
| Narrative | The original extraction from pipeline-core was driven in part by PGM-scale rendering failures (172K Plotly traces, multi-GB HTML, OOM — tracked as C-105/C-106 in pipeline-core, never migrated here). `mapping.py` renders one polygon per cell with no cap, pagination, downsampling, or streaming. The demo PGM report (~13K cells, one origin) is already 86 MB; a full global grid (~260K cells) across multiple origins/targets would multiply this. No guard, no warning, no documented limit. This is the exact failure class the extraction was meant to make addressable — but the fix was never implemented, only relocated. Fails loud (OOM/browser hang) or degrades (unusable file size), not silent. Remediation: entity-count guard with explicit failure or downsampling path; possibly static raster tiles for large grids instead of per-cell vector polygons. **MITIGATED (#118, 2026-06-20):** an explicit **fail-loud cell-count guard** landed in `plot_map` — when the rendered entries (`len(mapping_dataframe)` = entities × time steps) exceed `ReportingConfig.max_map_cells` (default 50,000), it raises a `ValueError` naming the count + limit + override **before any trace construction**, converting the catastrophic case from a *late, uncontrolled* OOM crash / unusable multi-GB file (the original "fails loud but degrades" framing above) into an *early, controlled, actionable* refusal. The threshold is injected at the Compose boundary (ADR-016); the Render layer never reads config. **Residual (why this stays open, downgraded):** the **downsampling / raster-tile** path (render large grids rather than refuse them) is deliberately deferred to a separate follow-up — it changes output fidelity and is a larger feature. The acute Tier-2 uncontrolled-failure risk is resolved (the failure is now early and actionable); what remains is the missing-capability follow-up. **Tier recalibrated 2 → 3 (review-rr 2026-06-22):** the acute uncontrolled-failure risk was the Tier-2 driver and is resolved by the #118 fail-loud guard; the live residual is a deferred *capability* (downsampling / raster tiles, GitHub #125), not a structural fragility. |
| Cross-refs | Extraction postmortem (C-105/C-106 in pipeline-core); C-23 (the 56 MB shapefile feeds this render path); #118 (the fail-loud guard); ADR-016 (config injected to the Render layer); ADR-008 (fail-loud) |

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
| Narrative | Reconciliation runs across worker processes via `ProcessPoolExecutor`. Nothing in the register or test suite asserts that the assembled output is deterministic — independent of worker completion order, process count, or unseeded RNG in torch/numpy. For a forecasting *deliverable*, run-to-run variation (or worse, completion-order-dependent value assignment) would be a reproducibility/traceability failure. This is an assurance gap, not a demonstrated defect — if a concrete order- or seed-dependent value path is found, it becomes a silent-corruption concern (elevate toward Tier 1/2). Remediation: a determinism test (same input → byte-identical reconciled output across repeated runs and worker counts); confirm results are assembled by input key, not completion order, and that any RNG is seeded. Note: this concern relocates with reconciliation if it moves to views-postprocessing. **Compounding (repo-assimilation 2026-06-18):** failed `(country, time, target)` tasks are logged + WandB-alerted but the `raise RuntimeError` is commented out (`reconciliation.py:272-275`), so `reconcile()` returns a **partial** `reconciled_dataframe` as a success — silently completing fewer cells than submitted. A determinism/completeness guard should also assert the result count equals the submitted task count (or fail loud on any failed task). |
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
| Narrative | Prior statistics concerns covered thread-safety (C-01) and silent HDI *degradation signalling* (C-11), but not the *numerical correctness* of MAP/HDI on edge-shaped posteriors. The histogram-density-peak MAP picks a single mode on a bimodal posterior (potentially a misleading point estimate); degenerate/constant samples collapse the histogram; near-all-zero samples can make the peak unstable. These produce plausible-but-wrong-looking estimates with no error signal — the same silent-compute class as C-29, hence the matching calibration: Tier 3 as an assurance gap, **elevate to Tier 1 if a concrete wrong-estimate case is demonstrated**. Remediation: red-team tests over pathological sample distributions (multimodal, constant, all-zero, single-sample) asserting MAP/HDI behave sensibly or fail loud; document the single-mode MAP assumption. As of the views-frames adoption (S3), the hand-rolled MAP/HDI math now delegates to the conformance-tested, deterministic `views_frames_summarize` package (the joblib parallelism and its `Parallel.print_progress` monkeypatch are retired); the reporting-owned presentation (HDI nesting, MAP-inclusion, `enforce_non_negative`, NaN guards) is retained, so the assurance gap on pathological posteriors stands and the tier is unchanged. |
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
| Tier | 3 — **[backlog-watch]** (bounded, fails loud, known mitigation; monitor, not active risk) |
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

### C-46: CI was silently red for 12 days — local test gate diverges from CI (local ≠ CI)

| Field | Value |
|-------|-------|
| ID | C-46 |
| Tier | 2 |
| Source | incident / investigation (2026-06-18) |
| Trigger | When a new test reads a gitignored fixture under `tests/data/` without a skip-guard, or when any other local-vs-CI environment divergence is introduced — the local `pytest` gate (ship-it / review) stays green while CI goes red, and the divergence is not noticed because nothing in our flow checks CI status after a push/merge |
| Location | `tests/test_e2e_eval_report.py`, `tests/test_falsification_eval_ensemble_samples.py` (the two unguarded fixture tests); `.gitignore:80-82` (fixtures gitignored); `.github/workflows/ci.yml` (`pytest tests/ -x -q`); `tests/data/README.md` (the documented skip-when-absent contract) |
| Narrative | CI (`lint-and-test`) was red on `development` from 2026-06-06 14:17 (`9ebd7cf9`, last green) until 2026-06-18, and **~8 PRs plus several `development` pushes merged through it unnoticed**. Two eval-report tests hard-required the gitignored PredictionFrame fixtures and `FileNotFound`ed at `evaluation.py:508` on a fresh CI checkout, violating the documented "fixture-dependent tests skip when data is absent" contract. The reason it went unnoticed is the **local ≠ CI divergence**: our local ship-it/review gates run `pytest` where the gitignored fixtures exist (264 passed), while CI checks out without them — so local green gave false confidence, and we never verified CI post-push. A full fixtureless run with `pytest` and **no `-x`** confirmed **no hidden logic regression** was masked behind the first failure — only the two fixture failures — so this is a signal/process failure, not silent corruption (hence Tier 2, not Tier 1). **Mitigation:** PR #109 (`fix/ci-fixture-skip-guards`) adds the skip-guard to both tests, restoring CI to green and making local == CI for this case. **Residual (why this stays open):** the divergence pattern can recur — a future unguarded fixture test, or any other local/CI environment gap — and we have no habit or automation of verifying CI after a push/merge. The enforcement half (a red CI does not block merges) is C-47. Remediation: a post-push/pre-merge CI-status check in the workflow (`gh pr checks` green before merge); and keep the fixture-skip contract honored for any new fixture-dependent test. |
| Cross-refs | C-47 (the enforcement gap — no merge gate); C-18 (CI configuration exists — RESOLVED; distinct from this signal-integrity concern); PR #109 (acute mitigation) |

### C-47: No merge gate — a red CI does not block merges (no branch protection)

| Field | Value |
|-------|-------|
| ID | C-47 |
| Tier | 2 — **[accepted-open]** (user declined branch protection 2026-06-18; tracked for visibility, not an action item) |
| Source | incident / investigation (2026-06-18) |
| Trigger | When a PR (or direct `development` push) whose `lint-and-test` check is failing is merged — GitHub permits it because no branch-protection rule requires the check to pass |
| Location | GitHub repository settings (branch protection for `development` / `main` — absent); `.github/workflows/ci.yml` (`lint-and-test` is not a required status check) |
| Narrative | `development` and `main` have no branch-protection rule requiring the `lint-and-test` check to pass before merge. This is the structural reason ~8 PRs merged through 12 days of red CI (C-46): the signal existed but nothing enforced it. This is the durable enforcement half of the C-46 incident — even with local == CI restored, a future red CI could again be merged through. **The user has explicitly declined to enable branch protection for now**, so this is registered as an *accepted-open* risk for visibility rather than an action item. Remediation (when adopted): add a branch-protection rule on `development`/`main` making `lint-and-test` a required status check, so a red CI blocks merge. Fails loud once enabled (merge button disabled); until then the risk is that a red check is merged unnoticed. |
| Cross-refs | C-46 (the incident this gap enabled — signal integrity / local≠CI); accepted-open per user decision (2026-06-18) |

### C-48: Evaluation report reads constituent metrics from the WandB cloud replica, not the authoritative local eval files

| Field | Value |
|-------|-------|
| ID | C-48 |
| Tier | 2 |
| Source | expert-code-review (root-cause review, 2026-06-18); **CONFIRMED** via multi-agent live-WandB investigation (2026-06-18) |
| Trigger | When an evaluation/ensemble report is generated for models that have been re-run after their eval run (so the most-recently-*created* WandB run is not the eval run), or in an environment whose installed `views-pipeline-core` lacks the #177 `get_latest_run` contract / whose WandB cloud state differs from the local run — the report omits or mislabels constituents. **This has now been observed in the production runtime (see evidence below), not just latent.** |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_report_content` → `get_latest_run().summary`); authoritative local copy written by `views-pipeline-core/.../managers/prediction/io.py:146` (`save_evaluations` → `eval_<run_type>_<target>_{step,ts,month}_<ts>.parquet`) |
| Narrative | The ensemble report sources each constituent's metrics from the **WandB cloud** (`get_latest_run().summary`) even though the pipeline writes those same metrics **authoritatively to local disk** (`save_evaluations()` saves `eval_*.parquet`, *then* also logs to WandB). The report therefore reads a **mutable, eventually-consistent, network/version/environment-dependent remote replica of a value it already has on disk** — two sources of truth, wrong one chosen. This single design choice is the upstream **root cause** of the entire #105/#106/#177 saga: offline-run-has-no-cloud-project, silent constituent drops, the `None`-vs-raise contract (#177), the `retry`/`strict_constituents` symptom-management in #105, the "Could not find project" string-matching, and the conda-editable-vs-`.venv`-pinned-vs-published pipeline-core version skew. It can produce **silent wrong output** (a report that omits/mislabels constituents) — **elevate toward Tier 1 if that is ever observed in the production runtime**; Tier 2 today because production reports are generated in the conda `views_pipeline` env (editable pipeline-core *with* #177) and CI mocks the call (see C-46). **Remediation is UNCERTAIN and not yet decided (deliberately):** reading the local `eval_*.parquet` instead of the cloud is the obvious candidate and would delete the whole failure class, **but it is NOT assumed viable for the larger/distributed setup** — constituent models may be trained/evaluated on different machines or at different times, so their local eval files may not be co-located on the machine that builds the ensemble report (likely *why* the cloud fetch exists). Candidate mechanisms (read-local / caller-injects-resolved-runs / a real metrics-store abstraction) are an open **team design question**. Logged as "one day we will fix this; solution undecided," not an action item now. #105/`strict_constituents` make the gap *visible* but do not remove the coupling. **CONFIRMED MECHANISM + EVIDENCE (2026-06-18, multi-agent WandB investigation):** the defect is sharper than "wrong replica" — `get_latest_run` selects each model's **most-recently-*created*** run, **not** the latest run that actually carries the canonical eval metrics. Verified against live WandB for a real production ensemble report (target `lr_ged_sb`, `run_type=calibration`) by replaying the report's own `format_evaluation_dict` + `search_for_item_name` logic per run: **22 of 25 constituents render "not calculated" for ALL canonical reg-point metrics (MSLE/MSE/MCR_point/y_hat_bar) solely because the selected run lacks them, while an EARLIER run holds the full set under the exact expected key `time-series-wise/lr_ged_sb/<metric>_mean`.** The selected runs carry zero eval-metric keys under *any* eval_type/target (so it is **not** name/target drift) and have `_timestamp=null` (non-eval runs created after the eval run). Heavily re-run models are worst hit (run counts e.g. fast_car 204, brown_cheese 396, bittersweet_symphony 534). The 3 that render values (chunky_bunny, average_cmbaseline, zero_cmbaseline) are simply those whose newest run *happens* to be the eval run. The visible note ("add '<metric>' to `regression_point_metrics`") actively **misdirects** the user toward a config change when the real cause is run selection and the data already exists in an earlier run. **This is the elevation trigger firing in the production runtime** — the report is largely useless/misleading, observed (not latent). Kept Tier 2 because the failure is *visible* ("not calculated" notes), not a silently-wrong *number* — but it carries a latent **Tier-1** path: a model with multiple metric-bearing runs could have `get_latest_run` pick the wrong eval run and show a plausible-but-wrong NUMBER with no note. **Added remediation candidate:** metric-aware run selection (pick the latest run that actually contains the canonical metrics) — narrower than read-local and would fix the observed 22/25 case; read-local from `eval_*.parquet` (original C-48 framing) remains the durable option. Both stay a team design decision. **STATUS UPDATE (review-rr 2026-06-22):** the observed 22/25 production failure is now **mitigated by the shipped interim** (metric-aware run selection, #116 — see C-110); the "firing in production / observed (not latent)" framing above is **historical (pre-#116)**. What remains open in C-48 is the **durable** source-of-truth fix (read-local / injected `MetricFrame`), gated on views-frames (C-108). |
| Cross-refs | C-46 (tests mock `get_latest_run` → CI cannot catch the env/version skew — false confidence); C-27 (WandB hard runtime dependency for eval reports); C-22 (viewser — same render-time data-acquisition pattern); C-44 (undeclared wandb/viewser deps); C-36 (upstream pin caps); Cluster A. #177 (pipeline-core get_latest_run contract); #105/#106 (symptom-management layer above this root cause); C-110 (the interim metric-aware-selection remediation can itself trade this visible failure for a silent wrong number if done without scoping/ambiguity guards). |

### C-108: views-reporting acquires & classifies its inputs at render time instead of receiving them through an injected contract (the Cluster A root)

| Field | Value |
|-------|-------|
| ID | C-108 |
| Tier | 2 |
| Source | expert-code-review + expert-method-review (architecture/methodology synthesis, 2026-06-19) |
| Trigger | When a new report data-need (a metric, a new metadata field, a new input) is satisfied by adding a **render-time fetch** (a `get_latest_run` / viewser / other service call inside a template or accessor) rather than by **receiving** it as an injected, typed input — each such addition deepens the coupling and adds an environment/version-dependent failure path |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_report_content` → live `get_latest_run`); `views_reporting/metadata/entity_metadata.py` (live viewser `Queryset(...).publish().fetch()`). Contrast the compliant `forecast.py` (receives data) and `loaders/` (ADR-012 injected declared-format adapters). |
| Narrative | This is the **root cause** the rest of Cluster A are symptoms of. views-reporting is supposed to be a *render-from-given-data* layer (ADR-001/002: "depend on pipeline-core **containers**, not services") — and `forecast.py` + the loaders already are. But the evaluation template and the metadata accessors **acquire and classify their inputs at render time** by calling live external services. That single inversion of the dependency direction generates: C-48 (wandb eval scrape → wrong run), C-22 (viewser fetch), C-27 (wandb runtime dependency), C-44 (undeclared wandb/viewser), and C-46 (tests must mock the fetch → false confidence). **Methodology corollary (expert-method-review):** there is no declared *evaluation-of-record* — the source of truth for an evaluation is forecasts + actuals + the proper scoring rule (a re-derivable, transportable artifact), and the report mis-locates it at a mutable cache (wandb/parquet). **Remediation (the roadmap's north star):** dependency-invert onto a stable contract — reporting receives a typed `MetricFrame`/`PredictionFrame` (future **views-frames**) through an injected `EvaluationSource` adapter; scoring stays in **views-evaluation**; the source (store / files / wandb) becomes a swappable leaf adapter. Resolving this one entry dissolves most of Cluster A at once. Gated on views-frames existing + views-evaluation emitting a `MetricFrame` (see `documentation/roadmap_to_1.0.0.md` Phases 2–3); the Phase-1 interim is metric-aware run selection (C-48). |
| Cross-refs | **Root of Cluster A.** C-48 (wandb eval scrape — the confirmed instance), C-22 (viewser), C-27 (wandb runtime), C-44 (undeclared deps), C-46 (tests mock the fetch — false confidence), C-34 (provenance — what the injected contract should also carry), C-41 (non-uniform scoring / canonical-token drift — a views-evaluation-owned sibling); ADR-002 (depend on containers not services), ADR-012 (the injected-adapter pattern to extend); **ADR-018 (the written responsibility mandate that declares this inversion — #117)**; views-frames `MetricFrame` (the target contract). |

### C-109: Uncertainty is communicated as MAP/HDI, not as exceedance/threshold probabilities + calibration the conflict audience needs

| Field | Value |
|-------|-------|
| ID | C-109 |
| Tier | 3 |
| Source | expert-method-review (library-grounded, 2026-06-19) |
| Trigger | When a forecast/evaluation report is delivered to a conflict-escalation decision audience (e.g. partner deliverables, UN FAO) and the question is "how likely is escalation beyond threshold X" — the report shows a central HDI + a MAP point, not the decision-relevant exceedance probability or its calibration |
| Location | `views_reporting/visualizations/historical.py` (HDI bands), `views_reporting/visualizations/distributions.py` (MAP/HDI overlays), `views_reporting/templates/reports/forecast.py` (uncertainty surface of the forecast report) |
| Narrative | The reports communicate forecast uncertainty via **MAP** (modal point estimate) and **HDI** (central credible intervals). For a heavy-tailed, zero-inflated conflict process and a policy/partner decision audience, the decision-relevant quantities are **exceedance / threshold probabilities** (P(escalation beyond X)) and their **calibration**, not a central interval — and **MAP is a weak, potentially misleading point summary** of a skewed conflict posterior (the mode is not the decision-relevant location). Grounded in the library: *Lerch2017* (the forecaster's dilemma — evaluating/communicating extremes), *Gneiting2014* (sharpness subject to calibration), *Radford2022 / Hegre* (the conflict-forecasting domain). This is a *communication-appropriateness* gap for the decision-maker, **distinct from C-35** which concerns the *numerical correctness* of MAP/HDI on pathological posteriors. Remediation: add exceedance/threshold-probability views + calibration plots alongside (or in place of) the MAP-centric summary; roadmap Phase 4. |
| Cross-refs | C-35 (MAP/HDI numerical correctness — sibling, different axis: correctness vs decision-appropriateness); ADR-017 (canonical metrics — calibration/MCR already in the standard); `documentation/roadmap_to_1.0.0.md` Phase 4. |

### C-110: The C-48 interim fix (metric-aware run selection) can trade a visible "not calculated" for a silent wrong number

| Field | Value |
|-------|-------|
| ID | C-110 |
| Tier | 2 (latent Tier 1) |
| Source | expert-code-review (Sprint-1 epic review — Kleppmann seat, 2026-06-19) |
| Trigger | When a constituent's authoritative evaluation run is **re-logged under the same partition/level** (a stale re-log — an older eval re-run and re-uploaded), the metric-aware resolver (#116) cannot distinguish it from the original without provenance and may select it, rendering a plausible-but-wrong number silently. (The original pre-implementation hazard — selecting a wrong-*partition* run — is **closed**: the cross-constituent partition/level check raises loudly on it; see "AS IMPLEMENTED" below. Trigger refreshed to the residual by review-rr 2026-06-22.) |
| Location | `views_reporting/templates/reports/evaluation_run_resolver.py` (the interim metric-aware selection seam, #116); consumed by `evaluation.py` `_add_report_content` (cross-constituent partition/level guard) |
| Narrative | C-48's interim remediation makes constituent run-selection metric-aware (pick the latest run that *carries* the canonical metrics rather than the latest-*created* run). Done naively — "latest run with ANY/ALL canonical metric tokens" — this can be **worse** than the current failure: today a metric-less run yields a *visible* "not calculated"; a naive metric-aware selector that finds the *wrong* metric-bearing run among several would render a **silent wrong number** (right place, wrong evaluation) with no signal — exactly C-48's latent Tier-1 path, now *actively reachable* because the fix starts choosing among metric-bearing runs. Two hazards: (1) **ambiguity** — multiple runs carry the canonical set under different partitions/levels; recency alone is not run *identity*. (2) **mixing** — assembling one metric row from metrics drawn from different runs (a single row must come from a single evaluation). **Implementable guard (falsify P3, 2026-06-19 — corrected against the actual site `evaluation.py:187`):** at the selection site only `run_type` is an *a-priori* scope (it picks the wandb project `{model}_{run_type}`); `partition`/`level` are read from each run's `.config` *after* fetch (the existing consistency check at `evaluation.py:223-244`), and there is no `window` selection key. So the guard is: enumerate runs in the `run_type`-scoped project, pick the latest whose summary carries the canonical metric tokens, then **verify that selected run's `partition`/`level` metadata is consistent across constituents** (re-point the existing L223 check at the selected run, not at `get_latest_run`'s newest run); on **ambiguity** (more than one equally-valid metric-bearing run) **degrade-and-announce, never guess**; never source a single metric row from more than one run; emit an observability log when a fallback selection is used; implement the selection behind a `_select_eval_run(...)` **seam** so the durable views-frames `MetricFrame` adapter (C-108) replaces it cleanly. The regression test must use the synthetic `tests/_wandb_doubles.py` double (multiple runs per model), **not** an on-disk `*.parquet` fixture (gitignored → would skip in CI, the C-46 trap). **AS IMPLEMENTED (#116, 2026-06-19):** selection lives in the `evaluation_run_resolver` seam (self-contained, public `wandb.Api` — SDP); it picks the **newest run carrying any canonical metric token for the target**, and the **existing cross-constituent partition/level check (`evaluation.py`) is the loud guard** — it operates on the *selected* runs and `raise`s on a mismatched-partition run, so a wrong-partition number surfaces **loudly, never silently**. The earlier "within-model ambiguity → degrade" idea was **deliberately dropped**: "more than one metric-bearing run" is the *normal* case for re-run models, so degrading on it would re-blank exactly the constituents this fix targets; "newest on a consistent partition" is a defined rule, not a guess. **Residual (why this stays open):** a same-partition *stale re-log* (an older eval re-logged, same partition metadata) is indistinguishable from the authoritative run without provenance, so its number could render silently — a **latent Tier-1** path **closed only by the Phase-3 `MetricFrame` provenance (C-108)**. Tests: `tests/test_falsify_sprint1_readiness.py` (metric-aware selection, partition-check-on-selected-run, loud cross-constituent raise, one-row-one-run, the 22/25 regression). Tier 2 today; **elevate to Tier 1 if a stale-re-log wrong number is ever observed.** |
| Cross-refs | C-48 (the defect + the interim remediation this sharpens — the latent-Tier-1 note there is what this entry makes actively reachable), C-108 (the durable `MetricFrame` fix that retires this selection), C-41 (canonical-token drift — adjacent "not calculated" cause); Cluster A; GitHub #116 (where the guards must land). |

### C-111: No input-completeness validation at the report boundary — incomplete input renders silently

| Field | Value |
|-------|-------|
| ID | C-111 |
| Tier | 3 |
| Source | review-rr strategic (blind-spot analysis, 2026-06-22) |
| Trigger | When a report is generated from a prediction/eval input that is incomplete or malformed — a truncated/partial prediction file, missing months, NaN-filled samples, or a frame missing expected entities — nothing asserts input completeness before rendering, so the report renders a silently-partial result with no error signal |
| Location | `views_reporting/loaders/` (the ingestion adapters that receive predictions, ADR-012); consumed by `views_reporting/templates/reports/forecast.py` without a completeness assertion. Contrast C-29, which checks the transform/join assuming the input is already good. |
| Narrative | The reports **receive** predictions through the ingestion loaders and render them. C-29 covers render≠source *fidelity* (the transform/join dropping rows) but **assumes the received input is itself complete**. Nothing validates that the input frame is well-formed and complete — correct shape, no unexpected NaN in the sample axis, expected entity/time coverage — before rendering. A truncated prediction file, a frame missing months, or NaN-filled samples would render as a silently-partial report (the join-drop of 26 island states / 936 rows noted in C-29 is one observed instance of silent reduction; **input-side incompleteness is the un-tracked sibling**). Assurance gap, not a demonstrated defect, and the input is normally produced by the trusted pipeline — hence Tier 3 (same silent-class calibration as C-29/C-35), **elevate to Tier 1 if a silently-partial render from incomplete input is ever observed**. Remediation: an input-completeness assertion at the ingestion boundary (shape / NaN / coverage checks; fail-loud or visible-note on incompleteness) — naturally part of the value-correctness & contract assurance work, and the natural home is the typed input contract (C-108). **ADVANCED, not closed (epic #137 S5, #140):** the loaders now run `views_frames.conformance.assert_frame_contract` on every ingested frame (ADR-009 §1b) and the conformance floor is pinned — this fail-loud gate covers the **structural** contract (float32 values + explicit sample axis, complete integer `time`/`unit` identifiers of length `n_rows`, save/load round-trip). **Residual (stays Tier 3, open):** the contract does **not** reject NaN in the *values* axis nor verify expected time/entity *coverage* (a truncated/partial frame still passes), so the semantic-completeness half remains — to be closed by a coverage/NaN check or the Phase-3 typed input contract (C-108). |
| Cross-refs | C-29 (render≠source fidelity — the sibling that assumes good input); C-108 (the injected typed-contract direction where this validation belongs); C-35 (sibling assurance-gap calibration); Cluster F (value-correctness & contract assurance). |

### C-112: Bundled static reference data can silently go stale (forward risk created by the C-22 remediation)

| Field | Value |
|-------|-------|
| ID | C-112 |
| Tier | 4 |
| Source | review-rr strategic (blind-spot analysis — forward risk, 2026-06-22) |
| Trigger | When the C-22 remediation replaces the live VIEWSER querysets with a bundled static lookup table (pgid → lat/lon/row/col/iso3/name/gwcode) — from that point the bundled table can drift from upstream reference data (country border/code changes, GW-code reassignment, new/retired PRIO-GRID cells) with no refresh signal |
| Location | (future) the bundled static metadata table introduced by the C-22 remediation, replacing the live `Queryset(...).publish().fetch()` calls in `views_reporting/metadata/entity_metadata.py` |
| Narrative | C-22's recommended remediation swaps live VIEWSER fetches for a bundled static lookup table. That removes the runtime-dependency fragility but introduces the **opposite** risk: static reference data ages. Country names/ISO codes change, GW codes get reassigned, and PRIO-GRID cells can be added/retired; a frozen bundled table would silently serve **stale geography** (wrong label / wrong join) with no error signal. It does **not exist today** — Tier 4, forward/latent, no current incorrectness — but it becomes real the moment the bundled table ships and would warrant Tier 2–3 then. Registered now so the C-22 fix does not trade one silent risk for another unnoticed. Remediation (to pair with the C-22 fix): stamp the table with a version + source-date, document a refresh cadence, and add a checksum/regeneration check. |
| Cross-refs | C-22 (the remediation that creates this risk — pair them); C-39 (the accessor tests that would also cover the bundled table); Cluster F (assurance). |

### C-113: Observed/actuals data provenance & validation is untracked

| Field | Value |
|-------|-------|
| ID | C-113 |
| Tier | 4 |
| Source | review-rr strategic (blind-spot analysis, 2026-06-22) |
| Trigger | When the observed-history ("actuals") overlay in a report is re-sourced or refreshed (a change to where observed values come from), or when a partner questions whether the plotted observed line is the authoritative actuals — nothing validates or stamps the observed-data source |
| Location | `views_reporting/visualizations/historical.py` (the observed-history overlay) and the observed-data read path feeding it |
| Narrative | Reports overlay "observed history" against predictions (`historical.py`). C-37 (resolved) addressed only the *cutoff-line semantics* of that overlay, not the **provenance or validation of the observed values themselves** — where the actuals come from, whether they are the authoritative version, and whether they are validated before plotting. For a partner-facing forecast-vs-actuals chart, an unstated/unvalidated actuals source is a minor traceability/assurance gap — it underpins the very visual the partner judges accuracy by. Tier 4: no demonstrated defect, low likelihood, and partly subsumed once C-34 provenance lands. Remediation: document/validate the observed-data source and fold it into the C-34 provenance stamp. |
| Cross-refs | C-34 (provenance — the observed source should be stamped too); C-37 (resolved — cutoff semantics of the same overlay); C-29 (render fidelity); Cluster F (assurance). |

### C-114: views-reporting imports pipeline-core *private* dataset internals (`_CDataset`/`_PGDataset`/`_ViewsDataset`) across the repo boundary

| Field | Value |
|-------|-------|
| ID | C-114 |
| Tier | 2 |
| Source | gh-issue review (grounded in #138's brief + verified imports, 2026-06-22) |
| Trigger | When pipeline-core refactors, renames, moves, or changes the contract of its **private** dataset internals `_CDataset` / `_PGDataset` / `_ViewsDataset` (or relocates `views_pipeline_core.data.handlers`) — views-reporting imports them directly and would break with no contract, deprecation path, or version signal; also any audit of cross-repo boundary conformance |
| Location | `views_reporting/reconciliation/reconciliation.py:12`, `reconciliation/dataset_export.py:13`, `metadata/entity_metadata.py:13,521,531`, `statistics/dataset_statistics.py:17` (the **private** `_CDataset`/`_PGDataset`/`_ViewsDataset`); plus public `PGMDataset`/`CMDataset` imports in `mapping/mapping.py`, `visualizations/historical.py`, `loaders/_protocol.py` (lower concern — those names are public) |
| Narrative | views-reporting reaches across the repo boundary into pipeline-core's **private** dataset internals — underscore-prefixed `_CDataset`/`_PGDataset`/`_ViewsDataset` from `views_pipeline_core.data.handlers` — at **8 sites across 4 modules**. Importing another package's underscore-prefixed names is an unprotected coupling: pipeline-core owes no stability guarantee on private symbols, so a refactor/rename/move there breaks reporting with no contract and no deprecation path. This is the **"cross-repo private leakage"** the roadmap names as **C-135's reporting side** — where **C-135 is a pipeline-core register ID, not previously registered in this repo's register** (this entry fills that gap). Fails **loud** (ImportError/AttributeError on the next pipeline-core internal change), not silent → Tier 2 structural fragility with a realistic trigger (pipeline-core is actively evolving these, and the frames migration touches them). It is the **compile-time-coupling sibling of C-108's runtime service-acquisition** (both Cluster A, both dissolved by the same inversion). Remediation: adopt **views-frames** (#137/#138) so the data contract routes through the leaf's published `PredictionFrame`/`SpatioTemporalIndex`/`SpatialLevel` (which import nothing internal), replacing the private reads — the same move that breaks the #113 cycle. Until then the coupling is load-bearing and unguarded. |
| Cross-refs | C-108 (Cluster A root — the runtime-service-acquisition sibling of this compile-time coupling); C-30 (RESOLVED — the *sanctioned* prediction-manager boundary, a different and governed exception); C-13 (RESOLVED — an *internal* cross-module private import, distinct); #138 (the views-frames adoption move that removes this); #113 (the import cycle the same leaf routing breaks); roadmap C-135 / C-184 (the pipeline-core-side IDs this is the reporting side of); Cluster A. **Remediation in progress: epic #137 — S0 (ADR framing) landed; the private `_C/_PG/_ViewsDataset` reads are dropped by S4 (loaders) and S6 (render).** |

---

### C-116: `search_for_item_name` returns the first of multiple matches after only a log warning — a silent wrong-metric-value path

| Field | Value |
|-------|-------|
| ID | C-116 |
| Tier | 2 |
| Source | repo-assimilation (2026-06-22) |
| Trigger | When `views_evaluation` or a model config introduces a metric token that segment-matches another within the same `(task, pred_type)` cell, or when two eval-dict keys both match `[eval_type, metric, target, "mean"]` (e.g. overlapping target identifiers) — the report then shows the first match's number with no in-report signal |
| Location | `views_reporting/reports/utils.py:100-105` (`search_for_item_name` logs a WARNING on >1 match, then `return matches[0]`); consumed by `views_reporting/templates/reports/evaluation.py:328` (`_canonical_row`) and `views_reporting/templates/reports/evaluation_run_resolver.py:89` (`_carries_canonical_metrics`) |
| Narrative | The canonical-metric pipeline pulls each value by segment-matching a metric token against the WandB eval dict. When more than one key matches, `search_for_item_name` emits a WARNING to the log but still returns `matches[0]`, so an ambiguous match surfaces a possibly-wrong numeric metric into a partner-facing table with no in-report indication — the only signal is a log line a report consumer never sees. This is the **wrong-number** failure mode that C-41 explicitly excludes ("bounds damage to confusion, not wrong numbers"): C-41 covers a canonical name that *stops* matching (→ visible "not calculated"); this covers a canonical name that matches *too much* (→ silent wrong value). The sole current guard is the documented, **unenforced** segment-prefix naming rule in `config/_reporting.py:30-43` (no name may be a `/_-`-bounded prefix of another in a cell). Tier 2, not Tier 1: there is a log signal and a realistic structural trigger (cross-repo metric tokens evolve), but the in-report silence makes it more than maintainability. **Elevate to Tier 1 if an ambiguous-match wrong number is ever observed in a rendered report.** Remediation: fail loud (or render an explicit "ambiguous" cell) on multi-match, and add a contract test asserting the canonical map against a real run's summary tokens has no collisions. |
| Cross-refs | C-41 (sibling: name-drift → "not calculated"; this is the multi-match → wrong-value complement); C-110 (the C-48 interim fix's own silent-wrong-number path); C-29 (render-fidelity assurance gap); Cluster F (value-correctness & contract assurance) |

---

### C-117: `ReportModule.add_html` injects unescaped HTML while the rest of the builder is XSS-hardened

| Field | Value |
|-------|-------|
| ID | C-117 |
| Tier | 4 |
| Source | repo-assimilation (2026-06-22) |
| Trigger | When a caller routes externally-influenced text (a model name, run note, user-supplied caption, or other non-plot string) through `add_html` instead of `add_paragraph`/`add_markdown`/`add_table` |
| Location | `views_reporting/reports/report.py:134-174` (`add_html` embeds its `html` argument verbatim), contrasted with `escape()` in `add_heading`/`add_paragraph`/`add_table`/`add_image` caption (`report.py:95,126,378`) |
| Narrative | The README advertises "XSS-safe content (`html.escape()` on all user-facing text)", and C-19 (resolved) added escaping to the text methods. `add_html` is a deliberate exception: it passes raw HTML through, which is required to embed Plotly figure HTML. That is correct for trusted plot output, but it means the invariant "all report text is escaped" is not globally true — report safety rests on the unstated assumption that callers only ever send trusted/generated HTML to `add_html`. No current call site violates this (all `add_html` inputs are Plotly/figure HTML), so there is no live defect (Tier 4). The risk is a future caller treating `add_html` as a general text sink. Remediation: document the trust boundary at the method (and in the README claim), or split a sanitised path from the raw-figure path. |
| Cross-refs | C-19 (RESOLVED — text-method escaping; this is the intentional raw-HTML complement) |

---

### C-118: `loaders/__init__` registers loaders as an import-time side effect, coupling package import to global-registry mutation

| Field | Value |
|-------|-------|
| ID | C-118 |
| Tier | 4 |
| Source | repo-assimilation (2026-06-22) |
| Trigger | When a caller wants to import the loader facade or `PredictionLoader` protocol without triggering a `views_pipeline_core` import, or when any code path causes `views_reporting.loaders` registration to run twice |
| Location | `views_reporting/loaders/__init__.py:9-10` (`register_loader("dataframe", ...)` / `register_loader("prediction_frame", ...)` at module top); `views_reporting/loaders/_registry.py:21-27` (fail-loud on duplicate) |
| Narrative | `_protocol.py` and `_registry.py` were deliberately kept import-light (pipeline-core types referenced only under `TYPE_CHECKING`), but `loaders/__init__.py` runs `register_loader` at import time, which imports `dataframe_loader`/`prediction_frame_loader` and thereby eagerly pulls `views_pipeline_core.data.handlers`. So merely importing the loaders package executes registry mutation and the heavy pipeline-core import, undoing the import-light intent of the registry layer. `register_loader` is fail-loud on duplicates, so any re-registration path raises `ValueError`. Localized and not a correctness risk (Tier 4); the cost is hidden global state at import and a heavier-than-necessary import surface. Remediation: lazy registration (register on first `get_loader`) or an explicit `register_default_loaders()` call, keeping the package importable without the eager pipeline-core dependency. |
| Cross-refs | C-114 (the pipeline-core coupling this eager import participates in); Cluster A (external dependency coupling at import) |

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
| Resolution | Unresolved but **low-stakes and parked**: adopt Beck's view (inline 3-line computation is fine) unless a trigger fires. **Trigger to revisit:** when a second, compute-free consumer of PlotDistribution appears (a caller that already holds pre-computed stats and must not recompute). Until then, no action. (review-rr 2026-06-22) |

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
| Resolution | **Resolved (epic #137 S7, #148, 2026-06-23) — committed to *return a value, don't mutate* (Feathers/Hickey).** `reconcile()` now assembles reconciled cells into a fresh `result_df` and returns it; the input `pg_dataset.reconciled_dataframe` is no longer written (de-mutation; closes the cross-repo-mutation concern C-184 on the reporting side). Non-breaking: pipeline-core's ensemble managers consume the return value (`return reconciliation_manager.reconcile()`), not the side effect. Independent of the still-open relocation question (GitHub #72 / C-24 / Cluster B); Nygard's partial-failure-signal point remains a separate gap (reconciliation CIC Deviation #3). |

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

### C-115: README documented a `transformations/` package that no longer exists — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-115 |
| Resolved | 2026-06-22 |
| Resolution | **Fixed during review-rr (2026-06-22), same session as registration.** Removed the two stale `transformations` references from `README.md` (the five-layer architecture table and the project-structure tree) and deleted the orphaned `views_reporting/transformations/__pycache__/` directory (untracked `.pyc` files only). The README layer inventory now matches the code after the #119 / C-25 transformations removal. A Tier-4 mechanical doc fix; resolved immediately rather than carried as a standing risk entry. |
| Cross-refs | C-25 (RESOLVED — the transformations removal that created this drift); Cluster E; C-17 (RESOLVED — prior README staleness). |

---

### C-45: Eval sample-graph path silently defaulted `level` to `cm` — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-45 |
| Tier | 4 |
| Source | repo-assimilation (2026-06-18) |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_prediction_sample_graphs`) |
| Narrative | The eval sample-graphs path resolved the level with `self.config.get("level", "cm")` — a PGM model with a missing/typo'd `level` was silently treated as `cm`, picking the wrong `Dataset` class. Non-corrupting (the section is non-fatal, C-40) but an inconsistent fail-loud posture vs `forecast.py`'s required-key raise. |
| Resolution | **Fixed (#130, Sprint 2, 2026-06-21).** Removed the silent `"cm"` default: a missing/unknown `level` now resolves to a **visible skip** (`_note_unavailable("missing 'level' in config" / "unknown level '…'")` + a `logger.warning`) instead of silently mis-defaulting; the redundant second `level` re-fetch was also removed. Chose visible-skip over a hard `raise` (unlike forecast.py, which is fatal) because the sample-graphs section is **non-fatal** (C-40) — a missing level should not crash the whole report. Verified by inspection + the existing visible-skip tests; a dedicated unit test of this branch would need the gitignored prediction fixtures (the C-46 trap), so it is covered behaviourally. |
| Cross-refs | C-40 (visible skips — the bound); ADR-008 (fail-loud / visible degradation); ADR-003 (declarations over inference); epic #133 / story #130. |

### C-107: `ReportModule.add_markdown()` silently degraded on missing `markdown` — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-107 |
| Tier | 4 |
| Source | Migrated from views-pipeline-core C-133 (2026-06-19); origin falsify (2026-05-28) |
| Location | `views_reporting/reports/report.py` (`ReportModule.add_markdown()`) |
| Narrative | `add_markdown()` caught `ImportError` for the `markdown` package and fell back to plain text with **no log** (the module imported no `logging`) — monitoring had no signal the report was degraded (ADR-008 §Degraded-Operation violation). |
| Resolution | **Fixed (#130, Sprint 2, 2026-06-21).** Added a module logger to `report.py` and a `logger.warning(...)` **before** the plain-text fallback, so the degradation is programmatically visible (not just a user-facing HTML note). Guarded by `tests/test_report_module_degradation.py` (simulates a `markdown` `ImportError`; asserts the WARNING is logged + the plain-text fallback still renders). |
| Cross-refs | ADR-008 (fail-loud / degraded operation); pipeline-core C-133 (origin); epic #133 / story #130. |

### C-43: Compute-layer module imported the Render layer (ADR-002 direction inversion) — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-43 |
| Tier | 3 |
| Source | repo-assimilation (2026-06-18) |
| Location | (removed) `views_reporting/statistics/dataset_visualization.py` |
| Narrative | `statistics/dataset_visualization.py`'s `plot_map`/`plot_hdi` imported the Render-layer `visualizations.PlotDistribution` from a Compute-layer module — reversing ADR-002's ingestion→compute→render→compose direction. The two wrappers were thin pass-throughs with **zero production callers** (re-exported from `statistics/__init__.py` but unused). |
| Resolution | **Deleted (#129, Sprint 2, 2026-06-21).** Confirmed dead by a repo-wide grep (no callers anywhere — the only live `plot_map` is the unrelated `MappingModule.plot_map`); removed `dataset_visualization.py` entirely, its two `statistics/__init__.py` re-exports, and the file's entry in `tests/test_falsification_discoverability.py` `CORE_MODULES`. The ADR-002 inversion is gone. Deletion was preferred over relocation since the wrappers were dead — resurrect from git in the `visualizations` layer if single-cell MAP/HDI plotting is ever wanted. |
| Cross-refs | ADR-002 (topology); D-06/C-13 (the correct direction — Render importing from Compute); C-25 (sibling dead-surface, also deleted); epic #133 / story #129. |

### C-44: Direct imports of `wandb` and `viewser` were not declared in `pyproject.toml` — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-44 |
| Tier | 3 |
| Source | repo-assimilation (2026-06-18) |
| Location | `views_reporting/templates/reports/evaluation.py`, `templates/reports/evaluation_run_resolver.py`, `reconciliation/reconciliation.py` (`import wandb`); `metadata/entity_metadata.py` (`from viewser import …`) |
| Narrative | Production code imports `wandb` and `viewser` directly, but `pyproject.toml` declared only `views-pipeline-core` — both were pulled in **transitively**, so the package worked only by accident of the transitive graph; an upstream dependency-tree change would have broken first-party imports with no lockfile-visible signal. Fails loud (ImportError), not silent — Tier 3. |
| Resolution | **Declared (#120, 2026-06-21).** Added `wandb>=0.18.7,<0.19.0` and `viewser>=6.6.4,<7.0.0` to `[project].dependencies` — ranges match pipeline-core's `^0.18.7` / `^6.6.4` to avoid resolver conflicts (respecting the C-36 3.11 bound); `uv.lock` relocked (no version change — both were already resolved transitively, lockfile +4 edges). Guarded by `tests/test_declared_dependencies.py`, which fails loud if either declaration is dropped while the import remains. **INTERIM:** both leave the render path in Phase 3 (C-108) — `wandb` once reporting consumes an injected `MetricFrame`, `viewser` per the C-22 retirement (bundled / factory-sourced metadata); the declarations are removed then. |
| Cross-refs | C-22 (viewser retirement), C-27 (WandB runtime coupling), C-36 (upstream pins / the 3.11 bound), C-108 (the inversion that ultimately removes both); ADR-014 (build tooling); Cluster A (a symptom, not the root — declaring the deps does not dissolve the cluster). |

### C-25: DatasetTransformationModule — 1,501 LOC of legacy with zero live consumers — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-25 |
| Tier | 4 |
| Source | external-review (datafactory migration assessment) + consumer verification |
| Location | (removed) `views_reporting/transformations/transformations.py` |
| Narrative | `DatasetTransformationModule` managed the ln/lx/lr log-transform lifecycle with column-name tracking — labelled legacy per ADR-011 (this repo expects original-scale data; transform inference retired), with **zero production callers** and the **sole consumer of `polars` within views-reporting**. The open tail of Cluster E. |
| Resolution | **Deleted (#119, 2026-06-20).** Removed `views_reporting/transformations/` (module + README), `tests/test_transformations.py`, and the module CIC; updated `tests/test_falsification_discoverability.py`; dropped the **direct** `polars` declaration from `pyproject.toml` + relocked `uv.lock` (polars remains a *transitive* dep via views-pipeline-core, which declares it directly — the install footprint is unchanged until pipeline-core drops it; out of scope here). Governance updated: ADR-001 "Data Transformation" ontology category **retired** (audit marker left), ADR-011 reworded (principle kept), roadmap + CIC index + forecast-template CIC + INSTANTIATION_CHECKLIST + physical-architecture standard updated. **Cross-repo deletion qualified GREEN beforehand:** a GitHub-org code search (`gh api search/code`) + a local sweep of all ~18 platform repos found **zero importers** of `DatasetTransformationModule` / `views_reporting.transformations` / `views_pipeline_core.modules.transformations` — the only non-pipeline-core hits were views-stepshifter *docs* that explicitly **reject** reuse. The pipeline-core re-export shim + its orphaned tests are retired **separately** under the cross-repo epic **#126** as **views-platform/views-pipeline-core#183** (shim-set policy: views-pipeline-core#184, C-168). Resolves the open tail of **Cluster E**. |
| Cross-refs | ADR-011, ADR-001; C-10 (retired prefix convention); Cluster E; epic #126; pipeline-core shim removal views-platform/views-pipeline-core#183. |

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
- **ID numbering:** the native sequence ran C-01–C-48; the register then jumped to **C-107** (migrated from pipeline-core C-133, 2026-06-19) and continues C-108+ (now through C-118). The **C-49–C-106 range is intentionally unused** (no backfill); new entries continue from the current maximum.

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
