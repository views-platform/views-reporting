# views-reporting — Roadmap to 1.0.0

> **Status:** draft, 2026-06-19. Synthesis of the architecture/methodology review
> work that ran this period. Current shipped version: **0.2.0** (on PyPI + `main`).
> This document says **where the repo must get to before we call it 1.0.0**, what
> work that means *here*, and what is **blocking us in other repos**.
>
> Read it alongside `reports/technical_risk_register.md` (the C-IDs cited throughout)
> and `documentation/ADRs/`.

---

## 0. The one idea everything hangs on

After two expert panels (engineering + methodology) the repo's identity is now
clear, and it is *already what the governance says* (ADR-001/002), just not what
the code does:

> **views-reporting is a render-from-given-data presentation/synthesis layer.**
> It *receives* already-produced data (predictions, metrics, actuals, metadata)
> and turns it into human-facing artifacts (HTML reports, choropleth maps,
> posterior/HDI plots) for people who do **not** open WandB. It must **not**
> acquire or compute its inputs at render time.

Everything below is, at bottom, **closing the gap between that identity and the
code** — the code currently *fetches and classifies* (WandB `get_latest_run`,
viewser querysets) and *reaches into* pipeline-core internals, instead of
*receiving* typed data through a stable contract.

**The structural fix (north star):** depend on the **`views-frames`** leaf
contract (the new numpy-only data-contract package) — `PredictionFrame`,
`TargetFrame`, `MetricFrame`, `SpatioTemporalIndex`, `SpatialLevel`. Reporting
receives frames and renders them; *sources* (WandB / a metrics store / files)
become injected adapters; *scoring* stays in views-evaluation. This single
inversion dissolves most of the open risk register at once.

---

## 1. Where we are (0.2.0)

**Works:** forecast reports, evaluation reports, country/PRIO-GRID choropleths,
posterior MAP/HDI, hierarchical reconciliation. Governance is mature: 18 ADRs,
CICs, a 49-entry risk register, red/green/beige test taxonomy, CI green, trusted-
publishing release pipeline.

**The headline problem, confirmed in production this period (C-48):** the
evaluation report sources each constituent's metrics by scraping WandB
(`get_latest_run().summary`). `get_latest_run` returns the latest-*created* run,
**not** the latest run *with* the metrics — so for heavily re-run models it reads a
metric-less run. Verified: **22 of 25 constituents rendered "not calculated"** in a
real ensemble report while the real scores sat in an earlier run / the local
`eval_*.parquet`. The report is currently *largely useless/misleading* for
ensembles. This is the single most important thing to fix.

---

## 2. What 1.0.0 *means* (definition of done)

We can rest at 1.0.0 when views-reporting is a clean render-from-given-data
library:

1. **No live external service in the render path** — no WandB / viewser fetch
   while building a report. Inputs arrive as typed data. (Closes Cluster A:
   C-22/C-27/C-28/C-44.)
2. **Evaluation reports are correct** — they show *the* evaluation's metrics, not
   "whatever run the tracker surfaced last." (Closes C-48.)
