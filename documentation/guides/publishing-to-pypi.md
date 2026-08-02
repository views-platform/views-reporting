# Publishing `views-reporting` to PyPI

A practical runbook for releasing this package. Written to be followed **solo, cold, months later** — every command is copy-paste-able with the expected output, and the *why* is spelled out. If you only need to ship a routine update, the cheat sheet below is enough; the rest is detail and safety nets.

> **Last verified:** 2026-06-04 with `uv 0.8.13`, releasing `views-reporting 0.1.0`.
> Build tooling is governed by **ADR-014** (`../ADRs/014_migrate_to_hatchling_uv.md`); the Python envelope (`>=3.11,<3.15` declared, **3.11 tested-on**) by risk **C-36** (`../../reports/technical_risk_register.md`). If either changes, update this guide.

---

## TL;DR — release an update (the automated way)

Normal releases are published **by CI** when you publish a **GitHub Release** — you do **not** run `uv publish` by hand. Auth is PyPI Trusted Publishing (no token); see ADR-015 and `.github/workflows/publish_package.yml`.

```bash
# 1. bump the version on a branch (you can NEVER reuse a published version)
$EDITOR pyproject.toml                         # under [project]: version = "X.Y.Z"
git commit -am "release: vX.Y.Z" && git push   # open a PR -> merge to main

# 2. (optional, wise for big changes) rehearse on TestPyPI first — see §A

# 3. cut the GitHub Release FROM main — this triggers the publish workflow:
gh release create vX.Y.Z --target main --title "views-reporting X.Y.Z" --notes "what changed"
#    (or GitHub UI: Releases -> Draft a new release -> tag vX.Y.Z on main -> Publish)

# 4. confirm: Actions tab shows "Publish Package" green, then
#    https://pypi.org/project/views-reporting/
```

The workflow guards the version (must beat PyPI) and publishes via Trusted Publishing — **no token needed for this path**. The manual `uv publish` route is the break-glass fallback (§B). First-ever setup requires the one-time PyPI trusted-publisher config — see Prerequisites.

---

## Why this repo is special (read once — these bite if forgotten)

| Thing | What | Why |
|---|---|---|
| **Declared 3.11–3.14, TESTED on 3.11** | `pyproject.toml` declares the platform envelope `requires-python = ">=3.11,<3.15"` (matching views-pipeline-core 3.0.0 / views-evaluation, decision 2026-08-02) | Build *and* test-install on **3.11** — it is the only version the full stack installs on in practice: `views-pipeline-core → ingester3 → levenshtein 0.20.9` has no cp312+ wheel and its sdist build fails on 3.12/3.13 (re-verified 2026-08-02). 3.12+ installs fail loudly at that upstream build; tracked as risk **C-36** — the fix is upstream (ingester3), not a cap here. |
| **Versions are write-once** | Once `X.Y.Z` is on PyPI/TestPyPI it can never be re-uploaded or truly deleted (only "yanked") | Always **bump the version first**. For repeated TestPyPI rehearsals, use a throwaway like `0.1.1.dev1`. |
| **uv + hatchling, NOT poetry** | Build backend is `hatchling.build`; tooling is `uv` | Use `uv build` / `uv publish`. See ADR-014. (`poetry` is not installed and not used.) |
| **TestPyPI needs a second index** | Installing from TestPyPI requires `--extra-index-url https://pypi.org/simple/` | TestPyPI only hosts *your* package; its dependencies (geopandas, plotly, pyarrow, …) live on **real** PyPI. |
| **Big assets are bundled** | The wheel includes ~56 MB of PRIO-GRID shapefiles (compresses to a ~6.7 MB wheel) | After `uv build`, sanity-check they're present (command in §A). |

---

## Prerequisites (one-time setup)

### Trusted Publishing — the automated path (do this once; no token)

The automated release workflow (`.github/workflows/publish_package.yml`, ADR-015) authenticates to PyPI with **Trusted Publishing (OIDC)** — there is **no stored token**. A project owner enables it **once** on PyPI:

