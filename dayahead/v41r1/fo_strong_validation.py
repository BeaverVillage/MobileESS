"""Predefined B0 selection and separate finite global B1 validation solves."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.reserve import require

PLAN=ROOT/'dayahead/artifacts/v41r1_bounded_compute/REPRESENTATIVE_GLOBAL_VALIDATION_PLAN.json'


def select():
    from dayahead.v41.electrical import load
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    rows=[]
    for d in range(1,32):
        day=f'2025-05-{d:02}';ctx=load(day)
        try:
            reference=RUNTIME/'inputs'/day/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
            power=planning_power(import_frozen(read(reference)),ctx)
            grid=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,power['pcc'],()),ctx.nodes)
            rows.append(dict(day=day,B0_rho_max=grid['rho_max'],B0_reference=record(reference),electrical=ctx.v41_electrical_certificate))
            print('B0_SELECTION',day,grid['rho_max'],flush=True)
        finally:ctx.electrical.voltage.close();ctx.electrical.current.close()
    ordered=sorted(rows,key=lambda r:(r['B0_rho_max'],r['day']))
    selected={ordered[0]['day']:'LOW_B0_LOADING',ordered[15]['day']:'MEDIAN_B0_LOADING',ordered[-1]['day']:'HIGH_B0_LOADING'}
    selected['2025-05-04']=selected.get('2025-05-04','')+' PREDECLARED_COMPUTATIONALLY_DIFFICULT'
    if len(selected)<4:
        for row in reversed(ordered[23:]+ordered[:23]):
            if row['day'] not in selected:selected[row['day']]='ADDITIONAL_B0_LOADING_QUARTILE';break
    write_json(PLAN,dict(status='FROZEN_SELECTION',selection='LOW_MEDIAN_HIGH_B0_LOADING_PLUS_PREDECLARED_MAY04',
        proposed_policy_outcomes_read=0,policies=['B1'],days=[dict(day=d,reason=r) for d,r in sorted(selected.items())],
        all_31_B0_physical_characteristics=rows,global_MIPGap=.005,total_seconds_per_day=7200,
        P1_seconds=5400,P2_seconds=1800,threads=4,parallel_validation_workers=1,
        execute_after='FULL_MAY_COMPLETE_TO_AVOID_COMPETING_WITH_4_BY_4_PRODUCTION',
        P2_bound_scope='FULL_B1_CANDIDATE_MODEL_CONDITIONAL_ON_MONTHLY_ACCEPTED_P1_LOCK',
        scope='B1_GLOBAL_MILP_BOUNDS; DOES_NOT_CERTIFY_GLOBAL_B2_B3_MESS_OR_JOINT_OPTIMALITY',
        certificate_claim='PENDING_UNTIL_GLOBAL_SOLVER_OUTPUT_EXISTS'))


def worker():
    import gurobipy as gp
    from gurobipy import GRB
    from .feasible_seed import row_audit
    from .bounded_solver import finite,relative_gap
    require(read(RUNTIME/'campaign_state.json')['status']=='COMPLETE','GLOBAL_VALIDATION_WAITS_FOR_FULL_MAY')
    from .fo_release import verify
    verify()
    plan=read(PLAN);root=RUNTIME/'strong_global_validation';root.mkdir(parents=True,exist_ok=True)
    write_json(root/'WORKER.json',dict(pid=os.getpid(),started=time.time(),plan=record(PLAN)))
    for row in plan['days']:
        day=row['day'];out=root/day
        if (out/'RESULT.json').exists():continue
        a0=RUNTIME/day/'B1/dayahead/A0';solver=read(a0/'BOUNDED_SOLVER_REPORT.json')
        monthly=solver['stages'][-1]['accepted_objective_vector'];npz=solver['stages'][-1]['checkpoint']['path']
        short=Path('D:/MobileESS_FO_global')/uuid.uuid4().hex[:10];short.mkdir(parents=True)
        model_path=short/'model.mps';out.mkdir(parents=True,exist_ok=True)
        with gzip.open(a0/'PRIMARY_MODEL.mps.gz','rb') as src,model_path.open('wb') as dst:
            for block in iter(lambda:src.read(8*1024*1024),b''):dst.write(block)
        m=gp.read(str(model_path));stages=[]
        try:
            with np.load(a0/'POLICY_FEASIBLE_SEED.npz',allow_pickle=False) as z:names=z['names'].tolist()
            with np.load(npz,allow_pickle=False) as z:by_name=dict(zip(names,z['values'].tolist()))
            vs=m.getVars();start=[by_name[v.VarName] for v in vs];del by_name
            require(row_audit(m,start)['status']=='PASS','GLOBAL_VALIDATION_MONTHLY_START_INVALID')
            m.setAttr('Start',vs,start);m.Params.Threads=4;m.Params.Method=1;m.Params.Seed=20260905
            m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.MIPGap=.005;m.Params.MIPGapAbs=0
            m.Params.NodefileStart=.5;m.Params.NodefileDir=str(short);m.Params.LogFile=str(out/'GLOBAL_SOLVER.log')
            for stage,seconds in [('P1',5400),('P2',1800)]:
                if stage=='P2':
                    rho=m.getVarByName('rho_max');m.addConstr(1000*rho<=1000*monthly[0],name='MONTHLY_ACCEPTED_P1_LOCK')
                    xi=[v for v in vs if v.VarName.startswith('V41_H4_shortfall_GPUh[')]
                    m.setObjective(gp.quicksum(xi)/len(xi),GRB.MINIMIZE);m.setAttr('Start',vs,start)
                m.Params.TimeLimit=seconds;m.Params.WorkLimit=GRB.INFINITY;t=time.perf_counter();m.optimize()
                result=dict(stage=stage,status=int(m.Status),global_bound=finite(m.ObjBound),incumbent=finite(m.ObjVal) if m.SolCount else None,
                    seconds=time.perf_counter()-t,monthly_incumbent=monthly[0 if stage=='P1' else 1],
                    bound_scope='FULL_ORIGINAL_B1_DOMAIN'+('_CONDITIONAL_ON_MONTHLY_P1_LOCK' if stage=='P2' else ''))
                result['monthly_certified_gap']=relative_gap(result['monthly_incumbent'],result['global_bound'])
                if m.SolCount:
                    result['feasibility']=row_audit(m,m.getAttr('X',vs));require(result['feasibility']['status']=='PASS','GLOBAL_RESULT_RESIDUAL_FAILURE')
                    np.savez_compressed(out/(stage+'_GLOBAL_INCUMBENT.npz'),values=m.getAttr('X',vs),names=np.asarray([v.VarName for v in vs]))
                stages.append(result);write_json(out/'STAGES.json',stages)
            write_json(out/'RESULT.json',dict(status='PASS',day=day,policy='B1',selection=row,plan=record(PLAN),
                monthly_solver=record(a0/'BOUNDED_SOLVER_REPORT.json'),stages=stages,production_decision_modified=False))
        finally:m.dispose()
    write_json(root/'COMPLETE.json',dict(status='PASS',plan=record(PLAN),days=[record(root/r['day']/'RESULT.json') for r in plan['days']]))
    from .fo_quality import aggregate
    aggregate()


def launch():
    import psutil
    from dayahead.tools.v41_detached_launcher import git_executable
    require(read(RUNTIME/'campaign_state.json')['status']=='COMPLETE','GLOBAL_VALIDATION_WAITS_FOR_FULL_MAY')
    for p in psutil.process_iter(['cmdline']):
        cmd=p.info['cmdline'] or []
        require(not ('dayahead.v41r1.fo_strong_validation' in cmd and 'worker' in cmd),'GLOBAL_VALIDATION_ALREADY_RUNNING')
    require(not (RUNTIME/'strong_global_validation/COMPLETE.json').exists(),'GLOBAL_VALIDATION_ALREADY_COMPLETE')
    token=uuid.uuid4().hex;helper=RUNTIME/'launcher_helpers'/('strong_'+token+'.ps1');helper.parent.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-u','-m','dayahead.v41r1.fo_strong_validation','worker','--git',git_executable()]
    quote=lambda x:"'"+str(x).replace("'","''")+"'"
    script=("$ErrorActionPreference='Stop'\n"
        "$s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$p=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+quote(subprocess.list2cmdline(args))+
        ";CurrentDirectory="+quote(ROOT)+";ProcessStartupInformation=$s}\n$p | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper.write_text(script,encoding='utf-8-sig')
    import json
    result=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],text=True))
    require(result['ReturnValue']==0,'GLOBAL_VALIDATION_DETACHED_LAUNCH_FAILED')
    write_json(RUNTIME/'strong_global_validation/LAUNCH.json',dict(pid=result['ProcessId'],plan=record(PLAN),helper=record(helper)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['select','worker','launch']);p.add_argument('--git');a=p.parse_args()
    if a.mode=='worker':
        if a.git:
            from dayahead.tools.v41_detached_launcher import provision_git
            provision_git(a.git)
        from dayahead.v41.detached import job_membership
        require(not job_membership(),'GLOBAL_VALIDATION_NOT_DETACHED')
        os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
        root=RUNTIME/'strong_global_validation';root.mkdir(parents=True,exist_ok=True)
        sys.stdin=open(os.devnull,'r');sys.stdout=(root/'WORKER.log').open('a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
        worker()
    else:select() if a.mode=='select' else launch()
