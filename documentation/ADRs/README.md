
# ADR README and Governance Map

This repository uses Architectural Decision Records (ADRs) to govern
structural, semantic, and operational behavior.

ADRs are divided into three categories:

1. **Constitutional ADRs (000-009)**  
   Foundational architectural rules that apply across the system.

2. **Project-Specific ADRs (010+, unless identity-class — see category 3)**  
   Domain, implementation, or feature-level decisions.

3. **Identity / Foundational ADRs**  
   Decisions that define *what this package is for* and are **constitutional in force regardless of their number**. The constitutional band (000-009) is closed; identity-defining decisions reached later are recorded here and cross-linked into the conceptual map alongside Ontology (001) and Topology (002).

---

## Constitutional ADRs

These ADRs define system philosophy and governance:

- **ADR-000** — Use of Architecture Decision Records (ADRs)  
  Establishes ADRs as the mechanism for recording significant decisions.

- **ADR-001** — Ontology of the Repository  
  Defines what concepts exist: statistical analysis, visualization, report infrastructure, report templates, data transformation, reconciliation, and binary assets.

- **ADR-002** — Topology and Dependency Rules  
  Defines the five-layer dependency structure (data containers, ingestion/loaders, pure computation, rendering, composition) and the outer-layer constraint with pipeline-core.

- **ADR-003** — Authority of Declarations Over Inference  
  Defines where semantic authority lives; forbids inferring metric types from column names or chart types from dataset subclasses.

- **ADR-004** — Rules for Evolution and Stability (Deferred)  
  Reserves a place for future stability and compatibility rules; deferred until the pipeline-core boundary hardens.

- **ADR-005** — Testing as Mandatory Critical Infrastructure  
  Defines red/beige/green test doctrine adapted for visualization scale, statistical accuracy, and report validity.

- **ADR-006** — Intent Contracts for Non-Trivial Classes  
  Requires declared class-level purpose for report modules, statistical classes, and template orchestrators.

- **ADR-007** — Silicon-Based Agents as Untrusted Contributors  
  Governs automated modification with heightened scrutiny for reporting and statistical code.

- **ADR-008** — Observability and Explicit Failure  
  Defines fail-loud + log requirements for report assembly, statistical computation, and rendering.

- **ADR-009** — Boundary Contracts and Configuration Validation  
  Defines explicit interface contracts at the pipeline-core boundary, statistical/visualization boundary, and report template/ReportingStage boundary.

These ADRs form the architectural constitution of the repository.

---

## Project-Specific ADRs

- **ADR-010** — Technical Risk Register  
  Establishes the risk register as a first-class governance artifact at `reports/technical_risk_register.md`.

- **ADR-011** — Data Arrives on Its Original Measurement Scale  
  Declares that views-reporting expects all incoming data on its original measurement scale. No function in this repository will infer, detect, or reverse mathematical transformations based on column naming conventions. Retires the `ln_`/`lx_`/`lr_` prefix convention from this codebase.

- **ADR-012** — Prediction Data Ingestion: Declared Format Dispatch  
  Prediction data loading uses a registry-based loader dispatch in `views_reporting/loaders/`. Two canonical formats: parquet DataFrame (point estimates) and numpy PredictionFrame (sample estimates). Format is declared in model config, never inferred. Loaders form the Ingestion layer (Layer 2 in ADR-002), between the Foundation containers and Computation.

- **ADR-013** — Build Tooling and Packaging: Target hatchling + uv, Ship v0.1 on poetry-core *(Superseded by ADR-014)*  
  Original decision: adopt hatchling + uv as the target but defer the migration, shipping v0.1 on poetry-core. Overturned the same day by an empirical migration spike + `/falsify` audit. Retained for the reasoning trail.

- **ADR-014** — Migrate to hatchling + uv Before First Publish  
  Supersedes ADR-013. views-reporting migrates to **hatchling + uv** (PEP 621/735, committed `uv.lock`) *before* the first PyPI publish — the migration proved cheap and byte-equivalent, and surfaced latent issues poetry hid. Bakes in the verified bounds: **`requires-python = ">=3.11,<3.12"`** (upstream `levenshtein` cap, C-36), Linux/macOS resolution scope, removal of the phantom `views-transformation-library` dep, and uv-based CI.

