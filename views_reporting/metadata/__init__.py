"""Index-keyed entity metadata accessors (country / PRIO-GRID) from the bundled assets.

Reads committed parquet tables (``metadata/data/``, regenerated dev-side by
``scripts/build_entity_metadata.py``) — no viewser, no service call at render
time (register C-22, ADR-018). Entity-keyed, month-broadcast.
"""

from .entity_metadata import get_isoab_for_index as get_isoab_for_index
from .entity_metadata import get_labels_for_index as get_labels_for_index
from .entity_metadata import get_name_for_index as get_name_for_index
