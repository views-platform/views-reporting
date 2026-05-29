"""
C-01 fix: Thread-safe PosteriorDistributionAnalyzer.

Test categories per ADR-005:
  Red team   — adversarial race reproduction
  Green team — numerical correctness under known distributions
  Beige team — realistic sequential usage patterns
"""

import threading

import numpy as np

from views_reporting.statistics.statistics import PosteriorDistributionAnalyzer

# ── Red team (adversarial) ────────────────────────────────────────────────


class TestRedTeamThreadSafety:

    def test_shared_instance_race_corrupts_map(self):
        """Two threads sharing one instance must not corrupt MAP values."""
        analyzer = PosteriorDistributionAnalyzer()
        trials = 200
        mismatches = 0

        for _ in range(trials):
            barrier = threading.Barrier(2)
            results = {}

            def worker(name, samples):
                barrier.wait()
                result = analyzer.analyze(samples=samples, credible_masses=(0.9,))
                results[name] = result["map"]

            samples_a = np.zeros(5000)
            samples_b = np.random.normal(500, 10, 5000)

            t1 = threading.Thread(target=worker, args=("A", samples_a))
            t2 = threading.Thread(target=worker, args=("B", samples_b))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            if results.get("B", 500) < 450:
                mismatches += 1

        assert mismatches == 0, (
            f"Shared instance: {mismatches}/{trials} corrupt MAP values"
        )

    def test_module_helper_race_via_singleton(self):
        """The module-level helpers that call analyze() must be thread-safe."""
        from views_reporting.statistics.dataset_statistics import (
            _compute_single_map,
        )

        trials = 200
        mismatches = 0

        for _ in range(trials):
            barrier = threading.Barrier(2)
            results = {}

            def worker(name, samples):
                barrier.wait()
                results[name] = _compute_single_map(samples)

            samples_a = np.zeros(5000)
            samples_b = np.random.normal(500, 10, 5000)

            t1 = threading.Thread(target=worker, args=("A", samples_a))
            t2 = threading.Thread(target=worker, args=("B", samples_b))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            if results.get("B", 500) < 450:
                mismatches += 1

        assert mismatches == 0, (
            f"Module helpers: {mismatches}/{trials} corrupt MAP values"
        )


# ── Green team (correctness) ─────────────────────────────────────────────


class TestGreenTeamCorrectness:

    def test_normal_distribution(self):
        """MAP near mean, HDI contains MAP, HDIs nested."""
        np.random.seed(42)
        samples = np.random.normal(loc=5.0, scale=2.0, size=10_000)
        analyzer = PosteriorDistributionAnalyzer()
        result = analyzer.analyze(samples, credible_masses=(0.5, 0.9, 0.99))

        assert 3.0 < result["map"] < 7.0
        for low, high in result["hdis"]:
            assert low <= result["map"] <= high
        for i in range(1, len(result["hdis"])):
            assert result["hdis"][i][0] <= result["hdis"][i - 1][0]
            assert result["hdis"][i][1] >= result["hdis"][i - 1][1]

    def test_zero_inflated(self):
        """80% zeros triggers zero-mass MAP override."""
        np.random.seed(42)
        samples = np.concatenate([
            np.zeros(8000),
            np.random.exponential(2.0, 2000),
        ])
        analyzer = PosteriorDistributionAnalyzer()
        result = analyzer.analyze(samples, credible_masses=(0.9,))

        assert result["map"] == 0.0
        assert result["mass_at_zero"] > 0.3

    def test_bimodal(self):
        """MAP near the dominant mode, HDI contains MAP."""
        np.random.seed(42)
        samples = np.concatenate([
            np.random.normal(-5, 1, 3000),
            np.random.normal(5, 1, 7000),
        ])
        analyzer = PosteriorDistributionAnalyzer()
        result = analyzer.analyze(samples, credible_masses=(0.5, 0.9))

        assert 3.0 < result["map"] < 7.0
        for low, high in result["hdis"]:
            assert low <= result["map"] <= high

    def test_credible_masses_count(self):
        """Number of HDIs must match number of credible masses."""
        samples = np.random.normal(0, 1, 5000)
        analyzer = PosteriorDistributionAnalyzer()

        r1 = analyzer.analyze(samples, credible_masses=(0.9,))
        assert len(r1["hdis"]) == 1

        r3 = analyzer.analyze(samples, credible_masses=(0.5, 0.9, 0.99))
        assert len(r3["hdis"]) == 3

    def test_per_call_instantiation_eliminates_race(self):
        """Fresh instances per thread must never produce corrupt results."""
        trials = 200
        mismatches = 0

        for _ in range(trials):
            barrier = threading.Barrier(2)
            results = {}

            def worker(name, samples):
                barrier.wait()
                local_analyzer = PosteriorDistributionAnalyzer()
                result = local_analyzer.analyze(samples=samples, credible_masses=(0.9,))
                results[name] = result["map"]

            samples_a = np.zeros(5000)
            samples_b = np.random.normal(500, 10, 5000)

            t1 = threading.Thread(target=worker, args=("A", samples_a))
            t2 = threading.Thread(target=worker, args=("B", samples_b))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            if results.get("B", 500) < 450:
                mismatches += 1

        assert mismatches == 0, (
            f"Per-call instantiation: {mismatches}/{trials} corrupt values"
        )


# ── Beige team (realistic usage) ─────────────────────────────────────────


class TestBeigeTeamRealisticUsage:

    def test_sequential_calls_different_params(self):
        """Sequential calls must not leak state between invocations."""
        analyzer = PosteriorDistributionAnalyzer()
        np.random.seed(42)

        r1 = analyzer.analyze(
            np.random.normal(0, 1, 5000),
            credible_masses=(0.5, 0.9, 0.99),
        )
        assert len(r1["hdis"]) == 3

        r2 = analyzer.analyze(
            np.random.normal(500, 10, 5000),
            credible_masses=(0.9,),
        )
        assert len(r2["hdis"]) == 1
        assert r2["map"] > 450

    def test_interactive_workflow(self):
        """analyze() → summary_dict() must return consistent results."""
        analyzer = PosteriorDistributionAnalyzer()
        np.random.seed(42)

        samples_a = np.random.normal(10, 2, 5000)
        result_a = analyzer.analyze(samples_a, credible_masses=(0.9,))
        summary_a = analyzer.summary_dict()
        assert summary_a is result_a
        assert summary_a["map"] == result_a["map"]

        samples_b = np.random.normal(500, 10, 5000)
        result_b = analyzer.analyze(samples_b, credible_masses=(0.5, 0.9))
        summary_b = analyzer.summary_dict()
        assert summary_b is result_b
        assert summary_b["map"] == result_b["map"]
        assert summary_b["map"] != summary_a["map"]
