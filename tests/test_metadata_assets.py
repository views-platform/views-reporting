"""Integrity net for the bundled entity-metadata assets (epic #204, S1 / #205).

The assets under ``views_reporting/metadata/data/`` are generated once by
``scripts/build_entity_metadata.py`` (viewser at dev time — register C-22) and
committed; these tests pin their schema, key uniqueness, referential integrity
and the C-112 stamp (version + source-date + checksums) — all runnable in CI
with no viewser access. The reduction logic is unit-tested against synthetic
frames (no assets needed), so the script is reviewable before any fetch runs.
"""

import hashlib
import importlib.util
import json
import pathlib

import pandas as pd
import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_DATA = _REPO / "views_reporting" / "metadata" / "data"
_SCRIPT = _REPO / "scripts" / "build_entity_metadata.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_entity_metadata", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Reduction logic (pure — no assets, no viewser) ──────────────────────────


@pytest.mark.green_team
def test_reduction_takes_last_nonnull_per_entity():
    """`groupby.last` semantics: retired entities keep their last-known values
    (a latest-month snapshot would drop them); renames pick up the newest name."""
    mod = _load_script()
    c_raw = pd.DataFrame(
        {
            "month_id": [100, 200, 300, 100, 200],
            "country_id": [1, 1, 1, 2, 2],
            "isoab": ["SWZ", "SWZ", "SWZ", "YUG", None],
            "name": ["Swaziland", "Eswatini", None, "Yugoslavia", None],
        }
    )
    out = mod.reduce_country(c_raw)
    swz = out[out["country_id"] == 1].iloc[0]
    assert swz["name"] == "Eswatini"  # rename picked up; trailing NaN skipped
    yug = out[out["country_id"] == 2].iloc[0]
    assert yug["isoab"] == "YUG" and yug["name"] == "Yugoslavia"  # retired entity kept


@pytest.mark.green_team
def test_priogrid_reduction_drops_and_counts_unassigned_cells():
    mod = _load_script()
    pg_raw = pd.DataFrame(
        {
            "month_id": [100, 200, 100, 200],
            "priogrid_id": [10, 10, 20, 20],
            "country_id": [5.0, 6.0, None, None],  # cell 20 never assigned
        }
    )
    out, n_null = mod.reduce_priogrid(pg_raw)
    assert n_null == 1
    assert out["priogrid_id"].tolist() == [10]
    assert out["country_id"].tolist() == [6]  # the LATEST assignment (border change)


@pytest.mark.red_team
def test_reduction_rejects_duplicate_keys():
    mod = _load_script()
    dup = pd.DataFrame(
        {
            "month_id": [100, 100],
            "country_id": [1, 1],
            "isoab": ["AAA", "BBB"],
            "name": ["A", "B"],
        }
    )
    # groupby collapses per-entity, so uniqueness holds by construction — the
    # guard exists for future refactors; exercise it directly on the output:
    out = mod.reduce_country(dup)
    assert out["country_id"].is_unique


# ── GAUL crosswalk logic (pure — the interim adapter seam, #231) ─────────────


@pytest.mark.green_team
def test_active_country_resolves_duplicate_isoab_to_latest_entity():
    """VIEWS isoab is not unique over history (retired states share codes with
    successors). The crosswalk must pick the entity observed furthest in time —
    e.g. unified Yemen over Yemen Arab Republic — never the retired one."""
    mod = _load_script()
    c_raw = pd.DataFrame(
        {
            "month_id": [100, 200, 500, 100, 300],
            # entity 196 last observed at month 200 (retired); 240 runs to 500
            "country_id": [196, 196, 240, 7, 7],
            "isoab": ["YEM", "YEM", "YEM", "NOR", "NOR"],
            "name": ["Yemen AR", "Yemen AR", "Yemen", "Norway", "Norway"],
        }
    )
    out = mod.active_country_by_isoab(c_raw)
    assert out["YEM"] == 240
    assert out["NOR"] == 7


