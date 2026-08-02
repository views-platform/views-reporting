# ADR-020: Posterior Samples Are Numpy-Bound; the Pandas Presentation Seam Carries Summaries Only (Enforced)

**Status:** Accepted
**Date:** 2026-07-13
**Deciders:** Simon (checkpoint decision on epic #215, 2026-07-06), Claude
**Consulted:** the pre-registered synthetic probe (epic #215 S1 / #216 — 7/7 predictions confirmed)
**Informed:** views-frames, views-pipeline-core maintainers

---

## Context

Simon challenged the standing — but never decided — architecture default: *"pandas inside the
render layer stays on purpose"*, doubting it could work at 1000s of posterior samples. The
challenge exposed two real gaps:

1. **The sample boundary was an expectation, not a contract.** The render architecture assumed
   posterior samples (numpy, `PredictionFrame`, N rows × S samples) are collapsed to summaries
   by the views-frames tower (ADR-019) *before* anything crosses into pandas — the seam's CIC
   even documented "S == 1 expected" — but nothing enforced it. Both seams
   (`mapping/_frame_adapter.py`, `visualizations/historical.py`) read `values[:, 0]`: handed an
   uncollapsed frame they silently rendered **posterior draw #0 as the point estimate**. One
   variant was **live**: the line graph's all-HDI-levels-failed fallback drew draw #0 labeled
   "(HDI unavailable)" (probe P6, demonstrated empirically).
2. **The pandas question itself was undecided.** No ADR said whether summary-shaped pandas in
   the Rendering layer (ADR-002 Layer 4) is sanctioned, or under what conditions.

The pre-registered probe (`documentation/investigations/sample_scaling_boundary.md`) answered
with measurements — 7/7 predictions confirmed:

- The seam DataFrame is **byte-identical across sample counts** for fixed rows (globe scale:
  471,447,540 B at S=100 and S=200 alike; CM: 1,015,272 B at S=100/1000/2000). O(rows), exactly.
- Report-artifact HTML is S-independent (ratio 1.0001 at S=100 vs S=1000; size is driven by
  entities × HDI-levels × time — the C-38 mechanism).
- The genuine globe×samples constraint is **tower collapse wall-time** (linear, ~2–4×10⁶
  sample-elements/s ⇒ ~15–26 min at globe × S=1000, plus a 12.4 GB frame) — pure numpy,
  unaffected by pandas' presence or absence.
- The silent draw-#0 crossing occurred at every grid point with zero warnings (P5), and the
  live fallback variant reproduced (P6).

## Decision

Per Simon's checkpoint decision (epic #215, 2026-07-06):

> **(i) Posterior samples are numpy-bound. The pandas presentation seam receives S == 1
> summaries only — ENFORCED.** `frames_to_mapping_df` and `HistoricalLineGraph._pred_df` raise
> `ValueError` on `sample_count > 1`, naming `calculate_map_frame` as the remedy (fail-loud,
> ADR-008). There is **no config knob**: S == 1 is a contract invariant of the seam, not a
> tunable budget — a knob would legitimize S > 1.
>
> **(ii) Summary-shaped pandas in the Rendering layer is SANCTIONED, scoped.** Pandas may carry
> presentation-shaped data — one value per (entity, time), plus labels/joins — because it is
> provably O(rows) and sample-independent, and the plotting stack (plotly, matplotlib,
> geopandas) natively consumes dataframes. The sanction is conditional on (i): the guard is what
> keeps "summary-shaped" true.

Supporting rules:

1. **The degraded fallback renders summaries or nothing.** When HDI fails at every level, the
   line graph renders the entity's **MAP line** ("(HDI unavailable, MAP)"), or — if no MAP frame
   exists — **no fabricated line** (visible absence + loud log, per the C-11 visible-degradation
   convention). An arbitrary posterior draw can never again masquerade as the forecast.
2. **Sanctioned exceptions, named and scoped:**
   - `PlotDistribution` pools **all S samples in numpy** (→ seaborn/matplotlib directly) — the
     one intentional all-samples-in-memory consumer; it never touches pandas.
   - The **DataFrame loader** transiently holds every sample **inside pandas** at ingestion
     (array-in-cell object dtype, `loaders/dataframe_loader.py`) before stacking to the numpy
     frame. This is O(rows) *pandas objects* (not an O(rows×S) table) and ends at the frame
     boundary. The npy `PredictionFrameLoader` path never touches pandas. The invariant is
     therefore scoped to the **render seam**, not "pandas anywhere".
   - `HistoricalLineGraph._hist_df` reads a `TargetFrame` — S == 1 by nature (observed values);
     out of the guard's scope.
3. **The guard lives inside the seam**, so external construction routes — including
   views-pipeline-core's `modules/mapping/__init__.py` re-export shim — are covered without any
   cross-repo change.

**In scope:** the render-path sample boundary and the sanction for summary-shaped pandas in
Layer 4. **Out of scope:** removing pandas from the render layer (evidence showed no benefit —
the sanction supersedes that idea unless revisited); ingestion redesign; the tower's collapse
wall-time at globe×samples scale (a views-frames compute-budget question — see Open Questions).

## Rationale

- **Evidence over intuition.** The "1000s of samples" worry was legitimate and testable; the
  pre-registered probe falsified the scaling fear (the seam cannot see samples) while
  *confirming* a worse, subtler risk (silent draw-#0). The decision follows the evidence: guard
  the real hole, keep the harmless convenience.
- **Composition with the existing constitution.** ADR-002 already makes views-frames objects
  "numpy-only contracts" (Foundation layer); ADR-019 already computes MAP/HDI in the tower
  (summaries out, samples in); ADR-018's globe addendum already makes Render size-agnostic.
  This ADR adds the missing piece: the **enforced boundary** between those layers' data shapes.
- **A knob would be a lie.** `max_samples_at_seam` or similar would imply some S > 1 is
  acceptable at the seam. It never is — the seam renders point estimates; anything else is a
  correctness error, which is what exceptions (not budgets) are for (ADR-008).
- **Silent-wrong beats OOM in the severity calculus.** The pre-guard failure mode was not a
  crash but a plausible-looking wrong map — the worst class in the register (C-207, Tier 1).

## Considered Alternatives

### Alternative A: Auto-collapse at the seam
- **Pros:** convenient for direct callers; no new exceptions.
- **Cons:** hides a potentially ~26-minute computation (globe × S=1000) inside "draw a map";
  weakens ADR-019's explicit-collapse discipline; the caller loses control of the estimator.
- **Reason for rejection:** rejected at the checkpoint — computation this heavy must be
  explicit at the Compose boundary, not implicit in a render call.

### Alternative B: Docs-only (document the expectation, change no code)
- **Pros:** zero code risk.
- **Cons:** leaves C-207 open with a live Tier-1 variant; the CIC already documented the
  expectation and that demonstrably did not prevent the bug.
- **Reason for rejection:** rejected at the checkpoint — documentation without enforcement is
  the state that produced the bug.

### Alternative C: Remove pandas from the Rendering layer entirely
- **Pros:** one container fewer; stylistic purity.
- **Cons:** the probe showed pandas at the seam is O(rows), S-independent, and byte-identical
  across sample counts — removal buys no scaling headroom; the real cost (tower wall-time) is
  numpy-side; the plotting stack natively wants dataframes, so removal adds adapter code for
  negative benefit.
- **Reason for rejection:** overturned by evidence at the checkpoint (this was the original
  challenge; the measurements answered it).

## Consequences

### Positive
- The lying-chart class is extinct: guarded at both seams, red/green tested, canary-pinned in
  CI (S=1000, real Africa cell ids, unmocked metadata — `tests/test_sample_scale.py`).
- The pandas question has a recorded, evidence-backed answer instead of a default.
- The probe's scaling laws are published and re-derivable
  (`documentation/investigations/sample_scaling_boundary.md`).

### Negative
- Direct callers that previously (mis)used the seams with raw sample frames now get exceptions
  — intended, but a behaviour change for any out-of-tree caller (none known; pipeline-core's
  shim route is covered).
- The degraded no-MAP fallback now renders absence rather than *something* — a chart can have
  a visibly missing entity. This is deliberate (honest absence beats a fabricated line).

These trade-offs are accepted intentionally.

## Implementation Notes

Delivered by epic #215 (S1 evidence #216/PR #221 · S2 guards #217/PR #222 · S3 canary
#218/PR #223 · S4 this ADR #219). Register: **C-207** (Tier 1) opened by the probe, resolved by
the guards; see its entry for the full remediation trail. CICs updated in step with this ADR:
`cic_frame_mapping_adapter.md` (S==1 expectation → enforced guarantee),
`cic_historical_line_graph.md` (the fallback contract).

## Validation & Monitoring

This decision is working when:
- `tests/test_sample_boundary.py` (seam contracts, fallback honesty) and
  `tests/test_sample_scale.py` (the S=1000 canary: bounded, faithful, refused-when-raw) stay
  green in CI.
- No new `values[:, 0]`-style sample slicing appears outside the guarded seams (review-diff
  checkpoint: any new frame→pandas crossing must assert or inherit S == 1).
- Reports containing degraded entities show the "(HDI unavailable, MAP)" label or a logged
  absence — never an unlabeled arbitrary line.

Reconsider if: a product genuinely needs per-sample data in a pandas artifact (none exists —
`PlotDistribution` covers the visualization need in numpy), or the tower's collapse wall-time
at globe×samples scale forces a precomputed-summaries pipeline stage (which would *strengthen*
this boundary, not weaken it).

## Open Questions

- **Globe × samples collapse budget** (the probe's discovered constraint): ~15–26 min at
  globe × S=1000 is a views-frames tower question (chunking/parallelism) — tracked as a
  cross-repo note, not gating this ADR.

## References

- **Register:** C-207 (the enforced hole — Resolved); C-11 (visible degradation); C-26/C-38
  (the orthogonal cells×time budget axis); C-35 (tower correctness).
- **ADRs:** ADR-002 (numpy-only Foundation contracts), ADR-008 (fail-loud), ADR-016 (config
  injected — and why the guard is NOT config), ADR-018 + globe addendum (render from given
  data, size decisions at Compose), ADR-019 (tower computes summaries).
- **Evidence:** `documentation/investigations/sample_scaling_boundary.md` (pre-registered,
  7/7 confirmed); epic #215 and its checkpoint comment (the Decision source).
- **Guards/tests:** `views_reporting/mapping/_frame_adapter.py`,
  `views_reporting/visualizations/historical.py`, `tests/test_sample_boundary.py`,
  `tests/test_sample_scale.py`.
