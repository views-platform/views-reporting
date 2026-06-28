"""Entity metadata accessors for country and PRIO-GRID datasets."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from views_frames import SpatialLevel
from viewser import Column, Queryset

if TYPE_CHECKING:
    from views_pipeline_core.data.handlers import _CDataset, _PGDataset, _ViewsDataset

logger = logging.getLogger(__name__)


# ── Level-keyed metadata cache (epic #137, #138) ───────────────────────────
# The viewser metadata querysets are level-properties, not dataset-properties:
# the same CM/PGM metadata serves every frame/dataset at that level. They are
# fetched once per level and memoised here, keyed by SpatialLevel, and indexed
# by the level's (time, entity) MultiIndex. The dataset accessors below and the
# new ``*_for_index`` accessors both read from this single cache. The viewser
# fetch itself is unchanged (C-22 / Phase 3) — only the key contract flips
# dataset → MultiIndex.

_LEVEL_METADATA_CACHE: dict[SpatialLevel, pd.DataFrame] = {}


def _fetch_c_metadata() -> pd.DataFrame:
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


def _fetch_pg_metadata() -> pd.DataFrame:
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
        df.rename(columns={"priogrid_gid": "priogrid_id"}, inplace=True)
    return df


def _level_metadata(level: SpatialLevel) -> pd.DataFrame:
    """Fetch (once) and return the level's metadata, indexed by its index_names."""
    cached = _LEVEL_METADATA_CACHE.get(level)
    if cached is not None:
        return cached
    if level == SpatialLevel.CM:
        df = _fetch_c_metadata()
    else:
        df = _fetch_pg_metadata()
    df = df.set_index(list(level.index_names), drop=False)
    _LEVEL_METADATA_CACHE[level] = df
    return df


# ── Index-keyed accessors (frame-native edge) ──────────────────────────────


def get_isoab_for_index(index: pd.MultiIndex, level: SpatialLevel) -> pd.DataFrame:
    """ISO codes for the rows of ``index`` at ``level`` (left-join on identity)."""
    meta = _level_metadata(level)
    return meta["isoab"].reindex(index).to_frame(name="isoab")


def get_name_for_index(
    index: pd.MultiIndex, level: SpatialLevel, with_id: bool = False
) -> pd.DataFrame:
    """Country names for the rows of ``index`` at ``level``.

    With ``with_id`` the value is ``"{country_id} - {name}"`` for PGM (matching
    the legacy ``get_pg_name(with_id=True)``); for CM it is ``"{country_id} -
    {name}"`` too (matching ``get_c_name(with_id=True)``).
    """
    meta = _level_metadata(level)
    if not with_id:
        return meta["name"].reindex(index).to_frame(name="name")
    country_id = meta["country_id"].reindex(index)
    country_name = meta["name"].reindex(index)
    combined = country_id.astype(str) + " - " + country_name
    return combined.to_frame(name="name")


# ── Shared helpers ──────────────────────────────────────────────────────────


def _classify_region_by_gwcode(gwcode: pd.Series) -> pd.DataFrame:
    continent_rules = [
        (gwcode.between(2, 165), "Americas"),
        (gwcode.between(200, 399), "Europe"),
        (gwcode.between(400, 626), "Africa"),
        (gwcode.between(630, 698), "Middle East"),
        (gwcode.between(700, 899), "Asia"),
        (gwcode.between(900, 990), "Oceania"),
        (gwcode == 999, "International"),
    ]
    continent = pd.Series("Other", index=gwcode.index)
    for condition, name in continent_rules:
        continent = continent.where(~condition, name)
    return continent.to_frame(name="continent")


# ── PG metadata cache ──────────────────────────────────────────────────────


def build_pg_metadata_cache(pg_dataset: _PGDataset) -> None:
    if pg_dataset._entity_metadata_cache is not None:
        return
    pg_dataset._entity_metadata_cache = (
        (
            Queryset("pg_metadata", "priogrid_month")
            .with_column(
                Column("lat", from_loa="priogrid", from_column="latitude")
            )
            .with_column(
                Column("long", from_loa="priogrid", from_column="longitude")
            )
            .with_column(
                Column("gwcode", from_loa="country", from_column="gwcode")
            )
            .with_column(Column("row", from_loa="priogrid", from_column="row"))
            .with_column(Column("col", from_loa="priogrid", from_column="col"))
            .with_column(
                Column(
                    "year_id", from_loa="priogrid_year", from_column="year_id"
                )
            )
            .with_column(
                Column("isoab", from_loa="country", from_column="isoab")
            )
            .with_column(Column("name", from_loa="country", from_column="name"))
            .with_column(
                Column(
                    "country_id",
                    from_loa="country_month",
                    from_column="country_id",
                )
            )
        )
        .publish()
        .fetch()
        .reset_index()
    )
    if "priogrid_gid" in pg_dataset._entity_metadata_cache.columns:
        pg_dataset._entity_metadata_cache.rename(
            columns={"priogrid_gid": pg_dataset._entity_id}, inplace=True
        )
    pg_dataset._entity_metadata_cache.set_index(
        [pg_dataset._time_id, pg_dataset._entity_id], inplace=True, drop=False
    )


