"""Entity metadata accessors, keyed by (time, entity) index + SpatialLevel.

The legacy dataset-parameter accessors (``get_pg_*(pg_dataset)`` /
``get_c_*(c_dataset)`` / ``get_name(dataset)``), which annotated pipeline-core's
private ``_CDataset``/``_PGDataset``/``_ViewsDataset`` handlers, were deleted as
dead code (register C-114, epic #137): the render path consumes only the
index-keyed ``*_for_index`` accessors below, and nothing on the platform called
the dataset forms. The viewser fetch itself is unchanged (C-22 / Phase 3).
"""

from __future__ import annotations

import pandas as pd
from views_frames import SpatialLevel
from viewser import Column, Queryset

# ── Level-keyed metadata cache (epic #137, #138) ───────────────────────────
# The viewser metadata querysets are level-properties, not dataset-properties:
# the same CM/PGM metadata serves every frame at that level. They are fetched
# once per level and memoised here, keyed by SpatialLevel, and indexed by the
# level's (time, entity) MultiIndex; the ``*_for_index`` accessors read from
# this single cache. The viewser fetch itself is unchanged (C-22 / Phase 3).

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
