# views-reporting

Visualization, reporting, statistics, and mapping for the [VIEWS conflict forecasting platform](https://viewsforecasting.org). Extracted from [views-pipeline-core](https://github.com/views-platform/views-pipeline-core) per ADR-054.

## Installation

```bash
pip install -e /path/to/views-reporting
```

Or with Poetry:

```bash
cd views-reporting
poetry install
```

## Running tests

```bash
# Base environment (84 pass, 7 skip without views_pipeline_core)
pytest tests/ -v

# Full environment (158 pass, requires views_pipeline_core + viewser)
conda run -n views_pipeline pytest tests/ -v

# Fast run (skip slow integration tests)
pytest tests/ -v -m "not slow"
```

## Architecture

views-reporting is organized into 9 subpackages following a four-layer dependency model (ADR-002):

| Layer | Package | Purpose |
|-------|---------|---------|
| **Compute** | `statistics` | Bayesian posterior analysis (MAP, HDI), forecast reconciliation |
| **Compute** | `transformations` | Log transform lifecycle (legacy per ADR-011) |
| **Compute** | `reconciliation` | Hierarchical country↔grid forecast reconciliation |
| **Compute** | `metadata` | Entity metadata accessors via viewser (30 functions) |
| **Render** | `visualizations` | Distribution plots, historical line graphs |
| **Render** | `mapping` | Interactive/static choropleth maps |
| **Compose** | `reports` | HTML report builder with Tailwind CSS |
| **Compose** | `templates` | EvaluationReportTemplate, ForecastReportTemplate |
| **Assets** | `assets` | Shapefiles (country, priogrid), header images |

Data flows upward: compute → render → compose. No downward dependencies (ADR-002).

All incoming data is expected on its **original measurement scale** — this library does not infer or reverse mathematical transformations from column names (ADR-011).

## Governance

This repository uses structured governance documented in `documentation/`:

- **12 ADRs** (000-011) — architectural decisions, from foundational principles to data scale contracts
- **10 CICs** — intent contracts for every non-trivial class (ADR-006)
- **Risk register** — `reports/technical_risk_register.md` (ADR-010)
- **Testing doctrine** — red/green/beige team taxonomy (ADR-005)

Start with `documentation/ADRs/README.md` for the governance map.

## Key ADRs

| ADR | Title | Impact |
|-----|-------|--------|
| ADR-002 | Topology and dependency rules | Four-layer architecture, no downward deps |
| ADR-003 | Authority of declarations over inference | Fail-loud, no semantic inference |
| ADR-005 | Testing as mandatory critical infrastructure | Red/green/beige test categories |
| ADR-011 | Data arrives on original measurement scale | No transform detection from column names |

## Contributing

See `documentation/contributor_protocols/` for guidelines. AI-assisted contributions follow ADR-007 (silicon-based agents as untrusted contributors).