# ── PG metadata accessors ──────────────────────────────────────────────────


def detect_country_changes(
    pg_dataset: _PGDataset, include_previous_name: bool = False
) -> pd.DataFrame:
    country_df = get_country_id(pg_dataset)

    previous_country = (
        country_df.groupby(level=pg_dataset._entity_id, group_keys=False)
        .shift(1)
        .rename(columns={"country_id": "previous_country_id"})
    )

    current_country_ids = country_df["country_id"]
    missing_mask = previous_country["previous_country_id"].isna()
    previous_country["previous_country_id"] = previous_country[
        "previous_country_id"
    ].fillna(current_country_ids)

    if include_previous_name:
        build_pg_metadata_cache(pg_dataset)

        time_country_names = (
            pg_dataset._entity_metadata_cache.reset_index()[
                [pg_dataset._time_id, "country_id", "name"]
            ]
            .drop_duplicates([pg_dataset._time_id, "country_id"])
            .set_index([pg_dataset._time_id, "country_id"])["name"]
        )

        time_index = previous_country.index.get_level_values(pg_dataset._time_id)
        country_ids = previous_country["previous_country_id"].to_numpy()

        time_offsets = time_index.to_numpy() - np.where(missing_mask, 0, 1)

        lookup_index = pd.MultiIndex.from_arrays(
            [time_offsets, country_ids],
            names=[pg_dataset._time_id, "country_id"],
        )

        previous_country["previous_name"] = (
            time_country_names.reindex(lookup_index)
            .groupby("country_id")
            .ffill()
            .values
        )

    return previous_country.reindex(pg_dataset.dataframe.index)


