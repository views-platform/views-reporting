
# Class Intent Contract: DatasetTransformationModule

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts)  

---

## 1. Purpose

> **What is this class for?**

DatasetTransformationModule manages the lifecycle of logarithmic transformations (ln, lx, lr) on VIEWS forecast data stored as Polars DataFrames. It applies forward transforms, reverses them, tracks column name changes through a `column_mapping` dictionary, and maintains a `transformation_history` list for auditability. Its primary use case is undoing log transforms applied during model training so that predictions can be reported in interpretable (linear) scales.

Source: `views_reporting/transformations/transformations.py`, full file (~1494 lines).

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform statistical analysis or model training. It is a data preprocessing/postprocessing utility.
- This class does **not** handle non-logarithmic transformations (e.g., standardization, differencing, Box-Cox).
- This class does **not** validate the semantic correctness of transformations (e.g., whether applying ln to already-negative data is meaningful).
- This class does **not** persist data to disk. It operates on in-memory DataFrames only.
- This class does **not** modify the original dataset object passed to its constructor. It copies the DataFrame (lines 109-114).

---

## 3. Responsibilities and Guarantees

- **Forward transformations:** Three transform types:
  - `ln_transform()`: Applies `ln(x + 1)` and renames columns with `ln_` prefix (lines 580-683).
  - `lx_transform()`: Applies `ln(x + exp(offset))` with configurable offset (default -100) and renames with `lx_` prefix (lines 685-799).
  - `lr_transform()`: Identity (no mathematical operation), only adds `lr_` prefix for state tracking (lines 801-903).
- **Reverse transformations:**
  - `undo_ln_transform()`: Applies `exp(x) - 1`, converts `ln_` prefix to `lr_` (lines 909-1006).
  - `undo_lx_transform()`: Applies `exp(x) - exp(offset)`, converts `lx_` prefix to `lr_` (lines 1008-1114).
  - `undo_lr_transform()`: Removes `lr_` prefix (identity, lines 1116-1195).
  - `undo_transformations()`: Auto-detects prefix and applies appropriate reverse (lines 1328-1493).
  - `undo_all_transformations()`: Bulk reversal of all ln/lx columns to lr state (lines 1197-1326).
- **Column name tracking:** `column_mapping` dict maps original column names to current names. Updated by `_update_column_mapping()` on every transform (lines 361-396). Accessible via `get_current_column_name()`, `get_all_column_mappings()`, `get_transformed_columns()`.
- **History tracking:** `transformation_history` list records each operation with `'operation'`, `'old_name'`, `'new_name'`, and operation-specific fields (e.g., `'offset'` for lx). Accessible via `get_transformation_history()`.
- **Prefix management:** `_has_transform_prefix()`, `_add_transform_prefix()`, `_remove_transform_prefix()` handle underscore-separated prefix logic, including `pred_` prefixed columns (lines 430-574).
- **Skip duplicate transforms:** Each forward transform checks if the column already has that prefix and skips with a warning (e.g., lines 638-641).
- **Column existence validation:** `_validate_column_exists()` raises `ValueError` if a column is not in the DataFrame (lines 398-428).

---

## 4. Inputs and Assumptions

- **Constructor:** Accepts a `CMDataset` or `PGMDataset` from `views_pipeline_core.data.handlers`. The dataset must have a `.dataframe` attribute (Polars or Pandas DataFrame), `._time_id`, and `._entity_id`.
- **DataFrames:** If the input is a Pandas DataFrame, it is converted to Polars with `reset_index()` (line 113). This means index columns become regular columns.
- **Column names:** Transformation methods assume column names use underscore-separated parts where prefixes like `ln_`, `lx_`, `lr_`, `pred_` are meaningful tokens. The prefix detection splits on `_` and checks for exact matches (line 461).
- **Data values:** `ln_transform()` assumes `x >= -1` (since `ln(x + 1)` requires `x + 1 > 0`). No explicit validation of data ranges is performed -- invalid values will produce NaN or raise numpy warnings silently.
- **Offset consistency:** `undo_lx_transform()` requires the caller to pass the same offset used in the original `lx_transform()`. No enforcement exists.

---

## 5. Outputs and Side Effects

**Outputs:**
- `get_dataframe(as_pandas=True)`: Returns the current DataFrame as Pandas (with MultiIndex) or Polars (lines 140-188).
- `get_current_column_name()`: Returns the current name for an original column (lines 190-239).
- `get_all_column_mappings()`: Returns a copy of the full column mapping dict (lines 241-277).
- `get_transformed_columns()`: Returns only columns where original != current name (lines 279-314).
- `get_transformation_history()`: Returns a copy of the history list (lines 316-355).

**Side effects:**
- All transformation methods mutate `self.dataframe` in place (creating new columns, dropping old ones).
- All transformation methods append to `self.transformation_history`.
- All transformation methods update `self.column_mapping`.
- `undo_all_transformations()` clears `self.transformation_history` (line 1319).
- Extensive logging at DEBUG and INFO levels via the module-level `logger`.

