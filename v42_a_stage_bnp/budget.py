from time import time
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_early.native import BudgetStop
class Allocation(Budget):
    def __init__(self,seconds):super().__init__();self.component_deadline=min(self.record['deadline_unix'],time()+seconds)
    def remaining(self):
        left=min(super().remaining(),self.component_deadline-time())
        if left<=0:raise BudgetStop('COMPONENT_ALLOCATION_REACHED_WITHOUT_RESETTING_OVERNIGHT_BUDGET')
        return left
