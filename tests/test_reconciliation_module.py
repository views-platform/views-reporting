"""
CIC coverage for ReconciliationModule.

Red team: type validation, temporal alignment, target intersection.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

try:
    from views_pipeline_core.data.handlers import _CDataset, _PGDataset

    from views_reporting.reconciliation.reconciliation import ReconciliationModule
except ImportError:
    pytest.skip(
        "views_pipeline_core not installed", allow_module_level=True
    )


def _make_mock_datasets(
    time_steps_c=60,
    time_steps_pg=60,
    time_id_c="month_id",
    time_id_pg="month_id",
    time_values_c=None,
    time_values_pg=None,
    targets_c=None,
    targets_pg=None,
):
    """Build matching mock _CDataset and _PGDataset."""
    if time_values_c is None:
        time_values_c = pd.Series(range(480, 480 + time_steps_c))
    if time_values_pg is None:
        time_values_pg = pd.Series(range(480, 480 + time_steps_pg))
    if targets_c is None:
        targets_c = {"pred_ged_sb"}
    if targets_pg is None:
        targets_pg = {"pred_ged_sb"}

    c_ds = MagicMock(spec=_CDataset)
    c_ds.num_time_steps = time_steps_c
    c_ds._time_id = time_id_c
    c_ds._time_values = time_values_c
    c_ds._entity_values = pd.Series([1, 2, 3])
    c_ds.targets = targets_c

    pg_ds = MagicMock(spec=_PGDataset)
    pg_ds.num_time_steps = time_steps_pg
    pg_ds._time_id = time_id_pg
    pg_ds._time_values = time_values_pg
    pg_ds._country_to_grids_cache = None
    pg_ds._entity_metadata_cache = None
    pg_ds.targets = targets_pg

    return c_ds, pg_ds


# ── Red team: type validation ────────────────────────────────────────────


@pytest.mark.red_team
class TestReconciliationTypeValidation:

    def test_wrong_c_dataset_type_raises(self):
        _, pg_ds = _make_mock_datasets()
        with pytest.raises(TypeError, match="Expected _CDataset"):
            ReconciliationModule(
                c_dataset="not_a_dataset",
                pg_dataset=pg_ds,
                wandb_notifications=False,
            )

    def test_wrong_pg_dataset_type_raises(self):
        c_ds, _ = _make_mock_datasets()
        with pytest.raises(TypeError, match="Expected _PGDataset"):
            ReconciliationModule(
                c_dataset=c_ds,
                pg_dataset="not_a_dataset",
                wandb_notifications=False,
            )


# ── Red team: temporal alignment ─────────────────────────────────────────


@pytest.mark.red_team
class TestReconciliationTemporalValidation:

    @patch("views_reporting.reconciliation.reconciliation.build_country_to_grids_cache")
    def test_different_time_step_count_raises(self, mock_cache):
        c_ds, pg_ds = _make_mock_datasets(time_steps_c=60, time_steps_pg=36)
        with pytest.raises(ValueError, match="number of time steps"):
            ReconciliationModule(c_ds, pg_ds, wandb_notifications=False)

    @patch("views_reporting.reconciliation.reconciliation.build_country_to_grids_cache")
    def test_different_time_unit_raises(self, mock_cache):
        c_ds, pg_ds = _make_mock_datasets(
            time_id_c="month_id", time_id_pg="year_id"
        )
        with pytest.raises(ValueError, match="different time units"):
            ReconciliationModule(c_ds, pg_ds, wandb_notifications=False)

    @patch("views_reporting.reconciliation.reconciliation.build_country_to_grids_cache")
    def test_non_overlapping_times_raises(self, mock_cache):
        c_ds, pg_ds = _make_mock_datasets(
            time_values_c=pd.Series(range(480, 500)),
            time_values_pg=pd.Series(range(600, 620)),
            time_steps_c=20,
            time_steps_pg=20,
        )
        with pytest.raises(ValueError, match="different time steps"):
            ReconciliationModule(c_ds, pg_ds, wandb_notifications=False)

    @patch("views_reporting.reconciliation.reconciliation.build_country_to_grids_cache")
    def test_no_common_targets_raises(self, mock_cache):
        c_ds, pg_ds = _make_mock_datasets(
            targets_c={"target_a"},
            targets_pg={"target_b"},
        )
        pg_ds._country_to_grids_cache = {1: [10, 11], 2: [12, 13]}
        with pytest.raises(ValueError, match="No valid targets"):
            ReconciliationModule(c_ds, pg_ds, wandb_notifications=False)


# ── Green team: integration — full parallel reconciliation pipeline ──────


@pytest.mark.green_team
@pytest.mark.slow
class TestReconciliationIntegration:

    def test_reconcile_produces_correct_shape(self):
        """Full pipeline: construct → reconcile → verify output."""
        import numpy as np
        import torch
        from views_pipeline_core.data.handlers import CMDataset, PGMDataset

        np.random.seed(42)

        c_idx = pd.MultiIndex.from_tuples(
            [(528, 1), (528, 2), (529, 1), (529, 2)],
            names=["month_id", "country_id"],
        )
        c_df = pd.DataFrame(
            {"pred_ged_sb": [np.random.normal(50, 10, 20) for _ in range(4)]},
            index=c_idx,
        )
        c_ds = CMDataset(source=c_df)

        pg_idx = pd.MultiIndex.from_tuples(
            [
                (t, g)
                for t in [528, 529]
                for g in [100, 101, 102, 103]
            ],
            names=["month_id", "priogrid_id"],
        )
        pg_df = pd.DataFrame(
            {"pred_ged_sb": [np.random.normal(25, 5, 20) for _ in range(8)]},
            index=pg_idx,
        )
        pg_ds = PGMDataset(source=pg_df)

        pg_ds._country_to_grids_cache = {1: [100, 101], 2: [102, 103]}
        pg_ds._entity_metadata_cache = pd.DataFrame(
            {"country_id": [1, 1, 2, 2, 1, 1, 2, 2]},
            index=pd.MultiIndex.from_tuples(
                [(t, g) for t in [528, 529] for g in [100, 101, 102, 103]],
                names=["month_id", "priogrid_id"],
            ),
        )

        with patch("views_reporting.reconciliation.reconciliation.WandBModule"):
            rm = ReconciliationModule(c_ds, pg_ds, wandb_notifications=False)
            rm._device = torch.device("cpu")
            result = rm.reconcile(max_workers=2)

        assert result is not None
        assert result.shape == (8, 1)
        assert result.notna().all().all()
