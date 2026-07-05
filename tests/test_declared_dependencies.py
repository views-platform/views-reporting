"""Guard for C-44: third-party packages imported DIRECTLY by views_reporting must be
declared in `pyproject.toml` `[project].dependencies` — not relied on transitively.

History: `viewser` was the canonical case (declared by #120, retired by C-22 S2 / #206 —
the package now reads bundled parquets and only scripts/build_entity_metadata.py touches
viewser, at dev time). `wandb` left with C-108 B2 + #72. `pyarrow` joined with C-22
(the parquet engine for the bundled metadata assets — previously only transitive via
the viewser chain the epic retires). These tests fail loud if a declaration is dropped
while the direct import remains.
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
        ("pyarrow", "the parquet engine for the bundled metadata assets (C-22)"),
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
    pytest.importorskip("pyarrow")
    pytest.importorskip("views_frames")
    pytest.importorskip("views_frames_summarize")
