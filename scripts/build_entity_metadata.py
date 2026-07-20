"""Regenerate the bundled entity-metadata assets (views_reporting/metadata/data/).

Why (register C-22 / C-112, ADR-018): reports must render offline / air-gapped —
the render path reads these committed parquets instead of querying a service at
render time. All fetching happens HERE, once, at dev time; never at runtime and
never in CI. ``stamp.json`` records snapshot date, versions, row counts,
``max_month_id`` and per-file sha256 so staleness/integrity are observable
(C-112: version + source-date stamp, documented cadence, integrity check).

Source seam (the adapter layer — epic #230, issue #231): the runtime accessors
depend ONLY on the bundle schema contract (``country.parquet``:
country_id → isoab/name; ``priogrid.parquet``: priogrid_id → country_id).
This script is where coding systems are reconciled into that contract, so
sources can change without touching a single runtime call site:

- ``country``: viewser ``country_metadata`` queryset (global; unchanged).
- ``priogrid`` DEFAULT ``datafactory``: the views-datafactory GAUL-2024 admin
  harvest (global, 259,200 cells) crosswalked GAUL ``iso3_code`` → VIEWS
  ``isoab`` → ``country_id``. **This crosswalk is a declared INTERIM handover
  solution** (decision on #231): viewser's pgm loa is still Africa+ME-bounded
  while the datafactory (which the models already consume) is GAUL-coded with
  no VIEWS crosswalk of its own. The platform's eventual country-coding
  standard is an open decision (GAUL is FAO's coding; other partner codings
  may follow) — when it lands, only this adapter layer changes; a future
  multi-coding bundle would ADD coding columns rather than rewrite accessors.
  Declared limitations (also stamped — every figure below reconciles with
  stamp.json's ``unmatched_cells`` / ``unassigned_cells`` / ``unmatched_iso3``;
  state the denominator, always, #248):
  - Of the 64,818-cell FORECAST land region: 99.50% crosswalks; 322 cells
    (disputed / non-VIEWS territories — Western Sahara, Kashmir, Abyei…)
    carry no VIEWS country and degrade to the runtime's visible-NaN path.
  - GRID-WIDE: 29,373 of 95,578 GAUL-coded land cells are unmatched,
    dominated by Antarctica (25,444) and Greenland (3,038) — bulk regions
    outside the VIEWS forecast scope, not disputed-territory footnotes.
  - ~157 border cells (~1% of the old Africa+ME scope) differ from the
    retired viewser assignment because GAUL 2024 and the VIEWS DB draw
    borders differently.
  - Declared absorptions (KNOWN_GAUL_ABSORPTIONS, #249): GAUL codes some
    VIEWS-tracked territories under another country (Kosovo -> SRB), which
    the unmatched accounting cannot see; the stamp declares them explicitly.
- ``priogrid`` legacy ``viewser``: the pre-#231 ``pg_metadata`` queryset
  (kept for comparison/fallback; regional until the pgm loa goes global).

When to refresh: when VIEWS adds/renames/retires countries, when the grid
coverage expands, when the GAUL harvest is re-run, roughly annually otherwise —
or whenever the join-coverage contract test (tests/test_metadata_contract.py)
starts failing. Then commit the three regenerated files.

How to run (needs viewser + a local views-datafactory checkout with the
gaul_admin harvest — NOT available in CI):

    conda run -n views_pipeline python scripts/build_entity_metadata.py \
        [--priogrid-source datafactory|viewser] [--gaul-dir PATH]

Reduction semantics:
- ``groupby(entity).last()`` over the FULL fetched history (NOT the latest
  month): the last month contains only currently-existing states, so a
  latest-month snapshot would silently drop retired entities and strip labels
  from historical frames. ``last()`` keeps every entity ever observed with its
  last-known attributes (also picks up renames, e.g. Eswatini).
- PGM declared limitation: ``priogrid.parquet`` stores the LATEST known country
  assignment per cell — historical months before a border change (e.g. the 2011
  secession) will be labelled with the current assignment. Its only consumer is
  the PGM-choropleth hover label (cosmetic); upgradeable to interval encoding
  inside one function if a historical-PGM product ever needs exact-era labels.
- Cells with no country assignment in ANY month are dropped from the parquet
  (the runtime treats absent entities as unknown: NaN label + loud warning);
  the dropped count is recorded in the stamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "views_reporting" / "metadata" / "data"

# Dev-time convenience default: a sibling views-datafactory checkout. The
# harvest location is an explicit CLI arg precisely because it is a local-disk
# dependency, not a package one.
DEFAULT_GAUL_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "views-datafactory" / "data" / "raw" / "gaul_admin"
)

PRIOGRID_SEMANTICS = (
    "latest known assignment per cell; months before a border change are "
    "labelled with the current country (declared limitation, see epic #204). "
    "Since #231 the assignment is a static GAUL-2024 snapshot crosswalked to "
    "VIEWS country ids (interim handover — see stamp priogrid_source)"
)


# ── Fetch (viewser imported lazily — dev-time only) ─────────────────────────


def fetch_country() -> pd.DataFrame:
    """The country_month metadata queryset (same definition the runtime used
    pre-C-22, so the snapshot is a faithful freeze of what was fetched live)."""
    from viewser import Column, Queryset

    return (
        (
            Queryset("country_metadata", "country_month")
            .with_column(Column("isoab", from_loa="country", from_column="isoab"))
            .with_column(Column("name", from_loa="country", from_column="name"))
            .with_column(Column("gwcode", from_loa="country", from_column="gwcode"))
            .with_column(Column("isonum", from_loa="country", from_column="isonum"))
            .with_column(Column("capname", from_loa="country", from_column="capname"))
            .with_column(Column("caplat", from_loa="country", from_column="caplat"))
            .with_column(Column("caplong", from_loa="country", from_column="caplong"))
            .with_column(Column("in_africa", from_loa="country", from_column="in_africa"))
            .with_column(Column("in_me", from_loa="country", from_column="in_me"))
            .with_column(Column("year_id", from_loa="country_year", from_column="year_id"))
        )
        .publish()
        .fetch()
        .reset_index()
    )


def fetch_priogrid() -> pd.DataFrame:
    """The priogrid_month metadata queryset (same definition as pre-C-22)."""
    from viewser import Column, Queryset

    df = (
        (
            Queryset("pg_metadata", "priogrid_month")
            .with_column(Column("lat", from_loa="priogrid", from_column="latitude"))
            .with_column(Column("long", from_loa="priogrid", from_column="longitude"))
            .with_column(Column("gwcode", from_loa="country", from_column="gwcode"))
            .with_column(Column("row", from_loa="priogrid", from_column="row"))
            .with_column(Column("col", from_loa="priogrid", from_column="col"))
            .with_column(Column("year_id", from_loa="priogrid_year", from_column="year_id"))
            .with_column(Column("isoab", from_loa="country", from_column="isoab"))
            .with_column(Column("name", from_loa="country", from_column="name"))
            .with_column(
                Column("country_id", from_loa="country_month", from_column="country_id")
            )
        )
        .publish()
        .fetch()
        .reset_index()
    )
    if "priogrid_gid" in df.columns:
        df = df.rename(columns={"priogrid_gid": "priogrid_id"})
    return df


# ── Datafactory GAUL source (read + crosswalk; crosswalk is pure) ────────────


# The gaul_admin harvest layout, declared ONCE (#244): read_gaul_cells reads
# these files and main()'s source_sha256 provenance hashes the same tuple, so
# the stamp can never pin the identity of files other than the ones read.
GAUL_HARVEST_FILES = ("iso3_code.parquet", "gaul0_name.parquet")

# The full PRIO-GRID lattice: 360 lat-rows x 720 lon-cols of 0.5 deg cells.
PRIO_GRID_N_CELLS = 259_200

# Known GAUL absorptions (#249): territories VIEWS tracks as their own entity
# but GAUL folds into another country's code. These cells crosswalk to the
# absorbing country with NO trace in the unmatched accounting (their code is
# valid), so the stamp must declare them explicitly — silent territorial
# misattribution in a partner-facing artifact is exactly what the stamp exists
# to prevent. Validated against the built table at regen time (a harvest that
# starts coding these cells differently makes this declaration stale and the
# build fails loud). The platform-level coding decision is tracked in
# views-datafactory#341 / views-postprocessing#123.
KNOWN_GAUL_ABSORPTIONS = {
    "Kosovo -> SRB/Serbia": {
        "absorbed_views_country_id": 232,  # VIEWS Kosovo (null isoab)
        "absorbing_iso3": "SRB",
        "cells": 10,
        "gids": [190482, 190483, 191201, 191202, 191203, 191204,
                 191921, 191922, 191923, 191924],
        "note": (
            "GAUL 2024 has no Kosovo unit; its territory is coded SRB, so "
            "these cells crosswalk to VIEWS Serbia. VIEWS Kosovo "
            "(country_id 232) receives zero cells. Decision venue: "
            "views-datafactory#341 / views-postprocessing#123."
        ),
    },
}


def validate_absorptions(
    priogrid: pd.DataFrame, isoab_to_country: pd.Series
) -> None:
    """Bind KNOWN_GAUL_ABSORPTIONS to the built table (#249): every declared
    gid must exist and map to the absorbing country, and the absorbed VIEWS
    entity must hold zero cells. If a new harvest codes these cells
    differently, the declaration is stale — fail loud so it gets updated."""
    by_gid = priogrid.set_index("priogrid_id")["country_id"]
    for label, spec in KNOWN_GAUL_ABSORPTIONS.items():
        absorbing_id = isoab_to_country.get(spec["absorbing_iso3"])
        got = by_gid.reindex(spec["gids"])
        if got.isna().any() or not (got == absorbing_id).all():
            raise ValueError(
                f"Declared absorption {label!r} no longer matches the built "
                f"table (expected all {len(spec['gids'])} gids -> country_id "
                f"{absorbing_id}) — the harvest's coding changed; update "
                "KNOWN_GAUL_ABSORPTIONS."
            )
        if (priogrid["country_id"] == spec["absorbed_views_country_id"]).any():
            raise ValueError(
                f"Declared absorption {label!r} claims VIEWS country_id "
                f"{spec['absorbed_views_country_id']} holds zero cells, but "
                "the built table assigns it cells — update "
                "KNOWN_GAUL_ABSORPTIONS."
            )


def read_gaul_cells(gaul_dir: Path) -> pd.DataFrame:
    """Per-cell GAUL attributes from the views-datafactory ``gaul_admin``
    harvest: ``gid``, ``iso3`` (GAUL iso3_code), ``gaul0_name``. Full
    259,200-cell grid; ocean/unassigned cells carry a null/empty code.

    Fail-loud input validation (#239/#240, ADR-008): the two files must be
    parallel views of the same complete harvest — unique gids, identical gid
    sets, all 259,200 cells. Without these checks a duplicate gid dies in an
    opaque pandas reindex error and a partial/mismatched harvest silently
    NaN-fills, rebucketing real cells as "unassigned" (and a ~200k-cell
    partial harvest would still clear main()'s 50k output floor)."""
    iso_file, name_file = GAUL_HARVEST_FILES
    iso = pd.read_parquet(gaul_dir / iso_file).set_index("gid")["value"]
    name = pd.read_parquet(gaul_dir / name_file).set_index("gid")["value"]

    for fname, series in ((iso_file, iso), (name_file, name)):
        if not series.index.is_unique:
            n_dup = int(series.index.duplicated().sum())
            raise ValueError(
                f"{fname} has {n_dup} duplicate gid(s) — the gaul_admin "
                "harvest must be one row per cell."
            )
    mismatch = iso.index.symmetric_difference(name.index)
    if len(mismatch) > 0:
        only_iso = iso.index.difference(name.index)
        only_name = name.index.difference(iso.index)
        raise ValueError(
            f"{iso_file} and {name_file} cover different gid sets "
            f"({len(only_iso)} only in {iso_file}, {len(only_name)} only in "
            f"{name_file}; e.g. {list(mismatch[:5])}) — they must be parallel "
            "views of the same harvest."
        )
    if len(iso) != PRIO_GRID_N_CELLS:
        raise ValueError(
            f"GAUL harvest has {len(iso):,} cells, expected the full "
            f"{PRIO_GRID_N_CELLS:,}-cell PRIO-GRID (360 rows x 720 cols). "
            f"Partial/corrupt harvest or wrong --gaul-dir: {gaul_dir}. "
            "Refusing to build an incomplete 'global' bundle."
        )

    out = pd.DataFrame({"iso3": iso, "gaul0_name": name})
    out.index.name = "gid"
    return out.reset_index()


def active_country_by_isoab(country_raw: pd.DataFrame) -> pd.Series:
    """``isoab → country_id`` of the entity most recently observed under that
    ISO code. VIEWS isoab is NOT unique over history (retired states — e.g.
    pre-unification Yemen — share a code with their successor); the crosswalk
    must resolve each code to the currently-active entity, which is the one
    whose observations extend furthest in time.

    Fail-loud on ACTIVE-ACTIVE collisions (#242): retirement is resolvable
    ambiguity (the data says which entity is current), but two distinct
    entities both observed at the same latest month under one code is a data
    error — silently picking a winner would relabel every cell of a whole
    country. Raise instead."""
    per_entity = (
        country_raw.dropna(subset=["isoab"])
        .groupby(["isoab", "country_id"])["month_id"]
        .max()
        .reset_index()
        .sort_values(["isoab", "month_id", "country_id"])
    )
    latest = per_entity.groupby("isoab")["month_id"].transform("max")
    at_latest = per_entity[per_entity["month_id"] == latest]
    tied = at_latest.groupby("isoab")["country_id"].nunique()
    tied = tied[tied > 1]
    if len(tied) > 0:
        details = {
            str(code): {
                "country_ids": sorted(
                    int(c)
                    for c in at_latest.loc[
                        at_latest["isoab"] == code, "country_id"
                    ]
                ),
                "month_id": int(
                    at_latest.loc[at_latest["isoab"] == code, "month_id"].iloc[0]
                ),
            }
            for code in tied.index
        }
        raise ValueError(
            f"isoab active-active collision(s): {details} — multiple entities "
            "observed at the same latest month under one code. Data error in "
            "the country source, not a resolvable retirement."
        )
    return per_entity.groupby("isoab")["country_id"].last()


def crosswalk_priogrid(
    gaul_cells: pd.DataFrame, isoab_to_country: pd.Series
) -> tuple[pd.DataFrame, dict]:
    """GAUL cells → the bundle's ``priogrid_id → country_id`` table (INTERIM
    handover crosswalk, #231): GAUL ``iso3`` matched against VIEWS ``isoab``.

    Returns ``(table, stats)``. Cells fall in three buckets:
    - matched → in the table;
    - **unassigned** (null/empty iso3: ocean, no-code cells) → dropped, counted;
    - **unmatched** (a real code with no VIEWS country: disputed territories
      like Western Sahara/Kashmir, non-VIEWS territories like Greenland) →
      dropped, counted per code so the stamp declares exactly what is missing.
    """
    # Normalize ONCE: the bucket mask, the country lookup, and the unmatched
    # histogram must all read the same value (#241 — a padded code like
    # 'NOR ' would otherwise pass has_code yet miss the map and be silently
    # dropped as "unmatched" under a mangled key). Whitespace-strip only: NO
    # case-folding — GAUL's lowercase x-prefixed disputed codes (xJK, xAB…)
    # are intentionally non-matching and must keep their exact spelling.
    iso3 = gaul_cells["iso3"].astype("string").str.strip()
    has_code = iso3.notna() & (iso3 != "")
    country_id = iso3.map(isoab_to_country)
    matched = country_id.notna()

    out = pd.DataFrame(
        {
            "priogrid_id": gaul_cells.loc[matched, "gid"].astype("int32"),
            "country_id": country_id[matched].astype("int32"),
        }
    )
    if out["priogrid_id"].duplicated().any():
        raise ValueError("priogrid_id is not unique after crosswalk")
    unmatched = gaul_cells.loc[has_code & ~matched]
    counts = unmatched.groupby(iso3[unmatched.index])["gid"].count()
    stats = {
        "unassigned_cells": int((~has_code).sum()),
        "unmatched_cells": int(len(unmatched)),
        # Deterministic total order (#243): (-count, code). The committed
        # stamp must be byte-reproducible — pandas' unstable sort reshuffled
        # tied counts between runs/toolchains, churning provenance diffs.
        "unmatched_iso3": {
            str(code): int(n)
            for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        },
    }
    return out.sort_values("priogrid_id").reset_index(drop=True), stats


# ── Reduce (pure — unit-tested without viewser) ─────────────────────────────


def reduce_country(df: pd.DataFrame) -> pd.DataFrame:
    """``country_id → isoab, name``: last non-null per entity over the full
    history (keeps retired entities; picks up renames)."""
    out = (
        df.sort_values("month_id")
        .groupby("country_id")[["isoab", "name"]]
        .last()  # skips NaN — last *valid* value per column
        .reset_index()
    )
    out["country_id"] = out["country_id"].astype("int32")
    out["isoab"] = out["isoab"].astype("string")
    out["name"] = out["name"].astype("string")
    if out["country_id"].duplicated().any():
        raise ValueError("country_id is not unique after reduction")
    return out.sort_values("country_id").reset_index(drop=True)


def reduce_priogrid(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """``priogrid_id → country_id``: last non-null assignment per cell.

    Returns ``(table, n_cells_dropped)`` — cells with no country in any month
    are dropped (recorded in the stamp; the runtime treats them as unknown).
    """
    last = (
        df.sort_values("month_id")
        .groupby("priogrid_id")["country_id"]
        .last()
    )
    n_null = int(last.isna().sum())
    out = last.dropna().astype("int32").reset_index()
    out["priogrid_id"] = out["priogrid_id"].astype("int32")
    if out["priogrid_id"].duplicated().any():
        raise ValueError("priogrid_id is not unique after reduction")
    return out.sort_values("priogrid_id").reset_index(drop=True), n_null


# ── Write ────────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Per-source inner-key contract for the stamp's priogrid_source block
# (#246): the stamp is the C-112 observability contract, so its shape is
# validated at write time — a malformed provenance dict fails loud instead of
# shipping a stamp that silently under-declares coverage loss.
_PROVENANCE_REQUIRED_KEYS = {
    "views-datafactory": {
        "source", "source_sha256", "crosswalk", "unassigned_cells",
        "unmatched_cells", "unmatched_iso3", "known_gaul_absorptions",
    },
    "viewser": {"source", "null_country_cells_dropped"},
}


def write_bundle(
    country: pd.DataFrame,
    priogrid: pd.DataFrame,
    *,
    querysets: list[str],
    country_max_month: int,
    priogrid_max_month: int | None,
    priogrid_provenance: dict,
    out_dir: Path = OUT_DIR,
) -> dict:
    """Write the two parquets + stamp.json; return the stamp dict.

    ``querysets`` must list exactly the querysets the calling branch actually
    fetched (#246 — the viewser priogrid branch fetches pg_metadata too).
    ``priogrid_provenance`` is the source-specific stamp block (the adapter
    seam made observable): which source produced the cell→country table and,
    for the interim GAUL crosswalk, exactly what it could not map. Its inner
    keys are validated against the per-source contract above.
    ``priogrid_max_month`` is None for month-less sources (the GAUL harvest
    is a static assignment, not a month-indexed queryset).
    """
    source = str(priogrid_provenance.get("source", ""))
    required = next(
        (
            keys
            for prefix, keys in _PROVENANCE_REQUIRED_KEYS.items()
            if source.startswith(prefix)
        ),
        None,
    )
    if required is None:
        raise ValueError(
            f"priogrid_provenance has unrecognized source {source!r} — "
            f"expected one starting with {sorted(_PROVENANCE_REQUIRED_KEYS)}."
        )
    missing = required - set(priogrid_provenance)
    if missing:
        raise ValueError(
            f"priogrid_provenance for source {source!r} is missing required "
            f"keys {sorted(missing)} — refusing to write an under-declared "
            "stamp (C-112)."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    country_path = out_dir / "country.parquet"
    priogrid_path = out_dir / "priogrid.parquet"
    country.to_parquet(country_path, index=False)
    priogrid.to_parquet(priogrid_path, index=False)

    import pyarrow

    try:
        import viewser

        viewser_version = getattr(viewser, "__version__", "unknown")
    except ImportError:  # stamp still writable from a reduce-only context
        viewser_version = "unavailable"

    stamp = {
        "snapshot_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "querysets": list(querysets),
        "priogrid_source": priogrid_provenance,
        "viewser_version": viewser_version,
        "pandas_version": pd.__version__,
        "pyarrow_version": pyarrow.__version__,
        "rows": {"country": int(len(country)), "priogrid": int(len(priogrid))},
        "max_month_id": {"country": country_max_month, "priogrid": priogrid_max_month},
        # Entities the SOURCE serves without an ISO code (e.g. Kosovo has no
        # official alpha-3). Kept as-is — the bundle freezes reality; these
        # drop from CM maps exactly as they did under live viewser.
        "null_isoab_countries": sorted(country.loc[country["isoab"].isna(), "name"]),
        "priogrid_semantics": PRIOGRID_SEMANTICS,
        # Integrity bind (stamp <-> files edited together), NOT a
        # cross-pyarrow-version reproducibility guarantee.
        "sha256": {
            "country.parquet": _sha256(country_path),
            "priogrid.parquet": _sha256(priogrid_path),
        },
    }
    (out_dir / "stamp.json").write_text(json.dumps(stamp, indent=2) + "\n")
    return stamp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--priogrid-source",
        choices=["datafactory", "viewser"],
        default="datafactory",
        help="cell→country source: 'datafactory' (GAUL harvest + ISO3 "
        "crosswalk, global — the interim default, #231) or 'viewser' "
        "(legacy pg_metadata queryset; regional until the pgm loa goes global)",
    )
    parser.add_argument(
        "--gaul-dir",
        type=Path,
        default=DEFAULT_GAUL_DIR,
        help=f"gaul_admin harvest directory (default: {DEFAULT_GAUL_DIR})",
    )
    args = parser.parse_args(argv)

    print("Fetching country_metadata (country_month) ...", flush=True)
    c_raw = fetch_country()
    print(f"  fetched {len(c_raw):,} rows, columns: {list(c_raw.columns)}", flush=True)
    country = reduce_country(c_raw)

    if args.priogrid_source == "datafactory":
        gaul_dir = args.gaul_dir.resolve()
        print(f"Reading GAUL harvest from {gaul_dir} ...", flush=True)
        gaul_cells = read_gaul_cells(gaul_dir)
        print(f"  read {len(gaul_cells):,} cells", flush=True)
        isoab_to_country = active_country_by_isoab(c_raw)
        priogrid, xw_stats = crosswalk_priogrid(gaul_cells, isoab_to_country)
        # Secondary sanity only (#239): input completeness is enforced at
        # cause in read_gaul_cells (== 259,200 cells). This floor remains as
        # defence-in-depth against a crosswalk-side failure (e.g. an all-null
        # iso3 join) that the input count cannot see.
        if len(priogrid) < 50_000:
            raise ValueError(
                f"Crosswalk produced only {len(priogrid):,} cells — a global "
                "GAUL harvest yields ~66k. Corrupt/partial harvest or wrong "
                "--gaul-dir; refusing to write a near-empty bundle."
            )
        validate_absorptions(priogrid, isoab_to_country)
        querysets = ["country_metadata (country_month)"]
        priogrid_max_month: int | None = None
        priogrid_provenance = {
            # Identity is pinned by source_sha256; no machine-local paths in
            # committed provenance (they leak layout + churn between machines).
            "source": "views-datafactory gaul_admin harvest (GAUL 2024)",
            "source_sha256": {
                name: _sha256(gaul_dir / name) for name in GAUL_HARVEST_FILES
            },
            "crosswalk": (
                "INTERIM handover (#231): GAUL iso3_code -> VIEWS isoab -> "
                "country_id; duplicate isoab resolved to the most recently "
                "observed entity"
            ),
            "known_gaul_absorptions": KNOWN_GAUL_ABSORPTIONS,
            **xw_stats,
        }
    else:
        print("Fetching pg_metadata (priogrid_month) ...", flush=True)
        pg_raw = fetch_priogrid()
        print(
            f"  fetched {len(pg_raw):,} rows, columns: {list(pg_raw.columns)}",
            flush=True,
        )
        priogrid, n_null = reduce_priogrid(pg_raw)
        querysets = [
            "country_metadata (country_month)",
            "pg_metadata (priogrid_month)",
        ]
        priogrid_max_month = int(pg_raw["month_id"].max())
        priogrid_provenance = {
            "source": "viewser pg_metadata (priogrid_month) — legacy, regional",
            "null_country_cells_dropped": n_null,
        }

    stamp = write_bundle(
        country,
        priogrid,
        querysets=querysets,
        country_max_month=int(c_raw["month_id"].max()),
        priogrid_max_month=priogrid_max_month,
        priogrid_provenance=priogrid_provenance,
    )
    print(json.dumps(stamp, indent=2))
    print(f"\nWrote {OUT_DIR}/country.parquet ({len(country):,} rows), "
          f"priogrid.parquet ({len(priogrid):,} rows), stamp.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
