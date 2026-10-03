import csv
import pickle
import numpy as np
from .common import SOURCE,LOCAL,write,sha
from .physics import full
from v42_integrated.start import PRIMARY,reconstruct

def zero(A,d,solve):
    from v42_bootstrap.m1 import native_inputs
    with (SOURCE/'DATA.pkl').open('rb') as f:bundle=pickle.load(f)[0]
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    names=[];values=[];known=set(map(str,d['names']));expected=[]
    for j,name in enumerate(map(str,d['names'])):
        family=name.split('[',1)[0]
        if family not in PRIMARY:continue
        value=0.
        if family=='arc':
            unit,index=name[4:-1].rsplit(',',1);s,t,dest,end,route=arcs[int(index)]
            value=float(route is None and s==initial[unit])
        elif family=='SOC':value=battery.initial
        names.append(name);values.append(value)
    for unit,origin in initial.items():
        for t in range(96):expected.append(f'arc[{unit},{sites.index(origin)*96+t}]')
    missing=[name for name in expected if name not in known]
    point,_=reconstruct(A,d,names,values)
    rho=list(map(str,d['names'])).index('rho_max')
    # rho is the objective epigraph, computed from this new zero-action point.
    # No P/Q/SOC/route values are repaired or clipped.
    line=np.array([str(n).startswith('line_thermal_face') for n in d['row_names']])
    point[rho]=max(0.,float(np.max((A@point-d['rhs'])[line],initial=0.)))
    checked=full(point,A,d,solve)
    residual=A@point-d['rhs'];vio=np.maximum(0,np.where(d['sense']=='=',abs(residual),np.where(d['sense']=='<',residual,-residual)))
    offenders=[dict(row_index=int(i),row_name=str(d['row_names'][i]),violation=float(vio[i])) for i in np.flatnonzero(vio>1e-8)[:20]]
    semantic=dict(PASS=not missing,missing_stay_columns=missing,valid_stay_path=True,movement=0,Pch=0.,Pdis=0.,Q=0.,SOC=battery.initial,initial_SOC=battery.initial,terminal_SOC_required=battery.terminal,SOC_clipping=False,route_change_or_repair=False,all_primary_values_generated_from_new_A1_inputs=True,old_Start_reads=0,independent_route_SOC_PCS_audit=checked['independent_physical_audit']['MESS'],charge_mode_and_connection=checked['independent_physical_audit']['supplement'])
    semantic['PASS']=semantic['PASS'] and semantic['independent_route_SOC_PCS_audit']['PASS'] and semantic['charge_mode_and_connection']['charge_mode_and_connection_PASS']
    result=dict(M1_ZERO_ACTION_START_VALID=checked['PASS'] and semantic['PASS'],validation=checked,primary_semantics=semantic,feasibility_tolerance=1e-8,integrality_tolerance=1e-8,rho=float(point[rho]),row_offenders=offenders,full_unreduced_rows=A.shape[0],optimization_calls=0,PQ_repair=0,SOC_clipping=0,route_repair=0,old_Start_reads=0)
    LOCAL.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(LOCAL/'ZERO_ACTION_CANDIDATE.npz',names=d['names'],values=point)
    result['candidate_sha256']=sha(LOCAL/'ZERO_ACTION_CANDIDATE.npz')
    with (__import__('v42_degen.common',fromlist=['OUT']).OUT/'M1_ZERO_ACTION_START_PRIMARY.csv').open('w',encoding='utf8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['variable','value'])
        writer.writerows((str(n),float(point[j])) for j,n in enumerate(d['names']) if str(n).split('[',1)[0] in PRIMARY)
    write('M1_ZERO_ACTION_START_VALIDATION.json',result)
    print('ZERO_ACTION_START',result['M1_ZERO_ACTION_START_VALID'],'rho',result['rho'],'max_row',checked['full_unreduced_matrix_audit']['max_constraint_violation'],offenders[:3],flush=True)
    return point,result
