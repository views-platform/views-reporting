"""The sample boundary at the pandas seams (epic #215, S2 / #217 — register C-207).

Contract under enforcement: posterior samples are numpy-bound; the pandas
presentation seams (`frames_to_mapping_df`, the historical point-forecast line)
receive only collapsed S==1 summaries. An uncollapsed S>1 frame must be refused
loudly — never silently rendered as posterior draw #0 (the probe demonstrated
draw #0 ≠ tower MAP at every grid point; see
documentation/investigations/sample_scaling_boundary.md, P5/P6).

RED→GREEN history: the first commit of this file CHARACTERIZED the pre-guard
behaviour (draw #0 crossing silently); the guard commit flipped the assertions
to the enforced contract.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    import views_reporting.mapping._frame_adapter as frame_adapter
    import views_reporting.visualizations.historical as hist_mod
    from views_reporting.mapping._frame_adapter import frames_to_mapping_df
    from views_reporting.statistics.dataset_statistics import calculate_map_frame
    from views_reporting.visualizations.historical import HistoricalLineGraph
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

TARGET = "ged_sb"
PRED_TARGET = f"pred_{TARGET}"


def _cm_frame(n_units: int, n_times: int, s: int) -> PredictionFrame:
    rng = np.random.default_rng(7)
    n = n_units * n_times
    idx = SpatioTemporalIndex(
        time=np.repeat(np.arange(500, 500 + n_times, dtype=np.int64), n_units),
        unit=np.tile(np.arange(1, n_units + 1, dtype=np.int64), n_times),
        level=SpatialLevel.CM,
    )
    vals = rng.lognormal(0.0, 1.0, (n, s)).astype(np.float32)
    return PredictionFrame(vals, idx)


def _mock_iso(index, level):
    return pd.DataFrame({"isoab": ["AAA"] * len(index)}, index=index)


def _mock_name(index, level, with_id=False):
    ents = index.get_level_values(index.names[1])
    return pd.DataFrame({"name": [f"Country {e}" for e in ents]}, index=index)


# ── The mapping seam (frames_to_mapping_df) ──────────────────────────────────


@pytest.mark.red_team
def test_seam_passes_uncollapsed_sample_frame_as_draw0():
    """CHARACTERIZATION (C-207, pre-guard): an uncollapsed S>1 frame crosses the
    seam silently, rendering posterior draw #0 — which is NOT the tower MAP."""
    frame = _cm_frame(5, 6, s=200)
    with patch.object(frame_adapter, "get_isoab_for_index", side_effect=_mock_iso), \
         patch.object(frame_adapter, "get_name_for_index", side_effect=_mock_name):
        out = frames_to_mapping_df(frame, PRED_TARGET, SpatialLevel.CM)
    # today: draw #0 crosses, no error, no warning
    assert np.allclose(out[PRED_TARGET].to_numpy(), frame.values[:, 0])
    tower_map = calculate_map_frame(frame, PRED_TARGET).iloc[:, 0].to_numpy()
    assert not np.allclose(out[PRED_TARGET].to_numpy(), tower_map)


@pytest.mark.green_team
def test_seam_accepts_collapsed_frame():
    """The sanctioned path: a collapsed S==1 frame crosses the seam unchanged."""
    frame = _cm_frame(5, 6, s=1)
    with patch.object(frame_adapter, "get_isoab_for_index", side_effect=_mock_iso), \
         patch.object(frame_adapter, "get_name_for_index", side_effect=_mock_name):
        out = frames_to_mapping_df(frame, PRED_TARGET, SpatialLevel.CM)
    assert len(out) == 30
    assert np.allclose(out[PRED_TARGET].to_numpy(), frame.values[:, 0])


# ── The historical fallback (all HDI levels failed) ──────────────────────────


def _fallback_fig(frame):
    """Render a line graph with every HDI level forced to fail; return the fig."""

    def boom(*a, **k):
        raise ValueError("forced HDI failure (test)")

    with patch.object(hist_mod, "get_name_for_index", side_effect=_mock_name), \
         patch.object(hist_mod, "calculate_hdi_frame", side_effect=boom):
        hlg = HistoricalLineGraph(
            historical_frame=None, forecast_frame=frame, level=SpatialLevel.CM
        )
        return hlg._plot_interactive(
            entity_ids=[1],
            target=TARGET,
            alpha=0.9,
            vline=None,
            hdi=True,
            as_html=False,
            map_df=calculate_map_frame(frame, PRED_TARGET),
        )


@pytest.mark.red_team
def test_hdi_fallback_renders_draw0():
    """CHARACTERIZATION (C-207, pre-guard, LIVE variant): with all HDI levels
    failing, the "(HDI unavailable)" fallback line IS posterior draw #0."""
    frame = _cm_frame(3, 12, s=300)
    fig = _fallback_fig(frame)
    mask = frame.index.unit == 1
    order = np.argsort(frame.index.time[mask])
    draw0 = frame.values[mask][order][:, 0]
    fallback = [t for t in fig.data if "HDI unavailable" in (t.name or "")]
    assert len(fallback) == 1
    assert np.allclose(np.asarray(fallback[0].y, dtype=np.float32), draw0)
