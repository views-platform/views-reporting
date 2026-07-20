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


# ── GAUL harvest input validation (#239/#240 — fail at cause) ────────────────


def _write_harvest(tmp_path, iso_rows, name_rows):
    """Stage a tiny gaul_admin harvest dir; filenames come from the script's
    GAUL_HARVEST_FILES constant so these tests track the real layout (#244)."""
    mod = _load_script()
    iso_file, name_file = mod.GAUL_HARVEST_FILES
    pd.DataFrame(iso_rows).to_parquet(tmp_path / iso_file, index=False)
    pd.DataFrame(name_rows).to_parquet(tmp_path / name_file, index=False)
    return mod


@pytest.mark.red_team
def test_read_gaul_cells_rejects_duplicate_gid_named_by_file(tmp_path):
    """A duplicate gid must fail with a message naming the offending harvest
    file — not pandas' opaque duplicate-label reindex error (#240)."""
    mod = _write_harvest(
        tmp_path,
        {"gid": [1, 1], "value": ["NOR", "NOR"]},
        {"gid": [1, 2], "value": ["Norway", "Sweden"]},
    )
    with pytest.raises(ValueError, match="iso3_code.parquet.*duplicate gid"):
        mod.read_gaul_cells(tmp_path)


@pytest.mark.red_team
def test_read_gaul_cells_rejects_mismatched_gid_sets(tmp_path):
    """Disjoint gid sets must fail loud naming both files — the silent
    alternative NaN-fills and rebuckets real cells as 'unassigned' (#240)."""
    mod = _write_harvest(
        tmp_path,
        {"gid": [1, 2], "value": ["NOR", "SWE"]},
        {"gid": [2, 3], "value": ["Sweden", "Finland"]},
    )
    with pytest.raises(ValueError, match="different gid sets"):
        mod.read_gaul_cells(tmp_path)


@pytest.mark.red_team
def test_read_gaul_cells_rejects_partial_harvest(tmp_path):
    """The completeness contract is enforced at the INPUT (#239): a partial
    harvest — even one large enough that its crosswalk output would clear
    main()'s 50k floor — is refused with the expected grid size named."""
    n = 1_000  # any n != 259,200
    rows = {"gid": list(range(1, n + 1)), "value": ["NOR"] * n}
    mod = _write_harvest(tmp_path, rows, {"gid": rows["gid"], "value": ["x"] * n})
    with pytest.raises(ValueError, match="259,200"):
        mod.read_gaul_cells(tmp_path)


@pytest.mark.green_team
def test_read_gaul_cells_accepts_full_parallel_harvest(tmp_path):
    """Characterize the seam: a complete, parallel harvest round-trips with
    the expected columns and row count."""
    mod = _load_script()
    n = mod.PRIO_GRID_N_CELLS
    gids = list(range(1, n + 1))
    iso_file, name_file = mod.GAUL_HARVEST_FILES
    pd.DataFrame({"gid": gids, "value": ["NOR"] * n}).to_parquet(
        tmp_path / iso_file, index=False
    )
    pd.DataFrame({"gid": gids, "value": ["Norway"] * n}).to_parquet(
        tmp_path / name_file, index=False
    )
    out = mod.read_gaul_cells(tmp_path)
    assert list(out.columns) == ["gid", "iso3", "gaul0_name"]
    assert len(out) == n


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


@pytest.mark.green_team
def test_crosswalk_normalizes_padded_codes_and_keeps_disputed_exact():
    """One normalization for bucket, map, and histogram (#241): a padded
    valid code ('NOR ') matches its country; a disputed x-prefixed code
    stays unmatched under its EXACT original spelling (no case-folding);
    whitespace-only codes are unassigned, not unmatched."""
    mod = _load_script()
    gaul_cells = pd.DataFrame(
        {
            "gid": [1, 2, 3, 4],
            "iso3": ["NOR ", " NOR", "xJK", "   "],
            "gaul0_name": ["Norway", "Norway", "Jammu And Kashmir", ""],
        }
    )
    table, stats = mod.crosswalk_priogrid(gaul_cells, pd.Series({"NOR": 7}))
    assert table["priogrid_id"].tolist() == [1, 2]
    assert table["country_id"].tolist() == [7, 7]
    assert stats["unmatched_iso3"] == {"xJK": 1}
    assert stats["unassigned_cells"] == 1  # whitespace-only


