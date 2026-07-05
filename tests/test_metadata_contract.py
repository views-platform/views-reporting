"""Metadata contract assurance (epic #204, S3 / #207) — closes register C-39.

The real accessors, the real bundled tables, and the real shapefile, exercised
together with NO conftest doubles. The join-coverage contract is the C-112
drift tripwire: it fails when a regenerated bundle and the committed Natural
Earth vintage diverge — the signal to re-run ``scripts/build_entity_metadata.py``
or refresh the shapefile.

First catch (found while writing this suite, fixed in the same PR — register
C-206): Natural Earth codes South Sudan ``ADM0_A3="SDS"`` (an NE-internal code)
while VIEWS uses ISO ``SSD`` — South Sudan silently dropped from every CM
choropleth, live viewser included. The loader now normalizes the merge key to
``ISO_A3_EH`` where it is a real ISO code.
"""

import json
import pathlib
import subprocess
import zipfile

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.mapping.mapping import MappingModule
    from views_reporting.metadata.entity_metadata import metadata_snapshot_date
except ImportError:
    pytest.skip("views_frames / geopandas not installed", allow_module_level=True)

_REPO = pathlib.Path(__file__).resolve().parent.parent
_DATA = _REPO / "views_reporting" / "metadata" / "data"

# Bundled isoab codes correctly absent from the committed Natural Earth 110m
# shapefile, by category. A NEW code appearing in neither category means the
# bundle and the shapefile vintage have drifted (C-112) — regenerate or bump.
RETIRED_STATES = {"CSK", "DDR", "SCG", "SUN", "YUG", "YMD"}  # dissolved pre-vintage
MICROSTATES_ABSENT_AT_110M = {  # too small for the 1:110m resolution (C-29 class)
    "ATG", "BHR", "BRB", "COM", "CPV", "DMA", "FSM", "GRD", "KIR", "KNA",
    "LCA", "MDV", "MHL", "MLT", "MUS", "NRU", "PLW", "SGP", "STP", "SYC",
    "TON", "TUV", "VCT", "WSM",
}


def _cm_module(country_ids: list[int]) -> MappingModule:
    """A REAL CM MappingModule (no mocked shapefile) over a tiny frame."""
    n = len(country_ids)
    idx = SpatioTemporalIndex(
        time=np.full(n, 528, dtype=np.int64),
        unit=np.array(country_ids, dtype=np.int64),
        level=SpatialLevel.CM,
    )
    frame = PredictionFrame(np.ones((n, 1), dtype=np.float32), idx)
    return MappingModule(frame=frame, level=SpatialLevel.CM, target_column="pred_x")


def _country_id_for(isoab: str) -> int:
    c = pd.read_parquet(_DATA / "country.parquet")
    return int(c.loc[c["isoab"] == isoab, "country_id"].iloc[0])


# ── Join-coverage contract (the C-112 tripwire) ──────────────────────────────


@pytest.mark.green_team
def test_bundled_isoab_subset_of_shapefile_adm0a3():
    """Every bundled ISO code either joins the shapefile or is a documented,
    categorized absence — an uncategorized gap is bundle↔shapefile drift."""
    c = pd.read_parquet(_DATA / "country.parquet")
    world = _cm_module([_country_id_for("NGA")])._world
    unmatched = set(c["isoab"].dropna()) - set(world["ADM0_A3"])
    uncategorized = unmatched - RETIRED_STATES - MICROSTATES_ABSENT_AT_110M
    assert not uncategorized, (
        f"bundled isoab codes silently unmappable: {sorted(uncategorized)} — "
        "bundle/shapefile drift (C-112): regenerate via "
        "scripts/build_entity_metadata.py or refresh the Natural Earth asset, "
        "then re-categorize."
    )


@pytest.mark.red_team
def test_south_sudan_joins_the_shapefile():
    """The C-206 regression: NE codes South Sudan ADM0_A3='SDS' vs ISO 'SSD';
    without key normalization the country silently vanishes from CM maps."""
    world = _cm_module([_country_id_for("SSD")])._world
    assert "SSD" in set(world["ADM0_A3"])
    assert "SDS" not in set(world["ADM0_A3"])  # the NE-internal code is gone


# ── Golden values ─────────────────────────────────────────────────────────────


@pytest.mark.green_team
def test_known_entities_golden_values():
    """Spot-pins immune to the double-synthesis blindness that hid the
    future-months bug (doubles fabricate a value for ANY id)."""
    c = pd.read_parquet(_DATA / "country.parquet").set_index("country_id")
    assert c.loc[79, "isoab"] == "NGA" and c.loc[79, "name"] == "Nigeria"
    ssd = c[c["isoab"] == "SSD"]
    assert len(ssd) == 1 and ssd["name"].iloc[0] == "South Sudan"


# ── Unmocked end-to-end: the full identity chain ─────────────────────────────


@pytest.mark.green_team
def test_cm_map_dataframe_renders_unmocked_with_real_metadata():
    """Frame → real accessors → real shapefile merge → geometry, with NO
    conftest doubles: the chain the mocked seams never exercised (the
    'tests mock the fetch' concern). Includes South Sudan end-to-end."""
    ids = [_country_id_for("NGA"), _country_id_for("SSD")]
    module = _cm_module(ids)
    mdf = module.get_subset_mapping_dataframe(entity_ids=None, time_ids=None)
    assert len(mdf) == 2, "a country was silently dropped by the identity chain"
    assert set(mdf["isoab"]) == {"NGA", "SSD"}
    assert mdf.geometry.notna().all() and (~mdf.geometry.is_empty).all()
    # the frame adapter requests with_id labels: "{country_id} - {name}"
    assert {n.split(" - ", 1)[1] for n in mdf["country_name"]} == {
        "Nigeria",
        "South Sudan",
    }


# ── Provenance observability (C-112) ─────────────────────────────────────────


@pytest.mark.green_team
def test_metadata_snapshot_date_matches_stamp():
    stamp = json.loads((_DATA / "stamp.json").read_text())
    assert metadata_snapshot_date() == stamp["snapshot_utc"]
    pd.Timestamp(metadata_snapshot_date())  # parseable


# ── Packaging guard ──────────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.green_team
def test_wheel_contains_metadata_assets(tmp_path):
    """The bundle ships in the wheel — a future rename/exclude fails loud here,
    not at a partner's first offline render."""
    subprocess.run(
        ["uv", "build", "--wheel", "-o", str(tmp_path)],
        cwd=_REPO,
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    for asset in ("country.parquet", "priogrid.parquet", "stamp.json"):
        assert f"views_reporting/metadata/data/{asset}" in names, (
            f"{asset} missing from the wheel"
        )
