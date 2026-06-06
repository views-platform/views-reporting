"""Falsification stubs — claim: "the current setup produces full evaluation
reports like the Downloads artifact (ensemble calibration, with Prediction
Samples carrying the HDI legend selector)."

Audit verdict: FALSIFIED on provenance (the artifact is pre-#84/#88/#90 output);
capability survives. The one *code* finding worth enforcing is P4 below.

These are STUBS (xfail) describing the gap, not wired integration tests — the
ensemble path needs a ModelPathManager + on-disk raw data to drive end to end.
Remove the xfail and flesh out once the desired behaviour is decided.
"""

import pytest


@pytest.mark.red_team
@pytest.mark.xfail(
    reason="P4: ensemble eval with no config['models'] (or missing raw data) "
    "silently omits the Prediction Samples section — only a logged warning. The "
    "HDI-bearing graphs vanish from the report with no in-report signal. Decide: "
    "fail loud, or render a visible 'samples unavailable' note.",
    strict=False,
)
def test_ensemble_eval_missing_models_surfaces_skipped_samples():
    """When an ensemble EvaluationReportTemplate cannot build the prediction
    sample graphs (empty `config['models']` or no raw data), the report should
    make the omission VISIBLE (heading + note), not drop the section with only a
    `logger.warning`. Currently `_add_prediction_sample_graphs` returns early
    (evaluation.py ~348-360), so a reviewer cannot tell the HDI graphs are
    missing by reading the HTML."""
    raise NotImplementedError(
        "Wire EvaluationReportTemplate(target='ensemble', config without 'models') "
        "-> _add_prediction_sample_graphs -> assert a visible 'samples unavailable' "
        "note is added to the report (not just a log line)."
    )


@pytest.mark.green_team
def test_current_code_renders_multilevel_hdi_not_legacy_naming():
    """Provenance guard (P1/P2): current rendering emits the multi-level legend
    ('90% HDI' …) and never the legacy single-band 'HDI Lower (...)' naming.

    This already passes (locks current behaviour) — it exists so that any future
    report exhibiting 'HDI Lower' / no '% HDI' is flagged as STALE output, which
    is exactly how the Downloads artifact was identified as pre-#88/#90 code.
    Full coverage lives in TestHdiLevelSelector / TestHdiLevelLabel; this is a
    one-line provenance smoke check.
    """
    import numpy as np
    import pandas as pd

    try:
        from views_pipeline_core.data.handlers import CMDataset
    except ImportError:
        pytest.skip("views_pipeline_core not installed")

    from views_reporting.visualizations import HistoricalLineGraph

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
