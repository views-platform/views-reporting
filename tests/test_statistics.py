"""
CIC coverage for PosteriorDistributionAnalyzer and ForecastReconciler.

Harvested from inline test suites in statistics.py and expanded
with input validation (red team) and shape/non-negativity checks.
"""

import numpy as np
import pytest
import scipy.stats as stats
import torch

from views_reporting.statistics.statistics import (
    ForecastReconciler,
    PosteriorDistributionAnalyzer,
)

# ── PosteriorDistributionAnalyzer: 12-distribution suite (green team) ────


_DISTRIBUTIONS = {
    "Normal": lambda: stats.norm.rvs(loc=5, scale=2, size=10000),
    "Half-Normal": lambda: stats.halfnorm.rvs(loc=0, scale=2, size=10000),
    "Cauchy": lambda: stats.cauchy.rvs(loc=0, scale=1, size=10000),
    "Laplace": lambda: stats.laplace.rvs(loc=0, scale=1, size=10000),
    "Power-Law": lambda: np.random.pareto(a=3, size=10000) + 1,
    "Bimodal": lambda: np.concatenate([
        stats.norm.rvs(loc=-3, scale=1, size=5000),
        stats.norm.rvs(loc=3, scale=1, size=5000),
    ]),
    "Student-t": lambda: stats.t.rvs(df=1, loc=0, scale=1, size=10000),
    "Beta": lambda: stats.beta.rvs(0.5, 0.5, size=10000),
    "Skewed-Normal": lambda: stats.skewnorm.rvs(a=10, loc=0, scale=2, size=10000),
    "Triangular": lambda: stats.triang.rvs(c=0.5, loc=0, scale=4, size=10000),
    "Trimodal": lambda: np.concatenate([
        stats.norm.rvs(loc=-5, scale=1, size=3000),
        stats.norm.rvs(loc=0, scale=1, size=4000),
        stats.norm.rvs(loc=5, scale=1, size=3000),
    ]),
    "Gumbel": lambda: stats.gumbel_r.rvs(loc=0, scale=2, size=10000),
}


@pytest.mark.green_team
class TestPDADistributions:

    @pytest.fixture(autouse=True)
    def _seed(self):
        np.random.seed(42)

    @pytest.mark.parametrize("name", list(_DISTRIBUTIONS.keys()))
    def test_map_contained_in_all_hdis(self, name):
        samples = _DISTRIBUTIONS[name]()
        result = PosteriorDistributionAnalyzer().analyze(
            samples, credible_masses=(0.5, 0.95, 0.99)
        )
        for low, high in result["hdis"]:
            assert low <= result["map"] <= high, (
                f"{name}: MAP {result['map']:.4f} not in HDI [{low:.4f}, {high:.4f}]"
            )

    @pytest.mark.parametrize("name", list(_DISTRIBUTIONS.keys()))
    def test_hdis_properly_nested(self, name):
        samples = _DISTRIBUTIONS[name]()
        result = PosteriorDistributionAnalyzer().analyze(
            samples, credible_masses=(0.5, 0.95, 0.99)
        )
        hdis = result["hdis"]
        for i in range(1, len(hdis)):
            assert hdis[i][0] <= hdis[i - 1][0], (
                f"{name}: HDI {i} lower {hdis[i][0]:.4f} > HDI {i-1} lower {hdis[i-1][0]:.4f}"
            )
            assert hdis[i][1] >= hdis[i - 1][1], (
                f"{name}: HDI {i} upper {hdis[i][1]:.4f} < HDI {i-1} upper {hdis[i-1][1]:.4f}"
            )


# ── PosteriorDistributionAnalyzer: input validation (red team) ───────────


@pytest.mark.red_team
class TestPDAValidation:

    def test_invalid_credible_masses_raises(self):
        with pytest.raises(ValueError, match="credible masses"):
            PosteriorDistributionAnalyzer().analyze(
                np.random.normal(0, 1, 100), credible_masses=(1.5,)
            )

    def test_negative_zero_mass_threshold_raises(self):
        with pytest.raises(ValueError, match="zero_mass_threshold"):
            PosteriorDistributionAnalyzer().analyze(
                np.random.normal(0, 1, 100), zero_mass_threshold=-1
            )

    def test_zero_bins_raises(self):
        with pytest.raises(ValueError, match="bins"):
            PosteriorDistributionAnalyzer().analyze(
                np.random.normal(0, 1, 100), bins=0
            )

    def test_all_nan_samples_raises(self):
        with pytest.raises(ValueError, match="No valid samples"):
            PosteriorDistributionAnalyzer().analyze(
                np.array([np.nan, np.nan, np.nan])
            )


# ── ForecastReconciler: probabilistic reconciliation (green team) ────────


