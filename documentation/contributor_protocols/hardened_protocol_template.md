# The Hardened Protocol: Contributor Governance

This document defines the mandatory engineering and mathematical standards for the `views-reporting` repository. Adherence to this protocol is required for all contributions to guarantee absolute scientific integrity and reproducibility.

---

## 1. Core Principles

### A. The Authority of Declarations (ADR-003)
**"Never infer; only trust declarations."**
All meaningful semantics (statistical parameters, rendering configurations, reconciliation targets, seeds) must be explicitly declared in configuration. 
- **Prohibited:** Filename-based logic, directory-structure inference, or shape-based guessing.
- **Requirement:** If a parameter affects report identity or statistical output, it must be explicitly declared and validated at construction time.

### B. The Fail-Loud Mandate (ADR-008)
**"A crash is a successful defense of scientific integrity."**
Silent failures, implicit fallbacks, and "best-effort" corrections are forbidden. 
- **Requirement:** Violations of statistical, geographic, or configuration invariants must raise an explicit error immediately.
- **Prohibited:** Using `nan_to_num`, silent clipping, or "sensible defaults" for critical parameters such as HDI credible interval widths, MAP estimator tolerances, or reconciliation convergence thresholds.

### C. The Numerical Airlock
All data entering statistical computation must pass through a numerical airlock.
- **Requirement:** Detect and raise errors on NaNs or Infs at every boundary (data entry from VIEWSER, posterior distribution computation, reconciliation output, final report values).
- **Requirement:** Bayesian posterior analysis (HDI/MAP) must validate that posterior samples are finite and within declared bounds before computing summaries.
- **Requirement:** scipy optimization for spatial reconciliation must validate convergence status and raise on non-convergence rather than returning partial results.
- **Requirement:** torch tensor operations must validate device placement and dtype consistency at function boundaries.

### D. Physical Symmetrical Architecture
**"1 Class, 1 File, 1 Name."**
Organizational Zen is a requirement for maintainability.
- **Requirement:** Every non-trivial class must live in its own file named after the class in `snake_case`.
- **Requirement:** Heterogeneous logic (patches, exceptions) must be consolidated into pre-defined symmetrical hubs.

---

## 2. Contributor Requirements

### Adding a New Component (Visualization, Statistic, Report Module, Transformation)
1.  **Define the Configuration:** Register mandatory parameters in the component's configuration. Statistical parameters (confidence levels, iteration counts, tolerance thresholds) must be explicit.
2.  **Symmetrical Entry:** Create the file following the 1-Class-1-File rule.
3.  **Create Specs/CICs:** Write the **Class Intent Contract (CIC)**.
4.  **Register in Catalog:** Add instantiation logic to the appropriate module or factory.

---

## 3. Mandatory Testing Taxonomy (ADR-005)

Every Pull Request must include tests covering the following three perspectives:

### Green Team (Stability & Correctness)
*   **Goal:** Ensure the system works as intended and remains stable.
*   **Examples:** Statistical computation verification (HDI interval containment, MAP convergence), deterministic graph rendering with seeded entity sampling, report HTML structure validation, shapefile boundary integrity after projection transformations.

### Beige Team (DNA & Human Error)
*   **Goal:** Catch failures caused by common configuration mistakes or missing parameters.
*   **Examples:** Missing credible interval width in config, incompatible CRS in shapefile operations, report template referencing nonexistent data columns, reconciliation targets that sum to impossible totals.

### Red Team (Adversarial)
*   **Goal:** Expose failure modes by deliberately trying to make the system lie or fail.
*   **Examples:** Injecting NaN/Inf into posterior samples, passing zero-variance distributions to HDI computation, providing shapefiles with degenerate geometries, feeding reconciliation targets that violate physical constraints.

---

## 4. Operational Invariants

- **Statistical Computation Accuracy:** All statistical summaries (HDI, MAP, credible intervals) must be validated against known analytical solutions in test suites. Numerical precision requirements must be declared, not assumed.
- **Geographic Boundary Integrity:** Shapefile geometries must preserve topology after all transformations. CRS must be explicitly declared and validated, never inferred from file metadata alone.
- **Report HTML Structure:** Report output must conform to declared template schemas. Missing sections, broken references, or stale data must cause generation failure, not partial output.
- **Reproducibility:** Entity sampling for visualizations must be seeded. Graph rendering must be deterministic given identical inputs and seeds. Reconciliation optimization must use declared random state.

---

**"In this repository, we value correct statistical communication over convenient rendering."**
