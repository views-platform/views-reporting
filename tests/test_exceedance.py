"""calculate_exceedance_frame — the P(any violence) layer statistic (#233).

The share of posterior draws strictly above a threshold (default 0). On
zero-inflated data this is the layer that shows the at-risk surface the
MAP/mode hides — pinned here as a coverage law, not just per-value math.
"""

import numpy as np
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.statistics import (
        calculate_exceedance_frame,
        calculate_map_frame,
    )
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)


def _frame(vals: np.ndarray) -> PredictionFrame:
    n = vals.shape[0]
    idx = SpatioTemporalIndex(
        time=np.full(n, 540, dtype=np.int64),
        unit=np.arange(1, n + 1, dtype=np.int64),
        level=SpatialLevel.PGM,
    )
    return PredictionFrame(vals.astype(np.float32), idx)


@pytest.mark.green_team
def test_exceedance_values_and_index_contract():
    vals = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],  # never exceeds -> 0
            [1.0, 2.0, 3.0, 4.0],  # always -> 1
            [0.0, 0.0, 5.0, 0.0],  # one of four -> 0.25
        ]
    )
    out = calculate_exceedance_frame(_frame(vals), "pred_x")
    assert list(out.columns) == ["pred_x_p_any"]
    assert out.index.names == ["month_id", "priogrid_id"]
    assert out["pred_x_p_any"].tolist() == [0.0, 1.0, 0.25]


@pytest.mark.green_team
def test_exceedance_threshold_is_strict_and_parameterized():
    vals = np.array([[1.0, 1.0, 2.0, 3.0]])
    # strictly greater: draws == threshold do not count
    out = calculate_exceedance_frame(_frame(vals), "pred_x", threshold=1.0)
    assert out["pred_x_p_any"].tolist() == [0.5]


@pytest.mark.green_team
def test_exceedance_nan_policy_mirrors_map_collapse():
    vals = np.array(
        [
            [np.nan, 4.0, 0.0, 0.0],  # share over VALID draws: 1/3
            [np.nan, np.nan, np.nan, np.nan],  # all-NaN row -> NaN
        ]
    )
    out = calculate_exceedance_frame(_frame(vals), "pred_x")
    assert out["pred_x_p_any"].iloc[0] == pytest.approx(1 / 3)
    assert np.isnan(out["pred_x_p_any"].iloc[1])


@pytest.mark.green_team
def test_exceedance_lights_up_what_map_hides():
    """The coverage law that motivates the layer: on zero-inflated samples,
    cells with nonzero P(any) form a superset of cells with nonzero MAP."""
    rng = np.random.default_rng(0)
    vals = rng.lognormal(0.0, 1.0, (500, 64))
    vals[rng.random(vals.shape) < 0.9] = 0.0  # heavy zero-inflation
    fr = _frame(vals)
    p = calculate_exceedance_frame(fr, "pred_x")["pred_x_p_any"].to_numpy()
    m = calculate_map_frame(fr, "pred_x")["pred_x_map"].to_numpy()
    assert set(np.flatnonzero(m > 0)) <= set(np.flatnonzero(p > 0))
    assert (p > 0).sum() > (m > 0).sum()  # strictly more risk surface shown


@pytest.mark.green_team
def test_exceedance_is_probability_bounded():
    rng = np.random.default_rng(1)
    vals = rng.lognormal(0.0, 1.0, (200, 32))
    vals[rng.random(vals.shape) < 0.5] = 0.0
    p = calculate_exceedance_frame(_frame(vals), "pred_x")["pred_x_p_any"]
    assert ((p >= 0) & (p <= 1)).all()
