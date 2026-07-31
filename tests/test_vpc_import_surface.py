"""Guard the views-pipeline-core import surface (register C-213, #263).

Release-readiness guards for the vpc coupling (epic #262 S1). Two rules, both
derived from vpc's own module governance and enforced here so a drift fails
loud in OUR CI, not at the coordinated release (#179):

1. **No ADR-054 tombstone imports.** vpc's ``modules/*`` packages (reports,
   mapping, visualizations, reconciliation, statistics, transformations) are
   backward-compat shims scheduled for removal when vpc next publishes
   ("remove-when-forced", their #184). views-reporting is the *target* of
   several of them — importing one from here would be a cycle AND a
   publish-time breakage.
2. **``ModelPathManager`` only from its canonical home.** vpc ADR-045 E6
   relocated it to ``views_pipeline_core.data.model_path``; the old
   ``managers.model`` path is a compat re-export. We import canonically so a
   future compat-layer retirement cannot touch us.

Pattern follows the C-114 P6 guard (``test_falsify_views_frames_integration``):
rglob the source tree, regex the text, name the offenders.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).parent.parent
_SRC = _REPO / "views_reporting"


def _offenders(pattern: re.Pattern[str]) -> list[str]:
    return [
        str(p.relative_to(_REPO))
        for p in sorted(_SRC.rglob("*.py"))
        if pattern.search(p.read_text())
    ]


def test_no_vpc_modules_tombstone_imports():
    """No import may touch the ADR-054 tombstone namespace
    ``views_pipeline_core.modules`` (register C-213)."""
    pat = re.compile(r"\bviews_pipeline_core\.modules\b")
    offenders = _offenders(pat)
    assert not offenders, (
        "views_pipeline_core.modules.* is the ADR-054 tombstone/shim namespace "
        f"(removed at vpc's next publish) — do not import it: {offenders}"
    )


def test_model_path_manager_imported_only_from_canonical_home():
    """``ModelPathManager`` must come from ``views_pipeline_core.data.model_path``
    (canonical, vpc ADR-045 E6) — never the ``managers``-layer compat re-export
    (register C-213)."""
    # \(?[^)]*? + re.S covers parenthesized multi-line import lists too.
    pat = re.compile(
        r"from\s+views_pipeline_core\.managers[.\w]*\s+import\s+"
        r"\(?[^)]*?\bModelPathManager\b",
        re.S,
    )
    offenders = _offenders(pat)
    assert not offenders, (
        "ModelPathManager imported via the managers-layer compat re-export; "
        f"use views_pipeline_core.data.model_path instead: {offenders}"
    )
