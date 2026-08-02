"""
Tests for the views_reporting.loaders package.

Covers registry dispatch, DataFrameLoader, PredictionFrameLoader,
and the public load_predictions() API (now returning dict[str, PredictionFrame]).
Fixture-dependent tests skip when data is absent.
"""

import glob
import json
from pathlib import Path

import pytest

try:
    from views_frames import PredictionFrame
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

from views_reporting.loaders import (
    frames_from_dataframe,
    load_prediction_sequence,
    load_predictions,
)
from views_reporting.loaders._registry import (
    _LOADER_REGISTRY,
    get_loader,
    register_loader,
)
from views_reporting.loaders.dataframe_loader import DataFrameLoader
from views_reporting.loaders.prediction_frame_loader import PredictionFrameLoader
from views_reporting.statistics import calculate_map_frame

FIXTURE_DIR = Path(__file__).parent / "data"


def _manifest(model_name):
    path = FIXTURE_DIR / model_name / "manifest.json"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return json.loads(path.read_text())


# ── Registry tests ───────────────────────────────────────────────────────


class TestRegistry:

    def test_builtin_formats_registered(self):
        assert "dataframe" in _LOADER_REGISTRY
        assert "prediction_frame" in _LOADER_REGISTRY

    def test_get_loader_returns_correct_type(self):
        loader = get_loader("dataframe")
        assert isinstance(loader, DataFrameLoader)

        loader = get_loader("prediction_frame")
        assert isinstance(loader, PredictionFrameLoader)

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="No loader registered"):
            get_loader("nosuchformat")

    def test_unknown_format_lists_registered(self):
        with pytest.raises(ValueError, match="dataframe"):
            get_loader("nosuchformat")

    def test_duplicate_registration_raises(self):
        with pytest.raises(ValueError, match="already registered"):
            register_loader("dataframe", DataFrameLoader)


# ── DataFrameLoader tests ────────────────────────────────────────────────


