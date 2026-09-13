"""Original V41R4 K/beam MESS machinery, IEEE8500 electrical ports only."""
from common8500 import *
from types import SimpleNamespace
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import inspect,shutil
import mess_grid8500
from dayahead.v33m.mess_trajectory import MessTrajectory
class Authority(dict):
    @property
    def files(self):return list(self)
    def close(self):pass
def coefficients():
    # Encode normalized phase-current norm bounds via the existing complex
    # thermal API, in addition to native winding-kVA bounds. Matrices unchanged.
    return tuple(replace(build(t),transformer_ratings=tuple([None]*NL+[1.]*NT+AX['winding_rating_kVA'])) for t in range(96))
def integrated_adapter():
    from dayahead.v34.integrated_mess import solve_integrated_mess
    src=inspect.getsource(solve_integrated_mess)
    old='if len(controls) != 60 or len(node_names) != 386:'
    assert src.count(old)==1;src=src.replace(old,'if len(controls) != 60 or len(node_names) != 8639:')
    src=src.replace('"V34_FROZEN_C376_MAPPING"','"IEEE8500_FROZEN_24_MESS_PCC"')
    start=src.index('    for slot, coefficient in enumerate(coefficients):\n        for index, node in enumerate(node_names):')
    end=src.index('    cut_rows, trust_region_constraint_count = _add_restoration_cuts(',start)
    src=src[:start]+"    assert correction is None\n    grid_constraints += ieee8500_grid(model, coefficients, expressions_by_slot, eta, inputs)\n\n"+src[end:]
    ns=dict(solve_integrated_mess.__globals__,ieee8500_grid=mess_grid8500.integrated_grid);exec(compile(src,str(P/'mess_runtime.py')+'::electrical_adapter','exec'),ns)
    save(P/'MESS_INTEGRATED_SOURCE_ADAPTER.json',dict(source=record(inspect.getsourcefile(solve_integrated_mess)),authorized_differences=['IEEE8500 node dimension','Equivalent full electrical rows with certified redundant-row presolve'],original_non_electrical_MESS_model_and_objective_unchanged=True,adapted_source=src))
    return ns['solve_integrated_mess']
def traffic():
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE
    from dayahead.v35.execution import daily_traffic_authority
    from dayahead.v35.contracts import PHASE_CALIBRATION
    from dayahead.v41.execution import SOURCE_REPO
    inventory=SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json'
    frozen=read(inventory)['traffic']['2025-05-21']
    authorities={'TRAFFIC_FORECAST.npz':frozen['forecast']['file'],'ROUTE_TABLE.json.gz':frozen['route_table']['file']}
    dest=P/'traffic/shared/traffic/2025-05-21';dest.mkdir(parents=True,exist_ok=True)
    for name in ('TRAFFIC_FORECAST.npz','ROUTE_TABLE.json.gz'):
        src=Path(authorities[name]['path']);assert src.is_file() and sha(src)==authorities[name]['sha256'],('MISSING_OR_DRIFTED_FROZEN_MAY21_TRAFFIC_AUTHORITY',src)
        out=dest/name
        if out.exists():assert sha(out)==sha(src)
        else:shutil.copyfile(src,out)
    result=daily_traffic_authority(FROZEN_MESS_WORKTREE,P/'traffic',PHASE_CALIBRATION,'2025-05-21',None)
    assert result[0].causality_pass and result[0].future_actual_read_count==0
    assert result[0].canonical_sha256==frozen['forecast']['canonical_SHA'] and result[2].canonical_sha256==frozen['route_table']['canonical_SHA']
    save(P/'MESS_TRAFFIC_AUTHORITY.json',dict(status='PASS',files=list(authorities.values()),inventory_source=record(inventory),date='2025-05-21',Actual_reads=0))
    return result
