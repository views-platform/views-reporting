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


# ── Index-keyed metadata mocks (frame path, epic #137) ─────────────────────
# The frame adapter and historical graph call get_isoab_for_index /
# get_name_for_index (index + SpatialLevel) rather than the dataset wrappers.
# These mocks reproduce the deterministic ISO/name values offline.


def mock_isoab_for_index(index, level):
    """Fake isoab DataFrame keyed by a (time, entity) MultiIndex."""
    entity_name = index.names[1]
    entity_ids = sorted(set(index.get_level_values(entity_name)))
    code_map = {
        eid: REAL_ISO_CODES[i % len(REAL_ISO_CODES)]
        for i, eid in enumerate(entity_ids)
    }
    values = [code_map[e] for e in index.get_level_values(entity_name)]
    return pd.DataFrame({"isoab": values}, index=index)


def mock_name_for_index(index, level, with_id=False):
    """Fake name DataFrame keyed by a (time, entity) MultiIndex."""
    entity_name = index.names[1]
    values = [f"Country {e}" for e in index.get_level_values(entity_name)]
    return pd.DataFrame({"name": values}, index=index)


def cm_target_frame_from_df(df, target="ged_sb"):
    """Build a views_frames.TargetFrame from a CM historical (scalar) df."""
    from views_frames import SpatialLevel, SpatioTemporalIndex, TargetFrame

    time = df.index.get_level_values("month_id").to_numpy(dtype=np.int64)
    unit = df.index.get_level_values("country_id").to_numpy(dtype=np.int64)
    values = np.asarray(df[target].to_numpy(), dtype=np.float32).reshape(-1, 1)
    index = SpatioTemporalIndex(time=time, unit=unit, level=SpatialLevel.CM)
    return TargetFrame(values, index)


# ── views-frames bridge (epic #137) ───────────────────────────────────────
# Convert a synthetic CM forecast DataFrame (array-valued `pred_<target>` cells)
# into a views_frames.PredictionFrame. Rows are (month, country) TIME-MAJOR so they
# line up with SpatioTemporalIndex ordering and with the MultiIndex from_product
# used by the synthetic builders. Reused by the S2 equivalence oracle and later
# frame-path tests. Imports views_frames lazily so conftest stays importable even
# if the optional dep is absent in an exotic environment.
def cm_frame_from_df(df, target="ged_sb"):
    """Build a single-target views_frames.PredictionFrame from a CM forecast df."""
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    months = df.index.get_level_values("month_id").unique().tolist()
    countries = df.index.get_level_values("country_id").unique().tolist()
    values = np.stack(
        [df.loc[(m, c), f"pred_{target}"] for m in months for c in countries]
    ).astype(np.float32)
    index = SpatioTemporalIndex(
        time=np.repeat(months, len(countries)).astype(np.int64),
        unit=np.tile(countries, len(months)).astype(np.int64),
        level=SpatialLevel.CM,
    )
    return PredictionFrame(values, index)
