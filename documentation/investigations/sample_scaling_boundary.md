# Investigation Determination: the render-path sample-scaling boundary

**Epic:** #215 · **Story:** S1 (#216) · **Date:** 2026-07-06 · **Machine:** 31 GB RAM, Linux
**Claim under test:** *posterior samples are numpy-bound; the pandas presentation seam receives
only S==1 summaries; therefore 1000s of samples cannot blow up the render path.*

## 1. Verdict

**PENDING — pre-registration below was written and committed to before any measurement ran.**
(Filled in §§3–7 after the runs; this header updated last.)

## 2. Pre-registered predictions (written BEFORE measurement)

Following the repo's falsification convention: each prediction is risky (it can fail), and the
scoring rule is stated up front. Measurements that contradict a prediction FALSIFY it — no
post-hoc rescue.

| ID | Prediction | Scoring rule |
|----|-----------|--------------|
| **P1** | `PredictionFrame` memory is exactly `N × S × 4` bytes (float32 contract) | `frame.values.nbytes == N*S*4` at every grid point |
| **P2** | The seam DataFrame (`frames_to_mapping_df` output) is **O(rows) and S-independent**: for fixed N, its deep memory at S=1 vs S=2000 differs by < 1% | `df.memory_usage(deep=True).sum()` compared across S for fixed N |
| **P3** | `calculate_map_frame` wall-time grows **~linearly in N×S** (tower = per-row density work): doubling N×S changes wall-time by 2× ± 50% | log-log slope of wall-time vs N×S in [0.7, 1.3] |
| **P4** | Report-artifact HTML size is **S-independent** (C-38: driven by entities × HDI-levels × time): line-graph HTML at S=100 vs S=1000 differs by < 5% for fixed entities/levels/time | `len(html)` compared across S |
| **P5** | An **uncollapsed** S>1 frame passed directly to `frames_to_mapping_df` yields a value column equal to **draw #0** (`values[:, 0]`), differing from the tower MAP, with **no error and no warning** — the silent crossing | column equality vs `values[:,0]`; inequality vs `calculate_map_frame` output; captured warnings == 0 |
| **P6** | The historical all-HDI-failed fallback renders **draw #0** labeled "(HDI unavailable)" (`historical.py:298-307`) | trace y-values equal `values[:,0]` for the entity |
| **P7** | The DataFrame-loader ingest path transiently holds **all S samples inside pandas** (array-in-cell object dtype): ingest-df deep memory ≈ N×S×4 + object overhead, i.e. ≥ the frame it produces | `df.memory_usage(deep=True)` vs stacked frame nbytes |

## 3. Measurement grid (cap N×S ≤ ~5e8 f32; globe extrapolated, not maxed)

| Config | N (rows) | S | Expected frame size |
|---|---|---|---|
| CM: 190 countries × 36 months | 6,840 | 100 / 1,000 / 2,000 | 2.7 / 27 / 55 MB |
| PGM-Africa: 13,110 cells × 36 months | 471,960 | 100 / 1,000 | 189 MB / 1.9 GB |
| PGM-globe: 259,200 cells × 12 months | 3,110,400 | 100 / 200 | 1.2 / 2.5 GB (S=1000 ⇒ 12.4 GB **extrapolated, stated not run**) |

Additional measurements: eval-template line-graph path (HDI 3 levels + MAP tower wall-time at
N×S — the surface where S=1000 frames flow in production, `evaluation.py:555-568`); seam df
row-count identity (rows == N, never N×S).

*(§§4–7: results tables, per prediction. §8: implications. §9: method. §10: execution log.
Filled after the runs.)*
