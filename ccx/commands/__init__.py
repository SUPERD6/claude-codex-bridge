"""ccx commands, one module per group; each has register(sub) for its parser part."""
from . import delegation, install, memory, records, ui, workqueue

MODULES = (delegation, memory, install, records, workqueue, ui)
