"""Render==source fidelity (register C-29): the value drawn for a cell/country must
equal the source prediction for that exact (time, entity) — right number on the
right place — after the metadata + shapefile join, and an unmatchable entity must
be *dropped*, never silently re-assigned.

The join is exercised against a small synthetic world GeoDataFrame (deterministic,
no 56 MB shapefile, no VIEWSER) so a merge/index bug would flip a value or scramble
a place and fail loud here instead of in a delivered report.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

try:
    import geopandas as gpd
    from shapely.geometry import box
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.mapping.mapping import MappingModule
except ImportError:
    pytest.skip("views_frames / geopandas not installed", allow_module_level=True)

TARGET = "pred_ged_sb"
# country_id → ISO code; AAA/BBB/CCC exist in the synthetic world, ZZZ does not.
ENTITY_ISO = {1: "AAA", 2: "BBB", 3: "CCC", 4: "ZZZ"}
_ADAPTER = "views_reporting.mapping._frame_adapter"


def _point_frame(level, rows):
    """rows = [(time, entity, value)] → an S==1 PredictionFrame."""
    idx = SpatioTemporalIndex(
        time=np.array([t for t, _, _ in rows], dtype=np.int64),
        unit=np.array([e for _, e, _ in rows], dtype=np.int64),
        level=level,
    )
    vals = np.array([[v] for _, _, v in rows], dtype=np.float32)
    return PredictionFrame(vals, idx)


def _iso_side_effect(index, level):
    return pd.DataFrame({"isoab": [ENTITY_ISO.get(e, f"X{e}") for (_, e) in index]}, index=index)


def _name_side_effect(index, level, with_id=False):
    return pd.DataFrame({"name": [f"C{e}" for (_, e) in index]}, index=index)


def _labels_side_effect(index, level, with_id=False):
    out = _iso_side_effect(index, level)
    out["name"] = _name_side_effect(index, level, with_id)["name"]
    return out


def _cm_world():
    return gpd.GeoDataFrame(
        {"ADM0_A3": ["AAA", "BBB", "CCC"],
         "geometry": [box(0, 0, 1, 1), box(1, 1, 2, 2), box(2, 2, 3, 3)]},
        crs="EPSG:4326",
    )


def _pgm_world():
    return gpd.GeoDataFrame(
        {"gid": [10, 20, 30],
         "geometry": [box(0, 0, 1, 1), box(1, 1, 2, 2), box(2, 2, 3, 3)]},
        crs="EPSG:4326",
    )


def _subset(frame, level, world):
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=world), patch(
        f"{_ADAPTER}.get_labels_for_index", side_effect=_labels_side_effect
    ):
        mm = MappingModule(frame=frame, level=level, target_column=TARGET)
        return mm.get_subset_mapping_dataframe(entity_ids=None, time_ids=None)


@pytest.mark.green_team
def test_cm_value_lands_on_the_right_country_and_time():
    """Each (month, country) renders the *source* value, joined to the *right* iso."""
    rows = [(528, 1, 1528.0), (528, 2, 2528.0), (529, 3, 3529.0)]  # value = entity*1000 + time
    gdf = _subset(_point_frame(SpatialLevel.CM, rows), SpatialLevel.CM, _cm_world())

    got = {
        (int(r.month_id), int(r.country_id)): (float(getattr(r, TARGET)), r.isoab)
        for r in gdf.itertuples()
    }
    assert set(got) == {(t, e) for t, e, _ in rows}, "rendered (time,entity) set ≠ source"
    for t, e, v in rows:
        value, iso = got[(t, e)]
        assert value == pytest.approx(v), f"value for ({t},{e}) scrambled"
        assert iso == ENTITY_ISO[e], f"({t},{e}) joined to the wrong place ({iso})"


@pytest.mark.red_team
def test_cm_unmatchable_entity_is_dropped_not_corrupted():
    """A country with no shapefile geometry (ZZZ) is dropped (C-29's island-drop),
    and the surviving rows keep their correct values — the drop neither corrupts
    nor re-assigns survivors."""
    rows = [(528, 1, 1528.0), (528, 4, 4528.0), (529, 1, 1529.0)]  # entity 4 → ZZZ (absent)
    gdf = _subset(_point_frame(SpatialLevel.CM, rows), SpatialLevel.CM, _cm_world())

    out = {
        (int(r.month_id), int(r.country_id)): float(getattr(r, TARGET))
        for r in gdf.itertuples()
    }
    assert (528, 4) not in out, "unmatchable entity should be dropped, not rendered"
    assert out[(528, 1)] == pytest.approx(1528.0)
    assert out[(529, 1)] == pytest.approx(1529.0)
    # the dropped set is exactly the unmatchable entity — a *new* drop would change this
    assert set(out) == {(528, 1), (529, 1)}


@pytest.mark.green_team
def test_pgm_value_lands_on_the_right_cell():
    """PGM joins on priogrid_id↔gid; each cell renders its source value."""
    rows = [(528, 10, 11.0), (528, 20, 22.0), (529, 30, 33.0)]
    gdf = _subset(_point_frame(SpatialLevel.PGM, rows), SpatialLevel.PGM, _pgm_world())

    got = {
        (int(r.month_id), int(r.priogrid_id)): float(getattr(r, TARGET))
        for r in gdf.itertuples()
    }
    assert set(got) == {(t, e) for t, e, _ in rows}
    for t, e, v in rows:
        assert got[(t, e)] == pytest.approx(v), f"PGM cell ({t},{e}) value scrambled"