@pytest.mark.green_team
def test_crosswalk_unmatched_histogram_is_deterministically_ordered():
    """Byte-reproducible stamp (#243): tied counts order by (-count, code),
    independent of input row order."""
    import json

    mod = _load_script()

    code_by_gid = {1: "AAA", 2: "AAA", 3: "ZZZ", 4: "BBB", 5: "CCC", 6: "CCC"}

    def build(order):
        cells = pd.DataFrame(
            {
                "gid": order,
                "iso3": [code_by_gid[g] for g in order],
                "gaul0_name": ["x"] * len(order),
            }
        )
        _, stats = mod.crosswalk_priogrid(cells, pd.Series({"NOP": 1}))
        return stats["unmatched_iso3"]

    a = build([1, 2, 3, 4, 5, 6])
    b = build([6, 3, 1, 5, 2, 4])
    # counts: AAA=2, CCC=2, BBB=1, ZZZ=1 -> order (-count, code)
    assert list(a) == ["AAA", "CCC", "BBB", "ZZZ"]
    assert json.dumps(a) == json.dumps(b)


@pytest.mark.red_team
def test_active_country_raises_on_active_active_collision():
    """Two distinct entities both observed at the same latest month under one
    code is a data error, not a resolvable retirement — silently picking a
    winner would relabel a whole country (#242)."""
    mod = _load_script()
    c_raw = pd.DataFrame(
        {
            "month_id": [500, 500, 100],
            "country_id": [196, 240, 196],
            "isoab": ["YEM", "YEM", "YEM"],
            "name": ["A", "B", "A"],
        }
    )
    with pytest.raises(ValueError, match="active-active collision.*YEM"):
        mod.active_country_by_isoab(c_raw)


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
    # max_month_id.country is always an int; .priogrid is intentionally
    # NULLABLE — the GAUL harvest is a static assignment with no month
    # dimension (#246 documents the int -> null contract change of #231).
    assert isinstance(stamp["max_month_id"]["country"], int)
    assert stamp["max_month_id"]["priogrid"] is None or isinstance(
        stamp["max_month_id"]["priogrid"], int
    )


@pytest.mark.green_team
def test_stamp_datafactory_coverage_accounting():
    """'Coverage loss is declared, not silent' must be test-pinned (#246):
    for a datafactory-sourced stamp, the coverage keys exist and the three
    buckets partition the full 259,200-cell grid exactly."""
    stamp = json.loads((_DATA / "stamp.json").read_text())
    ps = stamp["priogrid_source"]
    if not str(ps.get("source", "")).startswith("views-datafactory"):
        pytest.skip("bundle not built from the datafactory source")
    for key in (
        "source_sha256",
        "crosswalk",
        "unassigned_cells",
        "unmatched_cells",
        "unmatched_iso3",
        "known_gaul_absorptions",
    ):
        assert key in ps, f"priogrid_source missing {key!r}"
    assert (
        ps["unassigned_cells"] + ps["unmatched_cells"] + stamp["rows"]["priogrid"]
        == 259_200
    ), "matched + unmatched + unassigned must partition the full grid"
    assert sum(ps["unmatched_iso3"].values()) == ps["unmatched_cells"]


