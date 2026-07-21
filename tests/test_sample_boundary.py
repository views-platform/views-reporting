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


def _mock_labels(index, level, with_id=False):
    # the #251 combined accessor: both labels from one resolution
    ents = index.get_level_values(index.names[1])
    return pd.DataFrame(
        {"isoab": ["AAA"] * len(index), "name": [f"Country {e}" for e in ents]},
        index=index,
    )


# ── The mapping seam (frames_to_mapping_df) ──────────────────────────────────


@pytest.mark.red_team
def test_seam_refuses_uncollapsed_sample_frame():
    """ENFORCED (C-207): an uncollapsed S>1 frame is refused loudly — pre-guard
    it silently rendered posterior draw #0 (≠ tower MAP; probe P5). The message
    names the remedy."""
    frame = _cm_frame(5, 6, s=200)
    with pytest.raises(ValueError, match="calculate_map_frame"):
        frames_to_mapping_df(frame, PRED_TARGET, SpatialLevel.CM)


@pytest.mark.green_team
def test_collapsed_frame_equals_tower_map_through_seam():
    """The sanctioned pipeline end-to-end: collapse → seam yields exactly the
    tower MAP (the faithfulness the guard protects)."""
    frame = _cm_frame(5, 6, s=200)
    map_df = calculate_map_frame(frame, PRED_TARGET)
    idx1 = SpatioTemporalIndex(
        time=map_df.index.get_level_values("month_id").to_numpy(dtype=np.int64),
        unit=map_df.index.get_level_values("country_id").to_numpy(dtype=np.int64),
        level=SpatialLevel.CM,
    )
    collapsed = PredictionFrame(
        map_df.iloc[:, 0].to_numpy(dtype=np.float32).reshape(-1, 1), idx1
    )
    with patch.object(frame_adapter, "get_labels_for_index", side_effect=_mock_labels):
        out = frames_to_mapping_df(collapsed, PRED_TARGET, SpatialLevel.CM)
    assert np.allclose(
        np.sort(out[PRED_TARGET].to_numpy()),
        np.sort(map_df.iloc[:, 0].to_numpy(dtype=np.float32)),
    )


@pytest.mark.green_team
def test_seam_accepts_collapsed_frame():
    """The sanctioned path: a collapsed S==1 frame crosses the seam unchanged."""
    frame = _cm_frame(5, 6, s=1)
    with patch.object(frame_adapter, "get_labels_for_index", side_effect=_mock_labels):
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
def test_hdi_fallback_renders_map_not_draw0():
    """ENFORCED (C-207, the LIVE variant fixed): with all HDI levels failing,
    the fallback line is the tower MAP — pre-guard it was posterior draw #0
    (probe P6 demonstrated the live bug)."""
    frame = _cm_frame(3, 12, s=300)
    fig = _fallback_fig(frame)
    mask = frame.index.unit == 1
    order = np.argsort(frame.index.time[mask])
    draw0 = frame.values[mask][order][:, 0]
    map_df = calculate_map_frame(frame, PRED_TARGET)
    expected_map = map_df.xs(1, level="country_id")[f"{PRED_TARGET}_map"].to_numpy()
    fallback = [t for t in fig.data if "HDI unavailable" in (t.name or "")]
    assert len(fallback) == 1
    y = np.asarray(fallback[0].y, dtype=np.float32)
    assert np.allclose(y, expected_map.astype(np.float32))  # the honest summary
    assert not np.allclose(y, draw0)  # never an arbitrary draw again


@pytest.mark.red_team
def test_hdi_fallback_without_map_renders_nothing_fabricated(caplog):
    """When HDI fails at every level AND no MAP frame exists, no forecast line
    is fabricated — visible absence + a loud log (C-11), never draw #0."""

    def boom(*a, **k):
        raise ValueError("forced HDI failure (test)")

    frame = _cm_frame(2, 6, s=100)
    with patch.object(hist_mod, "get_name_for_index", side_effect=_mock_name), \
         patch.object(hist_mod, "calculate_hdi_frame", side_effect=boom), \
         caplog.at_level("ERROR", logger="views_reporting.visualizations.historical"):
        hlg = HistoricalLineGraph(
            historical_frame=None, forecast_frame=frame, level=SpatialLevel.CM
        )
        fig = hlg._plot_interactive(
            entity_ids=[1],
            target=TARGET,
            alpha=0.9,
            vline=None,
            hdi=True,
            as_html=False,
            map_df=None,  # MAP also unavailable
        )
    assert len(fig.data) == 0  # nothing fabricated
    assert any("no forecast line rendered" in r.message for r in caplog.records)


@pytest.mark.green_team
def test_sample_line_graph_still_renders_hdi_and_map():
    """The sanctioned S>1 flow is unbroken: bands + MAP line render from a raw
    sample frame (the surface the eval template uses, evaluation.py:555-568)."""
    frame = _cm_frame(3, 12, s=300)
    with patch.object(hist_mod, "get_name_for_index", side_effect=_mock_name):
        hlg = HistoricalLineGraph(
            historical_frame=None, forecast_frame=frame, level=SpatialLevel.CM
        )
        fig = hlg._plot_interactive(
            entity_ids=[1, 2],
            target=TARGET,
            alpha=0.9,
            vline=None,
            hdi=True,
            as_html=False,
            map_df=calculate_map_frame(frame, PRED_TARGET),
            hdi_levels=[0.9, 0.95],
        )
    names = [t.name or "" for t in fig.data]
    assert any("(MAP)" in n for n in names)  # the summary line
    assert len(fig.data) > 2  # bands present
    assert not any("HDI unavailable" in n for n in names)  # no degradation


@pytest.mark.red_team
def test_pred_df_refuses_sample_frame():
    """The historical seam contract: _pred_df on an S>1 frame raises (it would
    read draw #0); the point-forecast path (S==1) is unaffected."""
    frame = _cm_frame(2, 6, s=50)
    with patch.object(hist_mod, "get_name_for_index", side_effect=_mock_name):
        hlg = HistoricalLineGraph(
            historical_frame=None, forecast_frame=frame, level=SpatialLevel.CM
        )
        with pytest.raises(ValueError, match="C-207"):
            hlg._pred_df(1, TARGET)


@pytest.mark.green_team
def test_point_forecast_line_graph_unaffected():
    """hdi=False with a genuine S==1 point frame renders the plain forecast line."""
    frame = _cm_frame(2, 6, s=1)
    with patch.object(hist_mod, "get_name_for_index", side_effect=_mock_name):
        hlg = HistoricalLineGraph(
            historical_frame=None, forecast_frame=frame, level=SpatialLevel.CM
        )
        fig = hlg._plot_interactive(
            entity_ids=[1],
            target=TARGET,
            alpha=0.9,
            vline=None,
            hdi=False,
            as_html=False,
        )
    assert len(fig.data) == 1
    assert np.allclose(
        np.asarray(fig.data[0].y, dtype=np.float32),
        frame.values[frame.index.unit == 1][:, 0],
    )
