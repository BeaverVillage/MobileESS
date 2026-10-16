"""Every Arm executes its own frozen Known plan and the same Unknown policy."""
from v43_actual.controller import V43EventController


class UniformArmController(V43EventController):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        # In the inherited engine this flag selects command/policy dispatch,
        # not Source change rights. B0/B2 previously selected legacy FIFO-only.
        # Frozen Known commands, policy C0/C1 and all permission/hard guards
        # now apply identically; this grants no new placement/migration right.
        self.flexible=True
