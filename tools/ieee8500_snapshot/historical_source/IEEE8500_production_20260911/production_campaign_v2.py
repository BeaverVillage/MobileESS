"""Execution-only fix: Gurobi paths use the verified ASCII workspace junction."""
import os,time
from pathlib import Path
import gurobipy as gp
import ac8500 as ac
import production_campaign as campaign
import mess_search8500 as mess
from run_support import atomic,Metrics
from dayahead.v33m.mess_mobility_milp import add_mess_mobility_block
ASCII=Path('D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911')
assert os.path.samefile(ASCII,ac.H)
def configured(folder,label):
    relative=Path(folder).relative_to(ac.H);target=ASCII/relative;assert os.path.samefile(target,folder)
    m=gp.Model(label);m.Params.OutputFlag=0;m.Params.LogFile=str(target/'SOLVER.log');m.Params.Threads=4;m.Params.Seed=20260911;m.Params.MIPGap=.001;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9;m.Params.OptimalityTol=1e-9;m.Params.MIPFocus=1;m.Params.Method=1;m.Params.NodefileStart=.5;m.Params.NodefileDir=str(target);return m
old_check=campaign.freeze_check
def freeze_check():
    old_check()
    for r in ac.read(ac.H/'PRODUCTION_EXECUTION_V2_FREEZE.json')['files']:assert ac.sha(r['path'])==r['sha256'],r['path']
def preflight(ctx,grid):
    H=ac.H;required=['B0_REPRODUCTION_AUDIT.json','NON_ELECTRICAL_INPUT_AND_BINDING_AUDIT.json','INDEPENDENT_COMPLEX_V2/VALIDATION.json']
    for p in required:assert ac.read(H/'preflight'/p)['status']=='PASS'
    print('PREFLIGHT_STRUCTURAL_V2_BUILD_NO_OPTIMIZATION',flush=True)
    folder=H/'preflight/STRUCTURAL_V2';folder.mkdir(exist_ok=False);metrics=Metrics();meta=campaign.aidc.options_metadata(ctx);chosen=campaign.aidc.initial_indices(ctx);jobs,power,audit=campaign.aidc.materialized(ctx,chosen)
    campaign.aidc.neighborhood(ctx,grid,chosen,power,None,None,meta,0,folder/'AIDC_BUILD',metrics,lambda:0.,[.85]);assert not metrics.solve
    model=configured(folder,'IEEE8500_PREFLIGHT_MESS_BUILD_ONLY');block=add_mess_mobility_block(model,ctx.mobility_inputs);model.update();inventory=dict(route_variables=len(block.move),variables=model.NumVars,constraints=model.NumConstrs,optimization_calls=0);model.dispose()
    expected=len(ctx.initial)*sum(o!=d and t+r.connection_ready_slots_15min<=96 and r.connection_ready_slots_15min>0 for (t,o,d),r in ctx.route_table.records.items());assert inventory['route_variables']==expected and expected>0
    atomic(H/'PREFLIGHT_PASS.json',dict(status='PASS',operating_authority=ac.record(ac.STRESS/'IEEE8500_STRESS_CALIBRATED_B0_AUTHORITY.json'),checks=[ac.record(H/'preflight'/p) for p in required],structural_AIDC_solver_calls=0,MESS_build=inventory,route_aliases={s:campaign.service_alias(s) for s in ctx.route_table.service_ids},IEEE123_electrical_artifacts_reused=False,production_execution_freeze=ac.record(H/'PRODUCTION_EXECUTION_FREEZE.json'),execution_path_patch=ac.record(H/'PRODUCTION_EXECUTION_V2_FREEZE.json')))
    print('IEEE8500_PRODUCTION_PREFLIGHT_PASS',flush=True)
mess.configured=configured;campaign.freeze_check=freeze_check;campaign.preflight=preflight
if __name__=='__main__':campaign.main()
