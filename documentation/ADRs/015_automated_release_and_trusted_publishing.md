# ADR-015: Automated PyPI Release via GitHub Release + Trusted Publishing

**Status:** Accepted
**Date:** 2026-06-04
**Deciders:** Simon, VIEWS platform team
**Related:** ADR-014 (build tooling — hatchling + uv)

---

## Context

`views-reporting 0.1.0` was published to PyPI **by hand** (`uv build` + `uv publish` from a laptop with a personal token). That is error-prone and unreproducible.

The platform already has a release-automation convention: five sibling repos (`views-pipeline-core`, `views-postprocessing`, `views-stepshifter`, `views-evaluation`, `views-r2darts2`) carry an identical `publish_package.yml` that, **on a published GitHub Release**, runs a version-guard and `poetry publish --build` using a stored `PYPI_TOKEN` repo secret.

We cannot copy that workflow: it is **poetry-specific** — it reads `pyproject['tool']['poetry']['version']` and builds with poetry — whereas views-reporting is **PEP 621 `[project]` + hatchling + uv** (ADR-014). It would fail at the version-guard step. No uv-flavoured publish workflow exists anywhere in the platform yet.

## Decision

Add `.github/workflows/publish_package.yml` to views-reporting that **automates releases**, adopting the platform's *trigger + guard* convention but modernising the *tooling* and *auth*:

1. **Trigger:** `on: release: [published]` plus `workflow_dispatch`. Publishing is tied to a **deliberate, tagged GitHub Release** — **not** a push to `main`.
2. **Version guard:** fail the run unless `pyproject`'s `[project].version` is strictly greater than the current PyPI version (PyPI versions are write-once).
3. **Build/publish with uv:** `uv build` then `uv publish` on Python 3.11 (the tested-on version; the declared envelope is `>=3.11,<3.15` since 2026-08-02 — risk C-36).
4. **Auth = PyPI Trusted Publishing (OIDC), not a stored token.** The job declares `permissions: id-token: write`; `uv publish --trusted-publishing always` mints a short-lived OIDC token. **No `PYPI_TOKEN` secret is stored in the repo.**
5. **Manual `uv publish` remains the documented fallback** (`documentation/guides/publishing-to-pypi.md`) for break-glass situations.

**In scope:** the release-to-PyPI automation for this repo. **Out of scope:** changing the sibling repos (they keep their poetry/token workflow until they migrate); CI lint/test (unchanged, `ci.yml`).

## Rationale

- **Trusted Publishing > stored token.** There is no long-lived secret to leak, rotate, or scope wrong; PyPI verifies the GitHub OIDC claim (owner/repo/workflow) directly. This is PyPA's recommended mechanism and strictly better than the platform's current `PYPI_TOKEN` approach.
- **Release-triggered, not push-to-main.** Publishing should be an intentional act bound to a tagged release, not a side effect of merging. Matches the sibling repos' trigger and keeps `main` merges cheap.
- **Reproducible + guarded.** CI builds in a clean runner every time; the version guard makes the common "forgot to bump" mistake a loud failure instead of a wasted version number.
- **Sets the uv template.** views-reporting becomes the first uv+hatchling publish workflow in the platform; the modern repos (faoapi, datafactory) can copy it when they need to publish.

## Considered Alternatives

### A. Copy the sibling `publish_package.yml` (poetry + `PYPI_TOKEN`)
- **Cons:** breaks on our PEP 621/hatchling pyproject; reintroduces a stored token to manage.
- **Rejected.** Wrong toolchain and weaker auth.

### B. Trusted Publishing but via `pypa/gh-action-pypi-publish`
- **Pros:** PyPA-maintained action.
- **Cons:** adds a non-uv step to an all-uv repo; `uv publish --trusted-publishing` covers the same OIDC path natively.
- **Rejected** for consistency (revisit if uv's support regresses).

### C. Trigger on push to `main`
- **Cons:** publishes on every merge; couples release to integration; easy to ship by accident.
- **Rejected.** Releases must be deliberate.

### D. Stay manual-only
- **Rejected.** Error-prone, unreproducible, out of step with the platform.

## Consequences

### Positive
- One-button releases: bump version → merge → publish a GitHub Release → PyPI updates, with a version guard and no secret to manage.
- Stronger security posture than the rest of the platform.

### Negative / required setup
- **One-time PyPI config (manual, by a project owner):** on the `views-reporting` PyPI project → Settings → Publishing → add a **trusted publisher**: Publisher *GitHub*, Owner *views-platform*, Repo *views-reporting*, Workflow *publish_package.yml*, Environment *blank*. Until this is configured, the workflow's publish step will fail (auth refused) — that's the only gap between merging this and it working.
- Divergence from the sibling repos' token workflow (intentional; they can follow later).

## Validation & Monitoring
- First real exercise: cut a `v0.1.1` (or next) GitHub Release and confirm the Action publishes without a token.
- The version-guard step must fail a release whose version isn't bumped (a deliberate guard test).
- If `uv` drops/changes `--trusted-publishing`, fall back to Alternative B.

## References
- `.github/workflows/publish_package.yml` (this repo); `documentation/guides/publishing-to-pypi.md`.
- ADR-014 (hatchling + uv, incl. the 2026-08-02 envelope update block); risk register C-36 (Python envelope / tested-on 3.11).
- Platform precedent: the sibling `publish_package.yml` (poetry + `PYPI_TOKEN`).
- PyPA Trusted Publishing (OIDC for GitHub Actions).
