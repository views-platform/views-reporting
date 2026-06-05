# ADR-016: Repository Configuration Mechanism — In-Package Defaults, Injected at the Compose Boundary

**Status:** Accepted
**Date:** 2026-06-05
**Deciders:** Simon, VIEWS platform team
**Related:** ADR-002 (topology/layers), ADR-003 (authority of declarations over inference), ADR-008 (observability & explicit failure)

---

## Context

views-reporting had **no configuration primitive of its own**. The only "configuration" in the codebase is the per-run `dict` the caller (pipeline-core) threads into the report templates (`config["targets"]`, `config["level"]`, …) — that describes *what to report for this run*. There was nowhere to declare views-reporting's *own* rendering defaults.

As a result, rendering defaults lived hardcoded deep in plotting code — e.g. the HDI credible level `alpha=0.9` is repeated at `templates/reports/forecast.py` and `evaluation.py` and throughout `statistics/` and `visualizations/`, invisible and un-tunable. The immediate trigger is the work to make the HDI level **visible and selectable** (issues #87–#91): the three levels `(0.9, 0.95, 0.99)` must be declared in **one place**, not buried in a script.

This decision is needed *now*, before that feature builds on it, so the first config primitive is governed rather than improvised. It must respect two constitutional ADRs: **ADR-002** (lower layers must not depend on higher ones) and **ADR-003** (semantics are explicitly declared and fail loud, never inferred). It must also keep working for a **pip-installed** user — the package is now published, so defaults have to ship in the wheel.

## Decision

Adopt an **in-package, Python-module configuration primitive** at `views_reporting/config/`:

1. **Form.** A `frozen` dataclass `ReportingConfig` plus a `get_config()` accessor (`views_reporting/config/`). It is *code that holds data*, deliberately isolated in its own package — **not** a YAML/TOML file and **not** constants scattered through plotting modules.
2. **Purpose.** It holds views-reporting's **own rendering defaults**. This is distinct from, and does not replace, the caller's per-run `config` dict — the two are separate concepts (package defaults vs. per-run instructions) and must stay distinct.
3. **Consumption pattern (the load-bearing rule).** Configuration is **read at the Compose boundary** (`templates/reports/`) and **injected downward as explicit parameters** into the Render layer (`visualizations/`, `mapping/`). Lower layers (Render, Compute) **must not** call `get_config()` themselves. This honours ADR-002: the highest layer that needs a value reads it and passes it down; nothing lower reaches up. It also matches the pattern already in place — `alpha` is already a *parameter* of `plot_predictions_vs_historical`, passed from the Compose layer.
4. **Fail-loud (ADR-003/008).** `ReportingConfig` validates at construction and raises on incoherent values (e.g. an HDI level outside `(0, 1)`, or a default not in the level set). No silent fallback, no inference.
5. **Seed.** It seeds the HDI credible levels (`hdi_levels`, `default_hdi_level`). Other hardcoded values (figure heights, colours, colormap, opacities, map quantiles) are *candidates* to migrate here later.

**In scope:** the configuration primitive, its consumption rule, and the HDI-level defaults. **Out of scope (for now):** letting the caller's per-run `dict` override these defaults (a later precedence layer), migrating the other magic values, and any file-based (YAML/TOML) configuration.

## Rationale

- **Zero new dependency, guaranteed available.** A Python module needs no parser; on this 3.11-only repo there is nothing to install. A YAML file would pull in/rely on PyYAML; a TOML file would need a reader. Fewer moving parts at the core of the render path.
- **Type-safe and fail-loud by construction.** A dataclass with validation gives ADR-003 compliance for free and catches mistakes at import/construction, not deep in a plot.
- **Ships in the wheel.** Living inside `views_reporting/` means `pip install views-reporting` users get the defaults out of the box; a repo-root `config/` would not ship.
- **Testable without globals.** Because values are *injected* (not read from a global inside Render), the visualization functions stay pure and can be unit-tested by passing levels directly — no monkeypatching of global state.
- **Consistent with what exists.** `alpha` is already a parameter threaded from Compose; this formalises where its default comes from rather than inventing a new flow.
- **Stops the mess at the source.** One declared home for rendering defaults is the antidote to the same constant being hardcoded in many files.

## Considered Alternatives

### Alternative A: YAML or TOML config file
- **Pros:** friendliest to hand-edit; YAML is the lingua franca of the wider pipeline; TOML matches `pyproject.toml`.
- **Cons:** needs a reader (PyYAML dep, or stdlib `tomllib` read-only); a data file in the wheel adds packaging/asset-loading surface; harder to validate/type than a dataclass.
- **Reason for rejection:** the dependency/asset cost is not justified for a small set of defaults; revisit if non-developers need to edit config without a release.

### Alternative B: Repository-root `config/` directory
- **Cons:** would not be included in the wheel, so a pip-installed user gets no defaults and the code must hardcode a fallback anyway — defeating the purpose.
- **Reason for rejection:** wrong home for *distributed* library defaults.

### Alternative C: Keep constants scattered / status quo
- **Cons:** this *is* the problem — the same value hardcoded across files, invisible and un-tunable.
- **Reason for rejection:** it is the mess this ADR exists to end.

### Alternative D: A global `get_config()` read directly inside the Render layer
- **Cons:** Render (Layer 4) reaching into a config authority and depending on global state violates ADR-002's injection direction and makes the render functions harder to test.
- **Reason for rejection:** breaks layering and testability. Config is read at Compose and injected.

## Consequences

### Positive
- A single, declared, **shipped** source of truth for rendering defaults; the HDI levels live in one editable place.
- Render layer stays pure and injection-tested; ADR-002/003 upheld.
- A clear template for migrating other magic values later, without re-litigating the mechanism.

### Negative
- It is **code, not a data file**: changing a default means a code edit and (for downstream users) a release — accepted, since these are developer-owned rendering defaults, not operator knobs.
- There are now **two configuration concepts** (the caller's per-run `dict` and the package defaults). They must be kept conceptually separate; a future ADR will define precedence if/when caller-override is added.

## Implementation Notes

- The package exists: `views_reporting/config/__init__.py` (re-exports `ReportingConfig`, `get_config`) and `views_reporting/config/_reporting.py` (the dataclass, validation, and the `get_config()` accessor).
- Enforcement points: the Compose call sites (`templates/reports/forecast.py`, `templates/reports/evaluation.py`) read `get_config()` and pass values into `plot_predictions_vs_historical(...)` (issue #88 onward).
- **Guardrail:** `views_reporting/visualizations/` and `views_reporting/mapping/` must **not** import `views_reporting.config`. Treat such an import as an ADR-002 violation in review.
- No migration of other constants is required by this ADR; they may move incrementally under their own changes.

## Validation & Monitoring

- **Invariant tests:** `tests/test_config.py` covers defaults, immutability, and fail-loud validation.
- **Layering invariant:** no module under `visualizations/` or `mapping/` imports `views_reporting.config` (grep-able guardrail; candidate for an automated check).
- **Exercise:** the HDI-levels feature (#88–#91) consumes config via injection end-to-end; if a value ever has to be read globally inside Render to make something work, that is the signal this pattern needs revisiting.

## Open Questions

- **Caller override precedence.** Should the pipeline-core per-run `dict` be able to override package defaults, and with what precedence? Deferred to a later ADR.
- **File-based config later.** If operators (not developers) ever need to tune defaults without a release, revisit Alternative A (likely TOML via stdlib `tomllib`).
- **Scope of migration.** Which other hardcoded values (heights, colours, colormap, map quantiles) are worth centralising, and when?

## References
- Issues #87–#91 (config-driven, legend-selectable HDI levels).
- `views_reporting/config/` (`_reporting.py`, `__init__.py`); `tests/test_config.py`.
- ADR-002 (topology/layers), ADR-003 (authority of declarations), ADR-008 (observability & explicit failure).
- Hardcoded `alpha=0.9` sites this supersedes as the source of truth: `templates/reports/forecast.py`, `templates/reports/evaluation.py`, `statistics/dataset_statistics.py`, `visualizations/`.
