"""
CIC coverage for report utility functions (filter_metrics_from_dict,
search_for_item_name, filter_metrics_by_eval_type_and_metrics).

All pure functions — no mocking needed.
"""

import pytest

try:
    from views_reporting.reports.utils import (
        filter_metrics_by_eval_type_and_metrics,
        filter_metrics_from_dict,
        search_for_item_name,
    )
except ImportError:
    import pytest
    pytest.skip(
        "views_pipeline_core not installed (required by reports/__init__.py)",
        allow_module_level=True,
    )


# ── search_for_item_name (green team) ────────────────────────────────────


@pytest.mark.green_team
class TestSearchForItemName:

    def test_single_match(self):
        searchspace = ["eval/mse/ged_sb_best", "eval/mae/ged_sb_best", "train/loss"]
        result = search_for_item_name(searchspace, ["mse", "ged_sb_best"])
        assert result == "eval/mse/ged_sb_best"

    def test_no_match_returns_none(self):
        searchspace = ["eval/mse/ged_sb_best", "eval/mae/ged_sb_best"]
        result = search_for_item_name(searchspace, ["nonexistent"])
        assert result is None

    def test_empty_keywords_returns_none(self):
        result = search_for_item_name(["a", "b", "c"], [])
        assert result is None

    def test_multiple_matches_raises_by_default(self):
        # C-116: a multi-match is ambiguous; the default must fail loud rather than
        # silently return the first (which would surface a possibly-wrong number).
        searchspace = ["eval/mse/target_a", "eval/mse/target_b"]
        with pytest.raises(ValueError, match="[Aa]mbiguous"):
            search_for_item_name(searchspace, ["mse"])

    def test_multiple_matches_first_when_lenient(self):
        searchspace = ["eval/mse/target_a", "eval/mse/target_b"]
        result = search_for_item_name(searchspace, ["mse"], on_ambiguous="first")
        assert result == "eval/mse/target_a"

    def test_multiple_matches_none_when_lenient(self):
        searchspace = ["eval/mse/target_a", "eval/mse/target_b"]
        assert search_for_item_name(searchspace, ["mse"], on_ambiguous="none") is None


# ── canonical-metric collision contract (C-116) ──────────────────────────


@pytest.mark.green_team
class TestCanonicalMetricCollisions:
    """C-116 proactive guard: the canonical report-metric tokens must be
    collision-free, so no token segment-matches more than one key in a realistic
    run summary (which would render an ambiguous / possibly-wrong value). Enforces
    the documented-but-previously-unenforced segment-prefix rule (config/_reporting.py)."""

    def test_no_canonical_token_is_ambiguous_against_its_own_keyset(self):
        from views_reporting.config import get_config

        cfg = get_config()
        target = "lr_ged_sb"
        for eval_type in ("time-series-wise", "step-wise", "month-wise"):
            for cell, metrics in cfg.canonical_report_metrics.items():
                # a realistic run summary: one `_mean` key per canonical metric
                keyset = [f"{eval_type}/{target}/{m}_mean" for m in metrics]
                for m in metrics:
                    # default (raise) must NOT raise → tokens are collision-free,
                    # and each resolves to its own key.
                    found = search_for_item_name(
                        keyset, [eval_type, m, target, "mean"]
                    )
                    assert found == f"{eval_type}/{target}/{m}_mean", (
                        f"canonical token '{m}' in cell {cell} is ambiguous or "
                        f"mismatched against its own keyset {keyset}"
                    )


# ── filter_metrics_from_dict (green team) ─────────────────────────────────


@pytest.mark.green_team
class TestFilterMetricsFromDict:

    def test_filters_by_target_and_metric(self):
        eval_dict = {
            "eval/mse/ged_sb_best": 0.5,
            "eval/mae/ged_sb_best": 0.3,
            "eval/mse/other_target": 0.9,
        }
        result = filter_metrics_from_dict(
            eval_dict, metrics=["mse"], target_identifier="ged_sb_best"
        )
        assert "eval/mse/ged_sb_best" in result.columns
        assert "eval/mse/other_target" not in result.columns

    def test_with_model_name_index(self):
        eval_dict = {"eval/mse/ged_sb_best": 0.5}
        result = filter_metrics_from_dict(
            eval_dict,
            metrics=["mse"],
            target_identifier="ged_sb_best",
            model_name="test_model",
        )
        assert result.index.name == "Model Name"
        assert result.index[0] == "test_model"

    def test_no_match_returns_empty(self):
        eval_dict = {"eval/mse/ged_sb_best": 0.5}
        result = filter_metrics_from_dict(
            eval_dict, metrics=["nonexistent"], target_identifier="ged_sb_best"
        )
        assert len(result.columns) == 0 or result.empty


# ── filter_metrics_by_eval_type_and_metrics (green + red team) ───────────


@pytest.mark.green_team
class TestFilterMetricsByEvalType:

    def test_filters_correctly(self):
        eval_dict = {
            "step-wise/mse/ged_sb_best": 0.5,
            "step-wise/mae/ged_sb_best": 0.3,
            "full/mse/ged_sb_best": 0.9,
        }
        result = filter_metrics_by_eval_type_and_metrics(
            evaluation_dict=eval_dict,
            eval_type="step-wise",
            metrics=["mse"],
            target_identifier="ged_sb_best",
            model_name="test_model",
        )
        assert len(result.columns) >= 1
        assert result.index[0] == "test_model"


@pytest.mark.red_team
class TestFilterMetricsValidation:

    def test_metrics_not_list_raises(self):
        with pytest.raises(ValueError, match="list"):
            filter_metrics_by_eval_type_and_metrics(
                evaluation_dict={},
                eval_type="step-wise",
                metrics="mse",
                target_identifier="target",
                model_name="m",
            )

    def test_eval_type_not_string_raises(self):
        with pytest.raises(ValueError, match="string"):
            filter_metrics_by_eval_type_and_metrics(
                evaluation_dict={},
                eval_type=123,
                metrics=["mse"],
                target_identifier="target",
                model_name="m",
            )

    def test_eval_dict_not_dict_raises(self):
        with pytest.raises(ValueError, match="dictionary"):
            filter_metrics_by_eval_type_and_metrics(
                evaluation_dict="not_a_dict",
                eval_type="step-wise",
                metrics=["mse"],
                target_identifier="target",
                model_name="m",
            )
