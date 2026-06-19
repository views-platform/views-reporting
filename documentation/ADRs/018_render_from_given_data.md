
# ADR-018: views-reporting Renders From Given Data — Depend on Contracts, Not Services

**Status:** Accepted  
**Date:** 2026-06-19  
**Deciders:** Simon, VIEWS platform team  
**Consulted:** expert-code-review panel (Martin, GoF, Feathers, Nygard, Kleppmann, Ousterhout, Hickey, Beck); expert-method-review panel (forecast-evaluation, calibration, conflict-domain seats)  
**Informed:** views-frames, views-evaluation, views-pipeline-core maintainers  

---

## Context

views-reporting was extracted to be the **outer-layer presentation and analysis package** for VIEWS (ADR-001). Three existing ADRs already point at an identity without ever naming it:

- **ADR-001 (Ontology)** lists *Report Templates* ("orchestrate which sections appear"), *Ingestion / Loaders* ("declared-format adapters that *receive* prediction storage"), and *Metadata* ("accessors that make **live viewser queries** … carries the viewser-retirement risk").
- **ADR-002 (Topology)** already forbids *"Computation, Rendering, or Composition reading prediction storage directly instead of through the Ingestion layer."*
- **ADR-012** established the injected, declared-format **loader** as the sanctioned way prediction data enters the package.

So the principle "**receive, don't fetch**" already governs *predictions*. But two input paths never came under it:

- the **evaluation template** scrapes evaluation metrics from **WandB at render time** (`get_latest_run().summary`), and
- the **metadata accessors** fetch geographic reference data from **viewser at render time** (`Queryset(...).publish().fetch()`).

These are not edge cases — they are the **root cause** of a whole cluster of risks (register **C-108**, the root of Cluster A: C-22 viewser, C-27 wandb runtime, C-44 undeclared deps, C-46 tests-mock-the-fetch, C-48 wrong-run scrape). The failure is not hypothetical: render-time acquisition is exactly what produced the production incident where **22 of 25 ensemble constituents rendered "not calculated"** (C-48) because the report selected the wrong WandB run.

Why now:

