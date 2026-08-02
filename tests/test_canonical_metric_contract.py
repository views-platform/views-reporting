"""Contract: the report's canonical metric names track the evaluator's tokens (C-41).

ADR-017 has the evaluation report pull values by matching `ReportingConfig`'s
canonical metric names against the tokens `views_evaluation` emits. If a canonical
name drifts from the evaluator's token, the metric renders "not calculated" forever
even though it *was* computed (a plausible-but-misleading report). This pins the
cross-repo coupling so drift fails loud in CI, not silently in a delivered report.
"""

import re

import pytest

pytest.importorskip("views_evaluation")
from views_evaluation.evaluation.metric_catalog import (  # noqa: E402
    METRIC_CATALOG,
    METRIC_MEMBERSHIP,
)

from views_reporting.config import get_config  # noqa: E402

_CANONICAL = get_config().canonical_report_metrics


def _segments(name: str) -> list[str]:
    return re.split(r"[/_-]", name)


def _is_segment_prefix(a: str, b: str) -> bool:
    """True if ``a`` is a `/_-`-bounded segment-prefix of ``b`` (and a != b)."""
    sa, sb = _segments(a), _segments(b)
    return a != b and len(sa) < len(sb) and sb[: len(sa)] == sa


@pytest.mark.green_team
def test_every_canonical_metric_is_an_implemented_evaluator_token():
    """Each canonical report metric must be a real, *implemented* evaluator token,
    in the evaluator's membership for that (task, pred_type) cell — else it would
    always read 'not calculated' (C-41)."""
    for cell, metrics in _CANONICAL.items():
        membership = METRIC_MEMBERSHIP.get(cell, set())
        for m in metrics:
            assert m in METRIC_CATALOG, (
                f"canonical metric {m!r} ({cell}) is not a known views_evaluation "
                f"token — it would render 'not calculated' (C-41)."
            )
            assert METRIC_CATALOG[m].implemented, (
                f"canonical metric {m!r} ({cell}) is declared but NOT implemented "
                f"upstream — it cannot be computed, so the report would mislead."
            )
            assert m in membership, (
                f"canonical metric {m!r} is not in the evaluator's membership for "
                f"{cell} ({sorted(membership)}); the cell/token pairing drifted."
            )


@pytest.mark.red_team
def test_no_canonical_metric_is_a_segment_prefix_of_another_in_its_cell():
    """The token matcher is segment-boundary based; if one canonical name is a
    `/_-`-bounded prefix of another in the same cell, the match is ambiguous
    (register C-41/C-116 naming rule, config/_reporting.py)."""
    for cell, metrics in _CANONICAL.items():
        for a in metrics:
            for b in metrics:
                assert not _is_segment_prefix(a, b), (
                    f"in {cell}, canonical metric {a!r} is a segment-prefix of "
                    f"{b!r} — ambiguous token match."
                )
