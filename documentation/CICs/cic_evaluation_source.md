
# Class Intent Contract: EvaluationSource Port & Adapters

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-26
**Related ADRs:** ADR-001/002 (Ontology/Topology — Ingestion is Layer 2), ADR-006 (Intent Contracts), ADR-008 (Observability — fail loud), ADR-012 (the injected-adapter pattern, extended from predictions to metrics), ADR-018 (Render From Given Data — the mandate this fulfils), views-frames ADR-020 (the MetricFrame type-home)

---

> **Scope note.** Covers the `EvaluationSource` *interface* (`typing.Protocol`), its concrete adapters (`MetricFrameFileSource` — durable; `WandbEvaluationSource` — interim, deleted in B2), the `EvaluationProvenance` value object, and the pure value queries (`mean_metric_value`, `unique_axis_value`, `AmbiguousMetric`). This is the evaluation-side counterpart of the prediction `loaders/` Ingestion surface (C-108 / #173).

Sources: `views_reporting/sources/_protocol.py`, `metric_frame_file_source.py`, `wandb_evaluation_source.py`, `evaluation_provenance.py`, `metric_value.py`, `__init__.py`.

---

## 1. Purpose

> Supply the evaluation report with the evaluation-of-record — a typed `MetricFrame` per model — that it *renders*, so it never *acquires* its own metrics at render time (ADR-018).

`EvaluationReportTemplate` depends on the `EvaluationSource` interface, not on where the metrics come from (a persisted frame, or — transitionally — a WandB scrape). This inverts the render-time WandB dependency that was the root of Cluster A (C-48/C-108).

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** score or compute metrics — scoring stays in views-evaluation (ADR-018).
- Does **not** render — it returns data; the template renders.
- There is **no registry** (unlike `loaders/`): a source is *injected* by the caller (composition root), not dispatched by a format token in the data. A registry would abstract a dispatch that does not exist (WET-before-DRY).
- `MetricFrameFileSource` does **not** define the on-disk layout authoritatively — that is pinned jointly with pipeline-core's producer (#218); the current convention is **provisional**.

---

## 3. Responsibilities and Guarantees

- **Port (`EvaluationSource`, a `typing.Protocol`).** Provides `metric_frame(model: str) -> MetricFrame | None` and `provenance() -> EvaluationProvenance`. A source is bound to one `target` at construction (a report is per-target), so only `model` varies per call. The render code is statically checkable against the interface (LSP/ISP); a new source is a new class, not a change here (OCP). `views_evaluation` is imported only under `TYPE_CHECKING` in the port so it stays import-light (SDP/SAP).
- **Failure taxonomy (the #105/#177 contract).** `metric_frame` returns **`None` = absent** (no evaluation for this model → the report degrades-and-announces, never a silent drop); **raises = transient** (a retrieval hiccup → the report retries once, then marks the model degraded).
- **`MetricFrameFileSource` (durable).** `metric_frame(model)` loads the persisted frame for `(model, run_type, target)` or returns `None` when its directory is absent; a corrupt/unreadable frame propagates (transient). `provenance()` is read from the subject model's frame metadata (run_id / evaluation_timestamp / data_version / scoring_code_version; no WandB url/owner).
- **`WandbEvaluationSource` (INTERIM, deleted in B2 / #218).** Builds a `MetricFrame` from a WandB scrape — the primary model from the injected run, constituents via the metric-aware `evaluation_run_resolver` (absent → `None`; transient → raise). **Preserves C-116:** it emits *one row per matching summary key* (via `find_item_names`), so colliding keys become >1 mean row and surface as ambiguous downstream rather than a silently-picked number. `provenance()` carries the clickable WandB `run_url` + `owner` so the report keeps its WandB link during the interim.
- **Value query (`mean_metric_value`).** Reads the `group_id="mean"` row for `(eval_type, target, metric)`: `None` when absent or NaN ("not calculated"); raises `AmbiguousMetric` on >1 matching mean row (C-116; ADR-008); else the `float`.
- **Axis query (`unique_axis_value`).** The single distinct value of an axis (`level`/`partition`) across a frame, for the cross-constituent consistency guard; raises if the axis is non-uniform within a frame.
- **`EvaluationProvenance`.** A frozen presentation DTO (`run_id` + optional `run_url`/`owner`/`run_date`/`data_version`/`scoring_code_version`) rendered with None-omission, so each source supplies only what it knows.

---

## 4. Inputs and Assumptions

- Concrete sources are constructed bound to `(run_type, target, primary_model, …)`; `MetricFrameFileSource` also takes a `root` path, `WandbEvaluationSource` a `wandb_run` + `config` + `eval_types`.
- `views-evaluation[frames]` is a hard dependency (declared; the MetricFrame substrate). The port stays import-light; the adapters and queries import it at runtime.
- `MetricFrameFileSource` assumes pipeline-core persisted frames at the agreed (provisional) layout.

---

## 5. Outputs and Side Effects

- `metric_frame` → a `MetricFrame` or `None`. No mutation of global state. `MetricFrameFileSource` performs file I/O (read); `WandbEvaluationSource` performs the WandB read (interim).
- `provenance` → an `EvaluationProvenance`. Pure for the file source after load; reads the WandB run for the interim source.
- Value/axis queries are pure (no I/O).

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| No evaluation for a model | `metric_frame` returns `None` (absent → announced) | all sources |
| Retrieval hiccup | `metric_frame` raises (transient → retry-once-then-degrade) | adapters |
| >1 mean row matches a metric | `mean_metric_value` raises `AmbiguousMetric` → visible "ambiguous" cell | `metric_value` |
| Metric absent / NaN | `mean_metric_value` returns `None` → visible "not calculated" note | `metric_value` |
| Non-uniform axis within a frame | `unique_axis_value` raises `ValueError` | `metric_value` |
| Constituents disagree on level/partition | template raises `ValueError` (loud, never a mixed table) | `EvaluationReportTemplate._verify_frame_consistency` |
| WandB colliding keys | interim adapter emits both rows → ambiguity preserved (not deduped) | `WandbEvaluationSource._build_frame` |

Nothing is silently dropped or silently guessed.

---

## 7. Boundaries and Interactions

- **Depends on:** `views_evaluation.evaluation.metric_frame` (`MetricFrame`/`MEAN_GROUP_ID`/`AXES`); `views_reporting.config` (canonical metric universe, interim adapter only); `views_reporting.reports.utils.find_item_names` (interim adapter); `views_reporting.templates.reports.evaluation_run_resolver` (interim adapter only — deleted in B2).
- **Consumed by:** `EvaluationReportTemplate.generate` (injected) and `_add_report_content`.
- **Must not depend on:** rendering, scoring, or (for the durable file source) any data-acquisition service.

---

## 8. Examples of Correct Usage

```python
# Durable (pipeline-core #219 will do this):
source = MetricFrameFileSource(root, run_type="calibration", target="lr_ged_sb",
                               primary_model="first_love")
template.generate(source=source, target="lr_ged_sb")

# Interim (today): the template wraps a wandb_run automatically.
template.generate(wandb_run=run, target="lr_ged_sb")
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: inferring a value on ambiguity instead of surfacing it.
try:
    v = mean_metric_value(frame, eval_type=et, target=t, metric=m)
except AmbiguousMetric:
    v = frame.values[0, 0]  # silently picks a number — defeats C-116

# WRONG: deduping colliding keys when building a frame (hides the ambiguity).
# WRONG: adding a registry/format-token dispatch for sources (no such dispatch exists).
```

---

## 10. Test Alignment

- **green:** `tests/test_sources_metric_value.py` (present/absent/NaN/mean-only/ambiguous/empty; axis uniqueness), `tests/test_sources_metric_frame_file_source.py` (round-trip, absent dir, provenance fallback).
- **beige:** `tests/test_eval_report_from_source.py` (the inverted template via a `FakeEvaluationSource`: sections, canonical cells, "not calculated", absent/degraded announce, strict, level mismatch), and `tests/test_e2e_eval_report.py` (the interim wandb path through `WandbEvaluationSource`).
- **red:** the ambiguity, absent, transient, strict, and consistency-mismatch cases in `tests/test_eval_report_from_source.py` + `tests/test_falsify_sprint1_readiness.py`.

---

## 11. Evolution Notes

- **B2 / #218 / #219:** once pipeline-core persists frames and injects a `MetricFrameFileSource`, delete `WandbEvaluationSource` + `evaluation_run_resolver.py`, drop the `wandb_run` parameter on `generate`, and pin the on-disk convention. The clickable WandB link/owner then naturally fall away (the file source leaves them `None`).
- The cross-constituent consistency check moved onto frame axes (`level`/`partition`); when run-resolved partition windows are plumbed into the producer (#220), they sharpen.

---

## End of Contract
