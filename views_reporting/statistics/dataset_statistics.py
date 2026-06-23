"""Dataset-level MAP and HDI computation delegated to views_frames_summarize.

The MAP/HDI math is routed through the conformance-tested, deterministic
``views_frames_summarize`` package via ephemeral ``PredictionFrame`` objects
(register C-35). The reporting-owned presentation — NaN guards,
``enforce_non_negative`` clamping, and DataFrame reassembly — is retained here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex
from views_frames_summarize import hdi as _vfs_hdi
from views_frames_summarize import map_estimate as _vfs_map_estimate

if TYPE_CHECKING:
    from views_pipeline_core.data.handlers import _ViewsDataset

logger = logging.getLogger(__name__)


def _level_for_dataset(dataset: _ViewsDataset) -> SpatialLevel:
    """Map a pipeline-core dataset's entity id to a views_frames SpatialLevel."""
    return (
        SpatialLevel.CM if dataset._entity_id == "country_id" else SpatialLevel.PGM
    )


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


def _frame_map(flat: np.ndarray, level: SpatialLevel) -> np.ndarray:
    """MAP per row via the summarizer.

    All-finite rows are computed in a single vectorized summarizer call. Rows
    that contain **any** NaN are routed per-row through ``compute_single_map``
    (which strips NaN, returns ``nan`` for all-NaN and ``0.0`` for empty) —
    preserving the legacy per-cell NaN handling that the vectorized summarizer
    cannot do (it raises / corrupts on a NaN row).
    """
    n_rows = flat.shape[0]
    out = np.empty(n_rows, dtype=np.float64)
    nan_any = np.isnan(flat).any(axis=1)
    finite = ~nan_any
    if finite.any():
        frame = _ephemeral_frame(flat[finite], level)
        out[finite] = _vfs_map_estimate(frame).values[:, 0].astype(np.float64)
    for i in np.nonzero(nan_any)[0]:
        out[i] = compute_single_map(flat[i])
    return out


def _frame_hdi(
    flat: np.ndarray, level: SpatialLevel, alpha: float
) -> Tuple[np.ndarray, np.ndarray]:
    """HDI lower/upper per row via the summarizer.

    All-finite rows are computed vectorized; any-NaN rows are routed per-row
    through ``calculate_single_hdi`` (NaN stripped; all-NaN → ``(nan, nan)``),
    preserving the legacy per-cell behaviour.
    """
    n_rows = flat.shape[0]
    lower = np.empty(n_rows, dtype=np.float64)
    upper = np.empty(n_rows, dtype=np.float64)
    nan_any = np.isnan(flat).any(axis=1)
    finite = ~nan_any
    if finite.any():
        frame = _ephemeral_frame(flat[finite], level)
        bounds = _vfs_hdi(frame, mass=alpha).astype(np.float64)
        lower[finite] = bounds[:, 0]
        upper[finite] = bounds[:, 1]
    for i in np.nonzero(nan_any)[0]:
        lo, hi = calculate_single_hdi(flat[i], alpha)
        lower[i] = lo
        upper[i] = hi
    return lower, upper


def compute_single_map(samples, enforce_non_negative=False, alpha=0.9):
    """
    Compute the Maximum A Posteriori (MAP) estimate via views_frames_summarize.

    Parameters:
    ----------
    samples : array-like
        Posterior samples.
    enforce_non_negative : bool
        If True, forces MAP estimate to be non-negative.

    Returns:
    -------
    float
        The estimated MAP.
    """

    samples = np.asarray(samples)
    if np.all(np.isnan(samples)):
        return np.nan

    samples = samples[~np.isnan(samples)]
    if len(samples) == 0:
        logger.error("❌ No valid samples. Returning MAP = 0.0")
        return 0.0

    frame = PredictionFrame(
        samples.astype(np.float32).reshape(1, -1),
        SpatioTemporalIndex(
            time=np.zeros(1, dtype=np.int64),
            unit=np.zeros(1, dtype=np.int64),
            level=SpatialLevel.CM,
        ),
    )
    map_val = float(_vfs_map_estimate(frame).values[0, 0])
    if enforce_non_negative and map_val < 0:
        logger.warning(
            f"📢  Negative MAP estimate detected ({map_val:.5f}). Setting to 0."
        )
        map_val = max(0, map_val)
    return float(map_val)


