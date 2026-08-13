
# Class Intent Contract: PosteriorDistributionAnalyzer

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-06-24  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts), ADR-008/009 (explicit failure / no silent semantic defaults), ADR-019 (render point/interval use the views-frames tower)  

---

## 1. Purpose

> **What is this class for?**

PosteriorDistributionAnalyzer computes a summary of a 1D posterior sample array and renders
it for inspection: a point estimate, a set of nested Highest Density Intervals (HDIs) at
requested credible masses, a bimodality flag, and basic statistics (min, max, mass-at-zero).
It provides a computation path (`analyze()` → result dict) and an interactive path
(`print_summary()`, `plot_summary()`, `summary_dict()`) that reads stored state.

**Delegation (the tower, ADR-019).** The point/interval math is **not** hand-rolled here.
`_compute_summary()` wraps the (validated, finite) samples in a 1-row ephemeral
`views_frames.PredictionFrame` and calls **`views_frames_summarize.summarize_tower`** once,
reading out:
- **point** — the tower **tip** (median of the tower's top floor — tip_mass 0.25 since views-frames 1.9.0, their ADR-019 Amendment 3; formerly the 0.5-mass "shorth" floor): mode-bias-free and
  robust to minority duplicated draws. Reported under the dict key `'map'` for result-shape
  stability, but it is **not** a histogram-mode MAP (see register C-185).
- **hdis** — the **constrained-nested** HDIs (`hdi_tower`): each wider interval contains the
  narrower ones, and the tip lies inside the narrowest floor, **by construction**.
- **bimodal** — a conservative 0/1 flag for a clearly separated second mode.

The reporting-owned presentation is retained: `mass_at_zero` (the tower does not expose it),
the NaN/inf filter + all-NaN guard, the result-dict assembly, and the text/plot renderers.

Source: `views_reporting/statistics/statistics.py`.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** perform MCMC sampling or model training — it analyzes pre-existing samples.
- Does **not** handle multi-dimensional posteriors — 1D sample arrays only.
- Does **not** persist results to disk (`plot_summary(save_path=...)` saves a figure, not the analysis).
- Does **not** estimate a histogram-mode MAP or a kernel-density estimate — the point estimate
  is the tower tip; there is no `bins` parameter.
- Does **not** provide dataset-level batch analysis. For batch point/HDI over dataset slices,
  see the module-level helpers `compute_single_map()` / `calculate_single_hdi()` in
  `views_reporting/statistics/dataset_statistics.py`, which call the tower directly (they do
  **not** instantiate this class).

---

## 3. Responsibilities and Guarantees

- **Input validation:** `analyze()` validates via `_validate_samples` (drops NaN/inf; raises
  `ValueError` if none remain) and `_validate_credible_masses` (each in `(0, 1)`; sorted
  ascending). There are no `bins`/`zero_mass_threshold` parameters (removed in the tower
  migration; ADR-008/009 forbids silent no-op parameters).
- **Point + interval estimation:** delegated to `views_frames_summarize.summarize_tower`
  (one pass): the tip point and the constrained-nested HDIs at the requested masses.
- **Structural guarantees come from the tower, not post-processing:** HDIs nest and the tip
  lies inside the narrowest floor **by construction** — there is no `_enforce_hdi_structure`
  step (removed; it only existed to patch the non-nesting frozen `hdi`).
- **Mass pinning:** each requested credible mass is pinned to the tower's fixed canonical mass
  grid; the pinned values are returned as `'pinned_masses'`. The defaults `(0.5, 0.95, 0.99)`
  pin losslessly.
- **Computation purity (C-01):** `_compute_summary()` reads only its parameters, never
  `self.*`. Instance state (`self.samples`, `self.credible_masses`, `self.summary`) is written
  **after** `_compute_summary()` returns; `self.summary` is written last.
- **Result structure:** `analyze()` returns a dict with keys `'map'` (float, tower tip),
  `'min'` (float), `'max'` (float), `'mass_at_zero'` (float), `'hdis'` (list of (lower, upper),
  one per requested mass, nested), `'bimodal'` (bool), `'pinned_masses'` (tuple of floats).
  `len(hdis) == len(pinned_masses) == len(credible_masses)`.

---

## 4. Inputs and Assumptions

- `samples`: 1D array-like of floats. NaN/inf are filtered; all-invalid raises `ValueError`.
- `credible_masses`: tuple of floats, each strictly in `(0, 1)`; sorted ascending; pinned to
  the canonical grid (see `'pinned_masses'`).
- Univariate posterior assumed; no distributional assumptions beyond finiteness.

---

## 5. Outputs and Side Effects

**Outputs:**
- `analyze()` returns the summary dict (section 3).
- `summary_dict()` returns the stored dict, or `None` if `analyze()` was not called.
- `print_summary()` writes formatted text (point/tip, min, max, mass-at-zero, bimodality flag
  with its caveat, and one nested-HDI line per pinned mass) to a `TextIO` stream.
- `plot_summary()` creates and **returns** a matplotlib figure (histogram + tip line + shaded
  nested-HDI bands; title annotated when bimodal).

**Side effects:**
- `analyze()` writes `self.samples`, `self.credible_masses`, `self.summary` (last).
- `plot_summary()` calls `plt.show()` when `show=True` (blocks in non-interactive backends),
  and optionally `fig.savefig(save_path)`.
- Logging at DEBUG/INFO/WARNING/ERROR via the module logger.

---

## 6. Failure Modes and Loudness

- **All samples invalid:** `_validate_samples()` raises `ValueError("No valid samples provided.")`.
- **Invalid credible masses:** `_validate_credible_masses()` raises `ValueError` if any mass ∉ (0, 1).
- **Tiny samples (e.g. N=1, N=2):** handled by the tower (a degenerate floor collapses to a
  point); `analyze()` returns a well-formed dict (HDIs may be degenerate, `low == high`). No
  manual degenerate-HDI branch remains.
- **Off-grid mass:** silently pinned to the nearest canonical floor (the pinned value is
  surfaced in `'pinned_masses'`). The dataset-level helpers additionally log an off-grid
  warning; the class path relies on `'pinned_masses'` for transparency.
- **No summary before interactive use:** `print_summary()` / `plot_summary()` check
  `self.summary is None` and return early with a warning, never crashing.

---

## 7. Boundaries and Interactions

- **Depends on:** `numpy`, `matplotlib.pyplot`, `logging`, and `views_frames` /
  `views_frames_summarize` (`summarize_tower`, via an ephemeral `PredictionFrame`).
- **Depended on by:** only the test suite and the public re-export
  `views_reporting.statistics.PosteriorDistributionAnalyzer`. It is **not** on the forecast
  render path. (Historically the `dataset_statistics` helpers and `PlotDistribution`
  instantiated it; since the views-frames adoption they call the tower / dataset helpers
  directly and no longer depend on this class.)
- **No dependency on:** dataset handlers, Polars/Pandas, PyTorch, or pipeline-core components.

---

## 8. Examples of Correct Usage

**Computation path (stateless, thread-safe):**
```python
import numpy as np
from views_reporting.statistics.statistics import PosteriorDistributionAnalyzer

samples = np.random.normal(5, 2, 10000)
analyzer = PosteriorDistributionAnalyzer()
result = analyzer.analyze(samples, credible_masses=(0.5, 0.95, 0.99))
print(f"point (tip): {result['map']:.2f}")
print(f"95% HDI: [{result['hdis'][1][0]:.2f}, {result['hdis'][1][1]:.2f}]")
print(f"bimodal: {result['bimodal']}, pinned: {result['pinned_masses']}")
```

**Interactive path (single-threaded only):**
```python
analyzer = PosteriorDistributionAnalyzer()
analyzer.analyze(samples, credible_masses=(0.5, 0.95))
analyzer.print_summary()
fig = analyzer.plot_summary(save_path="posterior.png", show=False)
summary = analyzer.summary_dict()
```

---

## 9. Examples of Incorrect Usage

**Sharing an instance across threads for interactive state:**
```python
# WRONG: self.summary / self.samples are not thread-safe for interactive reads.
shared = PosteriorDistributionAnalyzer()
# Thread A: shared.analyze(samples_a); shared.print_summary()
# Thread B: shared.analyze(samples_b); shared.print_summary()
```

**Calling interactive methods before analyze():**
```python
analyzer = PosteriorDistributionAnalyzer()
analyzer.print_summary()  # prints "No summary available" — no-op, does not crash
fig = analyzer.plot_summary()  # returns None
```

**Passing a removed parameter:**
```python
analyzer.analyze(samples, bins=50)  # TypeError — `bins`/`zero_mass_threshold` no longer exist
```

---

## 10. Test Alignment

**Existing pytest tests:**
- `tests/test_statistics.py` — `TestPDADistributions` (point∈all-HDIs + nesting over 12
  distributions), `TestPDATowerOutputs` (result keys incl. `bimodal`/`pinned_masses`,
  bimodality both directions, tip∈narrowest, determinism), `TestPDAValidation`
  (credible-mass + all-NaN guards), `TestFrameMapHdiSparseGrid` (frame-native
  MAP/HDI sparse-grid reassembly).
- `tests/test_statistics_presentation.py` (#260) — the presentation contract:
  `print_summary` before-`analyze` guard, current labels, values/HDI lines match the
  summary dict, call-time stdout resolution (redirect respected); `plot_summary`
  before-`analyze` guard, Figure structure (point line at the tip; one legend
  "% HDI" label per pinned mass), show semantics, bimodal title caveat, REAL
  `save_path` PNG write.
- `tests/test_c01_thread_safety.py` / `tests/test_c01_layer1_specification.py` — thread
  safety + `_compute_summary` parameter purity (the obsolete `bins`-purity test was
  repurposed to `credible_masses`).

**Invariants tests must enforce:**
- The point lies within all HDIs; HDIs are properly nested (both now hold by construction).
- `_compute_summary()` results depend only on its parameters, not prior `self.*` state.
- The result dict carries `bimodal` (bool) and `pinned_masses`.

---

## 11. Evolution Notes

**Stable:** the `analyze()` → result-dict pattern; the stateless computation / interactive
read split (C-01).

### Known Deviations — all resolved
1. ~~`plot_summary()` has a commented-out `return fig`~~ — **RESOLVED.** `plot_summary()`
   returns the Figure.
2. ~~`_enforce_hdi_structure()` post-processes HDIs for nesting/MAP-inclusion~~ — **REMOVED.**
   The tower nests and contains the tip by construction (ADR-019); no post-processing exists.
3. ~~`bins` / `zero_mass_threshold` parameters drive a histogram-mode MAP~~ — **REMOVED.**
   The tower has no such knobs (ADR-008/009).

### Open debt
- `'map'` is a misnomer — it now carries the tower tip (a shorth), not a MAP. The key is kept
  for result-shape stability; a coordinated rename is tracked as register **C-185**.

---

## End of Contract

This document defines the **intended meaning** of `PosteriorDistributionAnalyzer`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
