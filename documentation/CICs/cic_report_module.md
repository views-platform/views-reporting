
# Class Intent Contract: ReportModule

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** none  

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

- **Content accumulation.** Maintains an ordered `self.content` list (line 39) of HTML strings. Each `add_*` method appends one or more entries.
- **VIEWS branding.** On construction, automatically embeds the VIEWS header image from `views_reporting/assets/headers/views_header.png` as a base64-encoded `<img>` tag (lines 41-55).
- **Heading levels.** `add_heading()` (line 58) supports levels 1-3 with distinct Tailwind CSS classes and optional hyperlinks.
- **Table auto-splitting.** `add_table()` (line 372) automatically splits DataFrames exceeding `TABLE_SPLIT_THRESHOLD` (8 rows) or `TABLE_SPLIT_THRESHOLD_COLS` (6 columns) into multiple side-by-side or stacked tables.
- **Image embedding.** `add_image()` (line 292) accepts file paths or Matplotlib `Figure`/`Axes` objects, converts to base64, and embeds inline. No external file references.
- **Plotly.js loading.** `add_html()` (line 127) inserts the Plotly.js CDN script tag on first call (`_plotly_js_loaded` flag, line 150). The script is prepended to `self.content[0]`.
- **Markdown rendering.** `add_markdown()` (line 181) converts Markdown to HTML using the `markdown` package with extensions (tables, fenced code, nl2br, sane lists). Falls back to plain text if the package is unavailable.
- **Grid layout.** `start_grid()` / `add_to_grid()` / `end_grid()` (lines 707, 731, 768) provide a responsive CSS grid container.
- **Standalone export.** `export_as_html()` (line 807) wraps all accumulated content in a full HTML document with Tailwind CSS from CDN (via `views_reporting.reports.styles.tailwind.get_css()`), a footer with timestamp and `PipelineConfig.current_version`, and responsive viewport meta tags.

---

## 4. Inputs and Assumptions

- **No constructor arguments.** `__init__()` takes no parameters (line 27).
- **Header image must exist** at `views_reporting/assets/headers/views_header.png`. If missing, `add_image()` raises `FileNotFoundError` during construction.
- **`PipelineConfig.current_version`** (from `views_pipeline_core.configs.pipeline`) must be accessible at export time. It is used in the footer (line 841).
- **`add_table(data=...)`** expects either a `pd.DataFrame` or `dict`. Any other type raises `TypeError` (line 431).
- **`add_image(image=...)`** expects a `str` (file path), `plt.Figure`, or `plt.Axes`. Any other type raises `ValueError` (line 351).
- **`add_markdown()`** requires the `markdown` package to be installed for full functionality. It degrades gracefully if unavailable (line 229).
- **Grid operations** assume `start_grid()` is called before `add_to_grid()` and `end_grid()` is called to close the container. Missing `end_grid()` breaks HTML structure.
- **Tailwind CSS** and **Plotly.js** are loaded from CDN, so the exported HTML requires internet access to render correctly on first load (unless Tailwind's CDN script caches locally).

---

## 5. Outputs and Side Effects

- **`export_as_html(file_path)`** writes a single UTF-8 HTML file to the given path. The file is fully self-contained except for CDN dependencies (Tailwind CSS, Plotly.js).
- **`add_table(as_html=True)`** returns an HTML string instead of appending to the content list.
- **`add_image(as_html=True)`** returns an HTML string instead of appending to the content list.
- **Side effects:** Matplotlib figures passed to `add_image()` are closed via `plt.close(fig)` (line 339). The `_plotly_js_loaded` flag is mutated on first `add_html()` call. File I/O occurs only in `export_as_html()` and `add_image()` (when reading image files).

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
| `PipelineConfig.current_version` inaccessible | `AttributeError` at export time | `export_as_html`, line 841 |

There is no validation for grid nesting correctness. Calling `end_grid()` without `start_grid()` or calling `add_to_grid()` outside a grid context will produce malformed HTML without error.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_pipeline_core.configs.pipeline.PipelineConfig` -- `.current_version` for footer version stamp
  - `views_reporting.reports.styles.tailwind` -- `get_css()` for Tailwind CSS configuration and custom styles
  - `matplotlib.pyplot` -- for figure-to-image conversion
  - `pandas` -- for DataFrame table rendering (`.style.to_html()`)
  - `markdown` (optional) -- for Markdown-to-HTML conversion
  - CDN: `https://cdn.tailwindcss.com` (Tailwind CSS), `https://cdn.plot.ly/plotly-latest.min.js` (Plotly.js)
- **Must not depend on:**
  - `views_reporting.statistics` (no statistical computation)
  - `views_reporting.mapping` (no geographic rendering)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - Any specific dataset type -- this class is data-agnostic
- **Trusts:**
  - That HTML strings passed to `add_html()` are valid and safe (no sanitization is performed)
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

**No tests exist for ReportModule.** The existing test files (`tests/test_c01_thread_safety.py`, `tests/test_c01_layer1_specification.py`) cover `PosteriorDistributionAnalyzer`, not this class.

Tests that should exist:
- **Green:** Verify that `export_as_html()` produces valid HTML with expected structure (doctype, head, body, Tailwind script tag, content in order).
- **Green:** Verify that `add_table()` splits DataFrames correctly when exceeding row/column thresholds.
- **Green:** Verify that `add_image()` with a Matplotlib figure embeds a base64 PNG.
- **Beige:** Verify full report workflow: heading + paragraph + table + image + export.
- **Red:** Verify `FileNotFoundError` for missing image paths, `TypeError` for invalid table data, `ValueError` for unsupported image types.

---

## 11. Evolution Notes

### Known Deviations

1. **CDN dependency in "standalone" HTML.** `export_as_html()` is described as standalone, but the output requires internet access for Tailwind CSS (`https://cdn.tailwindcss.com`) and Plotly.js (`https://cdn.plot.ly/plotly-latest.min.js`). True offline operation is not supported.

2. **`PipelineConfig.current_version` coupling.** The footer (line 841) references `PipelineConfig.current_version` from `views-pipeline-core`. If this attribute changes or becomes unavailable, export will fail with `AttributeError`. This is a cross-package coupling to a configuration singleton.

3. **No grid nesting validation.** There is no state tracking for whether a grid is currently open. Calling `end_grid()` without `start_grid()`, or `add_to_grid()` outside a grid, produces malformed HTML silently.

4. **Plotly.js script insertion position.** On first `add_html()` call, the Plotly CDN script is inserted at `self.content[0]` via `self.content.insert(0, ...)` (line 151). This pushes the VIEWS header image (added during `__init__`) to index 1. If `add_html()` is called before any other content is added, the script tag will precede the header in the rendered output, which is likely the intended behavior but is position-dependent.

5. **`add_image()` does not validate image format.** The method uses `path.suffix[1:]` as the MIME type (line 349), which will produce incorrect MIME types for unusual file extensions (e.g., `.jpeg` instead of `.jpg` works, but `.svg` would embed as `image/svg` instead of `image/svg+xml`).

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
