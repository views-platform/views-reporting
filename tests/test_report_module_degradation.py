"""Guard for C-107: ReportModule.add_markdown must LOG (ADR-008) before degrading to
plain text when the optional `markdown` package is unavailable — the user-visible HTML
note alone is programmatically invisible to monitoring.
"""

import builtins
import logging

import pytest

try:
    from views_reporting.reports import ReportModule
except ImportError:  # pragma: no cover
    pytest.skip("views_reporting not importable", allow_module_level=True)


@pytest.mark.red_team
def test_add_markdown_warns_before_plaintext_degradation(caplog, monkeypatch):
    """With `markdown` unavailable, add_markdown logs a WARNING and still renders the
    plain-text fallback (degrade-and-announce, ADR-008 / C-107)."""
    real_import = builtins.__import__

    def _no_markdown(name, *args, **kwargs):
        if name == "markdown" or name.startswith("markdown."):
            raise ImportError("simulated: markdown not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_markdown)

    rm = ReportModule()
    with caplog.at_level(logging.WARNING, logger="views_reporting.reports.report"):
        rm.add_markdown("# Results\n\nsome text")

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("markdown" in r.message.lower() for r in warnings), (
        "add_markdown degraded to plain text without logging a WARNING (C-107)"
    )
    # The plain-text fallback still happened (degradation is announced, not swallowed).
    html = "".join(rm.content)
    assert "Markdown rendering unavailable" in html
