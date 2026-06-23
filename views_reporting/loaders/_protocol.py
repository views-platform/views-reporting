"""PredictionLoader protocol defining the loader interface contract."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from views_frames import PredictionFrame


class PredictionLoader(Protocol):
    """Load prediction data from a declared storage format into frames.

    Implementations handle one storage format each (SRP). New formats
    are added by writing a new loader and calling register_loader() (OCP).
    Format is always declared explicitly, never inferred (ADR-003).

    Returns a ``dict[str, PredictionFrame]`` mapping each requested target to
    its single-target ``views_frames.PredictionFrame`` (a frame is single-target
    by contract; epic #137). ``views_frames`` is imported only under
    TYPE_CHECKING so the protocol module stays import-light.
    """

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> dict[str, PredictionFrame]:
        """Load predictions for a single rolling origin (target → frame)."""
        ...

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[dict[str, PredictionFrame]]:
        """Load predictions for multiple rolling origins."""
        ...
