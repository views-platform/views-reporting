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
  Declared limitations (also stamped): disputed territories and non-VIEWS
  territories (~0.5% of land cells) carry no VIEWS country and degrade to the
  runtime's visible-NaN path; a small band of border cells (~1% of the old
  Africa+ME scope) differs from the retired viewser assignment because GAUL
  2024 and the VIEWS DB draw borders differently.
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


def read_gaul_cells(gaul_dir: Path) -> pd.DataFrame:
    """Per-cell GAUL attributes from the views-datafactory ``gaul_admin``
    harvest: ``gid``, ``iso3`` (GAUL iso3_code), ``gaul0_name``. Full
    259,200-cell grid; ocean/unassigned cells carry a null/empty code."""
    iso = pd.read_parquet(gaul_dir / "iso3_code.parquet").set_index("gid")["value"]
    name = pd.read_parquet(gaul_dir / "gaul0_name.parquet").set_index("gid")["value"]
    out = pd.DataFrame({"iso3": iso, "gaul0_name": name})
    out.index.name = "gid"
    return out.reset_index()


def active_country_by_isoab(country_raw: pd.DataFrame) -> pd.Series:
    """``isoab → country_id`` of the entity most recently observed under that
    ISO code. VIEWS isoab is NOT unique over history (retired states — e.g.
    pre-unification Yemen — share a code with their successor); the crosswalk
    must resolve each code to the currently-active entity, which is the one
    whose observations extend furthest in time. Ties break on country_id."""
    per_entity = (
        country_raw.dropna(subset=["isoab"])
        .groupby(["isoab", "country_id"])["month_id"]
        .max()
        .reset_index()
        .sort_values(["isoab", "month_id", "country_id"])
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
    iso3 = gaul_cells["iso3"].astype("string")
    has_code = iso3.notna() & (iso3.str.strip() != "")
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
    stats = {
        "unassigned_cells": int((~has_code).sum()),
        "unmatched_cells": int(len(unmatched)),
        "unmatched_iso3": {
            str(code): int(n)
            for code, n in unmatched.groupby(iso3[unmatched.index])["gid"]
            .count()
            .sort_values(ascending=False)
            .items()
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


def write_bundle(
    country: pd.DataFrame,
    priogrid: pd.DataFrame,
    *,
    country_max_month: int,
    priogrid_max_month: int | None,
    priogrid_provenance: dict,
    out_dir: Path = OUT_DIR,
) -> dict:
    """Write the two parquets + stamp.json; return the stamp dict.

    ``priogrid_provenance`` is the source-specific stamp block (the adapter
    seam made observable): which source produced the cell→country table and,
    for the interim GAUL crosswalk, exactly what it could not map.
    ``priogrid_max_month`` is None for month-less sources (the GAUL harvest
    is a static assignment, not a month-indexed queryset).
    """
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
        "querysets": ["country_metadata (country_month)"],
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
        priogrid, xw_stats = crosswalk_priogrid(
            gaul_cells, active_country_by_isoab(c_raw)
        )
        if len(priogrid) < 50_000:
            raise ValueError(
                f"Crosswalk produced only {len(priogrid):,} cells — a global "
                "GAUL harvest yields ~66k. Corrupt/partial harvest or wrong "
                "--gaul-dir; refusing to write a near-empty bundle."
            )
        priogrid_max_month: int | None = None
        priogrid_provenance = {
            # Identity is pinned by source_sha256; no machine-local paths in
            # committed provenance (they leak layout + churn between machines).
            "source": "views-datafactory gaul_admin harvest (GAUL 2024)",
            "source_sha256": {
                "iso3_code.parquet": _sha256(gaul_dir / "iso3_code.parquet"),
                "gaul0_name.parquet": _sha256(gaul_dir / "gaul0_name.parquet"),
            },
            "crosswalk": (
                "INTERIM handover (#231): GAUL iso3_code -> VIEWS isoab -> "
                "country_id; duplicate isoab resolved to the most recently "
                "observed entity"
            ),
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
        priogrid_max_month = int(pg_raw["month_id"].max())
        priogrid_provenance = {
            "source": "viewser pg_metadata (priogrid_month) — legacy, regional",
            "null_country_cells_dropped": n_null,
        }

    stamp = write_bundle(
        country,
        priogrid,
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
