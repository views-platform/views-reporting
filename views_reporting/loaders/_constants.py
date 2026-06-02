"""Shared constants for prediction loaders."""

from views_pipeline_core.data.handlers import CMDataset, PGMDataset

DATASET_CLASSES: dict[str, type] = {"cm": CMDataset, "pgm": PGMDataset}

INDEX_NAMES: dict[str, list[str]] = {
    "cm": ["month_id", "country_id"],
    "pgm": ["month_id", "priogrid_id"],
}