3. **Depends on a stable contract, not pipeline-core internals** — consumes
   `views-frames` frames/protocols; no private `_ViewsDataset` reads; no cross-repo
   mutation. (Closes the reporting side of C-135/C-184; breaks the #113 cycle.)
4. **Reproducible & provenanced** — every report stamps model run / data version /
   code revision, and rendered values are guaranteed equal to source. (Closes
   C-34/C-29.)
5. **Scale-safe & offline-capable** — guarded PGM rendering; vendored JS/CSS so a
   report opens with no network. (Closes C-26/C-38/C-28.)
6. **Honest tests + enforced CI** — contract tests over the data boundary; branch
   protection; the fixture-skip discipline kept. (Closes C-39/C-46/C-47.)
7. **A constitutional ADR** that *declares* the responsibility above, so the
   render-from-given-data identity is governed, not just intended.

---

## 3. The work — phased (and what each phase is blocked on)

### Phase 1 — Unblocked, do now (no other repo required)
These need nothing from views-frames/evaluation; they harden the repo and de-risk
the inversion.
- **Interim C-48 fix — metric-aware run selection.** Make the eval path select the
  latest run that *actually carries* the canonical metrics (not latest-created).
  Stops reports being mostly "not calculated" *today*; explicitly a stopgap toward
  Phase 3, not the destination.
- **Declare `wandb` + `viewser` as explicit deps** (C-44) until they're removed.
- **Vendor/inline Tailwind + Plotly** into exported HTML (C-28) — offline/partner
  (UN FAO) delivery.
- **PGM scale guard** (C-26/C-38) — cap/downsample or fail loud before OOM.
- **Remove the legacy `transformations/` module** (C-25; ~1,500 LOC, zero
  consumers; drops the `polars` dep).
- **Write the constitutional ADR** — "views-reporting renders given data; depends
  on views-frames containers, never on data-acquisition services; sources are
  injected adapters." This is the missing governance keystone the whole roadmap
  enforces.
- **Provenance footer** (C-34) — stamp model id(s)/run id(s)/data-version/code rev
  in every report (independent of the source redesign).

### Phase 2 — Blocked on `views-frames` *existing* (the contract layer)
Once `views-frames` ships `PredictionFrame` + `SpatioTemporalIndex` + `SpatialLevel`
(+ its conformance test suite):
- **Consume the frames** in loaders/statistics/mapping/visualizations; replace the
  private `_ViewsDataset` reads (`_time_id`/`_entity_id`/`.dataframe`/`.to_tensor`)
  with the published index/level protocols (C-135 reporting side).
- **Break the cycle (#113)** — route the data contract through the `views-frames`
  leaf; drop the `try/except ImportError` pipeline-core↔reporting coupling.
- **De-mutate reconciliation** — return a *new* frame instead of writing
  `pg_dataset.reconciled_dataframe` (C-184). Decide reconciliation's *placement*
  (C-24 / Cluster B — likely relocate to views-postprocessing; torch leaves with
  it).
- Replace `DATASET_CLASSES`/`INDEX_NAMES` bare strings with `SpatialLevel`.

### Phase 3 — Blocked on `views-evaluation` emitting a consumable `MetricFrame` + the SoT decision
The durable C-48 fix:
- **Consume `MetricFrame`** (the typed eval *output*, produced by views-evaluation)
  through an **injected `EvaluationSource` adapter** — extend the ADR-012 loader
  pattern from predictions to metrics. **Retire `get_latest_run` from the
  template.** WandB collapses to (at most) one adapter, or is dropped.
- **Run/eval identity in frame metadata** — the stamped identity that lets the
  report select *the* evaluation (the consumer-side cure for C-48; see
  `views-frames` §13.5).
- Same pattern for **entity metadata** → bundled static lookup / datafactory
  feature, killing the viewser render-time fetch (C-22).

### Phase 4 — 1.0 polish
- **Fidelity guarantee** (C-29) — a test that a rendered value equals its source
  value end-to-end.
- **Uncertainty communication for the conflict audience** (methodology finding) —
  add exceedance/threshold probabilities + calibration alongside MAP/HDI; cite
  Lerch2017 (forecaster's dilemma), Gneiting (sharpness s.t. calibration).
- **Cross-repo contract tests** — run the `views-frames` conformance suite in CI.
- **Branch protection** (C-47) so a red CI blocks merge.
- **Reconciliation placement resolved** (C-24) — torch out of the reporting install.

---

## 4. What is blocking 1.0.0 in OTHER repos (the hard dependencies)

views-reporting **cannot** reach 1.0.0 alone. The blockers, roughly in order:

1. **`views-frames` must be built** *(currently README-only scaffolding).* It is the
   keystone: `PredictionFrame`/`TargetFrame`/`MetricFrame`/`SpatioTemporalIndex`/
   `SpatialLevel` + the conformance suite. **Blocks Phase 2 entirely.** See
   `views-frames/perspectives/from_views-reporting_perspective.md` for exactly what
   this repo needs from it.
2. **`views-evaluation` must emit a consumable `MetricFrame`** — the eval outputs as
   a typed, addressable, **provenance-stamped** artifact (conform its existing
   `EvaluationFrame` to the views-frames index protocol; produce `MetricFrame`).
   **Blocks the durable Phase-3 C-48 fix.** Until then, only the Phase-1 interim
   (metric-aware selection) is available.
3. **A decided evaluation source-of-truth / metrics store** *(cross-repo team
   decision).* Where do `MetricFrame`s live and how is a run identified across
   machines? (The forecast-hub pattern.) This is the open question behind C-48 —
   "read-local vs caller-injects vs a metrics store." **Blocks Phase 3.**
4. **`views-pipeline-core`:**
   - **#177 (`get_latest_run` absent/transient contract) must be RELEASED** — it is
     merged on dev but *unreleased*; the pinned `>=2.3.0` lacks it, so reporting's
     #105 is only correct in the editable conda env, not against a published
     pipeline-core. (Mooted entirely once Phase 3 drops `get_latest_run`.)
   - **Move `PredictionFrame` into `views-frames`** (shim), **decompose
     `_ViewsDataset`** (their C-36), **typed reconciliation boundary** (their
     C-167). Enables Phase 2 cleanly.
5. **Reconciliation relocation** (GitHub #72 → views-postprocessing). Resolves
   C-24 (torch) and where the de-mutation (C-184) lands.
6. **Upstream Python/dependency pins** (C-36 register): the
   `pipeline-core → ingester3 → levenshtein` 3.11-only cap and the
   `viewser → docker → pywin32` Windows break — gate widening the install surface;
   tied to the viewser retirement (C-22).

---

## 5. Dependency picture (what unlocks what)

```
views-frames built ───────────────┐
        │                          ▼
        │                  Phase 2 (consume frames, break #113,
        │                          de-mutate reconciliation)
        ▼
views-evaluation emits MetricFrame ─┐
   + SoT/metrics-store decided      ▼
                            Phase 3 (durable C-48 fix: receive
                                     MetricFrame, retire get_latest_run)
                                     │
Phase 1 (interim C-48, deps, CDN,   │
  scale guard, legacy removal,      ▼
  constitutional ADR) ── independent, do now ──► Phase 4 polish ──► 1.0.0
```

- **Phase 1 is fully unblocked** — start there; it also makes reports usable again
  (interim C-48) while the contract layer is built.
- **Phases 2–3 are gated on views-frames and views-evaluation.** Our best lever on
  the timeline is helping those two land (we've already written views-frames its
  consumer-perspective doc).
- **1.0.0 = Phase 4 complete**, i.e. no live service in the render path, eval
  reports correct + provenanced, depends on views-frames, scale-safe, offline,
  CI-enforced.

---

## 6. Honest risk-register cross-reference

| Theme | Register IDs | Phase |
|---|---|---|
| Eval-metric source (the headline) | **C-48**, C-41, C-27 | 1 (interim) → 3 (durable) |
| Decouple from pipeline-core internals / cycle | C-135, #113, C-36 (pc) | 2 |
| Cross-repo mutation in reconciliation | C-184 (pc) | 2 |
| External runtime deps (Cluster A) | C-22, C-27, C-28, C-44 | 1 (declare/vendor) → 3 (remove) |
| Reconciliation placement / torch | C-24 | 2–4 (relocation) |
| Provenance & fidelity | C-34, C-29 | 1 (footer) / 4 (fidelity test) |
| Scale discipline | C-26, C-38 | 1 |
| Tests / CI enforcement | C-39, C-46✓, C-47 | 1/4 |
| Legacy transform machinery | C-25 | 1 |
| Uncertainty communication (methodology) | (C-M3) | 4 |
| Upstream pins / install surface | C-36 (reporting) | external |

(`pc` = tracked in views-pipeline-core's register; ✓ = already resolved.)

---

## 7. The one-paragraph version (for when you're tired)

0.2.0 works but the evaluation report is reading the wrong WandB run and showing
mostly "not calculated" — fix that first (metric-aware selection, now). The real
destination is to stop fetching/classifying in the render path and instead
**receive typed data from `views-frames`** (predictions, a `MetricFrame` of
evaluation outputs, actuals, the spatiotemporal index) and just render it — which
is what the governance always said. That inversion clears most of the risk
register at once, but it is **gated on `views-frames` being built and
`views-evaluation` emitting a `MetricFrame`** (plus a team decision on where the
evaluation source-of-truth lives). Until those land, do the unblocked Phase-1 work
here; help those two repos land; then finish provenance/fidelity/scale/CI polish
and call it 1.0.0.
