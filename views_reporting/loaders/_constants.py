"""Shared constants and the ingestion conformance gate for prediction loaders."""

from __future__ import annotations

import logging
from typing import TypeVar

import numpy as np
from views_frames import SpatialLevel
from views_frames.conformance import CONFORMANCE_FLOOR, assert_frame_contract

logger = logging.getLogger(__name__)

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
    round-trip) on every frame the loaders produce — ADR-009 §1b. Then adds the
    **values-completeness** half of register C-111 that the structural contract
    does not cover: a *wholly* NaN frame is a broken/empty input and raises
    (ADR-008 fail-loud); *partial* NaN is logged, not raised (sparse cells /
    all-NaN rows the tower handles per-cell are legitimate). Expected entity/time
    *coverage* — the remaining half of C-111 — is deferred to the C-108 Phase-3
    typed input contract. Returns the frame for call-site chaining; raises
    `AssertionError` (structure) or `ValueError` (all-NaN values).
    """
    assert_frame_contract(frame)
    values = np.asarray(frame.values)
    if values.size and np.isnan(values).all():
        raise ValueError(
            "Input frame is entirely NaN — no usable predictions to render "
            "(register C-111). Check the prediction source."
        )
    nan_count = int(np.isnan(values).sum())
    if nan_count:
        logger.warning(
            "Input frame carries %d/%d NaN values (%.1f%%) — the report will show "
            "blanks where data is missing (register C-111).",
            nan_count,
            values.size,
            100.0 * nan_count / values.size,
        )
    return frame


__all__ = [
    "LEVELS",
    "EXPECTED_CONFORMANCE_FLOOR",
    "CONFORMANCE_FLOOR",
    "assert_conformant",
]
