# Physical Architecture Standard

This standard defines the mandatory structural rules for the views-reporting repository to ensure **predictable discovery** and **absolute maintainability**.

---

## 1. The 1-Class-1-File Standard

**Every non-trivial class must live in its own file named after the class in `snake_case`.**

- **Correct:** `ClassName` lives in `class_name.py`.
- **Incorrect:** Bundling multiple classes in `utils.py` or `helpers.py`.
- **Exception:** Trivial data containers or exceptions directly related to a class may coexist in the same file.

---

## 2. Directory Ontology (Ontological Separation)

Files must be located in directories that match their **functional category**.

- `statistics/`: Statistical analysis classes (one per file). Bayesian HDI/MAP computation, distribution analysis, summary statistics.
- `visualizations/`: Chart and graph classes (one per file). Line graphs, heatmaps, scatter plots, forecast overlays.
- `mapping/`: Geographic rendering classes (one per file). Choropleth maps, boundary rendering, CRS management.
- `reports/`: Report assembly classes (one per file). Report orchestration, section composition, output generation.
- `reports/styles/`: Styling modules. CSS, color palettes, layout configuration.
- `templates/reports/`: Report template classes (one per file). HTML/Jinja templates and their Python template handlers.
- `loaders/`: Ingestion adapters (declared-format loaders, registry, conformance gate).
- `sources/`: Injected evaluation contracts (`EvaluationSource` port + adapters).
- `metadata/`: Bundled entity-identity accessors + committed data assets.
- `config/`: The frozen `ReportingConfig` boundary (ADR-016).
- `assets/`: Binary resources (shapefiles, fonts, static images). Not Python code. No `__init__.py`.

---

## 3. Symmetrical Hubs

Heterogeneous logic (patches, exceptions) must be consolidated into **Symmetrical Hubs** to prevent logic fragmentation.

- `utils/patches.py` / `utils/exceptions.py`: the designated hubs IF such logic ever appears — currently the repo has no monkey-patches and no cross-module custom exceptions, so these files intentionally do not exist (do not create them empty).

---

## 4. Import Conventions

- **Explicit Imports:** Avoid `from module import *`.
- **Circular Dependency Guard:** Follow ADR-002 to ensure a hierarchical dependency tree. Components in `utils/` must not depend on `visualizations/`, `reports/`, or `statistics/`.

---

## 5. Enforcement

Compliance with this standard is verified during **ADR Compliance Audits**. PRs violating this standard will be rejected until the structure is rectified.

**"The structure of the files is as rigorous as the logic of the code."**
