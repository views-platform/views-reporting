
# ADR-009: Boundary Contracts and Configuration Validation

**Status:** Accepted  
**Date:** 2026-05-28  
**Deciders:** Simon, VIEWS platform team  

---

## Context

Complex systems fail most often at boundaries:

- between modules,
- between configuration and runtime,
- between data producers and consumers,
- between planning and execution.

views-reporting operates at several critical boundaries:

- **views-reporting / pipeline-core boundary:** Report templates consume `_ViewsDataset` and `ModelPathManager` from pipeline-core. The schema of these data containers is owned by pipeline-core, not by this repository. If the contract drifts, reports break silently.
- **Statistical analysis / visualization boundary:** Computation results (HDI intervals, MAP estimates, reconciliation outputs) flow into rendering functions. The shape, units, and semantics of these intermediate results must be explicit.
- **Report templates / pipeline-core `ReportingStage` boundary:** Pipeline-core invokes report templates via deferred import. The calling convention, expected arguments, and return contract must be declared, not assumed.
- **Ingestion layer / pipeline-core prediction managers boundary:** The Ingestion layer (Layer 2, ADR-002) depends not only on pipeline-core data containers but on the pipeline-core *managers* that emit each prediction format — specifically `PredictionFrame` and `PredictionFrameConverter`. This is the one sanctioned exception to "Foundation depends only on containers" (ADR-002). The converter's output shape is a contract that, if it drifts, corrupts reports silently.

Ambiguous configuration, hidden defaults, and implicit contracts
introduce silent semantic drift and runtime fragility.

To preserve architectural integrity and fail-loud guarantees (ADR-003),
all external and internal boundaries must be explicit and validated.

---

## Decision

This repository adopts the following invariants:

> All architectural boundaries must declare explicit contracts.  
> All configuration must be validated at entry.  
> No semantic defaults may exist silently.

---

## 1. Boundary Contracts

Every boundary between components must define:

- Explicit input schema
- Explicit output schema
- Declared invariants
- Failure semantics

Key boundaries in views-reporting:

- **views-reporting / pipeline-core:** `_ViewsDataset` schema contract (expected attributes, MultiIndex structure), `ModelPathManager` interface (expected methods and path conventions)
- **Statistical analysis / visualization:** computation results must declare their semantic type (e.g., HDI bounds, MAP point estimate, reconciled prediction) — visualization must not infer semantics from array shape
- **Report templates / `ReportingStage`:** deferred import contract — templates must be importable without pipeline-core's full module graph, and must accept a declared argument signature
- **Ingestion layer / pipeline-core prediction managers:** see the dedicated contract in §1a

Implicit contracts are prohibited.

If a boundary assumption cannot be declared clearly,
the boundary is ill-defined and must be redesigned.

### 1a. Ingestion ↔ pipeline-core prediction-manager contract

The Ingestion layer (`views_reporting/loaders/`, Layer 2 per ADR-002) is permitted to import the following pipeline-core **managers/converters**, in addition to the Foundation data containers — this is the sanctioned exception to the containers-only rule:

- `views_pipeline_core.data.prediction_frame.PredictionFrame`
- `views_pipeline_core.managers.prediction.prediction_frame_converter.PredictionFrameConverter`

**Input schema (what loaders supply):** a declared `prediction_format` ∈ {`dataframe`, `prediction_frame`}, a `level` ∈ {`cm`, `pgm`}, a `targets` list, and a path. Format is declared, never inferred (ADR-003).

**Output contract (what the converter guarantees):** `PredictionFrameConverter().to_prediction_df(pf, target)` returns a `pd.DataFrame` whose MultiIndex levels are **unnamed (`[None, None]`)**. The loader is responsible for repairing this by calling `set_names(INDEX_NAMES[level])` before constructing a dataset (`views_reporting/loaders/prediction_frame_loader.py`). This unnamed-index handshake is the contract's most fragile point: if the converter begins emitting *named* levels, or different level order, the loader's `set_names` would mislabel axes and silently mis-align values to entities.

**Declared invariants:**
- The converter output row count equals the length of its identifier arrays.
- `level` and the resulting MultiIndex structure must agree (a `cm` load must yield `["month_id", "country_id"]`; `pgm` yields `["month_id", "priogrid_id"]`).

**Failure semantics:** unknown `level` → `ValueError` (loader); unknown `prediction_format` → `ValueError` listing registered formats (registry, ADR-008); a missing target directory or `y_pred.npy` → the error raised by `PredictionFrame.load`. Drift in the converter's index-naming contract is **not** currently detected by a guard — it is a known silent-corruption seam tracked in the risk register (C-30) and the loader CIC.

---

## 2. Configuration as First-Class Artifact

Configuration is not a convenience layer.
It is an architectural artifact.

Configuration must:

- Be explicit
- Be versionable
- Be externally inspectable
- Be validated before execution
- Not rely on hidden defaults

Changing configuration must not silently alter system meaning —
for example, changing a report template parameter must not silently
change which statistical metrics are included or how they are rendered.

---

## 3. Validation at Entry (Handshake Principle)

All configuration and external inputs must be validated at the system boundary.

Validation must occur:

- Before state mutation
- Before execution begins
- Before report assembly proceeds

The system must fail early if:

- Required fields are missing (e.g., dataset lacks expected columns)
- Types are incorrect (e.g., non-DataFrame passed where DataFrame expected)
- Redundant parameters disagree (e.g., declared level contradicts MultiIndex structure)
- Declared invariants are violated (e.g., spatial hierarchy constraints not met)

Borrowed or assumed state is prohibited.

---

## 4. Separation of Configuration Domains

Configuration domains must be separated conceptually.

In views-reporting:

- **Operational parameters** (affect computation): statistical method parameters, reconciliation constraints, sampling rates
- **Presentation parameters** (affect rendering): color scales, chart dimensions, map projections, tailwind classes
- **Metadata parameters** (informational only): report titles, date stamps, version labels

Cross-domain coupling must be explicit.

Configuration that affects computation must not be disguised as presentation,
and vice versa.

---

## 5. Redundancy and Consistency Checks

Where ambiguity risk is high, explicit redundancy is preferred.

Examples in views-reporting:

- Declaring both the expected resolution level and the MultiIndex structure
- Declaring both the metric type and the expected column names
- Declaring both the spatial hierarchy and the reconciliation constraints

Redundant declarations must be validated for consistency.

Silent derivation is discouraged where semantic meaning is involved.

---

## 6. Failure Semantics

Configuration validation failures must:

- Be logged (ADR-008)
- Be raised explicitly (ADR-008)
- Halt execution

Warnings are insufficient for structural configuration errors.

---

## Consequences

### Positive

- Eliminates hidden configuration drift
- Reduces boundary fragility, especially at the pipeline-core interface
- Strengthens fail-loud guarantees
- Improves reproducibility and traceability of generated reports

### Negative

- Requires explicit schemas
- Adds validation boilerplate
- Increases up-front configuration clarity requirements

These costs are accepted.

---

## Notes

This ADR does not prescribe:

- Specific file layouts
- Specific configuration libraries
- Specific schema frameworks

Operational configuration structures may vary,
provided they comply with the invariants defined here.
