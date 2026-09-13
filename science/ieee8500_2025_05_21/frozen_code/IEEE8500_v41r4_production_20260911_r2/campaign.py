from common8500 import *
import traceback,gc
import aidc_runtime,mess_runtime,grid8500
from dayahead.v40g_segments.canonical import planning_power,import_frozen
from dayahead.v40a.grid import controls_from_trajectory
def verify_release():
    r=read(P/'PRODUCTION_RELEASE.json');assert r['status']=='FROZEN_AUTHORIZED'
    for f in r['code']:assert sha(f['path'])==f['sha256'],f['path']
def policy(name,authority):
    v=read(P/'STATUS.json');results=v.get('policy_results',{});results[name]=authority
    state(policy_results=results)
def main():
    install_output_paths();verify_release();assert read(P/'LAUNCH_INPUTS.json')['status']=='PASS'
    if (P/'CAMPAIGN_STARTED.json').exists():raise RuntimeError('PRESERVE_STARTED_RUN_NO_AUTOMATIC_RESTART')
    save(P/'CAMPAIGN_STARTED.json',dict(pid=os.getpid(),started_unix=time.time(),release=record(P/'PRODUCTION_RELEASE.json')))
    ctx=new_context();policy('B0',dict(status='PASS',P1=read(P/'B0/FINAL.json')['metrics']['max_phase_line_loading_pu']))
    try:
        b1=aidc_runtime.run(ctx,'B1');p1=planning_power(import_frozen(b1['jobs']),ctx)
        np.savez_compressed(P/'B1/FINAL_POWER.npz',**p1);policy('B1',read(P/'B1/FINAL_AUTHORITY.json'));gc.collect()
        verify_release();b2,_=mess_runtime.search(ctx,ctx.power['pcc'],'B2');policy('B2',read(P/'B2/FINAL_AUTHORITY.json'));del b2;gc.collect()
        verify_release();b3started=time.perf_counter();m1,m1info=mess_runtime.search(ctx,p1['pcc'],'B3_M1');gc.collect()
        ctx.v41_fixed_mess=m1.slots;ctx.v41_a1_seed_jobs=b1['jobs'];ctx.v41_a1_seed_pcc=p1['pcc']
        checkpoint=b1['solver_stages'][-1]['checkpoint']
        ctx.ieee8500_final_B1_seed=dict(status='FINAL_B1_INDEPENDENTLY_VALIDATED',candidate_stream_sha256=EXPECTED,binding_gate_sha256=sha(BIND/'IEEE8500_V41R4_AIDC_BINDING_PASS.json'),assignment=checkpoint,variable_names=record(P/'B1/POLICY_FEASIBLE_SEED.npz'))
        state(stage='B3_A1:ELECTRICAL_BINDING',search_started=False)
        grid8500.prepare(ctx,P/'B3_A1_electrical_rows',controls_from_trajectory(ctx.coefficients,p1['pcc'],m1.slots))
        a1=aidc_runtime.run(ctx,'B3_A1');pa1=planning_power(import_frozen(a1['jobs']),ctx);gc.collect()
        verify_release();state(stage='B3_MF:FIXED_ROUTE_PQ',search_started=False);mfstarted=time.perf_counter()
        final=mess_runtime.recourse(ctx,pa1['pcc'],m1);mfwall=time.perf_counter()-mfstarted
        ac=exact(pa1['pcc'],final.slots,P/'B3/final_exact');assert ac['status']=='PASS'
        lin=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pa1['pcc'],final.slots),ctx.nodes)
        result=dict(status='PASS',P1=lin['rho_max'],AC=ac['metrics'],A0_final_B1_reuse=True,route_searches=1,A1_passes=1,MF_passes=1,incremental_runtime_seconds=time.perf_counter()-b3started,total_algorithm_runtime_seconds=read(P/'B1/FINAL_AUTHORITY.json')['total_runtime_seconds']+time.perf_counter()-b3started,M1_wall_seconds=read(P/'B3_M1/FINAL_AUTHORITY.json')['wall_seconds'],MF_wall_seconds=mfwall,jobs=a1['jobs'],trajectory_slots=[r.to_dict() for r in final.slots])
        save(P/'B3/FINAL_AUTHORITY.json',result);policy('B3',result)
        save(P/'CAMPAIGN_COMPLETE.json',dict(status='PASS',completed_unix=time.time(),policies={p:record(P/p/('FINAL.json' if p=='B0' else 'FINAL_AUTHORITY.json')) for p in ('B0','B1','B2','B3')}))
        state(status='COMPLETE',stage='B0_B1_B2_B3_COMPLETE',search_stopped=True)
    except BaseException as e:
        save(P/'CAMPAIGN_FAILURE.json',dict(status='STOPPED' if isinstance(e,KeyboardInterrupt) else 'FAIL_CLOSE',error=repr(e),traceback=traceback.format_exc(),all_checkpoints_preserved=True,automatic_restart=False))
        state(status='STOPPED' if isinstance(e,KeyboardInterrupt) else 'FAIL_CLOSE',stage='CAMPAIGN_STOPPED',error=repr(e),search_stopped=True);raise
if __name__=='__main__':main()
