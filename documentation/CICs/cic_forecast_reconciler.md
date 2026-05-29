
# Class Intent Contract: ForecastReconciler

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts)  

---

## 1. Purpose

> **What is this class for?**

ForecastReconciler adjusts grid-level forecasts so that their sum matches a given country-level total, using proportional scaling. It handles both probabilistic forecasts (2D tensors of posterior samples across grid cells) and point forecasts (1D tensors), preserving zero values in the grid throughout reconciliation.

Source: `views_reporting/statistics/statistics.py`, lines 545-905.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform optimization-based reconciliation. It uses simple proportional scaling only.
- This class does **not** perform hierarchical reconciliation across more than two levels. It reconciles grid-to-country only.
- This class does **not** train or fit any model. It is a post-hoc adjustment step.
- This class does **not** handle negative grid forecast values as a meaningful category. All results are clamped to non-negative via `clamp_(min=0)` (line 647).
- This class does **not** modify the country-level forecast. It only adjusts grid values to match the country total.

---

## 3. Responsibilities and Guarantees

- **Sum constraint:** After reconciliation, the sum of adjusted grid forecasts equals the country forecast for each sample (within floating-point tolerance). Enforced by proportional scaling: `adjusted = grid * (country_total / sum_nonzero)` (lines 643-645).
- **Zero preservation:** Grid cells with value 0 remain 0 after reconciliation. A boolean mask `mask_nonzero = grid_forecast > 0` isolates non-zero values; zeros are excluded from scaling (lines 638-640).
- **Shape preservation:** Output tensor has the same shape as the input tensor. Point forecasts are unsqueezed to 2D for processing, then squeezed back to 1D on return (lines 623-624, 648).
- **Device handling:** Tensors are moved to `self.device` for computation (line 632-633).
- **Non-negativity:** Results are clamped to `min=0` (line 647).
- **Format detection:** Automatically detects point vs. probabilistic forecasts based on tensor dimensionality (`grid_forecast.dim() == 1`, line 620).

---

## 4. Inputs and Assumptions

- `grid_forecast`: A PyTorch tensor. Either:
  - Probabilistic: shape `(num_samples, num_grid_cells)` -- 2D.
  - Point estimate: shape `(num_grid_cells,)` -- 1D.
- `country_forecast`: Either:
  - Probabilistic: shape `(num_samples,)` tensor matching `grid_forecast.shape[0]`.
  - Point estimate: a scalar float.

- The class assumes `grid_forecast.shape[0] == country_forecast.shape[0]` for probabilistic forecasts. This is enforced by a `ValueError` with a descriptive message.
- The class assumes grid forecast values are non-negative. Negative values will be included in the non-zero mask (`> 0` check) and scaled, then clamped to 0.

---

## 5. Outputs and Side Effects

**Outputs:**
- `reconcile_forecast()` returns a PyTorch tensor of adjusted grid forecasts with the same shape as the input.

**Side effects:**
- `__init__` calls `logging.basicConfig(level=logging.INFO)` (line 569), which configures the root logger. This affects the entire process's logging configuration and is a known deviation.
- Logging occurs at DEBUG and INFO levels via `self.logger`.
- `run_tests()`, `run_tests_probabilistic()`, and `run_tests_point()` print test results and timing to the logger.

---

## 6. Failure Modes and Loudness

- **Sample count mismatch:** Raises `ValueError` with descriptive message when `grid_forecast.shape[0] != country_forecast.shape[0]`.
- **All-zero grid forecast:** When all grid cells are zero, `sum_nonzero` is 0 and the denominator becomes `1e-8` (the epsilon guard, line 644). The scaling factor becomes `country_total / 1e-8`, producing extremely large values that are then multiplied by zero (since all values are zero). The result is all zeros, which is correct but the mechanism is fragile.
- **Division precision:** The epsilon `1e-8` in `sum_nonzero + 1e-8` (line 644) prevents division by zero but introduces a small error when `sum_nonzero` is very small but non-zero.
- **No input validation on tensor types:** The method assumes PyTorch tensors. Passing numpy arrays or other types will fail with an `AttributeError` on `.dim()`.

---

## 7. Boundaries and Interactions

- **Depends on:** `torch`, `logging`, `time` (for inline tests only).
- **No dependency on:** numpy, matplotlib, scipy, Polars, Pandas, or pipeline-core.
- **Standalone:** This class has no imports from other views-reporting modules. It operates entirely on PyTorch tensors.
- **Not currently called by:** any other class in the repository (based on code inspection). It appears to be used directly by pipeline orchestration code outside this repository.

