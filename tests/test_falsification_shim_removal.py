"""
Falsification test stubs for shim-removal readiness.

These tests encode findings from the falsification audit of the claim:
"If concerned only with the 7 local repos, the shims can be removed whenever."

The hard falsification is that views-reporting is a runtime dependency
of views-pipeline-core but is not declared in any pyproject.toml.
"""

from pathlib import Path

import pytest

PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.xfail(
    reason="views-reporting is not declared as a dependency of pipeline-core"
)
def test_pipeline_core_declares_views_reporting_dependency():
    """pipeline-core imports from views_reporting at runtime (stage.py,
    ensemble.py, dataframe_ensemble.py) but does not list views-reporting
    in its pyproject.toml dependencies."""
    pyproject = PLATFORM_ROOT / "views-pipeline-core" / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("views-pipeline-core not found at expected path")
    content = pyproject.read_text()
    assert "views-reporting" in content or "views_reporting" in content, (
        "views-pipeline-core has deferred imports from views_reporting "
        "(stage.py, ensemble.py, dataframe_ensemble.py) but does not "
        "declare views-reporting as a dependency in pyproject.toml. "
        "A clean install will fail at runtime."
    )
