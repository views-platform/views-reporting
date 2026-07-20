"""Sample-scaling canary (epic #215, S3 / #218) — pins the laws the probe measured.

The permanent CI subset of the S1 investigation
(documentation/investigations/sample_scaling_boundary.md): a seeded S=1000 frame
at CI-tractable dimension (a FIXED 13,110-cell subset of the real bundle × 3
months ≈ 157 MB float32) runs the sanctioned pipeline — tower collapse →
pandas seam → raster render — bounded and FAITHFUL (the rendered value is the
tower MAP, never posterior draw #0). The full grid sweeps, globe runs and
wall-time benchmarks stay in the investigation doc; only the law-verifying
cases live here (mirrors tests/test_global_scale.py).

Uses REAL bundled priogrid ids (metadata/data/priogrid.parquet) so the
metadata accessors run unmocked — no conftest doubles anywhere in this file.
The canary takes the first ``_N_CELLS`` sorted bundle ids (NOT the whole
bundle): the canary's dimensions are a pinned budget, decoupled from bundle
coverage, which went global in #231 (13,110 → 66k+ cells) and may grow again.
"""

import pathlib
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.loaders import frames_from_dataframe
    from views_reporting.mapping._frame_adapter import frames_to_mapping_df
    from views_reporting.mapping.mapping import MappingModule
    from views_reporting.statistics.dataset_statistics import calculate_map_frame
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

_REPO = pathlib.Path(__file__).resolve().parent.parent
_PG_BUNDLE = _REPO / "views_reporting" / "metadata" / "data" / "priogrid.parquet"

TARGET = "pred_ged_sb"
_N_TIMES = 3
_S = 1000
_N_CELLS = 13_110  # pinned canary dimension — deliberately NOT len(bundle)


def _bundle_sample_frame(s: int = _S, n_times: int = _N_TIMES) -> PredictionFrame:
    """A seeded S-sample frame over REAL bundled cell ids (fixed-size subset)."""
    gids = np.sort(
        pd.read_parquet(_PG_BUNDLE)["priogrid_id"].to_numpy(dtype=np.int64)
    )[:_N_CELLS]
    rng = np.random.default_rng(0)
    n = len(gids) * n_times
    idx = SpatioTemporalIndex(
        time=np.repeat(np.arange(540, 540 + n_times, dtype=np.int64), len(gids)),
        unit=np.tile(gids, n_times),
        level=SpatialLevel.PGM,
    )
    vals = rng.lognormal(0.0, 1.0, (n, s)).astype(np.float32)
    vals[rng.random((n, s)) < 0.6] = 0.0  # zero-inflated, the realistic shape
    return PredictionFrame(vals, idx)


@pytest.mark.slow
@pytest.mark.green_team
def test_s1000_collapse_seam_render_bounded_and_faithful():
    """The sanctioned pipeline at S=1000: (a) the seam df is O(rows) —
    exactly cells × months, S never multiplies it, memory within budget;
    (b) FAITHFUL — the value column is exactly the tower MAP, not draw #0;
    (c) the raster render stays within the byte budget (probe law P2/P5)."""
    frame = _bundle_sample_frame()
    n_rows = _N_CELLS * _N_TIMES

    map_df = calculate_map_frame(frame, TARGET)  # the tower collapse (numpy)
    tower_map = map_df.iloc[:, 0].to_numpy(dtype=np.float32)

    idx1 = SpatioTemporalIndex(
        time=map_df.index.get_level_values("month_id").to_numpy(dtype=np.int64),
        unit=map_df.index.get_level_values("priogrid_id").to_numpy(dtype=np.int64),
        level=SpatialLevel.PGM,
    )
    collapsed = PredictionFrame(tower_map.reshape(-1, 1), idx1)

    mdf = frames_to_mapping_df(collapsed, TARGET, SpatialLevel.PGM)  # REAL accessors

    # (a) O(rows), S-independent, bounded
    assert len(mdf) == n_rows
    assert mdf.memory_usage(deep=True).sum() < 20_000_000  # probe: ~150 B/row
    # (b) faithful: seam value == tower MAP (draw #0 would differ — probe P5)
    assert np.allclose(np.sort(mdf[TARGET].to_numpy()), np.sort(tower_map))
    draw0 = frame.values[:, 0]
    assert not np.allclose(np.sort(mdf[TARGET].to_numpy()), np.sort(draw0))

    # (c) the raster heatmap render is bounded (test_global_scale pattern:
    # synthetic lattice coords; the mocked shapefile keeps the test hermetic)
    lat = (mdf["priogrid_id"].to_numpy() % 360).astype(np.float32) * 0.5 - 89.75
    lon = (mdf["priogrid_id"].to_numpy() // 360 % 720).astype(np.float32) * 0.5 - 179.75
    mdf = mdf.assign(
        gid=mdf["priogrid_id"], xcoord=lon, ycoord=lat, row=0, col=0
    )
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "xcoord", "ycoord", "col", "row", "geometry"]
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=mock_gdf):
        module = MappingModule(
            frame=collapsed, level=SpatialLevel.PGM, target_column=TARGET
        )
        html = module.plot_map(
            mdf, TARGET, interactive=True, as_html=True, raster=True
        )
    # LATTICE cell-frames of the subset's bbox × 3 months at ~34 B/cf
    # (uniform lattice: ocean nulls included, C-208) — the pinned budget
    # holds for any 13,110-cell subset whose bbox stays under ~200k
    # lattice cell-frames (the global-lowest-gid band is well under)
    assert len(html) < 20_000_000


@pytest.mark.slow
@pytest.mark.red_team
def test_s1000_uncollapsed_frame_refused_at_seam():
    """The S2 guard at scale: the same S=1000 frame, passed UNCOLLAPSED, is
    refused loudly — the pre-guard behaviour (silently rendering draw #0)
    is impossible (C-207)."""
    frame = _bundle_sample_frame()
    with pytest.raises(ValueError, match="calculate_map_frame"):
        frames_to_mapping_df(frame, TARGET, SpatialLevel.PGM)


@pytest.mark.green_team
def test_ingest_array_in_cell_characterization():
    """The documented ADR-020 asterisk, pinned: the DataFrame loader transiently
    holds every sample inside pandas (array-in-cell object dtype) before
    stacking to the numpy frame — the ingest df's deep memory is at least the
    frame it produces (probe P7). Small S: this is a shape pin, not a budget."""
    import sys

    sys.path.insert(0, str(_REPO / "tests"))
    from conftest import build_cm_forecast_df

    s = 64
    df = build_cm_forecast_df(
        n_months=6, n_countries=10, n_samples=s, targets=["ged_sb"]
    )
    frames = frames_from_dataframe(df, "cm", ["ged_sb"])
    frame = frames["ged_sb"]
    assert frame.values.shape == (60, s)
    assert frame.values.dtype == np.float32
    assert df.memory_usage(deep=True).sum() >= frame.values.nbytes
