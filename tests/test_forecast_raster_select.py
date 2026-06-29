"""The forecast template picks the render-strategy tier at the Compose boundary
(epic globe-readiness): for PGM, choropleth → bounded raster heatmap → PNG image, by
size; CM always choropleth. Guards large-PGM maps (C-204) and the globe-scale fallback
(C-205) without OOM/over-budget.

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


class _Sized:
    """A stand-in for the subset mapping dataframe with a chosen ``len()`` — lets the
    extreme tier (n > 1,000,000) be tested without materializing a huge DataFrame."""

    def __init__(self, n: int):
        self._n = n

    def __len__(self) -> int:
        return self._n


def _captured_plot_map_kwargs(level: str, n_cells: int) -> dict:
    """Run the forecast template with MappingModule/frames/report mocked; return the
    kwargs `plot_map` was called with for a `level` grid of `n_cells` cell-frames."""
    captured: dict = {}
    fake_subset = _Sized(n_cells)  # len() == n_cells (cheap at any size)

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
    """Mid tier: a PGM grid above the choropleth cell guard but within the heatmap
    budget renders as the bounded raster heatmap (raster=True, no PNG) instead of
    raising."""
    n = get_config().max_map_cells + 1
    kw = _captured_plot_map_kwargs("pgm", n)
    assert kw["raster"] is True
    assert kw["image_fallback"] is False  # still hover-capable — not yet the PNG tier
    assert kw["max_raster_cell_frames"] == get_config().max_raster_cell_frames
    # the choropleth guard is still injected (backstop for the non-raster path)
    assert kw["max_cells"] == get_config().max_map_cells


@pytest.mark.green_team
def test_small_pgm_keeps_choropleth():
    """Low tier: a small PGM grid (≤ guard) stays on the detailed vector choropleth —
    neither raster nor PNG."""
    kw = _captured_plot_map_kwargs("pgm", 100)
    assert kw["raster"] is False
    assert kw["image_fallback"] is False


@pytest.mark.green_team
def test_extreme_pgm_selects_png_image():
    """Top tier: a PGM grid past the heatmap budget (globe × many origins) escalates to
    the scale-flat PNG image (image_fallback=True), and does NOT also set raster — the
    PNG path supersedes the heatmap (C-205)."""
    n = get_config().max_raster_cell_frames + 1
    kw = _captured_plot_map_kwargs("pgm", n)
    assert kw["image_fallback"] is True
    assert kw["raster"] is False


@pytest.mark.green_team
def test_cm_never_rasters():
    """CM is not a lattice — it never selects raster or PNG, regardless of size."""
    kw = _captured_plot_map_kwargs("cm", get_config().max_map_cells + 1)
    assert kw["raster"] is False
    assert kw["image_fallback"] is False


@pytest.mark.green_team
def test_cm_never_image_even_past_heatmap_budget():
    """CM stays on the choropleth even past the heatmap budget — the PNG lattice path is
    PGM-only (CM has no regular grid to rasterize)."""
    kw = _captured_plot_map_kwargs("cm", get_config().max_raster_cell_frames + 1)
    assert kw["image_fallback"] is False
    assert kw["raster"] is False
