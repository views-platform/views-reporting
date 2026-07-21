# ADR-021: Global PGM forecast maps — the image tier is the primary product; the layer and horizon-step standard

**Status:** Accepted
**Date:** 2026-07-21
**Deciders:** Simon (decisions recorded on #230/#231, 2026-07-20/21); implementation epic #230 (S1–S6)

---

## Context

The first real global-PGM ensemble report (rusty_bucket: 8 constituent models,
3 targets, 64,818 land cells × 36 months, S=128 draws) flipped a design
assumption. The render ladder (ADR-016/018 lineage, epic #188) treated the PNG
image tier as an *emergency exit* for the rare globe-scale render — minimal by
design: one silently-chosen month (`times[-1]`), MAP only, no month/date
labelling. Global PGM is now the **standard** workload, so the minimal tier had
become the primary forecast deliverable.

Three forcing facts (all measured on the real run):

1. **Byte physics.** A full-horizon interactive animation of the global grid is
   ~7.2M uniform-lattice cell-frames ≈ 245 MB of offline HTML — over any
   defensible budget (C-209). One global PNG is ~300 KB; one single-month
   global heatmap (~202k cell-frames) fits the existing 2M budget.
2. **The mode hides the risk surface.** With 99.5%+ of draws exactly zero, the
   MAP/mode is 0 almost everywhere: at step +1 (sb), MAP lights 80 cells while
   the posterior carries risk mass in 1,399. A MAP-only map structurally
   under-communicates a zero-inflated forecast — the concern that opened the
   epic ("how can this work with 1000s of samples").
3. **Identity metadata was regional.** The viewser pgm loa still serves only
   Africa+ME (13,110 cells), while the models consume the GAUL-coded
   views-datafactory. Global maps need global cell→country identity that
   viewser cannot currently supply.

## Decision

1. **For PGM at every scale, the report renders HORIZON STEPS, not a
   whole-horizon animation**: steps **+1, +6, +12, +24, +36** months ahead
   (clamped to the horizon), each as a scale-flat PNG. Step **+1 additionally
   renders as the hover-capable raster heatmap** (single month — inside the
   C-209 budget by construction). Month choice is EXPLICIT at the Compose
   boundary; the image renderer refuses multi-month input (ADR-008). CM keeps
   the whole-horizon choropleth.
2. **Sample forecasts render FOUR summary layers per PGM target**, each an
   S==1 frame through the ADR-020 seam: **MAP point estimate** (headline),
   **P(any violence)** (share of draws > 0), and the **upper 90% and 95% HDI
   bounds**. CM renders MAP only (its line graph already carries HDI).
3. **Colour is layer-typed**: count layers (MAP, HDI bounds) use the
   nonzero-anchored log scale with original-unit labels (C-191); probability
   layers use a **linear 0–1 scale** with quarter ticks. The mode is validated
   at the `plot_map` boundary; probability-on-choropleth fails loud.
4. **No-data is grey (`#d9d9d9`), never blank**: on both PGM tiers, with a
   caption distinguishing "no data / outside coverage" from "zero forecast"
   (C-190 — omission must never read as "no risk").
5. **Cell→country identity comes from the bundled metadata built via an
   explicitly INTERIM crosswalk**: GAUL `iso3_code` → VIEWS `isoab` →
   `country_id`, sourced from the views-datafactory `gaul_admin` harvest
   (#231, register C-211). Declared, both directions: unmatched codes are
   enumerated in the stamp; known absorptions (Kosovo→SRB) and legitimately
   zero-cell countries are declared and validated against the built table at
   every regeneration.
6. **The samples-to-report path must scale to S=1000**: targets stream one at
   a time (load → collapse to all layers → release) and the collapse is
   float32-preserving end-to-end (C-212).

In scope: the PGM forecast-map product shape, its colour semantics, its
identity source, and its memory discipline. Out of scope: CM product changes;
the platform's eventual country-coding standard (see Path Forward); model-side
target semantics.

## Rationale

- **Faithfulness scales; interactivity does not.** The uniform-lattice PNG is
  faithful by construction (one cell → one pixel, no aggregation C-189, no
  omission C-190) at any grid size; interactive payloads scale with
  cells × frames. So interactivity is spent precisely where it pays: the
  operationally-relevant first step.
- **Communicate the distribution, not just its mode.** P(any) and HDI-upper
  are the honest summaries of a zero-inflated posterior; MAP remains the
  headline because it answers "what is the single most probable outcome".
- **Colour honesty is per-quantity.** A probability on a log-count scale (or
  a count on an unlabelled log scale) misleads silently — the strongest class
  of map error (C-191).
- **Interim, but contained.** The crosswalk decision (Simon, #231) is
  explicitly a handover: runtime accessors depend only on the bundle schema
  (`priogrid_id → country_id`), so swapping/adding coding systems is a
  build-script-only change (DIP); new codings would ADD columns, not rewrite
  accessors (OCP).

## Considered Alternatives

### A: Full-horizon interactive animation (status quo, scaled up)
- **Pros:** one figure per target; time slider.
- **Cons:** 245 MB offline HTML at global scale — physically over budget.
- **Rejected:** byte physics; revisit only if the offline-HTML constraint
  itself is dropped (e.g. a served, tiled map product).

### B: All 36 months as PNGs with an HTML selector
- **Pros:** complete horizon coverage.
- **Cons:** ~30+ MB per layer set and a 100+-image page; the intermediate
  months add little over the sampled steps for a monthly-cadence reader.
- **Rejected:** volume without proportionate insight; revisit if partners
  request specific non-sampled months.

### C: Mean instead of (or beside) P(any)/HDI
- **Pros:** familiar; expected-value semantics.
- **Cons:** overlaps what P(any)+HDI communicate while hiding the
  zero-inflation structure; invites over-reading point certainty.
- **Rejected for the default set** (decision on #230); may be added as an
  optional layer if requested.

### D: Wait for viewser's pgm loa to go global (identity)
- **Cons:** timeline unknown; runs against the platform's datafactory
  migration (the models already left viewser).
- **Rejected:** blocked the entire epic on an external timeline.

## Consequences

### Positive
- A 3-target global report is ~46 MB, renders offline, and shows the risk
  surface (1,399 cells vs 80 at step +1), bounded uncertainty, and worldwide
  country identity — measured, not aspirational.
- S=1000 is feasible: ~12 GB peak on a 31 GB machine (streamed targets,
  zero-copy collapse), guarded by a CI memory-bound test.
- Every silent behavior found on the way is now a loud one: multi-month
  renders, unknown colour modes, partial harvests, undeclared absorptions.

### Negative / accepted debts
- No per-cell hover beyond step +1 (the PNG tradeoff) — revisit if a served
  map product materializes.
- 4 layers × 5 steps × N targets is a long page; navigation relies on
  headings (no in-page selector yet).
- The GAUL crosswalk is a declared interim (below).

## Path Forward (the C-211 handover)

The country-coding standard for the platform is deliberately undecided: GAUL
is FAO's coding; other partner codings may follow (decision record on #231).
The deep-dive/decision is delegated cross-repo:
**views-datafactory#341** and **views-postprocessing#123**, which are asked to
announce any general solution back to this repo via an issue. When it lands,
`scripts/build_entity_metadata.py` is the ONLY thing that changes here — the
bundle schema is the contract the renderers see. Until then, register C-211
keeps the transition visible; the stamp's `priogrid_source` block is the
per-artifact declaration of exactly what the interim maps can and cannot
label.

## References

Epic #230 (S1 #231, S2 #232, S3 #233, S4 #234, S5 #235, S6 #236); PRs
#238, #252, #253, #254, #255. Register: C-190, C-191, C-205, C-208, C-209,
C-211, C-212. Composes with ADR-008 (fail loud), ADR-016 (config at the
Compose boundary), ADR-018 (+globe addendum), ADR-019 (tower summaries),
ADR-020 (samples numpy-bound; every layer is an S==1 frame through the seam).