def _create_map_dataframe(
    dataset: _ViewsDataset,
    var_name: str,
    values: np.ndarray,
    time_ids: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
) -> pd.DataFrame:
    """Helper to format MAP results into DataFrame"""
    if time_ids is not None:
        if not isinstance(time_ids, list):
            time_ids = [time_ids]
        time_steps = pd.Index(time_ids)
    else:
        time_steps = dataset.dataframe.index.get_level_values(dataset._time_id).unique()

    if entity_ids is not None:
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]
        entities = pd.Index(entity_ids)
    else:
        entities = dataset.dataframe.index.get_level_values(dataset._entity_id).unique()

    return (
        pd.DataFrame(values, index=time_steps, columns=entities)
        .stack()
        .to_frame(f"{var_name}_map")
    )


def _create_hdi_dataframe(
    dataset: _ViewsDataset,
    var_name: str,
    lower: np.ndarray,
    upper: np.ndarray,
    time_ids: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
) -> pd.DataFrame:
    """Helper to format HDI results into DataFrame"""
    if time_ids is not None:
        if not isinstance(time_ids, list):
            time_ids = [time_ids]
        time_steps = pd.Index(time_ids)
    else:
        time_steps = dataset.dataframe.index.get_level_values(dataset._time_id).unique()

    if entity_ids is not None:
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]
        entities = pd.Index(entity_ids)
    else:
        entities = dataset.dataframe.index.get_level_values(dataset._entity_id).unique()

    index = pd.MultiIndex.from_product(
        [time_steps, entities], names=[dataset._time_id, dataset._entity_id]
    )

    return pd.DataFrame(
        {
            f"{var_name}_hdi_lower": lower.flatten(),
            f"{var_name}_hdi_upper": upper.flatten(),
        },
        index=index,
    )


def calculate_single_hdi(
    data: np.ndarray, alpha: float
) -> Tuple[float, float]:
    """Calculate HDI for a 1D array via views_frames_summarize."""
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
    bounds = _vfs_hdi(frame, mass=alpha)
    return (float(bounds[0, 0]), float(bounds[0, 1]))


def _format_statistics(dataset: _ViewsDataset, stats: List[Dict]) -> pd.DataFrame:
    """
    Format statistics into a multi-index DataFrame.

    Parameters:
    dataset: The dataset providing index structure
    stats: A list of dictionaries where each dictionary contains statistical metrics
    """
    dfs = []
    for stat in stats:
        for metric in [
            "mean",
            "std",
            "q05",
            "q25",
            "q50",
            "q75",
            "q95",
            "q98",
            "q100",
        ]:
            df = (
                pd.DataFrame(
                    stat[metric],
                    index=dataset.dataframe.index.get_level_values(
                        dataset._time_id
                    ).unique(),
                    columns=dataset.dataframe.index.get_level_values(
                        dataset._entity_id
                    ).unique(),
                )
                .stack()
                .to_frame(f"{stat['variable']}_{metric}")
            )
            dfs.append(df)

    return pd.concat(dfs, axis=1)


