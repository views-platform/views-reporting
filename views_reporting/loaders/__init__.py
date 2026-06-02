"""Declared-format prediction data loaders (ADR-003)."""

from views_reporting.loaders._registry import get_loader as get_loader
from views_reporting.loaders._registry import register_loader as register_loader
from views_reporting.loaders.dataframe_loader import DataFrameLoader
from views_reporting.loaders.prediction_frame_loader import PredictionFrameLoader

register_loader("dataframe", DataFrameLoader)
register_loader("prediction_frame", PredictionFrameLoader)


def load_predictions(prediction_format, path, level, targets):
    """Load predictions for a single origin using the declared format."""
    loader = get_loader(prediction_format)
    return loader.load_single_origin(path, level, targets)


def load_prediction_sequence(prediction_format, paths, level, targets):
    """Load predictions for multiple rolling origins."""
    loader = get_loader(prediction_format)
    return loader.load_multi_origin(paths, level, targets)
