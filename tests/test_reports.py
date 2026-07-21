"""
CIC coverage for ReportModule.

Tests content accumulation, HTML generation, and table splitting.
Mocks PipelineConfig to avoid views_pipeline_core dependency.
"""

from unittest.mock import patch

import pandas as pd
import pytest

try:
    from views_reporting.reports.report import ReportModule, get_build_info
except ImportError:
    pytest.skip(
        "views_pipeline_core not installed",
        allow_module_level=True,
    )


# ── Green team: content accumulation ─────────────────────────────────────


@pytest.mark.green_team
class TestContentAccumulation:

    def test_constructor_adds_header_image(self):
        report = ReportModule()
        assert len(report.content) == 1
        assert "data:image/" in report.content[0]

    def test_add_heading_h1(self):
        report = ReportModule()
        report.add_heading("Test Title", level=1)
        assert any("<h1" in c for c in report.content)

    def test_add_heading_h2(self):
        report = ReportModule()
        report.add_heading("Subtitle", level=2)
        assert any("<h2" in c for c in report.content)

    def test_add_paragraph(self):
        report = ReportModule()
        report.add_paragraph("Hello world")
        assert any("Hello world" in c for c in report.content)
        assert any("<p" in c for c in report.content)

    def test_heading_escapes_html(self):
        report = ReportModule()
        report.add_heading("<script>alert('xss')</script>", level=1)
        html = "\n".join(report.content)
        assert "&lt;script&gt;" in html
        assert "<script>" not in html.split("</head>")[-1]

    def test_paragraph_escapes_html(self):
        report = ReportModule()
        report.add_paragraph("<img onerror=alert(1)>")
        html = "\n".join(report.content)
        assert "&lt;img" in html

    # ── add_html trust boundary (register C-117) ─────────────────────────────

    def test_add_html_passes_trusted_figure_html_verbatim(self):
        """The documented exception: figure HTML (scripts and all) must pass
        through unescaped — that is add_html's whole job."""
        report = ReportModule()
        fig_html = '<div id="plot"><script>Plotly.newPlot("plot", []);</script></div>'
        report.add_html(fig_html)
        html = "\n".join(report.content)
        assert fig_html in html  # verbatim, not escaped

    def test_add_html_height_none_sizes_to_content(self):
        """#234: height=None omits the fixed-height style — <img> embeds get
        no dead 900px scroll box; a fixed height still emits the style."""
        report = ReportModule()
        report.add_html('<img src="data:image/png;base64,xyz">', height=None)
        report.add_html("<div>fig</div>", height=900)
        html = "\n".join(report.content)
        assert html.count("style=\"height:") == 1
        assert "height: 900px" in html

    def test_add_html_warns_on_markupless_text(self, caplog):
        """The misuse signal: a plain string (no markup) arriving at the raw
        sink is almost certainly a text-sink mistake — visible, not silent."""
        report = ReportModule()
        with caplog.at_level("WARNING", logger="views_reporting.reports.report"):
            report.add_html("model run note from a user")
        assert any("VERBATIM" in r.message for r in caplog.records)

    def test_add_html_does_not_warn_on_figure_html(self, caplog):
        report = ReportModule()
        with caplog.at_level("WARNING", logger="views_reporting.reports.report"):
            report.add_html("<div>figure</div>")
        assert not [r for r in caplog.records if "VERBATIM" in r.message]

    def test_add_table_dict(self):
        report = ReportModule()
        report.add_table({"key1": "val1", "key2": "val2"})
        assert any("<table" in c for c in report.content)

    def test_add_table_dataframe(self):
        report = ReportModule()
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        report.add_table(df)
        assert any("<table" in c.lower() for c in report.content)

    def test_add_table_invalid_type_raises(self):
        report = ReportModule()
        with pytest.raises(TypeError, match="DataFrame or dictionary"):
            report.add_table("not a table")


# ── Green team: table splitting ──────────────────────────────────────────


@pytest.mark.green_team
class TestTableSplitting:

    def test_large_dataframe_splits_by_rows(self):
        report = ReportModule()
        df = pd.DataFrame({"A": range(20), "B": range(20)})
        report.add_table(df, split_threshold=8)
        html = "\n".join(report.content)
        assert "split-table-container" in html or html.count("<table") >= 2

    def test_small_dataframe_no_split(self):
        report = ReportModule()
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        report.add_table(df)
        html = "\n".join(report.content)
        assert "split-table-container" not in html


# ── Beige team: export workflow ──────────────────────────────────────────