> On the **`views-reporting`** PyPI project → **Settings → Publishing → Add a trusted publisher (GitHub)**:
> - **Owner:** `views-platform`  ·  **Repository:** `views-reporting`
> - **Workflow name:** `publish_package.yml`  ·  **Environment:** *(leave blank)*

Until this is configured, the workflow's publish step fails with an auth error — that's the only gap between merging the workflow and it working. (TestPyPI has the same "Publishing" settings if you ever want to trust-publish there too.)

### API tokens — only for the TestPyPI rehearsal (§A) and the manual fallback (§B)

You still need tokens for the *manual* routes. They're on **two separate sites**:

| | TestPyPI (rehearsal) | Real PyPI (production) |
|---|---|---|
| Register | https://test.pypi.org/account/register/ | https://pypi.org/account/register/ |
| 2FA | required | required |
| Make a token | Account settings → **API tokens** → Add token | same |
| First-upload scope | "Entire account" (project doesn't exist yet) | "Entire account" for the *very first* upload; **project-scoped** thereafter |

The token looks like `pypi-AgEN…` and is shown **once** — copy it somewhere safe.

> 🔒 **Token-safety rule:** type a token **only in your own terminal**. Never paste it into a chat/transcript/PR. The publish commands do not echo it. To keep it out of shell history, prefix the command with a space, or `export UV_PUBLISH_TOKEN=pypi-…` and drop `--token`.

---

## A. Test deployment — the TestPyPI dress rehearsal

TestPyPI is a throwaway clone of PyPI. Rehearse the full upload→install loop here so the real publish is boring. Do this whenever you're unsure or it's a big release.

**1. Build + check** (from the repo root, on the branch you're releasing):
```bash
rm -rf dist && uv build
uvx --from twine twine check dist/*           # both files must say PASSED
# sanity: assets bundled + correct metadata
unzip -l dist/*.whl | grep -cE "\.shp|\.dbf"  # expect 4
unzip -p dist/*.whl "*.dist-info/METADATA" | grep -iE "^Version|^Requires-Python|^License"
```

**2. Upload to TestPyPI** (your terminal; replace the token):
```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token pypi-<YOUR-TESTPYPI-TOKEN> dist/*
```
Expected: `Uploading views_reporting-… (6.7MiB)` for both files, then back to the prompt with no error.

**3. Eyeball the page:** https://test.pypi.org/project/views-reporting/ — version, README renders, `License: MIT`.

**4. Install it back into a clean room** (the real test — proves a fresh machine can get the package *and* its deps):
```bash
uv venv --clear --python 3.11 /tmp/tp-check     # MUST be 3.11 (see gotchas)
source /tmp/tp-check/bin/activate
uv pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               views-reporting
python -c "import views_reporting; print('import OK')"
deactivate && rm -rf /tmp/tp-check
```
> The **two index URLs are both required** (see gotchas). This step downloads ~300 MB (GDAL/geopandas stack; torch left with #72) — a few minutes is normal.

Rehearsal passes when: build checks PASS, upload succeeds, the page looks right, and the clean-room `import OK`.

---

## B. First real deployment (how `0.1.0` was shipped)

This is what we did the first time. Same as the cheat sheet, with the careful ordering:

```bash
# release from the released line
git checkout main && git pull --ff-only

# build fresh + verify (as in §A step 1)
rm -rf dist && uv build
uvx --from twine twine check dist/*

# create the version tag locally (don't push yet)
git tag -a vX.Y.Z -m "views-reporting X.Y.Z — <one-line summary>"

# publish to REAL PyPI — the ONLY difference from the rehearsal is dropping --publish-url
uv publish --token pypi-<YOUR-REAL-PYPI-TOKEN> dist/*
```
Then **confirm it's live** before pushing the tag:
```bash
curl -s https://pypi.org/pypi/views-reporting/json | python3 -c "import sys,json;d=json.load(sys.stdin)['info'];print(d['name'],d['version'])"
# optional clean-room install from REAL PyPI (no --extra-index-url needed; PyPI has everything):
uv venv --clear --python 3.11 /tmp/pypi-check
uv pip install --python /tmp/pypi-check/bin/python views-reporting
/tmp/pypi-check/bin/python -c "import views_reporting; print('import OK')"
rm -rf /tmp/pypi-check
```
Once confirmed, **push the tag** (so the tag reflects what's actually published):
```bash
git push origin vX.Y.Z
```

---

## C. Future updates (the repeatable loop — automated)

Since ADR-015, normal releases are **published by CI on a GitHub Release** — you don't run `uv publish`. The loop:

1. **Bump the version** in `pyproject.toml` under `[project]` (`version = "X.Y.Z"`). You **cannot** reuse a published version (semver: patch for fixes, minor for features).
2. (Recommended) note what changed (use the GitHub Release notes for this).
3. Commit on a branch → PR → **merge to `main`**.
4. (Optional, wise for big changes) **rehearse on TestPyPI** (§A) with a throwaway dev version (`X.Y.Z.dev1`) so you don't burn the real number; revert to `X.Y.Z` before merging.
5. **Cut the GitHub Release from `main`** — this triggers `publish_package.yml`:
   ```bash
   gh release create vX.Y.Z --target main --title "views-reporting X.Y.Z" --notes "what changed"
   ```
   The workflow runs the **version guard**, `uv build`, and `uv publish` via **Trusted Publishing** (no token).
6. **Verify:** the **Actions** tab shows *Publish Package* green, then https://pypi.org/project/views-reporting/.

> **How it works under the hood:** `release: published` → `permissions: id-token: write` mints an OIDC token → PyPI checks the GitHub claim against the trusted publisher you configured → upload. The version guard fails the run if `[project].version` isn't higher than what's on PyPI, so "forgot to bump" is a loud error, not a wasted version.

### Break-glass: manual publish (only if CI is down)
```bash
git checkout main && git pull --ff-only
rm -rf dist && uv build && uvx --from twine twine check dist/*
uv publish --token pypi-<YOUR-PYPI-TOKEN> dist/*       # project-scoped token
git tag -a vX.Y.Z -m "views-reporting X.Y.Z" && git push origin vX.Y.Z
```

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `403 Forbidden` on upload | Wrong/expired token, or a **TestPyPI token used on real PyPI** (or vice-versa). Use the token for the site you're publishing to. |
| `400 … File already exists` | That version is already uploaded — **versions are write-once**. Bump `version` in `pyproject.toml` and rebuild. |
| Install fails building `levenshtein` (0.20.9) | You're on 3.12–3.14: resolution succeeds (declared envelope `<3.15`) but the upstream `ingester3 → levenshtein` sdist build fails — **expected-loud** (C-36). Use `uv venv --python 3.11 …` — 3.11 is the only version the full stack installs on in practice. |
| `pip/uv install` says *"requires a different Python"* | You're outside `>=3.11,<3.15` (e.g. 3.10 or 3.15+). Use a Python inside the envelope — practically **3.11** (C-36). |
| Install from TestPyPI can't find deps | Missing `--extra-index-url https://pypi.org/simple/` — TestPyPI doesn't host the dependencies. |
| `twine check` fails on metadata | Stale build — `rm -rf dist && uv build` and re-check. |
| `poetry: command not found` | This repo uses **uv**, not poetry (ADR-014). Use `uv build` / `uv publish`. |

---

## Provenance
- The **manual** path (§A/§B) was verified end-to-end **2026-06-04** — TestPyPI rehearsal → real publish of `0.1.0` → clean-room install.
- The **automated** path (§C, `.github/workflows/publish_package.yml`, **ADR-015**) was added the same day and **has now been exercised for real**: v0.3.0 (2026-08-02) published to PyPI automatically on GitHub-release creation via Trusted Publishing (Actions run 30745908919, green — no manual step, no token). The trusted-publisher config is in place.
- Build tooling: **ADR-014** (hatchling + uv). Python envelope `>=3.11,<3.15` declared / **3.11 tested-on** (decision 2026-08-02): risk **C-36**. Release automation: **ADR-015**. All in this repo's governance — if they change, this guide should change with them.