---

## 6. Failure Modes and Loudness

- **Column not found:** `_validate_column_exists()` raises `ValueError` with the missing column name and logs available columns at DEBUG level (lines 423-428).
- **Invalid column name after prefix removal:** `_remove_transform_prefix()` raises `ValueError` if removing a prefix would leave only `"pred"` as the column name (lines 567-570).
- **Invalid DataFrame type:** `__init__` raises `TypeError` if `dataset.dataframe` is neither Polars nor Pandas (lines 116-118).
- **Column already transformed (silent skip):** If a column already has the target prefix, the transform method logs a warning and skips it. This is not an error -- it is by design.
- **Missing column in mapping:** `get_current_column_name()` raises `KeyError` if the original name was never in the DataFrame (lines 229-235).
- **Data range violations:** No validation. Applying `ln_transform()` to data with values < -1 produces NaN silently. No fail-loud behavior exists for this case.

---

## 7. Boundaries and Interactions

- **Depends on:** `polars`, `pandas`, `numpy`, `logging`, `views_pipeline_core.data.handlers` (for `CMDataset`, `PGMDataset` types).
- **Standalone within views-reporting:** No other views-reporting module imports or depends on this class.
- **Trusts:** The dataset object's `._time_id` and `._entity_id` attributes to be correct column names.
- **Must not depend on:** Statistics, visualization, or reconciliation modules.

---

## 8. Examples of Correct Usage

**Standard undo-transform workflow for reporting:**
```python
from views_pipeline_core.data.handlers import CMDataset
from views_reporting.transformations.transformations import DatasetTransformationModule

dataset = CMDataset(source="forecast.parquet")
transformer = DatasetTransformationModule(dataset)

# Undo all log transforms applied during training
transformer.undo_all_transformations()

# Get results in interpretable scale
df = transformer.get_dataframe(as_pandas=True)
```

**Selective transform/undo cycle:**
```python
transformer = DatasetTransformationModule(dataset)
transformer.ln_transform(["ged_sb_dep"])
current_name = transformer.get_current_column_name("ged_sb_dep")
# current_name == "ln_ged_sb_dep"

transformer.undo_ln_transform(["ln_ged_sb_dep"])
current_name = transformer.get_current_column_name("ged_sb_dep")
# current_name == "lr_ged_sb_dep"
```

---

## 9. Examples of Incorrect Usage

**Passing raw DataFrames instead of dataset objects (constructor rejects them):**

**Passing raw DataFrames instead of dataset objects:**
```python
import polars as pl
# WRONG: Constructor expects CMDataset/PGMDataset, not a bare DataFrame.
df = pl.DataFrame({"a": [1, 2, 3]})
transformer = DatasetTransformationModule(df)  # AttributeError: 'DataFrame' has no attribute 'dataframe'
```

---

## 10. Test Alignment

**Existing pytest tests:** `tests/test_transformations.py` — 19 tests covering:
- Round-trip correctness (ln, lx with default and custom offset, lr)
- C-04 reproduction (near-zero data with non-default offset)
- Column mapping tracking through transforms
- Transformation history recording
- Duplicate transform skip behavior
- Realistic pandas export workflow
- Validation (nonexistent column, invalid dataframe type)
- Parametrized undo_all round-trip for offsets -10/-50/-100/-200
- Mixed ln + lx undo_all recovery

---

## 11. Evolution Notes

**Stable:**
- The three transform types (ln, lx, lr) and their mathematical definitions.
- Column mapping tracking via `_update_column_mapping()`.
- The underscore-based prefix naming convention.

**Expected to change:**
- The `map_elements` lambda-based transformations could be replaced with native Polars expressions for performance.

### Known Deviations

1. ~~`undo_all_transformations()` hardcodes `offset=-100` for lx transforms~~ — **RESOLVED** in C-04 fix. Both `undo_all_transformations()` and `undo_transformations()` now use `_lookup_lx_offset()` to read offset from `transformation_history`.

2. ~~`undo_transformations()` also hardcodes `offset=-100`~~ — **RESOLVED** in C-04 fix (same `_lookup_lx_offset()` helper).

3. **`transformation_history` is cleared by `undo_all_transformations()` but not by `undo_transformations()`** (line 1319 vs. absent in `undo_transformations`). This inconsistency means `get_transformation_history()` returns different results depending on which undo method was used.

4. **No data range validation on forward transforms.** `ln_transform()` does not check that values are >= -1 before applying `ln(x + 1)`. Invalid values silently become NaN.

5. **No pytest tests exist.** The class has zero automated test coverage.

6. **`get_dataframe(as_pandas=False)` returns `self.dataframe` directly, not a copy** (line 185). This leaks the internal DataFrame, allowing external mutation to corrupt the module's state. The `as_pandas=True` path returns a new Pandas DataFrame, so it does not have this issue.

---

## End of Contract

This document defines the **intended meaning** of `DatasetTransformationModule`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
