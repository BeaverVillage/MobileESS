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
from .diagnostics import diagnose_model,bounded_iis

def substitute_fixed(case):
    """Diagnostic algebra only: singleton rows imply bounds, then substitute.

    Every implied fixed variable retains its original-row derivation. No point
    from this diagnostic reduction can reach the initialization admission gate.
    """
    low=case.d['lower'].copy();high=case.d['upper'].copy();derivations=[]
    for iteration in range(12):
        fixed=low==high;values=np.where(fixed,low,0.)
        remaining=np.flatnonzero(~fixed)
        A=case.A[:,remaining].tocsr();rhs=case.d['rhs']-case.A@values
        rows=np.flatnonzero(np.diff(A.indptr)==1);changed=False
        for i in rows:
            k=A.indptr[i];j=int(remaining[A.indices[k]]);coefficient=float(A.data[k])
            bound=float(rhs[i])/coefficient;sense=str(case.d['sense'][i]);old=(low[j],high[j])
            if sense=='=' or (sense=='<' and coefficient<0) or (sense=='>' and coefficient>0):low[j]=max(low[j],bound)
            if sense=='=' or (sense=='<' and coefficient>0) or (sense=='>' and coefficient<0):high[j]=min(high[j],bound)
            if low[j]>high[j]:
                # Leave conflicting inequalities intact for Native Farkas/IIS.
                low[j],high[j]=old;continue
            if old!=(low[j],high[j]):
                changed=True;derivations.append(dict(iteration=iteration,row_index=int(i),
                    row_name=str(case.d['row_names'][i]),variable_index=j,variable_name=str(case.d['names'][j]),
                    coefficient=coefficient,reduced_rhs=float(rhs[i]),lower=float(low[j]),upper=float(high[j])))
        if not changed:break
    fixed=low==high;values=np.where(fixed,low,0.);remaining=np.flatnonzero(~fixed)
    reduced=case.A[:,remaining].tocsr();used=np.unique(reduced.indices);columns=remaining[used]
    data=dict(case.d)
    for key in ('names','lower','upper','types','objective'):data[key]=case.d[key][columns].copy()
    data['lower']=low[columns];data['upper']=high[columns];data['objective']=np.zeros(len(columns))
    data['rhs']=case.d['rhs']-case.A@values;data['constant']=np.array(0.)
    return NS(A=reduced[:,used].tocsr(),d=data,case_sha=case.case_sha),dict(
        original_columns=columns.tolist(),fixed_indices=np.flatnonzero(fixed).tolist(),
        fixed_values=values[fixed].tolist(),singleton_original_row_derivations=derivations,
        diagnostic_only=True,initialization_constraints_removed=0)

