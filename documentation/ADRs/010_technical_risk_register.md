# ADR-010: Technical Risk Register

**Status:** Accepted
**Date:** 2026-05-28
**Deciders:** Simon, VIEWS platform team

---

## Context

As views-reporting is established via the extraction from views-pipeline-core (ADR-054), technical risks need a durable, trackable home accessible to all contributors. Risks identified during extraction, code reviews, falsification audits, and future development need structured tracking rather than ad-hoc documentation in conversations or audit reports.

Pipeline-core already maintains a risk register (ADR-044). Views-reporting adopts the same pattern independently, since it is a separate repository with its own governance.

## Decision

We establish a **Technical Risk Register** as a first-class governance artifact at `reports/technical_risk_register.md`.

### Register Format

Each entry has:
- **ID:** `C-xx` for concerns, `D-xx` for disagreements
- **Tier:** 1 (critical) through 4 (minor)
- **Description:** What the risk is
- **Trigger:** The specific circumstance under which the risk becomes actionable
- **Source:** Where this risk was identified (e.g., expert review, falsification audit, extraction review)
- **Status:** Open / Mitigated / Accepted

### Tier Definitions

| Tier | Severity | Criteria |
|------|----------|----------|
| 1 | Critical | Silent data corruption or model output incorrectness. No error signal. Requires immediate attention. |
| 2 | High | Structural fragility that will cause failures under realistic change scenarios. Clear trigger exists. |
| 3 | Medium | Maintainability or coupling issues that increase cost of change. Multiple developers affected. |
| 4 | Low | Code quality observations. Single-developer scope. No correctness or reliability impact. |

### When to Add Entries

Concerns are opened during:
- Expert code reviews
- Tech debt audits
- Falsification audits
- Extraction reviews (PRs 1-8)
- Incident post-mortems

### When to Close Entries

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach

Closure requires updating the entry's status and adding a resolution note.

## Rationale

A centralized risk register prevents technical risks from being rediscovered repeatedly. It provides a prioritized backlog for tech debt work and a historical record of architectural decisions. As extracted code arrives in views-reporting (PRs 1-8), new risks specific to this package will be tracked here rather than in pipeline-core's register.

## Consequences

### Positive
- Risks are tracked and prioritized independently from pipeline-core
- New contributors can see known issues before modifying affected code
- AI assistants can check the register before proposing changes to risky areas

### Negative
- Register maintenance overhead
- Risk of register going stale if not updated during refactoring

## References

- [Technical Risk Register](../../reports/technical_risk_register.md)
- [ADR-004: Rules for Evolution and Stability](004_rules_for_evolution_and_stability.md)
- Pipeline-core ADR-044 (same pattern, separate register)

---
*End of ADR-010.*
