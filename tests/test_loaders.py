"""
Tests for the views_reporting.loaders package.

Covers registry dispatch, DataFrameLoader, PredictionFrameLoader,
and the public load_predictions() API. Fixture-dependent tests skip
when data is absent.
"""

import glob
import json
from pathlib import Path

import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset, PGMDataset
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

from views_reporting.loaders import (
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
from views_reporting.statistics import calculate_map

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

    def test_cm_parquet_loads_dataset(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        loader = DataFrameLoader()
        ds = loader.load_single_origin(Path(files[0]), "cm", manifest["targets"])

        assert isinstance(ds, CMDataset)
        assert ds.sample_size == 1
        assert ds.is_prediction

    def test_pgm_parquet_loads_dataset(self):
        manifest = _manifest("average_pgmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_pgmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_pgmbaseline parquets")

        loader = DataFrameLoader()
        ds = loader.load_single_origin(Path(files[0]), "pgm", manifest["targets"])

        assert isinstance(ds, PGMDataset)
        assert ds.sample_size == 1

    def test_parquet_multi_origin(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        loader = DataFrameLoader()
        datasets = loader.load_multi_origin(
            [Path(f) for f in files], "cm", manifest["targets"]
        )

        assert len(datasets) == 13
        assert all(isinstance(ds, CMDataset) for ds in datasets)

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
        loaded as a prediction dataset — the dataset constructor fails loud
        with ValueError. EvaluationReportTemplate relies on this contract to
        skip such sequences gracefully (C-32); if pipeline-core ever changes
        the error type, this test fails and flags that the skip will degrade.
        """
        from tests.conftest import build_cm_historical_df

        df = build_cm_historical_df(n_months=2, n_countries=3)  # no pred_* columns
        path = tmp_path / "no_predictions.parquet"
        df.to_parquet(path)

        # Positive control: the frame is otherwise valid — it constructs fine
        # when targets are supplied — so the raise below is specifically from
        # the missing prediction columns, not an unrelated frame defect.
        assert isinstance(CMDataset(df, targets=["ged_sb"]), CMDataset)

        with pytest.raises(ValueError):
            load_predictions("dataframe", path, "cm", ["ged_sb"])


# ── PredictionFrameLoader tests ──────────────────────────────────────────


class TestPredictionFrameLoader:

    def test_cm_numpy_loads_dataset(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        ds = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        assert isinstance(ds, CMDataset)
        assert ds.sample_size == 256
        assert ds.is_prediction

    def test_numpy_index_names_correct(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        ds = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        assert ds.dataframe.index.names == ["month_id", "country_id"]

    def test_numpy_multi_origin(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        paths = [pf_dir / f"origin_{i}" for i in range(13)]
        if not all(p.exists() for p in paths):
            pytest.skip("Not all 13 origins present")

        loader = PredictionFrameLoader()
        datasets = loader.load_multi_origin(paths, "cm", manifest["targets"])

        assert len(datasets) == 13
        assert all(isinstance(ds, CMDataset) for ds in datasets)
        assert all(ds.sample_size == 256 for ds in datasets)

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

    def test_loaded_numpy_dataset_calculates_map(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        loader = PredictionFrameLoader()
        ds = loader.load_single_origin(
            pf_dir / "origin_0", "cm", manifest["targets"]
        )

        target_col = f"pred_{manifest['targets'][0]}"
        map_df = calculate_map(ds, features=[target_col], alpha=0.9)
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

        ds = load_predictions("dataframe", Path(files[0]), "cm", manifest["targets"])
        assert isinstance(ds, CMDataset)
        assert ds.sample_size == 1

    def test_load_predictions_dispatches_prediction_frame(self):
        manifest = _manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip("No red_ranger predictions")

        ds = load_predictions(
            "prediction_frame",
            pf_dir / "origin_0",
            "cm",
            manifest["targets"],
        )
        assert isinstance(ds, CMDataset)
        assert ds.sample_size == 256

    def test_load_prediction_sequence_works(self):
        manifest = _manifest("average_cmbaseline")
        ts = manifest["run_timestamp"]
        files = sorted(glob.glob(
            str(FIXTURE_DIR / "average_cmbaseline" / f"predictions_calibration_{ts}_*.parquet")
        ))
        if not files:
            pytest.skip("No average_cmbaseline parquets")

        datasets = load_prediction_sequence(
            "dataframe", [Path(f) for f in files], "cm", manifest["targets"]
        )
        assert len(datasets) == 13

    def test_load_predictions_unknown_format_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No loader registered"):
            load_predictions("nosuchformat", tmp_path, "cm", ["t"])