@pytest.mark.green_team
def test_stamp_declares_kosovo_absorption_and_bundle_agrees():
    """The GAUL Kosovo->Serbia absorption is declared AND bound to the built
    table (#249): the declared gids are present, Kosovo's own country_id
    holds zero cells, so declaration and bundle cannot silently drift."""
    stamp = json.loads((_DATA / "stamp.json").read_text())
    absorptions = stamp["priogrid_source"]["known_gaul_absorptions"]
    kosovo = next(v for k, v in absorptions.items() if "Kosovo" in k)
    assert kosovo["cells"] == 10 and len(kosovo["gids"]) == 10
    pg = pd.read_parquet(_DATA / "priogrid.parquet")
    by_gid = pg.set_index("priogrid_id")["country_id"]
    declared = by_gid.reindex(kosovo["gids"])
    assert declared.notna().all(), "declared absorption gids missing from bundle"
    assert declared.nunique() == 1, "absorbed gids map to more than one country"
    assert not (pg["country_id"] == kosovo["absorbed_views_country_id"]).any()


@pytest.mark.red_team
def test_write_bundle_rejects_underdeclared_provenance(tmp_path):
    """The stamp is the C-112 contract — a provenance dict missing its
    source's required inner keys must fail loud at write time, not ship an
    under-declared stamp (#246)."""
    mod = _load_script()
    country = pd.DataFrame({"country_id": [1], "isoab": ["NOR"], "name": ["Norway"]})
    priogrid = pd.DataFrame({"priogrid_id": [1], "country_id": [1]})
    with pytest.raises(ValueError, match="missing required keys"):
        mod.write_bundle(
            country,
            priogrid,
            querysets=["country_metadata (country_month)"],
            country_max_month=500,
            priogrid_max_month=None,
            priogrid_provenance={"source": "views-datafactory gaul_admin"},
            out_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="unrecognized source"):
        mod.write_bundle(
            country,
            priogrid,
            querysets=["country_metadata (country_month)"],
            country_max_month=500,
            priogrid_max_month=None,
            priogrid_provenance={"source": "something else"},
            out_dir=tmp_path,
        )


@pytest.mark.green_team
def test_stamp_sha_keys_match_harvest_files_read():
    """The provenance sha256 keys and the files read_gaul_cells consumes come
    from ONE constant (#244) — the stamp can only pin the identity of the
    files that were actually crosswalked."""
    mod = _load_script()
    stamp = json.loads((_DATA / "stamp.json").read_text())
    ps = stamp["priogrid_source"]
    if not str(ps.get("source", "")).startswith("views-datafactory"):
        pytest.skip("bundle not built from the datafactory source")
    assert set(ps["source_sha256"].keys()) == set(mod.GAUL_HARVEST_FILES)


@pytest.mark.green_team
def test_priogrid_covers_global_land_surface():
    """Row floor (#245): the PGM identity table spans global land on the 0.5°
    grid (~66k today). A regen silently dropping a region still passes schema,
    uniqueness, subset and checksum checks (a regen rewrites stamp+parquet
    together, so checksums always match themselves) — this floor is the only
    net that watches magnitude. Floor 60k leaves headroom for boundary churn
    while catching continent-scale drops."""
    df = pd.read_parquet(_DATA / "priogrid.parquet")
    assert len(df) > 60_000, (
        f"priogrid has only {len(df)} cells — global land coverage is ~66k; "
        "a regen may have dropped a region. Inspect the crosswalk stats in "
        "stamp.json before committing."
    )


@pytest.mark.green_team
def test_priogrid_spans_widely_separated_continents():
    """Continental canaries (#245): stable interior cells on three continents
    catch a regional drop that stays above the aggregate row floor. gids are
    permanent grid coordinates, not entity ids — they survive border churn."""
    gids = set(pd.read_parquet(_DATA / "priogrid.parquet")["priogrid_id"])
    canaries = {
        "Europe (Ukraine)": 193387,
        "South America (Brazil)": 116140,
        "Asia (India)": 162510,
    }
    missing = {region: g for region, g in canaries.items() if g not in gids}
    assert not missing, f"continental coverage gap — cells absent: {missing}"


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
