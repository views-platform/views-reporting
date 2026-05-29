
# Class Intent Contract: PosteriorDistributionAnalyzer

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts)  

---

## 1. Purpose

> **What is this class for?**

PosteriorDistributionAnalyzer computes empirical summary statistics from posterior samples: a Maximum A Posteriori (MAP) estimate via histogram density peak detection, Highest Density Intervals (HDI) via the shortest-interval method on sorted samples, and basic statistics (min, max, mass-at-zero). It provides both a computation path (`analyze()`) that returns a result dictionary and an interactive path (`print_summary()`, `plot_summary()`, `summary_dict()`) that reads from stored state.

Source: `views_reporting/statistics/statistics.py`, lines 13-543.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform MCMC sampling or model training. It only analyzes pre-existing samples.
- This class does **not** handle multi-dimensional posteriors. It operates on 1D sample arrays only.
- This class does **not** persist results to disk. The `save_path` parameter in `plot_summary()` saves a matplotlib figure, not analysis results.
- This class does **not** compute kernel density estimates (KDE). MAP estimation uses histogram binning only.
- This class does **not** provide dataset-level batch analysis. For batch MAP/HDI over dataset slices, see the module-level helpers `_simon_compute_single_map()` and `_calculate_single_hdi()` in `views_reporting/statistics/dataset_statistics.py`, which instantiate this class per call.

---

## 3. Responsibilities and Guarantees

- **Input validation:** `analyze()` validates all parameters via static validators (`_validate_samples`, `_validate_credible_masses`, `_validate_zero_mass_threshold`, `_validate_bins`) before any computation. Invalid inputs raise `ValueError` immediately.
- **MAP estimation:** Computes MAP as the bin center with highest density in a histogram of `bins` bins (line 203-205). If the proportion of near-zero samples exceeds `zero_mass_threshold`, MAP is forced to 0.0 (lines 196-201).
- **HDI computation:** Computes HDIs via vectorized shortest-interval on sorted samples for each credible mass (lines 209-228).
- **Structural enforcement:** `_enforce_hdi_structure()` guarantees that (a) the narrowest HDI contains the MAP estimate, and (b) each wider HDI fully contains all narrower HDIs (lines 241-311).
- **Computation purity after C-01 fix:** `_compute_summary()` reads only from its parameters, never from `self.*` attributes. Instance state (`self.samples`, `self.credible_masses`, `self.bins`, `self.summary`) is written *after* `_compute_summary()` returns (lines 168-176).
- **Result structure:** `analyze()` always returns a dict with keys `'map'` (float), `'min'` (float), `'max'` (float), `'mass_at_zero'` (float), `'hdis'` (list of (float, float) tuples). The number of HDI tuples equals `len(credible_masses)`.

---

## 4. Inputs and Assumptions

- `samples`: Must be a 1D array-like of floats. NaN and infinite values are silently filtered out. If all values are NaN/infinite, `ValueError` is raised.
- `credible_masses`: Tuple of floats, each strictly in (0, 1). These are sorted ascending before use.
- `zero_mass_threshold`: Float in [0, 1]. Determines when zero-mass MAP override activates.
- `bins`: Positive integer for histogram-based MAP estimation.
- The class assumes samples are drawn from a univariate posterior distribution. No distributional assumptions are made beyond finiteness.

---

## 5. Outputs and Side Effects

**Outputs:**
- `analyze()` returns a summary dictionary (see section 3 for structure).
- `summary_dict()` returns the same dictionary stored at `self.summary`, or `None` if `analyze()` has not been called.
- `print_summary()` writes formatted text to a `TextIO` stream (default: `sys.stdout`).
- `plot_summary()` creates a matplotlib figure with histogram, MAP line, and HDI shading.

**Side effects:**
- `analyze()` writes to instance attributes: `self.samples`, `self.credible_masses`, `self.zero_mass_threshold`, `self.bins`, `self.summary` (lines 171-175). `self.summary` is written last because `print_summary()` and `plot_summary()` gate on `self.summary is None`.
- `plot_summary()` calls `plt.show()` when `show=True` (default). This blocks in non-interactive backends.
- `plot_summary()` optionally saves a figure to disk via `fig.savefig(save_path)`.
- Logging occurs at DEBUG, INFO, WARNING, and ERROR levels via the module-level `logger`.

---

## 6. Failure Modes and Loudness

- **All samples invalid:** `_validate_samples()` raises `ValueError("No valid samples provided.")` if all samples are NaN or infinite (line 50-52).
- **Invalid credible masses:** `_validate_credible_masses()` raises `ValueError` if any mass is not in (0, 1) (line 74).
- **Invalid zero_mass_threshold:** `_validate_zero_mass_threshold()` raises `ValueError` if threshold not in [0, 1] (line 96).
- **Invalid bins:** `_validate_bins()` raises `ValueError` if bins is not positive (line 117-118).
- **Too few samples for HDI:** If `floor(mass * n) < 1` for a given credible mass, a warning is logged and a degenerate HDI `(sorted_samples[0], sorted_samples[0])` is returned (lines 215-221). This does not raise an error -- it is a silent degradation.
- **No summary before interactive use:** `print_summary()` and `plot_summary()` check `self.summary is None` and return early with a warning, never crashing (lines 354-356, 398-400).

