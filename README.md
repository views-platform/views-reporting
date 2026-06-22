<div style="width: 100%; max-width: 1500px; height: 400px; overflow: hidden; position: relative;">
  <img src="https://github.com/user-attachments/assets/1ec9e217-508d-4b10-a41a-08dface269c7" alt="VIEWS Twitter Header" style="position: absolute; top: -50px; width: 100%; height: auto;">
</div>

# **VIEWS Reporting**: Visualization, Statistics & Mapping

> **Part of the [VIEWS Platform](https://github.com/views-platform) ecosystem for large-scale conflict forecasting.**

---

## Table of Contents

1. [Overview](#overview)
2. [Role in the VIEWS Pipeline](#role-in-the-views-pipeline)
3. [Architecture](#architecture)
4. [Features](#features)
5. [Installation](#installation)
6. [Running Tests](#running-tests)
7. [Project Structure](#project-structure)
8. [Governance](#governance)
9. [Contributing](#contributing)
10. [Acknowledgements](#acknowledgements)

---

## Overview

**VIEWS Reporting** provides the visualization, statistical analysis, reconciliation, and report generation layer for the VIEWS conflict forecasting pipeline. It produces HTML evaluation reports, interactive choropleth maps, posterior distribution analyses, and hierarchical forecast reconciliation.

All incoming data is expected on its **original measurement scale** -- this library does not infer or reverse mathematical transformations from column names (ADR-011, Architecture Decision Record).

**Key Capabilities**:
- **Bayesian posterior analysis** -- MAP (Maximum A Posteriori) estimation, HDI (Highest Density Interval) computation, and credible interval reporting
- **Hierarchical forecast reconciliation** -- proportional scaling to ensure country-grid consistency
- **HTML report generation** -- Tailwind CSS-styled evaluation and forecast reports with XSS-safe content
- **Interactive mapping** -- choropleth maps at country and [PRIO-GRID](https://grid.prio.org/) (Peace Research Institute Oslo grid) resolution via GeoPandas and Mapclassify

---

## Role in the VIEWS Pipeline

**VIEWS Reporting** sits at the output end of the forecasting pipeline, consuming model predictions and producing human-readable reports, maps, and statistical summaries.

### Integration with Other Repositories

- **[views-pipeline-core](https://github.com/views-platform/views-pipeline-core):** Pipeline infrastructure -- provides orchestration, configuration, and the queryset/partition framework that reporting consumes.
- **[views-models](https://github.com/views-platform/views-models):** Model outputs -- predictions and posterior samples evaluated and visualized by this library.
- **[views-evaluation](https://github.com/views-platform/views-evaluation):** Evaluation metrics -- scoring and calibration results displayed in evaluation reports.
- **[views-stepshifter](https://github.com/views-platform/views-stepshifter):** Stepshift model predictions consumed for reconciliation and visualization.
- **[docs](https://github.com/views-platform/docs):** Organization/pipeline level documentation.

### Integration Workflow

1. **Data Input:** Receives evaluated predictions and posterior samples from the pipeline.
2. **Analysis:** Computes MAP estimates, HDI intervals, and reconciles hierarchical forecasts.
3. **Output:** Generates HTML reports, distribution plots, historical line graphs, and choropleth maps.

---

## Architecture

The repository follows a five-layer dependency model (ADR-002):

| Layer | Package | Purpose |
|-------|---------|---------|
| **Ingestion** | `loaders` | Declared-format prediction loaders (parquet / numpy PredictionFrame) → datasets (ADR-012) |
| **Compute** | `statistics` | Bayesian posterior analysis (MAP, HDI), forecast reconciliation |
| **Compute** | `reconciliation` | Hierarchical country-grid forecast reconciliation |
| **Compute** | `metadata` | Entity metadata accessors via [viewser](https://github.com/prio-data/viewser) (30 functions) |
| **Render** | `visualizations` | Distribution plots, historical line graphs |
| **Render** | `mapping` | Interactive/static choropleth maps |
| **Compose** | `reports` | HTML report builder with Tailwind CSS |
| **Compose** | `templates` | EvaluationReportTemplate, ForecastReportTemplate |
| **Assets** | `assets` | Shapefiles (country, priogrid), header images |

Data flows upward: ingestion -> compute -> render -> compose. No downward dependencies (ADR-002).

---

## Features

- **Posterior Distribution Analysis:** MAP via histogram density peak, HDI via shortest-interval on sorted samples, configurable credible masses and zero-mass thresholds.
- **Forecast Reconciliation:** Proportional scaling that preserves zeros, clamps non-negative, and ensures country totals match grid sums. Parallel execution via ProcessPoolExecutor.
- **HTML Reports:** Content accumulation API (headings, paragraphs, tables, images, footers) with `html.escape()` on all user-facing text. Tailwind CSS styling. Export to standalone HTML files.
- **Choropleth Mapping:** Country and PRIO-GRID level maps with bundled shapefiles, configurable classification schemes, and interactive Folium output.
- **Historical Line Graphs:** Plotly-based time series with HDI bands, forecast cutoff markers, and entity dropdown navigation.
- **Distribution Plots:** HDI and MAP overlays on posterior sample histograms.

---

## Installation

### Prerequisites

- **Python 3.11** — 3.12+ is not yet supported: an upstream transitive dependency
  (`views-pipeline-core → ingester3 → levenshtein`) has no 3.12/3.13 build. See
  ADR-014 and risk register C-36. The package is resolved for Linux and macOS.
- [uv](https://docs.astral.sh/uv/) for development (hatchling + uv per ADR-014).

### Steps

For development (recommended):

```bash
git clone https://github.com/views-platform/views-reporting
cd views-reporting
uv sync          # creates .venv from uv.lock
```

Or install the published package into an existing environment:

```bash
pip install views-reporting
```

See the organization/pipeline level [docs](https://github.com/views-platform/docs) for full environment setup.

---

## Running Tests

```bash
uv run pytest tests/ -q                 # full suite
uv run pytest tests/ -q -m "not slow"   # skip slow integration tests
```

Fixture-dependent tests skip automatically when their data is absent.

---

## Project Structure

```plaintext
views-reporting/
├── README.md                   # Documentation
├── tests/                      # 85–161 tests depending on environment
├── views_reporting/            # Main source code
│   ├── assets/                 # Shapefiles and header images
│   ├── mapping/                # Choropleth map generation
│   ├── metadata/               # Entity metadata accessors
│   ├── reconciliation/         # Hierarchical forecast reconciliation
│   ├── reports/                # HTML report builder + Tailwind CSS
│   ├── statistics/             # Posterior analysis (MAP, HDI)
│   ├── templates/              # Report templates (evaluation, forecast)
│   ├── visualizations/         # Distribution and historical plots
│   └── __init__.py             # Package initialization
├── documentation/
│   ├── ADRs/                   # 18 Architecture Decision Records
│   ├── CICs/                   # 13 Class Intent Contracts
│   └── guides/                 # Operational runbooks (e.g. publishing to PyPI)
├── reports/                    # Technical risk register
├── .github/workflows/          # CI configuration
└── pyproject.toml              # Project metadata (PEP 621) + hatchling/uv
```

---

## Governance

This repository uses structured governance documented in `documentation/`:

- **18 ADRs** (000-017) -- architectural decisions, from foundational principles to data ingestion, build tooling, release automation, configuration, and evaluation-report standards
- **13 CICs** -- intent contracts covering every non-trivial class plus the full Ingestion-layer loader surface (ADR-006)
- **Risk register** -- `reports/technical_risk_register.md` (ADR-010)
- **Testing doctrine** -- red/green/beige team taxonomy (ADR-005)
- **Guides** -- operational runbooks in `documentation/guides/` (e.g. [publishing to PyPI](documentation/guides/publishing-to-pypi.md))

Start with `documentation/ADRs/README.md` for the governance map.

| ADR | Title | Impact |
|-----|-------|--------|
| ADR-002 | Topology and dependency rules | Four-layer architecture, no downward deps |
| ADR-003 | Authority of declarations over inference | Fail-loud, no semantic inference |
| ADR-005 | Testing as mandatory critical infrastructure | Red/green/beige test categories |
| ADR-011 | Data arrives on original measurement scale | No transform detection from column names |

---

## Contributing

We welcome contributions! Please follow the contribution guidelines outlined in the [VIEWS Documentation](https://github.com/views-platform/docs). See also `documentation/contributor_protocols/` for repo-specific protocols.

All contributions must comply with the constitutional ADRs in `documentation/ADRs/`, including:

- **ADR-003** -- Explicit declarations over inference; fail loud on semantic ambiguity
- **ADR-005** -- Testing is mandatory (red / beige / green taxonomy)
- **ADR-006** -- Non-trivial classes require intent contracts
- **ADR-007** -- Silicon-based agents are untrusted contributors

---

## Acknowledgements

<p align="center">
  <img src="https://raw.githubusercontent.com/views-platform/docs/main/images/views_funders.png" alt="Views Funders" width="80%">
</p>

Special thanks to the **VIEWS MD&D Team** for their collaboration and support.
