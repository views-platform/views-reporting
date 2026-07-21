"""Loader for numpy-stored PredictionFrame predictions (sample estimates)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from views_frames import PredictionFrame, SpatioTemporalIndex

from views_reporting.loaders._constants import LEVELS, assert_conformant


class PredictionFrameLoader:
    """Load predictions from numpy PredictionFrame directories.

    The on-disk layout pipeline-core writes is ``{target}/y_pred.npy`` (an
    ``(N, S)`` float32 array) plus ``{target}/identifiers.npz`` (integer
    ``time`` and ``unit`` arrays). We **construct** a
    ``views_frames.PredictionFrame`` directly from those raw arrays — we do NOT
    call ``views_frames.PredictionFrame.load`` (which expects a different
    ``values.npy`` + ``header.json`` layout). One frame per target.
    """

    def iter_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ):
        """Yield ``(target, frame)`` one target at a time (C-212 / #235): the
        streaming seam — nothing but the current target's arrays is resident.
        Note on ``mmap_mode`` (evaluated for #235, NOT adopted): with the
        float32-preserving collapse the resident peak is already ~1x the
        source per target, while memory-mapping would re-read the multi-GB
        ``y_pred.npy`` from disk once per summary layer (4x I/O)."""
        if level not in LEVELS:
            raise ValueError(
                f"Unknown level '{level}'. Expected one of: {sorted(LEVELS)}"
            )
        spatial_level = LEVELS[level]

        for target in targets:
            target_dir = Path(path) / target
            y_pred = np.load(target_dir / "y_pred.npy")
            ids = np.load(target_dir / "identifiers.npz")
            index = SpatioTemporalIndex(
                time=np.asarray(ids["time"], dtype=np.int64),
                unit=np.asarray(ids["unit"], dtype=np.int64),
                level=spatial_level,
            )
            yield target, assert_conformant(
                PredictionFrame(np.asarray(y_pred, dtype=np.float32), index)
            )

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> dict[str, PredictionFrame]:
        return dict(self.iter_single_origin(path, level, targets))

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[dict[str, PredictionFrame]]:
        return [self.load_single_origin(p, level, targets) for p in paths]
