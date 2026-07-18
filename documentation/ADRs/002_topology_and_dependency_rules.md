# ADR-002: Topology and Dependency Rules

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

views-reporting was extracted from views-pipeline-core specifically to enforce a clean architectural boundary between pipeline infrastructure and presentation/analysis code. Without explicit topology rules, this separation will erode as:

- visualization modules begin importing report template internals,
- statistical analysis code pulls in rendering libraries,
- report templates reach back into pipeline-core lifecycle code,
- and binary assets get loaded eagerly at import time, coupling the entire module graph to the filesystem.

A clear rule is required to define **who may depend on whom**, both within views-reporting and across the boundary to pipeline-core.

---

## Decision

This repository enforces a strict, directional dependency structure.

> Dependencies must follow declared architectural direction.
> No component may depend on a layer above it.

Dependency direction is part of the system's structural integrity.

Violations are architectural defects.

---

## Layering Principle

views-reporting defines five architectural layers, ordered from lowest to highest:

1. **Foundation — Data contracts.** The going-forward foundation is the **views-frames** value objects (`PredictionFrame`, `TargetFrame`, `SpatioTemporalIndex`, `SpatialLevel`) — typed, immutable, numpy-only contracts (ADR-018). Pipeline-core **orchestration** types (`ModelPathManager`, `PipelineConfig`) remain a legitimate dependency of the Composition layer. Pipeline-core **private dataset internals** (`_ViewsDataset`, `_CDataset`, `_PGDataset`) are **forbidden** — a cross-repo private coupling (register C-114/C-135) being retired by the views-frames adoption (epic #137). The public `CMDataset`/`PGMDataset` containers are legacy on the render path and leave as each story lands.
2. **Ingestion — Loaders** (`views_reporting/loaders/`: declared-format adapters that read external prediction storage and produce Foundation datasets)
3. **Computation — Pure computation** (Statistical analysis, data transformation, reconciliation)
4. **Rendering** (Visualization, mapping)
5. **Composition and pipeline interface** (Report infrastructure, report templates)

The following invariant applies:

- Higher-level modules may depend on lower-level modules.
- Lower-level modules must not depend on higher-level modules.
- Cross-layer shortcuts are forbidden.

Dependency direction must remain acyclic.

### The Ingestion layer (Layer 2)

The Ingestion layer was added when views-reporting gained a declared-format loader registry (ADR-012). It exists because the pipeline emits predictions in more than one storage format (parquet DataFrames, numpy `PredictionFrame` directories), and that format distinction must be absorbed at a single boundary rather than leaking into computation, rendering, or composition.

Ingestion-layer rules:

- **Loaders may depend on the Foundation layer** — the **views-frames** `PredictionFrame` they produce (ADR-012), with per-level dispatch keyed by `SpatialLevel` (not bare `"cm"/"pgm"` strings).
- **Loaders construct the frame directly** from the declared storage format (parquet rows / numpy arrays + identifiers). The former sanctioned exception that let loaders import pipeline-core's `PredictionFrame`/`PredictionFrameConverter` is **being retired** with the views-frames adoption (epic #137 / S4); the conformance gate at the ingestion boundary is governed by ADR-009 §1b.
- **Loaders must not depend on Computation, Rendering, or Composition** (Layers 3–5). An ingestion adapter that imported a statistic or a renderer would be inverting the stack.
- **Any higher layer may call ingestion** via the `load_predictions` / `load_prediction_sequence` entry points — though in practice the Composition layer (report templates) is the primary consumer.

Format is always declared, never inferred (ADR-003). The Ingestion layer is the only place storage format is known.

---

## Architectural Boundaries

Each component must:

- Declare its responsibility zone (see ADR-001),
- Respect dependency direction (this ADR),
- Avoid implicit cross-layer coupling.

This ADR governs **structural dependency direction only**.

> The definition and validation of boundary contracts (schemas, configuration validation, handshake rules) are governed separately by ADR-009.

Topology defines *who may depend on whom*.  
ADR-009 defines *what must be true at the boundary*.

---

## Forbidden Patterns

The following are architectural violations in this repository:

- Visualization importing from report templates (Rendering depending on Composition)
- Statistical analysis depending on rendering libraries (Computation depending on Rendering)
- Report templates importing pipeline lifecycle code from pipeline-core (Composition reaching into foreign orchestration)
- A loader importing from Computation, Rendering, or Composition (Ingestion depending on a higher layer)
- Importing pipeline-core **private** dataset internals (`_CDataset` / `_PGDataset` / `_ViewsDataset`) anywhere in the repo (cross-repo private coupling — register C-114/C-135; depend on the views-frames contract instead)
- Computation, Rendering, or Composition reading prediction storage directly instead of through the Ingestion layer (bypassing the format boundary)
- Any module depending on binary assets at import time (lazy load only — binary assets must be loaded on demand, never at module import)
- Computation (statistics) importing visualization utilities
- Ingestion (loaders) importing report infrastructure
- Any circular dependency between ontological categories

If a dependency feels "convenient but wrong," it probably is.

---

## Cross-Repository Boundary: pipeline-core

views-reporting is an outer-layer package. The following constraint is absolute:

> views-reporting MUST NEVER be imported by pipeline-core as a hard dependency.

Pipeline-core may invoke views-reporting only via deferred import (e.g., `ReportingStage` importing report templates at runtime, not at module level). This preserves pipeline-core's ability to function without views-reporting installed.

---

## Consequences

### Positive

- Improved modularity
- Easier reasoning about change impact
- Safer refactoring
- Reduced architectural entropy
- Clean separation from pipeline-core is maintained

### Negative

- May require additional abstraction layers
- Can introduce short-term friction during refactoring
- Some rendering utilities may need to be duplicated rather than shared upward

These costs are accepted intentionally.

---

## Notes

This ADR defines structural direction of dependencies.

It does not define:

- boundary contract validation (ADR-009),
- semantic authority (ADR-003),
- or testing obligations (ADR-005).

Topology governs structure.  
Contracts govern interaction.
