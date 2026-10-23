"""Independent checks and final scope certificates. No operating AC solves."""
from collections import Counter
from pathlib import Path
import ast,csv,gzip,json,subprocess
import numpy as np
from .prestart import ROOT,DOC,OUT,RUN,read,sha,put,table,record,digest,INITIAL,SOURCE

def geometry():
    path=DOC/'AIDC12_STA12_PCC_MAPPING.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8')))
    a=np.array([[float(v['source_or_proxy_x']),float(v['source_or_proxy_y'])] for v in rows])
    b=np.array([[float(v['common_frame_x_km']),float(v['common_frame_y_km'])] for v in rows])
    x=a-a.mean(0);y=b-b.mean(0);M=np.linalg.lstsq(x,y,rcond=None)[0];pred=x@M+b.mean(0)
    assert np.max(abs(pred-b))<1e-8 and np.linalg.det(M)>0
    return put('LOCATION_COMMON_TRANSFORM_READBACK.json',dict(source=record(path),row_vector_matrix=M.tolist(),
        source_centroid=a.mean(0).tolist(),common_frame_centroid=b.mean(0).tolist(),positive_uniform_scale=float(np.sqrt(np.linalg.det(M))),
        rotation_degrees=float(np.rad2deg(np.arctan2(M[0,1],M[0,0]))),max_coordinate_reproduction_error=float(np.max(abs(pred-b))),
        reflection=bool(np.linalg.det(M)<0),field_GIS_claim=False,services=[v['route_service_id'] for v in rows]))

def fleet():
    from .prestart_native import inputs
    from v42_native.mess import validate
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0];bundle=read(day['files']['native']['path'])
    sites,initial,routes,battery,receipt=inputs(bundle,INITIAL)
    rows=list(csv.DictReader((OUT/'TWO_PEAK_UNIT_TRAJECTORIES.csv').open(encoding='utf-8')));checks=[]
    for name in sorted({r['schedule'] for r in rows}):
        units=[r for r in rows if r['schedule']==name];by={(r['vehicle'],int(r['slot'])):r for r in units}
        values={};chosen={}
        for u,origin in initial.items():
            chosen[u]=[sites.index(origin)*96+t for t in range(96)]
            for t in range(97):values[f'SOC[{u},{t}]']=float(by[u,min(t,95)]['SOC_start' if t<96 else 'SOC_end'])
            for s in sites:
                for t in range(96):
                    r=by[u,t];p=float(r['P_demand_kw']) if s==origin else 0.;q=float(r['Q_demand_kvar']) if s==origin else 0.
                    values[f'Pch[{u},{s},{t}]']=max(p,0);values[f'Pdis[{u},{s},{t}]']=max(-p,0);values[f'Q[{u},{s},{t}]']=-q
        proof=validate(dict(values=values,initial_sites=initial,chosen_arcs=chosen,mode='MILP'),sites,routes,battery,96)
        assert proof['PASS']
        proof.update(schedule=name,Original_source=record(ROOT/'v42_native/mess.py'),Q250_PASS=all(abs(float(r['Q_demand_kvar']))<=250 for r in units),
            one_per_STA_PASS=len(set(initial.values()))==8,selected_route_is_STAY_witness_only=True,optimizer_MOVE_restricted=False)
        checks.append(proof)
    tabledata=json.loads(gzip.decompress(Path(bundle['route_table']['path']).read_bytes()))
    moves=[]
    local=list(csv.DictReader((OUT/'TWO_PEAK_LOCAL_PCC_SENSITIVITY.csv').open(encoding='utf-8')))
    response={(x['site'],int(x['eval_slot']),x['direction']):float(x['delta_loading_pp']) for x in local}
    for u,s in initial.items():
        for dest in (x for x in sites if x.startswith('STA') and x!=s):
            r=next(x for x in tabledata['routes'] if x['origin_service_id']==s and x['destination_service_id']==dest and x['departure_slot_15']==35)
            moves.append(dict(vehicle=u,initial=s,destination=dest,departure=35,connect=35+r['connection_ready_slots_15min'],
                energy_safe_kWh=r['energy_safe_kwh'],ready_before_evening_68=35+r['connection_ready_slots_15min']<=68,
                slot74_delta_P_response_pp_per5=response[dest,74,'P']-response[s,74,'P'],
                slot74_delta_Q_response_pp_per5=response[dest,74,'Q']-response[s,74,'Q'],
                scope='Frozen route availability and local fixed-state response; no optimized MOVE/control schedule certified'))
    table('MESS8_MOVE_REACHABILITY_AND_LOCAL_VALUE.csv',moves)
    new=read(OUT/'MESS8_NATIVE0_BUILD_REPORT.json');eight=next(x for x in new['builds'] if x['units']==8)
    return put('MESS8_ROUTE_SOC_PQ_PORT_CERTIFICATION.json',dict(
        status='FINITE_STAY_WITNESSES_PASS_FULL_MOVE_AND_GRID_CONTRACT_BLOCKED',initial_sites=INITIAL,
        first4='Original V44 daily initial states; unchanged',extra4='Existing PR236 preregistered STA02/03/04/05; not optimization-selected',
        original_route_receipt=receipt,finite_witnesses=checks,battery=vars(battery),Q_kvar_limit=250,PCS_faces=16,
        STA480V_750kVA_port600kVA_occupancy1=True,Actual_TIME_eval96_and_Fresh='TWO_PEAK_FRESH_CHECKS.json',
        full120_voltage_PASS=False,all8_MOVE_STAY_modelled=all(v>0 for v in eight['context']['reachable_move_columns_by_unit'].values()),
        IDC12_route_destination_mobile_PCS_hardware_certified=False,complete_joint_FULL_model_PASS=False,
        initial_alternatives_selected_using_Actual=False,additional_vehicles_10_12_added=False,
        independent_source_validator='v42_native.mess.validate; coupled port/Q250 plus allAC line/tx/SVR/security checks remain separate'))

