# VIEWS Pipeline Core: Posterior Statistics Module

> File: `views_reporting/statistics/statistics.py`  
> Class:  
    - `PosteriorDistributionAnalyzer`  

This module provides statistical utilities for summarizing posterior distributions
from probabilistic model outputs (MAP, HDIs, zero-mass handling).

It supports uncertainty-aware workflows common in conflict forecasting: zero-inflated
severity distributions, heavy-tailed event intensities, and probabilistic ensemble
outputs.

> **Note (C-108 / #72):** hierarchical forecast *reconciliation* no longer lives here.
> The reconciler is now `views_frames_reconcile` in **views-frames** (frames-native,
> numpy, parity-proven against the former `ForecastReconciler`); pipeline-core consumes
> it via an injected `Reconciler` protocol. Reporting renders; it does not reconcile.

---

## Contents

- [PosteriorDistributionAnalyzer](#posteriordistributionanalyzer)
    - [Overview](#overview)
    - [Key Features](#key-features)
    - [API](#api)
    - [Usage Examples](#usage-examples)
- [Error Handling & Logging](#error-handling--logging)
- [FAQ](#faq)

---

## PosteriorDistributionAnalyzer

### Overview

`PosteriorDistributionAnalyzer` computes empirical posterior summaries from raw sample arrays. It extracts:  
- MAP (maximum a posteriori) via histogram mode  
- Highest Density Intervals (HDIs) at configurable credible levels  
- Zero-mass proportion (for zero-inflated conflict count processes)  
- Structural guarantees: MAP contained in narrowest HDI; HDIs are nested  

Designed for post-prediction uncertainty interpretation: fatality intensity, event counts, log-scaled targets, or probabilistic ensemble outputs.

### Key Features

- Robust sample cleaning (filters NaN/inf)  
- Credible mass validation with automatic sorting  
- Zero-inflation shortcut: enforce MAP = 0 when mass at zero exceeds threshold  
- Fast empirical HDI computation using shortest interval search  
- Automatic HDI nesting (outer contains inner)  
- MAP containment enforced with minimal shifts  
- Built-in plotting and formatted printing  
- Multi-distribution test suite (normal, heavy-tailed, skewed, multimodal)  

### API

```python
analyzer = PosteriorDistributionAnalyzer()
summary = analyzer.analyze(
        samples=samples_array,
        credible_masses=(0.5, 0.95, 0.99),
        zero_mass_threshold=0.3,
        bins=100
)
summary_dict = analyzer.summary_dict()
analyzer.print_summary()
analyzer.plot_summary(save_path='posterior.png')
```

### Usage Examples

#### Basic Analysis

```python
import numpy as np
from views_reporting.statistics import PosteriorDistributionAnalyzer

samples = np.random.lognormal(mean=1.2, sigma=0.8, size=10_000)
analyzer = PosteriorDistributionAnalyzer()
result = analyzer.analyze(samples, credible_masses=(0.5, 0.9))
print(f"MAP: {result['map']:.2f}")
for mass, (lo, hi) in zip((0.5, 0.9), result['hdis']):
        print(f"{int(mass*100)}% HDI: [{lo:.2f}, {hi:.2f}]")
```

#### Zero-Inflated Distribution

```python
base = np.random.poisson(0.4, size=8000)
samples = np.where(np.random.rand(8000) < 0.6, 0, base)  # 60% structural zeros
analyzer = PosteriorDistributionAnalyzer()
summary = analyzer.analyze(samples, zero_mass_threshold=0.5)
print(f"Mass at zero: {summary['mass_at_zero']:.1%}, MAP: {summary['map']}")
```

#### Plot Posterior

```python
analyzer.plot_summary(save_path='outputs/posterior_summary.png')
```

---

## Error Handling & Logging

- **ERROR:** Invalid inputs (all NaN, bad credible mass)  
- **WARNING:** Missing summary before plotting / printing  
- **INFO:** Test suite completions  
- **DEBUG:** Interval adjustments, MAP decisions, expansion operations  

Configure via project logging: `views_pipeline_core/configs/logging.yaml`.

---

## FAQ

| **Question**                                   | **Answer**                                                                 |
|------------------------------------------------|-----------------------------------------------------------------------------|
| Why histogram MAP instead of mean?            | Mode better captures most probable intensity in skewed/zero-inflated data. |
| Can HDIs handle multimodal distributions?     | Shortest-interval HDIs may bridge modes; interpret accordingly.            |