def diagnostic_subsystem(case,description,ids,values,source):
    """An IIS search subsystem only. Feasible points are NEVER admitted here.

    Infeasibility of a subset of original rows proves this fixed candidate
    impossible; feasibility of the subset says nothing about FULL feasibility.
    """
    rows=read(source/'INITIALIZATION_FAILURE_CONSTRAINT_ANALYSIS.json')['original_stationary_background_failures']
    voltage={r['index'] for r in rows if r['domain']=='C3A' and r['name'].startswith('voltage_')}
    connected=set()
    for unit,path in description['paths'].items():
        for k in path:
            arc=case.graph[2][k]
            if arc[-1] is None:connected.add((unit,arc[0],arc[1]))
    active=np.zeros(case.A.shape[1],dtype=bool)
    for j,name in enumerate(map(str,case.d['names'])):
        if name.startswith(('Pch[','Pdis[','Q[','node_activity[')):
            axis=name.split('[',1)[1][:-1].split(',')
            active[j]=(axis[0],axis[1],int(axis[2])) in connected
    prefix=np.r_[0,np.cumsum(active[case.A.indices],dtype=np.int64)]
    active_row=(prefix[case.A.indptr[1:]]-prefix[case.A.indptr[:-1]])>0
    keep=[]
    families={'energy_balance','initial_SOC','terminal_SOC','no_simultaneous_charge','no_simultaneous_discharge',
        'connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin','injection_P_binding','injection_Q_binding',
        'flow','terminal_location','node_activity_link'}
    for i,name in enumerate(map(str,case.d['row_names'])):
        family=name.split('[',1)[0]
        if family in ('voltage_upper','voltage_lower') or family in families or (family=='PCS16' and active_row[i]):keep.append(i)
    selected=np.asarray(keep,dtype=np.int64);A=case.A[selected]
    fix=sparse.csr_matrix((np.ones(len(ids)),(np.arange(len(ids)),ids)),shape=(len(ids),case.A.shape[1]))
    data=dict(case.d)
    data['rhs']=np.concatenate([case.d['rhs'][selected],values])
    data['sense']=np.concatenate([case.d['sense'][selected],np.array(['=']*len(ids))])
    data['row_names']=np.concatenate([case.d['row_names'][selected],np.array(['FIXED_'+str(case.d['names'][j]) for j in ids])])
    return NS(A=sparse.vstack([A,fix],format='csr'),d=data,case_sha=case.case_sha),selected

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
        candidate,source_rows=diagnostic_subsystem(case,description,ids,values,source)
        candidate,substitution=substitute_fixed(candidate)
        model,receipt=original._model(candidate,continuous=True)
        try:
            out=output/('V18_'+name);out.mkdir(exist_ok=True)
            np.savez_compressed(out/'ORIGINAL_SUBSYSTEM_ROW_MAP.npz',original_C3A_rows=source_rows)
            atomic(out/'ORIGINAL_CANDIDATE_AUTHORITY.json',dict(candidate=record(old/'CANDIDATE.json'),
                full_replay=record(old/'FULL_REPLAY.json'),old_termination=read(old/'FULL_REPLAY.json'),
                original_rows_and_fixed_integer_equalities_reproduced=True,
                diagnostic_only_original_row_subsystem=True,original_row_count=A.shape[0],
                subsystem_original_rows=len(source_rows),no_subsystem_feasible_point_admitted=True,
                reason='NATIVE_FARKAS_FOR_AN_INFEASIBLE_SUBSYSTEM; INITIALIZER_ALWAYS_RETAINS_ALL_ROWS'))
            atomic(out/'DIAGNOSTIC_EXACT_FIXED_SUBSTITUTION.json',substitution)
            if progress:progress(dict(phase='V18_CANDIDATE_FARKAS_'+name))
            diagnose_model(candidate,model,budget,out,model.getAttr('VType'),seconds=15.,run_phase_one=name=='00')
            if not (out/'FARKAS_DIAGNOSTIC.json').exists():
                if progress:progress(dict(phase='V18_CANDIDATE_IIS_'+name))
                bounded_iis(candidate,model,out,seconds=15.)
            summaries.append(dict(candidate=name,kind=description['kind'],status=read(out/'DIAGNOSTIC_STATUS.json'),
                IIS=read(out/'IIS_DIAGNOSTIC.json') if (out/'IIS_DIAGNOSTIC.json').exists() else None,
                Farkas=read(out/'FARKAS_DIAGNOSTIC.json') if (out/'FARKAS_DIAGNOSTIC.json').exists() else None))
        finally:model.dispose()
    atomic(output/'V18_CANDIDATE_CAUSE_ANALYSIS.json',dict(candidates=summaries,Native_Runtime=budget.used(),
        Native_calls=len(budget.calls),diagnostics_only=True,original_FULL_MILP_infeasibility_claimed=False))
    return dict(PASS=all(s['Farkas'] is not None or s['IIS'] is not None for s in summaries),status='DIAGNOSTICS_COMPLETED',
        diagnostics_only=True,Native_Runtime=budget.used(),Native_calls=len(budget.calls),UB=None,
        first_FULL_pass_wall_seconds=None,Adaptive_entered=False,LB=None,Global_Gap=None)
