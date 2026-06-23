"""Shared constants for prediction loaders."""

from __future__ import annotations

from views_frames import SpatialLevel

# Declared spatiotemporal level (ADR-003) → views_frames.SpatialLevel.
# Replaces the former pipeline-core DATASET_CLASSES / INDEX_NAMES tables: the
# render path is now frame-native (epic #137, #138). SpatialLevel carries both
# the entity column (country_id / priogrid_id) and the time-first index names.
LEVELS: dict[str, SpatialLevel] = {
    "cm": SpatialLevel.CM,
    "pgm": SpatialLevel.PGM,
}
