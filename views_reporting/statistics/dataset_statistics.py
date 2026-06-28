"""Dataset-level point + interval estimates delegated to views_frames_summarize.

The point estimate is the **tower tip** (``tower_point`` — median of the 0.5-mass
"shorth" floor) and the interval is the **constrained-nested HDI** (``hdi_tower``),
both from the conformance-tested ``views_frames_summarize`` package, computed on
ephemeral ``PredictionFrame`` objects. This addresses reporting's MAP/HDI
correctness gap (register **C-35**; ADR-019) by inheriting the views-frames tower
fixes — upstream *views-frames* register C-32 (MAP mode bias), C-33 (HDI
non-nesting), and the 1.2.0 C-44 duplicate-robustness fix — replacing the frozen
histogram-mode MAP and non-nested empirical HDI on the render path.

For contract stability the output columns keep their historical names
(``{t}_map`` / ``{t}_hdi_lower|upper``) — but note ``{t}_map`` now carries the
tower tip (a shorth), **not** a histogram mode. The reporting-owned presentation
— NaN guards, ``enforce_non_negative`` clamping, and DataFrame reassembly — is
retained here.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import pandas as pd
from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex
from views_frames_summarize import config as _tower_config
from views_frames_summarize import hdi_tower as _vfs_hdi_tower
from views_frames_summarize import tower_point as _vfs_tower_point

logger = logging.getLogger(__name__)


def _ephemeral_frame(flat: np.ndarray, level: SpatialLevel) -> PredictionFrame:
    """Wrap a flat ``(N, S)`` sample array as an ephemeral PredictionFrame.

    MAP/HDI reduce the trailing (sample) axis per row, so the row index content
    is irrelevant to the numbers; only ``n_rows`` matters. The frame is
    discarded after the summarizer call.
    """
    n_rows = flat.shape[0]
    index = SpatioTemporalIndex(
        time=np.zeros(n_rows, dtype=np.int64),
        unit=np.arange(n_rows, dtype=np.int64),
        level=level,
    )
    return PredictionFrame(flat.astype(np.float32), index)


def _warn_if_alpha_off_grid(alpha: float) -> None:
    """Log if ``alpha`` is not a tower canonical floor.

    ``hdi_tower`` reads its interval off a fixed canonical mass grid, pinning the
    requested mass to the nearest floor (deterministic, reproducible). The default
    ``alpha=0.9`` is on the grid (``0.90``); an off-grid request snaps silently, so
    surface it rather than return a credible-looking interval at the wrong mass.
    """
    floors = _tower_config.canonical_floors()
    nearest = float(floors[int(np.argmin(np.abs(floors - alpha)))])
    if abs(nearest - alpha) > 1e-9:
        logger.warning(
            "📢  hdi_tower pins the requested mass to a fixed canonical grid; "
            f"alpha={alpha} snaps to {nearest}."
        )


def _tower_hdi_bounds(frame: PredictionFrame, alpha: float) -> np.ndarray:
    """``(N, 2)`` lower/upper from the constrained-nested tower at mass ``alpha``."""
    return _vfs_hdi_tower(frame, masses=(alpha,))[:, 0, :]


def _frame_map(flat: np.ndarray, level: SpatialLevel) -> np.ndarray:
    """Point estimate (tower tip) per row via the summarizer.

    All-finite rows are computed in a single vectorized ``tower_point`` call. Rows
    that contain **any** NaN are routed per-row through ``compute_single_map``
    (which strips NaN, returns ``nan`` for all-NaN and ``0.0`` for empty) —
    preserving the legacy per-cell NaN handling that the vectorized summarizer
    cannot do (it corrupts on a NaN row). The per-cell path uses the *same* tower
    estimator, so finite and any-NaN rows stay on one estimator.
    """
    n_rows = flat.shape[0]
    out = np.empty(n_rows, dtype=np.float64)
    nan_any = np.isnan(flat).any(axis=1)
    finite = ~nan_any
    if finite.any():
        frame = _ephemeral_frame(flat[finite], level)
        out[finite] = _vfs_tower_point(frame).values[:, 0].astype(np.float64)
    for i in np.nonzero(nan_any)[0]:
        out[i] = compute_single_map(flat[i])
    return out


def _frame_hdi(
    flat: np.ndarray, level: SpatialLevel, alpha: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Constrained-nested HDI lower/upper per row via the summarizer.

    All-finite rows are computed vectorized via ``hdi_tower``; any-NaN rows are
    routed per-row through ``calculate_single_hdi`` (NaN stripped; all-NaN →
    ``(nan, nan)``) on the *same* tower estimator, preserving the legacy per-cell
    behaviour.
    """
    _warn_if_alpha_off_grid(alpha)
    n_rows = flat.shape[0]
    lower = np.empty(n_rows, dtype=np.float64)
    upper = np.empty(n_rows, dtype=np.float64)
    nan_any = np.isnan(flat).any(axis=1)
    finite = ~nan_any
    if finite.any():
        frame = _ephemeral_frame(flat[finite], level)
        bounds = _tower_hdi_bounds(frame, alpha).astype(np.float64)
        lower[finite] = bounds[:, 0]
        upper[finite] = bounds[:, 1]
    for i in np.nonzero(nan_any)[0]:
        lo, hi = calculate_single_hdi(flat[i], alpha)
        lower[i] = lo
        upper[i] = hi
    return lower, upper


