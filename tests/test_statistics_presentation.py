"""
CIC coverage for PosteriorDistributionAnalyzer's PRESENTATION methods (#260).

`print_summary()` and `plot_summary()` were covered only by pipeline-core's
relic `tests/test_modules/test_statistics.py` (never run in their CI, pruned
in their #316), leaving both methods untested in either repo. These tests pin
the presentation contract IN the repo that owns it:

  * every summary-dict key the methods consume ('map', 'min', 'max',
    'mass_at_zero', 'bimodal', 'pinned_masses', 'hdis') is exercised
    end-to-end through analyze(), so the next key rename fails HERE first
    instead of raising KeyError at report-generation time;
  * `plot_summary(save_path=...)` is verified by a REAL file write (the relic
    suite mocked `savefig`, which is exactly how "silently stops writing
    files" escapes).

Red team: not-yet-analyzed guards. Green team: output/figure correctness.
"""

import io

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from views_reporting.statistics.statistics import (  # noqa: E402
    PosteriorDistributionAnalyzer,
)


@pytest.fixture
def analyzed():
    """An analyzer with a peaked, part-zero posterior at two HDI masses."""
    rng = np.random.RandomState(42)
    samples = np.concatenate(
        [np.abs(rng.normal(5.0, 2.0, 900)), np.zeros(100)]
    )
    analyzer = PosteriorDistributionAnalyzer()
    analyzer.analyze(samples, credible_masses=(0.5, 0.95))
    return analyzer


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ── print_summary ────────────────────────────────────────────────────────────


@pytest.mark.red_team
class TestPrintSummaryGuard:
    def test_before_analyze_prints_notice_and_returns(self):
        """No summary → the notice goes to the GIVEN stream, nothing raises."""
        out = io.StringIO()
        PosteriorDistributionAnalyzer().print_summary(file=out)
        assert "No summary available" in out.getvalue()


@pytest.mark.green_team
class TestPrintSummaryOutput:
    def test_all_lines_present_with_current_labels(self, analyzed):
        """Pins the CURRENT label set — the relic suite still asserted the
        pre-tower 'MAP estimate:' label, which is the drift class this file
        exists to catch."""
        out = io.StringIO()
        analyzed.print_summary(file=out)
        text = out.getvalue()

        assert "Point estimate (tower tip):" in text
        assert "Min:" in text
        assert "Max:" in text
        assert "Mass at zero:" in text
        assert "Bimodal:" in text
        assert "NOT proven unimodal" in text

    def test_values_match_summary_dict(self, analyzed):
        """Printed numbers are the summary dict's, in the documented formats."""
        out = io.StringIO()
        analyzed.print_summary(file=out)
        text = out.getvalue()
        s = analyzed.summary_dict()

        assert f"Point estimate (tower tip): {s['map']:.4f}" in text
        assert f"Min: {s['min']:.4f}" in text
        assert f"Max: {s['max']:.4f}" in text
        assert f"Mass at zero: {s['mass_at_zero']:.2%}" in text
        # ~10% exact zeros in the fixture must show up as a real percentage
        assert s["mass_at_zero"] >= 0.09

    def test_one_hdi_line_per_pinned_mass(self, analyzed):
        """HDI lines are labelled by the PINNED (canonical-grid) masses and
        carry that mass's own bounds."""
        out = io.StringIO()
        analyzed.print_summary(file=out)
        text = out.getvalue()
        s = analyzed.summary_dict()

        assert len(s["pinned_masses"]) == len(s["hdis"]) == 2
        for mass, (low, high) in zip(s["pinned_masses"], s["hdis"]):
            assert f"{round(mass * 100)}% HDI: [{low:.4f}, {high:.4f}]" in text

    def test_default_stream_is_current_stdout(self, analyzed, capsys):
        """Calling with no file argument prints to the CURRENT sys.stdout.

        RED-proven: this failed against the original `file: TextIO =
        sys.stdout` signature, which froze the import-time stream so any
        later redirection (pytest capture, contextlib.redirect_stdout)
        was silently bypassed — fixed to resolve at call time (#260)."""
        analyzed.print_summary()
        assert "Point estimate (tower tip):" in capsys.readouterr().out

    def test_redirect_stdout_is_respected(self, analyzed):
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            analyzed.print_summary()
        assert "Point estimate (tower tip):" in buf.getvalue()


# ── plot_summary ─────────────────────────────────────────────────────────────


@pytest.mark.red_team
class TestPlotSummaryGuard:
    def test_before_analyze_returns_none(self):
        assert PosteriorDistributionAnalyzer().plot_summary(show=False) is None


@pytest.mark.green_team
class TestPlotSummaryFigure:
    def test_returns_figure_with_point_line_and_hdi_spans(self, analyzed):
        fig = analyzed.plot_summary(show=False)
        assert isinstance(fig, plt.Figure)
        ax = fig.axes[0]
        s = analyzed.summary_dict()

        # the point (tip) line sits at summary['map']
        vlines = [
            ln for ln in ax.lines
            if np.allclose(ln.get_xdata(), s["map"])
        ]
        assert vlines, "no vertical line at the point estimate"

        # one shaded span per pinned mass, and the legend labels them
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        hdi_labels = [lb for lb in labels if lb.endswith("% HDI")]
        assert len(hdi_labels) == len(s["pinned_masses"])
        for mass in s["pinned_masses"]:
            assert f"{round(mass * 100)}% HDI" in hdi_labels
        assert any(lb.startswith("Point (tip)") for lb in labels)

    def test_show_false_does_not_call_show(self, analyzed, monkeypatch):
        calls = []
        monkeypatch.setattr(plt, "show", lambda *a, **k: calls.append(1))
        analyzed.plot_summary(show=False)
        assert calls == []

    def test_show_true_calls_show(self, analyzed, monkeypatch):
        calls = []
        monkeypatch.setattr(plt, "show", lambda *a, **k: calls.append(1))
        analyzed.plot_summary(show=True)
        assert calls == [1]

    def test_bimodal_flag_annotates_title(self, analyzed):
        """The bimodality caveat must reach the figure title. The flag is
        injected on the summary dict (presentation unit test): whether the
        tower DETECTS bimodality is upstream behaviour, pinned by their
        conformance suite, not by us."""
        analyzed.summary["bimodal"] = True
        fig = analyzed.plot_summary(show=False)
        assert "bimodal" in fig.axes[0].get_title()

    def test_unimodal_title_has_no_caveat(self, analyzed):
        """Injected like the True case — symmetric, so neither presentation
        test couples to the tower's detection boundary on this fixture."""
        analyzed.summary["bimodal"] = False
        fig = analyzed.plot_summary(show=False)
        assert "bimodal" not in fig.axes[0].get_title()


@pytest.mark.green_team
class TestPlotSummarySave:
    def test_save_path_writes_a_real_png(self, analyzed, tmp_path):
        """A REAL write — the relic suite mocked `savefig`, which cannot catch
        'silently stops writing files' (#260's stated bite)."""
        target = tmp_path / "posterior.png"
        analyzed.plot_summary(show=False, save_path=str(target))
        assert target.exists()
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert target.stat().st_size > 1000

    def test_no_save_path_writes_nothing(self, analyzed, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        analyzed.plot_summary(show=False)
        assert list(tmp_path.iterdir()) == []