---

## 8. Examples of Correct Usage

**Probabilistic reconciliation:**
```python
import torch
from views_reporting.statistics.statistics import ForecastReconciler

reconciler = ForecastReconciler(device='cpu')
grid = torch.rand(1000, 100)  # 1000 samples, 100 grid cells
country = grid.sum(dim=1) * 1.2  # Country total 20% higher
adjusted = reconciler.reconcile_forecast(grid, country)
# adjusted.sum(dim=1) ~= country (within floating-point tolerance)
```

**Point forecast reconciliation:**
```python
grid_point = torch.tensor([10., 20., 30., 0., 15.])
country_point = 100.0
adjusted_point = reconciler.reconcile_forecast(grid_point, country_point)
# adjusted_point.sum() ~= 100.0
# adjusted_point[3] == 0.0  (zero preserved)
```

---

## 9. Examples of Incorrect Usage

**Passing optimization parameters expecting them to work:**
```python
# WRONG: lr, max_iters, tol were removed in C-06 fix.
# This call behaves identically to one without these parameters.
adjusted = reconciler.reconcile_forecast(grid, country)  # lr/max_iters/tol removed in C-06 fix
```

**Passing numpy arrays instead of tensors:**
```python
import numpy as np
# WRONG: Will fail with AttributeError on .dim()
grid_np = np.random.rand(100)
adjusted = reconciler.reconcile_forecast(grid_np, 50.0)
```

---

## 10. Test Alignment

**Existing pytest tests:** None. No files in `tests/` cover `ForecastReconciler`.

**Inline test suite (not pytest-integrated):**
- `run_tests()` (line 650): Orchestrates both test suites below.
- `run_tests_probabilistic()` (lines 693-807): 8 test cases covering basic, all-zeros, extreme skew, sparse, large-scale, extreme scaling, floating-point precision, and mixed zeros/large values scenarios. Validates sum constraint (`< 1e-2`) and zero preservation.
- `run_tests_point()` (lines 810-903): 7 test cases covering similar scenarios for point forecasts.

**Existing pytest tests:** `tests/test_statistics.py` — 36 tests covering sum constraint (7 probabilistic + 7 point scenarios), per-cell zero preservation (14 tests), shape preservation, non-negativity, failure modes (sample count mismatch, epsilon guard, negative forecast, non-tensor input, dead params rejected), realistic usage (sequential calls, device=None), and 1 large-scale slow test.

**Invariants that should be tested (but are not via pytest):**
- Sum of adjusted grid forecasts equals country forecast per sample.
- Zero-valued grid cells remain zero after reconciliation.
- Output shape matches input shape.
- Point and probabilistic paths produce consistent results.

---

## 11. Evolution Notes

**Stable:**
- Proportional scaling algorithm.
- Zero preservation via masking.
- Point/probabilistic dual-path handling.

**Expected to change:**
- An optimization-based reconciliation method was once planned (the parameters `lr`, `max_iters`, `tol` existed but were never used). These were removed in the C-06 fix.
- The inline test suite should be migrated to pytest.

### Known Deviations

1. ~~`reconcile_forecast()` accepts `lr`, `max_iters`, `tol` parameters but never uses them~~ — **RESOLVED** in C-06 fix. Parameters removed from the entire call chain.

2. **`__init__` calls `logging.basicConfig(level=logging.INFO)`** (line 569). This configures the root logger for the entire process, which is bad practice. It should be the application's responsibility to configure logging, not a library class. Any code that imports and instantiates `ForecastReconciler` will have its root logging level set to INFO as a side effect.

3. ~~Uses `assert` for input validation~~ — **RESOLVED** in tech-debt cleanup (D3). Now raises `ValueError` with descriptive message.

4. ~~No pytest tests exist~~ — **RESOLVED.** 36 tests in `tests/test_statistics.py`. Inline test methods deleted in tech-debt cleanup (D5).

5. **`self.logger` vs module-level `logger`:** The class creates its own logger via `logging.getLogger(__name__)` as an instance attribute (line 568), rather than using a module-level logger. This is inconsistent with `PosteriorDistributionAnalyzer` which uses a module-level `logger` (line 11).

---

## End of Contract

This document defines the **intended meaning** of `ForecastReconciler`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
