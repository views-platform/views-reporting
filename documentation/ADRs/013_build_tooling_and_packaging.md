# ADR-013: Build Tooling and Packaging — Target hatchling + uv, Ship v0.1 on poetry-core

**Status:** Superseded by [ADR-014](014_migrate_to_hatchling_uv.md) (2026-06-04)
**Date:** 2026-06-04
**Deciders:** Simon, VIEWS platform team

---

> **Superseded the same day.** This ADR decided to *defer* the hatchling+uv migration and ship v0.1 on poetry-core. An empirical migration spike (uv was already available locally) plus a `/falsify` audit overturned that decision within the same effort: the migration proved cheap, byte-equivalent in the wheel, and it surfaced latent bugs the poetry setup hid. ADR-014 records the decision actually taken (migrate before first publish). This record is retained to preserve the reasoning trail. Where the two conflict, **ADR-014 governs.**

---

## Context

views-reporting is being prepared for its first publication to PyPI (`views-reporting`, v0.1.0). Publishing is currently the team's unblocking priority — a number of other improvements are deliberately gated behind "get it on PyPI first."

The repository's `pyproject.toml` declares a **Poetry** build:

```toml
[tool.poetry]
...
[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

There is no lockfile (`poetry.lock` / `uv.lock` absent); CI installs via plain `pip install -e .`, which works because pip invokes whatever PEP 517 backend the `[build-system]` table names.

The wider VIEWS platform is **mid-migration** in its build tooling:

| Tooling | Repos |
|---|---|
| **hatchling + uv** (newer standard) | views-bayesian, views-datafactory, views-faoapi, views-lab00, views-metric-lab — all with `uv.lock` |
| **poetry-core** (older) | **views-reporting**, views-pipeline-core, views-postprocessing, views-evaluation, views-stepshifter, views-baseline, views-r2darts2 |

The recently-active repos have standardized on **hatchling + uv**, which is clearly the platform's direction of travel. The migration is already documented platform-side as a precedent to follow: **views-faoapi ADR-020 (Build and Package Management Tooling)** records that repo's move from poetry-core to hatchling + uv, with dependencies declared via PEP 621 (`[project.dependencies]`) and PEP 735 (`[dependency-groups]`) and a committed `uv.lock`. This ADR adopts the same target for views-reporting.

views-reporting has not been migrated, and sits in the poetry cohort alongside its own core dependency, **views-pipeline-core**, which is also still on poetry-core.

### Why a decision is needed now

We want to publish *now*, and we want the repo to *eventually* match the hatchling + uv standard. A solo migration of views-reporting before publishing would:

- cost hours of verification and debugging (the failure-prone part is non-Python package data — see Implementation Notes),
- put views-reporting out of step with its own parent dependency (pipeline-core stays on poetry), and
- buy **no PyPI benefit**, because PyPI does not bind a project to a build backend: each release is just a wheel, and `0.1.0` may be built with poetry-core while `0.2.0` is built with hatchling, with no consequence for installers.

So the *decision* (which tooling we are committing to) and the *action* (when we migrate) are separable. This ADR records the decision and defers the action behind an explicit, de-risked trigger.

### Related decisions

- **ADR-002** (Topology): unaffected — build tooling does not change layer rules.
- **ADR-009** (Boundary Contracts and Configuration Validation): the dependency surface (torch, geopandas, the pipeline-core/viewser chain) is a boundary concern; the migration is the natural forcing point to revisit it.
- **Risk register** C-23 (shapefile committed to git), C-24 (torch coupled to reconciliation) — both become prerequisite decisions at migration time.

---

## Decision

1. **Target standard.** The committed build/workflow standard for views-reporting is **hatchling (build backend) + uv (dependency and workflow tooling)**, aligning with the platform's modern repos. poetry-core is explicitly a *legacy interim state*, not an endorsed end state.

2. **Interim for v0.1.** The **v0.1.0 PyPI release is built and published on poetry-core**, unchanged. This unblocks publishing without a same-day migration and keeps views-reporting consistent with views-pipeline-core for the release.

3. **Migration trigger.** views-reporting migrates to hatchling + uv **when views-pipeline-core migrates to hatchling + uv.** The parent dependency's migration is the signal; views-reporting follows so the two never diverge.

4. **Prerequisites at the trigger.** The migration is **not** a pure mechanical pyproject rewrite. Because it rewrites the dependency surface and introduces a lockfile, three coupled concerns must be **resolved or explicitly decided first** — each because the migration changes how it behaves, not merely how it is declared:
   - **torch (C-24)** — under a `uv.lock` the ~2 GB dependency dominates resolution and install time.
   - **Shapefiles / package data (C-23)** — poetry bundles them implicitly today; hatchling will not, so inclusion becomes an explicit choice.
   - **geopandas and the geo stack (GDAL / fiona / shapely / pyproj)** — a binary stack that is a known source of `uv.lock` resolution/build friction; *not yet a risk-register entry* (a candidate to register when this is taken up).

   The concrete options for each are enumerated under **Open Questions**; none are decided by this ADR.

5. **Out of scope.** This ADR does **not** migrate any other VIEWS repository, does **not** change any runtime behavior, and does **not** itself perform the views-reporting migration. It records direction, interim state, trigger, and prerequisites only.

---

## Rationale

- **No PyPI lock-in.** Build backend is a per-release detail on PyPI, so "publish now on poetry, migrate later" incurs the one-time pyproject rewrite *once* — not twice. The "avoid churn" argument for migrating-first does not hold.
- **Consistency with the dependency it imports.** views-reporting depends directly on views-pipeline-core. Coupling the migration trigger to pipeline-core guarantees the two stay on the same tooling, avoiding a window where a hatchling child depends on a poetry parent under divergent lock/resolution conventions.
- **De-risk by deferral, not avoidance.** The costly, error-prone part of the migration (package-data inclusion) is captured here as a checklist, turning vague dread into a scoped task. The direction is binding; only the timing is deferred.
- **Correctness/clarity over speed of modernization.** Migrating under time pressure, the same day as a first publish, is exactly when the shapefile-packaging breakage would slip through untested. Separating the two protects the release.

---

## Considered Alternatives

### Alternative A: Migrate to hatchling + uv *before* publishing v0.1
- **Pros:** v0.1 ships on the target standard; no interim divergence.
- **Cons:** hours of verification/debugging at the worst time; out of step with pipeline-core; the package-data breakage risk lands on the release; no PyPI benefit.
- **Reason for rejection:** all cost, no release benefit, maximum risk concentration. Revisit only if pipeline-core migrates before we publish.

### Alternative B: Stay on poetry-core indefinitely
- **Pros:** zero migration work ever.
- **Cons:** permanent divergence from the platform's modern standard; views-reporting becomes the odd one out as more repos move.
- **Reason for rejection:** contradicts the clear platform direction; we *want* hatchling + uv.

### Alternative C: Adopt uv as workflow now, keep poetry-core backend
- **Pros:** faster local installs/locking immediately.
- **Cons:** uv's project mode reads PEP 621 `[project]` metadata, which poetry's `[tool.poetry]` tables are not — so this is effectively a partial migration with a foot in both camps.
- **Reason for rejection:** a half-step that carries most of the migration's metadata work without finishing it; better done all at once at the trigger.

---

## Consequences

### Positive
- PyPI publication is **unblocked immediately** with zero migration risk.
- The target tooling (hatchling + uv) is now **on the record and binding**, resolving the ambiguity about where the repo is headed.
- The migration is pre-scoped (checklist + prerequisites), so when it happens it is a known task, not exploratory.

### Negative
- v0.1 ships on poetry-core — a **known, accepted, temporary divergence** from the target standard.
- A migration debt is explicitly taken on. It is mitigated by the trigger and checklist but is real until pipeline-core moves.
- The prerequisite decisions (torch, shapefiles, geopandas) are deferred, so the dependency surface remains heavier than ideal in the interim.

---

## Implementation Notes

### v0.1 release (now, poetry-core)
- Add a `license` field to `[tool.poetry]` (currently absent) before publishing.
- Build with `poetry build`; sanity-check the wheel size (the ~56 MB shapefile ships inside it — under PyPI's 100 MB per-file limit, but verify).
- Publish with `poetry publish` (PyPI account + API token required).

### Migration checklist (at the trigger — for the future implementer)
1. Convert `[tool.poetry]` + `[tool.poetry.dependencies]` → PEP 621 `[project]` metadata (name, version, license, dependencies, `requires-python`, classifiers, URLs), with dev/test dependencies as PEP 735 `[dependency-groups]` — matching the pattern in views-faoapi ADR-020.
2. Swap `[build-system]` to `requires = ["hatchling"]`, `build-backend = "hatchling.build"`.
3. **Force-include the non-Python assets** — the shapefiles and header images — via `[tool.hatch.build.targets.wheel.force-include]` (or `artifacts`). **This is the #1 breakage point**: hatchling does not auto-include package data the way poetry does.
4. Resolve the prerequisite decisions (see Decision §4 / Open Questions) and reflect them in the dependency declarations (e.g. optional extras).
5. Add `[tool.uv]` config and generate `uv.lock`.
6. Switch CI from `pip install -e .` to `uv sync` / `uv build`.
7. **Verify**: clean-environment `pip install` (and `uv` install) succeeds, the wheel contains the assets, and a smoke test renders at least one map end-to-end.

---

## Validation & Monitoring

- **Trigger signal to watch:** the `[build-system]` table of `views-pipeline-core`. When it becomes hatchling, views-reporting's migration is due.
- **Migration "done" criteria:** wheel builds under hatchling and contains the shapefile assets; clean-env install succeeds under both pip and uv; one map renders end-to-end; `uv.lock` committed; CI green on uv.
- **Failure mode that would reconsider this ADR:** if a hatchling-child / poetry-parent combination proves unworkable before pipeline-core migrates, the trigger may need to be brought forward (migrate views-reporting first) — revisit then.

---

## Open Questions

- **torch:** hard dependency, optional extra, or removed via the reconciliation move (#72)? (C-24)
- **Shapefiles:** ship in the wheel (force-include) or move to a remote/LFS asset store with download-on-first-use? (C-23)
- **geopandas / geo stack:** pinning and resolution strategy under `uv.lock`; should map rendering be an optional extra? (not yet a register entry — candidate for `register-risk`)
- Should the eventual migration also slim the base install into a lightweight core + optional `[reconciliation]` / `[mapping]` extras, rather than a single heavy package?

---

## References

- Risk register: C-23 (56 MB shapefile committed to git), C-24 (torch coupled to reconciliation); Cluster B (reconciliation placement), Cluster C (PRIO-GRID scale discipline).
- GitHub #72 (reconciliation → views-postprocessing) — affects the torch prerequisite.
- **views-faoapi ADR-020 — Build and Package Management Tooling** (`views-faoapi/docs/ADRs/active/020_build_and_package_management_tooling.md`): the platform precedent this ADR follows (poetry-core → hatchling + uv, PEP 621/735, committed `uv.lock`).
- Other sibling repos on the target standard: views-datafactory, views-bayesian, views-lab00, views-metric-lab (`hatchling.build` + `uv.lock`).
- `pyproject.toml` (current poetry-core configuration).
- ADR-002 (topology), ADR-009 (boundary contracts and configuration validation).
