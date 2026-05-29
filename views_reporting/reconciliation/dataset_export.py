from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Union

import numpy as np
import torch

from views_reporting.metadata import build_country_to_grids_cache

if TYPE_CHECKING:
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

    if "ln" in feature.split("_"):
        logger.debug(
            f"Unlogging tensor for feature '{feature}' for time_id '{time_id}' before reconciliation."
        )
        data = np.exp(data) - 1
    elif "lx" in feature.split("_"):
        data = np.exp(data) - np.exp(-100)
        logger.debug(
            f"Unlogging tensor with offset for feature '{feature}' for time_id '{time_id}' before reconciliation."
        )
    else:
        logger.debug(
            f"No transformation required for feature '{feature}' for time_id '{time_id}'."
        )

    # Transpose to (samples, entity) and convert to torch tensor
    return torch.from_numpy(data.transpose(1, 0))


def reconcile_pg_dataset(
    pg_dataset: _PGDataset,
    country_id: int,
    feature: str,
    reconciled_tensor: torch.Tensor,
    time_id: int,
) -> None:
    """
    Updates the reconciled dataframe with reconciled values for a specific country's grid cells.

    Args:
        pg_dataset: The PG-level dataset to update.
        country_id: The country ID whose grid cells will be updated.
        feature: The prediction feature/target variable to update.
        reconciled_tensor: Tensor containing reconciled values (shape: samples x num_grid_cells).
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

    # Initialize reconciled dataframe if not exists
    if pg_dataset.reconciled_dataframe is None:
        pg_dataset.reconciled_dataframe = pg_dataset.dataframe.copy()

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

    # Convert tensor to numpy array (handle device tensors)
    reconciled_np = reconciled_tensor.cpu().numpy()
    if "ln" in feature.split("_"):
        logger.debug(
            f"Applying log transformation to reconciled tensor for feature '{feature}' at time_id '{time_id}'."
        )
        reconciled_np = np.log(reconciled_np + 1)
    elif "lx" in feature.split("_"):
        reconciled_np = np.log(reconciled_np + np.exp(-100))
        logger.debug(
            f"Applying log transformation with offset to reconciled tensor for feature '{feature}' at time_id '{time_id}'."
        )
    else:
        logger.debug(
            f"No transformation required for feature '{feature}' for time_id '{time_id}'."
        )

    # Update each grid cell's data
    for idx, entity_id in enumerate(entity_ids):
        new_samples = reconciled_np[:, idx]
        pg_dataset.reconciled_dataframe.loc[(time_id, entity_id), feature] = new_samples
