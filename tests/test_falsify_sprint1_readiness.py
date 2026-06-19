"""Falsification stubs — Sprint-1 readiness audit (2026-06-19).

These encode the CORRECTED executable spec for the #116 interim metric-aware
run-selection, surfaced by falsifying the readiness claim "the Sprint-1 DoDs are
achievable as written against today's code". They are forward-looking: the #116
selection code does not exist yet, so each stub is xfail until #116 lands. When
#116 is implemented to the *corrected* DoD, flip these to passing.

Findings these guard against:
  - P3 (soft): the C-110/#116 DoD said "scope selection to (run_type, partition,
    window)". At evaluation.py:187 only `run_type` is an a-priori scope (it picks
    the wandb project `{model}_{run_type}`). partition/level are only knowable by
    inspecting each candidate run's .config AFTER fetch (L223-244); `window` is not
    a selection key at all. The implementable guard is: enumerate runs in the
    run_type-scoped project, pick the latest whose summary carries the canonical
    metric tokens AND whose partition/level metadata matches the other
    constituents; ambiguity among equally-valid metric-bearing runs -> degrade.
  - P8 (soft): the #116 DoD said "fixture-based regression". On-disk *.parquet
    fixtures are gitignored (.gitignore) and skip in CI (the C-46 trap). The
    regression MUST be built on the synthetic tests/_wandb_doubles.py double so it
    runs in CI with no on-disk fixture.
"""
import pytest

pytestmark = pytest.mark.xfail(
    reason="#116 metric-aware selection not yet implemented (Sprint-1 Story 1)",
    strict=False,
)


def test_metric_aware_selection_scoped_by_run_type_only():
    """P3: selection is scoped a-priori by run_type (the wandb project), NOT by a
    `window` key (which does not exist at evaluation.py:187). The latest run in the
    `{model}_{run_type}` project that carries the canonical metric tokens is chosen,
    even when it is not the most-recently-created run (the production 22/25 case).
    """
    raise AssertionError("implement #116: run_type-scoped, metric-aware run selection")


def test_partition_match_is_checked_post_fetch_not_as_selection_filter():
    """P3: partition/level is NOT an a-priori selection filter — it is read from each
    candidate run's .config and must match across constituents (the existing
    evaluation.py:223-244 check, now applied to the metric-aware-selected run, not to
    get_latest_run's newest run).
    """
    raise AssertionError("implement #116: apply partition/level consistency to the selected run")


def test_ambiguous_metric_bearing_runs_degrade_not_guess():
    """C-110: when >1 in-scope run carries the canonical set, the constituent is
    announced via the #105 degrade-and-announce path — never silently resolved to one
    (avoids trading a visible 'not calculated' for a silent wrong number).
    """
    raise AssertionError("implement #116: ambiguity -> degrade-and-announce")


def test_single_constituent_row_sourced_from_a_single_run():
    """C-110: a constituent's metric row is assembled from exactly one run — never
    mixed across runs (one row = one evaluation).
    """
    raise AssertionError("implement #116: no cross-run metric mixing")


def test_regression_uses_synthetic_wandb_double_runs_in_ci():
    """P8: the 22/25 regression is driven by tests/_wandb_doubles.py::make_get_latest_run
    extended to multiple runs per model (newest metric-less, earlier with the full set)
    — NOT an on-disk *.parquet fixture (gitignored -> skipped in CI -> the C-46 trap).
    """
    raise AssertionError("implement #116: synthetic-double-based regression, no on-disk fixture")
