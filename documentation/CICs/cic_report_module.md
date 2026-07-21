
# Class Intent Contract: ReportModule

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-06-26  
**Related ADRs:** none (provenance footer addresses register C-34)  

---

## 1. Purpose

> **What is this class for?**

ReportModule is an HTML report builder that accumulates styled content (headings, paragraphs, tables, images, interactive visualizations, Markdown) into a list of HTML strings and exports the result as a self-contained standalone HTML file with Tailwind CSS styling and VIEWS branding.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute any data, statistics, or predictions; it only renders pre-computed results.
- This class does **not** produce PDF, DOCX, or any format other than HTML.
- This class does **not** manage templates or multi-page reports; it produces a single linear HTML document.
- This class does **not** serve the report over HTTP or provide a preview server.
- This class does **not** validate the semantic correctness of content; it renders whatever strings are passed to it.

---

## 3. Responsibilities and Guarantees

- **Content accumulation.** Maintains an ordered `self.content` list of HTML strings. Each `add_*` method appends one or more entries.
- **VIEWS branding.** On construction, automatically embeds the VIEWS header image from `views_reporting/assets/headers/views_header.png` as a base64-encoded `<img>` tag.
- **Heading levels.** `add_heading()` supports levels 1-3 with distinct Tailwind CSS classes and optional hyperlinks.
- **Table auto-splitting.** `add_table()` automatically splits DataFrames exceeding `TABLE_SPLIT_THRESHOLD` (8 rows) or `TABLE_SPLIT_THRESHOLD_COLS` (6 columns) into multiple side-by-side or stacked tables.
- **Image embedding.** `add_image()` accepts file paths or Matplotlib `Figure`/`Axes` objects, converts to base64, and embeds inline. No external file references.
- **Plotly.js loading.** The report owns the SINGLE inlined plotly.js copy (#258, register C-28 — inlined via `plotly.offline.get_plotlyjs()`, never a CDN reference). Injection is CONTENT-AWARE (`_ensure_plotly_js`): the library is inserted at the top the first time html containing `Plotly.newPlot` arrives — via `add_html` OR `add_to_grid` — so image-only reports never carry the ~4 MB library. Figures arrive as fragments with `include_plotlyjs=False` (`mapping.py`, `historical.py`); a figure arriving with its OWN inlined library logs a loud duplication warning.
- **Markdown rendering.** `add_markdown()` converts Markdown to HTML using the `markdown` package with extensions (tables, fenced code, nl2br, sane lists). Falls back to plain text if the package is unavailable.
- **Grid layout.** `start_grid()` / `add_to_grid()` / `end_grid()` (lines 707, 731, 768) provide a responsive CSS grid container.
- **Standalone export.** `export_as_html()` wraps all accumulated content in a full HTML document with **inlined, vendored Tailwind CSS** (via `get_css()`, which reads `assets/tailwind.css` — no CDN, register C-28), a provenance footer (see below), a machine-readable provenance block, and responsive viewport meta tags. The output renders **fully offline**.
- **Key-value lists.** `add_key_value_list(data, title=None)` renders a dict as a styled definition list (escaped text sink, same invariant as the other text methods).
- **Machine-readable provenance (register C-188).** `export_as_html()` embeds a `<script type="application/json" id="views-report-provenance">` block carrying the report's identity (build info, pipeline version, timestamp, the provenance dict) as parseable data — `<` escaped to prevent `</script>` breakout — so a future report catalog can index a report without scraping rendered HTML.
- **Provenance footer (register C-34).** `export_as_html()` *always* renders a footer carrying, at minimum, a generation timestamp and a build line — `views-reporting vX (git_sha) · views-frames vY · views-pipeline-core vZ` — so every delivered report is self-identifying. `add_footer(text=None, *, provenance=None)` optionally adds a free-text line (`text`, escaped) and a structured **provenance block** (`provenance`, a `dict`): each non-`None` value is rendered as an escaped `key: value` row (`None` values omitted). The positional `text` form is back-compatible. Templates set provenance: the forecast template stamps model/target/run_type/level/targets/prediction_path; the evaluation template stamps model/target/run_type/eval_target/level + the `run_id` and the frame provenance (`data_version`, `scoring_code_version`) from the `MetricFrame` (+ constituent models for ensembles). The eval footer carries **no** WandB run URL or owner — the file source supplies neither.
- **Build provenance.** Module-level `get_build_info() -> dict` returns `{views_reporting, views_frames, git_sha}` — versions via `importlib.metadata.version(...)` (missing package → `"unknown"`), git short SHA via `subprocess` `git rev-parse --short HEAD` (cwd = package dir, 5s timeout). **Never raises**: any subprocess failure yields `git_sha="unavailable"`.

---

## 4. Inputs and Assumptions

- **No constructor arguments.** `__init__()` takes no parameters.
- **Header image must exist** at `views_reporting/assets/headers/views_header.png`. If missing, `add_image()` raises `FileNotFoundError` during construction.
- **`PipelineConfig.current_version`** (from `views_pipeline_core.configs.pipeline`) is read into the footer build line via `getattr(..., "unknown")` — accessible is preferred, but absence degrades to `"unknown"` rather than failing the export.
- **`add_table(data=...)`** expects either a `pd.DataFrame` or `dict`. Any other type raises `TypeError`.
- **`add_image(image=...)`** expects a `str` (file path), `plt.Figure`, or `plt.Axes`. Any other type raises `ValueError`.
- **`add_markdown()`** requires the `markdown` package to be installed for full functionality. It degrades gracefully if unavailable.
- **Grid operations** assume `start_grid()` is called before `add_to_grid()` and `end_grid()` is called to close the container. Missing `end_grid()` breaks HTML structure.
- **Tailwind CSS is vendored and inlined** (`assets/tailwind.css`, shipped in the wheel) and **Plotly.js is inlined by each figure**, so the exported HTML renders **fully offline** — no CDN, no network (register C-28).

---

## 5. Outputs and Side Effects

- **`export_as_html(file_path)`** writes a single UTF-8 HTML file to the given path. The file is **fully self-contained** (Tailwind inlined, Plotly inlined per-figure) — no CDN dependency (register C-28).
- **`add_table(as_html=True)`** returns an HTML string instead of appending to the content list.
- **`add_image(as_html=True)`** returns an HTML string instead of appending to the content list.
- **Side effects:** Matplotlib figures passed to `add_image()` are closed via `plt.close(fig)`. The `_plotly_js_loaded` flag is mutated on first `add_html()` call. File I/O occurs only in `export_as_html()` and `add_image()` (when reading image files).

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| Header image missing at construction | `FileNotFoundError` raised | `__init__` -> `add_image`, line 345 |
| `add_image()` with nonexistent file path | `FileNotFoundError` raised | `add_image`, line 346 |
| `add_image()` with unsupported type | `ValueError` raised | `add_image`, line 351 |
| `add_table()` with non-DataFrame/non-dict | `TypeError` raised | `add_table`, line 431 |
| `markdown` package not installed | Falls back to plain text with warning paragraph | `add_markdown`, lines 229-233 |
| `end_grid()` not called after `start_grid()` | Broken HTML structure (unclosed `<div>`) | No validation |
| `PipelineConfig.current_version` inaccessible | Degrades to `"unknown"` in the build line (no raise) | `export_as_html` (`getattr(..., "unknown")`) |
| `views-reporting` / `views-frames` not installed | Version degrades to `"unknown"` in the build line | `get_build_info` (`PackageNotFoundError`) |
| `git rev-parse` fails (no repo / git absent / timeout) | `git_sha` degrades to `"unavailable"` (no raise) | `get_build_info` (`OSError`/`SubprocessError`) |

There is no validation for grid nesting correctness. Calling `end_grid()` without `start_grid()` or calling `add_to_grid()` outside a grid context will produce malformed HTML without error.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_pipeline_core.configs.pipeline.PipelineConfig` -- `.current_version` for footer version stamp
  - `views_reporting.reports.styles.tailwind` -- `get_css()` for Tailwind CSS configuration and custom styles
  - `matplotlib.pyplot` -- for figure-to-image conversion
  - `pandas` -- for DataFrame table rendering (`.style.to_html()`)
  - `markdown` (optional) -- for Markdown-to-HTML conversion
  - `views_reporting/reports/assets/tailwind.css` — the vendored, prebuilt Tailwind CSS (shipped in the wheel; no CDN)
- **Must not depend on:**
  - `views_reporting.statistics` (no statistical computation)
  - `views_reporting.mapping` (no geographic rendering)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - Any specific dataset type -- this class is data-agnostic
- **Trusts:**
  - That HTML strings passed to `add_html()` are valid and safe (no sanitization is performed). This is the builder's **one documented exception** to the `html.escape()` text invariant (register C-117, Resolved): it exists to carry trusted, code-generated figure HTML. As a misuse signal, a markup-less input (no `<`) logs a warning — legitimate figure HTML always contains markup.
  - That `get_css()` returns valid HTML `<style>` and `<script>` tags

---

## 8. Examples of Correct Usage

```python
from views_reporting.reports import ReportModule
import pandas as pd

report = ReportModule()
report.add_heading("Model Evaluation Report", level=1)
report.add_paragraph("This report summarizes the forecast evaluation results.")

# Add a table
df = pd.DataFrame({'Metric': ['MSE', 'MAE'], 'Value': [0.045, 0.123]})
report.add_table(df, header="Evaluation Metrics")

# Add a Plotly visualization
report.add_html(plotly_fig.to_html(), height=500)

# Add an image from matplotlib
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
report.add_image(fig, caption="Sample plot")

# Export
report.export_as_html("output/report.html")
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Forgetting to close grid layout
report.start_grid(columns=3)
report.add_to_grid(table_html)
# Missing report.end_grid() -- HTML will be malformed

# WRONG: Passing unsupported type to add_table
report.add_table([1, 2, 3])  # Raises TypeError, must be DataFrame or dict

# WRONG: Passing unsupported type to add_image
report.add_image(42)  # Raises ValueError

# WRONG: Using add_to_grid outside of a grid context
report.add_to_grid(table_html)  # Produces orphaned <div> -- no error raised
```

---

## 10. Test Alignment

`tests/test_reports.py` covers ReportModule: content accumulation + escaping, table auto-splitting, the export workflow, the provenance footer, and `get_build_info`. The end-to-end footer wiring is covered by `tests/test_e2e_synthetic.py` (forecast) and `tests/test_e2e_eval_report.py` (evaluation).

Provenance-footer coverage (`TestProvenanceFooter`, C-34):
- **Green:** `get_build_info()` returns the `{views_reporting, views_frames, git_sha}` shape with non-empty strings.
- **Green:** a git failure (monkeypatched `subprocess.run`) degrades `git_sha` to `"unavailable"` — never raises.
- **Green:** the build/version stamp renders even with no `add_footer` call; provenance dict fields render, are HTML-escaped, and `None` values are omitted; positional `text` stays back-compatible.
- **Beige (e2e):** the forecast report carries the build line + `run_type`; the eval report carries the build line + `run_id` + frame provenance (`data_version`, `scoring_code_version`) + constituent models (no WandB url/owner).

Further coverage worth adding: table-splitting thresholds and `add_image` base64 embedding.

---

## 11. Evolution Notes

### Known Deviations

1. **CDN dependency in "standalone" HTML — RESOLVED (#132, register C-28).** Exported HTML is now genuinely standalone: Tailwind is vendored + inlined (`assets/tailwind.css`, generated by `scripts/build_tailwind_css.sh`, shipped in the wheel) and Plotly is inlined per-figure. True offline operation is supported and guarded by `tests/test_offline_assets.py`.

2. **`PipelineConfig.current_version` coupling.** The footer build line references `PipelineConfig.current_version` from `views-pipeline-core`. As of the C-34 provenance footer this is read via `getattr(..., "unknown")`, so an inaccessible attribute degrades to `"unknown"` rather than raising `AttributeError` (it previously raised). The cross-package coupling to a configuration singleton remains.

3. **No grid nesting validation.** There is no state tracking for whether a grid is currently open. Calling `end_grid()` without `start_grid()`, or `add_to_grid()` outside a grid, produces malformed HTML silently.

4. **Plotly.js script insertion position.** The first PLOTLY-containing content (`_ensure_plotly_js`, keyed on `Plotly.newPlot`) inserts the single library `<script>` at `self.content[0]` (#258 — figures ship without their own copy; image-only reports get no library). This pushes the VIEWS header image (added during `__init__`) to index 1. If `add_html()` is called before any other content is added, the script tag will precede the header in the rendered output, which is likely the intended behavior but is position-dependent.

5. **`add_image()` does not validate image format.** The method uses `path.suffix[1:]` as the MIME type, which will produce incorrect MIME types for unusual file extensions (e.g., `.jpeg` instead of `.jpg` works, but `.svg` would embed as `image/svg` instead of `image/svg+xml`).

6. **Header image manipulation uses fragile string replacement.** Lines 45-55 modify the header image's HTML by replacing CSS class strings. This is brittle and will break silently if the `add_image()` output format changes.

### Stability

- The content accumulation + export pattern is stable.
- The Tailwind CSS styling system (via `get_css()`) is stable.
- The table splitting thresholds (`TABLE_SPLIT_THRESHOLD=8`, `TABLE_SPLIT_THRESHOLD_COLS=6`) are class-level constants and can be overridden per-call.

### Expected Changes

- CDN dependencies may need to be replaced with bundled assets for true offline support.
- Grid nesting validation could be added to prevent malformed HTML.
- The `PipelineConfig` coupling should be evaluated for whether it belongs in this package.

---

## End of Contract

This document defines the **intended meaning** of `ReportModule`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
