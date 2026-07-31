"""Input values-completeness guard at the ingestion boundary (register C-111).

The structural conformance contract (float32 / sample axis / integer ids) does not
inspect the *values* for NaN. `assert_conformant` adds the values half: a wholly-NaN
frame is a broken input → raise (ADR-008 fail-loud); partial NaN is legitimate
(sparse cells) → warn, not raise. The coverage half (epic #262 S4, #266) applies
the same doctrine to the time/entity axes: interior time-axis gaps raise (certain
data loss), ragged entity coverage warns once (possibly legitimate). Truncation at
the END of a horizon stays undetectable without an external expectation — that
residual lives with the C-108 Phase-3 typed input contract.
"""

import logging

import numpy as np
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.loaders._constants import assert_conformant
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)


def _frame(values_2d):
    arr = np.asarray(values_2d, dtype=np.float32)
    n = arr.shape[0]
    idx = SpatioTemporalIndex(
        time=np.full(n, 528, dtype=np.int64),
        unit=np.arange(1, n + 1, dtype=np.int64),
        level=SpatialLevel.CM,
    )
    return PredictionFrame(arr, idx)


@pytest.mark.green_team
def test_clean_frame_passes_and_returns_self():
    frame = _frame([[1.0], [2.0], [3.0]])
    assert assert_conformant(frame) is frame


@pytest.mark.red_team
def test_all_nan_frame_raises():
    frame = _frame([[np.nan], [np.nan]])
    with pytest.raises(ValueError, match="entirely NaN"):
        assert_conformant(frame)


@pytest.mark.red_team
def test_partial_nan_warns_but_passes(caplog):
    frame = _frame([[1.0], [np.nan], [3.0]])
    with caplog.at_level(logging.WARNING):
        assert assert_conformant(frame) is frame
    assert any("NaN" in r.message for r in caplog.records), "partial NaN should warn"


# ── Coverage half (epic #262 S4, #266): gap → raise, ragged → warn ──────────


def _panel_frame(times, units):
    times = np.asarray(times, dtype=np.int64)
    units = np.asarray(units, dtype=np.int64)
    idx = SpatioTemporalIndex(time=times, unit=units, level=SpatialLevel.CM)
    return PredictionFrame(np.ones((len(times), 1), dtype=np.float32), idx)


@pytest.mark.red_team
def test_interior_time_gap_raises():
    """A month missing from the MIDDLE of the horizon is certain data loss
    (no producer emits a gapped horizon) — fail loud, naming the hole."""
    frame = _panel_frame(
        times=[600, 600, 601, 601, 603, 603],  # 602 missing
        units=[1, 2, 1, 2, 1, 2],
    )
    with pytest.raises(ValueError, match="602"):
        assert_conformant(frame)


@pytest.mark.green_team
def test_contiguous_months_pass():
    frame = _panel_frame(
        times=[600, 600, 601, 601, 602, 602],
        units=[1, 2, 1, 2, 1, 2],
    )
    assert assert_conformant(frame) is frame


@pytest.mark.red_team
def test_ragged_entity_coverage_warns_but_passes(caplog):
    """Entity coverage differing across months can be legitimate (country
    systems change) — degrade visibly: ONE aggregated warning, never a veto."""
    frame = _panel_frame(
        times=[600, 600, 600, 601, 601],  # month 601 lost unit 3
        units=[1, 2, 3, 1, 2],
    )
    with caplog.at_level(logging.WARNING):
        assert assert_conformant(frame) is frame
    coverage_warnings = [r for r in caplog.records if "coverage" in r.message]
    assert len(coverage_warnings) == 1, "expected exactly one aggregated warning"


@pytest.mark.green_team
def test_rectangular_panel_emits_no_coverage_warning(caplog):
    frame = _panel_frame(
        times=[600, 600, 601, 601],
        units=[1, 2, 1, 2],
    )
    with caplog.at_level(logging.WARNING):
        assert_conformant(frame)
    assert not [r for r in caplog.records if "coverage" in r.message]
