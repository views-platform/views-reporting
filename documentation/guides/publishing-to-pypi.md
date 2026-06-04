# Publishing `views-reporting` to PyPI

A practical runbook for releasing this package. Written to be followed **solo, cold, months later** — every command is copy-paste-able with the expected output, and the *why* is spelled out. If you only need to ship a routine update, the cheat sheet below is enough; the rest is detail and safety nets.

> **Last verified:** 2026-06-04 with `uv 0.8.13`, releasing `views-reporting 0.1.0`.
> Build tooling is governed by **ADR-014** (`../ADRs/014_migrate_to_hatchling_uv.md`); the Python-3.11 cap by risk **C-36** (`../../reports/technical_risk_register.md`). If either changes, update this guide.

---

## TL;DR — release an update (you've done this before)

From a clean checkout of the **released branch** (`main`), with `dist/` rebuilt:

```bash
# 1. bump the version (you can NEVER reuse a published version)
$EDITOR pyproject.toml          # version = "X.Y.Z"

# 2. build + sanity-check (from the repo root)
rm -rf dist && uv build
uvx --from twine twine check dist/*

# 3. publish to real PyPI  (run in YOUR terminal — token is a secret)
uv publish --token pypi-<YOUR-PYPI-TOKEN> dist/*

# 4. tag the release and push the tag
git tag -a vX.Y.Z -m "views-reporting X.Y.Z" && git push origin vX.Y.Z

# 5. confirm: https://pypi.org/project/views-reporting/
```

First time ever, or want to be careful? Do the **TestPyPI rehearsal (§A)** before step 3.

---

## Why this repo is special (read once — these bite if forgotten)

| Thing | What | Why |
|---|---|---|
| **Python 3.11 only** | `pyproject.toml` pins `requires-python = ">=3.11,<3.12"` | An upstream dep chain (`views-pipeline-core → ingester3 → levenshtein 0.20.9`) has **no 3.12/3.13 build**. Build *and* test-install on **3.11**, or installs fail. Tracked as risk **C-36**; widen the cap only after upstream updates. |
| **Versions are write-once** | Once `X.Y.Z` is on PyPI/TestPyPI it can never be re-uploaded or truly deleted (only "yanked") | Always **bump the version first**. For repeated TestPyPI rehearsals, use a throwaway like `0.1.1.dev1`. |
| **uv + hatchling, NOT poetry** | Build backend is `hatchling.build`; tooling is `uv` | Use `uv build` / `uv publish`. See ADR-014. (`poetry` is not installed and not used.) |
| **TestPyPI needs a second index** | Installing from TestPyPI requires `--extra-index-url https://pypi.org/simple/` | TestPyPI only hosts *your* package; its dependencies (torch, geopandas, viewser, …) live on **real** PyPI. |
| **Big assets are bundled** | The wheel includes ~56 MB of PRIO-GRID shapefiles (compresses to a ~6.7 MB wheel) | After `uv build`, sanity-check they're present (command in §A). |

---

## Prerequisites (one-time setup)

You need accounts + API tokens on **two separate sites**:

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
> The **two index URLs are both required** (see gotchas). This step downloads ~2 GB (torch + GDAL stack) — a few minutes is normal.

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

## C. Future updates (the repeatable loop)

Every subsequent release:

1. **Bump the version** in `pyproject.toml` (`version = "X.Y.Z"`). You **cannot** reuse a published version — pick the next one (semver: patch for fixes, minor for features).
2. (Recommended) write a short note of what changed (CHANGELOG / release notes).
3. **Build + check:** `rm -rf dist && uv build && uvx --from twine twine check dist/*`.
4. (Optional but wise for big changes) **rehearse on TestPyPI** (§A) using a throwaway dev version (e.g. `X.Y.Z.dev1`) so you don't burn the real version number. Revert to `X.Y.Z` before the real publish.
5. **Publish:** `uv publish --token pypi-<YOUR-PYPI-TOKEN> dist/*` (prefer a **project-scoped** token now that the project exists).
6. **Tag + push:** `git tag -a vX.Y.Z -m "…" && git push origin vX.Y.Z`.
7. **Verify** on https://pypi.org/project/views-reporting/.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `403 Forbidden` on upload | Wrong/expired token, or a **TestPyPI token used on real PyPI** (or vice-versa). Use the token for the site you're publishing to. |
| `400 … File already exists` | That version is already uploaded — **versions are write-once**. Bump `version` in `pyproject.toml` and rebuild. |
| `pip/uv install` says *"requires a different Python"* | You're on 3.12/3.13. The package is **3.11-only** (C-36). `uv venv --python 3.11 …`. |
| Install from TestPyPI can't find deps | Missing `--extra-index-url https://pypi.org/simple/` — TestPyPI doesn't host the dependencies. |
| `twine check` fails on metadata | Stale build — `rm -rf dist && uv build` and re-check. |
| `poetry: command not found` | This repo uses **uv**, not poetry (ADR-014). Use `uv build` / `uv publish`. |

---

## Provenance
- Verified end-to-end 2026-06-04 (TestPyPI rehearsal → real publish of `0.1.0` → clean-room install).
- Build tooling: **ADR-014** (hatchling + uv). Python-3.11 cap: risk **C-36**. Both in this repo's governance — if they change, this guide should change with them.