def compute_statistics(dataset: _ViewsDataset) -> pd.DataFrame:
    """
    Calculate distribution statistics for predictions.

    Returns:
        pd.DataFrame: A DataFrame containing the calculated statistics for each dependent variable.

    Raises:
        ValueError: If the method is called on a non-prediction dataframe.
    """
    if not dataset.is_prediction:
        raise ValueError("Statistics only available for prediction dataframes")

    tensor = dataset.to_tensor()
    stats = []

    for var_idx, var_name in enumerate(dataset.targets):
        var_tensor = tensor[..., var_idx]
        stats.append(
            {
                "variable": var_name,
                "mean": np.mean(var_tensor, axis=2),
                "std": np.std(var_tensor, axis=2),
                "q05": np.quantile(var_tensor, 0.05, axis=2),
                "q25": np.quantile(var_tensor, 0.25, axis=2),
                "q50": np.quantile(var_tensor, 0.5, axis=2),
                "q75": np.quantile(var_tensor, 0.75, axis=2),
                "q95": np.quantile(var_tensor, 0.95, axis=2),
                "q98": np.quantile(var_tensor, 0.98, axis=2),
                "q100": np.quantile(var_tensor, 1.00, axis=2),
            }
        )

    return _format_statistics(dataset, stats)


def sample_predictions(dataset: _ViewsDataset, num_samples: int = 1) -> pd.DataFrame:
    """
    Draw random samples from the prediction distribution.

    Parameters:
    dataset: The dataset to sample from
    num_samples: The number of samples to draw for each variable. Default is 1.

    Returns:
    pd.DataFrame: A DataFrame containing the sampled predictions.

    Raises:
    ValueError: If the dataset is not a prediction dataframe.
    """
    if not dataset.is_prediction:
        raise ValueError("Sampling only available for prediction dataframes")

    tensor = dataset.to_tensor()
    samples = []

    for var_idx, var_name in enumerate(dataset.targets):
        var_tensor = tensor[..., var_idx]
        sampled = np.apply_along_axis(
            lambda x: np.random.choice(x, num_samples), axis=2, arr=var_tensor
        )

        if num_samples == 1:
            samples.append(
                pd.DataFrame(
                    sampled.squeeze(),
                    index=dataset.dataframe.index.get_level_values(
                        dataset._time_id
                    ).unique(),
                    columns=dataset.dataframe.index.get_level_values(
                        dataset._entity_id
                    ).unique(),
                )
                .stack()
                .rename(var_name)
            )
        else:
            for i in range(num_samples):
                samples.append(
                    pd.DataFrame(
                        sampled[:, :, i],
                        index=dataset.dataframe.index.get_level_values(
                            dataset._time_id
                        ).unique(),
                        columns=dataset.dataframe.index.get_level_values(
                            dataset._entity_id
                        ).unique(),
                    )
                    .stack()
                    .rename(f"{var_name}_sample{i+1}")
                )

    return pd.concat(samples, axis=1)


def calculate_hdi(
    dataset: _ViewsDataset,
    alpha: float = 0.9,
    features: Optional[Union[str, List[str]]] = None,
    sample_idx: Optional[Union[int, List[int]]] = None,
    time_ids: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
) -> pd.DataFrame:
    """
    Calculate Highest Density Intervals (HDIs) for prediction distributions.

    Parameters:
    dataset: The dataset to calculate HDIs for
    alpha: Credibility level for HDI (e.g., 0.9 for 90% HDI). Must be between 0 and 1.
    features: Feature names to calculate HDI for (None for all)
    sample_idx: Sample indices to include (None for all)
    time_ids: Time IDs to include (None for all)
    entity_ids: Entity IDs to include (None for all)

    Returns:
    pd.DataFrame: DataFrame with multi-index (time, entity) and columns for each variable's HDI bounds.

    Raises:
    ValueError: If called on non-prediction data or invalid alpha.
    """
    if not dataset.is_prediction:
        raise ValueError("HDI calculation only valid for prediction dataframes")
    if not 0 < alpha < 1:
        raise ValueError(f"Alpha must be between 0 and 1, got {alpha}")

    if dataset.dataframe.empty:
        return pd.DataFrame()

    if features is not None:
        if not isinstance(features, list):
            features = [features]
        invalid = set(features) - set(dataset.targets)
        if invalid:
            raise ValueError(f"Invalid features specified: {invalid}")
        selected_vars = features
    else:
        selected_vars = dataset.targets

    tensor = dataset.get_subset_tensor(
        features=selected_vars,
        sample_idx=sample_idx,
        time_ids=time_ids,
        entity_ids=entity_ids,
    )
    hdi_results = []

    for var_idx, var_name in enumerate(selected_vars):
        var_tensor = tensor[..., var_idx]
        flat_tensor = var_tensor.reshape(-1, var_tensor.shape[2])

        lower_flat, upper_flat = _frame_hdi(flat_tensor, _level_for_dataset(dataset), alpha)
        hdi_lower = lower_flat.reshape(var_tensor.shape[:2])
        hdi_upper = upper_flat.reshape(var_tensor.shape[:2])

        df = _create_hdi_dataframe(dataset, var_name, hdi_lower, hdi_upper, time_ids, entity_ids)
        hdi_results.append(df)

    return pd.concat(hdi_results, axis=1)


