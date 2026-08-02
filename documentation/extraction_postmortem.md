# Extraction Post-Mortem

> **HISTORICAL DOCUMENT** — a point-in-time record of the extraction era. Counts, modules and risks described here reflect that moment, not the current repository.

**Period:** 2026-05-27 to 2026-06-01 (5 days)
**Scope:** Extract ~8,285 LOC from views-pipeline-core into views-reporting, bring to operational readiness

---

## Timeline

| Date | What happened |
|------|---------------|
| May 27 | Architectural investigation completed. ADR-054 written. Package skeleton created (PR 0). |
| May 28 | PRs 1–5 landed: transformations, statistics, visualizations, mapping, reports. Governance infrastructure bootstrapped (12 ADRs, risk register). |
| May 29 | PRs 7–8 landed: reconciliation, god class surgery on `handlers.py` (2,294 → 946 LOC). C-01 thread safety bug found and fixed. 8 CICs written. Test coverage built from 13 to 158 tests across 8 PRs. C-04 and C-05 fixed. Tech debt cleanup on statistics.py. |
| May 30 | ADR-011 decision (data on original scale). Three expert-code-reviews mapped the HDI/MAP flow, reconciliation chain, and governance hierarchy. Registered C-10 through C-15 and D-06 through D-10. |
| May 31 | C-10 fixed (transform-detection deleted per ADR-011). Remaining register items resolved (C-11, C-13, C-14, C-15, D-06). Infrastructure sprint: README, CI, HTML escaping (C-17, C-18, C-19). Falsification campaigns on operational readiness. Test count reached 161 in full environment. |
| Jun 1 | README aligned to platform style. Discoverability audit (C-20, C-21). Module docstrings added across 24 files. Register brought to 21/21 resolved, 0 open. |

**Final stats:** 66 commits, 20 merged PRs, 7,318 LOC of source, 2,043 LOC of tests, 33 governance documents, 109 tests in base environment (161 in full).

---

## What Went Well

### The investigation-first approach saved us

The architectural investigation in pipeline-core mapped every file, every
import chain, every consumer, every method in the god class — before any
code moved. This meant the extraction PR sequence was mechanical. We knew
exactly what to move, in what order, and where the risks were. PR 8 (the
god class surgery) was flagged as high-risk from day one, and it was —
but we knew that going in.

### WET-before-DRY was the right call

Moving code as exact copies, without simultaneous refactoring, kept each
PR reviewable and individually revertible. The temptation to "fix it while
we're moving it" was real — statistics.py had inline test methods, dead
code, wrong signs, hardcoded offsets — but mixing extraction with
remediation would have made every PR a gamble instead of a mechanical step.

The refactoring happened afterward, on stable ground, with tests in place.

### The risk register drove prioritization

Starting with repo-assimilation → register-risk on the freshly extracted
code immediately surfaced 19 concerns, tiered by severity. This gave us
a prioritized punch list instead of an undifferentiated backlog. C-01
(thread-unsafe singleton, Tier 1) was fixed before anything else. C-10
(transform detection, Tier 1) waited until ADR-011 provided the
architectural justification for deletion rather than repair.

The register also prevented scope creep — disagreements (D-07, D-08, D-09)
were recorded and deferred rather than rat-holed on.

### Falsification caught real problems

Three falsification campaigns found issues that tests-pass-and-lint-clean
would have missed:

- **C-01:** The singleton PosteriorDistributionAnalyzer was 20% corrupted
  under concurrent joblib threads. The falsification empirically demonstrated
  the corruption rate before the fix, and 0/1000 after.
- **C-16:** ForecastReconciler's sum constraint fails silently on
  all-negative grids. Found by a boundary probe nobody would have written
  as a unit test.
- **C-20/C-21:** The discoverability audit proved that zero module
  docstrings existed across the entire codebase — a blind spot that
  code review and test coverage cannot see.

### The governance infrastructure paid for itself immediately

Writing CICs before tests meant the tests were derived from contracts
rather than from implementation details. When C-01 was fixed, the CIC
told us exactly what `analyze()` must guarantee, which made the test
suite targetable. When C-10 was resolved, the CIC for
DatasetTransformationModule already documented it as legacy.

---

## What Surprised Us

### C-01 was a silent data corruption bug hiding in plain sight

The module-level `_analyzer = PosteriorDistributionAnalyzer()` singleton
in `dataset_statistics.py` was shared across joblib threads during
`calculate_map()`. Each thread called `_analyzer.analyze()`, which wrote
to `self.summary`, `self.samples`, `self.credible_masses` — instance
state mutated concurrently with no synchronization.

This wasn't a theoretical race condition. The falsification probe showed
**20% of results were corrupted** in a 1,000-iteration concurrent test.
One in five MAP estimates was wrong. Silently.

The fix was straightforward — make `_compute_summary()` a pure function
that takes parameters instead of reading `self.*`, then instantiate a
fresh analyzer per call. But the bug had been shipping in pipeline-core
for an unknown duration.

**Lesson:** Module-level mutable singletons in a library that uses joblib
are a Tier 1 risk by default. The assimilation should have flagged this
pattern immediately.

