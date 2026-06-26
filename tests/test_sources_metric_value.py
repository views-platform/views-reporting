"""CIC coverage for the MetricFrame value query (sources/metric_value.py).

Pure reads over synthetic frames — no I/O, no WandB, no pipeline-core producer.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

try:
    from views_evaluation.evaluation.metric_frame import AXES, MEAN_GROUP_ID, MetricFrame

    from views_reporting.sources import (
        AmbiguousMetric,
        mean_metric_value,
        unique_axis_value,
    )
except ImportError:
    pytest.skip(
        "views_evaluation[frames] not installed", allow_module_level=True
    )

sys.path.insert(0, str(Path(__file__).parent))
from _eval_source_doubles import make_metric_frame  # noqa: E402

TARGET = "lr_ged_sb"
ET = "time-series-wise"


def _raw_frame(rows):
    """MetricFrame from explicit (eval_type, target, metric, group_id, partition,
    level, value) row tuples — for cases make_metric_frame's mean-only shape can't build."""
    cols = {a: [] for a in AXES}
    vals = []
    for eval_type, target, metric, group_id, partition, level, value in rows:
        cols["eval_type"].append(eval_type)
        cols["target"].append(target)
        cols["metric"].append(metric)
        cols["group_id"].append(group_id)
        cols["partition"].append(partition)
        cols["level"].append(level)
        vals.append(value)
    return MetricFrame(
        values=np.asarray(vals, dtype=np.float32).reshape(-1, 1),
        identifiers={a: np.asarray(cols[a], dtype=str) for a in AXES},
    )


@pytest.mark.green_team
class TestMeanMetricValue:
    def test_present_returns_float(self):
        f = make_metric_frame({"MSLE": 0.42}, target=TARGET)
        got = mean_metric_value(f, eval_type=ET, target=TARGET, metric="MSLE")
        assert got == pytest.approx(0.42)

    def test_absent_row_returns_none(self):
        f = make_metric_frame({"MSLE": 0.42}, target=TARGET)
        assert mean_metric_value(f, eval_type=ET, target=TARGET, metric="CRPS") is None

    def test_nan_returns_none(self):
        f = make_metric_frame({"MSE": float("nan")}, target=TARGET)
        assert mean_metric_value(f, eval_type=ET, target=TARGET, metric="MSE") is None

    def test_wrong_target_returns_none(self):
        f = make_metric_frame({"MSLE": 0.42}, target=TARGET)
        assert mean_metric_value(f, eval_type=ET, target="other", metric="MSLE") is None

    def test_only_mean_row_matches(self):
        # A per-group (non-mean) row must NOT be read as the value.
        f = _raw_frame([
            (ET, TARGET, "MSLE", "ts00", "p", "cm", 9.9),
            (ET, TARGET, "MSLE", MEAN_GROUP_ID, "p", "cm", 0.42),
        ])
        got = mean_metric_value(f, eval_type=ET, target=TARGET, metric="MSLE")
        assert got == pytest.approx(0.42)

    def test_duplicate_mean_rows_raise_ambiguous(self):
        # C-116: two mean rows for the same metric → ambiguous, never a picked number.
        f = make_metric_frame(
            {"MSLE": 0.51}, target=TARGET, extra_rows=[("MSLE", 0.99)]
        )
        with pytest.raises(AmbiguousMetric):
            mean_metric_value(f, eval_type=ET, target=TARGET, metric="MSLE")

    def test_empty_frame_returns_none(self):
        f = make_metric_frame({}, target=TARGET)
        assert f.n_rows == 0
        assert mean_metric_value(f, eval_type=ET, target=TARGET, metric="MSLE") is None


@pytest.mark.green_team
class TestUniqueAxisValue:
    def test_uniform_axis(self):
        f = make_metric_frame({"MSLE": 0.42}, target=TARGET, level="cm")
        assert unique_axis_value(f, "level") == "cm"

    def test_empty_frame_none(self):
        assert unique_axis_value(make_metric_frame({}, target=TARGET), "level") is None

    def test_non_uniform_raises(self):
        f = _raw_frame([
            (ET, TARGET, "MSLE", MEAN_GROUP_ID, "p", "cm", 0.1),
            (ET, TARGET, "MSLE", MEAN_GROUP_ID, "p", "pgm", 0.1),
        ])
        with pytest.raises(ValueError, match="not uniform"):
            unique_axis_value(f, "level")
