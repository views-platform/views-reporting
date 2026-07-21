"""Collapse-path memory bounds (C-212, #235).

The S=1000 global goal dies if a single collapse call multiplies the sample
array: the old path forced a float64 copy (2x), boolean-masked it again (2x),
then cast back to float32 for the tower (1x) — ~5x the source at peak, ~46 GB
for one global S=1000 target. The guard pins the collapse to a float32-
preserving path (~1-2x). Measured in a SUBPROCESS so the max-RSS high-water
mark belongs to this workload alone, not to whatever ran earlier in the test
process.
"""

import subprocess
import sys
import textwrap

import pytest

_PROBE = textwrap.dedent(
    """
    import numpy as np, resource
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex
    from views_reporting.statistics import calculate_map_frame

    n_cells, n_months, s = 40_000, 3, 500
    n = n_cells * n_months
    rng = np.random.default_rng(0)
    # float32-native generation: the probe's own transients must not pollute
    # the baseline watermark
    vals = rng.standard_normal((n, s), dtype=np.float32)
    np.exp(vals, out=vals)
    mask = rng.random((n, s), dtype=np.float32) < 0.6
    vals[mask] = 0.0
    del mask
    idx = SpatioTemporalIndex(
        time=np.repeat(np.arange(540, 540 + n_months, dtype=np.int64), n_cells),
        unit=np.tile(np.arange(n_cells, dtype=np.int64) + 62356, n_months),
        level=SpatialLevel.PGM,
    )
    frame = PredictionFrame(vals, idx)
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux
    calculate_map_frame(frame, "pred_x")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print((peak - base) * 1024 / vals.nbytes)
    """
)


@pytest.mark.slow
@pytest.mark.red_team
def test_collapse_peak_memory_is_float32_bounded():
    """One collapse call must not multiply the sample array: peak growth
    beyond the resident source stays under 3.5x source bytes (float32-
    preserving path measures ~1-2x; the float64 detour measured ~5x)."""
    out = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, check=True
    )
    ratio = float(out.stdout.strip())
    assert ratio < 3.5, (
        f"collapse allocated {ratio:.1f}x the float32 source at peak — the "
        "float64 detour is back (C-212); at S=1000 global scale that is a "
        ">40 GB transient per target"
    )
