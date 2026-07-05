"""The entity-keyed metadata accessors against the REAL bundled assets
(epic #204, S2 / #206 — the C-22 runtime swap).

The old implementation keyed lookups on exact ``(month_id, entity_id)`` pairs,
so months absent from the source table silently NaN'd every label (emptying CM
maps via the geometry merge). These tests exercise the actual accessors — no
conftest doubles — including the future-months broadcast that the old code
would fail.
"""

import json
import pathlib
import re
import subprocess

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import SpatialLevel

    from views_reporting.metadata import entity_metadata as em
    from views_reporting.visualizations.historical import HistoricalLineGraph
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

_REPO = pathlib.Path(__file__).resolve().parent.parent
_DATA = _REPO / "views_reporting" / "metadata" / "data"

# A month safely beyond the snapshot horizon (stamp max_month_id) — the
# forecast-month case the old exact-month keying could not resolve.
_FUTURE_MONTH = json.loads((_DATA / "stamp.json").read_text())["max_month_id"]["country"] + 60


def _index(level: SpatialLevel, months, entities) -> pd.MultiIndex:
    return pd.MultiIndex.from_product(
        [months, entities], names=list(level.index_names)
    )


def _nigeria_cell() -> int:
    """A real grid cell assigned to Nigeria (country_id 79) in the bundle."""
    pg = pd.read_parquet(_DATA / "priogrid.parquet")
    return int(pg.loc[pg["country_id"] == 79, "priogrid_id"].iloc[0])


@pytest.fixture(autouse=True)
def _fresh_cache():
    em._reset_metadata_cache()
    yield
    em._reset_metadata_cache()


# ── The regression test: entity-keyed broadcast over future months ──────────


@pytest.mark.green_team
def test_isoab_broadcasts_to_future_months():
    """Labels resolve for months beyond the snapshot horizon — forecast frames
    carry future months, and identity metadata must broadcast, not month-match.
    (Would FAIL against the pre-C-22 exact-(month, entity) reindex.)"""
    idx = _index(SpatialLevel.CM, [_FUTURE_MONTH, _FUTURE_MONTH + 1], [79])  # Nigeria
    out = em.get_isoab_for_index(idx, SpatialLevel.CM)
    assert list(out.columns) == ["isoab"]
    assert out.index.equals(idx)
    assert (out["isoab"] == "NGA").all()


@pytest.mark.green_team
def test_pgm_isoab_broadcasts_to_future_months():
    idx = _index(SpatialLevel.PGM, [_FUTURE_MONTH], [_nigeria_cell()])
    out = em.get_isoab_for_index(idx, SpatialLevel.PGM)
    assert (out["isoab"] == "NGA").all()


# ── Label shapes ─────────────────────────────────────────────────────────────


@pytest.mark.green_team
def test_name_with_id_cm_uses_index_entity():
    idx = _index(SpatialLevel.CM, [500], [79])
    out = em.get_name_for_index(idx, SpatialLevel.CM, with_id=True)
    assert out["name"].iloc[0] == "79 - Nigeria"


@pytest.mark.green_team
def test_name_with_id_pgm_joins_both_tables():
    """PGM labels need cell→country (priogrid.parquet) joined to country→name
    (country.parquet)."""
    idx = _index(SpatialLevel.PGM, [500], [_nigeria_cell()])
    out = em.get_name_for_index(idx, SpatialLevel.PGM, with_id=True)
    assert out["name"].iloc[0] == "79 - Nigeria"


@pytest.mark.green_team
def test_plain_name_cm():
    idx = _index(SpatialLevel.CM, [500], [79])
    out = em.get_name_for_index(idx, SpatialLevel.CM)
    assert out["name"].iloc[0] == "Nigeria"


# ── Failure semantics (ADR-008 / ADR-018 calibration) ───────────────────────


@pytest.mark.red_team
def test_unknown_entity_yields_nan_and_warns_once(caplog):
    """A partially-unknown frame degrades visibly: NaN for the unknown entity,
    ONE aggregated warning — the lookup table must not veto the report."""
    idx = _index(SpatialLevel.CM, [500], [79, 999_999])
    with caplog.at_level("WARNING", logger="views_reporting.metadata.entity_metadata"):
        out = em.get_isoab_for_index(idx, SpatialLevel.CM)
    assert out["isoab"].iloc[0] == "NGA"
    assert pd.isna(out["isoab"].iloc[1])
    warnings = [r for r in caplog.records if "not in the bundled metadata" in r.message]
    assert len(warnings) == 1
    assert "999999" in warnings[0].getMessage()


@pytest.mark.red_team
def test_all_unknown_entities_raise():
    """A frame with NO known entity is a wrong-table/level error, not sparse
    coverage — fail loud instead of emitting an empty artifact."""
    idx = _index(SpatialLevel.CM, [500], [999_998, 999_999])
    with pytest.raises(ValueError, match="bundled metadata"):
        em.get_isoab_for_index(idx, SpatialLevel.CM)


@pytest.mark.red_team
def test_missing_bundle_raises_with_regeneration_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(em, "_DATA_DIR", tmp_path)
    em._reset_metadata_cache()
    idx = _index(SpatialLevel.CM, [500], [79])
    with pytest.raises(FileNotFoundError, match="build_entity_metadata"):
        em.get_isoab_for_index(idx, SpatialLevel.CM)


@pytest.mark.green_team
def test_cache_reset_hook():
    idx = _index(SpatialLevel.CM, [500], [79])
    em.get_isoab_for_index(idx, SpatialLevel.CM)
    assert em._TABLE_CACHE  # populated
    em._reset_metadata_cache()
    assert not em._TABLE_CACHE  # cleared — no state leaks between tests


@pytest.mark.red_team
def test_historical_nan_label_falls_back_to_entity_n():
    """The NaN-poisoning fix: an entity whose mapped label is NaN renders as
    'Entity N', never the literal string 'nan' (silent-wrong-value class)."""
    hlg = HistoricalLineGraph.__new__(HistoricalLineGraph)  # method under test is arg-pure
    assert hlg._get_entity_label(7, {7: np.nan}) == "Entity 7"
    assert hlg._get_entity_label(7, {7: "Nigeria"}) == "Nigeria"
    assert hlg._get_entity_label(8, {7: "Nigeria"}) == "Entity 8"
    assert hlg._get_entity_label(9, None) == "Entity 9"


# ── The C-22 closing guard ───────────────────────────────────────────────────


@pytest.mark.red_team
def test_no_viewser_import_under_views_reporting():
    """C-22 closed: nothing in the shipped package imports viewser (the only
    permitted user is scripts/build_entity_metadata.py, dev-time). Grep-guard,
    same pattern as the falsify-P6 private-internals guard."""
    pat = re.compile(r"^\s*(from viewser\b|import viewser\b)", re.MULTILINE)
    offenders = [
        str(p.relative_to(_REPO))
        for p in (_REPO / "views_reporting").rglob("*.py")
        if pat.search(p.read_text())
    ]
    assert not offenders, f"viewser imports remain in the package: {offenders}"


@pytest.mark.green_team
def test_offline_render_no_network_modules():
    """The metadata edge works with viewser absent: the accessor module itself
    must not have viewser in its imports (belt to the grep-guard's braces)."""
    result = subprocess.run(
        [
            "python",
            "-c",
            "import sys; sys.modules['viewser']=None; "
            "import importlib; importlib.import_module("
            "'views_reporting.metadata.entity_metadata'); print('ok')",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO,
    )
    assert "ok" in result.stdout, result.stderr
