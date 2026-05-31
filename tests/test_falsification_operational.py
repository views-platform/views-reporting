"""
Falsification audit: operational readiness (orthogonal angle).

Tests that FAIL on current code, proving specific issues found
during the audit.
"""

import torch
import pytest

from views_reporting.statistics.statistics import ForecastReconciler


class TestReconcilerSumConstraintEdgeCases:

    def test_all_negative_grid_violates_sum_constraint(self):
        """P4: All-negative grid → output sums to 0, not country total.

        The mask_nonzero = grid > 0 treats negatives as zeros.
        After clamping, no cell has value, so the sum is 0 regardless
        of what the country forecast is. The CIC guarantees sum
        preservation unconditionally — this case violates it.
        """
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.tensor([[-5.0, -10.0, -3.0]])
        country = torch.tensor([50.0])
        adjusted = reconciler.reconcile_forecast(grid, country)

        sum_diff = abs(adjusted.sum().item() - country.item())
        assert sum_diff < 0.01, (
            f"Sum constraint violated: output sum={adjusted.sum().item():.2f}, "
            f"expected={country.item():.2f}"
        )
