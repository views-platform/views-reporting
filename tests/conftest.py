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

    np.random.seed(42)
    idx = pd.MultiIndex.from_tuples(
        [(528, 1), (528, 2), (529, 1), (529, 2), (530, 1), (530, 2)],
        names=["month_id", "country_id"],
    )
    samples = [np.random.normal(5, 2, 50) for _ in range(6)]
    df = pd.DataFrame({"pred_ged_sb": samples}, index=idx)
    return CMDataset(source=df)
