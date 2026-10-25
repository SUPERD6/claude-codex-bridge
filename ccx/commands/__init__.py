"""ccx commands, one module per group; each has register(sub) for its parser part."""
from . import delegation, discuss, install, memory, records, ui, workqueue

MODULES = (delegation, memory, install, records, workqueue, ui, discuss)