### C-02 was caught before it shipped, but barely

`dataset_export.py` line 69 had `np.exp(100)` where it should have been
`np.exp(-100)` — reversing an `ln(x + 100)` transform. `np.exp(100)` is
~2.7 × 10^43. This would have produced astronomically wrong forecasts
for any `lx`-transformed feature.

It was caught during the first code review, before the initial commit to
views-reporting. But it existed in pipeline-core's codebase. The fact
that no production model currently uses `lx` transforms is why nobody
had noticed — the code path was dead in practice but live in the API.

**Lesson:** Dead code paths with mathematical operations are Tier 1 risks.
They don't trigger test failures because nobody tests them, and they
don't trigger runtime errors because nobody calls them — until someone does.

### The transform-detection code was dead across all 56+ models

When we investigated C-10 (transform-detection logic that sniffed column
prefixes like `ln_`, `lx_`), we checked every production model. All 56+
models use `lr_` targets. The `ln` and `lx` branches in `to_reconciler()`
and `reconcile_pg_dataset()` had zero production consumers. The code was
inferring transformations from naming conventions that the platform had
already moved past.

This led directly to ADR-011 — the decision that views-reporting expects
data on its original measurement scale, period. The deletion of the
transform-detection branches was not a refactor but a policy decision:
this repo will never infer semantics from column names.

**Lesson:** "Clever" code that infers behavior from naming conventions
accumulates without anyone noticing it's never exercised. Deletion
requires an architectural decision, not just a coverage report.

### handlers.py was worse than the investigation predicted

The investigation estimated ~1,342 LOC of misplaced methods in
`handlers.py`. The actual extraction (PR 8) confirmed this, but the
difficulty was higher than expected. The entity metadata methods had
hidden dependencies on VIEWSER network calls via
`_build_entity_metadata_cache()`, which meant the extracted functions
needed idempotent caching strategies that didn't exist in the original
code. The integration tests needed to pre-populate these caches to avoid
network calls and CUDA fork issues in ProcessPoolExecutor workers.

**Lesson:** LOC counts understate extraction difficulty. Method-level
coupling to hidden side effects (network calls, global state, device
selection) is where the real complexity lives.

### The repo had zero docstrings

After all the governance work — 12 ADRs, 10 CICs, a risk register with
21 entries, 161 tests — a falsification audit on "is this repo intuitive
for a newcomer" found that zero of 9 `__init__.py` files and zero of 14
core `.py` files had module docstrings. The top-level `__init__.py` was
literally empty (0 bytes).

The repo had excellent structural documentation (README, ADRs, CICs) but
zero semantic documentation at the code level. A newcomer leaving the
README entered a documentation void.

**Lesson:** Governance artifacts and code-level discoverability are
orthogonal. You can have a perfect risk register and a completely mute
codebase. Test for both.

---

## What We'd Do Differently

### Write module docstrings during extraction, not after

Every PR that moved a file should have added a one-line module docstring
at the top. It takes 10 seconds per file and would have prevented C-20
entirely. Instead we moved 24 files with zero docstrings and didn't
notice for 4 days.

### Run the discoverability falsification earlier

The "does this repo scream its domain" probe should have been one of the
first falsification campaigns, not the last. Structural readiness
(tests pass, lint clean, register empty) is not the same as human
readiness (can a person understand this). We spent 4 days building a
repo that was technically complete but silent about what it does.

### Don't defer the CI setup

CI (C-18) was set up on day 4. Every PR before that was merged with
manual lint and test runs. Nothing broke, but that was luck compounded
36 times. CI should have been PR 0.5 — right after the skeleton, before
any code landed.

### Flag module-level mutable state as Tier 1 during assimilation

The assimilation protocol should automatically flag any module-level
mutable object (`_analyzer = SomeClass()`) in a library that uses
concurrent execution (joblib, multiprocessing, threading) as a Tier 1
concern. C-01 was the most dangerous bug in the extraction and it was
hiding behind a one-line pattern that looks completely normal in
sequential code.

### Track the "dead code but live API" pattern

C-02 (wrong sign) and C-10 (dead transform branches) were both in code
paths with zero production consumers but a fully public API. The
assimilation should have a specific check: "is this public API exercised
by any known consumer?" Code that is public, untested, and uncalled is
either dead (delete it) or a trap (test it). There is no safe middle
ground.

---

## Open Items Carried Forward

| Item | Status | Notes |
|------|--------|-------|
| D-07 | Open disagreement | Should PlotDistribution compute its own statistics or receive pre-computed data? Deferred until a real use case for computation-free rendering appears. |
| D-08 | Open disagreement | Should reconciliation workers receive DataFrames or pre-extracted tensors? Partially derisked by C-10 resolution. |
| D-09 | Open disagreement | Should `reconcile()` return a value or mutate in-place? Current API does both. Needs a decision. |
| Re-export shims | Active in pipeline-core | 7 `__init__.py` files in pipeline-core have `try/except ImportError` shims. Remove after downstream repos update imports. |
| `DatasetTransformationModule` | Legacy | Entire module marked legacy per ADR-011. No production consumer. Candidate for eventual removal. |
