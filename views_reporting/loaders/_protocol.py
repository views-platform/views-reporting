"""PredictionLoader protocol defining the loader interface contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class PredictionLoader(Protocol):
    """Load prediction data from a declared storage format into a Dataset.

    Implementations handle one storage format each (SRP). New formats
    are added by writing a new loader and calling register_loader() (OCP).
    Format is always declared explicitly, never inferred (ADR-003).

    Returns CMDataset or PGMDataset (from views_pipeline_core), typed
    as Any here to avoid coupling the protocol to concrete types.
    """

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> Any:
        """Load predictions for a single rolling origin."""
        ...

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[Any]:
        """Load predictions for multiple rolling origins."""
        ...
