"""Loader for parquet-stored DataFrame predictions (point estimates)."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd
from views_pipeline_core.data.handlers import CMDataset, PGMDataset

_DATASET_CLASSES: dict[str, type] = {"cm": CMDataset, "pgm": PGMDataset}


class DataFrameLoader:
    """Load predictions from parquet files into CMDataset or PGMDataset."""

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> Union[CMDataset, PGMDataset]:
        if level not in _DATASET_CLASSES:
            raise ValueError(
                f"Unknown level '{level}'. Expected one of: {sorted(_DATASET_CLASSES)}"
            )
        df = pd.read_parquet(path)
        return _DATASET_CLASSES[level](df)

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[Union[CMDataset, PGMDataset]]:
        return [self.load_single_origin(p, level, targets) for p in paths]