_PROB_CASES = [
    pytest.param(1000, 100, 0.3, 1.2, id="basic"),
    pytest.param(1000, 100, 1.0, 1.2, id="all-zeros"),
    pytest.param(1000, 100, 0.2, 10, id="extreme-skew"),
    pytest.param(1000, 100, 0.95, 1.2, id="sparse-95pct"),
    pytest.param(1000, 100, 0.3, 10, id="extreme-scaling"),
    pytest.param(1000, 100, 0.5, 1e-5, id="float-precision"),
    pytest.param(1000, 100, 0.7, 5, id="mixed-zeros-large"),
]

_PROB_CASE_SLOW = pytest.param(10000, 500, 0.5, 1.1, id="large-scale")


@pytest.mark.green_team
class TestReconcilerProbabilistic:

    @pytest.mark.parametrize(
        "num_samples,num_grid_cells,zero_fraction,scaling_factor",
        _PROB_CASES,
    )
    def test_sum_constraint(
        self, num_samples, num_grid_cells, zero_fraction, scaling_factor
    ):
        torch.manual_seed(42)
        reconciler = ForecastReconciler(device="cpu")

        zero_mask = torch.rand((num_samples, num_grid_cells)) < zero_fraction
        grid = torch.randint(1, 100, (num_samples, num_grid_cells), dtype=torch.float32)
        grid[zero_mask] = 0
        country = grid.sum(dim=1) * scaling_factor

        adjusted = reconciler.reconcile_forecast(grid, country)

        sum_diff = torch.abs(adjusted.sum(dim=1) - country).max().item()
        assert sum_diff < 1e-2, f"Sum constraint violated: max diff {sum_diff}"

    @pytest.mark.parametrize(
        "num_samples,num_grid_cells,zero_fraction,scaling_factor",
        _PROB_CASES,
    )
    def test_zero_preservation_per_cell(
        self, num_samples, num_grid_cells, zero_fraction, scaling_factor
    ):
        torch.manual_seed(42)
        reconciler = ForecastReconciler(device="cpu")

        zero_mask = torch.rand((num_samples, num_grid_cells)) < zero_fraction
        grid = torch.randint(1, 100, (num_samples, num_grid_cells), dtype=torch.float32)
        grid[zero_mask] = 0
        country = grid.sum(dim=1) * scaling_factor

        adjusted = reconciler.reconcile_forecast(grid, country)

        zero_cells = grid == 0
        assert torch.all(adjusted[zero_cells] == 0), "Zero cells became nonzero"

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "num_samples,num_grid_cells,zero_fraction,scaling_factor",
        [_PROB_CASE_SLOW],
    )
    def test_large_scale_sum_constraint(
        self, num_samples, num_grid_cells, zero_fraction, scaling_factor
    ):
        torch.manual_seed(42)
        reconciler = ForecastReconciler(device="cpu")

        zero_mask = torch.rand((num_samples, num_grid_cells)) < zero_fraction
        grid = torch.randint(1, 100, (num_samples, num_grid_cells), dtype=torch.float32)
        grid[zero_mask] = 0
        country = grid.sum(dim=1) * scaling_factor

        adjusted = reconciler.reconcile_forecast(grid, country)
        sum_diff = torch.abs(adjusted.sum(dim=1) - country).max().item()
        assert sum_diff < 1e-2


# ── ForecastReconciler: point reconciliation (green team) ────────────────


_POINT_CASES = [
    pytest.param(100, 0.3, 1.2, id="basic"),
    pytest.param(100, 1.0, 1.2, id="all-zeros"),
    pytest.param(100, 0.2, 10, id="extreme-skew"),
    pytest.param(100, 0.95, 1.2, id="sparse-95pct"),
    pytest.param(100, 0.3, 10, id="extreme-scaling"),
    pytest.param(100, 0.5, 1e-5, id="float-precision"),
    pytest.param(100, 0.7, 5, id="mixed-zeros-large"),
]


@pytest.mark.green_team
class TestReconcilerPoint:

    @pytest.mark.parametrize(
        "num_grid_cells,zero_fraction,scaling_factor",
        _POINT_CASES,
    )
    def test_sum_constraint(self, num_grid_cells, zero_fraction, scaling_factor):
        torch.manual_seed(42)
        reconciler = ForecastReconciler(device="cpu")

        zero_mask = torch.rand(num_grid_cells) < zero_fraction
        grid = torch.randint(1, 100, (num_grid_cells,), dtype=torch.float32)
        grid[zero_mask] = 0
        country = grid.sum().item() * scaling_factor

        adjusted = reconciler.reconcile_forecast(grid, country)

        sum_diff = abs(adjusted.sum().item() - country)
        assert sum_diff < 1e-2, f"Sum constraint violated: diff {sum_diff}"

    @pytest.mark.parametrize(
        "num_grid_cells,zero_fraction,scaling_factor",
        _POINT_CASES,
    )
    def test_zero_preservation_per_cell(
        self, num_grid_cells, zero_fraction, scaling_factor
    ):
        torch.manual_seed(42)
        reconciler = ForecastReconciler(device="cpu")

        zero_mask = torch.rand(num_grid_cells) < zero_fraction
        grid = torch.randint(1, 100, (num_grid_cells,), dtype=torch.float32)
        grid[zero_mask] = 0
        country = grid.sum().item() * scaling_factor

        adjusted = reconciler.reconcile_forecast(grid, country)

        zero_cells = grid == 0
        assert torch.all(adjusted[zero_cells] == 0), "Zero cells became nonzero"