def report_hdi(
    dataset: _ViewsDataset, alphas: Tuple[float, ...] = (0.5, 0.9, 0.95)
) -> pd.DataFrame:
    """
    Generate HDI report for multiple credibility levels.

    Parameters:
    dataset: The dataset to report on
    alphas: Tuple of credibility levels to calculate

    Returns:
    pd.DataFrame: Summary statistics of HDIs across all entities and time steps
    """
    if not dataset.is_prediction:
        raise ValueError("HDI reporting only available for prediction dataframes")

    reports = []
    for alpha in alphas:
        hdi_df = calculate_hdi(dataset, alpha)
        for var in dataset.targets:
            var_hdi = hdi_df[[f"{var}_hdi_lower", f"{var}_hdi_upper"]]
            reports.append(
                {
                    "variable": var,
                    "alpha": alpha,
                    "mean_lower": var_hdi[f"{var}_hdi_lower"].mean(),
                    "mean_upper": var_hdi[f"{var}_hdi_upper"].mean(),
                    "median_lower": var_hdi[f"{var}_hdi_lower"].median(),
                    "median_upper": var_hdi[f"{var}_hdi_upper"].median(),
                }
            )

    return pd.DataFrame(reports)


def calculate_map(
    dataset: _ViewsDataset,
    enforce_non_negative: bool = False,
    features: Optional[Union[str, List[str]]] = None,
    sample_idx: Optional[Union[int, List[int]]] = None,
    time_ids: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
    alpha: float = 0.9,
) -> pd.DataFrame:
    """
    Calculate Maximum A Posteriori (MAP) estimates for prediction distributions.

    Parameters:
    dataset: The dataset to calculate MAP for
    enforce_non_negative: If True, forces MAP estimates to be non-negative
    features: List of features to calculate MAP for. If None, uses all prediction targets.
    sample_idx: Sample indices to include (None for all)
    time_ids: Time IDs to include (None for all)
    entity_ids: Entity IDs to include (None for all)
    alpha: Credibility level for HDI (e.g., 0.9 for 90% HDI).

    Returns:
    pd.DataFrame: DataFrame with MAP estimates (time x entity x targets)
    """

    if not dataset.is_prediction:
        raise ValueError("MAP calculation only valid for prediction dataframes")

    if features is not None:
        if not isinstance(features, list):
            features = [features]
        invalid = set(features) - set(dataset.targets)
        if invalid:
            raise ValueError(f"Invalid features specified: {invalid}")
        selected_vars = features
    else:
        selected_vars = dataset.targets

    tensor = dataset.get_subset_tensor(
        features=selected_vars,
        sample_idx=sample_idx,
        time_ids=time_ids,
        entity_ids=entity_ids,
    )
    map_results = []

    for var_name in tqdm(selected_vars, desc="Processing features"):
        var_idx = selected_vars.index(var_name)
        var_tensor = tensor[..., var_idx]
        orig_shape = var_tensor.shape[:2]

        flat_tensor = var_tensor.reshape(-1, var_tensor.shape[2])
        nan_mask_flat = np.isnan(flat_tensor).all(axis=1)

        map_flat = _frame_map(flat_tensor, _level_for_dataset(dataset))
        if enforce_non_negative:
            negative = ~nan_mask_flat & (map_flat < 0)
            if np.any(negative):
                logger.warning(
                    f"📢  Negative MAP estimate(s) detected for {var_name}. "
                    "Setting to 0."
                )
            map_flat = np.where(negative, 0.0, map_flat)

        map_estimates = map_flat.reshape(orig_shape)
        df = _create_map_dataframe(dataset, var_name, map_estimates, time_ids, entity_ids)
        map_results.append(df)

    return pd.concat(map_results, axis=1)


