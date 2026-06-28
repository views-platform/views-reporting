"""Input values-completeness guard at the ingestion boundary (register C-111).

The structural conformance contract (float32 / sample axis / integer ids) does not
inspect the *values* for NaN. `assert_conformant` adds the values half: a wholly-NaN
frame is a broken input → raise (ADR-008 fail-loud); partial NaN is legitimate
(sparse cells) → warn, not raise. (Expected entity/time *coverage* — the other half
of C-111 — is deferred to the C-108 Phase-3 typed input contract.)
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
