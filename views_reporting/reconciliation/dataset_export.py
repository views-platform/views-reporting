"""Tensor extraction and dataset writeback for the forecast reconciliation pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Union

import torch

from views_reporting.metadata import build_country_to_grids_cache

if TYPE_CHECKING:
    import pandas as pd
    from views_pipeline_core.data.handlers import _PGDataset, _ViewsDataset

logger = logging.getLogger(__name__)


def to_reconciler(
    dataset: _ViewsDataset,
    feature: str,
    time_id: int,
    sample_idx: Optional[Union[int, List[int]]] = None,
    entity_ids: Optional[Union[int, List[int]]] = None,
) -> torch.Tensor:
    """
    Extracts a tensor compatible with ForecastReconciler for a specified feature and time_id.

    The tensor is extracted for the specified time step, formatted as
    (num_samples, num_entities) for probabilistic reconciliation.

    Args:
        dataset: The dataset to extract from.
        feature: Name of the prediction target variable to reconcile.
        time_id: The time ID (e.g., month_id) for which to extract the tensor.
        sample_idx: Sample indices to include (None for all)
        entity_ids: Entity IDs to include (None for all)

    Returns:
        torch.Tensor: Tensor of shape (samples, entities) for the specified feature
                    at the given time_id.

    Raises:
        ValueError: If dataset is not in prediction mode, feature not found,
                    or time_id is invalid.
    """
    if not dataset.is_prediction:
        raise ValueError("Dataset must be in prediction mode to use to_reconciler")
    if feature not in dataset.targets:
        raise ValueError(f"Feature '{feature}' not found in targets {dataset.targets}")
    if time_id not in dataset._time_values:
        raise ValueError(f"Time ID {time_id} not found in dataset's time values.")

    pred_tensor = dataset.get_subset_tensor(
        time_ids=[time_id],
        features=[feature],
        sample_idx=sample_idx,
        entity_ids=entity_ids,
    )

    # Remove the time and feature dimensions
    # Shape: (1, entity, samples, 1) -> (entity, samples)
    data = pred_tensor[0, :, :, 0]

    # Transpose to (samples, entity) and convert to torch tensor
    return torch.from_numpy(data.transpose(1, 0))


def reconcile_pg_dataset(
    pg_dataset: _PGDataset,
    result_df: pd.DataFrame,
    country_id: int,
    feature: str,
    reconciled_tensor: torch.Tensor,
    time_id: int,
) -> None:
    """
    Write reconciled values for one country's grid cells into ``result_df``.

    **De-mutated (register C-184):** writes into the caller-owned ``result_df``
    (a copy of the pg dataset's dataframe) rather than mutating
    ``pg_dataset.reconciled_dataframe``. ``pg_dataset`` is read-only here — used
    only for validation and the country→grids cache — so reconciliation no longer
    mutates a foreign (pipeline-core-owned) object across the repo boundary.

    Args:
        pg_dataset: The PG-level dataset (read-only: validation + country→grids cache).
        result_df: The caller-owned DataFrame to write reconciled cells into.
        country_id: The country ID whose grid cells will be updated.
        feature: The prediction feature/target variable to update.
        reconciled_tensor: Tensor of reconciled values (shape: samples x num_grid_cells).
        time_id: The time ID (e.g., month_id) for which to update the reconciliation.

    Raises:
        ValueError: If dataset isn't in prediction mode, feature is invalid,
                    tensor shape mismatches the country's grid cell count,
                    or time_id is invalid.
    """
    if not pg_dataset.is_prediction:
        raise ValueError(
            "Reconciliation can only be applied to prediction datasets"
        )
    if feature not in pg_dataset.targets:
        raise ValueError(f"Feature '{feature}' not found in dataset targets")
    if time_id not in pg_dataset._time_values:
        raise ValueError(
            f"Time ID {time_id} not found in the dataset's time values."
        )

    # Get grid cell IDs for the country
    build_country_to_grids_cache(pg_dataset)
    entity_ids = pg_dataset._country_to_grids_cache.get(country_id, [])
    if not entity_ids:
        raise ValueError(f"No grid cells found for country_id {country_id}")

    # Validate tensor dimensions
    if reconciled_tensor.shape[1] != len(entity_ids):
        raise ValueError(
            f"Tensor shape {reconciled_tensor.shape} doesn't match "
            f"{len(entity_ids)} grid cells in country {country_id}"
        )

    # Convert tensor to numpy array and write each grid cell into result_df
    reconciled_np = reconciled_tensor.cpu().numpy()
    for idx, entity_id in enumerate(entity_ids):
        new_samples = reconciled_np[:, idx]
        result_df.loc[(time_id, entity_id), feature] = new_samples
