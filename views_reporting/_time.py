"""VIEWS month_id ↔ human date label (epoch: month_id 1 = January 1980).

Tiny shared helper (#232): both the mapping renderers (figure titles) and the
report templates (headings) need to show a month_id as a date a reader can
parse. Kept dependency-free and separate from report/mapping modules so either
side can import it without coupling to the other.
"""

from __future__ import annotations

_EPOCH_YEAR = 1980  # month_id 1 == January 1980

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def month_id_to_label(month_id: int) -> str:
    """``594`` → ``"Jun 2029"``. Fails loud on non-positive ids (ADR-008) —
    a zero/negative month_id is an upstream indexing error, not a date."""
    m = int(month_id)
    if m < 1:
        raise ValueError(f"month_id must be >= 1 (1 == Jan 1980); got {month_id!r}")
    year, month0 = divmod(m - 1, 12)
    return f"{_MONTHS[month0]} {_EPOCH_YEAR + year}"