def get_country_id(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return (
        pg_dataset._entity_metadata_cache["country_id"]
        .reindex(pg_dataset.dataframe.index)
        .to_frame(name="country_id")
    )


def get_pg_lat_lon(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return pd.DataFrame(
        {
            "lat": pg_dataset._entity_metadata_cache["lat"].reindex(
                pg_dataset.dataframe.index
            ),
            "lon": pg_dataset._entity_metadata_cache["long"].reindex(
                pg_dataset.dataframe.index
            ),
        }
    )


def get_pg_row_col(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return pd.DataFrame(
        {
            "row": pg_dataset._entity_metadata_cache["row"].reindex(
                pg_dataset.dataframe.index
            ),
            "col": pg_dataset._entity_metadata_cache["col"].reindex(
                pg_dataset.dataframe.index
            ),
        }
    )


def get_pg_isoab(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return (
        pg_dataset._entity_metadata_cache["isoab"]
        .reindex(pg_dataset.dataframe.index)
        .to_frame(name="isoab")
    )


def get_pg_name(pg_dataset: _PGDataset, with_id: bool = False) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    if not with_id:
        return (
            pg_dataset._entity_metadata_cache["name"]
            .reindex(pg_dataset.dataframe.index)
            .to_frame(name="name")
        )
    else:
        country_id = pg_dataset._entity_metadata_cache["country_id"].reindex(
            pg_dataset.dataframe.index
        )
        country_name = pg_dataset._entity_metadata_cache["name"].reindex(
            pg_dataset.dataframe.index
        )
        combined = country_id.astype(str) + " - " + country_name
        return combined.to_frame(name="name")


def get_pg_region(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    gwcode = pg_dataset._entity_metadata_cache["gwcode"].reindex(
        pg_dataset.dataframe.index
    )
    return _classify_region_by_gwcode(gwcode)


# ── PG temporal accessors ──────────────────────────────────────────────────


def get_pg_year(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return (
        pg_dataset._entity_metadata_cache["year_id"]
        .reindex(pg_dataset.dataframe.index)
        .to_frame(name="year_id")
    )


def get_pg_month(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    return (
        pg_dataset._entity_metadata_cache["month_id"]
        .reindex(pg_dataset.dataframe.index)
        .to_frame(name="month_id")
    )


def get_pg_date(pg_dataset: _PGDataset) -> pd.DataFrame:
    years = get_pg_year(pg_dataset)["year_id"]
    months = get_pg_month(pg_dataset)["month_id"]

    def wrap_month(month_id: int) -> int:
        return (month_id - 1) % 12 + 1

    months = months.apply(wrap_month)
    dates = pd.to_datetime(years.astype(str) + "-" + months.astype(str) + "-01")
    return dates.to_frame(name="date")


def get_pg_month_of_year(pg_dataset: _PGDataset) -> pd.DataFrame:
    build_pg_metadata_cache(pg_dataset)
    months_since_base = pg_dataset._entity_metadata_cache["month_id"].reindex(
        pg_dataset.dataframe.index
    )
    month_of_year = ((months_since_base - 1) % 12) + 1
    return month_of_year.to_frame(name="month")


# ── C metadata cache ───────────────────────────────────────────────────────


def build_c_metadata_cache(c_dataset: _CDataset) -> None:
    if c_dataset._entity_metadata_cache is not None:
        return
    c_dataset._entity_metadata_cache = (
        (
            Queryset("country_metadata", "country_month")
            .with_column(
                Column("isoab", from_loa="country", from_column="isoab")
            )
            .with_column(Column("name", from_loa="country", from_column="name"))
            .with_column(
                Column("gwcode", from_loa="country", from_column="gwcode")
            )
            .with_column(
                Column("isonum", from_loa="country", from_column="isonum")
            )
            .with_column(
                Column("capname", from_loa="country", from_column="capname")
            )
            .with_column(
                Column("caplat", from_loa="country", from_column="caplat")
            )
            .with_column(
                Column("caplong", from_loa="country", from_column="caplong")
            )
            .with_column(
                Column(
                    "in_africa", from_loa="country", from_column="in_africa"
                )
            )
            .with_column(
                Column("in_me", from_loa="country", from_column="in_me")
            )
            .with_column(
                Column(
                    "year_id", from_loa="country_year", from_column="year_id"
                )
            )
        )
        .publish()
        .fetch()
        .reset_index()
        .set_index([c_dataset._time_id, c_dataset._entity_id], drop=False)
    )


# ── C metadata accessors ──────────────────────────────────────────────────


def get_c_isoab(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["isoab"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="isoab")
    )


def get_c_name(c_dataset: _CDataset, with_id: bool = False) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    if not with_id:
        return (
            c_dataset._entity_metadata_cache["name"]
            .reindex(c_dataset.dataframe.index)
            .to_frame(name="name")
        )
    else:
        country_id = c_dataset._entity_metadata_cache["country_id"].reindex(
            c_dataset.dataframe.index
        )
        country_name = c_dataset._entity_metadata_cache["name"].reindex(
            c_dataset.dataframe.index
        )
        combined = country_id.astype(str) + " - " + country_name
        return combined.to_frame(name="name")


def get_c_gwcode(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["gwcode"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="gwcode")
    )


def get_c_isonum(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["isonum"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="isonum")
    )


def get_c_capname(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["capname"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="capname")
    )


def get_c_cap_lat_lon(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return pd.DataFrame(
        {
            "cap_lat": c_dataset._entity_metadata_cache["caplat"].reindex(
                c_dataset.dataframe.index
            ),
            "cap_lon": c_dataset._entity_metadata_cache["caplong"].reindex(
                c_dataset.dataframe.index
            ),
        }
    )


def get_c_region_flags(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return pd.DataFrame(
        {
            "in_africa": c_dataset._entity_metadata_cache["in_africa"].reindex(
                c_dataset.dataframe.index
            ),
            "in_me": c_dataset._entity_metadata_cache["in_me"].reindex(
                c_dataset.dataframe.index
            ),
        }
    )


def get_c_region(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    gwcode = c_dataset._entity_metadata_cache["gwcode"].reindex(
        c_dataset.dataframe.index
    )
    return _classify_region_by_gwcode(gwcode)


# ── C temporal accessors ───────────────────────────────────────────────────


def get_c_year(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["year_id"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="year_id")
    )


def get_c_month(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    return (
        c_dataset._entity_metadata_cache["month_id"]
        .reindex(c_dataset.dataframe.index)
        .to_frame(name="month_id")
    )


def get_c_date(c_dataset: _CDataset) -> pd.DataFrame:
    years = get_c_year(c_dataset)["year_id"]
    months = get_c_month(c_dataset)["month_id"]

    def wrap_month(month_id: int) -> int:
        return (month_id - 1) % 12 + 1

    months = months.apply(wrap_month)
    dates = pd.to_datetime(years.astype(str) + "-" + months.astype(str) + "-01")
    return dates.to_frame(name="date")


def get_c_quarter(c_dataset: _CDataset) -> pd.DataFrame:
    months = get_c_month(c_dataset)["month_id"]
    return ((months - 1) // 3 + 1).to_frame(name="quarter")


def get_c_month_of_year(c_dataset: _CDataset) -> pd.DataFrame:
    build_c_metadata_cache(c_dataset)
    months_since_base = c_dataset._entity_metadata_cache["month_id"].reindex(
        c_dataset.dataframe.index
    )
    month_of_year = ((months_since_base - 1) % 12) + 1
    return month_of_year.to_frame(name="month")


# ── Polymorphic dispatch ───────────────────────────────────────────────────


def _level_for_dataset(dataset: _ViewsDataset) -> SpatialLevel:
    return (
        SpatialLevel.CM if dataset._entity_id == "country_id" else SpatialLevel.PGM
    )


def get_name(dataset: _ViewsDataset, **kwargs) -> pd.DataFrame:
    """Dataset wrapper — delegates to ``get_name_for_index`` (epic #137)."""
    return get_name_for_index(
        dataset.dataframe.index, _level_for_dataset(dataset), **kwargs
    )


def get_isoab(dataset: _ViewsDataset) -> pd.DataFrame:
    """Dataset wrapper — delegates to ``get_isoab_for_index`` (epic #137)."""
    return get_isoab_for_index(
        dataset.dataframe.index, _level_for_dataset(dataset)
    )