def equivalence():
    paths=['v42_native/mess.py','v42_native/aidc.py','v42_job_capability.py','v42_temporal/native.py',
        'v44/q250_m4.py','v44/config.py','v44/planning.py','v44/stages.py','v44/worker.py',
        'v43_mess/library.py','v43_mess/case.py','v42_may_campaign_native90/m_model.py',
        'v42_integrated/contract.py','v42_m1_research/check_ub.py']
    sources=[]
    for path in paths:
        original=subprocess.check_output(['git','show',SOURCE+':'+path],cwd=ROOT)
        source=(ROOT/path).read_bytes()
        sources.append(dict(path=path,pinned_source_SHA=sha(original),working_SHA=sha(source),byte_identical=source==original,
            AST_equivalent=ast.dump(ast.parse(original.decode('utf-8-sig')))==ast.dump(ast.parse(source.decode('utf-8-sig')))))
    assert all(r['AST_equivalent'] for r in sources)
    # Preserve the non-comparable experimental replay and refuse attribution.
    aidc=read(OUT/'AIDC_CAUSAL_FLEXIBILITY_CERTIFICATION.json')
    put('AIDC_CAUSAL_DIAGNOSTIC_REJECTION.json',dict(status='REJECTED_AS_CERTIFIED_FLEXIBILITY_WITNESS',
        diagnostic=record(OUT/'AIDC_CAUSAL_FLEXIBILITY_CERTIFICATION.json'),
        reasons=['Control/reference used different original flexible dispatch paths; baseline differs from frozen r043 FCFS',
                 'Whole-population day compute GPUh differs; terminal carryout/completion work equality not independently closed',
                 'Original FULL joint Job/grid validation and current r043 policy integration absent'],
        baseline_frozen_max_error_kw=aidc['baseline_vs_existing_frozen_P_max_kw'],
        observed_day_GPUh_delta=aidc['GPUh_total_change'],nonzero_certified_Actual_flexible_kw=None,
        observed_nonzero_diagnostic_is_not_feasible_original_campaign_power=True))
    return put('IEEE8500_V44_R043_FULL_EQUIVALENCE.json',dict(status='NOT_CERTIFIED',PASS=False,source_commit=SOURCE,source_functions=sources,
        source_file_writes=0,original_mobility_all8_Native0='PASS_WITH_SCOPE_IN_MESS8_NATIVE0_BUILD_REPORT',
        Native_fixture_A1_M1_A2_M2='ORIGINAL_NATIVE_STAGE_FIXTURE_CALLS.json; native builders only',
        Planning_cache_acceptance='Strict original FULL per-job/joint-resource verifier rejects414 starts; no new accepted A1 point',
        remaining={'IEEE8500_Planning96_response_coefficients':'NOT_GENERATED_OR_BOUND',
            'all_line_parent_objective_and_both_end_linear_safety_rows':'AC verified separately; not present in Native0 mobility matrix',
            'all_original_transformer_and_SVR_rows':'Actual AC rated; current Native wrappers still120 IEEE123 rows',
            'K48_Beam_DirectJoint_originalFULL':'Not bound to8500/8car; no root/pricing/Joint solve',
            'A2_M1_exact_handoff':'Source function preserved; actual8500 complete-case test missing',
            'Global_LB_UB_gap':'No new bounds; cannot copy IEEE123/old-date/restricted bounds',
            'Source_QoS_and_causal_FULL_Job':'No accepted nonzero Actual witness; diagnostic rejected',
            'MESS_IDC12_PCS_connection':'Route graph permits24 services; only12 STA LV ports certified'},
        forbidden_shortcuts_used=False,IEEE123_vs_IEEE8500_FULL_performance_measured=False,real8500_8car_FULL_build_PASS=False))

def preserve_and_archive():
    old=read(OUT/'BASELINE_PRESERVATION.json');bad=[p for p,h in old['files'].items() if sha((ROOT/p).read_bytes())!=h]
    assert not bad,bad
    records=[record(p) for p in sorted(RUN.rglob('*')) if p.is_file() and p.suffix in ('.json','.npz')]
    put('PRESTART_RUNTIME_ARCHIVE_MANIFEST.json',dict(records=records,scope='Owned prestart diagnostics only; large arrays remain in separate runtime',Native_optimizer_calls=0))
    put('BASELINE_PRESERVATION_RESULT.json',dict(PASS=True,baseline=old['commit'],unchanged_files=len(old['files']),changed_old_files=bad,
        existing_workers_forced_terminated=False,only_owned_observer_overhead_diagnostic_interrupted=True))

if __name__=='__main__':
    geometry();fleet();equivalence();preserve_and_archive()