def search(ctx,pcc,policy):
    from dayahead.tools import run_v35r3e_r1_beam as beam
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    from dayahead.v37 import runner as old
    from dayahead.v35.execution import _planning_grid
    from dayahead.v36.runner import _prepare_seed_npz
    from dayahead.v39e.runtime import four_thread_fixed_candidate
    from dayahead.v40b.windows_paths import install_beam_paths
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    _install_windows_safe_k_archive();install_beam_paths()
    folder=P/policy;folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    cc=coefficients();voltage=Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes']))
    electrical=SimpleNamespace(legacy_context=None,voltage=voltage,current=Authority())
    tr=traffic();mapping={r['service']:r['PCC'] for r in read(PREF/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
    arrays,_=_planning_grid(cc,voltage,pcc,MessTrajectory(()));_prepare_seed_npz(folder,ctx.day,'B0' if policy=='B2' else 'B1',arrays,cc)
    keys=('APR01','CACHE_ROOT','prepare_aidc_stages','daily_traffic_authority','slot_coefficients','EXECUTION_CACHE_CONTEXT','PROGRESS_CALLBACK','ProcessPoolExecutor','build_fixed_candidate_model','_local_search','_solve_worker','_service_mapping','solve_integrated_mess')
    original={k:getattr(beam,k) for k in keys};guards=(r3.assert_apr01_only,r3e.assert_apr01_only);cwd=Path.cwd()
    def selected(day):assert day=='2025-05-21'
    def progress(e):state(status='RUNNING',stage=policy+':MESS_FULL_SEARCH',search_started=False,MESS_progress=dict(e))
    class Pool(ThreadPoolExecutor):
        def __init__(self,max_workers=None,initializer=None,initargs=(),**kw):super().__init__(max_workers=1,initializer=initializer,initargs=initargs)
    try:
        beam.APR01=ctx.day;beam.CACHE_ROOT=folder/'beam'
        beam.prepare_aidc_stages=lambda *a,**k:(None,electrical,{'B0':{'planning_pcc_power_kw':pcc},'B1':{'planning_pcc_power_kw':pcc}})
        beam.daily_traffic_authority=lambda *a,**k:tr;beam.slot_coefficients=lambda *a:cc[int(a[-1])]
        beam.EXECUTION_CACHE_CONTEXT=dict(stage=policy,workspace=str(P),coefficient_SHAs=[c.coefficient_sha256 for c in cc],candidate_cache_root=str(folder/'candidate_cache'),binding=sha(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),source=sha(P/'mess_runtime.py'))
        beam.PROGRESS_CALLBACK=progress;beam.ProcessPoolExecutor=Pool;beam.build_fixed_candidate_model=four_thread_fixed_candidate
        beam._local_search=lambda **kw:old._run_local_with_frozen_k_fallback(beam,original['_local_search'],**kw)
        beam._solve_worker=old._v37_safe_restricted_worker;beam._service_mapping=lambda:mapping
        beam.solve_integrated_mess=integrated_adapter();r3.assert_apr01_only=r3e.assert_apr01_only=selected
        os.chdir(folder);result=None
        for width in (2,4):
            try:result=beam._run_case('B2' if policy=='B2' else 'B3',width,1);break
            except Exception as error:
                if width==2 and old._beam_fallback_allowed(error):continue
                raise
        trajectory=MessTrajectory(tuple(beam._restore_slots(result['trajectory_slots'])))
        exact_report=exact(pcc,trajectory.slots,folder/'final_exact');assert exact_report['status']=='PASS'
        save(folder/'FINAL_AUTHORITY.json',dict(status='PASS',P1=result['planning']['rho'],AC=exact_report['metrics'],wall_seconds=time.perf_counter()-started,trajectory_slots=result['trajectory_slots'],original_K_sequence=[200,400,800,'FULL'],original_beams=[2,4],worker_count=1))
        return trajectory,result
    finally:
        os.chdir(cwd)
        for k,v in original.items():setattr(beam,k,v)
        r3.assert_apr01_only,r3e.assert_apr01_only=guards
def recourse(ctx,pcc,m1):
    from dayahead.v40a import recourse as old
    prior_functions=(old.add_grid,old.evaluate_grid);old.add_grid=mess_grid8500.add;old.evaluate_grid=evaluate_grid
    try:
        result=old.solve_fixed_route(pcc,m1,ctx)
        from dayahead.v40a.grid import controls_from_trajectory
        before=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,m1.slots),ctx.nodes)
        accepted=result['status']=='PASS' and result['grid']['rho_max']<=before['rho_max']+1e-6
        selected=result['trajectory'] if accepted else m1
        ac=exact(pcc,selected.slots,P/'B3_MF/final_exact')
        if ac['status']!='PASS':
            fallback=exact(pcc,m1.slots,P/'B3_MF/fallback_exact');assert fallback['status']=='PASS';selected=m1
        save(P/'B3_MF/RESULT.json',result)
        return selected
    finally:old.add_grid,old.evaluate_grid=prior_functions
