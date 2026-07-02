"""Index-keyed entity metadata accessors (country / PRIO-GRID) via the viewser query API.

The legacy dataset-parameter accessor surface was deleted as dead code
(register C-114, epic #137) — only the ``*_for_index`` edge remains.
"""

from .entity_metadata import get_isoab_for_index as get_isoab_for_index
from .entity_metadata import get_name_for_index as get_name_for_index
