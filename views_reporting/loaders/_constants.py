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
    all-NaN rows the tower handles per-cell are legitimate). Then the
    **coverage** half (epic #262 S4, #266), same doctrine on the time/entity
    axes: an *interior time-axis gap* is certain data loss (no producer emits a
    gapped horizon) and raises; *ragged entity coverage* across months can be
    legitimate (country systems change — the South Sudan class) and degrades to
    ONE aggregated warning, never a veto. Truncation at the *end* of a horizon
    is indistinguishable from a shorter run without an external expectation —
    that residual stays with the C-108 typed input contract. Returns the frame
    for call-site chaining; raises `AssertionError` (structure) or `ValueError`
    (all-NaN values / gapped time axis).
    """
    assert_frame_contract(frame)

    # ── Coverage (C-111, #266): numpy on the index arrays only (C-212). ──
    times = np.asarray(frame.index.time, dtype=np.int64)
    months, counts = np.unique(times, return_counts=True)
    if months.size > 1:
        gap_starts = months[:-1][np.diff(months) > 1]
        if gap_starts.size:
            missing: list[int] = []
            for start in gap_starts:
                stop = int(months[np.searchsorted(months, start) + 1])
                missing.extend(range(int(start) + 1, stop))
            shown = ", ".join(str(m) for m in missing[:10])
            more = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
            raise ValueError(
                f"Input frame's time axis has interior gap(s) — missing "
                f"month_id(s) {shown}{more} within [{int(months[0])}, "
                f"{int(months[-1])}] (register C-111): a gapped horizon means a "
                "truncated/partial input, not a shorter run. Regenerate or "
                "re-fetch the predictions."
            )
        if counts.min() != counts.max():
            lo, hi = int(np.argmin(counts)), int(np.argmax(counts))
            logger.warning(
                "Entity coverage varies across months (min %d @ month_id %d, "
                "max %d @ month_id %d) — legitimate when the entity system "
                "changes, but verify if unexpected (register C-111): missing "
                "entities render as visible no-data.",
                int(counts[lo]),
                int(months[lo]),
                int(counts[hi]),
                int(months[hi]),
            )

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
