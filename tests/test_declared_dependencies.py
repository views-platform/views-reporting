"""Guard for C-44: third-party packages imported DIRECTLY by views_reporting must be
declared in `pyproject.toml` `[project].dependencies` — not relied on transitively.

views-reporting imports `wandb` (eval report / run-resolver / reconciliation) and
`viewser` (metadata) directly. Before #120 these were only pulled in transitively via
views-pipeline-core, so an upstream dependency-tree change could have broken first-party
imports with no signal in this repo's lockfile. These tests fail loud if either
declaration is dropped while the import remains.

INTERIM: both are removed in Phase 3 (C-108) — wandb once reporting consumes an injected
MetricFrame, viewser per the C-22 retirement. When that lands, delete the corresponding
assertion here together with the import.
"""

import tomllib
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _declared_dependencies() -> str:
    data = tomllib.loads(_PYPROJECT.read_text())
    return " ".join(data["project"]["dependencies"]).lower()


@pytest.mark.parametrize(
    "package, why",
    [
        ("wandb", "imported directly in evaluation / run-resolver / reconciliation"),
        ("viewser", "imported directly in metadata/entity_metadata.py"),
        ("views-frames", "leaf data contract; adopted by epic #137 (used from S3-S4)"),
    ],
)
def test_directly_imported_package_is_declared(package, why):
    deps = _declared_dependencies()
    assert package in deps, (
        f"`{package}` is {why} but is not declared in pyproject `[project].dependencies` "
        f"— it would be pulled only transitively (C-44). Declare it explicitly."
    )


def test_directly_imported_packages_are_importable():
    """Sanity: the declared packages actually import (catches a broken/missing install)."""
    pytest.importorskip("wandb")
    pytest.importorskip("viewser")
    pytest.importorskip("views_frames")
    pytest.importorskip("views_frames_summarize")
