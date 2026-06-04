"""PredictionLoader protocol defining the loader interface contract."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    from views_pipeline_core.data.handlers import CMDataset, PGMDataset


class PredictionLoader(Protocol):
    """Load prediction data from a declared storage format into a Dataset.

    Implementations handle one storage format each (SRP). New formats
    are added by writing a new loader and calling register_loader() (OCP).
    Format is always declared explicitly, never inferred (ADR-003).

    Returns a CMDataset or PGMDataset (from views_pipeline_core). The
    containers are imported only under TYPE_CHECKING so the protocol
    module stays import-light and does not trigger a pipeline-core import
    at load time.
    """

    def load_single_origin(
        self,
        path: Path,
        level: str,
        targets: list[str],
    ) -> Union[CMDataset, PGMDataset]:
        """Load predictions for a single rolling origin."""
        ...

    def load_multi_origin(
        self,
        paths: list[Path],
        level: str,
        targets: list[str],
    ) -> list[Union[CMDataset, PGMDataset]]:
        """Load predictions for multiple rolling origins."""
        ...
