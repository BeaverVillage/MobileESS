"""Narrow D0 user-authorized pilot admission on the unchanged canonical ledger."""
from copy import deepcopy
import math

import numpy as np

from .budget import IntegrationBudget
from .unified_resource import UnifiedResearchBudget
from .d0_case import require_case
from .m_engine import matrix_sha,domain_sha


def native_binding(model):
    model.update()
    domain={key:np.asarray(model.getAttr(attr)) for attr,key in (
        ('LB','lower'),('UB','upper'),('Obj','objective'),('VType','types'),('VarName','names'),
        ('RHS','rhs'),('Sense','sense'),('ConstrName','row_names'))}
    domain['constant']=np.asarray(model.ObjCon)
    return dict(matrix_sha=matrix_sha(model.getA().tocsr()),domain_sha=domain_sha(domain),
        objective_sense=int(model.ModelSense),rows=int(model.NumConstrs),columns=int(model.NumVars),
        nonzeros=int(model.NumNZs),Threads=int(model.Params.Threads))


class D0PilotBudget(UnifiedResearchBudget):
    """No reset, no old manifest rewrite, no reopening a historical session."""
    def __init__(self,manifest,*,stage_case_sha,source_input_sha,pilot_limit=25.,return_reserve=30.):
        super().__init__()
        require_case(manifest,stage='A1')
        if (not math.isfinite(float(pilot_limit)) or not math.isfinite(float(return_reserve)) or
            not 0.<pilot_limit<=25. or return_reserve<30.):
            raise ValueError('D0_SHORT_PILOT_AND_RETURN_RESERVE_REQUIRED')
        self.d0_manifest=deepcopy(manifest)
        self.d0_stage_case_sha=stage_case_sha;self.d0_source_input_sha=source_input_sha
        self.pilot_limit=float(pilot_limit);self.return_reserve=float(return_reserve)
        self.pilot_started_used=self.used()
        if self.remaining(reserve=return_reserve)<pilot_limit:
            raise RuntimeError('D0_PILOT_CANONICAL_BUDGET_WITH_RETURN_RESERVE_REQUIRED')

    def solve(self,model,*,label,cap,callback=None):
        require_case(self.d0_manifest,stage='A1')
        context=deepcopy(getattr(self,'stage_context',{}))
        if (not label.startswith('D0_A1_ORIGINAL_') or
            context.get('D0_case_sha')!=self.d0_manifest['identity']['case_sha'] or
            context.get('D0_science_sha')!=self.d0_manifest['identity']['science_sha'] or
            context.get('stage_case_sha')!=self.d0_stage_case_sha or
            context.get('source_input_sha')!=self.d0_source_input_sha):
            raise ValueError('D0_EXACT_USER_AUTHORIZED_A1_ONLY')
        used=self.used()-self.pilot_started_used
        if (not math.isfinite(float(cap)) or cap<=0 or cap>self.pilot_limit-used+1e-7 or
            cap>self.remaining(reserve=self.return_reserve)):
            raise RuntimeError('D0_PILOT_LIMIT_OR_CANONICAL_RETURN_RESERVE_GATE')
        binding=native_binding(model)
        if binding['Threads']!=1 or binding['objective_sense']!=1:
            raise ValueError('D0_ORIGINAL_MINIMIZATION_ONE_THREAD_REQUIRED')
        context.update(D0_manifest_sha=self.d0_manifest['manifest_sha'],
            current_native_binding=binding,historical_prefix_gate_used=False,
            user_authorization='D0_STATE_CONDITIONED_PLANNING_20261015',usage_reset=False)
        with self.exclusive_worker():
            before=len(self.document['calls'])
            with self._transaction():self.document['active_stage_context']=context
            try:
                return IntegrationBudget.solve(self,model,label=label,cap=cap,callback=callback)
            finally:
                with self._transaction():
                    if len(self.document['calls'])>before:
                        self.document['calls'][-1].update(session_identity=deepcopy(self.document['identity']),
                            stage_context=context,D0_identity=deepcopy(self.d0_manifest['identity']),
                            D0_manifest_sha=self.d0_manifest['manifest_sha'],usage_reset=False,
                            bound_scope='CURRENT_D0_FIXED_MESS_SOURCE_AUTHORIZED_A_ONLY')
                    self.document['active_stage_context']=None
