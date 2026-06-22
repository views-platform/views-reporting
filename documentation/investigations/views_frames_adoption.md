# Investigation Determination: views-reporting → views-frames v1.0.0

**Date:** 2026-06-22 · **Status:** ✅ **GO** · **Source:** investigation per `/home/simon/.claude/plans/this-information-is-to-gentle-codd.md`
**Closes the investigation deliverable for:** epic #137 (children #138/#139/#140), #113, and the reconciliation-on-frames question behind #72.

> This is the written **determination** (the #113-style deliverable) backed by a throwaway spike. It does
> not change production code. It authorizes the implementation slices in §8.

---

## 1. Verdict

All go-criteria hold; no no-go trigger fired. **Proceed to implementation** (slices in §8).

| Gate | Result |
|------|--------|
| W1 install + conformance | ✅ `views-frames==1.0.0` (+ `views_frames_summarize`, same distribution) installs into the project `.venv` with **zero resolver conflict** against the full tree (torch/scipy/geopandas/pipeline-core, numpy 1.26.4). `assert_frame_contract` passes at `CONFORMANCE_FLOOR="1.0.0"` for `PredictionFrame` and `TargetFrame`. |
| W4 spike — `(N,S)↔(time,entity)` reassembly | ✅ A `PredictionFrame` built from the conftest CM fixture round-trips through the summarizers and reassembles to the per-(time,entity) result. |
| W3 summarizer equivalence | ✅ HDI **bit-exact** (0.0 diff); MAP equivalent on peaked posteriors; differs only where the posterior is near-uniform and the mode is ill-defined (see §3). |
| W7 reconciliation-on-frames | ✅ Runs in place; de-mutation feasible; cross-level mapping available; sums conserved (diff 9.5e-7). |
| W6 test pinning | ✅ Existing assertions are invariant/shape-based, not value-exact (see §6) — low regression risk. |

---

## 2. Ground truth: the views-frames contract (verified by reading the source)

- `PredictionFrame.values` is strictly **`(N, S)` float32, one target**; `N` = flattened `(time, unit)` rows,
  recoverable via `frame.index`. **One frame ≈ one target column**; multi-target reporting needs a frame-set + assembly.
- `TargetFrame` is `(N, 1)` — models the observed/historical "actuals" overlay (`is_sample == False`).
- `SpatioTemporalIndex` (integer `time`/`unit` + `SpatialLevel`) provides same-level joins (`searchsorted`/`reindex`/
  `intersect`/`is_superset_of`, time-major `argsort`) and **cross-level** `cross_level_align(mapping, target_level)`
  (+ columnar `cross_level_align_arrays`) — the cm↔pgm primitive.
- `SpatialLevel.{CM,PGM}` → `.entity_column` (`country_id`/`priogrid_id`), `.index_names` (**time-first**).
- `views_frames_summarize`: `map_estimate(bins=100, zero_mass_threshold=0.3)`, `hdi(mass)`, `quantiles(qs)`,
  `collapse(reducer)`, `aggregate_distributions` (conservation-correct joint-sample sum, grid→country).
  All **vectorized + row-blocked** internally — no joblib.
- `assert_frame_contract` requires float32 + integer identifiers + save/load round-trip; **does not forbid NaN**.

**Gaps found (not blockers):**
- **No year-level (CY/PGY).** `SpatialLevel` is CM/PGM only and `index_names` hardcodes `month_id`. Reporting's
  `historical.py` type-hints `CYDataset/PGYDataset`, but the report path only constructs CM/PGM
  (`loaders/_constants.py` `DATASET_CLASSES={"cm","pgm"}`), so year-level is **effectively dead on the report path**.
  Confirm before relying on it; raise upstream only if a year-level report is ever required.
- **NaN handling stays reporting-side** — the contract permits NaN in `values`; the summarizers don't strip it.
  Reporting's existing NaN guards (`compute_single_map_with_checks`, `np.all(np.isnan)`, nan-mask reapplication)
  must be preserved around the summarizer calls.
- **`MetricFrame` does not exist** (views-evaluation, roadmap Phase 3). The eval-report/C-48 path is **out of scope**.

---

## 3. Summarizer equivalence (W3) — the key numeric finding

Spike on a 4×5×200 CM fixture (zero-inflated + peaked cells), hand-rolled path (`CMDataset` + `calculate_map`/
`calculate_hdi`) vs `views_frames_summarize`:

```
HDI   max|diff| = 0.000e+00      (bit-exact, lower & upper)
MAP   max|diff| = 2.842e+00   on 2/20 rows;  18/20 exact to 4 dp
```

The two divergent rows are **near-uniform posteriors** (`n_modes_near=100` — all 100 histogram bins within 1 count of
the max). There the "mode" is meaningless, and **reporting is already internally non-deterministic**: on row 14,
`calculate_map`=4.62 but reporting's own `compute_single_map`=3.50 for the *same* samples. `map_estimate` (1.78) is a
third equally-arbitrary pick — and is in fact **better**: deterministic and numpy-version-portable (its register C-24).
The residual cause is float32-vs-float64 histogram-edge computation between `np.histogram` and `map_estimate`'s batched
binning. This is the MAP instability register **C-35** already warns about, now empirically demonstrated.

**Implication:** HDI/quantiles/collapse are safe drop-ins. MAP is a safe drop-in for the algorithm; the equivalence
oracle must use a **tolerance** and assert on **peaked** posteriors (realistic conflict data is zero-inflated/peaked),
not exact-match on diffuse cells. Reporting keeps its presentation wrapper (HDI nesting, MAP-forced-inside-narrowest,
degenerate fallback, `enforce_non_negative`, default levels) around the summarizer primitives, and **drops the joblib /
`tqdm_joblib` machinery** (the summarizers row-block internally) — which also retires the global
`Parallel.print_progress` monkeypatch concurrency smell.

---

## 4. Shape-impedance map (W2) — per-consumer migration disposition

| Consumer | Reads today | Frame-side | Disposition |
|---|---|---|---|
| `loaders/_constants.py`, `_protocol.py`, `_registry.py`, `dataframe_loader.py`, `prediction_frame_loader.py`, `__init__.py` | `DATASET_CLASSES`/`INDEX_NAMES` bare strings; pipeline-core `PredictionFrame`+`PredictionFrameConverter`; wrap in CM/PGMDataset | `SpatialLevel` dispatch; construct `views_frames.PredictionFrame` directly from parquet/numpy | **outright** (#138 interim direct-construction path) |
| `statistics/dataset_statistics.py` | `.to_tensor()`/`.get_subset_tensor()` 4D, `.is_prediction`, `.targets`, MultiIndex reassembly | `frame.values` `(N,S)` + summarizers; reassemble to MultiIndex df | **outright** (#139) |
| `visualizations/distributions.py` | `.to_tensor()`, `._get_entity_index`/`._get_time_index`, `.targets` | `frame.values`, index positions via `SpatioTemporalIndex` | **outright** (#139) |
| `mapping/mapping.py` | `.dataframe` MultiIndex+array cells, `.get_subset_dataframe`, `._entity_id`/`._time_id`, geopandas join | reporting-owned `frame(s)_to_mapping_df(frames, level)` adapter producing today's df shape | **thin adapter** |
| `visualizations/historical.py` | `.get_subset_dataframe`, `._time_values`/`._entity_values`, `.sample_size` | same adapter + `TargetFrame` for historical | **thin adapter** |
| `templates/reports/forecast.py` | constructs datasets, `.sample_size`, `isinstance(_CDataset)` | receives frames; `frame.is_sample`; `level` from `SpatialLevel` | **outright** |
| `reconciliation/{reconciliation,dataset_export}.py`, `ForecastReconciler` | `_C/_PGDataset`, `get_subset_tensor`, `_country_to_grids_cache`, **mutates** `reconciled_dataframe` | frame tensors; `cross_level_align`; **return new frame** | **own slice (W7), last** |
| `metadata/entity_metadata.py` | viewser `Queryset` → pandas keyed by `_time_id`/`_entity_id` | join key from `SpatialLevel.entity_column`; viewser fetch stays (C-22, Phase 3) | **edge adapter, not migrated now** |

No unresolved cell: every read maps to a frame-side counterpart or a named reporting-owned converter/adapter.

---

## 5. Adapter-boundary determination (W5): **HYBRID**

- **Stats path → outright.** `dataset_statistics` + `distributions.py` consume the tensor only to compute MAP/HDI and
  re-emit a MultiIndex. With the summarizers owning the math and `frame.values`/`index` owning the data, drop the
  Dataset here. Strongest ADR-018 alignment; this is where #139 points.
- **Mapping/historical + geopandas edge → thin reporting-owned adapter** (`frame(s)_to_mapping_df`). These are
  pandas/MultiIndex/geopandas-centric (shapefile joins, `pivot_table`, array-cell unwrap). The views-frames consumer
  perspective doc itself keeps the pandas/geopandas edge as a consumer adapter (array authoritative, pandas at the
  edge). A single chokepoint lets the heavy, well-tested plotly/legend/dropdown logic migrate behind a stable seam.
- **Reconciliation → its own slice, last**, adapter-style + de-mutation.

Rationale: pure-A multiplies the `(N,S)→4D`/multi-target reassembly across the hardest-to-pin renderers; pure-B keeps a
Dataset dependency exactly where the contract substitution is cleanest. Hybrid is the most reversible.

---

## 6. Test-equivalence (W6)

- `test_statistics.py` asserts **invariants** (MAP ∈ HDI; HDIs nested; one tight peaked synthetic `|map-42|<0.1`) — all
  preserved by the presentation wrapper.
- `test_e2e_golden.py` / `test_e2e_fixture.py` assert **shape/smoke** (map col present, not all-NaN, dtype,
  `len(map_df)==len(prediction_df)`, report exists, contains model name, size>5000) — not value-exact golden numbers,
  so a MAP-on-near-uniform flip does not break them.
- **Main migration cost:** `conftest.mock_views_dataset` is a `MagicMock` returning a 4D tensor — it migrates to a
  frame-shaped double. Add an old-path-vs-new-path equivalence oracle (tolerance on MAP, exact on HDI) over the
  conftest fixtures, and characterization tests for `mapping`/`historical` before their adapter swap.

---

## 7. #113 cycle determination (W8)

Frame adoption removes reporting's **data-contract edge** to pipeline-core — the private
`_CDataset`/`_PGDataset`/`_ViewsDataset` reads (C-114/C-135), the pipeline-core `PredictionFrame` +
`PredictionFrameConverter`, and the pipeline-core re-export of `PosteriorDistributionAnalyzer`. That is the hardest,
most fragile leg.

**But frames are necessary, not sufficient, to fully break #113.** Reporting still imports pipeline-core for
**orchestration/config/io/wandb** in the templates: `PipelineConfig`, `ModelPathManager`, `ForecastingModelManager`,
`files.utils.{generate_model_file_name,read_dataframe}`, `modules.wandb.{WandBModule,format_evaluation_dict,…}`. These
are legitimate reporting→pipeline-core dependencies (the safe direction). The cycle's **reverse edges** (pipeline-core's
`try/except ImportError` re-export shims, `ReportingStage`, `ensemble→ReconciliationModule`) are pipeline-core-side
removals (#183) plus reconciliation relocation (#72). **Determination:** adopt frames to dissolve the data-contract leg
and unblock #183/#72; full cycle closure is a coordinated cross-repo follow-up, not gated on this work.

---

## 8. Implementation slices (ordered, each independently shippable)

1. **Declare the dependency** — add `views-frames>=1.0.0,<2.0.0` to `pyproject.toml`; `uv lock`/`sync`. (numpy-only, verified conflict-free.)
2. **Stats path outright (#139)** — call `views_frames_summarize` in `dataset_statistics.py`/`distributions.py` behind the existing public functions; keep the reporting presentation wrapper (HDI nesting, MAP shift, NaN guards, defaults); drop joblib/`tqdm_joblib`. Land behind the equivalence oracle (HDI exact, MAP tolerance on peaked fixtures).
3. **Loader repoint (#138 interim)** — construct `views_frames.PredictionFrame` directly; replace `DATASET_CLASSES`/`INDEX_NAMES` with `SpatialLevel`.
4. **Mapping/historical adapter** — `frame(s)_to_mapping_df(frames, level)` chokepoint; migrate behind it with characterization tests; `TargetFrame` for the historical overlay.
5. **Conformance at ingestion (#140 → resolves C-111)** — `assert_frame_contract` on loaded frames; pin `CONFORMANCE_FLOOR`.
6. **Reconciliation on frames + de-mutation (C-184)** — frame tensors + `cross_level_align`; return a new frame; relocation (#72) stays a separate later decision.

Register linkage: closes/advances **C-114, C-135, C-111, C-184**; demonstrates **C-35** (MAP instability); retires the joblib monkeypatch blind spot. **C-48 untouched** (Phase 3 / MetricFrame).

---

## 9. How the spike was run (method — scripts were throwaway, not committed)

The spikes were one-off scratch scripts (not part of the repo). To reproduce, install views-frames
non-destructively and re-create the two checks from the methods described in §3 and §7:

```bash
# non-destructive: installs into .venv only (pyproject.toml / uv.lock untouched; a `uv sync` removes it)
uv pip install --python .venv/bin/python 'views-frames>=1.0.0,<2.0.0'
```

1. **Summarizer equivalence + `(N,S)↔(time,entity)` reassembly (§3):** build the conftest
   `build_cm_forecast_df` fixture, run it through `CMDataset` + `calculate_map`/`calculate_hdi` (current path)
   and through a `views_frames.PredictionFrame` (rows time-major) + `views_frames_summarize.map_estimate`/`hdi`
   (new path); reshape the frame result back to `(time, entity)` and compare. Expect HDI bit-exact; MAP exact on
   peaked cells, divergent only on near-uniform cells (§3).
2. **Reconciliation on frames (§7):** build PGM + CM `PredictionFrame`s, use
   `SpatioTemporalIndex.cross_level_align({(time, priogrid_id): country_id}, SpatialLevel.CM)` for the country↔grid
   grouping, run `ForecastReconciler.reconcile_forecast` on the frame-derived tensors, and assert the inputs are
   unmutated and the reconciled cells sum to the country total per sample.

> Slice 1 (§8) declares `views-frames` in `pyproject.toml` for real; until then the install above is `.venv`-only.
