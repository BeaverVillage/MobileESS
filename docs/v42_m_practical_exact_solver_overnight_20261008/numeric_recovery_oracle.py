"""One evidence-triggered numeric stability rescue of the same original LP."""
import primal_recovery_oracle as prior
from practical_support import *

class LPOracle(prior.LPOracle):
    def __init__(self):
        super().__init__();self.m.Params.NumericFocus=3
    def solve(self,node):
        result=super().solve(node)
        result['numerical_recovery']=dict(NumericFocus=3,source_SHA256=sha(__file__),same_original_matrix_bounds_objective=True,registered_root_Method=0,child_Method=1,tolerances_unchanged=True,no_objective_scaling=True)
        atomic(prior.registered.OUT/result['receipt'],result);return result
core=prior.core
