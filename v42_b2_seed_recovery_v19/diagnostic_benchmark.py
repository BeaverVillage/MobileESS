"""Replay sealed V18 fixed candidates with Farkas settings; no new physical point."""
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
from scipy import sparse
from v42_may_campaign_native90 import m_stage as original
from v42_may_campaign_native90.m_model import _domain_sha
from v42_m1_hybrid.blocks import matrix_sha
from v42_bootstrap.m1 import native_inputs
from v42_b2_seed_recovery_v18.initialization import values_for
from .common import read,atomic,record
from .diagnostics import diagnose_model

def run(request,budget,progress):
    root=Path(request['root']);manifest=read(request['manifest'])
    source=Path(manifest['campaign_root'])/'initialization_benchmark_v18r2_01/dates/B2/2025-05-03/attempts/seed_policy_v18r2_01/output'
    identity=read(source/'SCIENTIFIC_CASE_IDENTITY.json');A=sparse.load_npz(source/'C3A_A.npz')
    with np.load(source/'C3A_DATA.npz',allow_pickle=False) as saved:d={k:saved[k].copy() for k in saved.files}
    if matrix_sha(A)!=identity['selected_matrix_sha'] or _domain_sha(d)!=identity['selected_domain_sha']:
        raise ValueError('DIAGNOSTIC_ORIGINAL_MATRIX_DOMAIN_SHA_DRIFT')
    bundle=read(Path(request['input_folder'])/'NATIVE_INPUT.json')
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    case=NS(A=A,d=d,graph=graph,case_sha=identity['case_sha'])
    output=Path(request['output']);output.mkdir(parents=True,exist_ok=True)
    atomic(output/'DIAGNOSTIC_SOURCE_AUTHORITY.json',dict(identity=record(source/'SCIENTIFIC_CASE_IDENTITY.json'),
        matrix=record(source/'C3A_A.npz'),domain=record(source/'C3A_DATA.npz'),matrix_SHA_match=True,domain_SHA_match=True,
        previous_runtime_not_reset=True,no_new_initial_point_claimed=True))
    peak=read(source/'INITIALIZATION_VOLTAGE_SENSITIVITY.json')['peak_slot'];summaries=[]
    for name in ('00','01','02','03'):
        old=source/'INITIALIZATION_CANDIDATES'/name;description=read(old/'CANDIDATE.json')
        if description['kind']=='STATIONARY_CHARGE_BEFORE_PEAK':charge=lambda u,t:t<peak
        elif description['kind']=='STATIONARY_CHARGE_AFTER_PEAK':charge=lambda u,t:t>=peak
        else:charge=lambda u,t:t<16 or t>=description['charging_return_slot']
        ids,values=values_for(case,description['paths'],charge)
        model,receipt=original._model(case,continuous=True)
        try:
            fix=sparse.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),ids)),shape=(len(ids),A.shape[1]))
            model.addMConstr(fix,model.getVars(),'=',values,name='INITIALIZATION_ONLY_FIXED_ORIGINAL_INTEGERS');model.update()
            extended=sparse.vstack([A,fix],format='csr');data=dict(d)
            data['rhs']=np.concatenate([d['rhs'],values]);data['sense']=np.concatenate([d['sense'],np.array(['=']*len(ids))])
            data['row_names']=np.concatenate([d['row_names'],np.array(['FIXED_'+str(d['names'][j]) for j in ids])])
            candidate=NS(A=extended,d=data,case_sha=case.case_sha)
            out=output/('V18_'+name);out.mkdir(exist_ok=True)
            atomic(out/'ORIGINAL_CANDIDATE_AUTHORITY.json',dict(candidate=record(old/'CANDIDATE.json'),
                full_replay=record(old/'FULL_REPLAY.json'),old_termination=read(old/'FULL_REPLAY.json'),
                original_rows_and_fixed_integer_equalities_reproduced=True))
            if progress:progress(dict(phase='V18_CANDIDATE_FARKAS_'+name))
            diagnose_model(candidate,model,budget,out,model.getAttr('VType'),seconds=15.,run_phase_one=name=='00')
            summaries.append(dict(candidate=name,kind=description['kind'],status=read(out/'DIAGNOSTIC_STATUS.json'),
                Farkas=read(out/'FARKAS_DIAGNOSTIC.json') if (out/'FARKAS_DIAGNOSTIC.json').exists() else None))
        finally:model.dispose()
    atomic(output/'V18_CANDIDATE_CAUSE_ANALYSIS.json',dict(candidates=summaries,Native_Runtime=budget.used(),
        Native_calls=len(budget.calls),diagnostics_only=True,original_FULL_MILP_infeasibility_claimed=False))
    return dict(PASS=all(s['Farkas'] is not None for s in summaries),status='DIAGNOSTICS_COMPLETED',
        diagnostics_only=True,Native_Runtime=budget.used(),Native_calls=len(budget.calls),UB=None,
        first_FULL_pass_wall_seconds=None,Adaptive_entered=False,LB=None,Global_Gap=None)
