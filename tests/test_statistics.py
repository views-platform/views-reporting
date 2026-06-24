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

# ── Frame-native MAP/HDI: sparse-grid reassembly (green team) — #138 ──────


@pytest.mark.green_team
class TestFrameMapHdiSparseGrid:
    """calculate_map_frame / calculate_hdi_frame must rebuild the result on a
    per-row MultiIndex taken from frame.index — NOT a from_product densification
    — so a SPARSE (time, entity) grid round-trips. The dense characterization
    fixtures cannot catch a from_product bug; this one can."""

    def _sparse_frame(self):
        from views_frames import (
            PredictionFrame,
            SpatialLevel,
            SpatioTemporalIndex,
        )

        # A deliberately sparse grid: (528,1), (528,3), (530,2) — NOT a full
        # cartesian product of {528,530} × {1,2,3}.
        time = np.array([528, 528, 530], dtype=np.int64)
        unit = np.array([1, 3, 2], dtype=np.int64)
        rng = np.random.RandomState(5)
        # peaked posteriors so MAP is well-defined
        values = np.stack(
            [np.abs(rng.normal(loc, 0.4, 500)) for loc in (2.0, 7.0, 4.0)]
        ).astype(np.float32)
        index = SpatioTemporalIndex(time=time, unit=unit, level=SpatialLevel.CM)
        return PredictionFrame(values, index), time, unit

    def test_map_frame_preserves_sparse_index(self):
        from views_reporting.statistics import calculate_map_frame

        frame, time, unit = self._sparse_frame()
        out = calculate_map_frame(frame, "pred_ged_sb")

        assert out.index.names == ["month_id", "country_id"]
        assert list(out.index) == list(zip(time.tolist(), unit.tolist()))
        # the missing cells must NOT have been materialised
        assert (528, 2) not in out.index
        assert (530, 1) not in out.index
        # peaked posteriors centred near 2 / 7 / 4
        vals = out["pred_ged_sb_map"].values
        np.testing.assert_allclose(vals, [2.0, 7.0, 4.0], atol=0.5)

    def test_hdi_frame_preserves_sparse_index(self):
        from views_reporting.statistics import calculate_hdi_frame

        frame, time, unit = self._sparse_frame()
        out = calculate_hdi_frame(frame, "pred_ged_sb", alpha=0.9)

        assert list(out.index) == list(zip(time.tolist(), unit.tolist()))
        # lower <= upper per row
        assert (
            out["pred_ged_sb_hdi_lower"] <= out["pred_ged_sb_hdi_upper"]
        ).all()

    def test_map_frame_enforce_non_negative(self):
        from views_frames import (
            PredictionFrame,
            SpatialLevel,
            SpatioTemporalIndex,
        )

        from views_reporting.statistics import calculate_map_frame

        index = SpatioTemporalIndex(
            time=np.array([1], dtype=np.int64),
            unit=np.array([1], dtype=np.int64),
            level=SpatialLevel.CM,
        )
        frame = PredictionFrame(
            np.full((1, 200), -5.0, dtype=np.float32), index
        )
        out = calculate_map_frame(
            frame, "pred_ged_sb", enforce_non_negative=True
        )
        assert out["pred_ged_sb_map"].iloc[0] == 0.0

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


# ── PosteriorDistributionAnalyzer: tower outputs + laws (green team) ─────


@pytest.mark.green_team
class TestPDATowerOutputs:
    """The tower migration (ADR-019): result keys, bimodality, pinned masses,
    and the by-construction laws as surfaced through analyze()."""

    def test_result_keys_include_bimodal_and_pinned_masses(self):
        r = PosteriorDistributionAnalyzer().analyze(
            np.abs(np.random.default_rng(0).normal(5, 1, 2000)),
            credible_masses=(0.5, 0.95, 0.99),
        )
        assert set(r) == {
            "map", "min", "max", "mass_at_zero", "hdis", "bimodal", "pinned_masses"
        }
        assert isinstance(r["bimodal"], bool)
        assert r["bimodal"] in (True, False)
        # default credible masses land on the canonical grid (lossless pinning)
        assert [round(m, 2) for m in r["pinned_masses"]] == [0.5, 0.95, 0.99]
        assert len(r["hdis"]) == len(r["pinned_masses"])

    def test_clear_two_peak_flags_bimodal(self):
        rng = np.random.default_rng(1)
        twopeak = np.concatenate(
            [rng.normal(2.0, 0.4, 1000), rng.normal(20.0, 1.0, 1000)]
        )
        assert PosteriorDistributionAnalyzer().analyze(twopeak)["bimodal"] is True

    def test_skewed_unimodal_not_flagged(self):
        rng = np.random.default_rng(2)
        assert (
            PosteriorDistributionAnalyzer().analyze(rng.gamma(2.5, 1.5, 4000))["bimodal"]
            is False
        )

    def test_tip_inside_narrowest_hdi(self):
        rng = np.random.default_rng(3)
        r = PosteriorDistributionAnalyzer().analyze(rng.lognormal(0.5, 0.8, 3000))
        low, high = r["hdis"][0]
        assert low - 1e-6 <= r["map"] <= high + 1e-6

    def test_determinism(self):
        s = np.abs(np.random.default_rng(4).normal(5, 1, 2000))
        a = PosteriorDistributionAnalyzer().analyze(s)
        b = PosteriorDistributionAnalyzer().analyze(s)
        assert a == b


# ── PosteriorDistributionAnalyzer: input validation (red team) ───────────


@pytest.mark.red_team
class TestPDAValidation:

    def test_invalid_credible_masses_raises(self):
        with pytest.raises(ValueError, match="credible masses"):
            PosteriorDistributionAnalyzer().analyze(
                np.random.normal(0, 1, 100), credible_masses=(1.5,)
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
        with pytest.raises(ValueError, match="Mismatch"):
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

    def test_dead_params_rejected(self):
        """C-06: lr, max_iters, tol should not be accepted."""
        reconciler = ForecastReconciler(device="cpu")
        grid = torch.rand(10, 5)
        country = grid.sum(dim=1)
        with pytest.raises(TypeError):
            reconciler.reconcile_forecast(grid, country, lr=0.1)
        with pytest.raises(TypeError):
            reconciler.reconcile_forecast(grid, country, max_iters=100)
        with pytest.raises(TypeError):
            reconciler.reconcile_forecast(grid, country, tol=1e-3)


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
