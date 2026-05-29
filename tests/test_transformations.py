"""
CIC coverage for DatasetTransformationModule.

Tests round-trip correctness, column mapping, and C-04 reproduction.
Uses SimpleNamespace mock to avoid views_pipeline_core dependency.
"""

from types import SimpleNamespace

import pytest

try:
    import polars as pl

    from views_reporting.transformations.transformations import (
        DatasetTransformationModule,
    )
except ImportError:
    pytest.skip(
        "polars or views_pipeline_core not installed",
        allow_module_level=True,
    )


@pytest.fixture
def mock_dataset():
    df = pl.DataFrame({
        "month_id": [1, 1, 2, 2],
        "country_id": [1, 2, 1, 2],
        "ged_sb_dep": [10.0, 0.0, 5.0, 20.0],
        "feature_1": [100.0, 200.0, 150.0, 250.0],
    })
    return SimpleNamespace(
        dataframe=df,
        _time_id="month_id",
        _entity_id="country_id",
    )


def _get_values(transformer, col_name):
    return [float(v) for v in transformer.dataframe[col_name].to_list()]


# ── Green team: round-trip correctness ───────────────────────────────────


@pytest.mark.green_team
class TestRoundTrip:

    def test_ln_round_trip(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        originals = _get_values(t, "ged_sb_dep")

        t.ln_transform(["ged_sb_dep"])
        assert "ln_ged_sb_dep" in t.dataframe.columns

        t.undo_ln_transform(["ln_ged_sb_dep"])
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-10, f"{orig} != {rec}"

    def test_lx_round_trip_default_offset(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        originals = _get_values(t, "ged_sb_dep")

        t.lx_transform(["ged_sb_dep"])
        assert "lx_ged_sb_dep" in t.dataframe.columns

        t.undo_lx_transform(["lx_ged_sb_dep"])
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-10, f"{orig} != {rec}"

    def test_lx_round_trip_custom_offset(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        originals = _get_values(t, "ged_sb_dep")

        t.lx_transform(["ged_sb_dep"], offset=-50)
        t.undo_lx_transform(["lx_ged_sb_dep"], offset=-50)
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-10, f"{orig} != {rec}"

    def test_lr_round_trip(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        originals = _get_values(t, "ged_sb_dep")

        t.lr_transform(["ged_sb_dep"])
        assert "lr_ged_sb_dep" in t.dataframe.columns

        t.undo_lr_transform(["lr_ged_sb_dep"])
        recovered = _get_values(t, "ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert orig == rec


# ── Red team: C-04 reproduction ──────────────────────────────────────────


@pytest.mark.red_team
class TestC04Reproduction:

    @staticmethod
    def _make_tiny_dataset():
        from types import SimpleNamespace
        df = pl.DataFrame({
            "month_id": [1, 1],
            "country_id": [1, 2],
            "ged_sb_dep": [1e-20, 1e-25],
        })
        return SimpleNamespace(
            dataframe=df, _time_id="month_id", _entity_id="country_id",
        )

    def test_undo_all_with_non_default_offset(self):
        """C-04: undo_all_transformations() must read offset from history."""
        tiny = self._make_tiny_dataset()
        t = DatasetTransformationModule(tiny)
        originals = _get_values(t, "ged_sb_dep")

        t.lx_transform(["ged_sb_dep"], offset=-50)
        t.undo_all_transformations()
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-6 * max(abs(orig), 1e-30), (
                f"C-04: undo_all used wrong offset. Expected {orig}, got {rec}"
            )

    def test_undo_transformations_with_non_default_offset(self):
        """Same bug in undo_transformations() — also hardcodes -100."""
        tiny = self._make_tiny_dataset()
        t = DatasetTransformationModule(tiny)
        originals = _get_values(t, "ged_sb_dep")

        t.lx_transform(["ged_sb_dep"], offset=-50)
        t.undo_transformations(["lx_ged_sb_dep"])
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-6 * max(abs(orig), 1e-30), (
                f"C-04: undo_transformations used wrong offset. Expected {orig}, got {rec}"
            )


# ── Green team: undo_all round-trip with various offsets ──────────────────


@pytest.mark.green_team
class TestUndoAllOffsets:

    @staticmethod
    def _make_dataset(values):
        from types import SimpleNamespace
        df = pl.DataFrame({
            "month_id": [1] * len(values),
            "country_id": list(range(1, len(values) + 1)),
            "ged_sb_dep": values,
        })
        return SimpleNamespace(
            dataframe=df, _time_id="month_id", _entity_id="country_id",
        )

    @pytest.mark.parametrize("offset", [-10, -50, -100, -200])
    def test_undo_all_round_trip(self, offset):
        ds = self._make_dataset([1.0, 10.0, 100.0])
        t = DatasetTransformationModule(ds)
        originals = _get_values(t, "ged_sb_dep")

        t.lx_transform(["ged_sb_dep"], offset=offset)
        t.undo_all_transformations()
        recovered = _get_values(t, "lr_ged_sb_dep")

        for orig, rec in zip(originals, recovered):
            assert abs(orig - rec) < 1e-8, f"offset={offset}: {orig} != {rec}"


# ── Beige team: mixed transforms with undo_all ──────────────────────────


@pytest.mark.beige_team
class TestMixedTransformUndoAll:

    def test_ln_and_lx_undo_all_both_recover(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        orig_ged = _get_values(t, "ged_sb_dep")
        orig_feat = _get_values(t, "feature_1")

        t.ln_transform(["ged_sb_dep"])
        t.lx_transform(["feature_1"], offset=-50)
        t.undo_all_transformations()

        rec_ged = _get_values(t, "lr_ged_sb_dep")
        rec_feat = _get_values(t, "lr_feature_1")

        for o, r in zip(orig_ged, rec_ged):
            assert abs(o - r) < 1e-10, f"ln col: {o} != {r}"
        for o, r in zip(orig_feat, rec_feat):
            assert abs(o - r) < 1e-6 * max(abs(o), 1e-30), f"lx col: {o} != {r}"


# ── Green team: column mapping ───────────────────────────────────────────


@pytest.mark.green_team
class TestColumnMapping:

    def test_ln_updates_mapping(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        t.ln_transform(["ged_sb_dep"])
        assert t.get_current_column_name("ged_sb_dep") == "ln_ged_sb_dep"

    def test_undo_ln_updates_mapping(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        t.ln_transform(["ged_sb_dep"])
        t.undo_ln_transform(["ln_ged_sb_dep"])
        assert t.get_current_column_name("ged_sb_dep") == "lr_ged_sb_dep"

    def test_transformed_columns_tracks_changes(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        assert len(t.get_transformed_columns()) == 0

        t.ln_transform(["ged_sb_dep"])
        transformed = t.get_transformed_columns()
        assert "ged_sb_dep" in transformed
        assert transformed["ged_sb_dep"] == "ln_ged_sb_dep"

    def test_history_records_operations(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        t.ln_transform(["ged_sb_dep"])
        history = t.get_transformation_history()
        assert len(history) == 1
        assert history[0]["operation"] == "ln_transform"
        assert history[0]["old_name"] == "ged_sb_dep"
        assert history[0]["new_name"] == "ln_ged_sb_dep"


# ── Beige team: realistic usage ──────────────────────────────────────────


@pytest.mark.beige_team
class TestRealisticUsage:

    def test_get_dataframe_as_pandas(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        t.ln_transform(["ged_sb_dep"])
        df = t.get_dataframe(as_pandas=True)
        assert "ln_ged_sb_dep" in df.columns
        assert df.index.names == ["month_id", "country_id"]

    def test_duplicate_transform_skips(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        t.ln_transform(["ged_sb_dep"])
        t.ln_transform(["ln_ged_sb_dep"])
        assert "ln_ged_sb_dep" in t.dataframe.columns
        assert len(t.get_transformation_history()) == 1


# ── Red team: validation ─────────────────────────────────────────────────


@pytest.mark.red_team
class TestTransformValidation:

    def test_nonexistent_column_raises(self, mock_dataset):
        t = DatasetTransformationModule(mock_dataset)
        with pytest.raises(ValueError, match="not found"):
            t.ln_transform(["nonexistent"])

    def test_invalid_dataframe_type_raises(self):
        mock = SimpleNamespace(
            dataframe="not_a_dataframe",
            _time_id="month_id",
            _entity_id="country_id",
        )
        with pytest.raises(TypeError, match="Polars or Pandas"):
            DatasetTransformationModule(mock)
