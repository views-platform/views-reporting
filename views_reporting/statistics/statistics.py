"""PosteriorDistributionAnalyzer core class."""

import logging
import sys
from typing import Dict, List, Optional, TextIO, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex
from views_frames_summarize import summarize_tower as _vfs_summarize_tower

logger = logging.getLogger(__name__)


def _single_row_frame(samples: np.ndarray) -> PredictionFrame:
    """Wrap a 1D finite sample vector as a 1-row ephemeral PredictionFrame.

    MAP/HDI reduce the trailing (sample) axis per row, so the index content is
    irrelevant to the numbers; only ``n_rows == 1`` matters. The frame is
    discarded by the caller after the summarizer call.
    """
    values = np.asarray(samples, dtype=np.float32).reshape(1, -1)
    index = SpatioTemporalIndex(
        time=np.zeros(1, dtype=np.int64),
        unit=np.zeros(1, dtype=np.int64),
        level=SpatialLevel.CM,
    )
    return PredictionFrame(values, index)

class PosteriorDistributionAnalyzer:
    """
    Posterior analyzer using empirical summaries and HDI computation.

    Provides MAP detection with optional zero-dominance logic, empirical HDI
    via sorted samples, and optional HDI nesting enforcement.
    """

    def __init__(self):
        self.summary: Optional[dict] = None

    @staticmethod
    def _validate_samples(samples: Union[List[float], np.ndarray]) -> np.ndarray:
        """
        Validate and clean sample array by removing invalid values.

        Internal Use:
            Called by analyze() before processing samples.

        Args:
            samples: Raw posterior samples that may contain NaN or infinite values

        Returns:
            Cleaned numpy array with only finite values

        Raises:
            ValueError: If all samples are NaN or infinite
        """
        arr = np.asarray(samples)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            logger.error("No valid samples provided (NaN or infinite values filtered out).")
            raise ValueError("No valid samples provided.")
        return arr

    @staticmethod
    def _validate_credible_masses(masses: Tuple[float, ...]) -> Tuple[float, ...]:
        """
        Validate and sort credible mass values.

        Internal Use:
            Called by analyze() to validate HDI mass parameters.

        Args:
            masses: Tuple of credible mass values (e.g., (0.5, 0.95, 0.99))

        Returns:
            Sorted tuple of validated mass values

        Raises:
            ValueError: If any mass is not in range (0, 1)
        """
        if not all(0 < m < 1 for m in masses):
            logger.error(f"Invalid credible_masses: {masses}. Must be between 0 and 1.")
            raise ValueError("All credible masses must be between 0 and 1.")
        return tuple(sorted(masses))

    def analyze(
        self,
        samples: np.array,
        credible_masses: Tuple[float, ...] = (0.5, 0.95, 0.99),
    ) -> dict:
        """
        Compute posterior summary statistics including MAP and HDIs.

        Analyzes posterior samples to extract maximum a posteriori (MAP) estimate,
        highest density intervals (HDI) at multiple credible levels, and basic
        statistics.

        Args:
            samples: Posterior samples to analyze (1D array)
            credible_masses: Tuple of HDI credible levels (e.g., (0.5, 0.95, 0.99)).
                Each value must be in (0, 1). Each is pinned to the tower's fixed
                canonical mass grid (see 'pinned_masses' in the result).

        Returns:
            Dictionary containing:
                - 'map' (float): point estimate — the tower tip (a shorth), NOT a
                  histogram-mode MAP. Key kept as 'map' for result-shape stability.
                - 'min' (float): Minimum sample value
                - 'max' (float): Maximum sample value
                - 'mass_at_zero' (float): Proportion of samples ≈ 0
                - 'hdis' (list): List of (lower, upper) nested HDI tuples, one per
                  requested mass (narrowest → widest)
                - 'bimodal' (bool): tower bimodality flag — True means a clearly
                  separated second mode was detected; False means "no clear
                  bimodality detected", NOT "proven unimodal"
                - 'pinned_masses' (tuple): the canonical masses the requested
                  credible_masses pinned to

        Example:
            >>> samples = np.random.normal(5, 2, 10000)
            >>> analyzer = PosteriorDistributionAnalyzer()
            >>> result = analyzer.analyze(samples, credible_masses=(0.5, 0.95))
            >>> print(f"point: {result['map']:.2f}")
            point: 5.01

        Note:
            - Point + nested HDIs + bimodality come from the views-frames tower
              (`summarize_tower`) in one pass; HDIs nest and the tip lies inside the
              narrowest floor BY CONSTRUCTION (no post-hoc enforcement). See ADR-019.
        """
        samples = self._validate_samples(samples)
        credible_masses = self._validate_credible_masses(credible_masses)

        result = self._compute_summary(samples, credible_masses)

        # Interactive state: written after computation so _compute_summary
        # never reads from self.*. summary is set last because print_summary
        # and plot_summary gate on self.summary is None.
        self.samples = samples
        self.credible_masses = credible_masses
        self.summary = result
        return result

    def _compute_summary(
        self,
        samples: np.ndarray,
        credible_masses: Tuple[float, ...],
    ) -> dict:
        """
        Compute the point estimate, nested HDIs, bimodality flag, and stats.

        Internal Use:
            Called by analyze() after validation to perform core computation.

        Returns:
            Dictionary with keys: 'map' (tower tip), 'min', 'max', 'mass_at_zero',
            'hdis' (nested, one per requested mass), 'bimodal' (bool),
            'pinned_masses'.
        """
        # The point/interval math is delegated to the conformance-tested
        # views_frames_summarize TOWER on a 1-row ephemeral frame: the tip
        # (mode-bias-free point), constrained-nested HDIs, and a bimodality
        # flag, all in one pass. Nesting + tip-in-floor hold BY CONSTRUCTION,
        # so no post-hoc structure enforcement is needed (register C-35,
        # ADR-019). mass_at_zero stays reporting-owned (the tower omits it).
        mass_at_zero = np.mean(np.isclose(samples, 0.0, atol=1e-8))

        frame = _single_row_frame(samples)
        summary = _vfs_summarize_tower(frame, masses=credible_masses)

        map_val = float(summary.point.values[0, 0])
        hdis = [
            (float(summary.intervals[0, j, 0]), float(summary.intervals[0, j, 1]))
            for j in range(summary.intervals.shape[1])
        ]
        bimodal = bool(summary.bimodal[0, 0])
        pinned_masses = tuple(float(m) for m in summary.masses)
        logger.debug(
            f"Tower summary: map={map_val}, bimodal={bimodal}, "
            f"pinned_masses={pinned_masses}"
        )

        return {
            'map': map_val,
            'min': float(np.min(samples)),
            'max': float(np.max(samples)),
            'mass_at_zero': float(mass_at_zero),
            'hdis': hdis,
            'bimodal': bimodal,
            'pinned_masses': pinned_masses,
        }


    def summary_dict(self) -> Optional[Dict]:
        """
        Get computed posterior summary as dictionary.

        Returns:
            Summary dictionary with MAP, HDIs, and statistics.
            None if analyze() has not been called.

        Example:
            >>> analyzer = PosteriorDistributionAnalyzer()
            >>> analyzer.analyze(samples)
            >>> summary = analyzer.summary_dict()
            >>> print(summary['map'])
            5.123
        """
        return self.summary


    def print_summary(self, file: TextIO = sys.stdout) -> None:
        """
        Print formatted posterior summary to file or console.

        Args:
            file: Output stream (default: sys.stdout for console)

        Example:
            >>> analyzer = PosteriorDistributionAnalyzer()
            >>> analyzer.analyze(samples)
            >>> analyzer.print_summary()
            MAP estimate: 5.1234
            Min: 0.0012
            Max: 10.4567
            Mass at zero: 15.30%
            50% HDI: [3.2100, 7.0345]
            95% HDI: [1.0834, 9.1267]

        Note:
            - Prints nothing if analyze() has not been called
            - Useful for quick inspection during interactive analysis
        """
        if self.summary is None:
            logger.warning("Summary not computed yet. Call `analyze()` first.")
            print("No summary available. Please run `.analyze()` first.", file=file)
            return

        print(f"Point estimate (tower tip): {self.summary['map']:.4f}", file=file)
        print(f"Min: {self.summary['min']:.4f}", file=file)
        print(f"Max: {self.summary['max']:.4f}", file=file)
        print(f"Mass at zero: {self.summary['mass_at_zero']:.2%}", file=file)

        flag = "yes" if self.summary['bimodal'] else "no"
        print(
            f"Bimodal: {flag} "
            "('no' = no clear bimodality detected, NOT proven unimodal)",
            file=file,
        )

        # Label HDIs by the masses the request actually pinned to (canonical grid).
        for mass, (low, high) in zip(
            self.summary['pinned_masses'], self.summary['hdis']
        ):
            print(f"{round(mass * 100)}% HDI: [{low:.4f}, {high:.4f}]", file=file)



    def plot_summary(
        self,
        show: bool = True,
        save_path: Optional[str] = None,
    ) -> Optional[plt.Figure]:
        """
        Visualize posterior distribution with MAP and HDI overlays.

        Creates histogram of posterior samples with vertical line at MAP and
        shaded regions for each HDI interval.

        Args:
            show: Whether to display plot immediately
            save_path: Optional file path to save plot (e.g., 'posterior.png')

        Returns:
            Matplotlib Figure object for further customization, or None if no summary

        Example:
            >>> analyzer = PosteriorDistributionAnalyzer()
            >>> analyzer.analyze(samples)
            >>> analyzer.plot_summary(save_path='results/posterior_plot.png')

        Note:
            - Requires analyze() to be called first
            - HDIs shown as semi-transparent shaded regions
            - MAP shown as red dashed vertical line
        """
        if self.summary is None:
            logger.warning("No summary available. Run `.analyze()` before plotting.")
            return None

        fig, ax = plt.subplots(figsize=(10, 5))

        # Histogram (plot-only resolution; the tower estimator has no `bins`)
        bins = 100
        ax.hist(self.samples, bins=bins, density=True, alpha=0.3, label='Posterior Histogram')

        # Point (tower tip) line
        map_val = self.summary['map']
        ax.axvline(map_val, color='red', linestyle='--', label=f'Point (tip) = {map_val:.2f}')

        # Nested HDIs, labelled by the pinned (canonical) masses
        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
        for i, (mass, (low, high)) in enumerate(
            zip(self.summary['pinned_masses'], self.summary['hdis'])
        ):
            ax.axvspan(
                low, high,
                color=colors[i % len(colors)],
                alpha=0.3,
                label=f'{round(mass * 100)}% HDI',
            )

        # Labels and styling
        title = "Posterior Summary"
        if self.summary['bimodal']:
            title += " — bimodal (point/HDI may be ill-defined)"
        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.set_ylabel("Density")
        ax.legend()
        plt.tight_layout()

        # Save or show
        if save_path:
            fig.savefig(save_path)
            logger.info(f"Saved plot to {save_path}")
        if show:
            plt.show()

        return fig