@pytest.mark.green_team
def test_crosswalk_buckets_matched_unassigned_unmatched():
    """The three cell buckets: matched → table; null/empty code (ocean) →
    unassigned count; real-but-unknown code (disputed territory) → unmatched
    count keyed per code, so the stamp declares exactly what is missing."""
    mod = _load_script()
    gaul_cells = pd.DataFrame(
        {
            "gid": [1, 2, 3, 4, 5],
            "iso3": ["NOR", "ESH", None, "", "NOR"],
            "gaul0_name": ["Norway", "Western Sahara", None, "", "Norway"],
        }
    )
    isoab_to_country = pd.Series({"NOR": 7})
    table, stats = mod.crosswalk_priogrid(gaul_cells, isoab_to_country)
    assert table["priogrid_id"].tolist() == [1, 5]
    assert table["country_id"].tolist() == [7, 7]
    assert stats["unassigned_cells"] == 2  # None + empty string
    assert stats["unmatched_cells"] == 1
    assert stats["unmatched_iso3"] == {"ESH": 1}


@pytest.mark.red_team
def test_crosswalk_rejects_duplicate_gids():
    mod = _load_script()
    gaul_cells = pd.DataFrame(
        {
            "gid": [1, 1],
            "iso3": ["NOR", "NOR"],
            "gaul0_name": ["Norway", "Norway"],
        }
    )
    with pytest.raises(ValueError, match="not unique"):
        mod.crosswalk_priogrid(gaul_cells, pd.Series({"NOR": 7}))


# ── Committed assets (schema / keys / integrity) ─────────────────────────────


@pytest.mark.green_team
def test_country_parquet_schema_and_unique_key():
    df = pd.read_parquet(_DATA / "country.parquet")
    assert list(df.columns) == ["country_id", "isoab", "name"]
    assert df["country_id"].is_unique
    assert df["name"].notna().all()  # every entity is at least nameable
    # isoab CAN be null where the source has no ISO code (Kosovo has no
    # official alpha-3) — frozen as-is, and every case must be declared in
    # the stamp so it is a recorded fact, not a surprise.
    stamp = json.loads((_DATA / "stamp.json").read_text())
    null_isoab = df.loc[df["isoab"].isna(), "name"].tolist()
    assert sorted(null_isoab) == sorted(stamp["null_isoab_countries"])
    assert len(null_isoab) <= 3, f"unexpectedly many ISO-less entities: {null_isoab}"
    assert len(df) > 150  # every entity ever observed, incl. retired states


@pytest.mark.green_team
def test_priogrid_parquet_schema_and_unique_key():
    df = pd.read_parquet(_DATA / "priogrid.parquet")
    assert list(df.columns) == ["priogrid_id", "country_id"]
    assert df["priogrid_id"].is_unique
    assert df["country_id"].notna().all()  # unassigned cells were dropped, not NaN'd


@pytest.mark.green_team
def test_priogrid_country_ids_are_subset_of_country_table():
    """Referential integrity between the two parquets — every cell's country
    resolves to a labelled entity (the PGM with_id join cannot silently NaN)."""
    pg = pd.read_parquet(_DATA / "priogrid.parquet")
    c = pd.read_parquet(_DATA / "country.parquet")
    unknown = set(pg["country_id"]) - set(c["country_id"])
    assert not unknown, f"priogrid references unlabelled country_ids: {sorted(unknown)[:10]}"


@pytest.mark.green_team
def test_stamp_required_fields_parseable():
    stamp = json.loads((_DATA / "stamp.json").read_text())
    for key in (
        "snapshot_utc",
        "querysets",
        "priogrid_source",  # the adapter-seam provenance block (#231)
        "rows",
        "max_month_id",
        "priogrid_semantics",
        "sha256",
    ):
        assert key in stamp, f"stamp.json missing {key!r}"
    # source-date is a real, parseable timestamp (C-112: version + source-date)
    pd.Timestamp(stamp["snapshot_utc"])
    assert stamp["rows"]["country"] > 0 and stamp["rows"]["priogrid"] > 0


@pytest.mark.green_team
def test_stamp_checksums_match_files():
    """Integrity bind: stamp and parquets were edited together. (sha256 of the
    written bytes — NOT a cross-pyarrow-version reproducibility guarantee.)"""
    stamp = json.loads((_DATA / "stamp.json").read_text())
    for fname, expected in stamp["sha256"].items():
        actual = hashlib.sha256((_DATA / fname).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{fname} does not match stamp.json — regenerate the bundle via "
            "scripts/build_entity_metadata.py (assets and stamp must be "
            "committed together)"
        )
