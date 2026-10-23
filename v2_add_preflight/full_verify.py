"""Independent completed-evidence checks and deliberate corruption tests."""
import copy,csv,unittest,types
import numpy as np
from .full_common import *

def verify():
    init();resources();import psutil;psutil.Process().cpu_affinity([13]);tests=[]
    def check(name,ok,**details):
        tests.append(dict(test=name,PASS=bool(ok),**details))
        if not ok:print('FAILED',name,flush=True)
    b=init();check('all_prior_V2_evidence_unchanged',True,files=len(b['files']))
    exact=read(OUT/'B0_FCFS_EXACT_REPLAY.json');check('B0_exact_original_FCFS_GPU_C1_and_Fresh',exact['PASS'] and exact['independent_event_Fresh_identical'])
    from .full_jobs import prepare,conservation
    args=prepare(day_input('2025-05-01'),'INDEPENDENT_VERIFY');base=read(RUN/'jobs/BASE/EVENTS.json')
    z=np.load(RUN/'jobs/BASE/PHYSICAL.npz');base.update(occupancy_GPU=z['GPU'],compute_occupancy_GPU=z['compute_GPU'])
    cert,_=conservation(base,args);check('all2498_actual_Jobs_private_service_compute_carryout',cert['PASS'],certificate=cert)
    trial=dict(base,compute_occupancy_GPU=base['compute_occupancy_GPU'].copy());trial['compute_occupancy_GPU'][30,0]+=1
    bad,_=conservation(trial,args);check('fault_injection_GPUh_corruption_rejected',not bad['PASS'])
    carry=copy.deepcopy(base['carryout']);uid=next(u for u,v in carry['simulator_only_remaining_compute_seconds'].items() if v>0)
    carry['simulator_only_remaining_compute_seconds'][uid]=0
    bad,_=conservation(dict(base,carryout=carry),args);check('fault_injection_missing_tail_rejected',not bad['PASS'],uid=uid)
    jobs=read(OUT/'AIDC_SAME_POLICY_STUDY.json')
    check('finite_AIDC_source_FULL_and_same_policy_work',read(OUT/'AIDC_ORIGINAL_FULL_SELECTED_ACCEPTANCE.json')['PASS'] and
        jobs['Fresh_identical'] and all(v['PASS'] for v in jobs['independent_work'].values()))
    check('AIDC_not_misrepresented_as_FCFS_or_campaign_FULL',jobs['full_optimizer_acceptance'] is False and jobs['GPU_scaling_run'] is False)
    manifest=read(OUT/'GRID_COEFFICIENT_MANIFEST.json');axes=read(OUT/'GRID_AXES.json')
    check('whole96_coefficient_hashes',len(manifest['records'])==96 and all(record(r['path'])['sha256']==r['sha256'] for r in manifest['records']))
    check('all_original_lines_and_both_ends_in_grid',len({r['element'] for r in axes['line']})==3703 and
        len({r['element'] for r in axes['line'] if r['group']=='Triplex'})==1177 and sum(axes['parent_mask'])==6156 and sum(axes['security_mask'])==12322)
    check('separate_building_and24_mobile_controls',len(axes['controls'])==60 and len(set(axes['controls']))==60)
    slot=read(OUT/'ONE_SLOT_NATIVE0_GRID_FIXTURE.json')
    check('actual_native_single_slot_all_families_matrix_readback',slot['PASS'] and slot['model']['linear_constraints']==210617 and
        all(b['native_readback_max_error']==0 for b in slot['blocks']))
    if (OUT/'MESS8_FULL_NATIVE0_REPORT.json').exists():
        full=read(OUT/'MESS8_FULL_NATIVE0_REPORT.json')
        check('no_partial_Native0_promotion',full['full96_Native0_build_PASS']==(full['grid_slots']==96 and full['error'] is None))
        check('original8_free_mobility_binary_domain_retained',full['mobility_before_grid']['binary']==417296 and full['original24_services_retained'])
    if (OUT/'FULL96_MATRIX_PACK_CERTIFICATION.json').exists():
        import scipy.sparse as sp
        from .full_pack import numerical,PACK
        mc=read(OUT/'FULL96_MATRIX_PACK_CERTIFICATION.json');point=np.load(mc['full_point']['path'],mmap_mode='r')
        with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:dd={k:z[k] for k in z.files}
        A=sp.load_npz(PACK/'MOBILITY.npz');proof=numerical(A,dd['rhs'],dd['sense'],point[:A.shape[1]],dd)
        totalrows=A.shape[0];totalnnz=A.nnz;allpass=proof['PASS'];hashes=True;maximum=0.;domainok=True
        for b in mc['identity']['blocks']:
            t=b['slot'];p=PACK/f'{t:02d}';B=sp.load_npz(p/'MATRIX.npz')
            with np.load(p/'ROWS.npz') as z:r=z['rhs'];sense=z['sense']
            with np.load(p/'DOMAIN.npz') as z:
                offset=len(dd['names'])+t*34329;v=point[offset:offset+34329]
                domainok &= bool(np.all(v>=z['lower']-1e-5) and np.all(v<=z['upper']+1e-5) and np.all(z['types']=='C'))
            residual=B@point-r;violation=np.maximum(0,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
            maximum=max(maximum,float(violation.max(initial=0)));totalrows+=B.shape[0];totalnnz+=B.nnz
            hashes &= all(record(vv['path'])['sha256']==vv['sha256'] for vv in (b['matrix'],b['domain'],b['rows']))
        check('complete_FULL96_saved_matrix_domain_independent_readback',mc['matrix_domain_pack_PASS'] and hashes and allpass and domainok and maximum<=1e-5
            and totalrows==mc['matrix']['rows'] and totalnnz==mc['matrix']['nonzeros'] and digest(mc['identity'])==mc['case_sha'],
            rows=totalrows,nonzeros=totalnnz,maximum_violation=maximum,all_aux_domains_PASS=domainok)
        check('FULL_matrix_pack_not_promoted_to_monolithic_or_campaign',not mc['monolithic_full_Gurobi_build_PASS'] and not mc['K48_Beam_Joint_stage_connected'])
    # Independently verify each as-of witness against the unchanged original
    # hourly source, including exactly which prior finite row was held.
    import pandas as pd
    source=read(day_input('2025-05-01')['files']['provenance']['path'])['raw_realized_sources']['weather']
    f=pd.read_parquet(source['path'],columns=['ts','t_wb_c','rh_pct']);st=np.array([pd.Timestamp(v).timestamp() for v in f.ts]);vals=f[['t_wb_c','rh_pct']].to_numpy(float)
    for p in sorted(OUT.glob('WEATHER_ASOF_*.csv')):
        ok=True
        for r in csv.DictReader(p.open(encoding='utf-8')):
            now=float(r['decision_seconds']);ix=np.flatnonzero((st<=now)&np.isfinite(vals).all(axis=1));j=int(ix[np.argmax(st[ix])])
            ok &= st[j]==float(r['observed_seconds']) and now-st[j]<=7200 and np.array_equal(vals[j],[float(r['t_wb_c']),float(r['rh_pct'])])
        check('independent_weather_asof_'+p.stem[-10:],ok)
    continuation=[]
    for date,count in [('2025-05-03',2),('2025-05-07',5)]:
        fix=read(OUT/('AIDC_DAY_'+date+'_EXTERNAL_RUNNING_CONTINUATION.json'));e=read(RUN/'jobs'/('DAY_'+date)/'EVENTS.json')
        initial=read(day_input(date)['files']['initial_running_authority']['path'])['mapping'];q={r['uid']:r for r in e['qos_ledger']};ok=len(fix['UIDs'])==count
        for uid in fix['UIDs']:
            b=e['qos_budget_ledger'][uid];j=e['carryout']['controller']['episode_jobs'][uid]
            ok &= b['budget_seconds']==0 and q[uid]['total_intentional_burden_seconds']==0 and j['current_site']==initial[uid]
        continuation.append(dict(day=date,count=count,PASS=ok))
    check('dated_external_Running_continuation_preserves_site_and_zero_flexibility',all(r['PASS'] for r in continuation),days=continuation)
    from .full_execution import require_campaign
    try:require_campaign('NONEXISTENT_APPROVAL_FILE')
    except PermissionError as exc:check('new_campaign_HOLD_rejects_before_approval_IO',str(exc)=='PRESTART_BLOCKED_WITH_EVIDENCE')
    else:check('new_campaign_HOLD_rejects_before_approval_IO',False)
    # Prior acceptance/checkpoint contracts are exercised without invoking
    # their report writer or any physical/campaign worker.
    from .prestart_verify import PrestartTests
    names=['test_bad_golden_cache_reaches_actual_acceptance_and_is_rejected','test_reference_full_job_domain_and_joint_resource_validation',
        'test_a1_reuse_binds_every_case_and_acceptance_field','test_scheduler_failure_isolated_and_resume_does_not_reexecute',
        'test_checkpoint_detects_mutated_artifact_and_source','test_duplicate_lock_is_denied_without_stale_pid_bypass',
        'test_generic_pass_cannot_authorize_full_stage_or_prefix','test_campaign_hold_rejects_before_missing_user_permit_is_read']
    suite=unittest.TestSuite(PrestartTests(n) for n in names);result=unittest.TextTestRunner(verbosity=1).run(suite)
    check('original_acceptance_checkpoint_HOLD_regressions',result.wasSuccessful(),tests=result.testsRun,
        errors=[str(e) for e in result.errors],failures=[str(e) for e in result.failures])
    put('INDEPENDENT_INTEGRATION_TESTS.json',dict(PASS=all(t['PASS'] for t in tests),checks=tests,Native_calls=0,
        complete_campaign_FULL_certification=False))
    print('INDEPENDENT INTEGRATION',len(tests),all(t['PASS'] for t in tests),flush=True)

if __name__=='__main__':verify()
