# ADR-014: Migrate to hatchling + uv Before First Publish

**Status:** Accepted
**Date:** 2026-06-04
**Deciders:** Simon, VIEWS platform team
**Supersedes:** ADR-013 (Build Tooling and Packaging — deferral decision)

---

## Context

[ADR-013](013_build_tooling_and_packaging.md) decided to ship v0.1 on the existing poetry-core backend and *defer* the hatchling + uv migration until views-pipeline-core migrated. Its deferral rested on three pillars: tooling friction, "hours of debugging" the package-data inclusion, and consistency with the still-poetry parent dependency.

While walking through the first PyPI publish, those pillars collapsed against evidence:

- **`uv` was already installed locally** (`uv 0.8.13`) and built the package in seconds. No tooling friction.
- The package-data worry was overstated: hatchling **auto-includes the git-tracked shapefiles** (no `force-include` needed), and the verify loop (`uv build` → inspect wheel) is the same check, in seconds.
- Build backends are **per-package and independent**: a hatchling-built views-reporting depending on a poetry-built views-pipeline-core resolves fine. The "stay consistent with the parent" pillar only ever applied to dev-workflow taste, not correctness.

A migration spike on branch `feat/migrate-hatchling-uv`, followed by a `/falsify` audit, then settled it empirically.

### What the empirical migration found

- **Build is byte-equivalent.** The hatchling wheel has an *identical 54-file manifest* to the poetry wheel; shapefiles bundle automatically; 6.7 MB; sdist→wheel preserves assets; `twine check` PASSES (Metadata 2.4, `License-Expression: MIT`).
- **Full suite green on Python 3.11** under the uv-synced toolchain: 228 passed, 2 xfailed.
- **It surfaced latent problems the poetry setup hid** (no lockfile ever resolved the tree):
  1. A `pytest` conflict — `views-pipeline-core` pins `pytest<9` (runtime), but the dev group asked for `>=9.0.3`. Fixed by aligning the dev pin to `<9`.
  2. **Python is bounded to 3.11** — `views-pipeline-core → ingester3 → levenshtein 0.20.9` has no wheel and fails to build on 3.12 **and** 3.13 (both verified). The original `requires-python = ">=3.11,<3.15"` was simply false.
  3. **Windows does not resolve** — `viewser → docker → pywin32` breaks universal resolution; scoped via `[tool.uv] environments` to Linux/macOS (confirmed as standing policy).
  4. A **phantom dependency**: `views-transformation-library` was declared but never imported, and is pulled transitively via pipeline-core anyway. Removed (zero change to the installed tree).

## Decision

views-reporting **migrates to hatchling + uv now, before the first PyPI publish.**

- **Build backend:** `hatchling`. **Workflow/dependency tooling:** `uv`, with a committed `uv.lock`.
- **Metadata:** PEP 621 `[project]` + PEP 735 `[dependency-groups]` (matching views-faoapi ADR-020).
- **`requires-python = ">=3.11,<3.12"`** — the honest, verified bound. Widen when upstream updates `levenshtein` (tracked as **C-36**).
- **`[tool.uv] environments`** scoped to `linux` + `darwin`.
- **Drop** the phantom `views-transformation-library` direct dependency.
- **CI** runs on `uv sync --frozen` + `uv run`, so the lockfile is exercised.
- v0.1 publishes from this hatchling build, on Python 3.11.

**Out of scope:** the residual heavy-dependency questions (torch as optional extra; the geopandas/geo stack) remain future work; the upstream `levenshtein`/`docker`/`pytest` pins are upstream's to fix.

## Rationale

- Migrating-first costs the one-time pyproject rewrite we'd pay anyway; doing it *before* publish means v0.1 ships on the target tooling and with **honest metadata** (a 3.12 user is refused upfront rather than hitting a cryptic build failure post-install).
- The lockfile makes the environment **reproducible** and exposed real latent bugs — correctness gained, not just modernization.
- It aligns with the platform standard (views-faoapi ADR-020) and the build is provably equivalent to the poetry one, so the migration is low-risk.

## Consequences

### Positive
- v0.1 ships on the modern standard with a reproducible lockfile and truthful `requires-python`.
- Two latent bugs (pytest conflict, false Python range) fixed; one phantom dependency removed.
- CI now validates the locked environment.

### Negative
- views-reporting is now **explicitly Python 3.11-only and Linux/macOS-only** (was implicitly so; now enforced). Reach is capped until upstream updates — tracked as **C-36**.
- The repo diverges in tooling from still-poetry siblings (pipeline-core, postprocessing, …) until they follow.

## Validation & Monitoring

- Guarded by `tests/test_packaging_invariants.py`: `requires-python` capped `<3.12`, uv environments scoped, no phantom transformation-library dep.
- Re-evaluate `requires-python` and platform scope when `views-pipeline-core` / `ingester3` update the `levenshtein` pin (C-36) or when viewser sheds docker/pywin32 (C-22).

## References

- Supersedes ADR-013 (deferral decision, retained for the reasoning trail).
- views-faoapi ADR-020 (hatchling + uv precedent).
- Risk register: C-36 (Python/platform bound), C-23 (shapefile — now resolved: hatchling auto-includes), C-24 (heavy deps), C-22 (viewser retirement).
- Branch `feat/migrate-hatchling-uv`; `/falsify` audit (2026-06-04).
