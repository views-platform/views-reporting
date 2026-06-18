"""Falsification follow-through.

The `/falsify` audit of "the current setup produces full evaluation reports like
the Downloads artifact" found (P4) that the Prediction-Samples section — home of
the HDI legend selector — was dropped *silently* for misconfigured ensembles, so
a partial report read as complete. C-40 fixes that: the omission is now made
VISIBLE. These tests enforce the fix and guard against the stale-output
signature (legacy `HDI Lower` naming) that flagged the artifact as pre-feature.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from views_reporting.reports import ReportModule
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
    from views_reporting.visualizations import HistoricalLineGraph
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

_PF_ORIGINS = (
    Path(__file__).parent / "data" / "red_ranger" / "predictions_calibration"
)


@pytest.mark.red_team
def test_ensemble_eval_missing_models_surfaces_skipped_samples(tmp_path):
    """C-40: an ensemble report whose config has no constituent ``models`` must
    add a VISIBLE 'Prediction samples unavailable' note, not drop the section
    with only a `logger.warning`."""
    # Discovery must succeed first (it precedes the ensemble-models check), so
    # this test needs the real rolling-origin fixture dirs, which are gitignored
    # (absent on CI / fresh clones). Skip rather than fail, per the repo's fixture
    # contract (see tests/data/README.md, test_e2e_fixture.py).
    if not _PF_ORIGINS.exists():
        pytest.skip(f"prediction fixtures absent: {_PF_ORIGINS}")

    model_path = MagicMock()
    model_path.target = "ensemble"
    # Point discovery at the real rolling-origin fixture dirs.
    model_path._get_generated_pf_prediction_paths.return_value = [_PF_ORIGINS]

    template = EvaluationReportTemplate(
        {"level": "cm", "prediction_format": "prediction_frame", "models": []},
        model_path,
        run_type="calibration",
    )
    report_manager = ReportModule()
    template._add_prediction_sample_graphs(report_manager, "lr_ged_sb")

    out = tmp_path / "report.html"
    report_manager.export_as_html(str(out))
    html = out.read_text()
    assert "Prediction Samples" in html
    assert "unavailable" in html.lower()
    assert "models" in html.lower()  # the stated reason


@pytest.mark.green_team
def test_current_code_renders_multilevel_hdi_not_legacy_naming():
    """Provenance guard (P1/P2): current rendering emits the multi-level legend
    ('90% HDI' …) and never the legacy single-band 'HDI Lower (...)' naming. Any
    future report exhibiting 'HDI Lower' / no '% HDI' is therefore STALE output,
    which is exactly how the Downloads artifact was identified as pre-#88/#90."""
    import numpy as np
    import pandas as pd

    try:
        from views_pipeline_core.data.handlers import CMDataset
    except ImportError:
        pytest.skip("views_pipeline_core not installed")

    np.random.seed(3)
    idx = pd.MultiIndex.from_tuples(
        [(528, 1), (529, 1), (530, 1)], names=["month_id", "country_id"]
    )
    df = pd.DataFrame(
        {"pred_ged_sb": [np.random.normal(5, 2, 50) for _ in range(3)]}, index=idx
    )
    html = HistoricalLineGraph(
        historical_dataset=None, forecast_dataset=CMDataset(source=df)
    ).plot_predictions_vs_historical(
        entity_ids=[1], interactive=True, as_html=True,
        alpha=0.9, hdi_levels=[0.9, 0.95, 0.99],
    )
    assert "90% HDI" in html and "95% HDI" in html  # current
    assert "HDI Lower" not in html  # legacy (stale-report signature)
