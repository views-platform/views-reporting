from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "red_team: adversarial tests (ADR-005)")
    config.addinivalue_line("markers", "green_team: correctness tests (ADR-005)")
    config.addinivalue_line("markers", "beige_team: realistic usage tests (ADR-005)")


@pytest.fixture
def mock_views_dataset():
    """Mock _ViewsDataset with tensor support."""
    np.random.seed(42)
    ds = MagicMock()
    ds.targets = ["pred_ged_sb"]
    ds.features = ["feature_1"]
    ds.is_prediction = True
    ds.sample_size = 100
    ds._time_id = "month_id"
    ds._entity_id = "country_id"
    ds._time_values = pd.Series([528, 529, 530])
    ds._entity_values = pd.Series([1, 2, 3])
    tensor = np.random.normal(5, 2, (3, 3, 100, 1))
    ds.to_tensor.return_value = tensor
    ds._get_entity_index.return_value = 0
    ds._get_time_index.return_value = 0
    return ds


@pytest.fixture
def cm_prediction_dataset():
    """Real CMDataset with array-valued cells for integration tests."""
    try:
        from views_pipeline_core.data.handlers import CMDataset
    except ImportError:
        pytest.skip("views_pipeline_core not installed")

    df = build_cm_forecast_df(n_months=3, n_countries=2, n_samples=50, seed=42)
    return CMDataset(source=df)


# ── Shared synthetic data builders ───────────────────────────────────────

REAL_ISO_CODES = [
    "TZA", "CAN", "USA", "KAZ", "UZB", "PNG", "IDN", "ARG", "FJI", "BRA",
]


def build_cm_forecast_df(
    n_months=3,
    n_countries=5,
    n_samples=20,
    targets=("ged_sb",),
    month_start=528,
    country_ids=None,
    seed=42,
):
    """Build a synthetic CM forecast DataFrame with array-valued cells.

    Returns a DataFrame (not a CMDataset) so callers that lack
    views_pipeline_core can still use it for non-dataset tests.
    """
    rng = np.random.RandomState(seed)
    if country_ids is None:
        country_ids = list(range(1, n_countries + 1))
    months = list(range(month_start, month_start + n_months))

    idx = pd.MultiIndex.from_product(
        [months, country_ids], names=["month_id", "country_id"]
    )
    data = {}
    for target in targets:
        col = f"pred_{target}"
        data[col] = [
            np.abs(rng.normal(3.0, 1.5, n_samples)).astype(np.float32)
            for _ in range(len(idx))
        ]
    return pd.DataFrame(data, index=idx)


def build_cm_historical_df(
    n_months=6,
    n_countries=5,
    targets=("ged_sb",),
    month_start=522,
    country_ids=None,
    seed=99,
):
    """Build a synthetic CM historical DataFrame with scalar values."""
    rng = np.random.RandomState(seed)
    if country_ids is None:
        country_ids = list(range(1, n_countries + 1))
    months = list(range(month_start, month_start + n_months))

    idx = pd.MultiIndex.from_product(
        [months, country_ids], names=["month_id", "country_id"]
    )
    data = {}
    for target in targets:
        data[target] = np.abs(rng.normal(2.0, 1.0, len(idx))).astype(np.float32)
    return pd.DataFrame(data, index=idx)


def mock_isoab_for_df(df, entity_id="country_id", time_id="month_id"):
    """Build a fake isoab DataFrame using real ISO codes from the shapefile."""
    flat = df.reset_index()[[time_id, entity_id]].drop_duplicates()
    entity_ids = sorted(flat[entity_id].unique())
    code_map = {
        eid: REAL_ISO_CODES[i % len(REAL_ISO_CODES)]
        for i, eid in enumerate(entity_ids)
    }
    flat["isoab"] = [code_map[eid] for eid in flat[entity_id]]
    return flat.set_index([time_id, entity_id])


def mock_name_for_df(df, entity_id="country_id", time_id="month_id"):
    """Build a fake name DataFrame matching the dataset's index."""
    flat = df.reset_index()[[time_id, entity_id]].drop_duplicates()
    flat["name"] = [f"Country {eid}" for eid in flat[entity_id]]
    return flat.set_index([time_id, entity_id])
