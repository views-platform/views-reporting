"""The forecast template auto-selects the bounded raster for an oversized PGM grid
(restoring large-PGM maps — C-26 / #125 / register C-204) instead of failing the
choropleth guard, and leaves small PGM on the detailed choropleth.

CI-runnable: MappingModule + frame building are mocked, so no fixtures, no 56 MB
shapefile, no VIEWSER fetch — the test isolates the Compose-boundary decision in
`ForecastReportTemplate._create_report` (forecast.py).
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

try:
    from views_reporting.config import get_config
    from views_reporting.templates.reports.forecast import ForecastReportTemplate
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)


def _captured_plot_map_kwargs(level: str, n_cells: int) -> dict:
    """Run the forecast template with MappingModule/frames/report mocked; return the
    kwargs `plot_map` was called with for a `level` grid of `n_cells` cell-frames."""
    captured: dict = {}
    fake_subset = pd.DataFrame({"v": range(n_cells)})  # len() == n_cells

    mm = MagicMock()
    mm.get_subset_mapping_dataframe.return_value = fake_subset
    mm.plot_map.side_effect = lambda **kw: captured.update(kw) or "<div>map</div>"

    fake_frame = MagicMock()
    fake_frame.is_sample = False  # point forecast → no MAP collapse, no line graph

    config = {"name": "m", "level": level, "targets": ["ged_sb"]}
    model_path = MagicMock()
    model_path.target = "model"
    model_path.model_name = "m"

    fc = "views_reporting.templates.reports.forecast"
    with patch(f"{fc}.MappingModule", return_value=mm), patch(
        f"{fc}.frames_from_dataframe", return_value={"ged_sb": fake_frame}
    ), patch(f"{fc}.ReportModule", return_value=MagicMock()), patch(
        f"{fc}.HistoricalLineGraph", return_value=MagicMock()
    ), patch(f"{fc}.generate_model_file_name", return_value="m_fixture"):
        template = ForecastReportTemplate(
            config=config, model_path=model_path, run_type="calibration"
        )
        template.generate(forecast_dataframe=pd.DataFrame({"a": [1]}))
    return captured


@pytest.mark.green_team
def test_oversized_pgm_selects_raster():
    """A PGM grid above the choropleth cell guard renders as the bounded raster
    (raster=True + the frame-aware budget injected) instead of raising."""
    n = get_config().max_map_cells + 1
    kw = _captured_plot_map_kwargs("pgm", n)
    assert kw["raster"] is True
    assert kw["max_raster_cell_frames"] == get_config().max_raster_cell_frames
    # the choropleth guard is still injected (backstop for the non-raster path)
    assert kw["max_cells"] == get_config().max_map_cells


@pytest.mark.green_team
def test_small_pgm_keeps_choropleth():
    """A small PGM grid (≤ guard) stays on the detailed vector choropleth."""
    kw = _captured_plot_map_kwargs("pgm", 100)
    assert kw["raster"] is False


@pytest.mark.green_team
def test_cm_never_rasters():
    """CM is not a lattice — it never selects raster, regardless of size."""
    kw = _captured_plot_map_kwargs("cm", get_config().max_map_cells + 1)
    assert kw["raster"] is False
