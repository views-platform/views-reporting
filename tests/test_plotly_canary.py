"""Plotly probe-string canary + provenance stamp (register C-214, #265).

The #258/#259 single-plotly.js architecture keys on strings that are
plotly.py serializer INTERNALS, not contracts: the ``plotly-graph-div``
fragment class + ``Plotly.newPlot`` bootstrap call (injection probes) and the
``* plotly.js v`` bundle banner (double-inclusion warning, e2e single-library
assertions, provenance parse). If a plotly bump changes any of them, this
module fails loud **on the bump PR** — upstream of the e2e tripwires and long
before a blank-figure report could reach a partner (epic #262 S3).
"""

from __future__ import annotations

import re

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from views_reporting.reports.report import ReportModule


def _fragment() -> str:
    fig = go.Figure(go.Scatter(y=[1, 2]))
    return fig.to_html(full_html=False, include_plotlyjs=False)


def test_fragment_carries_both_injection_probe_strings():
    """A real lean fragment must carry BOTH probes ``_ensure_plotly_js`` keys
    on — a bump that drops either weakens injection to a single probe; a bump
    that drops both would silently blank every figure (the C-214 hazard)."""
    html = _fragment()
    assert "plotly-graph-div" in html, "structural container-class probe broken"
    assert "Plotly.newPlot" in html, "bootstrap-call probe broken"


def test_vendored_bundle_banner_parseable():
    """The vendored bundle's ``* plotly.js v<semver>`` banner backs the
    double-inclusion warning, the e2e count==1 assertions, AND the provenance
    stamp — it must exist and parse."""
    match = re.search(r"\* plotly\.js v([\w.\-]+)", get_plotlyjs())
    assert match, "plotly.js bundle banner missing/reformatted"
    assert re.fullmatch(r"\d+\.\d+[\w.\-]*", match.group(1))


def test_injection_fires_on_either_probe_alone():
    """Redundancy is the point (C-214): each probe alone must trigger
    injection, so a serializer change must break BOTH to disable it."""
    for lone_marker in (
        '<div class="plotly-graph-div" id="x"></div>',
        "<script>Plotly.newPlot('x', [], {})</script>",
    ):
        report = ReportModule()
        report._ensure_plotly_js(lone_marker)
        assert report._plotly_js_loaded, f"probe failed to fire: {lone_marker!r}"


def test_plain_html_still_skips_the_library():
    """Text-only reports keep skipping the ~4 MB library (the #258 economy
    the probes exist to protect)."""
    report = ReportModule()
    report._ensure_plotly_js("<p>no figures here, just prose about plots</p>")
    assert not report._plotly_js_loaded


def test_provenance_carries_plotly_versions():
    """The delivered artifact's JS is traceable (C-214): both versions in the
    machine-readable provenance payload and the footer build line."""
    import plotly

    versions = ReportModule._plotly_versions()
    assert versions["plotly"] == plotly.__version__
    assert versions["plotly_js"], "vendored js version unparsed"

    report = ReportModule()
    report.add_heading("t", level=1)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r.html"
        report.export_as_html(str(out))
        html = out.read_text()
    payload = re.search(
        r'<script type="application/json" id="views-report-provenance">(.*?)</script>',
        html,
        re.S,
    )
    assert payload
    import json

    data = json.loads(payload.group(1))
    assert data["plotly"] == plotly.__version__
    assert data["plotly_js"] == versions["plotly_js"]
    assert f"plotly v{plotly.__version__}" in html  # footer prose line