def compute_single_map(samples, enforce_non_negative=False, alpha=0.9):
    """
    Compute the single-cell point estimate (tower tip) via views_frames_summarize.

    Named ``compute_single_map`` for API/contract stability; it now returns the
    tower tip (``tower_point`` — a shorth), not a histogram-mode MAP.

    Parameters:
    ----------
    samples : array-like
        Posterior samples.
    enforce_non_negative : bool
        If True, forces the estimate to be non-negative.

    Returns:
    -------
    float
        The estimated point value (tower tip).
    """

    samples = np.asarray(samples)
    if np.all(np.isnan(samples)):
        return np.nan

    samples = samples[~np.isnan(samples)]
    if len(samples) == 0:
        logger.error("❌ No valid samples. Returning estimate = 0.0")
        return 0.0

    frame = PredictionFrame(
        samples.astype(np.float32).reshape(1, -1),
        SpatioTemporalIndex(
            time=np.zeros(1, dtype=np.int64),
            unit=np.zeros(1, dtype=np.int64),
            level=SpatialLevel.CM,
        ),
    )
    map_val = float(_vfs_tower_point(frame).values[0, 0])
    if enforce_non_negative and map_val < 0:
        logger.warning(
            f"📢  Negative MAP estimate detected ({map_val:.5f}). Setting to 0."
        )
        map_val = max(0, map_val)
    return float(map_val)


def calculate_single_hdi(
    data: np.ndarray, alpha: float
) -> Tuple[float, float]:
    """Calculate the constrained-nested HDI for a 1D array via views_frames_summarize."""
    data = np.asarray(data)
    if np.all(np.isnan(data)):
        return (np.nan, np.nan)
    data = data[~np.isnan(data)]
    frame = PredictionFrame(
        data.astype(np.float32).reshape(1, -1),
        SpatioTemporalIndex(
            time=np.zeros(1, dtype=np.int64),
            unit=np.zeros(1, dtype=np.int64),
            level=SpatialLevel.CM,
        ),
    )
    bounds = _tower_hdi_bounds(frame, alpha)
    return (float(bounds[0, 0]), float(bounds[0, 1]))


# ── Frame-native MAP / HDI (epic #137, #138) ────────────────────────────────
# These consume a views_frames.PredictionFrame directly and assemble the
# presentation columns (``pred_{t}_map`` / ``pred_{t}_hdi_lower|upper``) on a
# (time, entity) MultiIndex built PER-ROW from ``frame.index`` — so a sparse grid
# round-trips faithfully (no from_product densification). These replaced the
# dataset-level functions, which were retired with the pipeline-core
# private-dataset decoupling (C-114 / #113).


def _frame_multiindex(frame: PredictionFrame) -> pd.MultiIndex:
    """A (time, entity) MultiIndex built per-row from the frame's own index."""
    time_name, entity_name = frame.index.level.index_names
    return pd.MultiIndex.from_arrays(
        [frame.index.time, frame.index.unit],
        names=[time_name, entity_name],
    )


def calculate_map_frame(
    frame: PredictionFrame,
    target: str,
    *,
    enforce_non_negative: bool = False,
) -> pd.DataFrame:
    """MAP estimates for one PredictionFrame → ``{target}_map`` column.

    ``target`` is the prediction column stem (e.g. ``pred_ged_sb``); the output
    column is ``{target}_map``. Reproduces the dataset ``calculate_map``
    presentation (NaN guards via the per-cell strip, ``enforce_non_negative``
    clamp) on a per-row MultiIndex from ``frame.index``.
    """
    flat = np.asarray(frame.values, dtype=np.float64)
    nan_mask_flat = np.isnan(flat).all(axis=1)
    map_flat = _frame_map(flat, frame.index.level)
    if enforce_non_negative:
        negative = ~nan_mask_flat & (map_flat < 0)
        if np.any(negative):
            logger.warning(
                f"📢  Negative MAP estimate(s) detected for {target}. "
                "Setting to 0."
            )
        map_flat = np.where(negative, 0.0, map_flat)

    return pd.DataFrame(
        {f"{target}_map": map_flat},
        index=_frame_multiindex(frame),
    )


def calculate_hdi_frame(
    frame: PredictionFrame,
    target: str,
    *,
    alpha: float = 0.9,
) -> pd.DataFrame:
    """HDI bounds for one PredictionFrame → ``{target}_hdi_lower|upper`` columns.

    ``target`` is the prediction column stem (e.g. ``pred_ged_sb``). Reproduces
    the dataset ``calculate_hdi`` presentation on a per-row MultiIndex from
    ``frame.index``.
    """
    if not 0 < alpha < 1:
        raise ValueError(f"Alpha must be between 0 and 1, got {alpha}")
    flat = np.asarray(frame.values, dtype=np.float64)
    lower_flat, upper_flat = _frame_hdi(flat, frame.index.level, alpha)
    return pd.DataFrame(
        {
            f"{target}_hdi_lower": lower_flat,
            f"{target}_hdi_upper": upper_flat,
        },
        index=_frame_multiindex(frame),
    )