class TestDataFrameLoader:

    def test_cm_parquet_loads_frames(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        loader = DataFrameLoader()
        frames = loader.load_single_origin(Path(files[0]), "cm", manifest["targets"])

        assert isinstance(frames, dict)
        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 1  # point estimate

    def test_pgm_parquet_loads_frames(self):
        manifest = _manifest("average_pgmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_pgmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_pgmbaseline parquets")

        loader = DataFrameLoader()
        frames = loader.load_single_origin(Path(files[0]), "pgm", manifest["targets"])

        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 1

    def test_parquet_multi_origin(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        loader = DataFrameLoader()
        results = loader.load_multi_origin(
            [Path(f) for f in files], "cm", manifest["targets"]
        )

        assert len(results) == 13
        target = manifest["targets"][0]
        assert all(isinstance(r[target], PredictionFrame) for r in results)

    def test_parquet_missing_file_raises(self, tmp_path):
        loader = DataFrameLoader()
        with pytest.raises((FileNotFoundError, OSError)):
            loader.load_single_origin(
                tmp_path / "nonexistent.parquet", "cm", ["lr_ged_sb"]
            )

    def test_invalid_level_raises(self, tmp_path):
        loader = DataFrameLoader()
        with pytest.raises(ValueError, match="Unknown level"):
            loader.load_single_origin(tmp_path / "f.parquet", "xyz", ["t"])

    def test_parquet_without_prediction_columns_raises(self, tmp_path):
        """Red: a parquet with a valid index but no pred_* columns cannot be
        loaded as predictions — frames_from_dataframe fails loud with ValueError.
        EvaluationReportTemplate relies on this contract to skip such sequences
        gracefully (C-32).
        """
        from tests.conftest import build_cm_historical_df

        df = build_cm_historical_df(n_months=2, n_countries=3)  # no pred_* columns
        path = tmp_path / "no_predictions.parquet"
        df.to_parquet(path)

        with pytest.raises(ValueError):
            load_predictions("dataframe", path, "cm", ["ged_sb"])

    def test_frames_from_dataframe_no_pred_columns_raises(self):
        """The no-prediction-columns ValueError contract, exercised directly."""
        from tests.conftest import build_cm_historical_df

        df = build_cm_historical_df(n_months=2, n_countries=3)
        with pytest.raises(ValueError, match="No usable prediction columns"):
            frames_from_dataframe(df, "cm", ["ged_sb"])


# ── PredictionFrameLoader tests ──────────────────────────────────────────


class TestPredictionFrameLoader:

    def test_cm_numpy_loads_frames(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        frames = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 256

    def test_numpy_index_level_cm(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        frames = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        from views_frames import SpatialLevel
        target = manifest["targets"][0]
        assert frames[target].index.level == SpatialLevel.CM
        assert frames[target].index.level.index_names == ("month_id", "country_id")

    def test_numpy_multi_origin(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        paths = [pf_dir / f"origin_{i}" for i in range(13)]
        if not all(p.exists() for p in paths):
            pytest.skip("Not all 13 origins present")

        loader = PredictionFrameLoader()
        results = loader.load_multi_origin(paths, "cm", manifest["targets"])

        assert len(results) == 13
        target = manifest["targets"][0]
        assert all(r[target].sample_count == 256 for r in results)

    def test_numpy_missing_directory_raises(self, tmp_path):
        loader = PredictionFrameLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_single_origin(
                tmp_path / "nonexistent", "cm", ["lr_ged_sb"]
            )

    def test_invalid_level_raises(self, tmp_path):
        loader = PredictionFrameLoader()
        with pytest.raises(ValueError, match="Unknown level"):
            loader.load_single_origin(tmp_path, "xyz", ["t"])


# ── Integration: load → compute ──────────────────────────────────────────


@pytest.mark.slow
class TestLoaderIntegration:

    def test_loaded_numpy_frame_calculates_map(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        frames = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        target = manifest["targets"][0]
        target_col = f"pred_{target}"
        map_df = calculate_map_frame(frames[target], target_col)
        assert f"{target_col}_map" in map_df.columns
        assert not map_df[f"{target_col}_map"].isna().all()


# ── Public API tests ─────────────────────────────────────────────────────


class TestPublicAPI:

    def test_load_predictions_dispatches_dataframe(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        frames = load_predictions(
            "dataframe", Path(files[0]), "cm", manifest["targets"]
        )
        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 1

    def test_load_predictions_dispatches_prediction_frame(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        frames = load_predictions(
            "prediction_frame",
            pf_dir / "origin_0",
            "cm",
            manifest["targets"],
        )
        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 256

    def test_load_prediction_sequence_works(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        results = load_prediction_sequence(
            "dataframe", [Path(f) for f in files], "cm", manifest["targets"]
        )
        assert len(results) == 13
        assert all(isinstance(r, dict) for r in results)

    def test_load_predictions_unknown_format_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No loader registered"):
            load_predictions("nosuchformat", tmp_path, "cm", ["t"])


@pytest.mark.green_team
def test_iter_predictions_streams_one_target_at_a_time(tmp_path, monkeypatch):
    """C-212 / #235: the streaming seam is genuinely lazy — pulling the first
    (target, frame) pair must load ONLY that target's arrays from disk; the
    next target's files are untouched until the consumer asks."""
    import numpy as np

    from views_reporting.loaders import iter_predictions

    for t in ("alpha", "beta"):
        d = tmp_path / t
        d.mkdir()
        np.save(d / "y_pred.npy", np.ones((6, 4), dtype=np.float32))
        np.savez(
            d / "identifiers.npz",
            time=np.repeat(np.arange(540, 543, dtype=np.int64), 2),
            unit=np.tile(np.array([62356, 62357], dtype=np.int64), 3),
        )

    loaded: list = []
    real_load = np.load

    def spy_load(path, *a, **kw):
        p = Path(path)
        # count only OUR staged files — frame conformance checks do their own
        # tempdir save/load round-trips that are not target loads
        if p.parent.parent == tmp_path:
            loaded.append(p.parent.name)
        return real_load(path, *a, **kw)

    monkeypatch.setattr(np, "load", spy_load)

    it = iter_predictions("prediction_frame", tmp_path, "pgm", ["alpha", "beta"])
    assert loaded == []  # nothing loads until the consumer pulls
    target, frame = next(it)
    assert target == "alpha" and frame.sample_count == 4
    assert set(loaded) == {"alpha"}, "second target loaded eagerly"
    target2, _ = next(it)
    assert target2 == "beta" and "beta" in set(loaded)
