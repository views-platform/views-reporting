from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from tqdm.auto import tqdm

from views_reporting.statistics.statistics import PosteriorDistributionAnalyzer

if TYPE_CHECKING:
    from views_pipeline_core.data.handlers import _ViewsDataset

logger = logging.getLogger(__name__)

_analyzer = PosteriorDistributionAnalyzer()


@contextmanager
def tqdm_joblib(tqdm_object):
    """Context manager to patch joblib to report into tqdm progress bar"""

    def tqdm_print_progress(self):
        if self.n_completed_tasks > tqdm_object.n:
            n = self.n_completed_tasks - tqdm_object.n
            tqdm_object.update(n=n)

    original_print_progress = Parallel.print_progress
    Parallel.print_progress = tqdm_print_progress

    try:
        yield tqdm_object
    finally:
        Parallel.print_progress = original_print_progress
        tqdm_object.close()


def _compute_single_map_with_checks(samples, enforce_non_negative, alpha=0.9):
    """Wrapper with NaN handling and input validation"""
    if np.all(np.isnan(samples)):
        return np.nan
    return _simon_compute_single_map(
        samples=samples[~np.isnan(samples)],
        enforce_non_negative=enforce_non_negative,
        alpha=alpha,
    )


def _simon_compute_single_map(samples, enforce_non_negative=False, alpha=0.9):
    """
    Compute the Maximum A Posteriori (MAP) estimate using an HDI-based histogram and KDE refinement.

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

    if len(samples) == 0:
        logger.error("❌ No valid samples. Returning MAP = 0.0")
        return 0.0

    map = _analyzer.analyze(
        samples=samples, credible_masses=(alpha,)
    ).get("map")
    if enforce_non_negative and map < 0:
        logger.warning(
            f"📢  Negative MAP estimate detected ({map:.5f}). Setting to 0."
        )
        map = max(0, map)
    return float(map)


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


def _calculate_single_hdi(
    data: np.ndarray, alpha: float
) -> Tuple[float, float]:
    """Calculate HDI for a 1D array"""
    if np.all(np.isnan(data)):
        return (np.nan, np.nan)
    return _analyzer.analyze(
        samples=data, credible_masses=(alpha,)
    ).get("hdis")[0]


def _analyze_samples(
    samples: np.ndarray, alpha: float, enforce_non_negative: bool
) -> Tuple[float, float, float]:
    """
    Analyze samples to get HDI bounds and MAP estimate in a single operation.

    Parameters:
    samples: Array of samples
    alpha: Credibility level for HDI
    enforce_non_negative: Whether to enforce non-negative MAP estimates

    Returns:
    Tuple of (hdi_lower, hdi_upper, map_estimate)
    """
    if np.all(np.isnan(samples)):
        return (np.nan, np.nan, np.nan)

    analysis = _analyzer.analyze(
        samples=samples, credible_masses=(alpha,)
    )

    hdi_lower, hdi_upper = analysis.get("hdis")[0]
    map_estimate = analysis.get("map")

    if enforce_non_negative and map_estimate < 0:
        map_estimate = max(0, map_estimate)

    return (hdi_lower, hdi_upper, map_estimate)


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
        hdi_pairs = np.apply_along_axis(
            lambda x: _calculate_single_hdi(x, alpha), axis=1, arr=flat_tensor
        )
        hdi_lower = hdi_pairs[:, 0].reshape(var_tensor.shape[:2])
        hdi_upper = hdi_pairs[:, 1].reshape(var_tensor.shape[:2])

        nan_mask = np.isnan(var_tensor).all(axis=2)
        hdi_lower[nan_mask] = np.nan
        hdi_upper[nan_mask] = np.nan

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

    sorted_tensor = np.sort(tensor, axis=2)

    for var_name in tqdm(selected_vars, desc="Processing features"):
        var_idx = selected_vars.index(var_name)
        var_tensor = sorted_tensor[..., var_idx]
        orig_shape = var_tensor.shape[:2]

        flat_tensor = var_tensor.reshape(-1, var_tensor.shape[2])
        n_samples = len(flat_tensor)

        batch_size = 1000
        batches = [
            flat_tensor[i : i + batch_size] for i in range(0, n_samples, batch_size)
        ]

        map_flat = []
        with tqdm_joblib(
            tqdm(total=len(batches), desc=f"{var_name} batches")
        ) as progress_bar:
            with Parallel(n_jobs=-1, prefer="threads") as parallel:
                for batch in batches:
                    batch_results = parallel(
                        delayed(_compute_single_map_with_checks)(
                            samples, enforce_non_negative, alpha
                        )
                        for samples in batch
                    )
                    map_flat.extend(batch_results)
                    progress_bar.update(1)

        map_estimates = np.array(map_flat).reshape(orig_shape)
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

        analysis_results = np.apply_along_axis(
            lambda x: _analyze_samples(x, alpha, enforce_non_negative),
            axis=1,
            arr=flat_tensor,
        )

        hdi_lower = analysis_results[:, 0].reshape(var_tensor.shape[:2])
        hdi_upper = analysis_results[:, 1].reshape(var_tensor.shape[:2])
        map_values = analysis_results[:, 2].reshape(var_tensor.shape[:2])

        nan_mask = np.isnan(var_tensor).all(axis=2)
        hdi_lower[nan_mask] = np.nan
        hdi_upper[nan_mask] = np.nan
        map_values[nan_mask] = np.nan

        hdi_df = _create_hdi_dataframe(dataset, var_name, hdi_lower, hdi_upper, time_ids, entity_ids)
        map_df = _create_map_dataframe(dataset, var_name, map_values, time_ids, entity_ids)

        merged_df = pd.concat([hdi_df, map_df], axis=1)
        results.append(merged_df)

    return pd.concat(results, axis=1)
