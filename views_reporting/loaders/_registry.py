"""Format-to-loader dispatch registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from views_reporting.loaders._protocol import PredictionLoader

_LOADER_REGISTRY: dict[str, type[PredictionLoader]] = {}


def register_loader(
    format_name: str, loader_cls: type[PredictionLoader]
) -> None:
    """Register a loader class for a declared prediction format.

    Raises ValueError on duplicate registration to prevent silent
    overwrites (ADR-008 fail-loud).
    """
    if format_name in _LOADER_REGISTRY:
        raise ValueError(
            f"Loader already registered for format '{format_name}': "
            f"{_LOADER_REGISTRY[format_name].__name__}. "
            f"Cannot register {loader_cls.__name__}."
        )
    _LOADER_REGISTRY[format_name] = loader_cls


def get_loader(format_name: str) -> PredictionLoader:
    """Return an instantiated loader for the declared format.

    Raises ValueError if the format is not registered, listing
    available formats (ADR-003 fail-loud, no inference).
    """
    if format_name not in _LOADER_REGISTRY:
        registered = sorted(_LOADER_REGISTRY.keys())
        raise ValueError(
            f"No loader registered for prediction_format='{format_name}'. "
            f"Registered formats: {registered}"
        )
    return _LOADER_REGISTRY[format_name]()
