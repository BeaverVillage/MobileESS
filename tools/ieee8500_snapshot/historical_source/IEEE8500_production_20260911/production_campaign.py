"""Audited single-day production campaign; only this workspace is writable."""
import sys,time,traceback,ctypes
from pathlib import Path
import numpy as np
import ac8500 as ac
from non_electrical_inputs import context,service_alias
from grid8500 import Grid
from run_support import atomic,Metrics,digest
import aidc_search8500 as aidc
import mess_search8500 as mess
from dayahead.v33m.mess_mobility_milp import add_mess_mobility_block
sys.dont_write_bytecode=True
H=ac.H
def freeze_check():
    for r in ac.read(H/'PRODUCTION_EXECUTION_FREEZE.json')['files']:
        assert ac.sha(r['path'])==r['sha256'],('PRODUCTION_INPUT_OR_CODE_DRIFT',r['path'])
def preflight(ctx,grid):
    required=['B0_REPRODUCTION_AUDIT.json','NON_ELECTRICAL_INPUT_AND_BINDING_AUDIT.json','INDEPENDENT_COMPLEX_V2/VALIDATION.json']
    for p in required:assert ac.read(H/'preflight'/p)['status']=='PASS',p
    print('PREFLIGHT_STRUCTURAL_MODEL_BUILD_NO_OPTIMIZATION',flush=True)
    metrics=Metrics();meta=aidc.options_metadata(ctx);chosen=aidc.initial_indices(ctx);jobs,power,audit=aidc.materialized(ctx,chosen)
    aidc.neighborhood(ctx,grid,chosen,power,None,None,meta,0,H/'preflight/DRY_AIDC_BUILD',metrics,lambda:0.,[.85])
    assert len(metrics.solve)==0
    model=mess.configured(H/'preflight','IEEE8500_PREFLIGHT_MESS_BUILD_ONLY');block=add_mess_mobility_block(model,ctx.mobility_inputs);model.update();inventory=dict(route_variables=len(block.move),variables=model.NumVars,constraints=model.NumConstrs,optimization_calls=0);model.dispose()
    expected=len(ctx.initial)*sum(o!=d and t+r.connection_ready_slots_15min<=96 and r.connection_ready_slots_15min>0 for (t,o,d),r in ctx.route_table.records.items());assert inventory['route_variables']==expected and expected>0
    atomic(H/'PREFLIGHT_PASS.json',dict(status='PASS',operating_authority=ac.record(ac.STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json'),checks=[ac.record(H/'preflight'/p) for p in required],structural_AIDC_solver_calls=0,MESS_build=inventory,route_aliases={s:service_alias(s) for s in ctx.route_table.service_ids},IEEE123_electrical_artifacts_reused=False,production_execution_freeze=ac.record(H/'PRODUCTION_EXECUTION_FREEZE.json')))
    print('IEEE8500_PRODUCTION_PREFLIGHT_PASS',flush=True)
def finish(results,started,grid):
    protected=ac.read(H/'PROTECTED_AUTHORITIES_BEFORE.json');rows=protected['files'] if isinstance(protected,dict) else protected;drift=[]
    for r in rows:
        if ac.sha(r['path'])!=r['sha256']:drift.append(r['path'])
    assert not drift,drift;freeze_check()
    b1=results['B1'];a1=results['B3_A1'];m1=results['B3_M1'];mf=results['B3_MF']
    metrics=dict(coefficient_generation_wall_seconds=ac.read(H/'coefficients_v2/GENERATION_RECEIPT.json')['wall_seconds'],coefficient_loading_seconds=grid.load_seconds,B1_total_runtime_seconds=b1['total_runtime_seconds'],B3_incremental_algorithm_runtime_seconds=m1['wall_seconds']+a1['total_runtime_seconds']+mf['wall_seconds'],B3_total_algorithm_runtime_seconds=b1['total_runtime_seconds']+m1['wall_seconds']+a1['total_runtime_seconds']+mf['wall_seconds'],M1_wall_seconds=m1['wall_seconds'],MF_wall_seconds=mf['wall_seconds'],B1_checkpoints=b1['timeline'],B3_A1_checkpoints=a1['timeline'],policies={k:v.get('metrics') for k,v in results.items() if 'metrics' in v},peak_RAM_bytes=max(v.get('metrics',{}).get('peak_RAM_bytes',0) for v in results.values()),campaign_wall_seconds=time.perf_counter()-started)
    atomic(H/'SCALABILITY_METRICS.json',metrics);atomic(H/'FINAL_CAMPAIGN_RECEIPT.json',dict(status='PASS',date='2025-05-21',authority_settings=dict(source_pu=1.04,Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF'),B0=results['B0'],B1=b1['AC'],B2=results['B2']['AC'],B3=mf['AC'],exact_B1_reused_as_A0=True,M1_fixed_in_A1=True,MF_route_fixed=True,old_authority_files_verified=len(rows),authority_drift=drift,all_final_policies_96_slot_exact_AC_PASS=True,metrics_file=str(H/'SCALABILITY_METRICS.json'),globally_optimal=False))
    lines=['# IEEE8500 production results','','FINAL authority unchanged: 2025-05-21; source 1.0400; all Vreg 123.5 V; alpha 0.50; CAPBank3 OFF.','','| Policy | exact AC max phase-line loading | Vmin | Vmax | TF phase current | TF winding kVA |','|---|---:|---:|---:|---:|---:|']
    for key,r in [('B0',results['B0']),('B1',b1['AC']),('B2',results['B2']['AC']),('B3',mf['AC'])]:lines.append(f"| {key} | {r['max_phase_line_loading_pu']:.12f} | {r['Vmin_pu']:.12f} | {r['Vmax_pu']:.12f} | {r['max_transformer_phase_current_pu']:.12f} | {r['max_transformer_winding_kva_pu']:.12f} |")
    lines+=['','All four final policies passed fresh chronological 96-slot exact AC validation. B1 and B3-A1 each completed one continuous 14,400-second search loop. These are bounded feasible incumbents; no global optimality claim.','',f"B1 total runtime: {metrics['B1_total_runtime_seconds']:.3f} s. B3 incremental / total algorithm runtime: {metrics['B3_incremental_algorithm_runtime_seconds']:.3f} / {metrics['B3_total_algorithm_runtime_seconds']:.3f} s."]
    (H/'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    files=[ac.record(p) for p in sorted(H.rglob('*')) if p.is_file() and not p.name.endswith(('.log','.tmp')) and p.name not in ['FINAL_SHA256_MANIFEST.json','FINAL_SHA256_MANIFEST.sha256','CAMPAIGN_STATUS.json']]
    atomic(H/'FINAL_SHA256_MANIFEST.json',dict(status='FINAL_FROZEN',files=files));(H/'FINAL_SHA256_MANIFEST.sha256').write_text(ac.sha(H/'FINAL_SHA256_MANIFEST.json')+'  FINAL_SHA256_MANIFEST.json\n',encoding='ascii');atomic(H/'CAMPAIGN_STATUS.json',dict(status='COMPLETE',wall_seconds=time.perf_counter()-started,manifest=ac.record(H/'FINAL_SHA256_MANIFEST.json')));print('IEEE8500_B0_B1_B2_B3_COMPLETE',flush=True)
def main():
    started=time.perf_counter();ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        freeze_check();atomic(H/'CAMPAIGN_STATUS.json',dict(status='PREFLIGHT_LOADING'));print('LOADING_CAUSAL_NON_ELECTRICAL_INPUTS',flush=True);ctx=context();print('LOADING_IEEE8500_COMPLEX_COEFFICIENTS',flush=True);grid=Grid();print('COEFFICIENTS_LOADED',grid.load_seconds,flush=True);preflight(ctx,grid)
        out=H/'policies';out.mkdir(exist_ok=False);results={};atomic(H/'CAMPAIGN_STATUS.json',dict(status='B0_FINAL'));results['B0']=ac.replay(out/'B0/FINAL_INDEPENDENT_AC',independent=True);assert results['B0']['feasible'];assert abs(results['B0']['max_phase_line_loading_pu']-.8487691403696187)<1e-10
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='B1_14400_SECOND_CONTINUOUS_SEARCH'));results['B1'],b1power=aidc.run(ctx,grid.fork(),out/'B1');freeze_check()
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='B2_FULL_MESS'));results['B2'],_,_,_=mess.run(ctx,grid.fork(),ctx.power['pcc'],out/'B2');freeze_check()
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='B3_M1_FULL_MESS'));results['B3_M1'],m1,mp,mq=mess.run(ctx,grid.fork(),b1power['pcc'],out/'B3_M1');m1sha=m1.canonical_sha256
        atomic(out/'B3_A0_EXACT_B1_REUSE.json',dict(source=ac.record(out/'B1/FINAL_AIDC.json'),decision_SHA=digest(results['B1']['indices']),power=ac.record(out/'B1/FINAL_POWER.npz'),reuse='EXACT_FINAL_B1_NO_RERUN'))
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='B3_A1_14400_SECOND_CONTINUOUS_SEARCH'));results['B3_A1'],a1power=aidc.run(ctx,grid.fork(),out/'B3_A1',seed_indices=results['B1']['indices'],mp=mp,mq=mq);assert m1.canonical_sha256==m1sha;freeze_check()
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='B3_MF_FIXED_ROUTE_PQ'));results['B3_MF'],mf,_,_=mess.run(ctx,grid.fork(),a1power['pcc'],out/'B3_MF',seed=m1,fixed_route=True);assert mess.route_sha(mf.slots)==mess.route_sha(m1.slots);finish(results,started,grid)
    except BaseException as ex:
        atomic(H/'CAMPAIGN_STATUS.json',dict(status='STOPPED_ERROR',error=type(ex).__name__,message=str(ex),traceback=traceback.format_exc(),authority_tuning=False));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
if __name__=='__main__':main()
