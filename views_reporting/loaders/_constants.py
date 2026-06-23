"""Shared constants and the ingestion conformance gate for prediction loaders."""

from __future__ import annotations

from typing import TypeVar

from views_frames import SpatialLevel
from views_frames.conformance import CONFORMANCE_FLOOR, assert_frame_contract

# Declared spatiotemporal level (ADR-003) → views_frames.SpatialLevel.
# Replaces the former pipeline-core DATASET_CLASSES / INDEX_NAMES tables: the
# render path is now frame-native (epic #137, #138). SpatialLevel carries both
# the entity column (country_id / priogrid_id) and the time-first index names.
LEVELS: dict[str, SpatialLevel] = {
    "cm": SpatialLevel.CM,
    "pgm": SpatialLevel.PGM,
}

# The views-frames conformance floor this consumer is tested against (ADR-016 of
# views-frames). Pinned so a leaf floor bump trips `test_conformance_floor_pinned`
# and forces a deliberate re-validation rather than silent drift (epic #137, S5).
EXPECTED_CONFORMANCE_FLOOR = "1.0.0"

_FrameT = TypeVar("_FrameT")


def assert_conformant(frame: _FrameT) -> _FrameT:
    """Fail loud at the ingestion boundary if a frame violates the contract.

    Runs the published `views_frames.conformance.assert_frame_contract` (float32
    values + explicit sample axis, complete integer identifiers, save/load
    round-trip) on every frame the loaders produce — ADR-009 §1b, closing the
    input-completeness gap (register C-111). Returns the frame for call-site
    chaining; raises `AssertionError` on a contract violation.
    """
    assert_frame_contract(frame)
    return frame


__all__ = [
    "LEVELS",
    "EXPECTED_CONFORMANCE_FLOOR",
    "CONFORMANCE_FLOOR",
    "assert_conformant",
]