@pytest.mark.beige_team
class TestExportWorkflow:

    def test_export_creates_valid_html(self, tmp_path):
        with patch(
            "views_reporting.reports.report.PipelineConfig"
        ) as mock_config:
            mock_config.current_version = "0.0.0-test"

            report = ReportModule()
            report.add_heading("Test Report")
            report.add_paragraph("Content here")
            report.add_table({"metric": "value"})

            out = tmp_path / "test_report.html"
            report.export_as_html(str(out))

            assert out.exists()
            html = out.read_text()
            assert "<!DOCTYPE html>" in html
            assert "Test Report" in html
            assert "Content here" in html

    def test_export_with_footer(self, tmp_path):
        with patch(
            "views_reporting.reports.report.PipelineConfig"
        ) as mock_config:
            mock_config.current_version = "0.0.0-test"

            report = ReportModule()
            report.add_footer("Generated by test")

            out = tmp_path / "footer_report.html"
            report.export_as_html(str(out))

            html = out.read_text()
            assert "Generated by test" in html


# ── Provenance footer (C-34) ─────────────────────────────────────────────


@pytest.mark.green_team
class TestProvenanceFooter:
    """C-34: every exported report carries a build+timestamp stamp; templates
    add model/run/source identity via add_footer(provenance=...). All values are
    HTML-escaped (C-19/C-117); None values are omitted; build-info never raises."""

    def _export(self, report, tmp_path, name="r.html"):
        with patch("views_reporting.reports.report.PipelineConfig") as mock_config:
            mock_config.current_version = "0.0.0-test"
            out = tmp_path / name
            report.export_as_html(str(out))
            return out.read_text()

    def test_get_build_info_shape(self):
        info = get_build_info()
        assert set(info) == {"views_reporting", "views_frames", "git_sha"}
        assert all(isinstance(v, str) and v for v in info.values())

    def test_git_sha_unavailable_is_graceful(self, monkeypatch):
        # Any subprocess failure → "unavailable" marker, never an exception.
        def _boom(*a, **k):
            raise OSError("git not found")

        monkeypatch.setattr(
            "views_reporting.reports.report.subprocess.run", _boom
        )
        info = get_build_info()
        assert info["git_sha"] == "unavailable"

    def test_footer_always_rendered_without_explicit_footer(self, tmp_path):
        # No add_footer call at all: the build/version stamp must still render.
        report = ReportModule()
        report.add_heading("X")
        html = self._export(report, tmp_path)
        assert "views-reporting v" in html and "views-frames v" in html

    def test_provenance_fields_rendered(self, tmp_path):
        report = ReportModule()
        report.add_footer(
            provenance={"model": "purple_alien", "run_type": "forecasting"}
        )
        html = self._export(report, tmp_path)
        assert "purple_alien" in html and "forecasting" in html

    def test_provenance_none_values_omitted(self, tmp_path):
        report = ReportModule()
        report.add_footer(
            provenance={"model": "m1", "prediction_path": None}
        )
        html = self._export(report, tmp_path)
        assert "m1" in html
        assert "prediction_path" not in html

    def test_provenance_values_escaped(self, tmp_path):
        report = ReportModule()
        report.add_footer(provenance={"model": "<script>x</script>"})
        html = self._export(report, tmp_path)
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html

    def test_footer_text_back_compat_positional(self, tmp_path):
        # add_footer("…") still works alongside the new provenance kwarg.
        report = ReportModule()
        report.add_footer("Generated by test", provenance={"model": "m2"})
        html = self._export(report, tmp_path)
        assert "Generated by test" in html and "m2" in html


@pytest.mark.red_team
def test_report_embeds_exactly_one_plotlyjs():
    """#258: the report owns the SINGLE inlined plotly.js copy (offline,
    C-28); figures arrive without their own. Two plotly figures in one report
    must yield exactly one library marker — not zero (broken offline), not
    two (the ~8 MB duplication class)."""
    import plotly.graph_objects as go

    report = ReportModule()
    fig_html = go.Figure().to_html(full_html=False, include_plotlyjs=False)
    report.add_html(fig_html)
    report.add_html(fig_html)
    html = "\n".join(report.content)
    assert html.count("* plotly.js v") == 1


@pytest.mark.green_team
def test_plotlyjs_injection_is_content_aware():
    """#258 review: the library injects only when PLOTLY content arrives —
    image-only reports stay lean (no ~4 MB dead weight) — and the guarantee
    holds for grid-embedded figures too."""
    # image-only report: no library
    r1 = ReportModule()
    r1.add_html('<img src="data:image/png;base64,xyz">')
    assert "* plotly.js v" not in "\n".join(r1.content)

    # plotly via a grid: library still arrives, exactly once
    r2 = ReportModule()
    r2.start_grid()
    r2.add_to_grid('<div id="p"><script>Plotly.newPlot("p", []);</script></div>')
    r2.end_grid()
    assert "\n".join(r2.content).count("* plotly.js v") == 1


@pytest.mark.green_team
def test_plotlyjs_double_inclusion_warns(caplog):
    """A figure arriving with its OWN library is a contract violation —
    warned, not silent (#258 review)."""
    import logging

    r = ReportModule()
    with caplog.at_level(logging.WARNING):
        r.add_html("<div><script>/** * plotly.js v9.9.9 */ Plotly.newPlot()</script></div>")
    assert "include_plotlyjs=False" in caplog.text
