"""B3 only; reuse final B1 and require accepted B2 physical closure."""
from common8500 import *
import traceback,gc
import aidc_runtime,mess_runtime,grid8500
from dayahead.v40g_segments.canonical import planning_power,import_frozen
from dayahead.v40a.grid import controls_from_trajectory

def verify_release():
    r=read(P/'PRODUCTION_RELEASE.json');assert r['status']=='FROZEN_AUTHORIZED'
    for f in r['code']+r['inherited_code']+r['inputs']+[r['rules']]:assert sha(f['path'])==f['sha256'],f['path']
    assert read(P/'B2/FINAL_AUTHORITY.json')['status']=='PASS'

def main():
    install_output_paths();verify_release();verify()
    assert not (P/'CAMPAIGN_STARTED.json').exists(),'PRESERVE_STARTED_RUN_NO_AUTOMATIC_RESTART'
    save(P/'CAMPAIGN_STARTED.json',dict(pid=os.getpid(),started_unix=time.time(),release=record(P/'PRODUCTION_RELEASE.json')))
    state(status='RUNNING',stage='B3:LOAD_FROZEN_DAILY_AUTHORITY',search_started=False,checkpoints={})
    started=time.perf_counter()
    try:
        ctx=new_context();b1=read(P/'B1/ACCEPTED_AIDC.json')
        with np.load(P/'B1/FINAL_POWER.npz') as z:p1={k:z[k].copy() for k in z.files}
        derived=planning_power(import_frozen(b1['jobs']),ctx)
        for key in ('pcc','qcc'):assert np.allclose(p1[key],derived[key],atol=1e-9,rtol=0),key
        save(P/'A0_REUSE_GATE.json',dict(status='PASS',B1_search_calls=0,jobs=record(P/'B1/ACCEPTED_AIDC.json'),
            power=record(P/'B1/FINAL_POWER.npz'),power_recomputed_equal=True))
        verify_release();state(stage='B3_M1:MESS_FULL_SEARCH',search_started=False)
        m1,m1info=mess_runtime.search(ctx,p1['pcc'],'B3_M1');gc.collect()
        ctx.v41_fixed_mess=m1.slots;ctx.v41_a1_seed_jobs=b1['jobs'];ctx.v41_a1_seed_pcc=p1['pcc']
        ctx.ieee8500_final_B1_seed=read(P/'FINAL_B1_REUSE.json')['seed_bundle']
        state(stage='B3_A1:ELECTRICAL_BINDING',search_started=False)
        grid8500.prepare(ctx,P/'B3_A1_electrical_rows',controls_from_trajectory(ctx.coefficients,p1['pcc'],m1.slots))
        a1=aidc_runtime.run(ctx,'B3_A1');pa1=planning_power(import_frozen(a1['jobs']),ctx);gc.collect()
        verify_release();state(stage='B3_MF:FIXED_ROUTE_PQ',search_started=False);mfstarted=time.perf_counter()
        final=mess_runtime.recourse(ctx,pa1['pcc'],m1);mfwall=time.perf_counter()-mfstarted
        ac=exact(pa1['pcc'],final.slots,P/'B3/final_exact');assert ac['status']=='PASS'
        lin=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pa1['pcc'],final.slots),ctx.nodes)
        result=dict(status='PASS',P1=lin['rho_max'],AC=ac['metrics'],A0_final_B1_reuse=True,route_searches=1,A1_passes=1,MF_passes=1,
            incremental_runtime_seconds=time.perf_counter()-started,
            total_algorithm_runtime_seconds=read(P/'B1/FINAL_AUTHORITY.json')['total_runtime_seconds']+time.perf_counter()-started,
            M1_wall_seconds=read(P/'B3_M1/FINAL_AUTHORITY.json')['wall_seconds'],MF_wall_seconds=mfwall,
            jobs=a1['jobs'],trajectory_slots=[r.to_dict() for r in final.slots])
        save(P/'B3/FINAL_AUTHORITY.json',result);verify_release()
        save(P/'CAMPAIGN_COMPLETE.json',dict(status='PASS',completed_unix=time.time(),B1_rerun=False,B2_rerun=False,
            B3=record(P/'B3/FINAL_AUTHORITY.json'),release=record(P/'PRODUCTION_RELEASE.json')))
        state(status='COMPLETE',stage='B3_COMPLETE',search_stopped=True)
    except BaseException as e:
        save(P/'CAMPAIGN_FAILURE.json',dict(status='STOPPED' if isinstance(e,KeyboardInterrupt) else 'FAIL_CLOSE',
            error=repr(e),traceback=traceback.format_exc(),all_checkpoints_preserved=True,automatic_restart=False))
        state(status='STOPPED' if isinstance(e,KeyboardInterrupt) else 'FAIL_CLOSE',stage='CAMPAIGN_STOPPED',error=repr(e),search_stopped=True)
        raise
if __name__=='__main__':main()
