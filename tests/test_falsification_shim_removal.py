"""
Falsification test stubs for shim-removal readiness.

These tests encode findings from the falsification audit of the claim:
"If concerned only with the 7 local repos, the shims can be removed whenever."

The hard falsification is that views-reporting is a runtime dependency
of views-pipeline-core but is not declared in any pyproject.toml.
"""

import re
import tomllib
from pathlib import Path

import pytest

PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent


def _pep508_name(dep: str) -> str:
    """The bare distribution name from a PEP 508 requirement string."""
    return re.split(r"[\s\[<>=!~@;(]", dep.strip(), maxsplit=1)[0]


@pytest.mark.xfail(
    strict=True,
    reason="views-reporting is not declared as a dependency of pipeline-core "
    "(re-verified against released vpc 3.0.0, 2026-08-03: 10 deps in "
    "requires_dist, none of them views-reporting, while "
    "managers/reporting/stage.py still imports views_reporting — the "
    "ensemble.py/dataframe_ensemble.py imports of the original finding are "
    "gone in 3.0.0). strict — if vpc ever declares it, this must fail loudly "
    "so the marker is removed deliberately, not flip to a silent XPASS.",
)
def test_pipeline_core_declares_views_reporting_dependency():
    """pipeline-core imports from views_reporting at runtime (as of released
    3.0.0: managers/reporting/stage.py; the original finding also covered
    ensemble.py/dataframe_ensemble.py, since migrated off) but does not list
    views-reporting in its pyproject.toml RUNTIME dependencies.

    Parses the actual runtime-dependency declarations (poetry main group or
    PEP 621 ``project.dependencies``) rather than substring-matching the raw
    file: vpc 3.0.0 added *comments* mentioning views-reporting, which flipped
    the old substring check to a false XPASS while the dependency remained
    undeclared. Dev/optional groups are deliberately excluded — they would not
    ship in ``requires_dist`` or fix the clean-install failure.
    """
    pyproject = PLATFORM_ROOT / "views-pipeline-core" / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("views-pipeline-core not found at expected path")
    doc = tomllib.loads(pyproject.read_text())

    runtime_names = {
        _pep508_name(dep)
        for dep in doc.get("project", {}).get("dependencies", [])
    }
    runtime_names.update(
        doc.get("tool", {}).get("poetry", {}).get("dependencies", {})
    )

    normalized = {n.lower().replace("_", "-") for n in runtime_names}
    assert "views-reporting" in normalized, (
        "views-pipeline-core has deferred imports from views_reporting "
        "(managers/reporting/stage.py as of 3.0.0) but does not "
        "declare views-reporting as a runtime dependency in pyproject.toml. "
        "A clean install will fail at runtime."
    )
