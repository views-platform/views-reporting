"""The forecast template's Compose-boundary render strategy (#232, epic #230).

PGM renders HORIZON STEPS (+1/+6/+12/+24/+36, clamped to the horizon): one
scale-flat PNG per step plus a hover-capable raster heatmap at step +1, each
call carrying exactly ONE month — the renderer never picks a month itself.
CM keeps the whole-horizon choropleth. Budgets (max_cells,
max_raster_cell_frames) stay injected so the render-side guards remain armed.

CI-runnable: MappingModule + frames are mocked — the tests isolate the
Compose-boundary decisions in `ForecastReportTemplate._create_report`.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_reporting.config import get_config
    from views_reporting.templates.reports.forecast import (
        HORIZON_STEPS,
        ForecastReportTemplate,
    )
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

_FIRST_MONTH = 559  # Jul 2026


def _run_template(level: str, n_months: int) -> tuple[list, list]:
    """Run the template with rendering mocked; return (plot_map_calls,
    headings). Each plot_map call's `mapping_dataframe` is a marker dict
    carrying the `time_ids` the subset was requested with."""
    calls: list = []
    headings: list = []

    mm = MagicMock()
    mm.get_subset_mapping_dataframe.side_effect = (
        lambda entity_ids=None, time_ids=None: {"time_ids": time_ids}
    )
    mm.plot_map.side_effect = lambda **kw: calls.append(kw) or "<div>map</div>"

    rm = MagicMock()
    rm.add_heading.side_effect = lambda text, level=1: headings.append(text)

    fake_frame = MagicMock()
    fake_frame.is_sample = False  # point forecast → no MAP collapse
    fake_frame.index.time = np.arange(
        _FIRST_MONTH, _FIRST_MONTH + n_months, dtype=np.int64
    )

    config = {"name": "m", "level": level, "targets": ["ged_sb"]}
    model_path = MagicMock()
    model_path.target = "model"
    model_path.model_name = "m"

    fc = "views_reporting.templates.reports.forecast"
    with patch(f"{fc}.MappingModule", return_value=mm), patch(
        f"{fc}.frames_from_dataframe", return_value={"ged_sb": fake_frame}
    ), patch(f"{fc}.ReportModule", return_value=rm), patch(
        f"{fc}.HistoricalLineGraph", return_value=MagicMock()
    ), patch(f"{fc}.generate_model_file_name", return_value="m_fixture"):
        template = ForecastReportTemplate(
            config=config, model_path=model_path, run_type="calibration"
        )
        template.generate(forecast_dataframe=pd.DataFrame({"a": [1]}))
    return calls, headings


@pytest.mark.green_team
def test_pgm_full_horizon_renders_all_steps_plus_heatmap():
    """36 months → 5 step PNGs (+1/+6/+12/+24/+36) + 1 heatmap at +1 = 6
    renders, each carrying exactly one month, at the right month."""
    calls, _ = _run_template("pgm", n_months=36)
    assert len(calls) == len(HORIZON_STEPS) + 1

    rasters = [kw for kw in calls if kw.get("raster")]
    pngs = [kw for kw in calls if kw.get("image_fallback")]
    assert len(rasters) == 1 and len(pngs) == len(HORIZON_STEPS)

    # heatmap is at step +1 (the first forecast month), single-month subset
    assert rasters[0]["mapping_dataframe"]["time_ids"] == [_FIRST_MONTH]
    assert rasters[0]["max_raster_cell_frames"] == (
        get_config().max_raster_cell_frames
    )

    # each PNG carries its step's month: months[s-1]
    png_months = [kw["mapping_dataframe"]["time_ids"] for kw in pngs]
    assert png_months == [[_FIRST_MONTH + s - 1] for s in HORIZON_STEPS]
    # every call is single-month — no renderer-side month picking possible
    assert all(len(kw["mapping_dataframe"]["time_ids"]) == 1 for kw in calls)


@pytest.mark.green_team
def test_pgm_short_horizon_clamps_steps():
    """A 3-month horizon has only step +1 (no +6 and beyond): 1 PNG + 1
    heatmap, both at the first month."""
    calls, _ = _run_template("pgm", n_months=3)
    assert len(calls) == 2
    assert all(
        kw["mapping_dataframe"]["time_ids"] == [_FIRST_MONTH] for kw in calls
    )
    assert sorted(bool(kw.get("raster")) for kw in calls) == [False, True]


@pytest.mark.green_team
def test_pgm_headings_carry_date_and_step():
    """Step headings are human-datable: month label + step offset (#232)."""
    _, headings = _run_template("pgm", n_months=36)
    step_headings = [h for h in headings if "step +" in h]
    assert len(step_headings) == len(HORIZON_STEPS)
    assert "Jul 2026 (step +1)" in step_headings[0]   # month 559
    assert "Jun 2029 (step +36)" in step_headings[-1]  # month 594


@pytest.mark.green_team
def test_cm_keeps_single_whole_horizon_choropleth():
    """CM is not a lattice: one whole-horizon choropleth, never raster/PNG,
    and the choropleth guard stays injected."""
    calls, _ = _run_template("cm", n_months=36)
    assert len(calls) == 1
    kw = calls[0]
    assert not kw.get("raster") and not kw.get("image_fallback")
    assert kw["max_cells"] == get_config().max_map_cells
    assert kw["mapping_dataframe"]["time_ids"] is None  # whole horizon


@pytest.mark.green_team
def test_pgm_step_render_is_announced(caplog):
    """The horizon-step strategy is visible in logs (which steps, what
    horizon) — not a silent layout decision."""
    import logging

    with caplog.at_level(
        logging.INFO, logger="views_reporting.templates.reports.forecast"
    ):
        _run_template("pgm", n_months=36)
    assert "horizon-step render" in caplog.text