---

## 7. Boundaries and Interactions

- **Depends on:** `numpy`, `matplotlib.pyplot`, `scipy.stats` (only used in `test_posterior_analyzer()`), `logging`.
- **Depended on by:** `views_reporting/statistics/dataset_statistics.py` -- the module-level helpers `_simon_compute_single_map()` and `_calculate_single_hdi()` instantiate `PosteriorDistributionAnalyzer` per call (dataset_statistics.py lines 75-77, 157-159).
- **Depended on by:** `views_reporting/visualizations/distributions.py` -- `PlotDistribution` imports and uses the dataset_statistics helpers, which in turn use this class.
- **No dependency on:** dataset handlers, Polars/Pandas, PyTorch, or any pipeline-core components.

---

## 8. Examples of Correct Usage

**Computation path (stateless, thread-safe):**
```python
import numpy as np
from views_reporting.statistics.statistics import PosteriorDistributionAnalyzer

samples = np.random.normal(5, 2, 10000)
analyzer = PosteriorDistributionAnalyzer()
result = analyzer.analyze(samples, credible_masses=(0.5, 0.95, 0.99))
print(f"MAP: {result['map']:.2f}")
print(f"95% HDI: [{result['hdis'][1][0]:.2f}, {result['hdis'][1][1]:.2f}]")
```

**Interactive path (single-threaded only):**
```python
analyzer = PosteriorDistributionAnalyzer()
analyzer.analyze(samples, credible_masses=(0.5, 0.95))
analyzer.print_summary()
analyzer.plot_summary(save_path="posterior.png", show=False)
summary = analyzer.summary_dict()
```

---

## 9. Examples of Incorrect Usage

**Sharing an instance across threads for interactive state:**
```python
# WRONG: self.summary / self.samples are not thread-safe for interactive reads
shared = PosteriorDistributionAnalyzer()
# Thread A: shared.analyze(samples_a); shared.print_summary()
# Thread B: shared.analyze(samples_b); shared.print_summary()
# print_summary() may read state written by the other thread.
```

**Calling interactive methods before analyze():**
```python
analyzer = PosteriorDistributionAnalyzer()
analyzer.print_summary()  # Prints "No summary available" -- does not crash but is a no-op
fig = analyzer.plot_summary()  # Returns None
```

---

## 10. Test Alignment

**Existing pytest tests (13 total):**
- `tests/test_c01_thread_safety.py` (9 tests):
  - Red team: `TestRedTeamThreadSafety` -- race condition reproduction on shared instances and module-level helpers (2 tests).
  - Green team: `TestGreenTeamCorrectness` -- numerical correctness for normal, zero-inflated, bimodal distributions; HDI count matches credible masses; per-call instantiation eliminates races (5 tests).
  - Beige team: `TestBeigeTeamRealisticUsage` -- sequential calls with different params; interactive workflow consistency (2 tests).
- `tests/test_c01_layer1_specification.py` (4 tests):
  - `TestComputeSummaryParameterization` -- verifies `_compute_summary()` uses its parameters, not stale `self.*` state (4 tests).

**Inline test suite (not pytest-integrated):**
- `test_posterior_analyzer()` (static method, lines 438-543): Tests 12 distribution types for MAP containment and HDI nesting. Must be called manually. Uses `np.random.seed(42)` for reproducibility. Not discovered by pytest.

**Invariants tests must enforce:**
- MAP is contained within all HDIs.
- HDIs are properly nested (each wider interval contains all narrower ones).
- `_compute_summary()` produces identical results regardless of prior `self.*` state.
- Sequential calls to `analyze()` with different parameters produce independent results.

---

## 11. Evolution Notes

**Stable:**
- The `analyze()` -> return dict pattern.
- HDI computation via shortest-interval on sorted samples.
- MAP estimation via histogram density peak.

**Expected to change:**
- The inline `test_posterior_analyzer()` should be migrated to pytest.
- Commented-out constructor parameters (`samples`, `auto_analyze`) at lines 22-29 suggest a possible future API where samples are passed at construction time.

### Known Deviations

1. **`plot_summary()` has commented-out `return fig`** (line 435). The docstring declares `Returns: Matplotlib Figure object for further customization, or None if no summary`, but the actual return is always `None` because `return fig` is commented out. This means callers cannot capture and customize the figure.

2. **Inline test suite not pytest-integrated.** `test_posterior_analyzer()` (lines 438-543) is a static method with its own assertion logic, emoji output, and timing. It is not discoverable by pytest and must be invoked manually.

3. **`_enforce_hdi_structure()` is an instance method but uses no instance state.** It could be a `@staticmethod` like the validators, but is not. This is cosmetic.

4. **`__init__` has commented-out parameters and `auto_analyze` logic** (lines 22-29). These remnants from a prior design create confusion about the intended construction API.

---

## End of Contract

This document defines the **intended meaning** of `PosteriorDistributionAnalyzer`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
