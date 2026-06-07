"""Tests for the in-package reporting configuration primitive.

Pure, dependency-free (no pipeline-core, no fixtures): the config module only
holds rendering defaults and a validating dataclass.
"""

import dataclasses

import pytest

from views_reporting.config import ReportingConfig, get_config

# ── defaults (green team) ────────────────────────────────────────────────


@pytest.mark.green_team
class TestDefaults:

    def test_seeded_hdi_levels(self):
        assert get_config().hdi_levels == (0.9, 0.95, 0.99)

    def test_default_level_is_ninety(self):
        assert get_config().default_hdi_level == 0.9

    def test_default_level_is_a_member(self):
        cfg = get_config()
        assert cfg.default_hdi_level in cfg.hdi_levels


# ── immutability (red team) ──────────────────────────────────────────────


@pytest.mark.red_team
class TestImmutable:

    def test_frozen_assignment_raises(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            get_config().default_hdi_level = 0.5  # type: ignore[misc]


# ── fail-loud validation (red team) ──────────────────────────────────────


@pytest.mark.red_team
class TestValidation:

    def test_empty_levels_rejected(self):
        with pytest.raises(ValueError):
            ReportingConfig(hdi_levels=(), default_hdi_level=0.9)

    @pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
    def test_level_outside_unit_interval_rejected(self, bad):
        with pytest.raises(ValueError):
            ReportingConfig(hdi_levels=(bad,), default_hdi_level=bad)

    def test_default_not_in_levels_rejected(self):
        with pytest.raises(ValueError):
            ReportingConfig(hdi_levels=(0.9, 0.95), default_hdi_level=0.99)


# ── canonical report metrics (green team) ────────────────────────────────


@pytest.mark.green_team
class TestCanonicalReportMetrics:

    def test_all_four_cells_present(self):
        cfg = get_config()
        assert set(cfg.canonical_report_metrics) == {
            ("regression", "point"),
            ("regression", "sample"),
            ("classification", "point"),
            ("classification", "sample"),
        }

    def test_accessor_returns_tuple_for_cell(self):
        cfg = get_config()
        assert cfg.canonical_metrics("regression", "sample") == (
            "CRPS", "MIS", "Ignorance", "MCR_sample", "y_hat_bar",
        )
        assert cfg.canonical_metrics("classification", "point") == ("AP", "Brier_cls_point")
        assert cfg.canonical_metrics("nope", "nope") == ()

    def test_each_cell_has_nonempty_metric_names(self):
        for metrics in get_config().canonical_report_metrics.values():
            assert metrics and all(isinstance(m, str) and m for m in metrics)


# ── canonical report metrics (red team) ──────────────────────────────────


@pytest.mark.red_team
class TestCanonicalReportMetricsValidation:

    def test_missing_cell_rejected(self):
        with pytest.raises(ValueError):
            ReportingConfig(
                canonical_report_metrics={
                    ("regression", "point"): ("MSLE",),
                    ("regression", "sample"): ("CRPS",),
                    ("classification", "point"): ("Brier_cls",),
                    # classification/sample missing
                }
            )

    def test_empty_metric_list_rejected(self):
        with pytest.raises(ValueError):
            ReportingConfig(
                canonical_report_metrics={
                    ("regression", "point"): (),
                    ("regression", "sample"): ("CRPS",),
                    ("classification", "point"): ("Brier_cls",),
                    ("classification", "sample"): ("Brier_cls_sample",),
                }
            )
