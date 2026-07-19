# Visualizations (views-reporting, Layer 4 — Rendering)

Interactive Plotly visualizations for `views_frames.PredictionFrame` data.

> **The contracts live in the CICs, not here** — this README is a signpost only
> (parallel API docs drift; see register C-210). Authoritative:
> `documentation/CICs/cic_historical_line_graph.md` and
> `documentation/CICs/cic_plot_distribution.md`.

## Classes

- **`HistoricalLineGraph(historical_frame=None, forecast_frame=None, level=...)`** —
  historical-vs-forecast line graphs (CM): HDI bands per credible level with a
  legend selector, MAP summary lines (views-frames tower, ADR-019), entity
  dropdown, mode-aware forecast-start cutoff. Sample frames never cross into a
  pandas line (ADR-020): `_pred_df` enforces S == 1; the all-HDI-failed
  fallback renders the MAP line or visible absence — never an arbitrary draw.
- **`PlotDistribution(frame=...)`** — posterior histograms/HDI shading from the
  pooled numpy samples (the one sanctioned all-samples-in-memory consumer;
  never touches pandas).

## Where things come from

Entity labels come from the bundled metadata accessors
(`views_reporting.metadata`, offline — C-22); MAP/HDI numbers from
`views_reporting.statistics` (the views-frames tower). Config (HDI levels)
is injected by the report templates (ADR-016) — nothing here reads config.

Tests: `tests/test_historical_line_graph.py`, `tests/test_plot_distribution.py`,
`tests/test_sample_boundary.py`, plus the characterization pins.
