"""Offline-delivery guards for exported reports (register C-28 / C-187 / C-188).

A delivered report must render with **no network** (no CDN), and carry machine-readable
provenance for a future catalog (C-188). These are fast, pure-HTML assertions.
"""

import json
import re

import pytest

try:
    from views_reporting.reports.report import ReportModule
    from views_reporting.reports.styles.tailwind import get_css
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

from unittest.mock import patch


def _export(tmp_path, *, provenance=None) -> str:
    with patch("views_reporting.reports.report.PipelineConfig") as cfg:
        cfg.current_version = "0.0.0-test"
        report = ReportModule()
        report.add_heading("Offline check")
        report.add_paragraph("body")
        if provenance is not None:
            report.add_footer(provenance=provenance)
        out = tmp_path / "r.html"
        report.export_as_html(str(out))
        return out.read_text()


@pytest.mark.green_team
class TestNoCDN:
    def test_get_css_has_no_cdn(self):
        css = get_css()
        assert "https://cdn." not in css
        assert "cdn.tailwindcss.com" not in css
        assert "cdn.plot.ly" not in css

    def test_exported_report_has_no_cdn(self, tmp_path):
        # The headline offline guarantee: nothing in the delivered HTML points at a CDN.
        html = _export(tmp_path)
        assert "https://cdn." not in html

    def test_vendored_tailwind_inlined(self):
        # Vendored utilities + theme tokens are present inline (not JIT'd from a CDN).
        css = get_css()
        for token in ("mt-12", "text-center", "on-surface-variant"):
            assert token in css, f"vendored Tailwind missing utility/token: {token}"
        # custom component CSS still inlined
        assert "table-container" in css


@pytest.mark.green_team
class TestClassCoverage:
    """C-187: every literal Tailwind class token the report code emits must be present
    in get_css() output (vendored utility CSS *or* the custom component CSS) — a missing
    class would render an element unstyled with no error. This guard fails loud if a
    template adds a class the vendored CSS lacks (regenerate via
    scripts/build_tailwind_css.sh, adding to its safelist if the scanner misses it)."""

    # Classes that are intentional semantic hooks with no CSS rule (never styled —
    # not Tailwind utilities). Excluded from the coverage requirement.
    SEMANTIC_HOOKS = {
        "report-footer", "footer-text", "footer-timestamp", "footer-provenance",
        "image-caption", "responsive-image",
    }
    # A valid Tailwind/CSS class token (drops f-string extraction artifacts).
    _VALID = re.compile(r"^[A-Za-z][A-Za-z0-9:/_.\-\[\]%()]*$")

    @staticmethod
    def _covered(token: str, css: str) -> bool:
        # Tailwind escapes :/[]().%,# in selectors (e.g. `.hover\:underline`,
        # `.min-w-\[120px\]`); custom component classes appear plain (`.table-container`).
        escaped = re.sub(r"([:/\[\]().%,#])", r"\\\1", token)
        return escaped in css or token in css

    def test_emitted_classes_are_covered(self):
        import pathlib

        css = get_css()
        tokens = set()
        for path in pathlib.Path("views_reporting").rglob("*.py"):
            for attr in re.findall(r'class="([^"{}]+)"', path.read_text()):
                tokens.update(attr.split())
        missing = sorted(
            t for t in tokens
            if self._VALID.match(t)
            and t not in self.SEMANTIC_HOOKS
            and not self._covered(t, css)
        )
        assert not missing, (
            f"Tailwind classes emitted by templates but absent from the vendored CSS: "
            f"{missing}. Regenerate scripts/build_tailwind_css.sh (add to its safelist "
            f"if the content scanner misses an arbitrary-value class)."
        )


@pytest.mark.green_team
class TestMachineReadableProvenance:
    """C-188: the report embeds its identity as parseable JSON for a future catalog."""

    def test_provenance_json_block_present_and_parseable(self, tmp_path):
        html = _export(
            tmp_path,
            provenance={"model": "purple_alien", "run_type": "forecasting"},
        )
        m = re.search(
            r'<script type="application/json" id="views-report-provenance">(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m, "machine-readable provenance block missing"
        data = json.loads(m.group(1).replace("\\u003c", "<"))
        assert set(("build", "generated", "provenance")) <= set(data)
        assert data["provenance"]["model"] == "purple_alien"
        assert "views_reporting" in data["build"]
