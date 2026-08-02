
# Class Intent Contract: PredictionLoader Protocol & Loader Registry

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-002 (Topology — Ingestion is Layer 2), ADR-003 (Declarations over inference), ADR-006 (Intent Contracts), ADR-008 (Observability — fail loud), ADR-009 (Boundary contracts — §1b ingestion conformance gate), ADR-012 (Prediction Data Ingestion)

---

> **Scope note.** This contract covers an *interface* (`PredictionLoader`, a `typing.Protocol`) and *module-level functions* (`register_loader`, `get_loader`, and the public `load_predictions` / `load_prediction_sequence` entry points) rather than a single stateful class. It is included for full coverage of the Ingestion-layer dispatch surface (issue #77 decision, 2026-06-04). The concrete loaders have their own contracts: `cic_prediction_frame_loader.md`, `cic_dataframe_loader.md`.

Sources: `views_reporting/loaders/_protocol.py`, `_registry.py`, `__init__.py`.

---

## 1. Purpose

> Define the loader interface and the declared-format dispatch mechanism that selects a loader at runtime.

The `PredictionLoader` Protocol is the contract every format loader satisfies. The registry maps a declared `prediction_format` string to a loader class; `load_predictions` / `load_prediction_sequence` are the single public entry points the rest of views-reporting calls. Together they make storage format a one-line, swappable, fail-loud decision.

---

## 2. Non-Goals (Explicit Exclusions)

- Does **not** read any file itself — concrete loaders do the I/O.
- Does **not** infer format from path or extension — the format is passed in (ADR-003).
- Does **not** auto-discover or auto-register loaders — registration is explicit at import.
- Does **not** convert, compute, render, or assemble.

---

## 3. Responsibilities and Guarantees

- **Interface contract (`PredictionLoader`).** Any loader provides `load_single_origin(path, level, targets) -> dict[str, PredictionFrame]` and `load_multi_origin(paths, level, targets) -> list[dict[str, PredictionFrame]]` (epic #137, #138 — frame-native; a frame is single-target so the return is keyed by target). The return is typed (not `Any`) so call sites and substitutes are statically checkable (LSP/ISP).
- **Registration (`register_loader(format_name, loader_cls)`).** Records a format→loader mapping. **Duplicate registration raises `ValueError`** — no silent overwrite (ADR-008).
- **Lookup (`get_loader(format_name)`).** Returns an instance of the registered loader. **Unknown format raises `ValueError` listing the registered formats** (ADR-008 fail-loud, ADR-003 no inference).
- **Open/Closed extension.** A new storage format is added by writing a loader that satisfies the Protocol and calling `register_loader("name", Loader)` — with no edits to existing loaders, the registry, or callers.
- **Built-in registrations.** On import of `views_reporting.loaders`, `"dataframe" → DataFrameLoader` and `"prediction_frame" → PredictionFrameLoader` are registered.
- **Ingestion conformance gate (ADR-009 §1b; epic #137 S5, #140).** Every frame a loader produces is passed through `views_frames.conformance.assert_frame_contract` (via `loaders._constants.assert_conformant`) before it leaves the Ingestion layer — float32 values + explicit sample axis, complete integer `time`/`unit` identifiers of length `n_rows`, save/load round-trip. A structural violation **fails loud** (`AssertionError`) at the boundary rather than propagating a malformed frame. The governed `CONFORMANCE_FLOOR` is pinned (`EXPECTED_CONFORMANCE_FLOOR`) so a leaf bump is caught. `assert_conformant` also adds the **values-completeness** half of register C-111: a wholly-NaN frame raises `ValueError` (no usable predictions — ADR-008 fail-loud) and partial NaN is logged (legitimate sparse cells are not rejected). The remaining residual is expected time/entity **coverage**, deferred to the C-108 Phase-3 typed input contract.

---

## 4. Inputs and Assumptions

- `register_loader(format_name: str, loader_cls: type[PredictionLoader])` — `loader_cls` is expected to satisfy the Protocol (structural typing; not enforced at runtime).
- `get_loader(format_name: str)` / `load_predictions(prediction_format, path, level, targets)` — `prediction_format` must be a registered key.
- Assumes registration happens at import time (the `views_reporting/loaders/__init__.py` side effects) before any lookup.

---

## 5. Outputs and Side Effects

- `register_loader` → `None`; **mutates the module-level `_LOADER_REGISTRY` dict** (the one piece of global mutable state in the package; populated at import).
- `get_loader` → an instantiated loader.
- `load_predictions` → `dict[str, PredictionFrame]`; `load_prediction_sequence` → a list of such dicts (one per origin).
- No file or network I/O at this layer; the concrete loader performs that.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| Registering an already-registered format | `ValueError` naming both classes | `_registry.py` `register_loader` |
| Looking up / loading an unregistered format | `ValueError` listing registered formats | `_registry.py` `get_loader` |
| Ingested frame violates the structural contract | `AssertionError` (fails loud at the boundary) | `_constants.py` `assert_conformant` |
| Ingested frame is wholly NaN (no usable predictions) | `ValueError` (C-111); partial NaN is logged, not raised | `_constants.py` `assert_conformant` |
| A registered class not satisfying the Protocol | Not checked at registration; surfaces as `AttributeError` when its methods are called | structural-typing limitation |

Must never fail silently: unknown and duplicate formats are loud. No format is ever guessed.

---

## 7. Boundaries and Interactions

- **`_protocol.py`** imports `views_frames.PredictionFrame` only under `TYPE_CHECKING` — the Protocol module stays import-light.
- **`_registry.py`** references the Protocol only under `TYPE_CHECKING`; at runtime it holds and returns classes/instances generically.
- **Must not depend on:** Computation, Rendering, or Composition (Layers 3–5).
- Concrete loaders (`DataFrameLoader`, `PredictionFrameLoader`) depend on this interface, not vice versa.

---

## 8. Examples of Correct Usage

```python
from views_reporting.loaders import load_predictions, register_loader

# Normal use — declared format dispatch
frames = load_predictions("dataframe", path, "cm", ["lr_ged_sb"])  # {target -> PredictionFrame}

# Extending with a new format (OCP) — no edits to existing code
class ArrowLoader:
    def load_single_origin(self, path, level, targets): ...
    def load_multi_origin(self, paths, level, targets): ...

register_loader("arrow", ArrowLoader)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: re-registering a built-in format — raises ValueError, by design.
register_loader("dataframe", MyOtherLoader)
```

```python
# WRONG: requesting an unregistered/typo'd format — raises ValueError
# listing the registered formats. Format is never inferred or defaulted.
load_predictions("parquet", path, "cm", ["lr_ged_sb"])   # it's "dataframe"
```

---

## 10. Test Alignment

- **Green/Red:** `tests/test_loaders.py::TestRegistry` — built-in formats registered; `get_loader` returns correct types; unknown format raises and lists registered formats; duplicate registration raises.
- **Beige:** `tests/test_loaders.py::TestPublicAPI` — `load_predictions` / `load_prediction_sequence` dispatch to the right loader for each declared format.
- Invariants tests must protect: fail-loud on unknown and duplicate formats; the typed Protocol return.

---

## 11. Evolution Notes

- The registry is the OCP seam for future formats (e.g., Arrow, remote/Appwrite sources). New formats should arrive as new loaders + a `register_loader` call, never as a branch inside an existing loader.
- Runtime Protocol conformance is intentionally unchecked (structural typing); if mis-registration becomes a real risk, add a registration-time `isinstance`/attribute check.

---

## End of Contract

This document defines the **intended meaning** of the `PredictionLoader` Protocol and the loader registry.

Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
