"""Loader for numpy-stored PredictionFrame predictions (sample estimates)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from views_frames import PredictionFrame, SpatioTemporalIndex

from views_reporting.loaders._constants import LEVELS


class PredictionFrameLoader:
    """Load predictions from numpy PredictionFrame directories.

    The on-disk layout pipeline-core writes is ``{target}/y_pred.npy`` (an
    ``(N, S)`` float32 array) plus ``{target}/identifiers.npz`` (integer
    ``time`` and ``unit`` arrays). We **construct** a
    ``views_frames.PredictionFrame`` directly from those raw arrays — we do NOT
    call ``views_frames.PredictionFrame.load`` (which expects a different
    ``values.npy`` + ``header.json`` layout). One frame per target.
    """

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> dict[str, PredictionFrame]:
        if level not in LEVELS:
            raise ValueError(
                f"Unknown level '{level}'. Expected one of: {sorted(LEVELS)}"
            )
        spatial_level = LEVELS[level]

        frames: dict[str, PredictionFrame] = {}
        for target in targets:
            target_dir = Path(path) / target
            y_pred = np.load(target_dir / "y_pred.npy")
            ids = np.load(target_dir / "identifiers.npz")
            index = SpatioTemporalIndex(
                time=np.asarray(ids["time"], dtype=np.int64),
                unit=np.asarray(ids["unit"], dtype=np.int64),
                level=spatial_level,
            )
            frames[target] = PredictionFrame(
                np.asarray(y_pred, dtype=np.float32), index
            )
        return frames

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[dict[str, PredictionFrame]]:
        return [self.load_single_origin(p, level, targets) for p in paths]
