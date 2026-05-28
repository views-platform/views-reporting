
# ADR-004: Rules for Evolution and Stability

**Status:** Deferred  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  
**Informed:** All contributors  

---

## Context

The preceding ADRs establish:

- **ADR-001:** the ontology of the repository (what exists in views-reporting)
- **ADR-002:** the topology of the repository (how components may relate, including the pipeline-core boundary)
- **ADR-003:** semantic authority (who owns meaning and how it is declared)

Together, these decisions define the system's structure and semantics at a point in time.

What they do **not** yet define is how the system is allowed to **change over time**:
- which components are expected to be stable (e.g., reconciliation, data transformation)
- which components may evolve freely (e.g., visualization, statistical analysis)
- what constitutes a breaking change to the pipeline-core boundary contract
- when compatibility guarantees apply to report templates consumed by pipeline-core's `ReportingStage`
- when a new ADR is required

These questions are architectural, cross-cutting, and costly to reverse once pipeline-core or downstream consumers depend on specific views-reporting interfaces.

---

## Decision

No decision is made at this time.

Rules governing stability, evolution, and backwards compatibility are **explicitly deferred**.

This ADR exists to:
- acknowledge the importance of this dimension
- reserve a place for a future, explicit decision
- prevent ad-hoc or implicit policies from emerging unnoticed

---

## Rationale for Deferral

At the time of writing:

- views-reporting has been recently extracted from pipeline-core; core abstractions are still being exercised and refined
- The boundary between experimental and stable components may shift as scale problems (C-105, C-106) are resolved
- Premature guarantees about visualization APIs or report template interfaces would either be ignored or constrain necessary exploration
- The deferred import contract with pipeline-core's `ReportingStage` is functional but not yet hardened

Deferring this decision preserves design freedom while maintaining architectural honesty.

---

## Trigger Conditions for Reconsideration

This ADR should be revisited when one or more of the following become true:

- Pipeline-core's `ReportingStage` depends on specific views-reporting interfaces that cannot change without coordination
- External users or downstream systems depend on views-reporting's statistical outputs
- Reproducibility across time becomes a contractual requirement for generated reports
- Breaking changes to visualization or report template APIs begin to incur real coordination or migration costs
- Multiple versions of the same report template must be supported concurrently
- Contributors express uncertainty about what is safe to change

At that point, a new ADR should supersede this one.

---

## Non-Decisions (Explicitly Out of Scope for Now)

This ADR does **not** define:
- Versioning schemes
- Release processes
- Migration tooling
- Deprecation mechanics
- API stability guarantees for report templates or statistical modules

Those topics are intentionally postponed.

---

## Consequences

### Positive
- Avoids premature or brittle guarantees
- Preserves flexibility during early post-extraction evolution
- Makes the absence of rules explicit rather than accidental

### Negative
- Contributors must exercise judgment when making breaking changes
- Some uncertainty remains about long-term guarantees for the pipeline-core boundary

These consequences are accepted intentionally.

---

## Notes

This ADR is a placeholder by design.

Its purpose is to ensure that when rules for evolution and stability are introduced, they are:
- explicit
- deliberate
- consistent with ADR-001 through ADR-003

Until then, change is governed by those ADRs and by careful review.
