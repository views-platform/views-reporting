"""HDI and MAP overlays on posterior sample histograms.

Renders from a views-frames ``PredictionFrame`` (one target's samples per frame),
not a pipeline-core dataset — reporting depends on the leaf data contract, not on
pipeline-core internals (C-114 / #113).
"""

from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from views_frames import PredictionFrame

from views_reporting.statistics import calculate_single_hdi, compute_single_map


class PlotDistribution:
    """Posterior-sample histograms with HDI/MAP overlays for one ``PredictionFrame``.

    The frame holds a single target's samples on a ``(time, entity)`` row index
    (``frame.values`` is ``(n_rows, n_samples)``). ``entity_id``/``time_id`` select
    a subset of rows by boolean mask on ``frame.index``; the selected rows' samples
    are pooled into the plotted distribution. ``var_name`` is an optional display
    label only (the frame already fixes the target).
    """

    def __init__(self, frame: PredictionFrame) -> None:
        self._frame = frame

    def _pooled_samples(
        self, entity_id: Optional[int], time_id: Optional[int]
    ) -> np.ndarray:
        """Samples pooled over the rows matching ``entity_id``/``time_id`` (NaNs dropped)."""
        values = np.asarray(self._frame.values, dtype=np.float64)  # (n_rows, n_samples)
        mask = np.ones(values.shape[0], dtype=bool)
        if entity_id is not None:
            mask &= np.asarray(self._frame.index.unit) == entity_id
        if time_id is not None:
            mask &= np.asarray(self._frame.index.time) == time_id
        flat = values[mask].flatten()
        return flat[~np.isnan(flat)]

    def plot_maximum_a_posteriori(
        self,
        entity_id: Optional[int] = None,
        time_id: Optional[int] = None,
        var_name: Optional[str] = None,
        hdi_alpha: float = 0.9,
        ax: Optional[plt.Axes] = None,
        colors: Optional[List[str]] = None,
        plot_kde: bool = True,
        max_bins: int = 100,
    ) -> plt.Axes:
        """
        entity_id (Optional[int]): Specific entity to plot.
        time_id (Optional[int]): Specific time step to plot.
        var_name (Optional[str]): Display label for the target (title only).
        hdi_alpha (float): Credibility level for HDI. Default is 0.9.
        ax (Optional[plt.Axes]): Matplotlib axes object. If None, a new axis is created.
        colors (Optional[List[str]]): List of colors for HDI and MAP lines.
            If None, default colors are used.
        plot_kde (bool): Whether to plot Kernel Density Estimate. Default is True.
        max_bins (int): Maximum number of bins for histogram. Default is 100.
        plt.Axes: Matplotlib axes object with the plot.

        Returns:
        matplotlib.axes.Axes
        """
        # Create axis if not provided
        ax = ax or plt.gca()

        # Pool the selected samples, handling NaNs
        valid_samples = self._pooled_samples(entity_id, time_id)

        # Handle empty data case
        if len(valid_samples) == 0:
            ax.text(0.5, 0.5, "No valid samples", ha="center", va="center")
            return ax

        # Calculate HDI and MAP simultaneously
        hdi_min, hdi_max = calculate_single_hdi(valid_samples, hdi_alpha)
        map_value = compute_single_map(valid_samples)

        # Adaptive histogram binning
        data_range = valid_samples.max() - valid_samples.min()
        bin_width = data_range / min(max_bins, len(valid_samples) // 10)
        bins = min(max_bins, max(10, int(data_range / bin_width)))

        # Plotting
        sns.histplot(
            valid_samples,
            bins=bins,
            kde=plot_kde,
            ax=ax,
            color="#3498DB",
            alpha=0.6,
            edgecolor="none",
            label="Distribution",
        )

        if colors is None:
            colors = sns.color_palette("colorblind", 1)

        # Plot HDI
        hdi_color = colors[0] if colors else "#2ECC71"
        ax.axvspan(
            hdi_min,
            hdi_max,
            color=hdi_color,
            alpha=0.3,
            label=f"{hdi_alpha*100:.0f}% HDI",
        )

        # Plot MAP
        map_color = colors[1] if colors and len(colors) > 1 else "#E74C3C"
        ax.axvline(
            map_value,
            color=map_color,
            linestyle="--",
            linewidth=2,
            label=f"MAP Estimate: {map_value:.2f}",
        )

        # Dynamic title
        title_parts = []
        if entity_id is not None:
            title_parts.append(f"Entity {entity_id}")
        if time_id is not None:
            title_parts.append(f"Time {time_id}")

        title = f"{var_name or 'Posterior'} Distribution"
        if title_parts:
            title += f" ({' - '.join(title_parts)})"

        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.set_ylabel("Density")
        ax.legend()

        return ax

    def plot_highest_density_intervals(
        self,
        entity_id: Optional[int] = None,
        time_id: Optional[int] = None,
        var_name: Optional[str] = None,
        alphas: Tuple[float, ...] = (0.9,),
        colors: Optional[List[str]] = None,
        ax: Optional[plt.Axes] = None,
    ) -> plt.Axes:
        """
        Plot distribution with multiple HDIs for a specific entity/time selection.

        Parameters:
        entity_id: Specific entity to plot (None for aggregate)
        time_id: Specific time step to plot (None for aggregate)
        var_name: Display label for the target (title only)
        alphas: Tuple of credibility levels to plot
        colors: Optional list of colors for each alpha level
        ax: Matplotlib axes to plot on (creates new if None)

        Returns:
        matplotlib.axes.Axes: The plot axes
        """
        if not self._frame.is_sample:
            raise ValueError("HDI plotting only available for sample (prediction) frames")
        if not isinstance(alphas, tuple):
            alphas = (alphas,)
        if not all(0 < a < 1 for a in alphas):
            raise ValueError("All alpha values must be between 0 and 1")

        # Pool the selected samples (NaNs dropped)
        flat_data = self._pooled_samples(entity_id, time_id)

        # Create plot
        ax = ax or plt.gca()
        sns.histplot(
            flat_data,
            bins=50,
            kde=True,
            ax=ax,
            color="blue",
            alpha=0.6,
            label="Distribution",
        )

        # Create color map if not provided
        if colors is None:
            # Use a colorblind-friendly color palette
            colors = sns.color_palette("colorblind", len(alphas))
        elif len(colors) != len(alphas):
            raise ValueError("Number of colors must match number of alpha levels")

        # Sort alphas for intuitive color progression
        sorted_alphas = sorted(alphas, reverse=True)

        # Plot each HDI with distinct color
        for alpha, color in zip(sorted_alphas, colors):
            hdi_min, hdi_max = calculate_single_hdi(flat_data, alpha)

            ax.fill_betweenx(
                y=[0, ax.get_ylim()[1]],
                x1=hdi_min,
                x2=hdi_max,
                color=color,
                alpha=0.3,
                label=f"{alpha*100:.0f}% HDI",
            )

        # Add annotations
        title_parts = []
        if entity_id is not None:
            title_parts.append(f"Entity {entity_id}")
        if time_id is not None:
            title_parts.append(f"Time {time_id}")
        title = f"{var_name or 'Posterior'} Posterior Distribution"
        if title_parts:
            title += f" ({' - '.join(title_parts)})"

        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.set_ylabel("Density")
        ax.legend()

        return ax
