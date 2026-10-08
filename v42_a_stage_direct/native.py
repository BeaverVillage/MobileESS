"""Unchanged scientific native compiler, with nonbinding incumbent hints."""
import numpy as np
import v42_a_stage_cg.native as cg
from v42_pr134_b1.common import atomic,record
from v42_a_stage_lexcases.policy import OUT
from .freeze import verify

class Native(cg.Native):
    def __init__(self,budget):
        super().__init__(budget);self.freeze_path=OUT/'DIRECT_SOURCE_FREEZE.json';self.live_model=None
    def verify(self):return verify()
    def solve(self,snapshot,folder,component):
        original=cg.materialize
        def wrapped(s,day):
            model,objectives=original(s,day);self.live_model=model
            hints=getattr(self,'hint_point',None)
            if hints is not None and model.NumIntVars:
                if len(hints)!=model.NumVars:raise ValueError('ORIGINAL_INCUMBENT_HINT_AXES_REQUIRED')
                indices=np.flatnonzero(s.vtypes!='C');allvars=model.getVars();variables=[allvars[int(j)] for j in indices]
                values=np.rint(hints[indices]).tolist()
                if any(v<s.lower[j] or v>s.upper[j] for j,v in zip(indices,values)):raise ValueError('INDIVIDUAL_HINTS_MUST_FIT_ORIGINAL_BOXES')
                model.setAttr('VarHintVal',variables,values);model.setAttr('VarHintPri',variables,[1]*len(values));model.update()
                actual=model.getAttr('VarHintVal',variables)
                if not np.array_equal(actual,values):raise ValueError('NATIVE_HINT_READBACK_FAILED')
                atomic(folder/'NONBINDING_INCUMBENT_HINTS.json',dict(PASS=True,columns=len(indices),source=getattr(self,'hint_record',None),
                    heuristic_guidance_only=True,not_pruning_or_feasibility_authority=True,current_query_primal_claimed=False,
                    original_rows_boxes_types_objectives_unchanged=True,hint_priority=1,
                    official_contract='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#varhintval'))
            return model,objectives
        cg.materialize=wrapped
        try:return super().solve(snapshot,folder,component)
        finally:cg.materialize=original;self.live_model=None
