"""Declared-format prediction data loaders (ADR-003)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from views_reporting.loaders._registry import get_loader as get_loader
from views_reporting.loaders._registry import register_loader as register_loader
from views_reporting.loaders.dataframe_loader import DataFrameLoader
from views_reporting.loaders.dataframe_loader import (
    frames_from_dataframe as frames_from_dataframe,
)
from views_reporting.loaders.dataframe_loader import (
    target_frame_from_dataframe as target_frame_from_dataframe,
)
from views_reporting.loaders.prediction_frame_loader import PredictionFrameLoader

if TYPE_CHECKING:
    from views_frames import PredictionFrame

register_loader("dataframe", DataFrameLoader)
register_loader("prediction_frame", PredictionFrameLoader)


def load_predictions(
    prediction_format: str,
    path: Path,
    level: str,
    targets: list[str],
) -> dict[str, PredictionFrame]:
    """Load predictions for a single origin using the declared format.

    Returns ``{target -> views_frames.PredictionFrame}``.
    """
    loader = get_loader(prediction_format)
    return loader.load_single_origin(path, level, targets)


def load_prediction_sequence(
    prediction_format: str,
    paths: list[Path],
    level: str,
    targets: list[str],
) -> list[dict[str, PredictionFrame]]:
    """Load predictions for multiple rolling origins (one dict per origin)."""
    loader = get_loader(prediction_format)
    return loader.load_multi_origin(paths, level, targets)
