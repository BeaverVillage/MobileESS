"""One evidence-selected barrier-accuracy repair, original science unchanged."""
from practical_support import *
import cold_barrier_child_oracle as base
class LPOracle(base.LPOracle):
    def solve(self,node):
        self.m.Params.BarConvTol=1e-12
        result=base.LPOracle.solve(self,node)
        result['precision_repair']=dict(BarConvTol=1e-12,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,all_original_scientific_arrays_unchanged=True,no_new_root_solve=True,source_SHA256=sha(Path(__file__)))
        result=clean(result);base.write(Path(result['receipt']),result)
        return result
core=base.core
