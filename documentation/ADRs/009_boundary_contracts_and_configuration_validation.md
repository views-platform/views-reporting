
# ADR-009: Boundary Contracts and Configuration Validation

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

Complex systems fail most often at boundaries:

- between modules,
- between configuration and runtime,
- between data producers and consumers,
- between planning and execution.

views-reporting operates at several critical boundaries:

- **views-reporting / pipeline-core boundary:** Report templates consume `_ViewsDataset` and `ModelPathManager` from pipeline-core. The schema of these data containers is owned by pipeline-core, not by this repository. If the contract drifts, reports break silently.
- **Statistical analysis / visualization boundary:** Computation results (HDI intervals, MAP estimates, reconciliation outputs) flow into rendering functions. The shape, units, and semantics of these intermediate results must be explicit.
- **Report templates / pipeline-core `ReportingStage` boundary:** Pipeline-core invokes report templates via deferred import. The calling convention, expected arguments, and return contract must be declared, not assumed.

Ambiguous configuration, hidden defaults, and implicit contracts
introduce silent semantic drift and runtime fragility.

To preserve architectural integrity and fail-loud guarantees (ADR-003),
all external and internal boundaries must be explicit and validated.

---

## Decision

This repository adopts the following invariants:

> All architectural boundaries must declare explicit contracts.  
> All configuration must be validated at entry.  
> No semantic defaults may exist silently.

---

## 1. Boundary Contracts

Every boundary between components must define:

- Explicit input schema
- Explicit output schema
- Declared invariants
- Failure semantics

Key boundaries in views-reporting:

- **views-reporting / pipeline-core:** `_ViewsDataset` schema contract (expected attributes, MultiIndex structure), `ModelPathManager` interface (expected methods and path conventions)
- **Statistical analysis / visualization:** computation results must declare their semantic type (e.g., HDI bounds, MAP point estimate, reconciled prediction) — visualization must not infer semantics from array shape
- **Report templates / `ReportingStage`:** deferred import contract — templates must be importable without pipeline-core's full module graph, and must accept a declared argument signature

Implicit contracts are prohibited.

If a boundary assumption cannot be declared clearly,
the boundary is ill-defined and must be redesigned.

---

## 2. Configuration as First-Class Artifact

Configuration is not a convenience layer.
It is an architectural artifact.

Configuration must:

- Be explicit
- Be versionable
- Be externally inspectable
- Be validated before execution
- Not rely on hidden defaults

Changing configuration must not silently alter system meaning —
for example, changing a report template parameter must not silently
change which statistical metrics are included or how they are rendered.

---

## 3. Validation at Entry (Handshake Principle)

All configuration and external inputs must be validated at the system boundary.

Validation must occur:

- Before state mutation
- Before execution begins
- Before report assembly proceeds

The system must fail early if:

- Required fields are missing (e.g., dataset lacks expected columns)
- Types are incorrect (e.g., non-DataFrame passed where DataFrame expected)
- Redundant parameters disagree (e.g., declared level contradicts MultiIndex structure)
- Declared invariants are violated (e.g., spatial hierarchy constraints not met)

Borrowed or assumed state is prohibited.

---

## 4. Separation of Configuration Domains

Configuration domains must be separated conceptually.

In views-reporting:

- **Operational parameters** (affect computation): statistical method parameters, reconciliation constraints, sampling rates
- **Presentation parameters** (affect rendering): color scales, chart dimensions, map projections, tailwind classes
- **Metadata parameters** (informational only): report titles, date stamps, version labels

Cross-domain coupling must be explicit.

Configuration that affects computation must not be disguised as presentation,
and vice versa.

---

## 5. Redundancy and Consistency Checks

Where ambiguity risk is high, explicit redundancy is preferred.

Examples in views-reporting:

- Declaring both the expected resolution level and the MultiIndex structure
- Declaring both the metric type and the expected column names
- Declaring both the spatial hierarchy and the reconciliation constraints

Redundant declarations must be validated for consistency.

Silent derivation is discouraged where semantic meaning is involved.

---

## 6. Failure Semantics

Configuration validation failures must:

- Be logged (ADR-008)
- Be raised explicitly (ADR-008)
- Halt execution

Warnings are insufficient for structural configuration errors.

---

## Consequences

### Positive

- Eliminates hidden configuration drift
- Reduces boundary fragility, especially at the pipeline-core interface
- Strengthens fail-loud guarantees
- Improves reproducibility and traceability of generated reports

### Negative

- Requires explicit schemas
- Adds validation boilerplate
- Increases up-front configuration clarity requirements

These costs are accepted.

---

## Notes

This ADR does not prescribe:

- Specific file layouts
- Specific configuration libraries
- Specific schema frameworks

Operational configuration structures may vary,
provided they comply with the invariants defined here.