# ── ForecastReconciler: shape and non-negativity (green team) ────────────


@pytest.mark.green_team
class TestReconcilerProperties:

    def test_probabilistic_shape_preserved(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(50, 20)
        country = grid.sum(dim=1) * 1.5
        adjusted = reconciler.reconcile_forecast(grid, country)
        assert adjusted.shape == grid.shape

    def test_point_shape_preserved(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(20)
        country = grid.sum().item() * 1.5
        adjusted = reconciler.reconcile_forecast(grid, country)
        assert adjusted.shape == grid.shape

    def test_non_negativity(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(100, 50)
        country = grid.sum(dim=1) * 2.0
        adjusted = reconciler.reconcile_forecast(grid, country)
        assert adjusted.min().item() >= 0


# ── ForecastReconciler: failure modes (red team) — F1/F2 ────────────────


@pytest.mark.red_team
class TestReconcilerFailureModes:

    def test_sample_count_mismatch_raises(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(100, 50)
        country = torch.rand(200)
        with pytest.raises(AssertionError, match="Mismatch"):
            reconciler.reconcile_forecast(grid, country)

    def test_epsilon_guard_tiny_values(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.full((10, 5), 1e-10)
        country = torch.full((10,), 1000.0)
        adjusted = reconciler.reconcile_forecast(grid, country)
        assert torch.all(torch.isfinite(adjusted))
        assert torch.all(adjusted >= 0)

    def test_negative_country_forecast_clamped(self):
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(5)
        adjusted = reconciler.reconcile_forecast(grid, -100.0)
        assert adjusted.min().item() >= 0

    def test_non_tensor_input_raises(self):
        reconciler = ForecastReconciler(device="cpu")
        with pytest.raises((AttributeError, TypeError)):
            reconciler.reconcile_forecast([1, 2, 3], 6.0)


# ── ForecastReconciler: realistic usage (beige team) — F1 ───────────────


@pytest.mark.beige_team
class TestReconcilerRealisticUsage:

    def test_sequential_calls_independent(self):
        reconciler = ForecastReconciler(device="cpu")

        grid_a = torch.tensor([10.0, 20.0, 30.0])
        adjusted_a = reconciler.reconcile_forecast(grid_a, 120.0)

        grid_b = torch.tensor([5.0, 5.0, 0.0])
        adjusted_b = reconciler.reconcile_forecast(grid_b, 20.0)

        assert abs(adjusted_a.sum().item() - 120.0) < 1e-2
        assert abs(adjusted_b.sum().item() - 20.0) < 1e-2

    def test_device_none_works(self):
        reconciler = ForecastReconciler(device=None)
        grid = torch.tensor([10.0, 20.0, 0.0, 15.0])
        adjusted = reconciler.reconcile_forecast(grid, 100.0)
        assert abs(adjusted.sum().item() - 100.0) < 1e-2


# ── PDA: missing failure modes (red team) — F3 ──────────────────────────


@pytest.mark.red_team
class TestPDAFailureModes:

    def test_too_few_samples_degenerate_hdi(self):
        samples = np.array([1.0, 2.0])
        result = PosteriorDistributionAnalyzer().analyze(
            samples, credible_masses=(0.99,)
        )
        assert "hdis" in result
        assert len(result["hdis"]) == 1
        low, high = result["hdis"][0]
        assert low <= high

    def test_single_sample(self):
        samples = np.array([42.0])
        result = PosteriorDistributionAnalyzer().analyze(
            samples, credible_masses=(0.5,)
        )
        assert abs(result["map"] - 42.0) < 0.1
        assert result["min"] == 42.0
        assert result["max"] == 42.0


# ── PDA: interactive workflow before analyze (beige team) — F3 ───────────


@pytest.mark.beige_team
class TestPDAInteractiveSafety:

    def test_summary_dict_before_analyze_returns_none(self):
        analyzer = PosteriorDistributionAnalyzer()
        assert analyzer.summary_dict() is None

    def test_print_summary_before_analyze_no_crash(self):
        import io
        analyzer = PosteriorDistributionAnalyzer()
        buf = io.StringIO()
        analyzer.print_summary(file=buf)
        assert "No summary available" in buf.getvalue()
