from time import perf_counter
from .native import BudgetStop

class Budget:
    def __init__(self, *, started=None, native_limit=900):
        self.started=perf_counter() if started is None else started
        self.native_limit=native_limit
        self.native_seconds=0.
    def accounted(self):return max(perf_counter()-self.started,self.native_seconds)
    def remaining(self):
        value=min(900-(perf_counter()-self.started),self.native_limit-self.native_seconds)
        if value<=0:raise BudgetStop('EARLY_SINGLE_CUMULATIVE_900_BUDGET')
        return value
    def charge(self,seconds):self.native_seconds+=seconds
    def reservation(self,workers):return self.remaining()/workers
