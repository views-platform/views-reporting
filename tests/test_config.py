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
