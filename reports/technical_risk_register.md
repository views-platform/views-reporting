# Technical Risk Register

**Last updated:** 2026-08-03
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 78 concerns (67 resolved, 11 open) + 5 disagreements (4 resolved)

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
| **A — External runtime dependencies** | **C-108 root: reporting *acquires/classifies* inputs at render time instead of *receiving* them through an injected contract.** Report generation/viewing needs external services with no offline/bundled fallback | **C-108 (root) ✓**, C-22 (VIEWSER), C-27 (WandB) ✓, C-44 ✓ (deps now declared — #120), C-46 (tests mock the fetch), C-48 ✓ (reads cloud metric replica — confirmed instance / #105/#106/#177 saga), C-110 ✓ (interim-fix mis-selection risk), C-114 ✓ (imported pipeline-core *private* dataset internals — compile-time coupling; closed 2026-07-02 by deleting the dead dataset-parameter accessor surface), C-22 ✓ (viewser runtime dependency — closed 2026-07-05 by the bundled metadata assets, epic #204) | **DISSOLVED (2026-07-05, epic #204): C-22 ✓ closed the last member — no render-path service acquisition remains; reports render fully offline (air-gapped / UN FAO delivery unblocked).** Successor forward risk: C-112 (bundled-data staleness, Cluster F, activated with guards). *(Correction: this row previously glossed "C-46" as "tests mock the fetch" — a mis-ID. The mocked-fetch assurance concern was C-39's scope, closed by the S3 unmocked e2e; the actual C-46 entry is the local≠CI divergence incident, unrelated to this cluster, still open.)* |
| **B — Reconciliation placement** | Reconciliation lives in a *reporting* repo but likely belongs in views-postprocessing | C-24 (torch), C-33 (determinism), D-08, D-09 | **RESOLVED (2026-06-28, #72): reconciliation deleted from views-reporting — it now lives in views-frames as `views_frames_reconcile` (parity-proven; consumed via pipeline-core's injected Reconciler protocol, wired in views-models). C-24 ✓, C-33 ✓, D-08 ✓ (moot), D-09 ✓. The reporting repo no longer carries torch/wandb for reconciliation.** |
| **C — PRIO-GRID scale discipline** | Repo handles ~260K-cell geodata without size discipline, at rest and at render | C-23 (shapefile in git), C-26 ✓ (render OOM → three-tier ladder), C-205 ✓ (globe legibility), C-209 (raster guard measures data rows, not the rendered lattice — reopened 2026-07-15, RESOLVED 2026-07-16), C-189 ✓ / C-190 ✓ (aggregation/omission methodology guards — closed superseded, ADR-021) | **Render side resolved (2026-06-29, globe epic #188): C-26 ✓ + C-205 ✓ — the three-tier choropleth → raster-heatmap → PNG ladder with a coastline overlay renders the full globe within budget. Remaining open: C-23 (56 MB cell shapefile committed — at-rest discipline).** C-189 ✓ / C-190 ✓ closed 2026-07-31 (superseded: ADR-021's per-cell-faithful raster/PNG designs the coarsening/subset path out; re-register if such a feature is ever proposed). |
| **D — Ingestion-layer boundary** | loaders/ crossed the pipeline-core boundary ahead of governance | C-30, C-31, C-32 | Resolved (PR #82) |
| **E — Legacy transform machinery** | RESOLVED (2026-06-20, #119) — `DatasetTransformationModule` removed + direct `polars` declaration dropped (polars stays transitive via pipeline-core) | C-25 ✓ (+ resolved C-10, C-04, C-02) | ✓ Resolved |
| **F — Value-correctness & contract assurance** | The load → compute → render → reconcile chain is tested for shape / does-not-crash, not for value equality, contract conformance, or input completeness | C-29 ✓ (render fidelity), C-35 ✓ (MAP/HDI correctness — render path + PosteriorDistributionAnalyzer both on the views-frames tower + law tests; RESOLVED, ADR-019 / #157), C-185 (`*_map` is a tower tip, not a MAP — naming debt), C-39 ✓ (metadata accessors untested — resolved, `tests/test_metadata_accessors.py`), C-41 ✓ (canonical-token contract test), C-116 ✓ (multi-match → silent wrong value — RESOLVED: fail-loud default + visible "ambiguous" cell + collision contract test), C-111 ✓ (input completeness — RESOLVED 2026-07-31, S4 #266), C-113 (actuals provenance), C-112 (bundled-data staleness — forward, pairs with C-22), C-186 ✓ (views-frames version → forecast-output drift), C-208 ✓ (gapped-lattice cell stretch/misplacement — rendering-geometry faithfulness, RESOLVED 2026-07-16), C-192 ✓ (cross-repo eval contract untested — RESOLVED 2026-07-31, executable seam test) (+ resolved C-01, C-11) | Open — highest latent severity; mostly "write the missing correctness/contract test" (an assurance sprint). Phase 1 (correctness/contract core) landed 2026-06-28: C-29 ✓ (render==source fidelity test), C-41 ✓ (canonical-metric contract test), C-111 values-half guarded. C-186 ✓ (tower behavioural-regime tests, Phase 2, 2026-06-28). Remaining: C-112 (guards live — watch the regen cadence), C-113 / C-185 (non-test); C-111 ✓ resolved (coverage checks, S4 #266); C-192 ✓ resolved (seam test landed, S2 #264); C-39 ✓ resolved (accessor tests landed, 2026-07). |
| **G — Partner-deliverable readiness** | Reports are built for internal preview, not yet hardened as a standalone, traceable, decision-appropriate *partner artifact* | C-28 ✓ (offline / self-contained — RESOLVED, vendored Tailwind, #132), C-34 ✓ (provenance / auditability — RESOLVED, footer stamp, #131), C-187 ✓ (vendored-CSS class coverage — RESOLVED, #132), C-188 ✓ (machine-readable provenance — RESOLVED, #132), C-109 (decision-appropriate uncertainty), C-214 ✓ (plotly-injection heuristics — RESOLVED 2026-07-31, S3 #265) | Open — C-109 (decision-appropriate uncertainty, partially delivered 2026-07: the #230 P(any) exceedance map layer) is the live remainder; C-214 ✓ resolved (S3 #265); offline + provenance now shipped |
| **H — Published-state qualification gap (dev-tandem ↔ PyPI seam)** | Contracts, pins, and names are qualified against dev branches moving in tandem, never against **published** artifacts — the coordinated publish (#179) is the single event where every deferred qualification fires at once | C-213 ✓ (root — vpc pin outran PyPI; import surface canonicalized + guarded 2026-07-31 S1 #263; ordering half resolved 2026-08-03 when vpc 3.0.0 published pre-qualified), C-192 ✓ (cross-repo seam untested — resolved S2 #264), C-36 (upstream transitive pins — re-probed at vpc's 2026-08-03 publish: envelope matches ours, ingester3==2.1.1 unchanged so the levenshtein wall persists), C-185 (rename waits on a coordinated cross-repo change), C-186 ✓ residual (b) (exact-pin views-frames for release), C-211 (partial — cross-repo decision, not publish-gated) | Open (added review-rr 2026-07-31) — mitigation is the #179 release-gate runbook (largely written); C-192's executable contract test landed (S2 #264); C-36 stays upstream-blocked regardless. **SECOND CONFIRMED FIRING (2026-08-02, v0.3.3):** 0.3.2's published `requires_dist` pin `views-evaluation>=0.4.0,<1.0.0` — qualified only against the dev-tandem git source — excluded views-evaluation **1.0.0** the day it hit PyPI, breaking platform co-resolution at the coordinated publish (caught by a sibling-repo agent). Fixed same-day: pin `>=1.0.0,<2.0.0`, interim git-source retired (its documented trigger fired), suite green against the RELEASED 1.0.0. The root cause has now bitten in production twice (vpc pin C-213(a) + this); every remaining dev-tandem git source (vpc, until their 3.0.0 publishes) carries the same latent defect until re-qualified at its publish. **CYCLE CLOSED (2026-08-03, #279):** vpc 3.0.0 published to PyPI carrying the pre-qualified pins (the vpc#313 warning worked — no third firing); the last dev-tandem git source retired, `views-reporting==0.3.3` co-resolves from PyPI alone, suite green against the released 3.0.0. **No dev-tandem git sources remain anywhere in pyproject/uv.lock** — the cluster's generating condition is discharged for this release cycle; it re-arises only if a future unreleased-dependency tandem is reintroduced. |

C-34 (provenance) and C-28 (offline) now anchor **Cluster G** (partner-deliverable readiness) rather than standing alone; the C-108 inversion does not fix C-28 (the exported HTML's view-time CDN dependency), which is why C-28 moved out of Cluster A.

---

## Open Concerns

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

### C-36: Installable surface is bounded to Python 3.11 + Linux/macOS by upstream transitive pins

| Field | Value |
|-------|-------|
| ID | C-36 |
| Tier | 2 |
| Source | falsify (hatchling+uv migration audit, 2026-06-04) |
| Trigger | When ingester3 bumps its `levenshtein` pin (or vpc drops ingester3/viewser) — re-probe 3.12–3.14 installs and update the tested-on claim; or when a user reports a 3.12+ install failing at the levenshtein build (expected-loud — point them to 3.11); or when a Windows install is attempted *(rewritten 2026-08-02 with the envelope decision — the old "adopting 3.12+ breaks resolution" half is retired: resolution now succeeds, the failure moved to the upstream build where it belongs)* |
| Location | `pyproject.toml` (`requires-python = ">=3.11,<3.15"` since 2026-08-02 — the platform envelope; `[tool.uv] environments = linux/darwin`); guard: `tests/test_packaging_invariants.py`; root cause upstream: `views-pipeline-core 3.0.0 → ingester3 2.1.1 → levenshtein 0.20.9`, and `viewser → docker → pywin32` |
| Narrative | Empirically (falsify probes), views-reporting only **installs on Python 3.11** and only **resolves on Linux/macOS**, both forced by upstream transitive pins it does not control. `levenshtein 0.20.9` (pulled via `views-pipeline-core → ingester3`, independent of the now-removed direct `views-transformation-library` dep) has no wheel and fails to build on 3.12 **and** 3.13; the `viewser → docker → pywin32` chain breaks universal Windows resolution. Failures are **loud** (pip refuses install / build error), not silent — hence Tier 2, not Tier 1. The constraint is bounded honestly via `requires-python<3.12` and uv environment scoping (ADR-014), but it caps the package's reach and **will block adoption when the ecosystem moves past 3.11**. Remediation is upstream: pipeline-core/ingester3 must update the `levenshtein` pin (and ideally drop the `pytest<9` runtime pin uv also surfaced), and viewser must shed the docker/pywin32 dependency (ties to the viewser retirement, C-22). views-reporting can widen `requires-python` and platform scope once upstream updates. **Update (2026-08-02, v0.3.2 — the cap DECISION is reversed; the practical bound is unchanged):** cross-repo friction surfaced during the coordinated release (sibling repos declare `<3.15`; our `<3.12` forced resolver exclusion of views-reporting in any 3.12+ platform env). Decision: **declare the platform envelope `>=3.11,<3.15`** (matching views-pipeline-core 3.0.0 and views-evaluation), enforced by `tests/test_packaging_invariants.py::test_requires_python_matches_platform_envelope`. Re-probed 2026-08-02: `levenshtein 0.20.9`'s last wheel is cp311 and its sdist build still fails on BOTH 3.12 and 3.13 (empirical uv-venv install probes), and vpc 3.0.0 still pins `ingester3 ==2.1.1` → the whole stack (vpc included, whose `<3.15` is equally aspirational) practically installs only on 3.11 — failures stay LOUD (build error at install). Tested-on remains 3.11. The entry stays open on the upstream half: ingester3's levenshtein pin (and the viewser→docker Windows chain). **Re-probe at publish (2026-08-03, #279):** vpc 3.0.0's PUBLISHED metadata confirms the dev-branch facts — `requires-python >=3.11,<3.15` (matches ours) and `ingester3 ==2.1.1` unchanged, so the levenshtein wall persists in the released stack; the C-213 cross-ref's "when the vpc pin is re-qualified at publish time" event has now fired. |
| Cross-refs | C-22 (viewser retirement — the docker/pywin32 chain rides on viewser; GitHub #70); C-24 (heavy upstream dependency surface); ADR-014 (build tooling; supersedes ADR-013); Cluster A (external/upstream dependency coupling); C-213 (release-gate sibling — re-probe this 3.11/platform bound when the vpc pin is re-qualified at publish time; fired 2026-08-03, see narrative; reciprocal) |

### C-38: CM line-graph HTML grows with the number of embedded HDI levels

| Field | Value |
|-------|-------|
| ID | C-38 |
| Tier | 3 — **[backlog-watch]** (bounded, fails loud, known mitigation; monitor, not active risk) |
| Source | review-diff / size measurement (#90–#91 HDI level selector, 2026-06-05) |
| Trigger | When a CM **sample** model's forecast/evaluation report is rendered for many entities × multiple HDI levels — particularly a full-country CM run (~190 countries) with more than the default three levels, or many rolling-origin sample graphs in one report |
| Location | `views_reporting/visualizations/historical.py` — multi-level HDI rendering embeds 3 band traces per (entity, level), and each entity dropdown button carries a visibility array of length = total traces, so the embedded payload grows ~O(entities² × levels × 3) |
| Narrative | The legend-selectable multi-level HDI feature (#90) embeds **all** levels for **all** entities in the static HTML (no server to recompute on click). Empirically, the red_ranger CM sample report (~191 countries, 3 levels) is **15.6 MB vs 13.4 MB single-level — +2.2 MB / +16%**; the growth comes both from the tripled band traces and, more steeply, from the entity dropdown's per-button visibility arrays (length = total traces × number of entity buttons). This is **bounded and fails loud** (a larger file, never silent corruption), so it is Tier 3, **not** the OOM-class PGM render risk. **Scope is CM line graphs only: the heavy PGM choropleth path is explicitly unaffected** — the historical line graph is gated on `isinstance(forecast_dataset, _CDataset)` (CM) in `templates/reports/forecast.py`, so the heavy PGM map report (C-26; ~37 MB since #259's single-plotly.js fix, formerly ~90 MB) does not carry HDI bands. The #89 tag-based visibility refactor *reduced* adjacent fragility (resolved CIC Deviation #5). Remediation if it grows: cap the entity count / levels for the line graph, lazily embed non-default levels, or switch to a server/recompute control for very large CM runs. |
| Cross-refs | C-26 (sibling render-size risk on the **PGM map** path — different mechanism, unaffected here); Cluster C (scale discipline); ADR-016 (levels are config-bounded via `ReportingConfig.hdi_levels`); CIC Deviation #5 (resolved, #89) |

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

### C-109: Uncertainty is communicated as MAP/HDI, not as exceedance/threshold probabilities + calibration the conflict audience needs

| Field | Value |
|-------|-------|
| ID | C-109 |
| Tier | 3 |
| Source | expert-method-review (library-grounded, 2026-06-19) |
| Trigger | When a forecast/evaluation report is delivered to a conflict-escalation decision audience (e.g. partner deliverables, UN FAO) and the question is "how likely is escalation beyond threshold X" — the report shows a central HDI + a MAP point, not the decision-relevant exceedance probability or its calibration |
| Location | `views_reporting/visualizations/historical.py` (HDI bands), `views_reporting/visualizations/distributions.py` (MAP/HDI overlays), `views_reporting/templates/reports/forecast.py` (uncertainty surface of the forecast report); `views_reporting/mapping/mapping.py` (the choropleth shows a `tower_point` per cell with no uncertainty cue — the map manifestation, merged from the #125 method review 2026-06-27) |
| Narrative | The reports communicate forecast uncertainty via **MAP** (modal point estimate) and **HDI** (central credible intervals). For a heavy-tailed, zero-inflated conflict process and a policy/partner decision audience, the decision-relevant quantities are **exceedance / threshold probabilities** (P(escalation beyond X)) and their **calibration**, not a central interval — and **MAP is a weak, potentially misleading point summary** of a skewed conflict posterior (the mode is not the decision-relevant location). Grounded in the library: *Lerch2017* (the forecaster's dilemma — evaluating/communicating extremes), *Gneiting2014* (sharpness subject to calibration), *Radford2022 / Hegre* (the conflict-forecasting domain). This is a *communication-appropriateness* gap for the decision-maker, **distinct from C-35** which concerns the *numerical correctness* of MAP/HDI on pathological posteriors. Remediation: add exceedance/threshold-probability views + calibration plots alongside (or in place of) the MAP-centric summary; roadmap Phase 4. **Map instance (#125 method review, 2026-06-27):** a large-grid choropleth shows a `tower_point` per cell with no uncertainty representation; the honest minimum is to **label it a point summary**, and the decision-grade companion is an **exceedance-probability map** (`P(Y>c)` per cell — bounded [0,1], well-behaved at scale, and the views-frames v1.5.0 estimator below renders it directly). **Upstream enabler (2026-06-25):** views-frames v1.5.0 ships a threshold **exceedance-probability estimator `P(Y>c)`** + expected-shortfall (views-frames ADR-021/022) — the primitive this concern needs. Adopting it becomes a near-term reporting story once views-frames is bumped (≥1.5.0; mind C-186's behavioural-test caveat on bump). **Update (2026-07-31, review-rr): PARTIALLY DELIVERED** — epic #230 (ADR-021) ships a **P(any violence) exceedance layer** (`calculate_exceedance_frame`, share of draws > 0) as a standard per-target PGM map layer alongside MAP and upper-HDI 90/95, closing the "map instance" half at threshold 0. Remaining open: partner-relevant thresholds beyond >0, the CM line-graph communication surface (still MAP/HDI-centric), and calibration plots. |
| Cross-refs | C-35 (MAP/HDI numerical correctness — sibling, different axis: correctness vs decision-appropriateness); ADR-017 (canonical metrics — calibration/MCR already in the standard); `documentation/roadmap_to_1.0.0.md` Phase 4. |

### C-112: Bundled static reference data can silently go stale (forward risk created by the C-22 remediation)

| Field | Value |
|-------|-------|
| ID | C-112 |
| Tier | 3 — **ACTIVATED 2026-07-05** (the bundled table shipped with epic #204; retiered from the forward-risk 4 as pre-registered, held at 3 rather than 2 because the guards below make drift *observable*, not silent) |
| Source | review-rr strategic (blind-spot analysis — forward risk, 2026-06-22) |
| Trigger | When upstream reference data changes under the frozen bundle — a country renames/recodes (Eswatini-class), GW codes are reassigned, the grid coverage expands (the global rollout!), or the Natural Earth shapefile is bumped — and `scripts/build_entity_metadata.py` is not re-run (or the shapefile/bundle vintages diverge) |
| Location | `views_reporting/metadata/data/{country,priogrid}.parquet` + `stamp.json` (the bundled assets, epic #204 S1 / #210); `scripts/build_entity_metadata.py` (the regenerator) |
| Narrative | C-22's remediation swapped live VIEWSER fetches for the bundled table — removing the runtime-dependency fragility but activating the **opposite** risk: static reference data ages, and a frozen bundle would serve **stale geography** (wrong label / wrong join) with no error signal. **Now live, with the pre-registered guards shipped (epic #204):** (1) **version + source-date stamp** — `stamp.json` records snapshot date, versions, row counts, `max_month_id`, per-file sha256 (integrity-bind tested); (2) **observability** — the snapshot date is stamped into every report's provenance footer (C-34 block), so staleness is visible in every delivered artifact without a CI time-bomb; (3) **drift tripwire** — `tests/test_metadata_contract.py::test_bundled_isoab_subset_of_shapefile_adm0a3` fails loud when a bundled ISO code is neither shapefile-joinable nor in a *categorized* allowlist (retired states / 1:110m microstates) — the C-206 catch proves the mechanism works; (4) **documented cadence** — regenerate on VIEWS country-table changes, coverage expansion, or tripwire failure (script header). **Known accepted deltas:** the PGM table is a latest-assignment snapshot (declared limitation, stamp + epic #204); coverage is **global since #231** (66,205 cells via the interim GAUL→VIEWS crosswalk — see C-211 for the crosswalk's declared limitations and the coding-transition risk this created). |
| Cross-refs | C-22 (RESOLVED — the remediation that activated this); C-39 (RESOLVED — the accessor tests that now cover the bundled table); C-206 (RESOLVED — the tripwire's first catch); C-34 (the provenance footer carrying the snapshot date); C-211 (the global crosswalk bundle this entry's guards now watch; reciprocal); Cluster F (assurance). |

### C-113: Observed/actuals data provenance & validation is untracked

| Field | Value |
|-------|-------|
| ID | C-113 |
| Tier | 4 — **[backlog-watch]** (subsumed once C-34 provenance lands) |
| Source | review-rr strategic (blind-spot analysis, 2026-06-22) |
| Trigger | When the observed-history ("actuals") overlay in a report is re-sourced or refreshed (a change to where observed values come from), or when a partner questions whether the plotted observed line is the authoritative actuals — nothing validates or stamps the observed-data source |
| Location | `views_reporting/visualizations/historical.py` (the observed-history overlay) and the observed-data read path feeding it |
| Narrative | Reports overlay "observed history" against predictions (`historical.py`). C-37 (resolved) addressed only the *cutoff-line semantics* of that overlay, not the **provenance or validation of the observed values themselves** — where the actuals come from, whether they are the authoritative version, and whether they are validated before plotting. For a partner-facing forecast-vs-actuals chart, an unstated/unvalidated actuals source is a minor traceability/assurance gap — it underpins the very visual the partner judges accuracy by. Tier 4: no demonstrated defect, low likelihood, and partly subsumed once C-34 provenance lands. Remediation: document/validate the observed-data source and fold it into the C-34 provenance stamp. |
| Cross-refs | C-34 (provenance — the observed source should be stamped too); C-37 (resolved — cutoff semantics of the same overlay); C-29 (render fidelity); Cluster F (assurance). |

### C-118: `loaders/__init__` registers loaders as an import-time side effect, coupling package import to global-registry mutation

| Field | Value |
|-------|-------|
| ID | C-118 |
| Tier | 4 — **[backlog-watch]** (localized; not a correctness risk) |
| Source | repo-assimilation (2026-06-22) |
| Trigger | When a caller wants to import the loader facade or `PredictionLoader` protocol without triggering a `views_pipeline_core` import, or when any code path causes `views_reporting.loaders` registration to run twice |
| Location | `views_reporting/loaders/__init__.py:9-10` (`register_loader("dataframe", ...)` / `register_loader("prediction_frame", ...)` at module top); `views_reporting/loaders/_registry.py:21-27` (fail-loud on duplicate) |
| Narrative | `_protocol.py` and `_registry.py` were deliberately kept import-light (pipeline-core types referenced only under `TYPE_CHECKING`), but `loaders/__init__.py` runs `register_loader` at import time, which imports `dataframe_loader`/`prediction_frame_loader` and thereby eagerly pulls `views_pipeline_core.data.handlers`. So merely importing the loaders package executes registry mutation and the heavy pipeline-core import, undoing the import-light intent of the registry layer. `register_loader` is fail-loud on duplicates, so any re-registration path raises `ValueError`. Localized and not a correctness risk (Tier 4); the cost is hidden global state at import and a heavier-than-necessary import surface. Remediation: lazy registration (register on first `get_loader`) or an explicit `register_default_loaders()` call, keeping the package importable without the eager pipeline-core dependency. **Update (2026-07-31, #263 audit):** the "eagerly pulls `views_pipeline_core.data.handlers`" premise is stale — the loaders are vpc-import-free today; what remains is only the import-time `register_loader` side effect itself (`loaders/__init__.py:24-25`). Tier 4 stands; remediation unchanged. |
| Cross-refs | C-114 (the pipeline-core coupling this eager import participates in); Cluster A (external dependency coupling at import) |

### C-185: `pred_*_map` column now carries a tower tip (shorth), not a MAP — name is a misnomer

| Field | Value |
|-------|-------|
| ID | C-185 |
| Tier | 4 — **[backlog-watch]** (documented decision/naming debt; rename is a coordinated cross-repo change) |
| Source | review-diff (tower adoption, 2026-06-24) |
| Trigger | When a downstream consumer (pipeline-core, a persisted-output reader, a partner) interprets `pred_*_map` as a histogram-mode MAP rather than the tower tip it now holds — or when a coordinated cross-repo rename is scheduled |
| Location | `views_reporting/statistics/dataset_statistics.py` (`calculate_map` / `calculate_map_frame` / `compute_single_map` emit `{t}_map`); ADR-019 |
| Narrative | ADR-019 swapped the render-path point estimate from the frozen histogram-mode `map_estimate` to the views-frames tower tip (`tower_point` — originally the median of the 0.5-mass "shorth" floor; **since views-frames 1.9.0 the top-quartile tip_mass 0.25 floor**, their ADR-019 Amendment 3 — see the local ADR-019 update block and C-186's 2026-08-02 entry). The output **column name was deliberately kept** as `{t}_map` for output-contract stability (no pipeline-core change), so the slot now carries a value that is **not** a Maximum-A-Posteriori mode. This is a naming-honesty / contract-clarity debt, not a correctness defect — the value is principled and well-defined; only its label is stale. Tier 4: no correctness or reliability impact, single-name scope. Remediation is a **coordinated cross-repo rename** (e.g. `{t}_point` / `{t}_tip`) spanning views-reporting + pipeline-core + any persisted-output consumers; until then ADR-019 + this entry are the record of the semantic change. **Elevate** if a downstream consumer is found to rely on the histogram-mode semantics. |
| Cross-refs | C-35 (the MAP/HDI-correctness remediation that introduced the tip); ADR-019; Cluster F (contract assurance); upstream views-frames ADR-019 / C-32 |

### C-211: Platform country-coding transition — the bundle's cell→country table rides an interim GAUL→VIEWS crosswalk

| Field | Value |
|-------|-------|
| ID | C-211 |
| Tier | 3 |
| Source | epic #230 / issue #231 investigation (2026-07-20); decision by Simon on #231 |
| Trigger | When CM-level model outputs migrate to views-datafactory (whose country identity is **GAUL `gaul0_code`**, not VIEWS `country_id` — its `grid_to_country_month` adapter groups by GAUL, and no GAUL↔VIEWS crosswalk exists in the factory); **or** when a partner integration requires a non-GAUL/non-VIEWS country coding; **or** when the GAUL harvest is re-run (GAUL 2024 → newer vintage) and the crosswalk's unmatched/border sets shift |
| Location | `scripts/build_entity_metadata.py` (`read_gaul_cells` / `active_country_by_isoab` / `crosswalk_priogrid` — the adapter seam); `views_reporting/metadata/data/stamp.json` (`priogrid_source` block declares the interim status + exactly what is unmapped); external: views-datafactory `src/datafactory_adapters/grid_to_country_month.py` |
| Narrative | The viewser pgm loa is regional (Africa+ME) while the platform's data supply has moved to the GAUL-coded datafactory — so the global bundle (#231) is built by an **explicitly interim** crosswalk: GAUL `iso3_code` → VIEWS `isoab` → `country_id`, duplicate isoab resolved to the most-recently-observed entity (active-active collisions fail loud, #242). Coverage is declared, not silent, **with denominators** (#248, all figures reconcile with the stamp): of the **64,818-cell forecast land region**, 99.50% crosswalks — 322 cells (disputed/non-VIEWS territories: Western Sahara, Kashmir, Abyei…) carry no VIEWS country and degrade via the visible-NaN path; **grid-wide**, 29,373 of 95,578 GAUL-coded land cells are unmatched, dominated by Antarctica (25,444) and Greenland (3,038) — bulk out-of-scope regions, not disputed footnotes. ~157 Africa+ME border cells differ from the retired viewser assignment (GAUL 2024 vs VIEWS DB borders, e.g. the Aouzou strip). **Declared absorption (#249):** GAUL 2024 has no Kosovo unit — its 10 cells carry `SRB` and crosswalk to Serbia (country_id 233) while VIEWS Kosovo (232) receives zero cells; because the code is valid this never enters the unmatched accounting, so the stamp declares it explicitly (`known_gaul_absorptions`, validated against the built table at regen). The structural risk is the **transition itself**: two coding systems now coexist in the platform with reporting owning the only bridge. Containment: runtime accessors depend ONLY on the bundle schema contract (`priogrid_id → country_id`) — swapping/adding codings is a build-script-only change (DIP), and a future multi-coding bundle would ADD coding columns rather than rewrite accessors (OCP). The eventual coding standard is deliberately undecided (GAUL is FAO's coding; other partner codings may follow) — the deep-dive/decision is filed cross-repo as views-datafactory#341 + views-postprocessing#123, which will announce any general solution back here. |
| Cross-refs | C-112 (bundle staleness observability — the stamp this entry extends; reciprocal); C-192 (sibling cross-repo contract-assurance theme); epic #230; views-datafactory#341 / views-postprocessing#123 (coding-decision venue); ADR-021 (documents the interim status + the handover path). |

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
| Resolution | Resolved/moot 2026-06-28 (#72) — reconciliation is deleted from views-reporting; the worker-data-shape question, if still relevant, lives with `views_frames_reconcile` in views-frames. No longer a views-reporting decision. |

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

### C-213: Coordinated-release coupling to views-pipeline-core — the `>=3.0.0` pin outruns PyPI (2.3.0) and the consumed import paths are un-qualified against vpc's shim removals — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-213 |
| Tier | 2 — structural fragility with a clear, dated trigger (executing the #179 release runbook); failures are **loud** (pip resolver error / ImportError), never silent → not Tier 1. Same calibration as C-36 (install surface shaped by upstream state). |
| Source | Release-readiness investigation (2026-07-27 session: #179 runbook rewrite + drafting views-pipeline-core#313); pin observed at `pyproject.toml:17`, PyPI state verified externally |
| Trigger | Executing #179's PyPI-publish step for views-reporting 0.3.0 **before** views-pipeline-core has published a 3.x; **or** bumping the vpc pin/lockfile to vpc's next *published* release without re-sweeping our vpc import paths against their final ADR-054 shim disposition |
| Location | `pyproject.toml:17` (`views-pipeline-core>=3.0.0,<4.0.0`); consumed vpc surfaces: `views_reporting/reports/report.py:16`, `views_reporting/templates/reports/evaluation.py:11-15` + `:426` + `:466`, `views_reporting/templates/reports/forecast.py:11-12` |
| Narrative | Two facets, one root: views-reporting's release health depends on views-pipeline-core's **publish state**, which the coordinated release (#179) changes underneath us. **(a) Ordering contradiction:** we pin `views-pipeline-core>=3.0.0,<4.0.0`, but PyPI's latest vpc is **2.3.0** — the pin is only satisfiable from dev branches (which is why the uv.lock works today). #179's recorded release order (views-frames → **views-reporting → pipeline-core** → postprocessing/models) would put views-reporting 0.3.0 on PyPI while its declared dependency is unresolvable there: a clean `pip install views-reporting` fails until vpc's 3.x lands. Either vpc publishes first/simultaneously, or #179 must declare and accept the uninstallable window. **(b) Shim exposure:** vpc's ADR-054 "remove-when-forced" policy fires exactly at their publish (their #184; qualification asked for in views-pipeline-core#313). Our import-path set has never been re-qualified against that disposition — and it demonstrably includes a legacy path: `evaluation.py` imports `ModelPathManager` from BOTH `views_pipeline_core.managers.model` (line 15) and `views_pipeline_core.data.model_path` (line 466); one of those is the tombstoned location. Remediation (a release-gate step, not code today): when vpc's 3.x version is known, re-verify the pin bounds against it; sweep all `views_pipeline_core` imports here against vpc's final shim-removal list and migrate any legacy paths; then correct #179's ordering step to "vpc 3.x on PyPI before (or with) views-reporting". **Update (2026-07-31, S1 #263 — facet (b) DONE, and the exposure claim corrected):** the audit against installed vpc 3.0.0 (dev) found the shim story was **backwards** — `data.model_path` is the **canonical** `ModelPathManager` home (vpc ADR-045 E6) and `managers.model` is the deliberately-retained compat re-export ("343+ references in downstream model repos"); the actual ADR-054 tombstone set is vpc's six `modules/*` shims, of which views-reporting imports **none** (we are their re-export *target*). All `ModelPathManager` imports canonicalized (`evaluation.py`, `forecast.py`) and pinned by a permanent guard (`tests/test_vpc_import_surface.py`: no `views_pipeline_core.modules.*` anywhere; `ModelPathManager` only from `data.model_path`); accuracy corrections posted on views-pipeline-core#313 and #179. **Remaining open: facet (a) only** — the PyPI ordering step, executed at the #179 release gate. |
| Cross-refs | C-192 (no executable cross-repo seam test — an import/signature drift surfaces only at runtime); C-186 residual (b) (exact-pin-for-release, the views-frames sibling of the same release-gate discipline); C-36 (install surface bounded by upstream pins — same loud-failure class); #179 (the runbook this entry gates); views-pipeline-core#313 (their shim-qualification ask) / their #184 (the remove-at-publish policy). |
| Resolved | 2026-08-03 (#279 — vpc 3.0.0 published to PyPI; interim git source retired) |
| Resolution | Facet (a) discharged by the event it gated: **views-pipeline-core 3.0.0 published to PyPI 2026-08-03** carrying the pins we pre-qualified on vpc#313 (`views-evaluation>=1.0.0,<2.0.0`, `views-frames>=1.10.2,<2.0.0`, `requires-python >=3.11,<3.15` — all matching ours). Verified from the published artifacts: `views-reporting==0.3.3` co-resolves from PyPI alone (uv pip compile → vpc 3.0.0 / views-evaluation 1.0.0 / views-frames 1.10.2); the accepted uninstallable window (0.3.0 published first, 2026-08-02) closed as planned. The last dev-tandem `[tool.uv.sources]` git source removed per its own documented trigger; `uv.lock` resolves vpc from the registry and the suite runs green against the RELEASED 3.0.0 (first time — previously only the git dev branch). The ordering half fired **without a third Cluster H incident** because the pin was re-qualified before their publish (the vpc#313 warning), which is the runbook lesson this entry existed to enforce. |

### C-111: No input-completeness validation at the report boundary — incomplete input renders silently — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-111 |
| Tier | 3 |
| Source | review-rr strategic (blind-spot analysis, 2026-06-22) |
| Trigger | When predictions arrive from a **new or changed producer** (a new model repo, a changed pipeline-core stage), or a **partial/interrupted pipeline run's** output is rendered — nothing verifies expected time/entity *coverage* before rendering (the structural and NaN halves are guarded, see narrative), so a truncated frame renders a silently-partial report *(trigger sharpened from the perpetual form, review-rr 2026-07-31)* |
| Location | `views_reporting/loaders/` (the ingestion adapters that receive predictions, ADR-012); consumed by `views_reporting/templates/reports/forecast.py` without a completeness assertion. Contrast C-29, which checks the transform/join assuming the input is already good. |
| Narrative | The reports **receive** predictions through the ingestion loaders and render them. C-29 covers render≠source *fidelity* (the transform/join dropping rows) but **assumes the received input is itself complete**. Nothing validates that the input frame is well-formed and complete — correct shape, no unexpected NaN in the sample axis, expected entity/time coverage — before rendering. A truncated prediction file, a frame missing months, or NaN-filled samples would render as a silently-partial report (the join-drop of 26 island states / 936 rows noted in C-29 is one observed instance of silent reduction; **input-side incompleteness is the un-tracked sibling**). Assurance gap, not a demonstrated defect, and the input is normally produced by the trusted pipeline — hence Tier 3 (same silent-class calibration as C-29/C-35), **elevate to Tier 1 if a silently-partial render from incomplete input is ever observed**. Remediation: an input-completeness assertion at the ingestion boundary (shape / NaN / coverage checks; fail-loud or visible-note on incompleteness) — naturally part of the value-correctness & contract assurance work, and the natural home is the typed input contract (C-108). **ADVANCED, not closed (epic #137 S5, #140):** the loaders now run `views_frames.conformance.assert_frame_contract` on every ingested frame (ADR-009 §1b) and the conformance floor is pinned — this fail-loud gate covers the **structural** contract (float32 values + explicit sample axis, complete integer `time`/`unit` identifiers of length `n_rows`, save/load round-trip). **Residual (stays Tier 3, open):** the contract does **not** reject NaN in the *values* axis nor verify expected time/entity *coverage* (a truncated/partial frame still passes), so the semantic-completeness half remains — to be closed by a coverage/NaN check or the Phase-3 typed input contract (C-108). **Update (2026-06-28, Cluster F sprint):** the **values** half is now guarded — `loaders/_constants.py:assert_conformant` raises on a wholly-NaN frame (ADR-008) and warns on partial NaN (legitimate sparse cells), tested in `tests/test_input_completeness.py`. The remaining half — expected entity/time **coverage** — stays deferred to the C-108 Phase-3 typed input contract. |
| Cross-refs | C-29 (render≠source fidelity — the sibling that assumes good input); C-108 (the injected typed-contract direction where this validation belongs); C-35 (sibling assurance-gap calibration); Cluster F (value-correctness & contract assurance). |
| Resolved | 2026-07-31 (epic #262 S4, #266; decision by Simon: gap→raise, ragged→warn) |
| Resolution | The final (coverage) half landed at the same seam as the earlier halves (`loaders/_constants.py::assert_conformant`, numpy-on-index-arrays only — C-212 discipline): an **interior time-axis gap raises** (`ValueError` naming the missing month_ids — certain data loss, no producer emits a gapped horizon; ADR-008) and **ragged entity coverage across months warns once** (aggregated min/max-per-month counts — possibly legitimate, the South Sudan class; C-11 visible degradation, and missing entities already render as visible no-data). RED→GREEN tests in `tests/test_input_completeness.py` (gap raise, contiguous pass, ragged single-warning, rectangular silent); full suite incl. e2e green — the real bundles are contiguous+rectangular, verified not assumed. **Declared residual (NOT tracked open):** end-of-horizon truncation is indistinguishable from a shorter run without an external expectation — it transfers to the C-108 Phase-3 typed input contract, recorded there by this entry's cross-ref. |

### C-214: Plotly-injection and single-library guards key on literal plotly-internal strings — a plotly bump can strip the JS from delivered reports — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-214 |
| Tier | 3 — assurance/coupling gap with an existing loud tripwire (the e2e `count==1` assertions), not a live silent path; **elevate to Tier 2/1 if a blank-figure report ever escapes the suite** |
| Source | review-rr strategic (blind-spot analysis, 2026-07-31); registered on user request |
| Trigger | When the `plotly` dependency is bumped (pyproject/`uv.lock`), or plotly.py changes its `to_html` fragment output / bundled-JS banner — the heuristics below match implementation-detail strings, not a contract |
| Location | `views_reporting/reports/report.py` — `_ensure_plotly_js` (needs-JS detection keys on the literal substring `"Plotly.newPlot"`; double-inclusion warning keys on `"* plotly.js v"`), `_get_plotly_script` (vendors `plotly.offline.get_plotlyjs()`); consumers `add_html` + the `add_to_grid` raw-HTML branch; producer sites `mapping/mapping.py` / `visualizations/historical.py` (`fig.to_html(full_html=False, include_plotlyjs=False)`) |
| Narrative | The #259 single-plotly.js architecture made JS inclusion **content-aware**: figures ship as lean fragments (`include_plotlyjs=False`) and the report injects the vendored bundle once, deciding "does this HTML need plotly?" by searching for `"Plotly.newPlot"`. That substring — like the `"* plotly.js v"` banner the double-inclusion warning and the e2e assertions probe — is **plotly.py serializer internals, not a contract**. If a future plotly version stops emitting it, injection silently skips and every interactive figure renders as a blank div: no exception, no log. **Existing tripwire:** the e2e suites assert exactly one `"* plotly.js v"` occurrence in exported reports, so a bump-induced skip fails CI **loud** (count 0) — which is what holds this at Tier 3. **Residual:** all three probes (injection key, double-inclusion warning, test assertion) are coupled to the *same class* of plotly-internal string and could drift together on the same bump; and the vendored plotly.js version is not stamped in report provenance (C-34 block), so which JS a delivered artifact carries is not traceable. Remediation: pin/assert the plotly version at the injection seam (fail loud on unqualified bump), derive the needs-JS test from something structural (e.g. the fragment's `<div class="plotly-graph-div">` marker AND the API call), and stamp the vendored plotly.js version into provenance. |
| Cross-refs | C-28 (offline self-containment — the vendoring this rides on); C-38 (sibling artifact-size mechanics); C-34 (the provenance stamp the JS version should join); #258/#259 (the architecture); Cluster G (partner-deliverable readiness — a blank-figure report is a deliverable-integrity failure). |
| Resolved | 2026-07-31 (epic #262 S3, #265) |
| Resolution | The registered remediation trio shipped. (1) **Redundant structural probes**: `_ensure_plotly_js` now fires on `plotly-graph-div` (container class) OR `Plotly.newPlot` (bootstrap call) — a serializer change must break BOTH before injection can skip. (2) **Bump canary** (`tests/test_plotly_canary.py`, 5 tests): pins both fragment probes, the `* plotly.js v` banner's presence + parseability, each-probe-alone injection, and the plain-HTML skip economy — fails loud on the bump PR, upstream of the e2e count==1 tripwires; RED demonstrated via probe mutation. (3) **Provenance stamp**: `plotly` + vendored `plotly_js` versions (parsed from the bundle banner, tolerant-None per C-34) in the machine-readable payload and the footer build line; e2e provenance test asserts both. |

### C-192: No executable cross-repo contract test for the eval `generate(source, target)` / MetricFrame consumption (views-reporting ↔ pipeline-core) — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-192 |
| Tier | 3 |
| Source | expert-code-review (Feathers/Nygard/Beck, 2026-06-28) |
| Trigger | When the `generate(source, target)` signature, or the `MetricFrame` fields/axes the eval report reads, are next changed on either side — or a new `EvaluationSource` consumer is added — this repo's tests (which mock pipeline-core) stay green while the real `pipeline-core ReportingStage → generate()` integration is exercised only at runtime in the conda dev-tandem env |
| Location | `views_reporting/templates/reports/evaluation.py:53` (`generate`); `views_reporting/sources/metric_frame_file_source.py` (the consumed contract); the seam = pipeline-core `views_pipeline_core/managers/reporting/stage.py` (external); this repo's eval tests construct the template directly with `FakeEvaluationSource`/temp-dir frames and never import pipeline-core's stage |
| Narrative | The B2 inversion (C-108) made the cross-repo eval contract an *injected* one: pipeline-core's reporting stage builds a `MetricFrameFileSource` and calls `generate(source=, target=)`, and its evaluation stage persists the frame at the agreed path. No executable test in **this** repo exercises that real seam — the suite mocks pipeline-core, so an API/semantic drift surfaces only at runtime. This was a **near-miss (2026-06-28):** this repo's `uv.lock` was pinned to a pre-epic pipeline-core dev commit that still called the deleted `generate(wandb_run=)` signature, and green CI hid it because nothing executes the seam; the instance was resolved by realigning the lock (#181) to pipeline-core's eval-of-record HEAD. **Durable residual:** the assurance gap itself — the contract is not pinned by an executable test on our side. **Mitigations already in place:** (a) pipeline-core's reporting stage has a **fail-loud preflight** that raises a clear upgrade message if the installed views-reporting lacks `MetricFrameFileSource` (catches a missing *consumer*, though not a *signature* change); (b) the on-disk frame path is a **locked cross-repo contract** documented on both sides (pipeline-core `managers/evaluation/stage.py` ↔ our `MetricFrameFileSource._frame_dir`) — this is what retired the earlier "provisional path" worry. Remediation: a contract test that imports the real `views_pipeline_core.managers.reporting.stage` and asserts it calls `generate(source=, target=)` (skip if absent), and/or a shared `MetricFrame` round-trip fixture both repos pin. Fails **loud** at runtime today (TypeError / preflight), not silent → Tier 3, **elevate if a silent semantic drift in the consumed `MetricFrame` is ever observed.** |
| Cross-refs | C-46 (sibling "mocked seam → false confidence" / CI-status gap — same theme, different mechanism); C-108 (the inversion that created this injected contract); C-34 (provenance the contract also carries); Cluster F (value-correctness & contract assurance); GitHub #179 (the publish-last coordination this contract gates); C-213 (the release-coupling entry gating the same publish event — the moment this un-tested seam becomes acute; reciprocal). |
| Resolved | 2026-07-31 (epic #262 S2, #264) |
| Resolution | **`tests/test_vpc_seam_contract.py` executes against the REAL pipeline-core stage** (skip-if-absent, C-46 contract): AST-pins the stage's single `evaluation_template.generate(source=, target=)` call (keyword-only, exactly those two); binds our `generate` signature against that call; pins the `MetricFrameFileSource(...)` construction kwargs + `root=<data_generated>`; pins the on-disk layout by **executable equality against the producer's own exported `METRICFRAME_DIR_PREFIX`** constant; bonus: both `forecast_template.generate(...)` call sites bind our forecast signature. RED demonstrated for a signature rename and a path-suffix drift. Rider: the stale "provisional layout" docstring in `metric_frame_file_source.py` corrected to the locked-contract language (the producer had long declared it C-202-locked). |

### C-189: Spatial aggregation of forecast cells can misrepresent the quantity (MAUP / wrong operator) — RESOLVED (superseded)

| Field | Value |
|-------|-------|
| ID | C-189 |
| Tier | 3 |
| Source | expert-method-review (spatial-statistics seat, 2026-06-27) |
| Trigger (historical) | When #125 implements an aggregation/binning path for large PGM maps and coarsens cells with `mean` or `max` (or an unlabelled bin size) on a **count** target |
| Location | `views_reporting/mapping/mapping.py` (the then-anticipated #125 aggregation path); `ReportingConfig` (the declared aggregation operator) |
| Narrative | Coarsening N×N grid cells invokes the **Modifiable Areal Unit Problem**: the apparent spatial pattern changes with bin size *and* operator, so the operator must match the quantity's semantics — **SUM** for predicted counts (preserves expected total events), **area-weighted MEAN** for rates/probabilities, and **never MAX** (it manufactures hotspots and is scale-dependent). A mismatched operator silently misrepresents forecast magnitude on a partner-facing map (no error signal). Aggregation also discards the model's native resolution — acceptable for a zoomed-out overview only. Remediation: fix the operator by target type, **label the bin size**, restrict to an opt-in overview (default stays fail-loud, #118). Gaps to fetch: Openshaw (MAUP). |
| Cross-refs | C-26 (the large-render path this guarded); C-190/C-191 (sibling methodology guards); Cluster C (scale discipline); ADR-021 (the superseding decision). |
| Resolved | 2026-07-31 (review-rr strategic, user-confirmed) |
| Resolution | **Superseded by design decision — the guarded path was never built and is now designed out.** ADR-021 (and the C-26/globe ladder before it) committed the large-PGM render path to **per-cell faithfulness by construction**: raster heatmap / PNG tiers map one cell → one array element / ≥1 pixel — C-26's resolution explicitly records "no aggregation C-189". #125 closed without an aggregation/binning path and none is planned. **Re-register if a spatial-coarsening / zoom-out overview feature is ever proposed** — the guard then is operator-matches-semantics (SUM for counts, area-weighted MEAN for rates/probabilities, never MAX) plus a labelled bin size. |

### C-190: Downsampling/subsetting a forecast map as the delivered artifact reads as "no risk" — RESOLVED (superseded)

| Field | Value |
|-------|-------|
| ID | C-190 |
| Tier | 3 |
| Source | expert-method-review (conflict-domain seat, 2026-06-27) |
| Trigger (historical) | When #125 offers a "representative subset" / downsampled large-grid map as the **report** map (not a clearly-labelled diagnostic) |
| Location | `views_reporting/mapping/mapping.py` (the then-anticipated #125 downsampling path) |
| Narrative | On a risk map an **omitted cell reads as "no conflict forecast there"** — a silent completeness failure with no error signal, compounded by under-reporting in the event data (a low value is already not zero; cf. `Vesco2026`). A partial map handed to a decision audience is worse than no map. **Elevate toward Tier 1/2 if a downsampled map is ever shipped as a partner deliverable.** Recommendation: do **not** deliver a subset as "the map"; if downsampling exists at all, restrict it to an explicitly-labelled diagnostic. The faithful + scalable alternative is raster rendering (1 cell → ≥1 pixel; see C-191 synthesis). |
| Cross-refs | C-26 (the large-render path this guarded); C-189/C-191 (sibling methodology guards); C-28 (partner-deliverable readiness); Cluster C/G; ADR-021 (the superseding decision). |
| Resolved | 2026-07-31 (review-rr strategic, user-confirmed) |
| Resolution | **Superseded by design decision — the delivered PGM artifact is always the full lattice.** The raster/PNG tiers render every cell (C-26's resolution records "no omission C-190"; a missing cell stays visibly no-data — grey since #234 — never dropped or back-filled), and no subset/downsampled deliverable exists or is planned. **Re-register if a downsampled or "representative subset" map is ever proposed as a delivered artifact** rather than an explicitly-labelled diagnostic. |

### C-212: S=1000 global forecast OOMs the report path — all-targets-at-once loading plus a float64 collapse detour — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-212 |
| Tier | 2 |
| Source | epic #230 / issue #235 investigation (PR #238 review measured the loader half; the collapse half found during S5 implementation, 2026-07-21) |
| Trigger | The first production forecast run at S=1000 samples on the global 64,818-cell grid (current runs are S=128, ≈3.6 GB total — fine) |
| Location | `views_reporting/loaders/__init__.py` (`load_predictions` materializes ALL targets before any collapse); `views_reporting/templates/reports/forecast.py` (consumes the full dict); `views_reporting/statistics/dataset_statistics.py` (`calculate_map_frame`/`_frame_map`/`_frame_hdi`/`calculate_exceedance_frame` force `np.asarray(values, dtype=np.float64)` then a masked copy then a float32 cast) |
| Narrative | Two stacked mechanisms. (1) **Loader**: all targets load upfront — at S=1000, 3 targets × 2.33M rows × 1000 × 4 B ≈ 28 GB resident before the first collapse, over the 31 GB dev machine. (2) **Collapse detour** (the larger term): each collapse forces a float64 copy of the full sample array (2× bytes), boolean-mask copies it again, then casts back to float32 for the tower (which computes in float32 regardless) — peak ≈ 5× the float32 source *per collapse call*, ≈ 46 GB for ONE global S=1000 target, repeated for each of the 4 layers. Failure mode is a hard OOM at report time (loud, not silent), but it structurally blocks the platform's stated S=1000 goal. Remediation (S5/#235): per-target load→collapse→release iteration; float32-preserving collapse path (the tower is float32 by frame contract — the float64 detour buys nothing on the vectorized path); memory-bound guard test at reduced dims. |
| Cross-refs | ADR-020 (samples numpy-bound — this is its scaling corollary); C-38 (report byte budget — the disk-side sibling); epic #230, #235. |
| Resolution | **#235 (same PR as this entry):** (1) streaming seam — `iter_predictions` yields one `(target, frame)` at a time (laziness test-pinned) and the template releases each target's samples+layers before the next loads; (2) float32-preserving collapse — the float64 force, the boolean-mask copy, and the ephemeral cast are gone (zero-copy on the all-finite norm; numerically identical, 49 value-pinning tests green). **Measured:** subprocess RSS probe, 194k rows × S=1000, all four layers: collapse delta ≈ 0.00 GB over the resident source (was ~3.8×); guard test pins < 3.5× in CI. Extrapolated full global S=1000: ~9.3 GB/target streamed → peak ≈ 12 GB on the 31 GB machine. mmap_mode evaluated and NOT adopted (4× re-read I/O for a peak already ~1× source). |

### C-210: CIC secondary sections drift undetected — reviews touch only PR-named sections; the CIC-registry validator was inert — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-210 |
| Tier | 3 |
| Source | /review-base-docs full audit (2026-07-18) |
| Resolved | 2026-07-18 (governance-drift round, same PR) |
| Trigger (historical) | Any code change whose CIC update edits only the sections named in the PR — the untouched Inputs/Trusts/Examples/failure-table sections keep describing the previous era, and nothing mechanical notices |
| Location | `documentation/CICs/*` (worst: `cic_forecast_report_template.md` — still Draft/pre-frames; `cic_mapping_module.md` + `cic_historical_line_graph.md` — dataset-era Inputs/Examples, a deleted `RuntimeError` in a failure table, ~all absolute line numbers wrong); `documentation/validate_docs.sh` (the CIC-registry check greped a format the README never used — matched zero rows since inception) |
| Resolution | **The instance fixed, the mechanical cause fixed, the drift-prone convention retired.** (1) Full-audit remediation shipped: forecast-template CIC rewritten frames-native (render ladder, `metadata_snapshot`, tests); mapping/historical CICs purged of dataset-era sections, phantom failure modes removed; eval-template mechanism corrected (`AmbiguousMetric`); `add_key_value_list` documented; loader §5 outputs fixed; NEW `cic_reporting_config.md` (ADR-006/009 triggers); ADR-002/017 text fixes + ADR-009/011 addenda; three standards/protocol docs de-reconciliation/viewser-ized; roadmap ticked; historical banners added. (2) `validate_docs.sh` CIC check made REAL and bidirectional: parses the actual README table AND flags CICs on disk missing from it (proven RED on the pre-fix omission of `cic_evaluation_source.md`, then GREEN). (3) **Policy: no absolute line numbers in CICs** — method-name anchors only (every audited line ref was wrong; all replaced). Residual (honest): content-level drift in prose remains a manual concern — the durable control is the periodic /review-base-docs audit, which this entry's Trigger describes. |
| Cross-refs | ADR-006 (CIC mandate); ADR-007 (docs as agent contract surface); C-34 (its own resolution text was an instance — fixed here); the C-114/C-22 epics (whose churn generated the drift). |

### C-191: Linear colour scale on zero-inflated, heavy-tailed forecasts renders an uninformative map — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-191 |
| Tier | 3 |
| Source | expert-method-review (cartography/uncertainty-viz seat, 2026-06-27) |
| Resolved | 2026-07-16 (two-stage: log transform #125-era; the anchoring defect user-caught and fixed this round) |
| Resolution | **Stage 1 (#125-era, partial):** all three render surfaces (CM/PGM choropleth, PGM raster heatmap, PGM PNG) moved to a **log1p colour transform** with original-unit tick labels — the entry's core ask. **Stage 2 (2026-07-16, the defect Simon caught eyeballing the demo colourbar):** the shipped anchoring was broken for exactly the data class this entry describes — `quantile(log values, [0.50, 0.95])` collapses to `cmin==cmax==0` when ≥95% of cell-frames are zero (the PGM norm), silently handing the range to plotly's auto-scale; consequences: the top of the bar (the darkest colours) unlabelled above the last generated tick, and a bare "(log scale)" title inviting original-unit ticks to be read as log units. Fixed via a single shared `_log_color_scale` helper used by all three surfaces: saturation anchored at the **95th percentile of the NONZERO values' logs** (floored at log1p(1)), `cmin=0` so zero cells stay visually distinct, **the top of the bar always labelled** — the final tick sits at the saturation point, reading "≥ N" when values exceed it — and the legend retitled "value (labels: original units; colour: log-scaled)". Contract-tested against a 96%-zero synthetic with a 500-fatality hotspot (`tests/test_colorbar_anchor.py`: helper laws + raster/PNG wiring; the PNG's separate `vmax` floor-degeneracy — everything above 1 fatality saturating — fixed by the same helper). Visual verification on the regenerated PGM demo. |
| Trigger (historical) | When a choropleth (CM today, or a large PGM map under #125) renders zero-inflated heavy-tailed predicted counts on the current **linear** OrRd scale |
| Location | `views_reporting/mapping/mapping.py` (the colour encoding of `plot_map`) |
| Narrative | Conflict-forecast cells are zero-inflated and heavy-tailed: on a linear colour ramp almost every cell renders at the floor colour and the few hotspots are visually understated → the map is uninformative/misleading **regardless of rendering backend**. The methodological lever for a legible map is the **colour transform** — a log or quantile/rank scale with a legend that **states the transform** (an unlabelled log scale misleads as much as a linear one); use a sequential, colour-blind-safe ramp. **Live today on CM maps**, not only a #125 concern — it is the single highest-payoff fix for map legibility. Gaps to fetch: Brewer (ColorBrewer), MacEachren. |
| Cross-refs | C-26 (the #125 large-render path); C-189/C-190 (sibling #125 methodology guards); C-109 (decision-appropriate uncertainty — the companion communication gap); Cluster C/G. |

### C-208: Gapped PGM lattices render misplaced/stretched cells — heatmap midpoint-stretch (live) and PNG even-spread (latent) — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-208 |
| Tier | 2 (structural fragility with a LIVE visible instance: cell area/position misrepresented in delivered artifacts — per-cell values and hover remain correct, which is what keeps this out of Tier 1; the latent PNG variant is Tier-1-class once that tier becomes reachable) |
| Source | User eyeball of the demo PGM report (2026-07-15, the "ocean pixels" streak) + /falsify audit of the fix spec (probe F3); data classification confirmed all flagged cells are real territories |
| Resolved | 2026-07-16 (uniform-lattice fix, spec v2 — falsify-corrected; one PR with C-209) |
| Resolution | **Both tiers now render on a uniform 0.5° lattice spanning the bounding box** (`_uniform_lattice` + `_lattice_indices`, index arithmetic per falsify F1): every plotly brick is exactly 0.5° (Marion's 12° gap renders as empty ocean, not stretched coastline), and the PNG's imshow gets the uniform z with the extent at outer cell EDGES (also fixing the pre-existing half-cell shift on gap-free lattices, and re-syncing the coastline overlay). `hoverongaps=False` (falsify F4). Guarded by the promoted falsify suite (`tests/test_falsify_uniform_lattice_fix.py`: uniform axes + true brick positions, budget-by-lattice, no-hover-on-fill, PNG true-latitude via pixel analysis on the Marion fixture) and the updated image/canary tests (0.5°-adjacent fixtures). Visual verification: PGM demo regenerated post-fix — the Cape streak and the Cape-Verde smear are gone; the real island cells (Mauritius, Comoros, Socotra, Cape Verde, Marion) remain, correctly 1-cell-sized. |
| Trigger | LIVE: any PGM raster render of data containing isolated territories — the standard Africa+ME fixture already contains Marion Island (gid 62356, 12° south of the mainland), Cape Verde, Mauritius, Comoros, Socotra, so every current PGM heatmap shows it. ACUTE/Tier-1-class: when the PNG tier becomes reachable (globe × many origins past `max_raster_cell_frames`) — its variant misplaces EVERY cell. |
| Location | `views_reporting/mapping/mapping.py` `_plot_interactive_raster_map` (x/y = `np.sort(unique coords)` — NON-uniform arrays; plotly draws brick edges at coordinate midpoints) and `_plot_image_map` (`imshow` spreads the row array EVENLY across `extent` — assumes uniform spacing). |
| Narrative | The dense z-matrix is built over the coordinates **present in the data**, not a uniform lattice. Two consequences. (1) **Heatmap (live):** plotly places cell boundaries at midpoints between neighbouring coordinates, so a lattice gap stretches the adjacent cells across half of it — Marion Island's 12° gap paints the Cape's southernmost coastal cells (19.25–20.25°E) as ~6°-tall bricks into open ocean (the user-spotted streak), and Marion itself equally; Cape Verde's cells smear toward Senegal. Land values are painted over ~empty sea and cell areas misrepresented ~12× — a C-189-class faithfulness violation by rendering geometry rather than aggregation. (2) **PNG (latent, verified from imshow semantics):** the row array is spread evenly across the lat/lon extent, so a gapped lattice shifts EVERY cell (up to ~11° here) and desyncs the coastline overlay — invisible to date because all PNG tests used gap-free lattices and the tier is not yet reachable with real data. NOT a data or metadata issue: every flagged "ocean pixel" resolved to a real territory (Marion/ZAF, Cape Verde, Mauritius, Comoros, Socotra/YEM); the separate islands-look-outline-less effect is the documented 1:110m microstate omission (C-206 allowlist). Remediation (fix-spec v2, /falsify-corrected): build both tiers on a **uniform 0.5° lattice** via index arithmetic (not float membership), NaN-fill, `hoverongaps=False`, PNG coastline-alignment regression test, Marion-class gapped fixture (xfail stubs prepared: `tests/test_falsify_uniform_lattice_fix.py`, untracked). MUST land together with the C-209 guard redefinition. |
| Cross-refs | C-189 (sibling faithfulness class — aggregation operator vs this rendering geometry); C-190 (inverse failure: omission vs this phantom presence); C-205 (RESOLVED — the coastline overlay whose 1:110m microstate omission makes the real island cells look like floating pixels; that part is documented, not a defect); C-209 (the budget-contract half of the same fix — land together); Cluster F (value-correctness assurance). |

### C-209: Raster budget guard measures data rows, decoupled from the rendered z payload — breaks the C-203 contract under any dense-lattice fix — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-209 |
| Tier | 3 (contract/calibration fragility; mildly live today — the z already carries ~2× the guarded quantity (unique-lats × unique-lons × frames = 949k vs len(mdf) = 472k on the fixture) — and becomes acutely wrong the moment the C-208 uniform-lattice fix lands as first specified) |
| Source | /falsify audit of the C-208 fix spec (probes F2/F5, HARD falsification), 2026-07-15 |
| Resolved | 2026-07-16 (guard re-keyed + budget recalibrated; one PR with C-208) |
| Resolution | **The guard and the Compose-boundary ladder are now keyed to `pgm_lattice_cell_frames`** (uniform-lattice rows × cols × time-frames — the true payload driver), not `len(mapping_dataframe)`: sparse-but-spread data escalates to the PNG tier instead of sailing past the guard or being refused where PNG would work. **Budget recalibrated by measurement** (Simon's checkpoint call: keep the hover-capable heatmap): the Africa+ME ×36 uniform lattice renders at 39.1 MB = ~34 bytes/lattice-cell-frame, so `max_raster_cell_frames` default moved 1,000,000 → **2,000,000** (≈70 MB ceiling; Africa at 1.147M has ~1.7× headroom; globe×8-origins 2.07M refused / escalates — global-scale canary updated accordingly). Config docstring carries the new calibration; CIC guard semantics updated. |
| Trigger | Implementing the C-208 uniform-lattice fix without redefining the guard quantity — the fixture's own lattice (179×178×36 = 1,147,032 cell-frames) exceeds the 1,000,000 budget while `len(mapping_dataframe)` = 471,960 passes; adversarial-shape case: sparse-but-spread data (e.g. Africa data after the globe rollout) passes the guard at 472k while the z carries 9.3M cell-frames ≈ +177 MB of JSON nulls. |
| Location | `views_reporting/mapping/mapping.py` (the raster guard keyed to `len(mapping_dataframe)`); `views_reporting/config/_reporting.py` `max_raster_cell_frames` (calibrated at ~70 B/cell-frame of DATA); `templates/reports/forecast.py` (the tier-escalation ladder reads the same quantity). |
| Narrative | `max_raster_cell_frames` (C-203) was calibrated when payload ≈ data rows. The heatmap's dense z is really unique-lats × unique-lons × frames — already ~2× the guarded number today, and equal to the full bounding box under the C-208 fix. The guard, the tier-escalation thresholds, and the "~70 bytes/cell-frame" calibration all silently measure the wrong quantity once the representation densifies: a report can blow the byte budget with a green guard, or (fixture case) the standard Africa render lands over the calibrated budget with no defined behaviour — refuse, escalate to PNG, or recalibrate is an OPEN DECISION (needs-decision on the fix story). Remediation: key the guard and the Compose-boundary ladder to **lattice_cells × frames** computed from the coord extents; re-measure bytes/cell-frame with JSON nulls (~20 B) and recalibrate the budget (or accept PGM-Africa escalating to PNG); document in the C-26/C-203 lineage. xfail stub prepared (`test_raster_budget_is_keyed_to_lattice_size_not_data_rows`). |
| Cross-refs | C-26 (RESOLVED — the budget lineage this recalibrates; "C-203"/"C-204" therein are absorbed expert-review finding IDs, not register entries — see Register Conventions); C-208 (the geometry fix that makes this acute — land together); C-38 (sibling artifact-size growth mechanism); ADR-008/ADR-016 (fail-loud at the Compose boundary); Cluster C (PRIO-GRID scale discipline). |

### C-207: Uncollapsed sample frames silently render posterior draw #0 at the pandas seams — live in the historical HDI fallback — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-207 |
| Tier | 1 (silent wrong artifact: an arbitrary single posterior draw rendered AS the point estimate, no error/warning — one variant was **live in production**; demonstrated, not hypothetical) |
| Source | Pre-registered synthetic probe, epic #215 S1 / #216 (`documentation/investigations/sample_scaling_boundary.md`, predictions P5/P6 — CONFIRMED at all 7 grid points, 2026-07-06) |
| Resolved | 2026-07-13 (epic #215 complete: S2 guards PR #222, S3 canary PR #223, ADR-020) |
| Resolution | **Enforced per the checkpoint decision (Simon, #215: "refuse loudly + fix fallback").** (1) Both seams now raise `ValueError` on `sample_count > 1` naming `calculate_map_frame` as the remedy (`frames_to_mapping_df`, `_pred_df`; ADR-008; no config knob — S==1 is a contract invariant, not a budget). The guard sits INSIDE the seam, covering the pipeline-core `modules/mapping` shim bypass for free. (2) The LIVE variant fixed: the all-HDI-levels-failed fallback renders the entity's **MAP summary line** ("(HDI unavailable, MAP)") or, with no MAP frame, **nothing fabricated** (visible absence + loud log, C-11) — never draw #0. The HDI path no longer builds a pandas line from the raw sample frame at all (gates on entity presence; tower summaries only); the sanctioned S>1 line-graph flow (eval template) verified unbroken. (3) RED→GREEN in-PR history (characterization `09648c0` → guards). (4) Permanent CI canary at S=1000 over the real bundled Africa cells, unmocked: seam O(rows), value == tower MAP ≠ draw #0, raw frame refused (`tests/test_sample_scale.py`, ~10 s). Governance: **ADR-020** records both halves (samples numpy-bound/enforced; summary-shaped pandas in Rendering sanctioned, scoped); CICs updated. |
| Trigger (historical) | (a) **Live now:** any sample-forecast line graph where every HDI level fails for an entity — the "(HDI unavailable)" fallback line IS draw #0 (`historical.py:298-307`, demonstrated empirically); (b) **latent:** any caller invoking `MappingModule`/`frames_to_mapping_df` directly with an uncollapsed S>1 frame — including externally via pipeline-core's `modules/mapping/__init__.py` re-export shim — bypassing the template's collapse (`forecast.py:114-120`). |
| Location | `views_reporting/mapping/_frame_adapter.py:36` and `views_reporting/visualizations/historical.py:207` (both hard-code `frame.values[:, 0]`, ignoring `sample_count`); the live fallback at `historical.py:298-307`; the CIC that documents-but-does-not-enforce S==1: `documentation/CICs/cic_frame_mapping_adapter.md`. |
| Narrative | The render architecture's sample boundary — samples numpy-bound, collapsed to summaries by the views-frames tower before the pandas seam — is real and measurably sound (probe: the seam df is byte-identical across S; artifact HTML S-independent; see the investigation doc), but it is **enforced by nothing**. Both seams take `values[:, 0]`: handed an S>1 frame they silently render **draw #0** — which the probe confirmed differs from the tower MAP and emits **zero warnings** at every grid point (CM/PGM-Africa/PGM-globe × S∈{100..2000}). The sanctioned template path can't hit the mapping variant (`is_sample`≡`sample_count>1` forces collapse), but the historical variant **fires on the sanctioned path**: when all HDI levels fail, the fallback trace labeled "(HDI unavailable)" is exactly draw #0 (P6, demonstrated). Remediation (epic #215): S2 (#217) — restructure the historical fallback to render the already-computed MAP line (or the C-11 visible message), then raise `ValueError` on `sample_count > 1` at both seams (ADR-008; no config knob — S==1 is a CIC contract invariant, not a budget); S3 (#218) — CI canary pinning rendered-value==tower-MAP at S=1000; S4 (#219) — ADR-020 records the enforced boundary. **Discovered alongside (not a defect):** the true globe×samples constraint is MAP-collapse wall-time (~2–4×10⁶ elements/s ⇒ ~15–26 min at globe×S=1000), a tower compute-budget question orthogonal to pandas. |
| Cross-refs | C-11 (visible-degradation convention the fallback should follow); C-26/C-38 (the cells×time budget axis — the sample axis is orthogonal); C-35/ADR-019 (the tower that computes the summaries); ADR-008 (fail-loud); `cic_frame_mapping_adapter.md` (the documented-but-unenforced S==1 expectation this promotes to contract); epic #215 (S1 evidence #216, S2 guards #217, S3 canary #218, S4 ADR-020 #219); pipeline-core `modules/mapping` shim (the external bypass route). |

### C-117: `ReportModule.add_html` injects unescaped HTML while the rest of the builder is XSS-hardened — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-117 |
| Tier | 4 — **[backlog-watch]** (no live call-site violated the trust boundary; latent) |
| Source | repo-assimilation (2026-06-22) |
| Resolved | 2026-07-06 (documented trust boundary + misuse signal) |
| Resolution | **The register's own remediation ("document the trust boundary at the method and in the README claim") executed, plus a cheap visibility guard.** (1) `add_html`'s docstring now declares the TRUST BOUNDARY explicitly: input is embedded VERBATIM by design (figure HTML — Plotly with inline plotly.js, base64 maps — must pass raw); externally-influenced text belongs in the escaping methods. (2) Both README "XSS-safe" claims now state the deliberate exception instead of overclaiming a global invariant. (3) Misuse signal (ADR-008 spirit, no behaviour change for legitimate callers): a **markup-less** string (no `<`) arriving at `add_html` logs a warning — every legitimate input is figure markup, so a plain string is almost certainly a text-sink mistake; the warning makes it visible instead of silent. A sanitising/split path was considered and rejected: sanitisation would break the raw-figure purpose, and no live caller misuses the sink (all inputs are code-generated figure HTML). Tests: verbatim passthrough of script-bearing figure HTML, the markup-less warning fires, figure HTML does not warn (`tests/test_reports.py`, alongside the C-19 escaping tests). |
| Trigger (historical) | When a caller routes externally-influenced text (a model name, run note, user-supplied caption, or other non-plot string) through `add_html` instead of `add_paragraph`/`add_markdown`/`add_table` |
| Location | `views_reporting/reports/report.py:134-174` (`add_html` embeds its `html` argument verbatim), contrasted with `escape()` in `add_heading`/`add_paragraph`/`add_table`/`add_image` caption (`report.py:95,126,378`) |
| Narrative | The README advertises "XSS-safe content (`html.escape()` on all user-facing text)", and C-19 (resolved) added escaping to the text methods. `add_html` is a deliberate exception: it passes raw HTML through, which is required to embed Plotly figure HTML. That is correct for trusted plot output, but it means the invariant "all report text is escaped" is not globally true — report safety rests on the unstated assumption that callers only ever send trusted/generated HTML to `add_html`. No current call site violates this (all `add_html` inputs are Plotly/figure HTML), so there is no live defect (Tier 4). The risk is a future caller treating `add_html` as a general text sink. Remediation: document the trust boundary at the method (and in the README claim), or split a sanitised path from the raw-figure path. |
| Cross-refs | C-19 (RESOLVED — text-method escaping; this is the intentional raw-HTML complement) |

### C-22: VIEWSER runtime dependency for entity metadata — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-22 |
| Tier | 2 |
| Source | external-review (datafactory migration assessment) |
| Resolved | 2026-07-05 (epic #204 / #70, PRs #210–#213) |
| Resolution | **Bundled metadata assets replace the live fetch — zero viewser imports in the shipped package** (grep-guarded). `scripts/build_entity_metadata.py` freezes the two querysets into committed, wheel-shipped parquets (88 KB: `country_id → isoab, name` for 213 entities incl. retired states via `groupby(entity).last()`; `priogrid_id → country_id` — 13,110 Africa+ME cells at resolution time, superseded by the 66,205-cell global crosswalk bundle, see C-211 / #231) + `stamp.json` (C-112 guards). The accessors were rewritten **entity-keyed with month-broadcast**, which also fixed a confirmed latent bug: the old exact-`(month, entity)` keying silently NaN'd labels for months absent from the source — a forecast-month CM map could drop ALL countries (see epic #204). The register-entry subtlety ("verify isoab ↔ ADM0_A3 are identical values") was executed as the S3 join-coverage contract test and immediately caught **C-206** (South Sudan `SDS`≠`SSD`, silently absent from every CM map — fixed). Column narrowing vs this entry's described schema is deliberate: only `isoab`/`name`/`country_id` were ever consumed (the rest died with the C-114 accessor deletion); lat/lon/row/col come from the priogrid shapefile. viewser left `[project].dependencies` → the `metadata-refresh` dependency group (declarative honesty — pipeline-core keeps it transitively). PGM latest-assignment snapshot is a declared limitation (stamp). Reports render fully offline; air-gapped partner delivery unblocked; ADR-018's last tracked deviation discharged; Cluster A dissolved. |
| Trigger (historical) | When VIEWSER is retired/decommissioned, or when a report is generated in an environment without VIEWSER DB access (no SSH/VPN to the PRIO PostgreSQL) |
| Location | `views_reporting/metadata/entity_metadata.py:45` (pg_metadata Queryset), `:335` (country_metadata Queryset) |
| Narrative | `entity_metadata.py` issues live `Queryset(...).publish().fetch()` calls to VIEWSER at runtime to obtain lat/lon, gwcode, isoab, isonum, country name, capname/caplat/caplong, row/col, in_africa/in_me. Every one of these fields is static geographic reference data, derivable from the PRIO-GRID definition or available as a datafactory feature. This is the last significant VIEWSER runtime dependency in the visualization chain. When VIEWSER is retired (the same retirement driving the UNFAO migration), report generation breaks. Remediation: replace the Querysets with a bundled static lookup table (~2 MB parquet: pgid → lat/lon/row/col/iso3/name/gwcode) or a datafactory-sourced feature requested via `load_dataset()`. Subtlety: mapping joins on `isoab` (ISO alpha-3) against the Natural Earth shapefile `ADM0_A3` field; the factory provides `iso3_code` from GAUL — verify these are identical values before swapping. Tracked as GitHub issue #70. Note the metadata module splits by consumer: display-label functions (`get_isoab`, `get_name`) serve mapping/visualization and stay in this repo; spatial-mapping functions (`build_country_to_grids_cache`, `get_subset_by_country_id`) serve reconciliation and would leave with it (see C-24 cross-ref). |
| Cross-refs | GitHub #70 (viewser tracking); C-24 (reconciliation placement affects which metadata functions stay) |

### C-39: Entity-metadata accessor surface has no direct in-repo tests — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-39 |
| Tier | 4 |
| Source | repo-assimilation (2026-06-05) |
| Resolved | 2026-07-05 (epic #204 S2+S3, PRs #211/#212) |
| Resolution | **The real accessors are now directly tested in CI against the real bundled tables** — exactly the "naturally addressed if C-22 swaps the Querysets for a bundled lookup" path this entry predicted. `tests/test_metadata_accessors.py` (12 tests: future-month broadcast CM+PGM, label shapes, warn/raise semantics, missing-bundle fail-loud, cache hygiene, no-viewser grep guard) + `tests/test_metadata_contract.py` (join-coverage tripwire, golden values — Nigeria 79→NGA, an **unmocked** CM end-to-end render through frame → accessors → shapefile → geometry). The conftest doubles remain as *render seams* with their scope documented — they are no longer the only coverage. The mocked-seam blindness this entry warned about was real: the doubles fabricated values for any entity/month, which is how the future-months bug and C-206 (South Sudan) stayed invisible; both were caught by exactly the direct tests this entry called for. |
| Trigger (historical) | When `metadata/entity_metadata.py` accessors are refactored, or when VIEWSER's queryset return shape/column names change upstream — a signature/semantics regression would surface only at live report-generation time, not in CI |
| Location | `views_reporting/metadata/entity_metadata.py`. **Surface shrunk (2026-07-02, C-114 resolution):** the ~30 legacy dataset-parameter accessors were deleted as dead code; what remains untested is the live edge — `get_isoab_for_index` / `get_name_for_index` + the two `_fetch_*_metadata` querysets and `_level_metadata` cache. Exercised only indirectly (mocked) via the mapping/historical characterization tests |
| Narrative | The metadata module is the widest untested public surface in the repo. Its functions are mocked in the mapping/reconciliation tests but never exercised against a recorded/known VIEWSER response, so a regression in an accessor (renamed column, changed return shape, off-by-one in row/col, isoab vs iso3 mismatch) would not be caught by CI — it would appear as a wrong label/join at live report time. This is an **assurance gap, not a known defect**: no current incorrectness is demonstrated, the runtime path works, and the values are static reference data — hence Tier 4. Distinct from C-22, which concerns the *runtime dependency* on VIEWSER (report breaks if VIEWSER is unreachable); this concerns the *absence of regression coverage* for the accessors regardless of availability. Remediation: contract tests over a recorded/mocked VIEWSER fixture asserting each accessor's column names and return shape (and the isoab↔ADM0_A3 join key noted in C-22). Naturally addressed if the C-22 remediation swaps the Querysets for a bundled static lookup (which would be directly testable). |
| Cross-refs | C-22 (same module — runtime dependency vs. this test-coverage gap; the C-22 static-lookup remediation would make these accessors testable); C-29 (sibling assurance gap — render fidelity) |

### C-206: South Sudan silently absent from every CM map — Natural Earth's ADM0_A3 uses NE-internal codes that don't match VIEWS isoab — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-206 |
| Tier | 1 (silent wrong artifact: a conflict-central country missing from delivered CM maps with no error signal — found already-live, not hypothetical) |
| Source | C-22 S3 join-coverage contract test development (2026-07-05, epic #204 / #207) — the exact `isoab↔ADM0_A3` verification the C-22 entry called for |
| Resolved | 2026-07-05 (same PR as the discovering test) |
| Trigger (historical) | Any CM forecast/eval map containing South Sudan (present in the standard Africa coverage) — the country rendered as a hole, indistinguishable from "no data". |
| Location | `views_reporting/mapping/mapping.py` `__get_country_shapefile` (the merge key); the CM merge `left_on="isoab", right_on="ADM0_A3"`. |
| Resolution | **Merge-key normalization at shapefile load.** Natural Earth's `ADM0_A3` carries NE-internal codes for a handful of territories — decisively **South Sudan `"SDS"` vs ISO `"SSD"`** (the code VIEWS serves). The isoab merge found no match → NaN geometry → `__check_missing_geometries` dropped the row with only a debug-level trace: **South Sudan was silently absent from every CM choropleth**, including under the pre-C-22 live viewser (the bug predates the bundle — the bundled snapshot + contract test is what *surfaced* it). Fix: `__get_country_shapefile` now prefers `ISO_A3_EH` wherever it is a real ISO code, keeping `ADM0_A3` only for the `"-99"` disputed territories (N. Cyprus, Somaliland, Kosovo — no VIEWS isoab exists for them). Audit of the full divergence set confirmed **SSD is the only** code where NE-internal ≠ ISO intersects VIEWS data (W. Sahara/Palestine don't appear in VIEWS isoab). Guarded by `tests/test_metadata_contract.py::test_south_sudan_joins_the_shapefile` (the specific regression) and `test_bundled_isoab_subset_of_shapefile_adm0a3` (the general categorized-allowlist tripwire: retired states + 1:110m microstates; an uncategorized gap fails loud). The unmocked e2e renders South Sudan's geometry end-to-end. |
| Cross-refs | C-22 (whose register entry explicitly warned "verify these are identical values before swapping" — this is that verification, done); C-29 (the sibling join-drop class: the ~24 microstates absent at 1:110m are now a *documented category*, not a silent loss); C-190 (omission-reads-as-no-risk — the failure class this instanced); C-112 (the drift tripwire that now guards the key); Cluster F (value-correctness assurance). |

### C-114: views-reporting imports pipeline-core *private* dataset internals (`_CDataset`/`_PGDataset`/`_ViewsDataset`) across the repo boundary — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-114 |
| Tier | 2 |
| Source | gh-issue review (grounded in #138's brief + verified imports, 2026-06-22) |
| Resolved | 2026-07-02 (dead dataset-parameter accessor deletion; epic #137 closeout) |
| Resolution | **Closed by deleting the last coupled surface — it was dead code.** After #72 (reconciliation deletion) and the C-114 sprint (dataset-level stats retirement), the only remaining private-internal coupling was `metadata/entity_metadata.py`'s TYPE_CHECKING hints on its ~30 legacy dataset-parameter accessors (`get_pg_*(pg_dataset)` / `get_c_*(c_dataset)` / `get_name(dataset)` / `build_*_metadata_cache`). A caller audit (repo + tests + all sibling repos) found **zero live callers** — the render path consumes only the index-keyed `get_isoab_for_index`/`get_name_for_index` edge (`mapping/_frame_adapter.py`, `visualizations/historical.py`). The dead accessor layer and its `TYPE_CHECKING` import were **deleted** (not annotation-laundered), `metadata/__init__.py` trimmed to the live `*_for_index` surface. This decoupled C-114's close from the C-22 viewser sprint (the earlier prediction was they'd retire together; the accessors turned out to be deletable now, while the viewser *fetch* itself genuinely stays for C-22). Falsify **P6** promoted from xfail to a permanent guard: no `_CDataset`/`_PGDataset`/`_ViewsDataset` import anywhere in `views_reporting/`. views-reporting's arrow of the #113 cycle is now fully closed; the pipeline-core→reporting arrow remains pipeline-core's own ADP call (out of our scope). |
| Trigger (historical) | When pipeline-core refactors, renames, moves, or changes the contract of its **private** dataset internals `_CDataset` / `_PGDataset` / `_ViewsDataset` (or relocates `views_pipeline_core.data.handlers`) — views-reporting imports them directly and would break with no contract, deprecation path, or version signal; also any audit of cross-repo boundary conformance |
| Location | `views_reporting/reconciliation/reconciliation.py:12` (a **runtime** import, not TYPE_CHECKING), `reconciliation/dataset_export.py:13`, `metadata/entity_metadata.py:13,521,531`, `statistics/dataset_statistics.py:33` (the **private** `_CDataset`/`_PGDataset`/`_ViewsDataset`); plus public `PGMDataset`/`CMDataset` imports in `mapping/mapping.py`, `visualizations/historical.py`, `loaders/_protocol.py` (lower concern — those names are public) |
| Narrative | views-reporting reaches across the repo boundary into pipeline-core's **private** dataset internals — underscore-prefixed `_CDataset`/`_PGDataset`/`_ViewsDataset` from `views_pipeline_core.data.handlers` — at **8 sites across 4 modules**. Importing another package's underscore-prefixed names is an unprotected coupling: pipeline-core owes no stability guarantee on private symbols, so a refactor/rename/move there breaks reporting with no contract and no deprecation path. This is the **"cross-repo private leakage"** the roadmap names as **C-135's reporting side** — where **C-135 is a pipeline-core register ID, not previously registered in this repo's register** (this entry fills that gap). Fails **loud** (ImportError/AttributeError on the next pipeline-core internal change), not silent → Tier 2 structural fragility with a realistic trigger (pipeline-core is actively evolving these, and the frames migration touches them). It is the **compile-time-coupling sibling of C-108's runtime service-acquisition** (both Cluster A, both dissolved by the same inversion). Remediation: adopt **views-frames** (#137/#138) so the data contract routes through the leaf's published `PredictionFrame`/`SpatioTemporalIndex`/`SpatialLevel` (which import nothing internal), replacing the private reads — the same move that breaks the #113 cycle. Until then the coupling is load-bearing and unguarded. **Update (2026-06-28, #72):** the reconciliation subsystem — the only **runtime** `_CDataset`/`_PGDataset` import (`reconciliation.py:12`) plus `dataset_export.py`'s TYPE_CHECKING ones — is deleted. Remaining private-internal coupling is now only TYPE_CHECKING type-hints in `metadata/entity_metadata.py` and the dataset-level stats API in `statistics/dataset_statistics.py` (the falsify P6 probe still finds these). Materially reduced; not fully closed. **Update (2026-06-28, C-114 sprint / #113):** the **dataset-level statistics API** (`calculate_map`/`calculate_hdi`/… on `_ViewsDataset` + `get_subset_tensor`) is **retired** — only the frame-native `*_frame` variants remain — and `visualizations/distributions.py` (`PlotDistribution`) is migrated to a views-frames `PredictionFrame`. The **only remaining** private-dataset coupling in `views_reporting/` is now `metadata/entity_metadata.py`'s TYPE_CHECKING hints on its dataset-keyed VIEWSER accessors — which retire with the **C-22/#70 viewser sprint** (same edit surface). So C-114 closes fully with C-22; falsify **P1** now passes, **P6** stays xfail naming entity_metadata as the last holdout. views-reporting's arrow of the #113 cycle is closed for all but that one file; the pipeline-core→reporting arrow remains pipeline-core's own ADP call (out of our scope). |
| Cross-refs | C-108 (Cluster A root — the runtime-service-acquisition sibling of this compile-time coupling); C-30 (RESOLVED — the *sanctioned* prediction-manager boundary, a different and governed exception); C-13 (RESOLVED — an *internal* cross-module private import, distinct); #138 (the views-frames adoption move that removes this); #113 (the import cycle the same leaf routing breaks); roadmap C-135 / C-184 (the pipeline-core-side IDs this is the reporting side of); Cluster A. **Remediation status (falsify audit, 2026-06-24): S4 (loaders) + S6 (render) dropped the private reads on the *prediction render path*, but the coupling PERSISTS — confirmed still present at `reconciliation/reconciliation.py:12` (runtime) and in the parallel dataset-level statistics API (`calculate_map`/`calculate_hdi`/… on `_ViewsDataset` + `get_subset_tensor`, kept alive by the S2 equivalence oracle). Full removal is gated on the reconciliation move (#72) and retiring the dataset-level stats API in favour of the frame-native `*_frame` variants.** |

### C-205: Global PGM raster map has no geographic reference (no coastlines/borders) and equirectangular distortion — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-205 |
| Tier | 3 |
| Source | expert-code-review (Kleppmann, 2026-06-28) |
| Resolved | 2026-06-29 (globe-expansion readiness epic #188, S2–S5 / #190–#193) |
| Trigger (historical) | When a **whole-globe** PGM forecast map (post Africa+ME expansion) is rendered and a human tries to *orient* on it — locate a country/region by eye. |
| Location | `views_reporting/mapping/mapping.py` (`_coastline_xy`, the heatmap `borders` trace, `_plot_image_map`); `templates/reports/forecast.py` (the Compose-boundary ladder). |
| Resolution | **Closed by a coastline overlay + a scale-flat PNG tier — both shipped.** (1) **Orientability:** `_coastline_xy()` derives a kilobyte-scale lon/lat border polyline from the committed **Natural-Earth 110m country** shapefile (~700 KB on disk; the simplified line layer is tens of KB — **not** the 56 MB PRIO-GRID cell shapefile, C-23), built lazily + cached, with `np.nan` segment separators. It is overlaid on the raster heatmap (a static `go.Scattergl` `borders` trace, kept as trace 1 so the animation frames still target the heatmap at trace 0) and on the PNG (`ax.plot`, clipped to the data extent). So a global value-lattice is now geographically orientable. (2) **Globe-scale render:** because even the bounded heatmap (dense JSON animation frames) eventually exceeds the offline byte budget at true global × many origins, `_plot_image_map()` renders the latest-origin lattice as a base64 **PNG `<img>`** — payload `O(figure pixels)`, independent of cell/origin count — selected as the top tier of the render ladder (choropleth → heatmap → PNG) at the Compose boundary (ADR-016 / ADR-003) once a PGM grid exceeds `max_raster_cell_frames`. Faithful by construction (one cell → one pixel: no aggregation C-189, no omission C-190 — a missing cell stays no-data, never back-filled), log-coloured with a labelled original-scale colourbar (C-191), and labelled a per-cell **point summary** (C-109) consistently with the heatmap. **Tradeoff (documented):** the PNG is static — no per-cell value hover — which is exactly why the heatmap stays primary wherever it fits the budget. The equirectangular note remains in the title/labels (Longitude/Latitude axes). Guarded by `tests/test_mapping_image.py` (PNG boundedness / faithfulness / colour / coastline artist / priogrid-not-loaded / hover-loss), `tests/test_forecast_raster_select.py` (tier selection + escalation logging), and `tests/test_global_scale.py` (global-dimension canary). Governance: CIC `cic_mapping_module.md` documents the PNG strategy, the escalation tiers, the new `plot_map(image_fallback=)` param, and the hover-vs-scale tradeoff; the ladder is recorded as a declared decision (ADR-018 addendum, under ADR-003). |
| Cross-refs | C-26 (the raster path this annotates; the three-tier ladder completes its globe-scale remainder); C-23 (the heavy cell shapefile this deliberately avoids); C-191 (colour legibility — honoured on the PNG too); C-189/C-190 (faithfulness — preserved); C-109 (point-summary labelling); C-28 (offline/self-contained — the PNG is inlined); ADR-016 / ADR-003 / ADR-018 (the declared render ladder); Cluster C (scale discipline). |

### C-186: A views-frames version bump can silently change reporting's forecast numbers (behavioural drift under a fixed CONFORMANCE_FLOOR) — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-186 |
| Tier | 3 |
| Source | review-rr strategic (blind-spot analysis, 2026-06-24) |
| Trigger | When views-frames is bumped to a new version and the suite passes — a behavioural change in the tower estimators (like 1.2.0→1.3.0's zero-policy flip) can ship altered forecast numbers if no fixture exercises the affected regime |
| Location | `pyproject.toml` / `uv.lock` (the views-frames pin); `views_reporting/statistics/dataset_statistics.py` (tower point/interval); guarded only by `tests/test_tower_estimators.py` (law tests) + the characterization pins |
| Narrative | Since the tower adoption (ADR-019), reporting's forecast point/interval values are produced by the views-frames leaf. `CONFORMANCE_FLOOR` pins the **structural** contract (float32 / sample axis / integer ids) but **not behaviour** — so a minor/patch leaf bump can change the numbers within the same floor. Demonstrated by 1.2.0→1.3.0 (the zero-policy flip: sub-1 cells no longer zeroed): only **one** law test caught it, and the characterization fixtures are all `max>1`, so the sub-1 behaviour change would have passed silently had that law test not existed. Assurance/coupling gap, not a demonstrated defect (the 1.3.0 change was caught and intended) — Tier 3, **elevate to Tier 1 if a leaf bump ever ships a silently-changed forecast number to a partner deliverable**. Remediation: (a) a behavioural-contract test exercising the regimes the tower is sensitive to (sub-1 / zero-inflated / multimodal cells) so a behavioural change fails loud on bump; (b) pin views-frames to an exact version (not a range) for releases; (c) stamp the resolved views-frames version in report provenance (C-34 ✓ — the build-line footer now carries it). **Update (2026-06-26):** bumped 1.3.0 → **1.6.0** (C-108 Phase-3 dep alignment, ADR-019 addendum); the full suite passed with **zero flips** (1.4–1.6 are additive — substrate + exceedance estimator — not tower-behaviour changes), so no characterization literals moved. This is reassurance for the *covered* regimes only; remediation (a) — the behavioural-contract test over uncovered regimes — **remains owed**, and (b) exact-pin-for-release is still deferred while the development branches move in tandem. **Update (2026-06-28, #181):** bumped 1.6.0 → **1.7.0** (lockfile realign to pipeline-core's eval-of-record HEAD); full suite green with **zero** characterization/law drift — another covered-regime reassurance; remediation (a) still owed. **Update (2026-08-02, v0.3.1 floor bump — THE GATE'S FIRST REAL FIRING):** bumped 1.7.0 → **1.10.2**; views-frames **v1.9.0 deliberately changed the tip** (tip_mass 0.5 → 0.25, their ADR-019 Amendment 3, evidence-backed) and BOTH characterization pins flipped (values moved up to 33%, e.g. 2.66481 → 1.77628) while every law/equivalence/fidelity test held. **Attribution matters: the catch came from the pre-existing characterization literals, NOT from remediation (a)'s regime law tests — those passed straight through the tip-policy change (they pin regime behaviour and invariants, not the tip's mass parameter). A tip-policy change in a regime WITHOUT characterization coverage would still ship silently; the blunt literals are currently the only tip-definition tripwire.** Literals re-baselined; local ADR-019 carries the amendment note. Release consequence honestly recorded: **v0.3.0 shipped with floor `>=1.0.0`**, so 0.3.0 installs resolved views-frames 1.10.2 and produced the NEW numbers despite being tested on 1.7.0 — v0.3.1 closes that gap by raising the floor to the tested substrate (`>=1.10.2,<2.0.0`); residual (b) remains a floor, not an exact pin, accepted per platform convention. |
| Resolved | 2026-06-28 (Cluster F Phase 2) |
| Resolution | Resolved 2026-06-28 (Cluster F Phase 2 / C-186). Remediation (a) landed: `tests/test_tower_estimators.py` now exercises the previously-uncovered regimes — sub-1, heavy zero-inflation (≥85% zeros), and multimodal — with the regime-agnostic law invariants (lower≤upper, nesting across masses, tip∈HDI, determinism, finiteness) PLUS per-regime *behavioural* assertions encoding the tower's expected policy (sub-1 not zeroed; the zero-inflated point estimate collapses to 0; the multimodal tip lands in a mode, not the inter-mode gap). A 1.3.0-class behaviour flip in any of these regimes now fails loud on the next views-frames bump. (c) is already done — the resolved views-frames version is stamped in the C-34 provenance footer. Residual (non-test, tracked): (b) pinning views-frames to an exact version for releases (vs the current range) — **the 2026-08-02 narrative update refutes the earlier 'not a silent-drift risk' verdict here: v0.3.0's `>=1.0.0` floor let installs resolve views-frames 1.10.2 and ship tip numbers untested against our suite — silent drift caused precisely by this residual. v0.3.1 mitigates by raising the floor to the tested substrate; a true exact pin remains open, per platform convention.** |
| Cross-refs | C-35 (the tower adoption that created this coupling); C-185 (sibling tower-adoption debt); C-34 (provenance should stamp the leaf version); Cluster F; upstream views-frames C-45 (the 1.3.0 behaviour change). |

### C-29: No verification that values rendered in reports match source predictions — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-29 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When the MAP-collapse, shapefile-join, or index-handling code in the load → render chain is next modified — an index/merge bug there would silently map country A's forecast onto country B |
| Location | `views_reporting/templates/reports/forecast.py` (load → `calculate_map` → `MappingModule` join → render chain); no test asserts render-output values equal source-prediction values |
| Narrative | The test suite proves the pipeline does not crash and produces well-formed HTML, but nothing asserts that the value drawn on a given cell/country equals the corresponding source prediction after the MAP collapse and the shapefile join. The mapping join drops rows with unmatchable geometries (observed: 26 small island states dropped, 936 rows) — a silent reduction that a fidelity check would surface. A merge or index bug in this chain would be a silent-corruption path (wrong number shown for the right place, or right number on the wrong place) with no error signal. Currently an assurance gap, not a known defect — hence Tier 3, not Tier 1. **Elevate to Tier 1 if any render≠source divergence is ever observed.** Remediation: a fidelity test that round-trips a known fixture value from input through to the rendered GeoDataFrame and asserts equality per entity. |
| Resolved | 2026-06-28 (Cluster F sprint) |
| Resolution | Resolved 2026-06-28 (Cluster F sprint). `tests/test_render_fidelity.py` round-trips known per-(time,entity) values through `MappingModule.get_subset_mapping_dataframe` (CM + PGM) and asserts the rendered value lands on the right place (value + join key) — catching any MAP-collapse / merge / index scramble (right number on the right place). A second test pins the unmatchable-entity drop (C-29's 26-island case): the dropped entity is absent and the survivors keep their exact values, so a *new* silent drop fails loud. The Tier-1 elevation trigger is unchanged (if a real render≠source divergence is ever observed). |
| Cross-refs | C-11 (silent HDI degradation — prior silent-rendering class); C-01 (silent MAP corruption — prior silent-compute class) |

### C-41: Canonical report-metric names can drift from the evaluator's emitted tokens — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-41 |
| Tier | 3 |
| Source | expert-design / ADR-017 (canonical evaluation-report metrics, 2026-06-06) |
| Trigger | When `views_evaluation` (or a model config) renames, adds, or re-tokenises a metric (e.g. changes how a metric key is spelled in the WandB run summary) without a matching update to `ReportingConfig.canonical_report_metrics` |
| Location | `views_reporting/config/_reporting.py` (`canonical_report_metrics`) vs the metric tokens emitted into the WandB run summary by `views_evaluation`; matched via `reports/utils.py:search_for_item_name` (segment match on `[eval_type, metric, target, "mean"]`) |
| Narrative | ADR-017 makes the report attempt a central canonical metric set and pull values from the run by token-matching the metric name. If a canonical name no longer matches the evaluator's emitted token, the metric will **always** render as "not calculated" even though it *was* computed — a plausible-but-misleading report (the failure is visible as a note, not silent corruption, hence Tier 3 not Tier 1). This is a cross-repo coupling: the canonical names in views-reporting must track the metric naming in views_evaluation / model configs. Mitigation: keep canonical names identical to the model-config metric names (which drive the evaluator); a contract test comparing the canonical map against a known real run's summary tokens would catch drift early. The "not calculated" note bounds the damage to confusion, not wrong numbers. |
| Resolved | 2026-06-28 (Cluster F sprint) |
| Resolution | Resolved 2026-06-28 (Cluster F sprint). `tests/test_canonical_metric_contract.py` asserts every `ReportingConfig.canonical_report_metrics` token is an *implemented* views-evaluation metric in the correct `METRIC_MEMBERSHIP` cell (imported from `views_evaluation.evaluation.metric_catalog`), plus the segment-prefix self-consistency rule — so a name-drift between the report's canonical set and the evaluator's tokens fails loud in CI instead of silently rendering 'not calculated'. |
| Cross-refs | ADR-017; C-27 (WandB coupling — surrounding eval-report dependency); C-39 (sibling assurance/coverage gap) |

### C-24: torch (~2 GB) dependency coupled to reconciliation living in a reporting repo — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-24 |
| Tier | 3 |
| Source | external-review (datafactory migration assessment) |
| Trigger | When packaging views-reporting for a lightweight or reports-only deployment, or when the ~2 GB PyTorch install becomes a measured constraint in a reports-only environment — torch is pulled for proportional scaling math that is, at core, per-country divide-by-sum then multiply-by-total |
| Location | `views_reporting/statistics/statistics.py:439` (ForecastReconciler, torch device), `views_reporting/reconciliation/reconciliation.py`, `views_reporting/reconciliation/dataset_export.py` |
| Narrative | `ForecastReconciler` uses torch (GPU-capable) for proportional reconciliation. The dependency is heavy relative to the arithmetic it performs. The external review flags this but defers it; the resolution is not standalone tuning — it is the reconciliation-placement question. torch lives in views-reporting *only because reconciliation lives here*. If reconciliation moves to views-postprocessing (GitHub #72 / views-postprocessing#3), torch leaves views-reporting entirely and this concern dissolves. Do not optimize the torch path in place; resolve via the reconciliation move. |
| Resolved | 2026-06-28 (#72) |
| Resolution | Resolved 2026-06-28 (#72). Reconciliation — torch's only consumer in this repo — was deleted; reporting renders, it does not reconcile. The live reconciler is `views_frames_reconcile` (views-frames, numpy, no torch), consumed by pipeline-core via an injected `Reconciler` protocol and wired in views-models. `torch` is dropped from `pyproject.toml`; `git grep 'import torch' views_reporting/` → none. |
| Cross-refs | GitHub #72 (reconciliation → views-frames); D-08, D-09 (reconciliation design debates) |

### C-33: Determinism of parallel reconciliation output is unverified — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-33 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Trigger | When a delivered forecast must be reproduced exactly (audit, re-delivery, regression baseline) and parallel reconciliation output is found to vary run-to-run, or when debugging a reconciliation discrepancy |
| Location | `views_reporting/reconciliation/reconciliation.py` (ProcessPoolExecutor parallel execution); `views_reporting/statistics/statistics.py` (`ForecastReconciler`) |
| Narrative | Reconciliation runs across worker processes via `ProcessPoolExecutor`. Nothing in the register or test suite asserts that the assembled output is deterministic — independent of worker completion order, process count, or unseeded RNG in torch/numpy. For a forecasting *deliverable*, run-to-run variation (or worse, completion-order-dependent value assignment) would be a reproducibility/traceability failure. This is an assurance gap, not a demonstrated defect — if a concrete order- or seed-dependent value path is found, it becomes a silent-corruption concern (elevate toward Tier 1/2). Remediation: a determinism test (same input → byte-identical reconciled output across repeated runs and worker counts); confirm results are assembled by input key, not completion order, and that any RNG is seeded. Note: this concern relocates with reconciliation if it moves to views-postprocessing. **Compounding (repo-assimilation 2026-06-18):** failed `(country, time, target)` tasks are logged + WandB-alerted but the `raise RuntimeError` is commented out (`reconciliation.py:272-275`), so `reconcile()` returns a **partial** `reconciled_dataframe` as a success — silently completing fewer cells than submitted. A determinism/completeness guard should also assert the result count equals the submitted task count (or fail loud on any failed task). **Re-confirmed (expert-code-review 2026-06-28):** the partial-success path is still live — the `raise` remains commented at `reconciliation.py:272-275` and `reconcile()` assembles `result_df` from the **successful results only** (`:280-290`, post-D-09 de-mutation). Fixing it — loud-fail on any failed task, or an explicit partial-result signal plus a completeness assert — is a **precondition for the #72 relocation**: moving the module as-is would export this silent-incompleteness defect into views-postprocessing. Carries a latent **Tier-1** path on the silent-incompleteness branch. |
| Resolved | 2026-06-28 (#72) |
| Resolution | Resolved 2026-06-28 (#72). The parallel `ProcessPoolExecutor` reconcile path — including the partial-failure-as-success branch (the commented-out `raise`) — is deleted with the subsystem. The live reconciler `views_frames_reconcile` is single-process numpy, parity-proven against the former `ForecastReconciler` (frozen oracle, rtol=1e-5), so this determinism/completeness bug class no longer exists in views-reporting; any residual completeness concern is views-frames' to own. |
| Cross-refs | Cluster B (reconciliation placement); C-24 (torch/placement), D-08 (worker data shape), D-09 (return vs mutate); GitHub #72 (relocates if reconciliation moves) |

### C-26: No scale guard — full global PGM rendering may OOM or produce multi-GB reports — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-26 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Resolved | 2026-06-27 (#118 guard + #125 raster) |
| Resolution | **Two-step: refuse, then render.** (1) #118 added the fail-loud cell-count guard (`max_map_cells`, default 50K) — an oversized *vector choropleth* raises before any trace construction. (2) **#125 delivers the deferred capability**: PGM-at-scale renders as a bounded **raster `go.Heatmap`** over the grid lattice (`_plot_interactive_raster_map`), opt-in via `ReportingConfig.pgm_raster` (declared, ADR-003) and exempt from the guard. The raster embeds **no polygon GeoJSON** (the ~260K-polygon base geojson is now built lazily and skipped on this path), so payload scales with cells, not polygon geometry — the full grid is renderable within the report budget (smoke: 4.7 MB raster vs 57 MB choropleth for identical data, the gap being the embedded geojson). Faithful by construction (one cell → one array element: no aggregation C-189, no omission C-190); colour is log-scaled with a labelled colourbar (addresses C-191 for PGM); the map is labelled a per-cell point summary (C-109). Guarded by `tests/test_mapping_raster.py` (heatmap type, no geojson, lazy-geojson, value→lon/lat mapping, guard-exemption, bounded size, CM fallback). **CORRECTION + completion (2026-06-28, "restore PGM raster" sprint):** the 2026-06-27 "Resolved" was **premature** — #125 shipped the raster *code* but it was **unreachable** (`forecast.py` hard-read `pgm_raster=False`, a frozen singleton with no setter; pipeline-core passed nothing; nothing ever set it true) **and unguarded** (the raster was unconditionally exempt from any budget). Net: large-PGM forecast reports *fail-loud-refused with no way to reach the replacement* — a functionality regression (the "eyeball the PGM forecast" capability was switched off, not made efficient; expert-code-review **C-204**). This sprint completes it: (a) **reachability** — `forecast.py` now auto-selects the raster at the Compose boundary (ADR-016) for any PGM grid exceeding `max_map_cells` (small PGM + CM keep the choropleth; `pgm_raster` remains an explicit override); (b) **frame-aware budget** — the raster is no longer unconditionally exempt: a new `ReportingConfig.max_raster_cell_frames` (default 1,000,000 ≈ a ~70 MB offline-HTML ceiling; the Africa+ME ×36-origin grid is ~472k cell-frames ≈ 33 MB) fails loud on the pathological full-globe × many-rolling-origins case (expert-code-review **C-203**), since each animation frame is a dense lattice array; (c) **hover** — the raster tooltip now carries the **cell id (gid)** + value (heatmap's edge over a static PNG). Tests: `test_mapping_raster.py` (cell-id hover, frame guard fires/passes) + `test_forecast_raster_select.py` (oversized PGM→raster, small PGM→choropleth, CM never rasters). **Globe-scale remainder — now delivered (2026-06-29, globe epic #188):** at true global × many origins even the bounded heatmap eventually exceeds budget, so the render path is now a **three-tier ladder** declared at the Compose boundary (ADR-016 / ADR-003): choropleth → **raster heatmap** (primary, hover-capable: cell-id + value) → **PNG image** (`_plot_image_map`, matplotlib → base64 `<img>`, payload `O(pixels)`, scale-flat) once a PGM grid exceeds `max_raster_cell_frames`. A **coastline/border overlay** (Natural-Earth 110m, C-205) makes both the heatmap and PNG geographically orientable; both remain labelled a per-cell **point summary** (C-109) and log-coloured with a labelled colourbar (C-191). The PNG's one tradeoff is **no per-cell hover** — which is why the heatmap stays primary wherever it fits. Tests: `test_mapping_image.py` (PNG boundedness / faithfulness / colour / coastline / hover-loss), `test_forecast_raster_select.py` (tier selection + escalation logging), `test_global_scale.py` (global-dimension canary). See **C-205 (Resolved)**. |
| Trigger (historical) | When a forecast report is generated for a full global PRIO-GRID-month model (all ~260K cells, multi-target, multi-origin) rather than the Africa+Middle East subset, or when a PGM evaluation report renders many origins |
| Location | `views_reporting/mapping/mapping.py` (the `plot_map` guard + the raster path); `ReportingConfig.pgm_raster`; `templates/reports/forecast.py` (Compose-boundary opt-in) |
| Narrative | The original extraction from pipeline-core was driven in part by PGM-scale rendering failures (172K Plotly traces, multi-GB HTML, OOM — tracked as C-105/C-106 in pipeline-core, never migrated here). `mapping.py` renders one polygon per cell with no cap, pagination, downsampling, or streaming. The demo PGM report (~13K cells, one origin) is already 86 MB; a full global grid (~260K cells) across multiple origins/targets would multiply this. No guard, no warning, no documented limit. This is the exact failure class the extraction was meant to make addressable — but the fix was never implemented, only relocated. Fails loud (OOM/browser hang) or degrades (unusable file size), not silent. Remediation: entity-count guard with explicit failure or downsampling path; possibly static raster tiles for large grids instead of per-cell vector polygons. **MITIGATED (#118, 2026-06-20):** an explicit **fail-loud cell-count guard** landed in `plot_map` — when the rendered entries (`len(mapping_dataframe)` = entities × time steps) exceed `ReportingConfig.max_map_cells` (default 50,000), it raises a `ValueError` naming the count + limit + override **before any trace construction**, converting the catastrophic case from a *late, uncontrolled* OOM crash / unusable multi-GB file (the original "fails loud but degrades" framing above) into an *early, controlled, actionable* refusal. The threshold is injected at the Compose boundary (ADR-016); the Render layer never reads config. **Residual (now closed):** the **downsampling / raster-tile** path (render large grids rather than refuse them) was deferred to #125 and is now delivered as the bounded raster heatmap (see Resolution above). |
| Cross-refs | Extraction postmortem (C-105/C-106 in pipeline-core); C-23 (the 56 MB shapefile feeds the choropleth path); #118 (the fail-loud guard); C-189/C-190/C-191 (the #125 large-render methodology guards); C-109 (point-summary/uncertainty); **C-205 (the globe-scale PNG + coastline tier that completes the ladder, Resolved)**; ADR-016 (config injected to the Render layer); ADR-008 (fail-loud); ADR-003 (the ladder is a declared decision) |

### C-28: Rendered reports depend on external CDNs (Tailwind, Plotly) at view time — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-28 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When a generated HTML report is opened in an air-gapped, offline, or CDN-blocked environment (e.g., a partner organization's restricted network) |
| Location | `views_reporting/reports/styles/tailwind.py`; `views_reporting/reports/report.py` |
| Resolved | 2026-06-26 (#132) |
| Resolution | **Reports now render fully offline — no CDN.** The Tailwind utilities + the repo's theme tokens are vendored as a static `views_reporting/reports/assets/tailwind.css` (generated by `scripts/build_tailwind_css.sh` via the Tailwind v3 CLI — Node only to *regenerate*, never at runtime/in the wheel) and inlined by `get_css()`; the former Play-CDN `<script>` + JS `tailwind.config` are gone. The redundant Plotly-CDN `<script>` is neutralised (`_get_plotly_script` → `""`) since both viz paths already inline plotly.js. Asset confirmed shipped in the wheel (`packages = ["views_reporting"]`). Guarded by `tests/test_offline_assets.py` (no `https://cdn.` in `get_css()` or an exported report; utilities/tokens inlined). Approach note: Tailwind v3 is JIT-only (no downloadable full build), so the asset is CLI-generated-once-and-committed rather than downloaded; the JIT-scan's coverage risk is closed by C-187's test. |
| Cross-refs | C-187 (vendored-CSS class-coverage guard, RESOLVED with this); C-188 (machine-readable provenance, RESOLVED with this); Cluster G. |

### C-187: Vendored Tailwind CSS may omit classes the templates use — silent unstyled elements — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-187 |
| Tier | 4 |
| Source | expert-code-review (Nygard/Feathers seats, 2026-06-26) |
| Trigger | When the vendored CSS omits a Tailwind class a template uses (now or after a later edit) → that element renders unstyled with no error |
| Location | `views_reporting/reports/styles/tailwind.py` (`get_css` → vendored CSS); the templates emitting Tailwind classes |
| Resolved | 2026-06-26 (#132) |
| Resolution | **Closed by a coverage guard, not by a full dump.** The vendored asset is JIT-generated from the templates (the content scanner reads every literal class token in the `.py` files, including inside f-strings); `tests/test_offline_assets.py::TestClassCoverage` then fails loud if any emitted Tailwind class is absent from `get_css()` (escaping-aware; an allowlist excludes intentional unstyled semantic hooks like `report-footer`). So a future template class that isn't regenerated into the asset breaks CI rather than shipping unstyled — the gap the entry warned about cannot ship silently. If the scanner ever misses an arbitrary-value class, the fix is the `safelist` in `scripts/build_tailwind_css.sh`. |
| Cross-refs | C-28 (the offline work this guards); C-26/C-38 (inlined-payload size context); Cluster G. |

### C-188: Report provenance is human-readable only — no machine-readable identity for a future report catalog — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-188 |
| Tier | 4 |
| Source | expert-code-review (Kleppmann/Feathers/Hickey seats, 2026-06-26) |
| Trigger | When an online catalog/ledger of generated reports needs to index reports by model / run_id / target / date / versions |
| Location | `views_reporting/reports/report.py` (`export_as_html`) |
| Resolved | 2026-06-26 (#132) |
| Resolution | **Each report now embeds its identity as parseable data.** `export_as_html` emits a `<script type="application/json" id="views-report-provenance">` block carrying the same identity the C-34 footer renders as prose (build info, pipeline version, timestamp, the provenance dict) — `<` escaped to prevent `</script>` breakout. A future report catalog can read a report's identity without scraping rendered HTML. Guarded by `tests/test_offline_assets.py::TestMachineReadableProvenance` (block present + parseable + expected keys). The catalog itself remains a separate future component (not built now — YAGNI), and this is complementary to WandB, not a re-implementation. |
| Cross-refs | C-34 (the provenance footer this makes machine-readable); C-28 (shipped together); Cluster G. |

### C-34: Reports carry no provenance — no model-run / data-version / code-revision stamp — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-34 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Trigger | When a partner (e.g., UN FAO) or an auditor needs to trace a delivered report back to the exact model run, data version, and code revision that produced it |
| Location | `views_reporting/reports/report.py` (`ReportModule` assembly/export); `views_reporting/templates/reports/` (templates) |
| Resolved | 2026-06-26 (#131) |
| Resolution | **The do-now provenance stamp landed: every exported report is now self-identifying.** `export_as_html` *always* renders a footer carrying a generation timestamp + a build line — `views-reporting vX (git_sha) · views-frames vY · views-pipeline-core vZ` — even when no footer is set (the templates previously never called the footer hook, so reports shipped with *no* footer at all). A new module-level `get_build_info()` reads package versions via `importlib.metadata` (missing → `"unknown"`) and the git short SHA via `subprocess` (failure → `"unavailable"`); it **never raises**. `add_footer(text=None, *, provenance=None)` gained a structured `provenance` dict rendered as escaped `key: value` rows (`None` omitted; positional `text` back-compatible). Both templates set it: **forecast** stamps model/target/run_type/level/targets/prediction_path; **evaluation** stamps model/target/run_type/eval_target/level + the frame provenance (`run_id`, `data_version`, `scoring_code_version` — no WandB url/owner since the C-108 inversion) (+ constituent models for ensembles) — the views-frames version (C-186) is carried by the build line. All values HTML-escaped (C-19/C-117). Covered by `tests/test_reports.py::TestProvenanceFooter` (build-info shape, graceful SHA-unavailable, always-rendered stamp, escaped fields, None-omission, positional back-compat) + e2e footer assertions in `test_e2e_synthetic.py` / `test_e2e_eval_report.py`; CIC `cic_report_module.md` documents the footer + `get_build_info`. **Scope note:** this is the do-now source stamp; the durable source-of-record provenance (typed run/data lineage) remains Phase-3 `MetricFrame` territory. **Deferred within scope:** data-version is not derivable from inputs today (omitted gracefully); build-time SHA baking noted as a future enhancement (runtime `git rev-parse` used now). |
| Cross-refs | C-28 (partner-delivery robustness context, Cluster G); C-27 (WandB is the run-metadata source); C-186 (leaf-version drift — the stamped views-frames version serves it); C-113 (actuals provenance — to fold into this stamp later) |

### C-116: `search_for_item_name` returns the first of multiple matches — silent wrong-metric-value path — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-116 |
| Tier | 2 |
| Source | repo-assimilation (2026-06-22) |
| Location | `views_reporting/reports/utils.py` (`search_for_item_name`); `templates/reports/evaluation.py` (`_canonical_row`); `templates/reports/evaluation_run_resolver.py` (`_carries_canonical_metrics`) |
| Resolved | 2026-06-26 |
| Resolution | **Closed the silent wrong-value path (ADR-008 fail-loud + C-40 visible degradation).** `search_for_item_name` now takes `on_ambiguous` (default **`"raise"`**): >1 match raises `ValueError` instead of silently returning `matches[0]`. The **value site** (`_canonical_row`) catches it and renders a **visible "ambiguous — multiple matching keys"** cell — not a guessed number, and the report still generates; the **benign sites** (`_maybe_sort`; the resolver's presence check `_carries_canonical_metrics`) opt into `on_ambiguous="first"`. The previously **unenforced** segment-prefix naming rule (`config/_reporting.py`) is now enforced by a **contract test** (`tests/test_report_utils.py::TestCanonicalMetricCollisions` — no canonical token is ambiguous against its own keyset), plus unit tests for the three modes and an e2e test that a colliding token renders "ambiguous" without crashing. CIC `cic_evaluation_report_template.md` documents the new visible failure mode. |
| Cross-refs | C-41 (sibling: name-drift → "not calculated"); C-110 (the C-48 interim fix's silent-wrong-number path); C-29 (render fidelity); Cluster F; ADR-008. |

### C-35: MAP/HDI correctness on pathological posteriors is unguarded — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-35 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis, 2026-06-04) |
| Location | `views_reporting/statistics/statistics.py` (`PosteriorDistributionAnalyzer`); `views_reporting/statistics/dataset_statistics.py` (render path) |
| Resolved | 2026-06-24 |
| Resolution | **Resolved in two steps, both onto the principled views-frames tower.** (1) The **render path** (`dataset_statistics.py`) moved to `tower_point` + `hdi_tower` (ADR-019): a mode-bias-free tip + constrained-nested HDIs, guarded by `tests/test_tower_estimators.py` (nesting, tip∈HDI, zero-cutoff, NaN locality, determinism) and the re-pointed equivalence oracle. (2) The standalone **`PosteriorDistributionAnalyzer`** (this entry's original Location) now delegates to `views_frames_summarize.summarize_tower` (epic #157 — S1 #158, S2 #159); the manual `_enforce_hdi_structure` patch and the histogram-mode `bins`/`zero_mass_threshold` knobs were deleted (nesting + tip-in-floor hold by construction), and a `bimodal` flag is surfaced for the genuinely-multimodal case the original concern named. Both estimators are now the conformance-tested tower, so the "plausible-but-wrong, no error signal" gap is closed and law-tested. Residual naming debt (`*_map` now carries a tip, not a MAP) is tracked separately as C-185. **Follow-up (views-frames 1.3.0 adoption, 2026-06-24, ADR-019 addendum):** bumped to 1.3.0 → tower is now distribution-agnostic (no sub-1 zeroing by default; `zero_cutoff` not re-imposed). Forecast-output change: sub-1 cells render their value, not 0 (intended). One law test flipped; no characterization literals changed; floor still `1.0.0`. |
| Cross-refs | C-29 (sibling assurance gap — render fidelity); C-11 / C-12 (resolved); C-185 (the `*_map` misnomer the tower tip introduces); Cluster F; ADR-019; epic #157 (#158/#159/#160); upstream views-frames C-32/C-33/C-44 (the inherited tower fixes). |

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
| Narrative | Production code imports `wandb` and `viewser` directly, but `pyproject.toml` declared only `views-pipeline-core` — both were pulled in **transitively**, so the package worked only by accident of the transitive graph; an upstream dependency-tree change would have broken first-party imports with no lockfile-visible signal. Fails loud (ImportError), not silent — Tier 3. **Update (2026-06-27, B2):** wandb is no longer used by the evaluation path (the eval scrape is deleted, C-108); the only remaining wandb use is `reconciliation/reconciliation.py` (`wandb.AlertLevel`), which drops with the reconciliation relocation (#72). **Update (2026-06-28, #72):** `wandb` and `torch` are no longer direct dependencies — reconciliation (their only first-party consumer) is deleted, so both were removed from `pyproject.toml` (wandb remains only transitively via pipeline-core; nothing in views-reporting imports it). Dropping them surfaced `jinja2` as an undeclared transitive freeloader (required by pandas `DataFrame.style` in `reports/report.py:732`) — now declared explicitly. `viewser` remains the one declared direct dep, leaving with C-22. |
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

**Update (2026-06-28, #72):** `ForecastReconciler` is deleted from views-reporting. This all-negative-grid edge case (and the rest of the algorithm) is captured in the frozen parity oracle that `views_frames_reconcile` reproduces (rtol=1e-5); the behaviour is now owned by views-frames.

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

### C-27: WandB is a hard runtime dependency for evaluation reports — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-27 |
| Tier | 3 |
| Source | review-rr (blind-spot analysis) |
| Trigger | When an evaluation report is requested in an environment without WandB access (CI, offline, air-gapped), or for a model whose WandB run is missing/expired/deleted |
| Location | `views_reporting/templates/reports/evaluation.py:50` (`generate(self, wandb_run, target)` requires a live `wandb.apis.public.runs.Run`); `:17` imports `get_latest_run` |
| Narrative | `EvaluationReportTemplate.generate()` requires a live WandB run object; all metrics and run metadata are read from `wandb_run.summary`/`wandb_run.config`. There is no local-metrics fallback — evaluation reports cannot be produced without WandB connectivity and an existing run. This is the same class of runtime-external-service coupling as C-22 (VIEWSER), but distinct: VIEWSER serves static geographic data that is replaceable with a bundled table, whereas WandB is the actual source of the evaluation metrics, so the coupling is more inherent and has no trivial local substitute. Lower severity than C-22 for that reason — it is working-as-designed availability coupling, not removable fragility — but it should be documented so report generation in restricted environments is known to be impossible without WandB. Fails loud. |
| Cross-refs | C-22 (parallel runtime-external-service dependency — VIEWSER) |
| Resolved | 2026-06-27 (B2 / C-108) |
| Resolution | Resolved 2026-06-27 (B2 / C-108). The evaluation report no longer imports or requires WandB. `EvaluationReportTemplate.generate(self, source, target)` renders from an injected `EvaluationSource` — pipeline-core's reporting stage constructs a `MetricFrameFileSource` over the persisted MetricFrame. The `wandb_run` kwarg, `get_latest_run`, and the wandb import are gone; eval reports now generate offline/air-gapped. WandB remains a dependency only for `reconciliation/` (`wandb.AlertLevel`), which drops with #72 — see C-44. |

---

### C-48: Evaluation report reads constituent metrics from the WandB cloud replica, not the authoritative local eval files — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-48 |
| Tier | 2 |
| Source | expert-code-review (root-cause review, 2026-06-18); **CONFIRMED** via multi-agent live-WandB investigation (2026-06-18) |
| Trigger | When an evaluation/ensemble report is generated for models that have been re-run after their eval run (so the most-recently-*created* WandB run is not the eval run), or in an environment whose installed `views-pipeline-core` lacks the #177 `get_latest_run` contract / whose WandB cloud state differs from the local run — the report omits or mislabels constituents. **This has now been observed in the production runtime (see evidence below), not just latent.** |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_report_content` → `get_latest_run().summary`); authoritative local copy written by `views-pipeline-core/.../managers/prediction/io.py:146` (`save_evaluations` → `eval_<run_type>_<target>_{step,ts,month}_<ts>.parquet`) |
| Narrative | The ensemble report sources each constituent's metrics from the **WandB cloud** (`get_latest_run().summary`) even though the pipeline writes those same metrics **authoritatively to local disk** (`save_evaluations()` saves `eval_*.parquet`, *then* also logs to WandB). The report therefore reads a **mutable, eventually-consistent, network/version/environment-dependent remote replica of a value it already has on disk** — two sources of truth, wrong one chosen. This single design choice is the upstream **root cause** of the entire #105/#106/#177 saga: offline-run-has-no-cloud-project, silent constituent drops, the `None`-vs-raise contract (#177), the `retry`/`strict_constituents` symptom-management in #105, the "Could not find project" string-matching, and the conda-editable-vs-`.venv`-pinned-vs-published pipeline-core version skew. It can produce **silent wrong output** (a report that omits/mislabels constituents) — **elevate toward Tier 1 if that is ever observed in the production runtime**; Tier 2 today because production reports are generated in the conda `views_pipeline` env (editable pipeline-core *with* #177) and CI mocks the call (see C-46). **Remediation is UNCERTAIN and not yet decided (deliberately):** reading the local `eval_*.parquet` instead of the cloud is the obvious candidate and would delete the whole failure class, **but it is NOT assumed viable for the larger/distributed setup** — constituent models may be trained/evaluated on different machines or at different times, so their local eval files may not be co-located on the machine that builds the ensemble report (likely *why* the cloud fetch exists). Candidate mechanisms (read-local / caller-injects-resolved-runs / a real metrics-store abstraction) are an open **team design question**. Logged as "one day we will fix this; solution undecided," not an action item now. #105/`strict_constituents` make the gap *visible* but do not remove the coupling. **CONFIRMED MECHANISM + EVIDENCE (2026-06-18, multi-agent WandB investigation):** the defect is sharper than "wrong replica" — `get_latest_run` selects each model's **most-recently-*created*** run, **not** the latest run that actually carries the canonical eval metrics. Verified against live WandB for a real production ensemble report (target `lr_ged_sb`, `run_type=calibration`) by replaying the report's own `format_evaluation_dict` + `search_for_item_name` logic per run: **22 of 25 constituents render "not calculated" for ALL canonical reg-point metrics (MSLE/MSE/MCR_point/y_hat_bar) solely because the selected run lacks them, while an EARLIER run holds the full set under the exact expected key `time-series-wise/lr_ged_sb/<metric>_mean`.** The selected runs carry zero eval-metric keys under *any* eval_type/target (so it is **not** name/target drift) and have `_timestamp=null` (non-eval runs created after the eval run). Heavily re-run models are worst hit (run counts e.g. fast_car 204, brown_cheese 396, bittersweet_symphony 534). The 3 that render values (chunky_bunny, average_cmbaseline, zero_cmbaseline) are simply those whose newest run *happens* to be the eval run. The visible note ("add '<metric>' to `regression_point_metrics`") actively **misdirects** the user toward a config change when the real cause is run selection and the data already exists in an earlier run. **This is the elevation trigger firing in the production runtime** — the report is largely useless/misleading, observed (not latent). Kept Tier 2 because the failure is *visible* ("not calculated" notes), not a silently-wrong *number* — but it carries a latent **Tier-1** path: a model with multiple metric-bearing runs could have `get_latest_run` pick the wrong eval run and show a plausible-but-wrong NUMBER with no note. **Added remediation candidate:** metric-aware run selection (pick the latest run that actually contains the canonical metrics) — narrower than read-local and would fix the observed 22/25 case; read-local from `eval_*.parquet` (original C-48 framing) remains the durable option. Both stay a team design decision. **STATUS UPDATE (review-rr 2026-06-22):** the observed 22/25 production failure is now **mitigated by the shipped interim** (metric-aware run selection, #116 — see C-110); the "firing in production / observed (not latent)" framing above is **historical (pre-#116)**. What remains open in C-48 is the **durable** source-of-truth fix (read-local / injected `MetricFrame`), gated on views-frames (C-108). |
| Cross-refs | C-46 (tests mock `get_latest_run` → CI cannot catch the env/version skew — false confidence); C-27 (WandB hard runtime dependency for eval reports); C-22 (viewser — same render-time data-acquisition pattern); C-44 (undeclared wandb/viewser deps); C-36 (upstream pin caps); Cluster A. #177 (pipeline-core get_latest_run contract); #105/#106 (symptom-management layer above this root cause); C-110 (the interim metric-aware-selection remediation can itself trade this visible failure for a silent wrong number if done without scoping/ambiguity guards). |
| Resolved | 2026-06-27 (B2 / C-108) |
| Resolution | Resolved 2026-06-27 (B2 / C-108). The two-sources-of-truth root is gone: the report reads the typed `MetricFrame` evaluation-of-record (persisted by pipeline-core), not the WandB cloud replica. The `get_latest_run`/`format_evaluation_dict` scrape and the `evaluation_run_resolver` selection seam are deleted, so the entire #105/#106/#177 run-selection failure class is structurally removed — there is no render-time run selection at all. |

---

### C-108: views-reporting acquires & classifies its inputs at render time instead of receiving them through an injected contract (the Cluster A root) — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-108 |
| Tier | 2 |
| Source | expert-code-review + expert-method-review (architecture/methodology synthesis, 2026-06-19) |
| Trigger | When a new report data-need (a metric, a new metadata field, a new input) is satisfied by adding a **render-time fetch** (a `get_latest_run` / viewser / other service call inside a template or accessor) rather than by **receiving** it as an injected, typed input — each such addition deepens the coupling and adds an environment/version-dependent failure path |
| Location | `views_reporting/templates/reports/evaluation.py` (`_add_report_content` → live `get_latest_run`); `views_reporting/metadata/entity_metadata.py` (live viewser `Queryset(...).publish().fetch()`). Contrast the compliant `forecast.py` (receives data) and `loaders/` (ADR-012 injected declared-format adapters). |
| Narrative | This is the **root cause** the rest of Cluster A are symptoms of. views-reporting is supposed to be a *render-from-given-data* layer (ADR-001/002: "depend on pipeline-core **containers**, not services") — and `forecast.py` + the loaders already are. But the evaluation template and the metadata accessors **acquire and classify their inputs at render time** by calling live external services. That single inversion of the dependency direction generates: C-48 (wandb eval scrape → wrong run), C-22 (viewser fetch), C-27 (wandb runtime dependency), C-44 (undeclared wandb/viewser), and C-46 (tests must mock the fetch → false confidence). **Methodology corollary (expert-method-review):** there is no declared *evaluation-of-record* — the source of truth for an evaluation is forecasts + actuals + the proper scoring rule (a re-derivable, transportable artifact), and the report mis-locates it at a mutable cache (wandb/parquet). **Remediation (the roadmap's north star):** dependency-invert onto a stable contract — reporting receives a typed `MetricFrame`/`PredictionFrame` (future **views-frames**) through an injected `EvaluationSource` adapter; scoring stays in **views-evaluation**; the source (store / files / wandb) becomes a swappable leaf adapter. Resolving this one entry dissolves most of Cluster A at once. Gated on views-frames existing + views-evaluation emitting a `MetricFrame` (see `documentation/roadmap_to_1.0.0.md` Phases 2–3); the Phase-1 interim is metric-aware run selection (C-48). **Upstream update (2026-06-25):** the `MetricFrame` type-home is now decided — views-frames **ADR-020** (Option B) hosts it in **views-evaluation** on the views-frames substrate, shipped v1.4.0 (`assert_frame_envelope` + generic `FrameMetadata` provenance `run_id`/`data_version`; eval-specific provenance stays in views-evaluation). The durable fix is no longer blocked on an undecided contract. **Upstream update (2026-06-26):** the emit (**views-evaluation#21**) is now **implemented and merged to views-evaluation `development`** (PR #22) — `EvaluationReport.to_metric_frame()` plus a `MetricFrame`/`MetricFrameMetadata` value object on the views-frames `FrameMetadata` + `assert_frame_envelope` substrate, with tests (`tests/test_metric_frame.py`). It is **not yet on `main`/released** (latest tag v0.4.0 predates it; issue #21 still shows OPEN only because the merge was to a non-default branch), so it is consumable today **only via a git/development dependency** (as we already source pipeline-core 3.0.0). **The gate splits in two (2026-06-26, B2 cross-repo planning):** **(B1, in-repo, unblocked)** invert the eval template onto an injected `EvaluationSource`→`MetricFrame` contract — doable entirely here (dependency graph aligned in Step A: views-evaluation@development + views-frames 1.6.0), but this alone keeps WandB as a *swappable leaf*, it does **not** delete the scrape. **(B2, durable end-to-end, NOT yet possible)** deleting the scrape needs a `MetricFrame` *producer*, and **none exists**: the cross-repo map confirms **zero `MetricFrame`/`to_metric_frame` references in pipeline-core** — nothing calls the emit or persists a frame at render time. So the durable fix additionally requires **two pipeline-core edits** (both unwritten, now filed): (a) **emit + persist** a `MetricFrame` in `managers/evaluation/stage.py` `_publish_results()` alongside `save_evaluations()` (**pipeline-core #218** — the standalone unblock); (b) **switch the caller** in `managers/reporting/stage.py` `generate_evaluation_report()` to pass an `EvaluationSource` instead of `wandb_run`+`get_latest_run` (**pipeline-core #219** — lands after B1). Edit (b) imports views-reporting's `EvaluationSource`, so it lands *after* B1. Net: a **coordinated three-repo epic** (views-evaluation ✓ emit done → pipeline-core produce+persist+caller [#218/#219] → views-reporting consume), not a single-repo fix; the producer (a) is the standalone unblock. **B1 implemented (2026-06-26, #173):** the injected `EvaluationSource` port + `MetricFrameFileSource` (durable) / `WandbEvaluationSource` (interim) adapters + the value query (`mean_metric_value`, C-116-preserving) landed in `views_reporting/sources/`, and `EvaluationReportTemplate` was inverted to render from a `MetricFrame` per model — the eval template **no longer imports wandb** (CIC `cic_evaluation_source.md`). The interim `WandbEvaluationSource` keeps the scrape working behind the port until B2; the durable `MetricFrameFileSource` is unit-tested but its on-disk convention stays provisional pending #218. **Remaining for C-108: B2** — pipeline-core #218 (producer) + #219 (caller switch). Keystone decision: views-frames#109. |
| Cross-refs | **Root of Cluster A.** C-48 (wandb eval scrape — the confirmed instance), C-22 (viewser), C-27 (wandb runtime), C-44 (undeclared deps), C-46 (tests mock the fetch — false confidence), C-34 (provenance — what the injected contract should also carry), C-41 (non-uniform scoring / canonical-token drift — a views-evaluation-owned sibling); ADR-002 (depend on containers not services), ADR-012 (the injected-adapter pattern to extend); **ADR-018 (the written responsibility mandate that declares this inversion — #117)**; views-frames `MetricFrame` (the target contract). |
| Resolved | 2026-06-27 (B2 / C-108) |
| Resolution | Resolved 2026-06-27 (B2). The dependency inversion is complete end-to-end on the evaluation side. B1 (#173) introduced the injected `EvaluationSource` port + `MetricFrameFileSource`/`mean_metric_value`; pipeline-core shipped the producer, persistence, and caller switch (evaluation-of-record epic #224, PRs #249–253) wiring its reporting stage to `generate(source=MetricFrameFileSource(...), target=...)`; B2 deletes the interim WandB scrape (`wandb_evaluation_source.py` + `evaluation_run_resolver.py`), leaving `generate(self, source, target)` as pure render-from-given-data. The eval path imports no wandb (verified `git grep`). C-27/C-48/C-110 (eval-side symptoms) resolve with it. Cluster A's non-eval members — C-22 (viewser), C-114 (private pipeline-core internals) — remain open; Cluster A is no longer rooted on the eval inversion. |

---

### C-110: The C-48 interim fix (metric-aware run selection) can trade a visible "not calculated" for a silent wrong number — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-110 |
| Tier | 2 (latent Tier 1) |
| Source | expert-code-review (Sprint-1 epic review — Kleppmann seat, 2026-06-19) |
| Trigger | When a constituent's authoritative evaluation run is **re-logged under the same partition/level** (a stale re-log — an older eval re-run and re-uploaded), the metric-aware resolver (#116) cannot distinguish it from the original without provenance and may select it, rendering a plausible-but-wrong number silently. (The original pre-implementation hazard — selecting a wrong-*partition* run — is **closed**: the cross-constituent partition/level check raises loudly on it; see "AS IMPLEMENTED" below. Trigger refreshed to the residual by review-rr 2026-06-22.) |
| Location | `views_reporting/templates/reports/evaluation_run_resolver.py` (the interim metric-aware selection seam, #116); consumed by `evaluation.py` `_add_report_content` (cross-constituent partition/level guard) |
| Narrative | C-48's interim remediation makes constituent run-selection metric-aware (pick the latest run that *carries* the canonical metrics rather than the latest-*created* run). Done naively — "latest run with ANY/ALL canonical metric tokens" — this can be **worse** than the current failure: today a metric-less run yields a *visible* "not calculated"; a naive metric-aware selector that finds the *wrong* metric-bearing run among several would render a **silent wrong number** (right place, wrong evaluation) with no signal — exactly C-48's latent Tier-1 path, now *actively reachable* because the fix starts choosing among metric-bearing runs. Two hazards: (1) **ambiguity** — multiple runs carry the canonical set under different partitions/levels; recency alone is not run *identity*. (2) **mixing** — assembling one metric row from metrics drawn from different runs (a single row must come from a single evaluation). **Implementable guard (falsify P3, 2026-06-19 — corrected against the actual site `evaluation.py:187`):** at the selection site only `run_type` is an *a-priori* scope (it picks the wandb project `{model}_{run_type}`); `partition`/`level` are read from each run's `.config` *after* fetch (the existing consistency check at `evaluation.py:223-244`), and there is no `window` selection key. So the guard is: enumerate runs in the `run_type`-scoped project, pick the latest whose summary carries the canonical metric tokens, then **verify that selected run's `partition`/`level` metadata is consistent across constituents** (re-point the existing L223 check at the selected run, not at `get_latest_run`'s newest run); on **ambiguity** (more than one equally-valid metric-bearing run) **degrade-and-announce, never guess**; never source a single metric row from more than one run; emit an observability log when a fallback selection is used; implement the selection behind a `_select_eval_run(...)` **seam** so the durable views-frames `MetricFrame` adapter (C-108) replaces it cleanly. The regression test must use the synthetic `tests/_wandb_doubles.py` double (multiple runs per model), **not** an on-disk `*.parquet` fixture (gitignored → would skip in CI, the C-46 trap). **AS IMPLEMENTED (#116, 2026-06-19):** selection lives in the `evaluation_run_resolver` seam (self-contained, public `wandb.Api` — SDP); it picks the **newest run carrying any canonical metric token for the target**, and the **existing cross-constituent partition/level check (`evaluation.py`) is the loud guard** — it operates on the *selected* runs and `raise`s on a mismatched-partition run, so a wrong-partition number surfaces **loudly, never silently**. The earlier "within-model ambiguity → degrade" idea was **deliberately dropped**: "more than one metric-bearing run" is the *normal* case for re-run models, so degrading on it would re-blank exactly the constituents this fix targets; "newest on a consistent partition" is a defined rule, not a guess. **Residual (why this stays open):** a same-partition *stale re-log* (an older eval re-logged, same partition metadata) is indistinguishable from the authoritative run without provenance, so its number could render silently — a **latent Tier-1** path **closed only by the Phase-3 `MetricFrame` provenance (C-108)**. Tests: `tests/test_falsify_sprint1_readiness.py` (metric-aware selection, partition-check-on-selected-run, loud cross-constituent raise, one-row-one-run, the 22/25 regression). Tier 2 today; **elevate to Tier 1 if a stale-re-log wrong number is ever observed.** **PROVENANCE-GAP CAVEAT (2026-06-26, B2 cross-repo planning):** the "closed by the MetricFrame" assumption needs a caveat — the `MetricFrame` as *currently producible* would **not** close this path. `run_id` and `data_version` are the fields that distinguish a stale re-log from the authoritative run, and **both are out of scope at pipeline-core's evaluation call site** (`run_id` is `None` pre-WandB-run; `data_version` is not captured at all — see the cross-repo map, `managers/evaluation/stage.py`). So a MetricFrame emitted today would carry **null `run_id`/`data_version`**, leaving the stale-relog discriminator absent. Fully closing C-110 therefore needs not just the MetricFrame inversion but **`data_version`/`run_id` plumbed into the evaluation call site** (a pipeline-core provenance task, **pipeline-core #220**, adjacent to C-34's data-version omission). |
| Cross-refs | C-48 (the defect + the interim remediation this sharpens — the latent-Tier-1 note there is what this entry makes actively reachable), C-108 (the durable `MetricFrame` fix that retires this selection), C-41 (canonical-token drift — adjacent "not calculated" cause); Cluster A; GitHub #116 (where the guards must land). |
| Resolved | 2026-06-27 (B2 / C-108) |
| Resolution | Resolved 2026-06-27 (B2 / C-108). The interim metric-aware run-selection mechanism (`evaluation_run_resolver`) is deleted — there is no render-time run selection left to mis-select, so the 'visible not-calculated traded for a silent wrong number' hazard cannot arise. The durable path reads a single persisted `MetricFrame` whose provenance (`run_id`/`data_version`, plumbed at the pipeline-core evaluation call site, #220-class) distinguishes a stale re-log from the authoritative run — closing the residual latent-Tier-1 stale-relog path. The `test_falsify_sprint1_readiness.py` regression suite was removed with the mechanism. |

---

## Register Conventions

Concerns are registered via the `register-risk` skill and curated via the `review-rr` skill.

- **C-xx:** Concern entries (technical risks, code quality issues, architectural debt)
- **D-xx:** Disagreement entries (unresolved debates between expert perspectives)
- **ID numbering:** the native sequence ran C-01–C-48; the register then jumped to **C-107** (migrated from pipeline-core C-133, 2026-06-19) and continued C-108–C-118; a later numbering re-sync jumped to **C-185+** (now through C-213). The **C-49–C-106 and C-119–C-184 ranges are intentionally unused** (no backfill). **C-193–C-204 were never standalone entries:** C-193–C-199 are unused; of the expert-code-review finding IDs, C-200 and C-202 were deduped into C-192 at intake, C-201 went moot with the reconciliation deletion (#72), and C-203/C-204 were absorbed into C-26's resolution narrative — mentions of "C-203"/"C-204" (there and in C-209) refer to those review findings, not to register entries. New entries continue from the current maximum.

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
