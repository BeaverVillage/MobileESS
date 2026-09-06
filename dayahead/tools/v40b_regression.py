"""Predeclared numerical re-execution with exact inherited solver-cache reuse.

The beam driver is executed; its completed stages are copied with hashes from
the exact original authority. Planning and OpenDSS execute again in a new
namespace. This does not claim an independent cold optimization repetition.
"""
from pathlib import Path
import sys,shutil,json,os,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pandas as pd
import numpy as np
from dayahead.v40b.common import *

def copy_stages(source,target):
    rows=[]
    for p in sorted(source.glob('STAGE_*.json')):
        q=target/p.name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        assert sha(p)==sha(q)
        rows.append({'source':str(p),'target':str(q),'sha256':sha(p)})
    if len(rows)!=4:raise ValueError('INCOMPLETE_ORIGINAL_BEAM')
    return rows

def compare_roots(original,current,day,case):
    from dayahead.v35r3e_r1.beam import OBJECTIVE_TOLERANCE,TRAJECTORY_TOLERANCE
    oldj=read(original/'summary/OBJECTIVE.json');newj=read(current/'summary/OBJECTIVE.json')
    # The inherited April storage regression is stricter than the beam tolerance.
    tolerance=1e-12 if day=='2025-04-01' else OBJECTIVE_TOLERANCE
    checks={};differences={}
    for field in ('primary_objective_J','rho_objective_component'):
        delta=abs(oldj[field]-newj[field]);differences[field]=delta;checks[field]=delta<=tolerance
    for namespace in ('planning','fresh'):
        name=f'{namespace.upper()}_SYSTEM_96.parquet'
        a=pd.read_parquet(original/namespace/name);b=pd.read_parquet(current/namespace/name)
        for field in ('system_rho','Vmin_pu','Vmax_pu','Imax_loading_ratio','transformer_current_loading_max','transformer_kva_loading_max'):
            delta=float(np.max(np.abs(a[field].to_numpy()-b[field].to_numpy())))
            differences[f'{namespace}.{field}']=delta;checks[f'{namespace}.{field}']=delta<=tolerance
    ag=read(original/'summary/PHYSICAL_GATES.json');bg=read(current/'summary/PHYSICAL_GATES.json')
    for ns in ('Planning','Fresh'):
        for field in ('voltage_violation_count','current_violation_count','transformer_violation_count'):
            checks[f'{ns}.{field}']=ag[ns][field]==bg[ns][field]
    a=pd.read_parquet(original/'mess/MESS_TRAJECTORY_96.parquet');b=pd.read_parquet(current/'mess/MESS_TRAJECTORY_96.parquet')
    discrete=['vehicle_id','slot','state','origin','current_location','destination','departure_slot','arrival_slot','connection_ready_slot','route_ID']
    checks['MESS_discrete_exact']=a[discrete].equals(b[discrete])
    checks['MESS_PQ_exact']=a[['P_kW','Q_kvar','SoC_fraction']].equals(b[['P_kW','Q_kvar','SoC_fraction']])
    checks['AIDC_ledger_exact']=pd.read_parquet(original/'aidc/AIDC_SCHEDULER_LEDGER.parquet').equals(pd.read_parquet(current/'aidc/AIDC_SCHEDULER_LEDGER.parquet'))
    checks['AIDC_site_exact']=pd.read_parquet(original/'aidc/IDC_FACILITY_96.parquet').equals(pd.read_parquet(current/'aidc/IDC_FACILITY_96.parquet'))
    return {'status':'PASS' if all(checks.values()) else 'FAIL','day':day,'case':case,'checks':checks,'max_abs_differences':differences,
      'tolerance':tolerance,'tolerance_source':'dayahead/v36/certification.py:_regression' if day=='2025-04-01' else 'dayahead/v35r3e_r1/beam.py:OBJECTIVE_TOLERANCE',
      'old_root':str(original),'current_root':str(current),'new_Fresh_calls':96,
      'criterion':'EXACT_AIDC_AND_MESS_DECISIONS; inherited numerical tolerance for repeated Planning/Fresh',
      'execution_design':'CURRENT_BEAM_DRIVER_WITH_HASH_VERIFIED_COMPLETED_STAGE_CACHE; NEW_PLANNING_AND_FRESH',
      'independent_cold_route_optimization_claim':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',required=True,choices=['2025-04-01','2025-05-01']);args=parser.parse_args();day=args.day
    from dayahead.v39e.runtime import install_runtime
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    install_runtime();_install_windows_safe_k_archive()
    from dayahead.v36 import runner as v36
    from dayahead.v39e.campaign_adapter import configure_v37_runner,build_day
    from dayahead.v36.aidc import build_apr01
    root=ROOT/'regression'/day;root.mkdir(parents=True,exist_ok=True)
    currentpass='V40B_REGRESSION';rows=[];copies=[]
    if day.startswith('2025-04'):
        original_repo=Path('C:/codex_mobileess_workspace/MobileESS_v36_apr01_calibration')
        originalpass='PRE_CALIBRATION'
        aidcs={c:build_apr01(REPO,c) for c in ('B0','B1','B2')}
        v36.CACHE_ROOT=Path('dayahead/cache/v40b_regression')
        source=original_repo/'dayahead/cache/v36_apr01_integrated_calibration_freeze/PRE_CALIBRATION/beam'/day/'B2/B2'
        target=REPO/v36.CACHE_ROOT/currentpass/'beam'/day/'B2/B2'
        copies=copy_stages(source,target)
        beam=v36._beam_case(REPO,currentpass,day,'B2',aidcs['B0'],aidcs['B1'])
    else:
        original_repo=OLD;originalpass='MAY_2025_V39E_FROZEN_DA'
        runner=configure_v37_runner();runner.PASS_ID=currentpass
        runner.STATUS_ROOT=ROOT/'regression/status'
        aidcs={c:build_day(REPO,day,'B0' if c=='B2' else c) for c in ('B0','B1','B2')}
        fp=runner.case_execution_fingerprint(REPO,day,'B2',aidcs['B2'])
        assert runner._valid_case_checkpoint(OLD,day,'B2',fp) is None # changed output namespace
        source=OLD/runner.CACHE_ROOT/originalpass/'beam'/fp['execution_fingerprint_sha256']/day/'B2/B2'
        target=REPO/runner.CACHE_ROOT/currentpass/'beam'/fp['execution_fingerprint_sha256']/day/'B2/B2'
        copies=copy_stages(source,target)
        beam,_=runner._beam_case(REPO,day,'B2',aidcs['B0'],aidcs['B1'],fp)
    write(root/'BEAM_CACHE_COPY.json',{'copies':copies,'source_files_modified':0,'May_tuning':0})
    for case in ('B0','B1','B2'):
        selected=beam if case=='B2' else None
        if day.startswith('2025-04'):result=v36.run_case(REPO,currentpass,day,case,aidcs[case],selected)
        else:result=runner._run_frozen_case(REPO,day,case,aidcs[case],selected)
        current=Path(result['root']);original=original_repo/'frozen_artifacts/v36_final_schema'/originalpass/day/case
        row=compare_roots(original,current,day,case);rows.append(row)
        write(root/f'{case}_REGRESSION.json',row)
        print(day,case,row['status'],{k:v for k,v in row['checks'].items() if not v},flush=True)
    write(root/'REGRESSION_RESULT.json',{'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','rows':rows})

if __name__=='__main__':main()
