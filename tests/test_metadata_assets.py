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
        "rows",
        "max_month_id",
        "null_country_cells_dropped",
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
