"""Loader for numpy-stored PredictionFrame predictions (sample estimates)."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from views_pipeline_core.data.handlers import CMDataset, PGMDataset
from views_pipeline_core.data.prediction_frame import PredictionFrame
from views_pipeline_core.managers.prediction.prediction_frame_converter import (
    PredictionFrameConverter,
)

from views_reporting.loaders._constants import DATASET_CLASSES, INDEX_NAMES


class PredictionFrameLoader:
    """Load predictions from numpy PredictionFrame directories."""

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> Union[CMDataset, PGMDataset]:
        if level not in DATASET_CLASSES:
            raise ValueError(
                f"Unknown level '{level}'. Expected one of: {sorted(DATASET_CLASSES)}"
            )

        converter = PredictionFrameConverter()
        dfs = []
        for target in targets:
            target_dir = Path(path) / target
            pf = PredictionFrame.load(target_dir)
            df = converter.to_prediction_df(pf, target)
            dfs.append(df)

        merged = dfs[0] if len(dfs) == 1 else dfs[0].join(dfs[1:])
        merged.index = merged.index.set_names(INDEX_NAMES[level])
        return DATASET_CLASSES[level](merged)

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[Union[CMDataset, PGMDataset]]:
        return [self.load_single_origin(p, level, targets) for p in paths]
