from ..core.adapter import Adapter
from .acs import AcsAdapter
from .boundaries import BoundariesAdapter
from .clarity import ClarityAdapter
from .fec import FecAdapter
from .history import HistoryAdapter
from .legislators import LegislatorsAdapter
from .seeds import OfficialCandidatesAdapter, StateOfficesAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    a.id: a
    for a in (
        StateOfficesAdapter,
        OfficialCandidatesAdapter,
        LegislatorsAdapter,
        FecAdapter,
        HistoryAdapter,
        BoundariesAdapter,
        AcsAdapter,
        ClarityAdapter,
    )
}
