"""
Falsification test stubs for discoverability claim.

These tests encode the findings from the falsification audit of the claim:
"The repo screams its domain and its business logic — a new team member
will know what is up and down immediately and intuitively."

Each test documents a specific discoverability gap. They are written to
FAIL until the gap is addressed, then pass once fixed.
"""

import ast
from pathlib import Path

import pytest

SUBPACKAGES = [
    "mapping",
    "metadata",
    "reconciliation",
    "reports",
    "statistics",
    "templates",
    "transformations",
    "visualizations",
]

CORE_MODULES = [
    "views_reporting/statistics/statistics.py",
    "views_reporting/reconciliation/reconciliation.py",
    "views_reporting/reports/report.py",
    "views_reporting/mapping/mapping.py",
    "views_reporting/visualizations/historical.py",
    "views_reporting/visualizations/distributions.py",
    "views_reporting/metadata/entity_metadata.py",
    "views_reporting/transformations/transformations.py",
    "views_reporting/reports/utils.py",
    "views_reporting/reconciliation/dataset_export.py",
    "views_reporting/statistics/dataset_statistics.py",
    "views_reporting/statistics/dataset_visualization.py",
    "views_reporting/templates/reports/evaluation.py",
    "views_reporting/templates/reports/forecast.py",
]


# ── F-1: Package __init__.py must have module docstrings ───────────────


@pytest.mark.parametrize("pkg", SUBPACKAGES)
def test_subpackage_init_has_docstring(pkg):
    """Every subpackage __init__.py should have a module docstring
    explaining what the package does and when you'd use it."""
    init_path = Path(f"views_reporting/{pkg}/__init__.py")
    tree = ast.parse(init_path.read_text())
    docstring = ast.get_docstring(tree)
    assert docstring is not None, f"views_reporting/{pkg}/__init__.py has no module docstring"
    assert len(docstring.strip()) > 20, f"Docstring too short to be useful: {docstring!r}"


# ── F-2: Core .py files must have module docstrings ────────────────────


@pytest.mark.parametrize("module_path", CORE_MODULES)
def test_core_module_has_docstring(module_path):
    """Every core implementation file should have a module-level docstring
    explaining what domain problem it solves."""
    path = Path(module_path)
    tree = ast.parse(path.read_text())
    docstring = ast.get_docstring(tree)
    assert docstring is not None, f"{module_path} has no module docstring"
    assert len(docstring.strip()) > 20, f"Docstring too short to be useful: {docstring!r}"


# ── F-3: README acronyms must be expanded on first use ─────────────────


REQUIRED_EXPANSIONS = {
    "MAP": "Maximum A Posteriori",
    "HDI": "Highest Density Interval",
    "PRIO-GRID": "PRIO",  # at minimum link or explain
}


def test_readme_expands_acronyms():
    """Key domain acronyms should be expanded on or before first use."""
    readme = Path("README.md").read_text()
    missing = []
    for acronym, expansion in REQUIRED_EXPANSIONS.items():
        first_use = readme.find(acronym)
        if first_use == -1:
            continue
        context = readme[:first_use + 200]
        if expansion.lower() not in context.lower():
            missing.append(f"{acronym} (first used without expanding to '{expansion}')")
    assert not missing, f"Unexpanded acronyms: {missing}"


# ── F-6: Top-level __init__.py should orient newcomers ─────────────────


def test_top_level_init_has_content():
    """The top-level __init__.py should have a module docstring or
    re-exports that orient a newcomer to the package."""
    init_path = Path("views_reporting/__init__.py")
    content = init_path.read_text().strip()
    assert len(content) > 0, "Top-level __init__.py is empty"
    tree = ast.parse(content)
    docstring = ast.get_docstring(tree)
    assert docstring is not None, "Top-level __init__.py has no module docstring"
