# Why views-reporting Exists

**Date:** 2026-05-27 (investigation) → 2026-05-29 (extraction complete)
**Governing decision:** ADR-054 in views-pipeline-core
**Author:** Simon Polichinel von der Maase, VIEWS platform team

---

## The Problem

By early 2026, `views-pipeline-core` had grown into something it was never
meant to be. Its legitimate role was pipeline orchestration — binding model
classes, evaluation packages, prediction stores, and the `views-models` repo.
Configuration, data loading, model management, prediction I/O, pipeline
lifecycle. Infrastructure.

Instead it had become a 2.5 GB dependency monster. Visualization code,
statistical analysis, report formatting, geographic rendering, data
transformation — all of it lived inside the orchestration library.
The practical consequences were severe.

### The dependency tax

`handlers.py` — the file that defines `CMDataset` and `PGMDataset`, the two
most imported classes in the entire platform — had these at the top:

```python
from views_pipeline_core.modules.statistics import PosteriorDistributionAnalyzer  # scipy
import matplotlib.pyplot as plt
from joblib import Parallel, delayed
import torch
```

These were **top-level imports**, not deferred. Any code anywhere in the
platform that wrote `from views_pipeline_core.data.handlers import CMDataset`
triggered loading of scipy (~150 MB), matplotlib (~80 MB), joblib (~5 MB),
and torch (~2 GB). All of it. Every time. Even if the code never touched
a single visualization or statistical function.

Eleven consumer modules imported from `handlers.py`. Only 7 of them ever
used the methods that required these dependencies. The other 4 paid a
~2.5 GB tax for nothing.

### The god class

`_ViewsDataset` — the base class for all dataset types — was 2,295 lines
of code with 85 methods. It mixed:

- **Data representation** (constructors, indexing, tensor conversion)
- **Statistical analysis** (MAP estimation, HDI computation, joblib parallelization)
- **Visualization** (distribution plots via matplotlib/seaborn, deferred Plotly imports)
- **Reconciliation export** (torch tensor conversion for ForecastReconciler)
- **Geographic metadata** (hidden VIEWSER network calls via `_build_entity_metadata_cache()`)

A typed DataFrame wrapper had become the dumping ground for every piece of
functionality that needed access to prediction data.

### Scale failures

The visualization code generated 172,000 Plotly traces at PRIO-GRID-month
level, producing multi-gigabyte HTML files and out-of-memory conditions
(C-105, C-106 in the pipeline-core risk register). These could not be fixed
in place because the code lived inside an orchestration library with no
rendering infrastructure — no pagination, no lazy loading, no streaming.

### Blocked work

Sprint 4's work on scale-aware evaluation report graphs (C-105) was paused.
The visualization pipeline could not be fixed without first understanding
the full dependency graph and relocating the misplaced code.

---

## The Investigation

A full architectural investigation mapped every file, every import chain,
every dependency, and every consumer (`architectural_misplacement_investigation.md`
in views-pipeline-core). The findings:

| What | Scale |
|------|-------|
| Source files that could move as complete units | 12 files, 6,943 LOC |
| Methods misplaced inside `handlers.py` | ~1,342 LOC across 46+ methods |
| Binary assets (shapefiles, header images) | 57 MB |
| Dependencies removable from pipeline-core | 8 packages (~510 MB certain, up to ~2.5 GB with torch) |
| Dead dependencies (zero import sites) | 1 (`properscoring`) |
| Internal consumers of `DatasetTransformationModule` | 0 |

The investigation also produced a complete dependency partition table
classifying every dependency as "stays" (orchestration), "moves" (misplaced),
or "dead" (unused).

---

## The Decision

Extract all visualization, reporting, statistics, mapping, and transformation
code to a new **`views-reporting`** package. Sibling repository at the same
level as `views-evaluation`, `views-baseline`, and `views-stepshifter`.
Independent git history, independent versioning.

The guiding principle was **WET-before-DRY**: move the code as exact copies
first, refactor later. No simultaneous move-and-refactor. The extraction had
to be safe and reversible at every step.

### What moved

```
views_reporting/
├── statistics/          # PosteriorDistributionAnalyzer, ForecastReconciler
├── visualizations/      # HistoricalLineGraph, PlotDistribution
├── mapping/             # MappingModule + 57 MB of shapefiles
├── reports/             # ReportModule, Tailwind CSS, utilities
├── templates/reports/   # EvaluationReportTemplate, ForecastReportTemplate
├── transformations/     # DatasetTransformationModule (zero consumers in pipeline-core)
├── reconciliation/      # ReconciliationModule, dataset export
├── metadata/            # 30 entity metadata functions extracted from handlers.py
└── assets/              # Shapefiles (country, priogrid), header images
```

### What stayed in pipeline-core

- `AggregationModule` — consumed by ensemble managers for core ensemble
  operations, not an outer-layer concern
- `_ViewsDataset` core (~953 LOC after surgery) — constructors, indexing,
  tensor conversion, subsetting. The legitimate typed DataFrame wrapper.
- `ReportingStage` — orchestration stage that imports report templates
- All managers, stages, dataloaders, prediction stores

---

## How It Was Done

### The Strangler Fig pattern

