
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

- **Purpose:** Bayesian posterior analysis (HDI, MAP). Consumes `_ViewsDataset` from pipeline-core, produces derived quantities. *(Reconciliation optimization, formerly hosted here via `ForecastReconciler`, was deleted 2026-06-28 (#72) and relocated to views-frames as `views_frames_reconcile` — see the Reconciliation category below.)*
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

### Data Transformation — RETIRED (removed 2026-06-20, C-25)

`DatasetTransformationModule` (the legacy `ln_`/`lx_`/`lr_` log-transform lifecycle) was a
legacy ontological category with **zero production callers**. It was **deleted** once
ADR-011 established that views-reporting expects data on its original measurement scale
(transform inference retired). **Data transformation is no longer an ontological category
of this repository.** *(History: pipeline-core ADR-054 extracted the module here; the
pipeline-core re-export shim is retired separately — see views-pipeline-core #183.)*

### Reconciliation — RELOCATED (deleted 2026-06-28, #72)

`ReconciliationModule` / `ForecastReconciler` (spatial hierarchy constraint optimization
for ensemble predictions) **lived in this repository** but was **deleted** with #72.
views-reporting now **renders**; it does not reconcile. **Reconciliation is no longer an
ontological category of this repository.** The live reconciler is `views_frames_reconcile`
in **views-frames** (frames-native, numpy, parity-proven against the former
`ForecastReconciler`), consumed by pipeline-core via an injected `Reconciler` protocol and
wired in views-models. *(History: it was extracted here from pipeline-core and carried the
torch dependency only while it lived here — see register C-24/C-33, Cluster B.)*

### Binary Assets

- **Purpose:** Shapefiles (country, priogrid) and report header images. Non-code resources consumed by mapping and report modules.
- **Authority:** Assets are authoritative geographic boundaries; must NOT contain derived or generated data.
- **Expected stability:** Stable.
- **What it must not contain:** Generated outputs, derived data, or code.

### Ingestion (Loaders)

- **Purpose:** `views_reporting/loaders/` — declared-format adapters (`DataFrameLoader`, `PredictionFrameLoader`) that read external prediction storage (parquet DataFrames, numpy PredictionFrame directories) and materialize `CMDataset`/`PGMDataset`. The storage format is declared by the caller, never inferred (ADR-003, ADR-012). This is the **Ingestion layer (Layer 2)** in the topology (ADR-002).
- **Authority:** Owns format dispatch and format→container conversion; does NOT own dataset schemas or the storage formats themselves. It is the single place in views-reporting where prediction storage format is known.
- **Expected stability:** Evolving — the pipeline is mid-migration from DataFrame to PredictionFrame storage (ADR-012); new formats are added by registering new loaders.
- **What it must not contain:** Storage-format definitions, statistical computation, rendering, or report assembly.

### Metadata

- **Purpose:** `views_reporting/metadata/` — index-keyed entity identity accessors (ISO codes, country names) for country and PRIO-GRID frames, read from the **bundled** parquet assets (`metadata/data/`, regenerated dev-side by `scripts/build_entity_metadata.py` — C-22 Resolved, epic #204). Consumed by mapping and visualization for labels and the isoab↔shapefile join. *(The country↔grid mapping accessors formerly also served reconciliation; reconciliation was deleted/relocated to views-frames 2026-06-28, #72. The dataset-parameter accessor surface was deleted as dead code 2026-07-02, C-114.)*
- **Authority:** Owns the accessor logic and the bundled identity assets; does NOT own entity definitions (VIEWS DB, frozen at snapshot) or the frames it annotates.
- **Expected stability:** Stable — no service calls (the viewser-retirement risk C-22 is resolved); the residual risk is bundle staleness, guarded and tracked as register C-112.
- **What it must not contain:** Entity definitions, dataset manipulation, pipeline orchestration, rendering, or any render-time service call (ADR-018).

---

## Stability Rules

- **Stable categories** (Report Infrastructure, Binary Assets) are expected to remain structurally unchanged across the lifetime of the project. (Data Transformation was retired and removed; Reconciliation was deleted and relocated to views-frames (#72) — see above.)
- **Evolving categories** (Statistical Analysis, Visualization, Report Templates, Ingestion, Metadata) are explicitly allowed to evolve or be replaced, but changes must respect the ontological boundaries defined here.
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