def calculate_hdi_map(
    dataset: _ViewsDataset,
    alpha: float = 0.9,
    features: Optional[Union[str, List[str]]] = None,
    sample_idx: Optional[Union[int, List[int]]] = None,
    time_ids: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
    enforce_non_negative: bool = False,
) -> pd.DataFrame:
    """
    Calculate both HDIs and MAP estimates in a single operation.

    Parameters:
    dataset: The dataset to calculate for
    alpha: Credibility level for HDI. Must be between 0 and 1.
    features: Feature names to calculate for (None for all)
    sample_idx: Sample indices to include (None for all)
    time_ids: Time IDs to include (None for all)
    entity_ids: Entity IDs to include (None for all)
    enforce_non_negative: If True, forces MAP estimates to be non-negative

    Returns:
    pd.DataFrame: DataFrame with HDI bounds and MAP estimates.

    Raises:
    ValueError: If called on non-prediction data or invalid alpha.
    """
    if not dataset.is_prediction:
        raise ValueError("HDI and MAP calculation only valid for prediction dataframes")
    if not 0 < alpha < 1:
        raise ValueError(f"Alpha must be between 0 and 1, got {alpha}")

    if dataset.dataframe.empty:
        return pd.DataFrame()

    if features is not None:
        if not isinstance(features, list):
            features = [features]
        invalid = set(features) - set(dataset.targets)
        if invalid:
            raise ValueError(f"Invalid features specified: {invalid}")
        selected_vars = features
    else:
        selected_vars = dataset.targets

    tensor = dataset.get_subset_tensor(
        features=selected_vars,
        sample_idx=sample_idx,
        time_ids=time_ids,
        entity_ids=entity_ids,
    )
    results = []

    for var_idx, var_name in enumerate(selected_vars):
        var_tensor = tensor[..., var_idx]
        flat_tensor = var_tensor.reshape(-1, var_tensor.shape[2])
        nan_mask_flat = np.isnan(flat_tensor).all(axis=1)

        lower_flat, upper_flat = _frame_hdi(flat_tensor, _level_for_dataset(dataset), alpha)
        map_flat = _frame_map(flat_tensor, _level_for_dataset(dataset))
        if enforce_non_negative:
            negative = ~nan_mask_flat & (map_flat < 0)
            map_flat = np.where(negative, 0.0, map_flat)

        hdi_lower = lower_flat.reshape(var_tensor.shape[:2])
        hdi_upper = upper_flat.reshape(var_tensor.shape[:2])
        map_values = map_flat.reshape(var_tensor.shape[:2])

        hdi_df = _create_hdi_dataframe(dataset, var_name, hdi_lower, hdi_upper, time_ids, entity_ids)
        map_df = _create_map_dataframe(dataset, var_name, map_values, time_ids, entity_ids)

        merged_df = pd.concat([hdi_df, map_df], axis=1)
        results.append(merged_df)

    return pd.concat(results, axis=1)


# ── Frame-native MAP / HDI (epic #137, #138) ────────────────────────────────
# These consume a views_frames.PredictionFrame directly and reassemble the same
# presentation columns (``pred_{t}_map`` / ``pred_{t}_hdi_lower|upper``) the
# dataset functions above produce, but on a (time, entity) MultiIndex built
# PER-ROW from ``frame.index`` — so a sparse grid round-trips faithfully (no
# from_product densification). The dataset functions are left untouched so the
# S2 equivalence oracle stays green.


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