- **ADR-015** — Automated PyPI Release via GitHub Release + Trusted Publishing  
  Adds `.github/workflows/publish_package.yml`: publishing a **GitHub Release** triggers `uv build` + `uv publish` to PyPI via **Trusted Publishing (OIDC)** — no stored token — with a version-bump guard. Adopts the platform's release-trigger convention (sibling repos' `publish_package.yml`) but modernises tooling (uv, not poetry) and auth (OIDC, not `PYPI_TOKEN`). Manual `uv publish` remains the documented fallback. See `documentation/guides/publishing-to-pypi.md`.

- **ADR-016** — Repository Configuration Mechanism  
  Establishes views-reporting's first configuration primitive: an **in-package Python module** (`views_reporting/config/` — a frozen `ReportingConfig` + `get_config()`) holding the repo's **own rendering defaults** (seeded with the HDI credible levels), distinct from the caller's per-run `dict`. Config is **read at the Compose boundary and injected downward** as parameters — Render/Compute layers must not read it (ADR-002) — and **validated fail-loud** at construction (ADR-003). Ships in the wheel; no new dependency.

- **ADR-017** — Canonical Evaluation-Report Metrics Owned by views-reporting  
  The evaluation report's metric set is a **central, reviewable standard** in `ReportingConfig.canonical_report_metrics`, keyed by **{regression, classification} × {point, sample}** — not the per-model lists from views-models (which stay for dev/training). A model occupies a cell when its `<task>_<pred_type>_metrics` config key is non-empty (declared, not inferred — ADR-003); the report renders the canonical metrics per active cell and shows an explicit "not calculated — add `<metric>` to `<key>`" note for any the run lacks (ADR-008). Inverts authority from developer to reporting standard.

These must comply with the constitutional ADRs above.

---

## Identity / Foundational ADRs

**Constitutional in force** — these define what views-reporting *is for*. They are numbered in the project band only because the constitutional band (000-009) was closed before they were reached; conceptually they sit alongside ADR-001 (Ontology) and ADR-002 (Topology).

- **ADR-018** — views-reporting Renders From Given Data: Depend on Contracts, Not Services  
  Declares the package's responsibility: it **renders human-facing artifacts from data it is given** and must **not** acquire its inputs (no live WandB/viewser calls in the render path). It depends on **contracts** (pipeline-core containers today; views-frames `PredictionFrame`/`MetricFrame` going forward) through **injected adapters** (extending the ADR-012 loader pattern from predictions to metrics + metadata); **scoring stays in views-evaluation** (reporting renders a `MetricFrame`, it does not score); and the **source of truth** for an evaluation is *forecasts + actuals + scoring rule*, not a WandB/parquet cache. Generalizes ADR-002's Ingestion-layer rule to **all** render inputs and admits views-frames as a Foundation-layer contract. The root mandate for resolving Cluster A (register **C-108**); enforcement is phased (`roadmap_to_1.0.0.md`).

---

## Governance Structure (Conceptual Map)

- **Ontology (001)** defines what exists.
- **Topology (002)** defines structural direction.
- **Responsibility (018)** defines what views-reporting is *for* — render from given data, depend on contracts not services.
- **Authority (003)** defines who owns meaning.
- **Boundary Contracts (009)** define interaction rules.
- **Observability (008)** enforces failure semantics.
- **Testing (005)** verifies system integrity.
- **Intent Contracts (006)** bind class-level behavior.
- **Automation Governance (007)** constrains silicon-based agents.

Together, these define the invariant layer of the system.

---

## Recommended Adoption Order

Constitutional ADRs are designed to be adopted incrementally:

### Phase 1 — Foundation
- **ADR-000** (Use of ADRs) — establishes the practice
- **ADR-003** (Authority of Declarations) — the fail-loud invariant
- **ADR-008** (Observability and Explicit Failure) — failure handling

These three are load-bearing. Start here.

### Phase 2 — Structure
- **ADR-001** (Ontology) — define what exists
- **ADR-002** (Topology) — define dependency direction

### Phase 3 — Testing & Intent
- **ADR-005** (Testing Doctrine) — red/beige/green framework
- **ADR-006** (Intent Contracts) — class-level purpose declarations

### Phase 4 — Boundaries & Automation
- **ADR-007** (Silicon-Based Agents) — AI governance
- **ADR-009** (Boundary Contracts) — configuration validation

ADR-004 (Evolution & Stability) is intentionally deferred and should be
revisited when external consumers or reproducibility requirements emerge.
