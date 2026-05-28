
# ADR-005: Testing as Mandatory Critical Infrastructure

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

This repository supports systems whose outputs directly inform conflict forecasting reports, visualizations, and statistical analyses consumed by decision-makers and researchers.

In such systems, failure is not limited to crashes or exceptions.
Failures may also include:
- silent semantic drift in rendered charts or computed statistics,
- misuse by well-intentioned users who misread visualizations,
- over-trust or under-trust in forecasting outputs presented through reports,
- brittle behavior under realistic conditions (e.g., 172,000 priogrid entities overwhelming a visualization pipeline).

Given this, testing is not a convenience or a quality signal.
It is **critical infrastructure**.

The absence of rigorous, multi-perspective testing constitutes unacceptable risk.

---

## Decision

This repository treats **testing as mandatory critical infrastructure**.

All non-trivial functionality **must be covered by tests**.

Testing is not limited to correctness under ideal conditions, but must explicitly address:
- adversarial behavior,
- realistic human use,
- and system robustness under expected operation.

To achieve this, tests are explicitly divided into **three complementary categories**:

- 🟥 **Red team tests** (adversarial)
- 🟫 **Beige team tests** (realistic, neutral misuse)
- 🟩 **Green team tests** (supportive, resilience-oriented)

Each category serves a distinct purpose and **none may substitute for another**.

---

## Test Taxonomy

### 🟥 Red Team Tests — Adversarial Testing

Red team tests deliberately attempt to **break, exploit, or misuse the system** by assuming hostile or worst-case behavior.

- **Goal:** expose failure modes, vulnerabilities, unsafe behaviors
- **Mindset:** *"How could this go wrong?"*
- **Typical focus in views-reporting:**
  - Adversarial scale inputs: feeding 172,000 priogrid entities to a visualization function designed for country-level data
  - Malformed MultiIndex DataFrames passed to statistical analysis or rendering functions
  - Missing VIEWSER data columns that statistical modules expect to be present
  - Corrupted or missing shapefiles fed to mapping modules
  - Extremely large sample counts that exhaust memory during HDI computation
  - Report templates invoked with contradictory or impossible configuration

Red team tests are expected to fail the system until weaknesses are addressed.

---

### 🟫 Beige Team Tests — Realistic, Neutral Usage

Beige team tests focus on **boring, realistic, non-adversarial usage patterns** that are neither friendly nor hostile — but still dangerous if mishandled.

- **Goal:** catch failures caused by normal human behavior
- **Mindset:** *"What will regular users actually do?"*
- **Typical focus in views-reporting:**
  - Mixed CM/PGM datasets passed to functions that expect a single resolution level
  - Partial sample data (fewer samples than expected) producing statistically misleading HDI intervals
  - Entity subsets that produce misleading graphs (e.g., cherry-picked countries that distort scale)
  - Users copy-pasting rendered HTML report sections without context
  - Ignoring confidence intervals in visualizations and treating point estimates as certain
  - Passing a dataset with NaN-heavy columns to chart rendering

Beige team tests are mandatory for any user-facing or decision-facing component.

---

### 🟩 Green Team Tests — Supportive, Resilience-Oriented Testing

Green team tests focus on **ensuring the system works as intended** under expected conditions and degrades safely.

- **Goal:** ensure reliability, robustness, and trustworthiness
- **Mindset:** *"How do we make this solid?"*
- **Typical focus in views-reporting:**
  - Correct rendering at CM scale (country-month level) — expected entity counts, proper axis labels, valid color scales
  - Statistical computation accuracy — HDI bounds match known analytical results, MAP estimates are correct
  - Report HTML validity — well-formed documents, correct tailwind class application, no broken internal links
  - Geographic map rendering — shapefiles load correctly, projections are consistent, priogrid boundaries align
  - Reconciliation module produces outputs that satisfy spatial hierarchy constraints

Green team tests are expected to pass continuously and form the backbone of CI.

---

## Relationship to Other ADRs

This ADR reinforces and operationalizes:

- **ADR-001 (Ontology):** tests must respect declared categories and stability expectations
- **ADR-002 (Topology):** tests must not bypass architectural boundaries (e.g., test utilities must not import across layers)
- **ADR-003 (Authority & Semantics):** tests must fail loudly on semantic ambiguity
- **ADR-004 (Deferred):** future evolution rules must account for test coverage obligations

Testing is a primary mechanism by which these ADRs are enforced.

---

## Enforcement Rules

- Code that meaningfully affects behavior **must not be merged without tests**
- Tests that only cover happy paths are insufficient
- Warning-only behavior in tests is unacceptable for decision-relevant semantics
- If a failure mode is known and untested, it is considered technical debt and must be tracked explicitly

The absence of appropriate tests is valid grounds for blocking a change.

---

## Consequences

### Positive
- Reduced risk of silent failure in reports and visualizations
- Earlier detection of misuse and misunderstanding
- Increased trustworthiness of statistical outputs
- Clearer system boundaries and guarantees

### Negative
- Higher upfront development cost
- Slower iteration if tests are neglected
- Requires cultural discipline and reviewer enforcement

These costs are accepted intentionally.

---

## Notes

Testing in this repository is not merely about correctness.

It is about **preventing harm, misunderstanding, and overconfidence**  
in systems that operate under uncertainty and pressure.
