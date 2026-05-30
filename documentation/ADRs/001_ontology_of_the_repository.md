
# ADR-001: Ontology of the Repository

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

views-reporting was extracted from views-pipeline-core to isolate visualization, reporting, statistics, and mapping concerns from pipeline infrastructure. This extraction created a repository with a distinct identity: it is the outer-layer presentation and analysis package for the VIEWS conflict forecasting platform.

Without an explicit ontology, this extracted codebase risks:
- implicit concepts bleeding back from pipeline-core
- overloaded abstractions that mix rendering with computation
- objects that combine data ownership with data presentation
- semantics that exist only in the heads of contributors who remember the pre-extraction monolith

An explicit ontology is required to define **what kinds of things are allowed to exist** in this repository, and which kinds of things are explicitly disallowed.

---

## Decision

This repository defines a **closed set of conceptual categories** ("entities") that are allowed to exist.

Each category has:
- a clear semantic role
- an expected stability level
- explicit boundaries

Anything that does not clearly belong to one of these categories is considered **out of scope** and must be re-designed or rejected.

---

## Core Ontological Categories

### Statistical Analysis

- **Purpose:** Bayesian posterior analysis (HDI, MAP), reconciliation optimization via scipy. Consumes `_ViewsDataset` from pipeline-core, produces derived quantities.
- **Authority:** Owns all statistical computation logic; does NOT own the data containers it operates on.
- **Expected stability:** Evolving — extracted from pipeline-core, subject to post-extraction refactoring.
- **What it must not contain:** Data container definitions, pipeline lifecycle logic, or rendering code.

### Visualization

- **Purpose:** Interactive and static charts — time-series line graphs, distribution plots, geographic maps. Consumes datasets, produces Plotly/matplotlib/geopandas figures.
- **Authority:** Owns rendering logic and visual presentation decisions; does NOT own the data schemas or decide which entities to visualize.
- **Expected stability:** Evolving — scale problems (C-105, C-106) will require sampling and lazy rendering.
- **What it must not contain:** Statistical computation, report assembly logic, or pipeline orchestration.

### Report Infrastructure

- **Purpose:** HTML report assembly — `ReportModule`, tailwind styling, metric filtering utilities. Composes visualizations and text into deliverable HTML documents.
- **Authority:** Owns report structure and formatting; does NOT own the content.
- **Expected stability:** Stable once extracted.
- **What it must not contain:** Rendering logic, statistical computation, or pipeline lifecycle management.

### Report Templates

- **Purpose:** Pipeline-facing entry points — `EvaluationReportTemplate`, `ForecastReportTemplate`. Called by pipeline-core's `ReportingStage` via deferred import.
- **Authority:** Owns the orchestration of which sections appear in each report type. Does NOT own pipeline lifecycle.
- **Expected stability:** Evolving — new report types may be added.
- **What it must not contain:** Pipeline stage definitions, model training logic, or direct rendering code.

### Data Transformation (Legacy)

- **Purpose:** `DatasetTransformationModule` — dataset operations consumed by downstream repos.
- **Authority:** Owns transformation logic; does NOT own the datasets or their schemas.
- **Expected stability:** Legacy. Per ADR-011 (2026-05-30), views-reporting expects data on its original measurement scale. `DatasetTransformationModule` has zero production callers and the `ln_`/`lx_`/`lr_` prefix convention is retired from this codebase. This category is a candidate for deprecation.
- **What it must not contain:** Data container definitions, visualization code, or report assembly.

### Reconciliation

- **Purpose:** `ReconciliationModule` — spatial hierarchy constraint optimization for ensemble predictions.
- **Authority:** Owns reconciliation algorithm; does NOT own ensemble composition.
- **Expected stability:** Stable.
- **What it must not contain:** Ensemble construction logic, visualization, or pipeline orchestration.

### Binary Assets

- **Purpose:** Shapefiles (country, priogrid) and report header images. Non-code resources consumed by mapping and report modules.
- **Authority:** Assets are authoritative geographic boundaries; must NOT contain derived or generated data.
- **Expected stability:** Stable.
- **What it must not contain:** Generated outputs, derived data, or code.

---

## Stability Rules

- **Stable categories** (Report Infrastructure, Reconciliation, Binary Assets) are expected to remain structurally unchanged across the lifetime of the project. Data Transformation is now legacy per ADR-011.
- **Evolving categories** (Statistical Analysis, Visualization, Report Templates) are explicitly allowed to evolve or be replaced, but changes must respect the ontological boundaries defined here.
- Stability expectations must be documented for each category and respected during review.

Stability is a design constraint, not a preference.

---

## Explicit Non-Entities

The following are **not allowed** as first-class concepts in this repository:

- Pipeline lifecycle objects (stages, runners, schedulers) — those belong in pipeline-core
- Data container definitions (`_ViewsDataset`, `ModelPathManager`) — imported, never defined here
- Model training or inference logic — belongs in pipeline-core or model repos
- Implicit or inferred semantics
- Objects that mix multiple ontological roles (e.g., a class that both computes statistics and renders charts)
- "Convenience" abstractions that hide meaning
- Concepts that exist only via naming conventions

If a concept matters, it must be explicit.

---

## Consequences

### Positive
- Shared vocabulary across contributors
- Reduced conceptual drift
- Clear review criteria for new abstractions
- Clean separation from pipeline-core prevents re-entanglement

### Negative
- Requires upfront discipline
- Some refactors may be blocked until concepts are clarified

These trade-offs are accepted.

---

## Notes

This ADR defines *what exists*, not *how components depend on each other*.  
Dependency rules are defined separately in ADR-002.
