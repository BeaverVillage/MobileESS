"""Explicit feasible-only downstream contract; never fabricate an LB or gap."""
from functools import wraps
from types import FunctionType
from pathlib import Path
import inspect,linecache,textwrap

POLICY='R025B_NATIVE60_PHASE1000_UB'


def admitted(result):
    return (result.get('policy') in (POLICY,'R025_NATIVE60_PHASE400_UB') and result.get('UB_feasible_only') is True
        and result.get('PASS') is True and result.get('FULL_feasible') is True
        and result.get('P2_calls')==0 and result.get('freeze') is not None
        and result.get('allow_downstream') is True and not result.get('error'))


def verify_ub(result):
    from v44.common import read,verify
    if not admitted(result):raise ValueError('R025B_VERIFIED_UB_ADMISSION_REQUIRED')
    verify([result['freeze'],result['planning']]);freeze=read(result['freeze']['path'])
    if (freeze.get('policy') not in (POLICY,'R025_NATIVE60_PHASE400_UB') or freeze.get('UB_feasible_only') is not True
            or freeze.get('PASS') is not True or freeze.get('accepted') is not True
            or freeze.get('global_gap_certified') is not False):
        raise ValueError('R025B_UB_FREEZE_NOT_INDEPENDENTLY_VERIFIED')
    verify([freeze['physical'],freeze['validated_original_integer_point']])
    physical=read(freeze['physical']['path'])
    if (physical.get('PASS') is not True or physical.get('original_integer_types_restored') is not True
            or physical.get('original_job_population_verified') is not True
            or physical.get('scientific_primal_replay',{}).get('PASS') is not True
            or physical.get('integral_max_residual',1)>1e-5):
        raise ValueError('R025B_UB_PHYSICAL_OR_INTEGER_PROOF_REQUIRED')
    for key in ('day','arm','stage'):
        if freeze.get(key)!=result.get(key):raise ValueError('R025B_UB_BINDING_MISMATCH:'+key)
    if freeze['planning']!=result['planning']:raise ValueError('R025B_UB_PLANNING_BINDING_MISMATCH')
    return freeze


def require_a2(original):
    @wraps(original)
    def require(result,day):
        if result.get('policy')==POLICY and result.get('FULL_feasible') is not True:
            from v44.common import NotReady
            raise NotReady('A2_NO_VERIFIED_FEASIBLE_UB:'+str(result.get('classification','INCONCLUSIVE')))
        if result.get('policy') not in (POLICY,'R025_NATIVE60_PHASE400_UB') or result.get('UB_feasible_only') is not True:return original(result,day)
        from v44.stages import require_parent
        from v44.common import read,verify
        require_parent(result,day=day,arm='B3',stage='A2')
        if result.get('freeze'):
            freeze=verify_ub(result)
            if freeze.get('fixed_M1_plan_sha')!=result.get('fixed_M1_plan_sha'):
                raise ValueError('R025B_A2_FIXED_M1_BINDING_MISMATCH')
        else:
            # M2 consumes the exported identity, bound to its original result.
            verify([result['parent_UB_result']]);parent=read(result['parent_UB_result']['path'])
            verify_ub(parent)
            if result.get('fixed_M1_plan_sha')!=parent.get('fixed_M1_plan_sha'):
                raise ValueError('R025B_A2_EXPORT_M1_BINDING_MISMATCH')
            if result.get('parent_case_sha')!=parent['freeze']['sha256']:
                raise ValueError('R025B_A2_EXPORT_PARENT_MISMATCH')
        return result
    return require


def export_a(original):
    source=textwrap.dedent(inspect.getsource(original))
    old="    if result.get('PASS') is not True or not 0<=result.get('certified_gap',1)<=.005:raise ValueError('INDEPENDENT_A_ACCEPTANCE_REQUIRED')"
    if source.count(old)!=1:raise ValueError('R025B_EXPORT_ADMISSION_SOURCE_DRIFT')
    source=source.replace(old,"    if _r025b_admitted(result):_r025b_verify_ub(result)\n    elif result.get('PASS') is not True or not 0<=result.get('certified_gap',1)<=.005:raise ValueError('INDEPENDENT_A_ACCEPTANCE_REQUIRED')")
    old="    atomic(folder/'AIDC_REFERENCE.json',dict(identity=identity,**aidc));return folder"
    if source.count(old)!=1:raise ValueError('R025B_EXPORT_IDENTITY_SOURCE_DRIFT')
    source=source.replace(old,"    if _r025b_admitted(result):\n        parent_result=Path(request['root'])/'R025B_UB_DOWNSTREAM_RESULT.json'\n        if parent_result.exists():raise FileExistsError('R025B_UB_EXPORT_RESULT_ALREADY_EXISTS')\n        atomic(parent_result,result)\n        identity.update(policy='R025B_NATIVE60_PHASE1000_UB',UB_feasible_only=True,allow_downstream=True,global_gap_certified=False,independent_Global_LB_validated=result['independent_Global_LB_validated'],parent_UB_result=record(parent_result))\n"+old)
    ns=dict(original.__globals__,_r025b_admitted=admitted,_r025b_verify_ub=verify_ub)
    filename=__file__+'.export.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),ns);return ns[original.__name__]


def worker_function(original):
    # Installed before CPU/rebuild/cost wrappers so those wrappers still run.
    import ast
    base=inspect.unwrap(original)
    source=textwrap.dedent(inspect.getsource(base))
    old="independent_Global_LB_validated=bool(result.get('PASS')),FULL_feasible=bool(result.get('PASS'))"
    if source.count(old)!=1:raise ValueError('R025B_WORKER_LB_SOURCE_DRIFT')
    source=source.replace(old,"independent_Global_LB_validated=bool(result.get('independent_Global_LB_validated',result.get('PASS'))),FULL_feasible=bool(result.get('FULL_feasible',result.get('PASS')))")
    tree=ast.parse(source);tree.body[0].decorator_list=[]
    ns={};exec(compile(tree,__file__+'.worker.generated','exec'),ns)
    changed=FunctionType(ns[base.__name__].__code__,base.__globals__,base.__name__,base.__defaults__)
    if original is not base:
        from v44.planning import stage_scope
        if getattr(original,'__wrapped__',None) is not base:raise ValueError('R025B_WORKER_WRAPPER_SOURCE_DRIFT')
        changed=stage_scope(changed)
    return changed
