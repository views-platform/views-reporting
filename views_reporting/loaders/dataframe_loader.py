"""Loader for parquet-stored DataFrame predictions (point estimates).

Also hosts the in-memory DataFrame → frame helpers (``frames_from_dataframe`` /
``target_frame_from_dataframe``) the report templates use to convert pre-loaded
forecast/historical DataFrames into ``views_frames`` frames (epic #137, #138).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from views_frames import (
    PredictionFrame,
    SpatialLevel,
    SpatioTemporalIndex,
    TargetFrame,
)

from views_reporting.loaders._constants import LEVELS


def _resolve_level(level: str) -> SpatialLevel:
    if level not in LEVELS:
        raise ValueError(
            f"Unknown level '{level}'. Expected one of: {sorted(LEVELS)}"
        )
    return LEVELS[level]


def _stack_cells(values: pd.Series) -> np.ndarray:
    """Stack a column of prediction cells into an ``(N, S)`` float32 array.

    Each cell is either a scalar point estimate (→ S == 1) or a 1-D sample array
    (→ S == sample_count). Scalars and arrays are normalised to the same width.
    """
    rows = [np.atleast_1d(np.asarray(v, dtype=np.float32)) for v in values]
    return np.stack(rows).astype(np.float32)


def _index_from_dataframe(
    df: pd.DataFrame, level: SpatialLevel
) -> SpatioTemporalIndex:
    """Build a per-row SpatioTemporalIndex from a (time, entity) MultiIndex.

    The index is taken row-by-row from the frame's own MultiIndex (NOT a
    from-product reconstruction) so a sparse grid round-trips faithfully.
    Levels are read **positionally** (level 0 = time, level 1 = entity) — the
    time-first ordering is the contract — so a PGM parquet whose entity level is
    named ``priogrid_gid`` rather than ``priogrid_id`` still loads.
    """
    time = df.index.get_level_values(0).to_numpy(dtype=np.int64)
    unit = df.index.get_level_values(1).to_numpy(dtype=np.int64)
    return SpatioTemporalIndex(time=time, unit=unit, level=level)


def target_frame_from_dataframe(
    df: pd.DataFrame, level: str, target: str
) -> TargetFrame:
    """Build a single-target ``TargetFrame`` (observed actuals) from a df.

    ``target`` is the bare target name (e.g. ``ged_sb``); the column is read
    verbatim. Cells are scalar observations → an ``(N, 1)`` value array.
    """
    spatial_level = _resolve_level(level)
    if target not in df.columns:
        raise ValueError(
            f"Target column '{target}' not found in historical DataFrame "
            f"(columns: {list(df.columns)})"
        )
    values = _stack_cells(df[target])
    index = _index_from_dataframe(df, spatial_level)
    return TargetFrame(values, index)


def frames_from_dataframe(
    df: pd.DataFrame, level: str, targets: list[str]
) -> dict[str, PredictionFrame]:
    """Build a ``dict[target -> PredictionFrame]`` from a forecast df.

    For each bare ``target`` the ``pred_{target}`` column is stacked into an
    ``(N, S)`` frame on a per-row index. **Fails loud** with ``ValueError`` when
    none of the requested ``pred_*`` columns are present — the no-prediction
    contract ``test_loaders`` and the evaluation graceful-skip rely on.
    """
    spatial_level = _resolve_level(level)
    index = _index_from_dataframe(df, spatial_level)

    frames: dict[str, PredictionFrame] = {}
    for target in targets:
        col = f"pred_{target}"
        if col not in df.columns:
            continue
        values = _stack_cells(df[col])
        frames[target] = PredictionFrame(values, index)

    if not frames:
        raise ValueError(
            "No usable prediction columns found in DataFrame for targets "
            f"{targets} (expected one of {[f'pred_{t}' for t in targets]}; "
            f"columns present: {list(df.columns)})"
        )
    return frames


class DataFrameLoader:
    """Load predictions from parquet files into per-target PredictionFrames."""

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> dict[str, PredictionFrame]:
        _resolve_level(level)
        df = pd.read_parquet(path)
        return frames_from_dataframe(df, level, targets)

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[dict[str, PredictionFrame]]:
        return [self.load_single_origin(p, level, targets) for p in paths]
