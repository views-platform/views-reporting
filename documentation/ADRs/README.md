
# ADR README and Governance Map

This repository uses Architectural Decision Records (ADRs) to govern
structural, semantic, and operational behavior.

ADRs are divided into two categories:

1. **Constitutional ADRs (000-009)**  
   Foundational architectural rules that apply across the system.

2. **Project-Specific ADRs (010+)**  
   Domain, implementation, or feature-level decisions.

---

## Constitutional ADRs

These ADRs define system philosophy and governance:

- **ADR-000** — Use of Architecture Decision Records (ADRs)  
  Establishes ADRs as the mechanism for recording significant decisions.

- **ADR-001** — Ontology of the Repository  
  Defines what concepts exist: statistical analysis, visualization, report infrastructure, report templates, data transformation, reconciliation, and binary assets.

- **ADR-002** — Topology and Dependency Rules  
  Defines the four-layer dependency structure (data containers, pure computation, rendering, composition) and the outer-layer constraint with pipeline-core.

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

These must comply with the constitutional ADRs above.

---

## Governance Structure (Conceptual Map)

- **Ontology (001)** defines what exists.
- **Topology (002)** defines structural direction.
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
