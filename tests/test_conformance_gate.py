"""S5 — ingestion conformance gate (epic #137, #140, register C-111).

Every frame the loaders produce is run through `views_frames.conformance.
assert_frame_contract` at the ingestion boundary (ADR-009 §1b), and the governed
conformance floor is pinned so a leaf bump is caught rather than silently drifting.
"""

import pytest

from tests.conftest import build_cm_forecast_df, build_cm_historical_df

pytest.importorskip("views_frames")

from views_reporting.loaders import _constants  # noqa: E402
from views_reporting.loaders._constants import (  # noqa: E402
    EXPECTED_CONFORMANCE_FLOOR,
    assert_conformant,
)
from views_reporting.loaders.dataframe_loader import (  # noqa: E402
    frames_from_dataframe,
    target_frame_from_dataframe,
)


def test_conformance_floor_pinned():
    """The leaf's governed floor must match what this consumer is tested against;
    a bump should trip here and force a deliberate re-validation (no silent drift)."""
    from views_frames.conformance import CONFORMANCE_FLOOR

    assert EXPECTED_CONFORMANCE_FLOOR == "1.0.0"
    assert CONFORMANCE_FLOOR == EXPECTED_CONFORMANCE_FLOOR


def test_loaded_prediction_frames_are_conformant():
    """frames_from_dataframe output passes the contract (sample + scalar paths)."""
    df = build_cm_forecast_df(n_months=2, n_countries=3, n_samples=40, seed=42)
    frames = frames_from_dataframe(df, "cm", ["ged_sb"])
    # No raise == conformant; re-assert explicitly for clarity.
    for frame in frames.values():
        assert assert_conformant(frame) is frame


def test_loaded_target_frame_is_conformant():
    df = build_cm_historical_df(n_months=4, n_countries=3, seed=99)
    tf = target_frame_from_dataframe(df, "cm", "ged_sb")
    assert assert_conformant(tf) is tf
    assert tf.values.shape[1] == 1  # actuals: explicit trailing axis, S == 1


def test_ingestion_invokes_the_gate(monkeypatch):
    """Fail-loud is actually wired: if the contract check raises, ingestion raises
    (the gate is not a no-op). Proves the boundary calls assert_frame_contract."""

    def _boom(_frame):
        raise AssertionError("contract violated")

    monkeypatch.setattr(_constants, "assert_frame_contract", _boom)
    df = build_cm_forecast_df(n_months=1, n_countries=2, n_samples=10, seed=1)
    with pytest.raises(AssertionError, match="contract violated"):
        frames_from_dataframe(df, "cm", ["ged_sb"])
