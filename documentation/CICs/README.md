# Class Intent Contracts README

This directory contains **Intent Contracts** as defined in ADR-006.

An Intent Contract is a human-readable, unambiguous declaration of:

- what a non-trivial class is meant to do,
- what it must never do,
- its invariants,
- and its failure semantics.

Intent Contracts are architectural artifacts.
They are not implementation documentation.

---

## When Is an Intent Contract Required?

An Intent Contract is mandatory for:

- Core domain classes
- Architectural boundary classes
- Orchestration components
- State-owning components
- Classes that enforce invariants
- Classes that modify semantics or transformation

Trivial value objects and pure utility functions do not require one.

---

## Structure of an Intent Contract

Each contract must define:

1. Purpose
2. Responsibility Boundary
3. Invariants
4. Explicit Non-Responsibilities
5. Failure Semantics
6. Observable Effects (if applicable)

Contracts must be clear enough that:

- Tests (ADR-005) can be derived from them.
- Architectural violations can be detected.
- Silicon-based agents cannot reinterpret intent (ADR-007).

---

## Active Contracts

| CIC File | Class | Source File |
|---|---|---|
| [`cic_posterior_distribution_analyzer.md`](cic_posterior_distribution_analyzer.md) | `PosteriorDistributionAnalyzer` | `views_reporting/statistics/statistics.py` |
| [`cic_forecast_reconciler.md`](cic_forecast_reconciler.md) | `ForecastReconciler` | `views_reporting/statistics/statistics.py` |
| [`cic_dataset_transformation_module.md`](cic_dataset_transformation_module.md) | `DatasetTransformationModule` | `views_reporting/transformations/transformations.py` |
| [`cic_plot_distribution.md`](cic_plot_distribution.md) | `PlotDistribution` | `views_reporting/visualizations/distributions.py` |
| [`cic_mapping_module.md`](cic_mapping_module.md) | `MappingModule` | `views_reporting/mapping/mapping.py` |
| [`cic_historical_line_graph.md`](cic_historical_line_graph.md) | `HistoricalLineGraph` | `views_reporting/visualizations/historical.py` |
| [`cic_report_module.md`](cic_report_module.md) | `ReportModule` | `views_reporting/reports/report.py` |
| [`cic_reconciliation_module.md`](cic_reconciliation_module.md) | `ReconciliationModule` | `views_reporting/reconciliation/reconciliation.py` |

---

## Governance Relationship

Intent Contracts are governed by:

- ADR-006 (Intent Contracts for Non-Trivial Classes)
- ADR-003 (Authority of Declarations)
- ADR-005 (Testing Doctrine)

If a class changes meaning, its Intent Contract must be updated.