Following the precedent set by ADR-045 (Pipeline Stage Architecture), the
extraction used a Strangler Fig approach:

1. **Copy code** to views-reporting as exact duplicates
2. **Leave re-export shims** in pipeline-core's `__init__.py` files:
   ```python
   try:
       from views_reporting.statistics import PosteriorDistributionAnalyzer
   except ImportError as e:
       raise ImportError(
           "PosteriorDistributionAnalyzer has moved to views-reporting. "
           "Install: pip install views-reporting"
       ) from e
   ```
3. **Downstream repos** update imports over one release cycle
4. **Remove shims** once all consumers have migrated

The shims fail loudly with install instructions. No silent degradation.

### The PR sequence

The extraction was executed as 11 sequential, independently mergeable PRs.
Each PR left the pipeline fully functional. The sequence was ordered by
risk — low-risk, self-contained modules first, the god class surgery last.

| PR | Scope | LOC | Risk |
|----|-------|-----|------|
| 0 | Package skeleton + ADR-054 | 0 | None |
| 1 | `transformations/` (zero internal consumers) | 1,431 | None |
| 2 | `statistics/` (PDA, ForecastReconciler) | 769 | Low |
| 3 | `visualizations/` (HistoricalLineGraph, PlotDistribution) | 737 | Low |
| 4 | `mapping/` + 57 MB of shapefiles | 868 | Low |
| 5 | `reports/` (ReportModule, Tailwind, utils) | 1,388 | Low |
| 6 | `templates/reports/` | 541 | Medium |
| 7 | `reconciliation/` (ReconciliationModule) | 298 | Medium |
| 8 | **God class surgery on `handlers.py`** | ~1,342 | **High** |
| 9 | Dependency cleanup (pyproject.toml) | 0 | Low |
| 10 | Documentation close-out | 0 | None |

PR 8 was the hardest — extracting ~1,342 LOC of methods from a 2,295-line
class with 85 methods. It removed 14 statistical functions, 2 visualization
functions, 2 reconciliation-export functions, and 30 entity metadata
functions. After surgery, `handlers.py` went from 2,294 LOC to 946 LOC.
The top-level imports of torch, matplotlib, scipy, joblib, and viewser
were removed from `handlers.py` entirely.

### Dependency direction

`views-reporting` depends on `views-pipeline-core` (it needs `_ViewsDataset`,
`CMDataset`, `PGMDataset` as input types). Pipeline-core **never** depends on
views-reporting. The re-export shims use `try/except ImportError` — they
provide a helpful error message but do not add views-reporting as an install
dependency.

---

## What It Achieved

### Dependencies removed from pipeline-core

| Package | Size | Why it was there |
|---------|------|-----------------|
| `scipy` | ~150 MB | PosteriorDistributionAnalyzer |
| `geopandas` | ~200 MB | MappingModule |
| `plotly` + `plotly-express` | ~50 MB | HistoricalLineGraph, MappingModule |
| `matplotlib` | ~80 MB | Distribution plots, handlers.py top-level |
| `seaborn` | ~20 MB | Distribution plots |
| `markdown` | ~5 MB | ReportModule |
| `joblib` | ~5 MB | MAP parallelization in handlers.py |
| `properscoring` | ~1 MB | Dead — zero import sites |
| **Total certain** | **~510 MB** | |
| `torch` (conditional) | ~2 GB | Moved with reconciliation; may leave pipeline-core |

### God class reduced

`_ViewsDataset`: 2,295 LOC → 946 LOC. From 85 methods to a focused data
container with constructors, indexing, tensor conversion, and subsetting.

### `handlers.py` import tax eliminated

Importing `CMDataset` no longer triggers loading of scipy, matplotlib,
joblib, or torch. The ~2.5 GB transitive dependency tax is gone for the 4
consumer modules that never used those methods.

### Scale problems addressable

C-105 (scale-aware eval report graphs) and C-106 (PGM scale guard) are
now fixable in views-reporting, which has proper rendering infrastructure
as an outer-layer package.

### Independent testing

Each module is testable in views-reporting without pipeline infrastructure.
The repo has 108 passing tests in its base environment (161 with full
pipeline-core installed).

---

## Current State

views-reporting is operationally complete with:

- 9 subpackages across a four-layer architecture (ADR-002)
- 12 Architecture Decision Records (ADR-000 through ADR-011)
- 10 Class Intent Contracts covering all non-trivial classes
- A technical risk register with 21 resolved concerns and 0 open
- CI via GitHub Actions (ruff + pytest)
- 108–161 tests depending on environment

The re-export shims in pipeline-core remain active. They will be removed
once all downstream repos (`views-models`, `views-hydranet`, `views-baseline`)
have updated their imports to the `views_reporting.*` paths.

---

## References

- **ADR-054** — `views-pipeline-core/documentation/ADRs/054_visualization_and_reporting_extraction.md`
- **Investigation** — `views-pipeline-core/reports/views_reporting_extraction/architectural_misplacement_investigation.md`
- **PR plans** — `views-pipeline-core/reports/views_reporting_extraction/extraction_pr_plans.md`
- **Pipeline-core PRs** — #91 through #101
- **ADR-045** — Pipeline Stage Architecture (established the Strangler Fig pattern)
