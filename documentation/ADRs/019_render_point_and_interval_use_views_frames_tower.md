
# ADR-019: Render-Path Point & Interval Estimators Use the views-frames Tower

**Status:** Accepted
**Date:** 2026-06-24
**Deciders:** Simon, VIEWS platform team
**Consulted:** views-frames maintainers (tower / ADR-019 author side)
**Informed:** views-pipeline-core maintainers (downstream `pred_*_map` / `pred_*_hdi_*` consumers)

---

## Context

views-reporting's forecast **point** and **interval** estimates are produced on the render
path by `views_reporting/statistics/dataset_statistics.py` and consumed by the forecast
map (`templates/reports/forecast.py` → `MappingModule`) and the historical line graph
(`visualizations/historical.py`). Since the views-frames adoption (epic #137, S3) these
functions already **delegate** the math to `views_frames_summarize` via ephemeral
`PredictionFrame` objects, but they delegated to the **frozen** estimators:

- `map_estimate` — a **binned histogram mode**. On the right-skewed, zero-inflated,
  low-sample posteriors typical of conflict forecasts it is directionally biased and has a
  lowest-index histogram tie-break (upstream *views-frames* register **C-32**).
- `hdi` — the empirical shortest interval. Successive credible masses are **not guaranteed
  to nest** (upstream *views-frames* register **C-33**), and a minority duplicated draw can
  hijack a narrow interval (*views-frames* **C-44**, fixed in views-frames 1.2.0).

This is exactly the gap reporting tracks as **register C-35** ("MAP/HDI correctness on
pathological posteriors is unguarded"): plausible-but-wrong point/interval estimates with no
error signal. views-frames has since shipped a principled alternative — the **constrained-
nested HDI tower** (`hdi_tower`), a **mass-aware tip** point estimate (`tower_point` — the
median of the 0.5-mass "shorth" floor), and a `bimodality` flag — all conformance-tested,
nested **by construction**, reproducible, and robust to the C-44 case.

Because the seam already routes through `views_frames_summarize`, adopting the tower is a
**backend swap at two private helpers** (`_frame_map`, `_frame_hdi`) plus the two single-cell
fallbacks. It **deliberately changes forecast output numbers** — that is the point: the new
numbers are the corrected ones.

## Decision

> **The render-path point estimate is the views-frames tower tip (`tower_point`); the
> render-path interval is the constrained-nested HDI (`hdi_tower`).**

1. **Estimators.** `_frame_map` and `compute_single_map` return `tower_point`; `_frame_hdi`
   and `calculate_single_hdi` return the single-mass `hdi_tower` floor. The per-cell NaN
   fallback uses the **same** tower estimator as the vectorized path, so finite and any-NaN
   rows never disagree on which estimator produced them.
2. **Output contract is unchanged.** The columns keep their historical names —
   `{t}_map` / `{t}_hdi_lower` / `{t}_hdi_upper` — on the same `(time, entity)` MultiIndex.
   **No pipeline-core contract change.** Note this makes `{t}_map` a **misnomer**: it now
   carries a tower tip (a shorth), **not** a Maximum-A-Posteriori mode. The honest rename is
   a cross-repo change and is deliberately deferred (tracked as register **C-185**).
3. **Reporting-owned presentation is retained.** `enforce_non_negative` clamping, all-NaN →
   `nan`, empty → `0.0`, and float64 reassembly are unchanged.
4. **Mass pinning is surfaced.** `hdi_tower` reads its interval off a fixed canonical mass
   grid, pinning the requested `alpha` to the nearest floor (default `0.9` is exact). An
   off-grid `alpha` is logged, not silently snapped (ADR-008).

**In scope:** the estimators behind the render-path point/interval (`dataset_statistics.py`).
**Out of scope:** the standalone `PosteriorDistributionAnalyzer` (`statistics.py`) — a
diagnostic tool, not render output — still uses the frozen estimators + a manual
`_enforce_hdi_structure`; migrating it to the tower is a follow-on under C-35. Surfacing the
`bimodality` flag in reports is a separate future feature.

## Rationale

- **Correctness over a frozen but biased estimator.** The tower tip carries no histogram
  tie-break and is robust to minority duplicates; the nested HDI cannot produce the
  "narrower interval not contained in the wider one" artefact. This is the substance of the
  C-35 remediation for the render path.
- **The seam already existed.** Reporting chose (S3) to delegate posterior math to
  views-frames precisely so the leaf could be improved and inherited. This ADR is that
  inheritance.
- **Contract stability beats nominal honesty, for now.** Renaming `{t}_map` would ripple
  into pipeline-core and any persisted-output consumers. Keeping the slot and recording the
  semantic change (here + C-185) is the lower-risk first step; the rename is a separate,
  coordinated decision.

## Considered Alternatives

- **A — Keep the frozen estimators.** Rejected: leaves C-35 unaddressed on the render path;
  the bias/nesting defects ship to partners.
- **B — Rename `{t}_map` to reflect the shorth.** Rejected *now*: breaks the pipeline-core
  output contract; a cross-repo change. Tracked as C-185 for a coordinated future rename.
- **C — Add the tower as opt-in parallel functions, default unchanged.** Rejected: defers
  the actual correctness fix and leaves two estimators live with no forcing function.

## Consequences

### Positive
- Render-path point/interval estimates are principled, nested-by-construction, and
  duplicate-robust; C-35 is advanced for the render path and guarded by law tests.
- No downstream contract change; pipeline-core consumers are unaffected.

### Negative / tracked
- **Forecast numbers change** (intended). Characterization pins were re-baselined; the
  algorithm-independent invariants are now guarded by `tests/test_tower_estimators.py` so a
  future re-baseline does not silently lose coverage.
- **`{t}_map` is a misnomer** until a coordinated rename (C-185).
- **`PosteriorDistributionAnalyzer` is not yet migrated** — the C-35 remediation is partial.

## Implementation Notes

- Swap localized to `dataset_statistics.py` (`_frame_map`, `_frame_hdi`,
  `compute_single_map`, `calculate_single_hdi`); call sites unchanged.
- The **S2 oracle** (`tests/test_summarizer_equivalence.py`) was re-pointed from the frozen
  estimators to the **tower** (`tower_point` / `hdi_tower`) — it now guards the
  wrapper/reassembly faithfulness against the leaf, bit-exact.
- New **law tests** (`tests/test_tower_estimators.py`): HDI ordering + nesting, tip∈HDI,
  `enforce_non_negative`, determinism, the zero cutoff, NaN locality + per-cell/vectorized
  consistency, and the off-grid-alpha warning.
- Requires views-frames **≥ 1.2.0** (the C-44-robust tower); `CONFORMANCE_FLOOR` unchanged
  (`1.0.0`).

## Validation & Monitoring

This decision is working when:
- `calculate_map`/`calculate_hdi` (and the `_frame` variants) read the tower, proven
  bit-exact against `tower_point`/`hdi_tower` by the re-pointed oracle.
- The tower law tests stay green (the invariants hold regardless of value re-baselines).
- A future `{t}_map` rename, if taken, is coordinated cross-repo (C-185), not done locally.

Reconsider if: views-frames deprecates the tower; or a downstream consumer is found to
depend on `{t}_map` being a histogram mode (then C-185 becomes urgent).

## References

- **Register:** C-35 (MAP/HDI correctness — the gap this advances); C-185 (the `{t}_map`
  misnomer / future rename debt); Cluster F (value-correctness & contract assurance).
- **ADRs:** ADR-018 (render from given data — reporting consumes views-frames contracts);
  ADR-008 (explicit failure — off-grid alpha is logged); ADR-006 (CICs — no class CIC for the
  module-level statistics functions).
- **Upstream:** *views-frames* ADR-019 (the tower); *views-frames* register C-32 / C-33 / C-44.
- **Code:** `views_reporting/statistics/dataset_statistics.py`;
  `tests/test_summarizer_equivalence.py`; `tests/test_tower_estimators.py`;
  `tests/test_mapping_characterization.py`; `tests/test_historical_characterization.py`.

---

## Addendum — views-frames 1.3.0 adoption (2026-06-24)

Bumped views-frames 1.2.0 → **1.3.0**, which makes the tower **distribution-agnostic**: the
magnitude-based "quiet row" rule (sub-1 rows forced to 0) is **off by default** (it was a
count-domain assumption that zeroed `[0,1]` rate/probability targets and erased low-intensity
counts — upstream views-frames C-45). **Decision: adopt the new default** — views-reporting does
**not** re-impose `zero_cutoff`. **Forecast-output effect:** sub-1 cells now render their actual
value instead of 0 (intended correction). Blast radius in this repo was a single law test
(`test_tower_estimators.py`: `test_zero_cutoff_quiet_row_collapses` → `test_subunit_rows_not_zeroed`);
no characterization literals changed (fixtures are all `max>1`). `CONFORMANCE_FLOOR` unchanged
(`1.0.0`).
