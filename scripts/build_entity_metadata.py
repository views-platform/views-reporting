"""Regenerate the bundled entity-metadata assets (views_reporting/metadata/data/).

Why (register C-22 / C-112, ADR-018): reports must render offline / air-gapped —
the render path reads these committed parquets instead of querying viewser at
render time. The viewser fetch happens HERE, once, at dev time; never at runtime
and never in CI. ``stamp.json`` records snapshot date, versions, row counts,
``max_month_id`` and per-file sha256 so staleness/integrity are observable
(C-112: version + source-date stamp, documented cadence, integrity check).

When to refresh: when VIEWS adds/renames/retires countries, when the grid
coverage expands (e.g. the global rollout), roughly annually otherwise — or
whenever the join-coverage contract test (tests/test_metadata_contract.py)
starts failing. Then commit the three regenerated files.

How to run (needs viewser + VIEWS DB access — NOT available in CI):

    conda run -n views_pipeline python scripts/build_entity_metadata.py

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

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent.parent / "views_reporting" / "metadata" / "data"

PRIOGRID_SEMANTICS = (
    "latest known assignment per cell; months before a border change are "
    "labelled with the current country (declared limitation, see epic #204)"
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
    priogrid_max_month: int,
    n_null_cells: int,
    out_dir: Path = OUT_DIR,
) -> dict:
    """Write the two parquets + stamp.json; return the stamp dict."""
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
        "querysets": ["country_metadata (country_month)", "pg_metadata (priogrid_month)"],
        "viewser_version": viewser_version,
        "pandas_version": pd.__version__,
        "pyarrow_version": pyarrow.__version__,
        "rows": {"country": int(len(country)), "priogrid": int(len(priogrid))},
        "max_month_id": {"country": country_max_month, "priogrid": priogrid_max_month},
        "null_country_cells_dropped": n_null_cells,
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


def main() -> int:
    print("Fetching country_metadata (country_month) ...", flush=True)
    c_raw = fetch_country()
    print(f"  fetched {len(c_raw):,} rows, columns: {list(c_raw.columns)}", flush=True)
    print("Fetching pg_metadata (priogrid_month) ...", flush=True)
    pg_raw = fetch_priogrid()
    print(f"  fetched {len(pg_raw):,} rows, columns: {list(pg_raw.columns)}", flush=True)

    country = reduce_country(c_raw)
    priogrid, n_null = reduce_priogrid(pg_raw)
    stamp = write_bundle(
        country,
        priogrid,
        country_max_month=int(c_raw["month_id"].max()),
        priogrid_max_month=int(pg_raw["month_id"].max()),
        n_null_cells=n_null,
    )
    print(json.dumps(stamp, indent=2))
    print(f"\nWrote {OUT_DIR}/country.parquet ({len(country):,} rows), "
          f"priogrid.parquet ({len(priogrid):,} rows), stamp.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
