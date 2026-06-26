"""CIC coverage for MetricFrameFileSource (sources/metric_frame_file_source.py).

Round-trips a saved MetricFrame off disk; missing directory → absent (None).
"""

import sys
from pathlib import Path

import pytest

try:
    from views_evaluation.evaluation.metric_frame import (
        FrameMetadata,  # noqa: F401  (presence check; imported lazily below)
    )
except Exception:  # pragma: no cover
    FrameMetadata = None

try:
    from views_reporting.sources import MetricFrameFileSource, mean_metric_value
except ImportError:
    pytest.skip("views_evaluation[frames] not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
from _eval_source_doubles import make_metric_frame  # noqa: E402

TARGET = "lr_ged_sb"


@pytest.mark.green_team
class TestMetricFrameFileSource:
    def _save(self, root: Path, model: str, run_type: str, frame) -> None:
        frame.save(root / model / run_type / f"metricframe_{TARGET}")

    def test_round_trips_persisted_frame(self, tmp_path):
        frame = make_metric_frame({"MSLE": 0.42, "CRPS": 0.93}, target=TARGET)
        self._save(tmp_path, "red_ranger", "calibration", frame)
        source = MetricFrameFileSource(
            tmp_path, "calibration", TARGET, "red_ranger"
        )
        loaded = source.metric_frame("red_ranger")
        assert loaded is not None
        assert mean_metric_value(
            loaded, eval_type="time-series-wise", target=TARGET, metric="MSLE"
        ) == pytest.approx(0.42)

    def test_missing_directory_is_absent(self, tmp_path):
        source = MetricFrameFileSource(
            tmp_path, "calibration", TARGET, "red_ranger"
        )
        assert source.metric_frame("red_ranger") is None

    def test_provenance_when_subject_absent(self, tmp_path):
        # No subject frame on disk → a minimal provenance, never a crash.
        source = MetricFrameFileSource(
            tmp_path, "calibration", TARGET, "red_ranger"
        )
        prov = source.provenance()
        assert prov.run_id == "unknown"
        assert prov.run_url is None and prov.owner is None