1. **The violation has already cost us** a broken production deliverable (C-48), and the only fix available today (#116) is an explicitly-interim seam — there is no governing ADR that says what the *durable* shape should be.
2. **views-frames is being designed now.** views-reporting is a named consumer of its `PredictionFrame`/`MetricFrame` contracts. Without a declared responsibility, the consumer side of that contract has no mandate and no acceptance criteria.
3. ADR-002 governs *structural direction* but never states the **responsibility** that makes the direction meaningful: *what is this package actually for, and what is it forbidden to do to get its inputs?*

An explicit responsibility ADR is required so that every future report data-need, and the views-frames adoption, is decided against a written mandate rather than re-litigated.

---

## Decision

> **views-reporting renders human-facing artifacts from data it is *given*.**
> It does not acquire, fetch, or compute its own inputs in the render path.

This package's job is **synthesis and presentation** — choropleth maps, posterior/HDI visualizations, the ADR-017 canonical-metric tables, self-contained HTML for stakeholders who cannot or should not use the live tooling. Its inputs arrive through **stable, typed contracts**; obtaining those inputs is **someone else's responsibility**.

Five rules follow, and are binding:

1. **Responsibility — render from given data.** views-reporting *synthesizes and renders* artifacts from provided data. It does **not** acquire its inputs (no live service calls in the render path) and does **not** compute model-evaluation results.

2. **Dependency rule — contracts, not services.** Render-path code depends on **data containers / contracts** — pipeline-core containers today, the **views-frames** `PredictionFrame` / `MetricFrame` going forward — and **never** on a data-*acquisition service* (WandB, viewser) reached at render time. A contract is a stable, typed, transportable value; a service is a network endpoint with availability, version, and consistency semantics that do not belong in a renderer.

3. **Adapters — sources are injected.** Where data must be read from somewhere (files, a store, and — transitionally — a remote service), it is read by an **injected, declared adapter**, following and extending the ADR-012 loader pattern from *predictions* to **metrics and metadata**. The render code depends on the adapter's *interface*, not its source. The eventual interface is an `EvaluationSource` (metrics) joining the existing prediction loaders.

4. **Scoring stays in views-evaluation.** views-reporting **renders** a `MetricFrame`; it does **not** score. Proper scoring rules (CRPS, Ignorance, MSLE/MSE, calibration — ADR-017) are computed in **views-evaluation**. Reporting is the *consumer-of-record* of evaluation output, never its producer.

5. **The source of truth for an evaluation is forecasts + actuals + scoring rule** — a re-derivable, transportable artifact — **not** a WandB run or a parquet cache. A stored metric value is a *cache* of that derivation; if a cache and a re-derivation disagree, the derivation wins. The report must locate truth at the artifact, not at whichever cache it happened to read.

**In scope:** the responsibility and dependency mandate for all render-path inputs (predictions, evaluation metrics, entity metadata); the contract/adapter direction; the location of scoring and of evaluation truth.

**Out of scope:** *how* views-frames is built (owned by views-frames); *how* scoring is implemented (owned by views-evaluation); the cross-repo metrics-store / addressable-eval-store decision (a pipeline concern). This ADR sets the destination and the rule, not the upstream implementations.

### Relationship to ADR-002 (no contradiction)

This ADR does **not** override the topology; it **generalizes** it. ADR-002 already forbids Composition/Rendering/Computation from reading *prediction storage* directly instead of through the Ingestion layer. ADR-018 extends that same prohibition to **all** render inputs — evaluation metrics and entity metadata — and admits **views-frames contracts as Foundation-layer (Layer 1) values** alongside the pipeline-core containers, and **metric/metadata adapters as Ingestion-layer (Layer 2) members** alongside the prediction loaders. Dependency direction (ADR-002), semantic authority (ADR-003), and boundary-contract validation (ADR-009) are unchanged.

---

## Rationale

- **Dependency Inversion (DIP) and Stable-Dependencies (SDP).** A renderer that depends on a live service depends on the *least stable* thing in the system. Depending on a typed contract inverts that: the renderer depends on an abstraction, and the volatile source becomes a swappable leaf. This is the same instinct ADR-012 already encoded for predictions.
- **The incident is the proof.** C-48 was not a fluke: acquiring-and-classifying inputs at render time put run-selection logic, network availability, version skew, and cache freshness *inside the renderer*. Every one of those is a defect surface that disappears once the renderer only receives data. "Render from given data" is the structural fix that dissolves most of Cluster A at once (C-108).
- **Methodological correctness.** An evaluation report is a *scientific artifact* delivered to partners (e.g. UN FAO). Its claims must be reproducible and traceable to the exact forecasts, actuals, and scoring rule that produced them. Locating the source of truth at a mutable cache (WandB) makes the artifact non-reproducible and fragile to run-selection bugs. Locating it at the re-derivable artifact makes the report auditable.
- **Screaming architecture.** Declaring the responsibility makes the package say what it is for. A new contributor should not have to read the eval template to discover that "this package sometimes phones WandB" — the rule says it must not.
- **It enables views-frames.** A consumer with a written responsibility gives views-frames concrete acceptance criteria: *what `MetricFrame` must carry for reporting to stop fetching.*

These principles are valued over the short-term convenience of "just fetch it here."

---

## Considered Alternatives

### Alternative A: Status quo — acquire inputs at render time
- **Pros:** No new contract package needed; the data is "right there."
- **Cons:** Is the documented root cause of Cluster A (C-108) and the C-48 production failure; couples a renderer to network, version, and cache semantics; untestable without mocking the fetch (C-46).
- **Reason for rejection:** It is precisely the pattern this ADR exists to retire.

### Alternative B: Declare the **local `eval_*.parquet`** the source of truth
- **Pros:** The pipeline writes it first, before mirroring to WandB; obvious and local.
- **Cons:** In the distributed VIEWS setup, constituent models are trained/evaluated on different machines, so a constituent's local eval file is not co-located with the machine building the ensemble report; a co-located cache is not a single addressable truth.
- **Reason for rejection (as the *truth* framing):** The parquet is a *cache*, like WandB — a valid **adapter source**, but not the source of truth. Truth is the re-derivable (forecasts + actuals + rule). *Conditions to revisit:* if a single addressable eval store with stable run identity is adopted upstream, it becomes the preferred adapter source.

### Alternative C: Keep WandB, fix only the run selection (the #116 interim)
- **Pros:** Makes the report usable now with minimal change.
- **Cons:** Leaves the render-time-acquisition coupling in place; the fix is throwaway.
- **Reason for rejection (as the destination):** Accepted **as an interim** (it ships behind the `evaluation_run_resolver` seam, explicitly deleted in Phase 3) — but it is a stopgap under this ADR, not a fulfillment of it.

---

## Consequences

### Positive
- A single written mandate dissolves the rationale for the whole of Cluster A (C-108 → C-22/C-27/C-44/C-46/C-48).
- Reports become reproducible, air-gap-deliverable, and testable without mocking a fetch.
- views-frames adoption and the `MetricFrame` contract gain concrete acceptance criteria.
- New report data-needs have a clear, reviewable rule: *receive it, don't fetch it.*

### Negative
- **The destination is gated on other repos.** Full compliance requires views-frames to exist and views-evaluation to emit a `MetricFrame`; until then the package **knowingly violates its own ADR** in the eval template and metadata accessors. This debt is explicit and tracked (C-108), not hidden.
- A transitional period carries **adapter shims** (e.g. the #116 `evaluation_run_resolver`) that wrap services behind the eventual interface — extra code that is later deleted.
- Some inputs (entity metadata) may move from a live query to a **bundled table** (C-22), trading a service dependency for a packaged asset.

These trade-offs are accepted intentionally.

---

## Implementation Notes

Enforcement is **phased** (see `documentation/roadmap_to_1.0.0.md`):

- **Phase 1 (now) — tolerate behind seams, declare honestly.** The eval template's WandB acquisition is isolated behind the interim `evaluation_run_resolver` seam (#116) and the metadata accessors remain live viewser queries (C-22). Both are *known, tracked violations* of this ADR, not compliant code. New code must not add render-time fetches.
- **Phase 2–3 — invert.** Consume views-frames `PredictionFrame`/`MetricFrame`; introduce an injected `EvaluationSource` adapter (extending the ADR-012 loaders from predictions to metrics); replace the WandB scrape and, per C-22, replace viewser queries with a bundled/factory-sourced table. Retire `wandb`/`viewser` from the render path and from `[project].dependencies` (C-44 / GitHub #120).

**Guardrail against regression:** the register C-108 trigger — *"when a new report data-need is satisfied by a render-time fetch rather than an injected input"* — is the review checkpoint. `/review-diff` and `/register-risk` treat any new service call in Computation/Rendering/Composition as an ADR-018 violation.

This ADR requires **no code change on its own**; it is the mandate the Phase-2–3 work executes against.

---

## Validation & Monitoring

This decision is working when:

- No new render-time service call is introduced in Layers 3–5 (caught at `/review-diff`; tracked by the C-108 trigger).
- The evaluation report is reproducible from `(forecasts, actuals, scoring rule)` and renders from an injected `MetricFrame` rather than `get_latest_run`.
- `wandb` and `viewser` leave the render path and `[project].dependencies` (C-44 resolved).
- The interim seams (`evaluation_run_resolver`, live metadata queries) are deleted, not extended.

Reconsider this ADR if: views-frames does not materialize and a different stable contract source is adopted; or the distributed-evaluation assumption changes such that a co-located store *is* the addressable truth (revisit Alternative B).

---

## Open Questions

- **views-frames timeline and `MetricFrame` shape** — what exactly the contract must carry (values + provenance: model id, run id, data version, scoring code) for reporting to stop fetching. (See `views-frames/perspectives/from_views-reporting_perspective.md`.)
- **The metrics-store / addressable-eval-store decision** — a cross-repo (pipeline) choice about where evaluation output is stored with stable run identity; this ADR is source-agnostic and does not pre-decide it.
- **Entity metadata** — bundled static table (C-22) versus a metadata adapter; both satisfy this ADR, the choice is a separate decision.

---

## References

- **Register:** C-108 (root — render-time acquisition vs injected contract; Cluster A); C-48 (the confirmed instance / #116 interim); C-22 (viewser), C-27 (WandB runtime), C-44 (undeclared deps), C-46 (tests mock the fetch).
- **ADRs:** ADR-001 (Ontology — Report Templates / Ingestion / Metadata categories); ADR-002 (Topology — the Ingestion-layer rule this generalizes); ADR-012 (Prediction Data Ingestion — the injected-adapter pattern to extend); ADR-003 (declarations over inference); ADR-009 (boundary contracts).
- **Design docs:** `documentation/roadmap_to_1.0.0.md` (the phased road to the inversion); `views-frames/perspectives/from_views-reporting_perspective.md` (the consumer perspective).
- **GitHub:** #117 (this ADR), #116 (the interim C-48 seam), #120 (declare wandb/viewser deps), epic #121.
- **Reviews:** the engineering and methodology expert panels (2026-06-19) that converged on this responsibility.
