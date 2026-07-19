# ADR-017: Canonical Evaluation-Report Metrics Owned by views-reporting

**Status:** Accepted
**Date:** 2026-06-06
**Deciders:** Simon, VIEWS platform team
**Related:** ADR-016 (configuration mechanism), ADR-003 (authority of declarations over inference), ADR-002 (topology), ADR-008 (observability & explicit failure)

---

## Context

The evaluation report decided **which metrics to show** by merging seven metric-list keys from the **model's own config** (authored by developers in views-models) and rendering whatever the WandB run happened to contain (`evaluation.py` `_add_report_content`). Two problems:

1. **Wrong authority.** Evaluation reports are a higher-authority artifact. There is a *canonical* set of metrics that **should** appear in a report, and that standard ought to be owned and reviewed by the people accountable for evaluation — not chosen per-model by whoever wrote the model. A developer is free to compute whatever metrics they like for development/training; that should not silently determine the official report.
2. **Silent omission.** If a metric wasn't in the run, the table simply lacked it — a reader couldn't tell whether it was *not part of the standard* or *not calculated*.

The canonical set depends on a taxonomy of **{regression, classification} × {point, sample}**, and a single model can occupy **any subset** of those four cells (e.g. regression-sample *and* classification-sample at once).

## Decision

The **canonical evaluation-report metric standard is owned centrally by views-reporting**, in the configuration primitive from ADR-016:

1. **Central standard.** `ReportingConfig.canonical_report_metrics` (`views_reporting/config/_reporting.py`) is an immutable map `{(task, pred_type): (metric names…)}` covering all four cells. It ships in the wheel, is type-checked, and is the one place the reporting authority edits to change what reports show.
2. **Cell occupancy is declared, not inferred (ADR-003).** A model occupies a cell when its corresponding config key — `regression_point_metrics`, `regression_sample_metrics`, `classification_point_metrics`, `classification_sample_metrics` — is **present and non-empty**. This is how the report knows task and point/sample without loading predictions or adding a field.
3. **Render canonical, per active cell.** For each active cell the report renders a labelled table of the **canonical** metrics (not the model's list), pulling values from the injected `MetricFrame` via the `EvaluationSource` port (originally the WandB run; inverted by C-108/B2, 2026-06-27). A model with several active cells gets several tables.
4. **Honest about gaps (ADR-008).** A canonical metric the run lacks is shown with an explicit note — *"not calculated — add `<metric>` to `<task>_<pred_type>_metrics`"* — naming the exact config key to enable it. No silent drop.
5. **Per-model lists stay in views-models** for development/training, and remain what makes the evaluator compute a metric in the first place — so "not calculated → enable it in your model config" is the correct, actionable nudge.

**In scope:** which metrics the report shows, cell occupancy, and missing-metric honesty. **Out of scope:** the evaluation scope (`eval_types`, still time-series-wise), the `mean`-only aggregation, the sort order, and a clickable link to the views-models config (we name the key in text instead).

## Rationale

- **Right authority, reviewably.** The reporting standard lives in one isolated, named structure the eval authority owns; a PR touching it is unambiguously "changing the reporting standard."
- **Declared, not inferred (ADR-003).** Occupancy comes from explicit config keys, not from sniffing predictions or run side-effects.
- **Honest (ADR-008).** Missing canonical metrics are surfaced, not hidden — the same principle as the C-40 fix.
- **Reuses an existing pattern.** `views_evaluation.native_evaluator._resolve_task_and_metrics` already selects `config[f"{task}_{pred_type}_metrics"]`; this mirrors that selection on the report side.
- **Consistent with ADR-016.** Keeps configuration as an in-package Python primitive rather than introducing a parallel file format.

## Considered Alternatives

### A. Keep per-model metric lists driving the report (status quo)
- **Rejected.** Puts report content under developer authority and drops anything not present, silently.

### B. Show every metric the run produced (run-driven)
- **Rejected.** Complete but uncurated and noisy; no enforceable standard.

### C. A dedicated YAML/TOML standard file
- **Pros:** arguably most reviewable by non-developers. **Cons:** introduces a second config format against ADR-016. **Rejected for now** — revisit if non-dev review of the standard becomes a hard requirement.

### D. Define the canonical sets in pipeline-core (shared)
- **Rejected (for now).** Heavier cross-repo change; the *report* standard belongs with the reporting repo. Could be promoted later if other consumers need it.

## Consequences

### Positive
- A single, central, reviewable, shipped reporting standard; multi-cell models handled; missing metrics are explicit and actionable.

### Negative / accepted
- **Canonical names must track the evaluator's emitted metric tokens** — drift makes a canonical metric read "not calculated" forever. Tracked in the risk register (C-41).
- The seeded canonical lists are **placeholders pending eval-authority sign-off**; they are trivially editable in `ReportingConfig` (that reviewability is the point).
- Two metric configs now coexist (per-model dev lists in views-models vs the central report standard) — intentional and documented.

## Implementation Notes
- `ReportingConfig.canonical_report_metrics` (+ `canonical_metrics(task, pred_type)` accessor), validated in `__post_init__` (all four cells; non-empty names).
- `EvaluationReportTemplate._add_report_content` resolves active cells from the four config keys and renders one canonical table per cell, value-or-note. The old seven-key `metrics` merge is removed.
- Read at the Compose layer via `get_config()` (ADR-016 / ADR-002).

## Validation & Monitoring
- e2e tests (`tests/test_e2e_eval_report.py`) assert per-cell tables, canonical metric rendering, and the "not calculated" note (naming the key); `tests/test_config.py` covers the map + validation.
- `scripts/generate_demo_eval_reports.py` renders a full offline report for visual review.
- **Drift signal:** a metric believed computed showing "not calculated" indicates a name mismatch between the canonical map and the evaluator's tokens (C-41).

## Open Questions
- The **actual** canonical metric lists per cell (current values are placeholders for sign-off).
- Whether to later open up `eval_types` / aggregation / sort, or move the standard to a data file (Alternative C) if non-dev review demands.

## References
- `views_reporting/config/_reporting.py` (`canonical_report_metrics`); `views_reporting/templates/reports/evaluation.py` (`_add_report_content`).
- `views_evaluation.native_evaluator._resolve_task_and_metrics` (the selection pattern mirrored here).
- ADR-016 (config primitive), ADR-003 (declarations over inference), ADR-008 (explicit failure); risk register C-41, C-42.
- **Source of the seeded lists:** the ensemble-governance protocol **ADR-029** (regression point/probabilistic decision metrics) reconciled with `views_evaluation`'s `metric_catalog.py` (`METRIC_CATALOG` / `METRIC_MEMBERSHIP`) for exact tokens. Diversity (`SD`) is omitted while `implemented=False` upstream; classification cells use the full implemented membership.
