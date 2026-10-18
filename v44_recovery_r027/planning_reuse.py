"""Reuse proven P1 closure and integer decisions; repair continuous values only."""
import gzip,pickle,inspect,linecache,textwrap
from copy import deepcopy
from pathlib import Path
import numpy as np
from v44.common import read,record,verify,atomic


def load_state(request,budget):
    parent=Path(request['planning_repair_parent']);output=Path(request['output'])
    if request['arm']!='B1' or parent.parents[2].name!=request['day']:
        raise PermissionError('R027_SAME_DATE_B1_REUSE_REQUIRED')
    failure=read(parent/'RESULT.json');producer=read(parent/'OUTPUT/A_RESULT.json')
    if failure.get('error')!="ValueError('NEGATIVE_ANONYMOUS_GPU')" or not producer.get('PASS'):
        raise PermissionError('R027_ONLY_DIAGNOSED_ACCEPTED_PLANNING_EXPORT_FAILURE')
    old=read(parent/'request.json');verify(old['sources'])
    for name in ('NATIVE_INPUT.json','WINDOWS.json'):
        old_input=record(Path(old['input_folder'])/name);new_input=record(Path(request['input_folder'])/name)
        if (old_input['bytes'],old_input['sha256'])!=(new_input['bytes'],new_input['sha256']):
            raise ValueError('R027_PLANNING_INPUT_IDENTITY_DRIFT')
    p=parent/'OUTPUT';state_path=p/'STATIC/P1_CLOSED_STATE.pkl.gz'
    with gzip.open(state_path,'rb') as stream:state=pickle.load(stream)
    source_ledger=read(parent/'NATIVE_RUNTIME_LEDGER.json')
    if source_ledger.get('inflight') or source_ledger['measured_Native_Runtime']>=5400:
        raise ValueError('R027_PLANNING_SOURCE_NATIVE_LEDGER_NOT_REUSABLE')
    budget.calls=deepcopy(source_ledger['calls']);budget.native_used=source_ledger['measured_Native_Runtime'];budget.persist()
    for name in ('PHASE_I_ZERO_CERTIFICATE.json','P1_RESULT.json'):
        value=read(p/name)
        if not value.get('PASS'):raise ValueError('R027_PARENT_P1_CERTIFICATE_FAILED:'+name)
        atomic(output/name,value)
    cert=read(p/'P1_RESULT.json');verify([cert['full_pricing']]);priced=read(cert['full_pricing']['path'])
    if not priced['no_negative_omitted_block_certified']:raise ValueError('R027_PARENT_FULL_PRICING_NOT_CLOSED')
    atomic(output/'R027_PLANNING_REUSE_ADMISSION.json',dict(PASS=True,state=record(state_path),
        accepted_producer=record(p/'A_RESULT.json'),original_failure=record(parent/'RESULT.json'),
        previous_Native_ledger=record(parent/'NATIVE_RUNTIME_LEDGER.json'),
        previous_Native_seconds=budget.native_used,total_Native_ceiling=5400,
        original_P1_closure=record(p/'P1_RESULT.json'),new_PhaseI_or_P1_search=False,
        fixed_original_integer_continuous_repair=True,all_physical_and_gap_checks_required=True))
    return state,priced


def load_point(request,typed,native,output):
    from .integer_repair import restore
    parent=Path(request['planning_repair_parent']);producer=read(parent/'OUTPUT/A_RESULT.json')
    ref=producer['incumbent']['point'];verify([ref])
    with np.load(ref['path'],allow_pickle=False) as arrays:point=arrays['X'].copy()
    from v42_a_stage_practical.integer_model import restore_types
    # Equality with the original saved integer model is checked before optimize.
    identity=read(parent/'OUTPUT/P1/INTEGER_CONTROL/MODEL_IDENTITY.json')
    if typed.fingerprint()!=identity['original_snapshot_sha256']:
        raise ValueError('R027_REUSED_ORIGINAL_TYPED_SNAPSHOT_DRIFT')
    result=restore(native,typed,point,Path(output)/'PARENT_EXACT_INTEGER_REPAIR')
    if result is None:raise ValueError('R027_EXPECTED_FRACTIONAL_INTEGER_REPAIR')
    return result


def run_reused(function):
    source=textwrap.dedent(inspect.getsource(function))
    edits={
        "            state = prepare(dict(request, _budget=budget), progress)":"            state,_r027_priced=_r027_load_state(request,budget)",
        "        state, _, expanded, priced = phase_group['run'](native, state, day)":"        priced=_r027_priced",
        "        rec, raw = native.solve(typed, output / 'P1/INTEGER_CONTROL', 'INTEGER_CONTROL')":"        rec,raw=_r027_load_point(request,typed,native,output)",
        "                              planning_rho_max=verification['physical']['P1_rho'])":"                              planning_rho_max=verification['physical']['P1_rho'],\n                              accepted_cache_output=str(Path(request['planning_repair_parent'])/'OUTPUT'),\n                              original_Planning_reused=True,new_Planning_search_Native_calls=0)"
    }
    for old,new in edits.items():
        assert source.count(old)==1,old
        source=source.replace(old,new)
    filename=__file__+'.run.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r027_load_state=load_state,_r027_load_point=load_point)
    exec(compile(source,filename,'exec'),ns)
    return ns[function.__name__]
