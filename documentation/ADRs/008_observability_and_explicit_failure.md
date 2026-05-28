
# ADR-008: Observability and Explicit Failure

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

This repository supports systems where silent failure, degraded semantics,
or partial execution can cause cascading downstream impact — a silently
corrupted statistical computation propagates into a misleading visualization,
which is then composed into a report consumed by decision-makers.

Stack traces alone are insufficient for traceability in a system that
spans statistical analysis, visualization rendering, and report assembly
across multiple modules.

To preserve architectural integrity and post-hoc auditability,
failures must be both:

- **explicitly raised**, and
- **persistently recorded**.

Inconsistent logging and error propagation patterns increase
debugging complexity and obscure structural failures — particularly
when report generation fails silently and produces incomplete HTML
without any indication of missing sections.

---

## Decision

The repository adopts the following invariant:

> Structural failures must be both **logged persistently** and **raised explicitly**.

### 1. Explicit Failure

- Invariant violations must raise exceptions.
- Structural failures must not be downgraded to warnings.
- Errors must not be silently swallowed.
- Fallback behavior must not hide semantic failure.

Fail-loud (ADR-003) applies fully to runtime behavior.

---

### 2. Persistent Observability

- Raised structural failures must be logged at `ERROR` level or higher.
- Critical system-wide failures must be logged at `CRITICAL`.
- Logging must occur before or at the point of raising.
- Logging is not a substitute for raising; raising is not a substitute for logging.

---

### 3. Scope

This ADR applies to:

- data validation failures (e.g., malformed MultiIndex in datasets),
- configuration inconsistencies (e.g., contradictory report template parameters),
- semantic ambiguity (e.g., undeclared metric types passed to visualization),
- broken invariants (e.g., spatial hierarchy violations in reconciliation),
- report assembly breakdowns (e.g., missing sections, failed rendering),
- and other structural system failures.

It does not prescribe formatting, spacing, or specific logging utilities.
Operational conventions may evolve separately.

---

## Consequences

### Positive

- Persistent traceability of structural failures
- Reduced debugging entropy
- Strong alignment with fail-loud invariant (ADR-003)
- Improved production observability for report generation pipelines

### Negative

- Slight increase in boilerplate
- Requires discipline in error handling

These costs are accepted.

---

## Notes

This ADR defines architectural requirements for failure handling.

It does not define log formatting standards, log retention policies,
or logging infrastructure configuration, which are operational concerns.

Observability must support understanding.
Failure must never be silent.
