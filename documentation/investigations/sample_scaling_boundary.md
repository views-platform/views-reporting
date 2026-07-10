# Investigation Determination: the render-path sample-scaling boundary

**Epic:** #215 · **Story:** S1 (#216) · **Date:** 2026-07-06 · **Machine:** 31 GB RAM, Linux
**Claim under test:** *posterior samples are numpy-bound; the pandas presentation seam receives
only S==1 summaries; therefore 1000s of samples cannot blow up the render path.*

## 1. Verdict

**SURVIVED, with one discovered constraint and one demonstrated hole. All 7 pre-registered
predictions CONFIRMED (7/7).** The pandas presentation seam is exactly O(rows) and
byte-identical across sample counts — 1000s of samples cannot blow it up, because samples
never legitimately reach it. The **real** globe×samples constraint is MAP-collapse wall-time
(numpy tower, ~2×10⁶ sample-elements/s: PGM-Africa × S=1000 = 237 s; extrapolated globe ×
S=1000 ≈ 26 min + a 12.4 GB frame). The **hole**: an uncollapsed frame crosses the seam
silently rendering **posterior draw #0** as the point estimate (confirmed at every grid point,
zero warnings), and the historical all-HDI-failed fallback **does this in production today**
(demonstrated). Registered as **C-207**; enforcement is story S2 (#217).

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

## 4. Results — memory laws (P1, P2, P7) — **all CONFIRMED** (W1)

| Config | N | S | Frame nbytes (=N×S×4?) | Seam df rows | Seam df deep memory |
|---|---|---|---|---|---|
| CM 190×36 | 6,840 | 100 | 2,736,000 ✓ | 6,840 | 1,015,272 |
| CM 190×36 | 6,840 | 1,000 | 27,360,000 ✓ | 6,840 | **1,015,272 (identical)** |
| CM 190×36 | 6,840 | 2,000 | 54,720,000 ✓ | 6,840 | **1,015,272 (identical)** |
| PGM-Africa 13,110×36 | 471,960 | 100 | 188,784,000 ✓ | 471,960 | 70,866,144 |
| PGM-Africa 13,110×36 | 471,960 | 1,000 | 1,887,840,000 ✓ | 471,960 | **70,866,144 (identical)** |
| PGM-globe 259,200×12 | 3,110,400 | 100 | 1,244,160,000 ✓ | 3,110,400 | 471,447,540 |
| PGM-globe 259,200×12 | 3,110,400 | 200 | 2,488,320,000 ✓ | 3,110,400 | **471,447,540 (identical)** |

- **P1 CONFIRMED**: frame nbytes = N×S×4 exactly at all 7 grid points (float32 contract holds).
- **P2 CONFIRMED**: seam df memory is **byte-identical across S** for fixed N — the seam is
  O(rows), sample-independent. A 69× larger posterior (S=2000 vs 29) changes the pandas seam
  by **zero bytes**.
- **P7 CONFIRMED**: the DataFrame-loader ingest df deep memory (28,208,484 B at CM×S=1000) ≥
  the stacked frame (27,360,000 B) — pandas **does** transiently hold every sample at ingest
  (array-in-cell object dtype; tracemalloc peak 158 MB ≈ several transient copies). The
  npy `PredictionFrameLoader` path never does. Any ADR claim must scope to the render seam.

## 5. Results — wall-time law (P3) — **CONFIRMED; the discovered real constraint** (W2)

| Config | N×S | `calculate_map_frame` wall-time | rate (elements/s) |
|---|---|---|---|
| CM × 100 | 6.84e5 | 0.39 s | 1.8e6 |
| CM × 1000 | 6.84e6 | 4.83 s | 1.4e6 |
| CM × 2000 | 1.37e7 | 9.74 s | 1.4e6 |
| PGM-Africa × 100 | 4.72e7 | 26.5 s | 1.8e6 |
| PGM-Africa × 1000 | 4.72e8 | **237.0 s** | 2.0e6 |
| PGM-globe × 100 | 3.11e8 | 74.0 s | 4.2e6 |
| PGM-globe × 200 | 6.22e8 | 187.3 s | 3.3e6 |

Log-log slope ≈ 1 (within the pre-registered [0.7, 1.3]) — **linear in N×S**, ~2–4×10⁶
sample-elements/s on this machine. **Extrapolated globe × S=1000: ≈ 15–26 minutes of MAP
collapse + a 12.4 GB frame** (stated, not run — pre-registered cap). The binding constraint
for globe-scale sampled forecasts is **tower wall-time in numpy, not pandas memory** — a
first-class finding for ADR-020 and a future-work note (chunked/parallel collapse), NOT a
pandas problem.

## 6. Results — artifact size (P4) — **CONFIRMED** (W3)

Line-graph HTML (20 entities × 36 months × 3 HDI levels): S=100 → 5,095,276 B;
S=1000 → 5,095,841 B (**ratio 1.0001**). Artifact size is driven by entities × levels × time
(the C-38 mechanism), independent of S — bands are summaries.

## 7. Results — the silent draw-#0 crossing (P5, P6) — **CONFIRMED at every point** (W4)

- **P5**: at all 7 grid points, an **uncollapsed** S>1 frame passed to `frames_to_mapping_df`
  produced a value column equal to `values[:, 0]` (draw #0), **unequal to the tower MAP**, with
  **zero warnings**. The seam ignores `sample_count` entirely.
- **P6**: with all HDI levels failing, the rendered fallback trace
  `"Country 1 (HDI unavailable) (Forecast)"` had y-values **exactly equal to draw #0** — the
  bug is live in production code (`historical.py:298-307`), not hypothetical.
- Registered as **C-207** (silent-wrong-artifact class). The sanctioned template path cannot
  hit the mapping-seam variant (`is_sample` ≡ `sample_count>1` forces collapse), but direct
  callers can — including via pipeline-core's `modules/mapping/__init__.py` re-export shim —
  and the historical fallback variant fires on the sanctioned path whenever HDI fails.

## 8. Implications for the decision (checkpoint on epic #215)

1. **The "1000s of samples" worry is answered**: samples scale the numpy side (linearly, in
   both bytes and collapse time) and **cannot** scale the pandas side — the seam is provably
   S-independent. Summary-shaped pandas in the Render layer carries no sample-scaling risk.
2. **The genuine risks are elsewhere**: (a) the silent draw-#0 crossing (C-207 — enforce S==1
   at the seam, fix the fallback); (b) globe×S collapse wall-time (~26 min — a compute-budget
   question for the tower, orthogonal to pandas).
3. Seam-contract options for the checkpoint: **A** fail-loud raise on S>1 (recommended —
   matches ADR-008 and the CIC's documented expectation); **B** auto-collapse at the seam
   (hides compute, weakens ADR-019's explicit-collapse discipline); **C** docs-only (leaves
   C-207 open).

## 9. Method (throwaway spike — scripts NOT committed)

Two probe scripts in the session scratchpad (`probe_sample_scaling.py`,
`probe_html_fallback.py`), run via `uv run python` against `development` @ `19b962f` (the
pre-registration commit). Seeded `np.random.default_rng(0/1)`; zero-inflated lognormal
posteriors (tower-test precedent); metadata accessors patched with offline doubles (probe
purity — no shapefile/bundle reads in the timing paths); memory via `values.nbytes` /
`DataFrame.memory_usage(deep=True)` / `tracemalloc`; wall-time via `time.perf_counter`.
Machine: 31 GB RAM, Linux. `pyproject.toml`/`uv.lock` untouched; no production code touched.

## 10. Execution log

- 2026-07-06 — pre-registration committed (`19b962f`) BEFORE any measurement; grid + P4/P6
  probes run same day; 7/7 predictions CONFIRMED; C-207 registered (Open); "Decision
  requested" posted on epic #215. Next: checkpoint → S2 (#217).
