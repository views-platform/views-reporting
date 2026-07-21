"""month_id ↔ label helper (#232). Epoch: month_id 1 == Jan 1980."""

import pytest

from views_reporting._time import month_id_to_label


@pytest.mark.green_team
def test_epoch_and_known_months():
    assert month_id_to_label(1) == "Jan 1980"
    assert month_id_to_label(12) == "Dec 1980"
    assert month_id_to_label(13) == "Jan 1981"
    assert month_id_to_label(559) == "Jul 2026"
    assert month_id_to_label(594) == "Jun 2029"


@pytest.mark.green_team
def test_accepts_integer_like_floats():
    # month ids arrive float32-cast from some mapping frames (#234); the
    # label must not carry the ".0" form.
    assert month_id_to_label(594.0) == "Jun 2029"


@pytest.mark.red_team
def test_rejects_nonpositive_ids():
    with pytest.raises(ValueError, match="month_id"):
        month_id_to_label(0)
