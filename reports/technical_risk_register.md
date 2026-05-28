# Technical Risk Register

**Last updated:** 2026-05-28
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 0 concerns (0 resolved) + 0 disagreements

---

## Tier Definitions

| Tier | Severity | Criteria |
|------|----------|----------|
| 1 | Critical | Silent data corruption or model output incorrectness. No error signal. Requires immediate attention. |
| 2 | High | Structural fragility that will cause failures under realistic change scenarios. Clear trigger exists. |
| 3 | Medium | Maintainability or coupling issues that increase cost of change. Multiple developers affected. |
| 4 | Low | Code quality observations. Single-developer scope. No correctness or reliability impact. |

---

## Open Concerns

| ID | Tier | Narrative | Trigger | Source | Status |
|----|------|-----------|---------|--------|--------|

---

## Disagreements

| ID | Narrative | Positions | Status |
|----|-----------|-----------|--------|

---

## Resolved Concerns

| ID | Tier | Narrative | Trigger | Source | Status |
|----|------|-----------|---------|--------|--------|

---

## Register Conventions

Concerns are registered via the `register-risk` skill and curated via the `review-rr` skill.

- **C-xx:** Concern entries (technical risks, code quality issues, architectural debt)
- **D-xx:** Disagreement entries (unresolved debates between expert perspectives)

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
