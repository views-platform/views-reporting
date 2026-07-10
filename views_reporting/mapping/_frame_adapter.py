"""Frame → mapping DataFrame adapter (epic #137, #138).

The **sole** ``views_frames.PredictionFrame`` → pandas seam on the mapping path.
``frames_to_mapping_df`` reproduces the pre-shapefile DataFrame that
``MappingModule.__add_isoab`` used to build from a pipeline-core dataset: a flat
``[time_id, entity_id, target_column]`` table left-joined with ``isoab`` and
``country_name`` via the index-keyed metadata accessors. ``MappingModule`` then
owns the geopandas merge + plot.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from views_frames import PredictionFrame, SpatialLevel

from views_reporting.metadata import get_isoab_for_index, get_name_for_index


def frames_to_mapping_df(
    frame: PredictionFrame,
    target_column: str,
    level: SpatialLevel,
) -> pd.DataFrame:
    """Flat ``[time_id, entity_id, target_column, isoab, country_name]`` df.

    The rendered value is ``frame.values[:, 0]`` and the frame MUST be a
    collapsed point estimate (S == 1, e.g. a MAP frame) — **enforced** (register
    C-207, ADR-020): posterior samples are numpy-bound and never cross this
    pandas seam. Pre-guard, an uncollapsed frame silently rendered posterior
    draw #0 as the point estimate (probe-confirmed ≠ tower MAP, epic #215).
    Rows come from ``frame.index`` per-row, so a sparse grid is preserved.
    """
    if frame.sample_count > 1:
        raise ValueError(
            f"frames_to_mapping_df received a sample frame (S={frame.sample_count}): "
            "posterior samples never cross the pandas seam (register C-207). "
            "Collapse to a point estimate first — e.g. "
            "views_reporting.statistics.calculate_map_frame(frame, target)."
        )
    time_name, entity_name = level.index_names
    base = pd.DataFrame(
        {
            time_name: np.asarray(frame.index.time, dtype=np.int64),
            entity_name: np.asarray(frame.index.unit, dtype=np.int64),
            target_column: np.asarray(frame.values[:, 0], dtype=np.float32),
        }
    )

    join_index = pd.MultiIndex.from_arrays(
        [base[time_name], base[entity_name]],
        names=[time_name, entity_name],
    )
    iso_df = get_isoab_for_index(join_index, level).reset_index()
    name_df = get_name_for_index(
        join_index, level, with_id=True
    ).reset_index()

    base = base.merge(
        iso_df[[time_name, entity_name, "isoab"]],
        on=[time_name, entity_name],
        how="left",
    )
    base = base.merge(
        name_df[[time_name, entity_name, "name"]],
        on=[time_name, entity_name],
        how="left",
    )
    base.rename(columns={"name": "country_name"}, inplace=True)
    return base
