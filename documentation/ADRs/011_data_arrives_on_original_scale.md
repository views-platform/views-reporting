
# ADR-011: Data Arrives on Its Original Measurement Scale

**Status:** Accepted  
**Date:** 2026-05-30  
**Deciders:** Simon, VIEWS platform team  

---

## Context

The VIEWS conflict forecasting platform historically used a column-naming convention to signal mathematical transformations applied to data: `ln_` for natural logarithm, `lx_` for offset logarithm, `lr_` for linear/raw (identity). Components downstream — including what is now views-reporting — inspected these prefixes to infer what transformation had been applied and to reverse it when needed (e.g., before geographic reconciliation).

This convention is no longer used for transform inference anywhere in the platform. The stepshifter, HydraNet, and other model architectures handle transformations internally and emit predictions on measurement scale. All 56+ production models in `views-models` use targets with the `lr_` prefix (linear), and no model emits `ln_` or `lx_` targets. The transform-detection branches in views-reporting never execute.

The convention created several problems:

1. **Combinatorial explosion.** Supporting `ln_`, `lx_` (with arbitrary offset), and `lr_` as inferable prefixes means every function that touches data must handle all three branches. Adding a new transform type would require changes across multiple modules.

2. **Implicit coupling.** The reporting library's reconciliation pipeline (`dataset_export.py`) silently inspects column names to decide whether to apply `exp()` before reconciliation and `log()` after. This couples the reporting layer to the training layer's naming decisions — a violation of the layered topology (ADR-002).

3. **Silent ambiguity.** A column named `ln_ged_sb` could mean "this was log-transformed" or "the upstream data source named it that way." The convention encodes transformation history into column names, making it impossible to distinguish intent from accident.

4. **Dead code.** The `DatasetTransformationModule` (~1,500 LOC) and the transform-detection branches in `dataset_export.py` were dead code with zero production callers, imposing maintenance cost without delivering value. *(The module has since been **removed** — C-25, 2026-06-20.)*

---

## Decision

**views-reporting expects all incoming data to be on its original measurement scale.**

This means:

- Data arriving at any views-reporting function — statistical analysis, visualization, mapping, reconciliation, report generation — is assumed to be in the units it will be displayed in.
- No function in this repository will inspect column names to infer, detect, or reverse mathematical transformations.
- No function will apply `exp()`, `log()`, or any inverse transform based on naming conventions.
- If data requires scale transformation before reporting, that transformation is the responsibility of the modeling library that produced it (e.g., views-hydranet, views-stepshifter, views-baseline). Neither views-pipeline-core nor this library performs or reverses transformations.

The term **"original measurement scale"** means: the scale in which the quantity is measured and interpreted. For conflict event counts, this is the count itself. For rates, this is the rate. Data arriving at views-reporting is expected to have already been converted back to measurement scale by the modeling library if that library worked internally in a different space (e.g., log-space). How that conversion happens is not this library's concern.

**Binary classification targets** (`by_` prefix) may also arrive alongside regression targets. These are on their own measurement scale (0/1). Whether views-reporting will need to handle `by_` columns is not yet determined — current usage flows classification evaluation through views-pipeline-core, not views-reporting. If this changes, `by_` data should be treated as already on measurement scale (binary *is* the measurement scale for a classification outcome).

---

## Consequences

### Positive

- Eliminates implicit coupling between reporting and training conventions
- Removes ~1,500 LOC of dead transform-detection and transform-lifecycle code
- Makes the reporting library's data contract explicit and simple
- Prevents the combinatorial explosion of supporting new transform types
- Aligns with the platform-wide retirement of prefix-based transform conventions

### Negative

- Any model or pipeline stage that currently passes log-transformed data to views-reporting must convert to measurement scale first
- The `DatasetTransformationModule` was removed (C-25, 2026-06-20); the **direct** `polars` declaration was dropped with it (it was the module's only consumer *in views-reporting*). Note `polars` remains a *transitive* dependency via **views-pipeline-core**, which declares it directly — so the install footprint is unchanged until pipeline-core drops it too
- Existing tests that exercise transform-related code paths become obsolete

### Migration

The migration is low-risk because the transform-detection branches are currently dead code (never triggered in production). The concrete steps are:

1. Remove the `ln`/`lx` branch logic from `dataset_export.py:to_reconciler()` and `reconcile_pg_dataset()`
2. Remove `DatasetTransformationModule` — **done** (C-25, 2026-06-20); the pipeline-core re-export shim is retired separately (views-pipeline-core #183)
3. Update CICs for affected classes
4. Update tests to remove transform-related test cases

These changes are tracked as C-10 in the technical risk register.

---

## Relationship to Other ADRs

- **ADR-001 (Ontology):** The "Data Transformation" category has been **retired and removed** from the ontology (C-25, 2026-06-20).
- **ADR-002 (Topology):** This decision enforces the topology rule that lower layers (computation) must not depend on upper layers (rendering). Transform detection violated this by making the reconciliation layer (mid) depend on naming conventions from the training layer (external).
- **ADR-003 (Authority of Declarations):** Data scale is now declared by the producer, not inferred by the consumer. This aligns with "declarations over inference."
- **ADR-009 (Boundary Contracts):** The boundary contract with pipeline-core now includes an explicit data scale requirement: data must arrive on its original measurement scale.

---

## Cross-Platform Context

Transformations and their inverses are the exclusive domain of the modeling libraries (views-hydranet, views-stepshifter, views-baseline, views-r2darts2). This is a platform-wide principle, not a unilateral decision by views-reporting. The corresponding ADRs are:

- **views-pipeline-core ADR-040:** Authority of declarations over inference — forbids inferring semantics (including scale) from data content.
- **views-models ADR-012:** Target scale and prefix convention — documents the producer-side contract: models emit `lr_` (linear) targets on measurement scale; the `transformations` config is an instruction to the modeling library, not to the pipeline.

This ADR states the consumer side of the same contract.

---

## Notes

This ADR governs views-reporting only. It does not mandate changes to other repositories — it states what views-reporting expects from its inputs. The producer-side responsibilities are documented in the producing repositories' own ADRs.

The phrase "original measurement scale" was chosen deliberately over "raw" (which implies unprocessed, potentially noisy data) and "untransformed" (which defines the concept by what it is not). "Original measurement scale" states positively what the data should be: in the units that correspond to the real-world quantity being measured.
