"""
CIC coverage for PosteriorDistributionAnalyzer.

Harvested from inline test suites in statistics.py and expanded
with input validation (red team) and shape/non-negativity checks.
"""

import numpy as np
import pytest
import scipy.stats as stats

from views_reporting.statistics.statistics import (
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
