
# ADR-003: Authority of Declarations Over Inference

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

In a reporting and visualization system for conflict forecasting, the same concept often appears in multiple representations:
- raw dataset vs transformed dataset
- statistical summary vs rendered chart
- metric name in configuration vs column header in a DataFrame

When these representations diverge, systems often attempt to **infer intent** after the fact — guessing chart types from data shapes, deriving metric semantics from column name prefixes, or assuming confidence intervals from sample counts.

Such inference leads to:
- silent errors in rendered outputs,
- irreproducible reports,
- post-hoc rationalization of visualization choices,
- and ambiguity about what the system actually believes a metric represents.

A clear rule is required to define **where semantic authority lives**, and how ambiguity is resolved.

---

## Decision

In this repository:

> **All meaningful semantics must be explicitly declared.  
> Inference of semantics across component boundaries is forbidden.**

When multiple representations of the same concept exist, **a single source of truth must be designated**.

If required semantics are missing, ambiguous, or contradictory, the system **must not guess**.

---

## Global Invariant: Fail Loud on Semantic Ambiguity

In this repository, **silent failure is considered a bug**.

Whenever required semantics are:
- missing,
- ambiguous,
- contradictory,
- or inconsistent across representations,

the system **must fail loudly and immediately**.

This includes, but is not limited to:
- raising explicit runtime errors,
- failing validation or consistency checks,
- refusing to proceed without explicit declaration.

Warning-only behavior, implicit fallbacks, or "best-effort" inference are **forbidden**
for any decision-relevant semantics.

This rule applies regardless of environment:
development, experimentation, evaluation, or production.

---

## Rules of Semantic Authority

The following rules apply throughout the repository:

- Semantics must be **declared**, not inferred.
- Transformations are owned by the component that performs them.
- Metadata overrides naming conventions.
- Visualization consumes **declared semantics only** — it does not derive chart types or axis labels from data shape.
- Statistical analysis consumes **declared metric types only** — it does not infer whether a column is a regression target or a classification target from its name.
- No component may guess another component's intent.

Inference is permitted **only within a component's internal logic**, never across component boundaries.

---

## Examples of Forbidden Behavior

The following are concrete violations of this ADR in the views-reporting domain:

- Inferring metric types (regression vs classification) from column name prefixes or suffixes
- Inferring chart types (line graph vs bar chart vs map) from dataset subclass or DataFrame shape
- Inferring confidence interval semantics from sample count or container type
- Inferring spatial resolution (CM vs PGM) from DataFrame row count
- Guessing report section order from module import order
- Deriving HDI bounds from column naming conventions instead of explicit statistical metadata
- Proceeding after emitting warnings when required semantics are unknown

If behavior matters, it must be declared.

---

## Consequences

### Positive
- Eliminates silent semantic drift in rendered outputs
- Improves reproducibility of reports and visualizations
- Makes disagreements explicit and resolvable
- Enables principled failure under uncertainty

### Negative
- Requires more explicit configuration and metadata
- Some convenience patterns are disallowed
- Errors may surface earlier and more frequently

These costs are accepted intentionally.

---

## Notes

This ADR does not define:
- what concepts exist (ADR-001),
- or how components depend on each other (ADR-002).

It defines **who is allowed to say what something means**,  
and mandates **loud failure over silent misinterpretation**.
