"""Restore continuous feasibility with saved exact integer decisions and a proven bound."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import FunctionType
from unittest.mock import patch
from copy import deepcopy
from fractions import Fraction
import ast,gzip,pickle
import numpy as np
from v44.common import read,record,verify,atomic


def fixed_model(typed,point,exact_lb):
    from v44_recovery_r029.integer_repair import fixed_snapshot
    fixed,integer,residual=fixed_snapshot(typed,point)
    # A redundant *certified* bound prevents the known feasibility-tolerance
    # undershoot. It never comes from the restricted MIP's progress ObjBound.
    objective=typed.objectives[0]
    coefficients=objective.coefficients()
    if objective.name!='rho' or objective.constant!=0 or len(coefficients)!=1:
        raise ValueError('R044_SINGLE_ORIGINAL_RHO_OBJECTIVE_REQUIRED')
    j,c=next(iter(coefficients.items()))
    if c!=1 or integer[j] or Fraction(float(exact_lb))!=exact_lb:
        raise ValueError('R044_EXACT_DYADIC_CONTINUOUS_RHO_BOUND_REQUIRED')
    lower=fixed.lower.copy();lower[j]=max(lower[j],float(exact_lb))
    if lower[j]>fixed.upper[j]:raise ValueError('R044_CERTIFIED_BOUND_OUTSIDE_ORIGINAL_BOX')
    return replace(fixed,lower=lower).require(),integer,residual,j


def repair(native,typed,request,output,exact_lb):
    from .operations import PARENT
    from v42_a_stage_phase1.core import primal_replay
    from v42_a_stage_lexfull.runner import objective_value
    parent=PARENT/'A2/OUTPUT';identity=read(parent/'P1/INTEGER_CONTROL/MODEL_IDENTITY.json')
    if typed.fingerprint()!=identity['original_snapshot_sha256']:
        raise ValueError('R044_RESTORED_ORIGINAL_INTEGER_MODEL_DRIFT')
    result=read(parent/'P1/INTEGER_CONTROL/NATIVE_RESULT.json');verify([result['raw_attributes']])
    with np.load(result['raw_attributes']['path'],allow_pickle=False) as raw:point=raw['X'].copy()
    before=primal_replay(typed,point);upper=objective_value(typed,point,'rho')
    if not before['PASS'] or not upper<exact_lb:
        raise ValueError('R044_ONLY_DIAGNOSED_TOLERATED_ROW_UNDERSHOOT')
    fixed,integer,residual,j=fixed_model(typed,point,exact_lb)
    if residual!=0 or not 0<before['max_row_violation']<=before['tolerance']:
        raise ValueError('R044_EXACT_SAVED_INTEGER_DECISIONS_REQUIRED')
    callback=native.incumbent_callback;native.incumbent_callback=None
    try:rec,raw=native.solve(fixed,Path(output)/'EXACT_CONTINUOUS_REPAIR','INTEGER_CONTROL')
    finally:native.incumbent_callback=callback
    if 'X' not in raw:raise ValueError('R044_CONTINUOUS_REPAIR_NO_POINT')
    x=raw['X'];after=primal_replay(typed,x);repaired_ub=objective_value(typed,x,'rho')
    same=bool(np.array_equal(x[integer],point[integer]))
    passed=bool(after['PASS'] and same and repaired_ub>=exact_lb)
    atomic(Path(output)/'EXACT_CONTINUOUS_REPAIR_CERTIFICATE.json',dict(PASS=passed,
        original_raw=result['raw_attributes'],original_integer_model_sha=typed.fingerprint(),
        repair_model_sha=fixed.fingerprint(),original_rows_before=before,original_rows_after=after,
        saved_integer_decisions_exact=True,integer_decisions_unchanged=same,
        exact_original_UB=str(upper),exact_repaired_UB=str(repaired_ub),exact_certified_LB=str(exact_lb),
        bound_origin=record(parent/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json'),
        redundant_certified_rho_lower_bound_column=int(j),restricted_ObjBound_not_used=True,
        native_result=record(Path(output)/'EXACT_CONTINUOUS_REPAIR/NATIVE_RESULT.json'),
        original_tolerances_unchanged=True,original_constraints_relaxed=False,
        full_original_physical_and_gap_validation_required=True,Native_clock_reset=False))
    if not passed:raise ValueError('R044_ORIGINAL_ROWS_INTEGER_OR_CERTIFIED_BOUND_REPLAY_FAILED')
    return rec,raw


def load_state(request,budget):
    from .operations import PARENT,validate_parent
    from v44_recovery_r029.voltage_policy import ACTIVE
    validate_parent();parent=PARENT/'A2';output=Path(request['output'])
    old=read(parent/'request.json')
    if request['M1_result']!=record(PARENT/'M1/RESULT.json'):
        raise PermissionError('R044_SAME_COMPLETED_M1_REQUIRED')
    for name in ('NATIVE_INPUT.json','WINDOWS.json'):
        a=record(Path(old['input_folder'])/name);b=record(Path(request['input_folder'])/name)
        if (a['sha256'],a['bytes'])!=(b['sha256'],b['bytes']):raise ValueError('R044_INPUT_DRIFT')
    output.mkdir(parents=True,exist_ok=False);(output/'STATIC').mkdir()
    with gzip.open(parent/'OUTPUT/STATIC/P1_CLOSED_STATE.pkl.gz','rb') as stream:state=pickle.load(stream)
    # This checkpoint never relaxed a voltage row. Reuse only that strict model.
    policy=read(parent/'OUTPUT/R029_CONDITIONAL_VOLTAGE_PROGRESS.json')
    if policy['approved_rows']:raise PermissionError('R044_STRICT_PARENT_MODEL_ONLY')
    controller=ACTIVE.get()
    if controller is None:raise PermissionError('R044_ORIGINAL_A2_VOLTAGE_SCOPE_REQUIRED')
    controller.bind(state)
    for name in ('PHASE_I_ZERO_CERTIFICATE.json','P1_RESULT.json','A_PREPARE_RECEIPT.json',
                 'INITIAL_VERIFICATION.json','BLOCK_PRICING_ORACLE_VERIFICATION.json'):
        value=read(parent/'OUTPUT'/name);atomic(output/name,value)
    original_policy=read(parent/'OUTPUT/A2_MODEL_VOLTAGE_POLICY.json')
    atomic(output/'A2_MODEL_VOLTAGE_POLICY.json',dict(original_policy,
        initial_state_built_fresh=False,old_A2_model_active_rows_dual_or_clock_imported=True,
        original_policy=record(parent/'OUTPUT/A2_MODEL_VOLTAGE_POLICY.json'),
        checkpoint_resumed=True,conditional_execution=controller.report()))
    ledger=read(parent/'NATIVE_RUNTIME_LEDGER.json')
    budget.calls=deepcopy(ledger['calls']);budget.costs=deepcopy(ledger['costs'])
    budget.native_used=ledger['measured_Native_Runtime'];budget.started=budget.clock()-ledger['wall_seconds']
    persist=budget.persist
    def continued_persist():
        persist();value=read(budget.path)
        value.update(checkpoint_resume=True,parent_ledger=record(parent/'NATIVE_RUNTIME_LEDGER.json'),
            inherited_Native_seconds=ledger['measured_Native_Runtime'],Native_clock_reset=False,
            historical_costs_reused=True,resumed_same_stage_budget=True,inherited_completed_calls=len(ledger['calls']))
        atomic(budget.path,value)
    budget.persist=continued_persist
    budget.persist()
    atomic(output/'R044_CLOSED_P1_RESTORATION.json',dict(PASS=True,
        state=record(parent/'OUTPUT/STATIC/P1_CLOSED_STATE.pkl.gz'),
        parent_ledger=record(parent/'NATIVE_RUNTIME_LEDGER.json'),
        inherited_Native_seconds=budget.native_used,Native_total_ceiling=5400.,Native_clock_reset=False,
        Phase_I_and_full_pricing_repeated=False,old_M1_reoptimized=False))
    return state


def priced(request):
    from .operations import PARENT
    result=read(PARENT/'A2/OUTPUT/P1_RESULT.json');verify([result['full_pricing']])
    value=read(result['full_pricing']['path'])
    if not value['no_negative_omitted_block_certified']:raise ValueError('R044_COMPLETE_P1_CLOSURE_REQUIRED')
    return value


def adapt_tree(tree):
    """Replace only restoration/search dispatch; all original acceptance stays."""
    counts=dict(prepare=0,phase=0,integer=0)
    class Restore(ast.NodeTransformer):
        def visit_Assign(self,node):
            if isinstance(node.value,ast.Call):
                call=node.value
                if isinstance(call.func,ast.Name) and call.func.id=='prepare':
                    counts['prepare']+=1;node.value=ast.parse('_r044_load_state(request,budget)',mode='eval').body
                elif isinstance(call.func,ast.Subscript) and isinstance(call.func.value,ast.Name) and call.func.value.id=='phase_group':
                    counts['phase']+=1;return ast.parse('priced=_r044_priced(request)').body[0]
                elif isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=='native' and call.func.attr=='solve':
                    counts['integer']+=1;node.value=ast.parse('_r044_repair(native,typed,request,output,exact_lb)',mode='eval').body
            return self.generic_visit(node)
    result=Restore().visit(deepcopy(tree))
    if counts!=dict(prepare=1,phase=1,integer=1):raise ValueError('R044_EXACT_A2_DISPATCH_BOUNDARY_DRIFT:'+repr(counts))
    return ast.fix_missing_locations(result)


@contextmanager
def scope():
    from v44 import a2
    from v44.frozen.v43_a2 import adapter
    original=a2.scope;source_tree=adapter.source_tree
    def tree(module,name):
        value=source_tree(module,name)
        return adapt_tree(value) if module.__name__=='v42_may_campaign_native90.a_stage' and name=='run' else value
    @contextmanager
    def continued(request,m1):
        with patch.object(adapter,'source_tree',tree),original(request,m1) as run:
            ns=dict(run.__globals__,_r044_load_state=load_state,_r044_priced=priced,_r044_repair=repair)
            yield FunctionType(run.__code__,ns,run.__name__,run.__defaults__,run.__closure__)
    with patch.object(a2,'scope',continued):yield
