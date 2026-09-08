"""Read-only production evidence; isolated finite May-04 flexibility probes."""
from pathlib import Path
import hashlib
import json
import shutil
import time
from types import FunctionType
import numpy as np
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import ROOT, record
from dayahead.v41.data import RUNTIME

DAY = '2025-05-04'
OUT = ROOT / 'dayahead/artifacts/v41r1_b1_flexibility_diagnostic' / DAY
WORK = Path('D:/MobileESS_B1_flexibility_diagnostic') / DAY
B0 = RUNTIME / DAY / 'B0'
OLD = RUNTIME / 'fa/03'
NEW = RUNTIME / 'fa/early03'
A0 = NEW / DAY / 'B1/dayahead/A0'


def preserve():
    if (OUT/'PRESERVATION.json').exists():
        return read(OUT/'PRESERVATION.json')
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    source = Path('C:/Users/kjw39/.codex/attachments/be9900de-3cb2-4238-b4f4-fc80191a6ce5/pasted-text.txt')
    shutil.copyfile(source, OUT/'USER_REQUEST.txt')
    roots={'B0': B0, 'pre_early_B1': OLD, 'early_B1': NEW,
           'electrical': RUNTIME/'e/20250504'}
    entries=[]
    for label, root in roots.items():
        files=sorted(p for p in root.rglob('*') if p.is_file())
        for p in files:
            rel=p.relative_to(root)
            target=WORK/'preserved'/label/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copyfile(p,target)
            original=record(p);saved=record(target)
            assert original['sha256']==saved['sha256']
            entries.append(dict(label=label,original=original,preserved=saved))
        print('PRESERVED',label,len(files),flush=True)
    from dayahead.v41.execution import science, commit
    value=dict(status='PASS',day=DAY,production_commit=commit(),production_science=science(),
        entries=entries,search_uses_Actual=False,Actual_files_archived_only=True,
        full_may_authorized=False)
    write_json(OUT/'PRESERVATION.json',value)
    return value


def context():
    """Clone the existing loader, redirecting only its upstream report writes."""
    from dayahead.v41 import electrical
    from dayahead.paper_analysis import storage
    def isolated_kernel(run):
        namespace=electrical.kernel(run)
        def redirect(p):
            p=Path(p)
            rel=p.resolve().relative_to(run.resolve())
            target=OUT/'context_reconstruction'/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            return target
        namespace['write_json']=lambda p,v: storage.write_json(redirect(p),v)
        namespace['write_npz']=lambda p,**v: storage.write_npz(redirect(p),**v)
        return namespace
    ns=dict(vars(electrical));ns['kernel']=isolated_kernel
    fn=electrical.load
    loader=FunctionType(fn.__code__,ns,fn.__name__,fn.__defaults__,fn.__closure__)
    ctx=loader(DAY)
    from dayahead.v41.reserve import bind
    p=RUNTIME/'inputs'/DAY/f'V41_ML_SNAPSHOT_{DAY}.json'
    bind(ctx,p,record(p)['sha256'])
    return ctx


def inspect():
    ctx=context()
    try:
        names=list(ctx.coefficients[0].control_names)
        print('CONTROL_NAMES',names,flush=True)
        print('VOLTAGE_CACHE_KEYS',list(ctx.electrical.voltage.files),flush=True)
        print('CURRENT_CACHE_KEYS',list(ctx.electrical.current.files),flush=True)
        print('CAPACITY',dict(ctx.capacity.site_capacity),flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


def electrical_table():
    ctx=context()
    try:
        from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
        from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters, anchored_polygon_loading, is_dominated_mess_current_row
        from dayahead.grid_lp import LINE_POLYGON_FACES
        from dayahead.v36.contracts import PF_TAN
        import math
        with np.load(B0/'dayahead/FROZEN_AIDC_POWER.npz') as z:pcc=z['pcc']
        controls=controls_from_trajectory(ctx.coefficients,pcc,())
        grid=evaluate_grid(ctx.coefficients,controls,ctx.nodes)
        t=grid['critical_slot'];c=ctx.coefficients[t];k=c.branch_names.index(grid['critical_line'])
        bias,correction,_=anchored_polygon_parameters(c)
        theta=2*np.pi*np.arange(LINE_POLYGON_FACES)/LINE_POLYGON_FACES
        p=c.flow_p_constant+c.flow_p_matrix@controls[t]
        q=c.flow_q_constant+c.flow_q_matrix@controls[t]
        face=int(np.argmax(np.cos(theta)*p[k]+np.sin(theta)*q[k]))
        denom=c.branch_limits[k]*math.cos(math.pi/LINE_POLYGON_FACES)
        weight=(np.cos(theta[face])*c.flow_p_matrix[k]+np.sin(theta[face])*c.flow_q_matrix[k])/denom+correction[:,k]
        table=[]
        for i,site in enumerate(ctx.capacity.aidc_ids):
            pi=c.control_names.index('mess_p_kw[IDC'+site[-2:]+']')
            qi=c.control_names.index('mess_q_kvar[IDC'+site[-2:]+']')
            shifted=controls[t].copy();shifted[i]+=1
            response=float(anchored_polygon_loading(c,shifted)[k]-anchored_polygon_loading(c,controls[t])[k])
            table.append(dict(IDC=site,critical_fixed_PF_load_sensitivity=float(weight[i]),
                one_kW_fixed_PF_perturbation=response,co_located_P_load_sensitivity=float(-weight[pi]),
                co_located_Q_load_sensitivity=float(-weight[qi]),
                fixed_PF_reconstruction_error=float(weight[i]+weight[pi]+PF_TAN*weight[qi])))
        near=[]
        for tt,cc in enumerate(ctx.coefficients):
            for kk,l in enumerate(anchored_polygon_loading(cc,controls[tt])):
                name=cc.branch_names[kk]
                if not name.startswith('transformer.') and not is_dominated_mess_current_row(name) and l>=grid['rho_max']*.99:
                    near.append(dict(branch=name,day_slot=tt,issue_slot=tt+24,loading=float(l)))
        value=dict(status='PASS',grid=grid,critical_issue_slot=t+24,critical_face=face,
            table=table,near_binding=near,coefficient_authority=ctx.v41_electrical_certificate,
            source='CURRENT_CERTIFIED_PLANNING_COEFFICIENTS',Actual_reads=0,pruning=False)
        write_json(OUT/'ELECTRICAL_RESPONSIVENESS.json',value)
        print('ELECTRICAL',grid['critical_line'],t,grid['rho_max'],flush=True)
        print('SENSITIVITIES',table,flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['preserve','inspect','electrical']);a=p.parse_args()
    {'preserve':preserve,'inspect':inspect,'electrical':electrical_table}[a.mode]()
