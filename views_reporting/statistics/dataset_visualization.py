from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from views_pipeline_core.data.handlers import _ViewsDataset


def plot_map(
    dataset: _ViewsDataset,
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
    Plot MAP with HDI highlighting for a specific entity/time/variable.

    Parameters:
    dataset: The dataset to plot from
    entity_id: Specific entity to plot.
    time_id: Specific time step to plot.
    var_name: Variable to plot.
    hdi_alpha: Credibility level for HDI. Default is 0.9.
    ax: Matplotlib axes object. If None, a new axis is created.
    colors: List of colors for HDI and MAP lines.
    plot_kde: Whether to plot Kernel Density Estimate. Default is True.
    max_bins: Maximum number of bins for histogram. Default is 100.

    Returns:
    matplotlib.axes.Axes
    """
    from views_reporting.visualizations import PlotDistribution

    plotter = PlotDistribution(dataset=dataset)
    return plotter.plot_maximum_a_posteriori(
        entity_id=entity_id,
        time_id=time_id,
        var_name=var_name,
        hdi_alpha=hdi_alpha,
        ax=ax,
        colors=colors,
        plot_kde=plot_kde,
        max_bins=max_bins,
    )


def plot_hdi(
    dataset: _ViewsDataset,
    entity_id: Optional[int] = None,
    time_id: Optional[int] = None,
    var_name: Optional[str] = None,
    alphas: Tuple[float, ...] = (0.9,),
    colors: Optional[List[str]] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Axes:
    """
    Plot distribution with multiple HDIs for a specific entity/time/variable.

    Parameters:
    dataset: The dataset to plot from
    entity_id: Specific entity to plot (None for aggregate)
    time_id: Specific time step to plot (None for aggregate)
    var_name: Variable to plot (required)
    alphas: Tuple of credibility levels to plot
    colors: Optional list of colors for each alpha level
    ax: Matplotlib axes to plot on (creates new if None)

    Returns:
    matplotlib.axes.Axes: The plot axes
    """
    from views_reporting.visualizations import PlotDistribution

    plotter = PlotDistribution(dataset=dataset)
    return plotter.plot_highest_density_intervals(
        entity_id=entity_id,
        time_id=time_id,
        var_name=var_name,
        alphas=alphas,
        colors=colors,
        ax=ax,
    )
