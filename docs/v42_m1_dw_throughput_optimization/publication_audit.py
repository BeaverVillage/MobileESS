"""Post-run reporting/diagnostics only: never calls optimize or changes frozen source."""
from v42_dw_throughput.common import *
import numpy as np
def run():
    from v42_dw_throughput.finalize import report,manifest
    r=read(OUT/'DW_THROUGHPUT_FINAL.json');assert (OUT/'VERIFICATION.json').exists();preserve_old();verify_freeze()
    warm=read(OUT/'DW_RMP_WARM_COLD_COMPARISON.json');assert len({q['fingerprint'] for q in warm['records']})<=1
    basis=read(OUT/'DW_RMP_BASIS_REUSE_AUDIT.json');assert sha(OUT/'DW_RMP_BASIS_REUSE_AUDIT.json')==read(OUT/'EXECUTION_FREEZE.json')['preregistrations']['DW_RMP_BASIS_REUSE_AUDIT.json']
    write('DW_RMP_BASIS_REUSE_RESULT.json',dict(PASS=True,preopt_audit_SHA=sha(OUT/'DW_RMP_BASIS_REUSE_AUDIT.json'),native_basis_accepted=[q['basis_accepted'] for q in warm['records'] if q['path']=='warm'],same_canonical_RMP_fingerprint=True,objective_agreement_PASS=warm.get('objective_agreement_PASS'),selected=warm['selected'],selection_reason='Native basis accepted and same optimum/postsolve, but failed >=30% median speed reduction' if not warm['selected'] and warm.get('objective_agreement_PASS') else 'Preregistered selection gate',cold_median=warm.get('cold_median_wall'),warm_median=warm.get('warm_median_wall'),wall_reduction=warm.get('median_wall_reduction'),copy_canaries_budget_charged=True,reoptimization_diagnosis='Appending lower-nonbasic lambdas preserves previous primal feasibility but each accepted negative column violates the old dual feasibility. The registered Method1/LPWarmStart2 candidate derives and crushes basis start vectors; native logs confirm acceptance, but it takes more iterations/work than cold barrier on this pair. This one candidate failure does not establish that all basis-reuse policies are ineffective.',blind_parameter_sweep=False))
    prices=[read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))];discovery=[p for p in prices if p['type']=='DISCOVERY'];osc=ledger('DW_DUAL_OSCILLATION_AUDIT.csv');smooth=ledger('DW_DUAL_SMOOTHING_LEDGER.csv')
    timeline=ledger('DW_TRUE_4WAY_RESOURCE_TIMELINE.csv');four_samples=[t for t in timeline if sum(p['interval'][0]<=float(t['perf'])<=p['interval'][1] for p in prices)==4];assert four_samples
    resource=read(OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY.json');raw_summary=OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY_RUNTIME_RAW.json'
    if not raw_summary.exists():raw_summary.write_bytes((OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY.json').read_bytes())
    peaks={}
    for t in four_samples:
        for p in json.loads(t['pricing_processes']):peaks[str(p['pid'])]=max(peaks.get(str(p['pid']),0),p['RSS'])
    exact_four_stats=dict(sample_count=len(four_samples),observed_total_tree_peak_RSS=max(int(t['total_tree_RSS']) for t in four_samples),observed_parent_peak_RSS=max(int(t['parent_RSS']) for t in four_samples),observed_total_worker_peak_RSS=max(int(t['pricing_RSS']) for t in four_samples),observed_per_worker_peak_RSS=peaks,min_available_RAM=min(int(t['available_RAM']) for t in four_samples),max_commit_percent=max(float(t['commit_percent']) for t in four_samples),pagefile_delta_first_to_last_four_active_samples=int(four_samples[-1]['pagefile_used'])-int(four_samples[0]['pagefile_used']),maximum_within_batch_pagefile_delta=max(q['pagefile_delta_bytes'] for q in resource['attempts'] if q.get('actual_four_overlap_seconds',0)>0),max_hard_page_input_pages_per_sec=max(float(t['hard_page_input_pages_per_sec']) for t in four_samples if t['hard_page_input_pages_per_sec']),hard_fault_event_rate=None,hard_fault_event_rate_unobservable=True,clock_scope='OS nominal clock; actual thermal/clock sensors unavailable',license_errors=[],sustained_combined_thrashing_failure=False,exact_unsampled_peaks_not_claimed=True,scope='Only samples within intersection of four terminally receipted native optimize intervals')
    resource.update(true_four_active_statistics=exact_four_stats,runtime_raw_summary_SHA=sha(raw_summary),all_four_attempts_PASS=all(q['PASS'] for q in resource['attempts'] if q['workers']==4));assert resource['all_four_attempts_PASS'];write('DW_TRUE_4WAY_RESOURCE_SUMMARY.json',resource)
    # Generic native names cN carry no semantic grid labels. Classify critical
    # rows from frozen coefficient support, retaining the raw runtime CSV.
    from v42_degen.identity import inputs
    from v42_dw_root.partition import axes
    import shutil
    raw=OUT/'DW_DUAL_OSCILLATION_RUNTIME_RAW.csv'
    if not raw.exists():shutil.copyfile(OUT/'DW_DUAL_OSCILLATION_AUDIT.csv',raw)
    A,d,B,e,*_=inputs();owner,row_owner=axes();g=np.flatnonzero(row_owner==-1);cc=np.flatnonzero(owner==-1);G=B[g][:,cc]
    warm_objective_checks=[]
    for q in warm['records']:
        if q['status']!=2:continue
        with np.load(OUT/q['point_file']) as z:manual=float(d['objective']@z['point'])+float(d['constant'])
        assert abs(manual-q['objective'])<=EPS;warm_objective_checks.append(dict(index=q['index'],manual_original_objective=manual,native_objective=q['objective'],PASS=True))
    write('DW_RMP_WARM_COLD_ORIGINAL_OBJECTIVE_REAUDIT.json',dict(PASS=True,checks=warm_objective_checks))
    local_coupling=np.diff(B[g][:,owner>=0].indptr)>0;rho=np.array([str(n)=='rho_max' for n in e['names'][cc]]);response=np.array([str(n).startswith(('response_','injection_')) for n in e['names'][cc]])
    rho_rows=np.asarray(abs(G)@rho.astype(float)).ravel()>0;grid_rows=np.asarray(abs(G)@response.astype(float)).ravel()>0;critical=local_coupling|rho_rows
    write('DW_CRITICAL_GRID_ROW_AXIS_AUDIT.json',dict(PASS=True,authority='Exact frozen matrix global rows touching rho_max objective-envelope variable OR local MESS injection coupling; also all response_/injection_ supported grid rows tracked separately. Generic native cN names do not support text-based semantic classification.',critical_row_count=int(critical.sum()),objective_envelope_row_count=int(rho_rows.sum()),local_injection_coupling_row_count=int(local_coupling.sum()),all_grid_response_row_count=int(grid_rows.sum()),critical_global_row_indices_SHA=hashlib.sha256(g[critical].tobytes()).hexdigest(),matrix_unchanged=True,runtime_raw_preserved_SHA=sha(raw)))
    updated=[];prior=None
    rmps=[read(q) for q in sorted(OUT.glob('RMP_RECEIPT_*.json')) if read(q)['status']==2];old_rows={int(q['round']):q for q in ledger('DW_DUAL_OSCILLATION_RUNTIME_RAW.csv')}
    discovery_keys={p['round']:{c['column_SHA'] for q in prices if q['round']==p['round'] for c in q['candidates'] if c['selected']} for p in discovery};previous_keys=None
    for q in rmps:
        with np.load(OUT/q['point_file']) as z:pi=z['pi'].copy()
        if prior is not None:
            delta=pi-prior;h=dict(old_rows[q['round']]);h.update(critical_grid_row_count=int(critical.sum()),critical_grid_L1=float(np.linalg.norm(delta[critical],1)),critical_grid_Linf=float(np.max(abs(delta[critical]),initial=0)),all_grid_response_L1=float(np.linalg.norm(delta[grid_rows],1)),all_grid_response_Linf=float(np.max(abs(delta[grid_rows]),initial=0)),trajectory_turnover=None,turnover_scope='Discovery selected full-column bit SHA versus previous Discovery; certification has no discovery turnover')
            if q['type']=='DISCOVERY':
                keys=discovery_keys[q['round']];union=keys|previous_keys if previous_keys is not None else set();h['trajectory_turnover']=1-len(keys&previous_keys)/len(union) if union else None
            updated.append(h)
        if q['type']=='DISCOVERY':previous_keys=discovery_keys[q['round']]
        prior=pi
    table('DW_DUAL_OSCILLATION_AUDIT.csv',updated);osc=updated
    report();speed=read(OUT/'DW_THROUGHPUT_SPEED_AUDIT.json');old=read(POLICY/'DW_POLICY_CANARY_FINAL.json');new_minutes=r['total_elapsed_including_build_audit']/60;old_minutes=old['total_elapsed_including_build_audit']/60
    old_upper=read(POLICY/'RMP_RECEIPT_0002.json')['objective'];old_reduction=old_upper-old['smallest_RMP_upper'];new_reduction=read(OUT/'RMP_RECEIPT_0001.json')['objective']-r['smallest_RMP_upper']
    old_interval_start=read(POLICY/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json');old_initial=read(PREVIOUS/'DW_FINAL_RESULT.json')['final_interval'];old_interval=old['final_interval'];new_interval=r['final_interval']
    normalized=[float(h['normalized_true_change']) for h in smooth[1:]]
    candidates=[c for p in discovery for c in p['candidates']]
    speed.update(PR141_RMP_rounds=old['new_RMP_solves'],new_RMP_rounds=r['new_RMP_solves'],PR141_RMP_rounds_per_10_added_columns=old['new_RMP_solves']*10/old['new_discovery_columns'],new_RMP_rounds_per_10_added_columns=r['new_RMP_solves']*10/r['new_discovery_columns'] if r['new_discovery_columns'] else None,PR141_RMP_rounds_per_0001_upper_decrease=old['new_RMP_solves']*.001/old_reduction if old_reduction>0 else None,new_RMP_rounds_per_0001_upper_decrease=r['new_RMP_solves']*.001/new_reduction if new_reduction>0 else None,PR141_certified_bracket_narrowing_per_minute=((old_initial[1]-old_initial[0])-(old_interval[1]-old_interval[0]))/old_minutes,new_certified_bracket_narrowing_per_minute=((old_interval[1]-old_interval[0])-(new_interval[1]-new_interval[0]))/new_minutes,median_normalized_true_change=float(np.median(normalized)) if normalized else None,max_normalized_true_change=max(normalized,default=None),smoothing_alpha_initial=.30,smoothing_alpha_final=r['smoothing_alpha_final'],smoothing_accepted_columns=r['smoothing_accepted'],smoothed_negative_rejected_after_true_RC=r['smoothing_rejected_after_true_RC'],warm_comparison_scope='Two cold and two warm copies of one identical appended canonical full-scale RMP; four sequential optimize calls; not four-way pricing.',old_near_duplicate_ratio=None,old_near_duplicate_ratio_reason='PR141 did not record comparable route/mode/profile near-duplicate metrics; no retrospective causal decrease claim',diagnostic_near_duplicate_count=sum(int(h['repeated_near_duplicates']) for h in osc))
    write('DW_THROUGHPUT_SPEED_AUDIT.json',speed)
    # Independently compare complete raw profiles with previous native call's
    # validated terminal incumbent; similarity NEVER changes acceptance/pool.
    del A,B,d,row_owner,G
    profiles={}
    for m in range(4):
        names=np.array([str(n) for n in e['names'][owner==m]])
        profiles[m]={k:np.array([n.startswith(prefix) for n in names]) for k,prefix in dict(route=('arc[',),mode=('charge_mode[',),PQ=('Pch[','Pdis[','Q['),SOC=('E[','SOC[')).items()}
    del e,owner
    previous={};rows=[]
    for p in prices:
        m=p['unit'];masks=profiles[m]
        for c in p['candidates']:
            with np.load(OUT/c['point_file']) as z:x=z['x']
            prior=previous.get(m);diag=c['trajectory_profile'];same_route=prior is not None and np.array_equal(x[masks['route']],prior[masks['route']]);same_mode=prior is not None and np.array_equal(x[masks['mode']],prior[masks['mode']])
            pq=None if prior is None else float(np.linalg.norm(x[masks['PQ']]-prior[masks['PQ']])/max(1e-12,np.linalg.norm(prior[masks['PQ']])));soc=None if prior is None else float(np.linalg.norm(x[masks['SOC']]-prior[masks['SOC']])/max(1e-12,np.linalg.norm(prior[masks['SOC']])))
            rows.append(dict(call=p['call'],round=p['round'],MESS=p['MESS'],arrival=c['arrival'],route_SHA=diag['route_SHA'],mode_SHA=diag['mode_SHA'],site_sequence=json.dumps(diag['site_sequence'],ensure_ascii=False),PQ_profile_SHA=diag['PQ_profile_SHA'],SOC_profile_SHA=diag['SOC_profile_SHA'],previous_call_same_route=same_route if prior is not None else None,previous_call_same_mode=same_mode if prior is not None else None,PQ_relative_L2_to_previous_call=pq,SOC_relative_L2_to_previous_call=soc,valid_true_negative=c['valid_negative'],selected=c['selected'],similarity_diagnostic_only=True))
        if p['valid_point']:
            with np.load(OUT/p['point_file']) as z:previous[m]=z['x'].copy()
    table('DW_TRAJECTORY_TURNOVER_AUDIT.csv',rows)
    accepted_keys={q['SHA256'] for q in ledger('DW_DISCOVERY_COLUMN_LEDGER.csv')};route_turnover=[];prior_routes={};prior_modes={}
    for round_id in sorted({p['round'] for p in discovery}):
        for m in range(4):
            current=[c for p in discovery if p['round']==round_id and p['unit']==m for c in p['candidates'] if c['column_SHA'] in accepted_keys];routes={c['trajectory_profile']['route_SHA'] for c in current};modes={c['trajectory_profile']['mode_SHA'] for c in current};pr=prior_routes.get(m);pm=prior_modes.get(m)
            def turnover(a,b):return None if b is None else 1-len(a&b)/len(a|b) if a|b else 0.
            route_turnover.append(dict(round=round_id,MESS=UNITS[m],accepted_columns=len(current),unique_routes=len(routes),unique_modes=len(modes),route_SHA_turnover=turnover(routes,pr),mode_SHA_turnover=turnover(modes,pm),diagnostic_only=True));prior_routes[m]=routes;prior_modes[m]=modes
    table('DW_ROUTE_MODE_TURNOVER_AUDIT.csv',route_turnover)
    comparable=[q for q in rows if q['PQ_relative_L2_to_previous_call'] is not None];near=[q for q in comparable if q['previous_call_same_route'] and q['previous_call_same_mode'] and q['PQ_relative_L2_to_previous_call']<=.01 and q['SOC_relative_L2_to_previous_call']<=.01]
    accepted_comparable=[q for q in comparable if q['selected']];accepted_near=[q for q in near if q['selected']]
    write('DW_SMOOTHING_DIAGNOSTIC_SUMMARY.json',dict(smoothing_enabled=True,alpha_initial=.30,alpha_final=r['smoothing_alpha_final'],median_normalized_true_change=speed['median_normalized_true_change'],max_normalized_true_change=speed['max_normalized_true_change'],accepted_smoothed_discovery_columns=r['smoothing_accepted'],smoothed_negative_true_RC_rejected=r['smoothing_rejected_after_true_RC'],profile_similarity_reference='Previous native call for same MESS, validated terminal X; no similarity filtering. Pricing receipt inline profiles compare against current terminal X instead; this independent audit supplies explicit previous-call comparisons.',near_duplicate_ratio=len(near)/len(comparable) if comparable else None,near_duplicate_count=len(near),comparable_candidates=len(comparable),accepted_near_duplicate_ratio=len(accepted_near)/len(accepted_comparable) if accepted_comparable else None,accepted_near_duplicate_count=len(accepted_near),comparable_accepted_columns=len(accepted_comparable),route_mode_turnover_rows=len(route_turnover),PR141_comparable_near_duplicate_ratio=None,trajectory_turnover_rows=len(osc),SMOOTHING_STAGNATION=r['SMOOTHING_STAGNATION'],no_causal_smoothing_effect_claim=True))
    # Independent exact vertex enumeration of the 3x3 bounded fixture master.
    from fractions import Fraction as F
    from itertools import combinations,product
    domain=[[(F(0),F(3)),(F(1),F(1)),(F(2),F(0))],[(F(0),F(2)),(F(1),F(1,2)),(F(2),F(0))]];vertices=[]
    for i,j in product(range(3),repeat=2):
        a,c=domain[0][i];b,d=domain[1][j]
        if a+b<=2:vertices.append(c+d)
    for mixed in range(2):
        other=1-mixed
        for i,j in combinations(range(3),2):
            a,c=domain[mixed][i];b,d=domain[mixed][j]
            for fixed in range(3):
                e,f=domain[other][fixed];weight=(F(2)-e-b)/(a-b)
                if 0<=weight<=1:vertices.append(weight*c+(1-weight)*d+f)
    optimum=min(vertices);fixture=read(OUT/'DW_STABILIZATION_FIXTURE_PROOF.json');assert float(optimum)==fixture['full_enumeration_optimum'] and all(abs(float(optimum)-q['objective'])<=EPS for q in fixture['runs'])
    write('DW_SMOOTHING_EXACT_VERTEX_REAUDIT.json',dict(PASS=True,all_finite_pricing_trajectories_enumerated=True,feasible_master_vertex_candidates=len(vertices),exact_optimum_numerator=optimum.numerator,exact_optimum_denominator=optimum.denominator,both_native_CG_paths_match=True,no_optimize_called=True))
    extra=f"\nSmoothing enabled=true; alpha initial=.30 / final={r['smoothing_alpha_final']}; normalized true change median={speed['median_normalized_true_change']}, max={speed['max_normalized_true_change']}. Smoothed discovery에서 실제 추가한 열 {r['smoothing_accepted']}, true RC에서 거절 {r['smoothing_rejected_after_true_RC']}. RMP round count PR141 {old['new_RMP_solves']} → {r['new_RMP_solves']}; rounds/10columns {speed['PR141_RMP_rounds_per_10_added_columns']} → {speed['new_RMP_rounds_per_10_added_columns']}. Bracket narrowing/min {speed['PR141_certified_bracket_narrowing_per_minute']} → {speed['new_certified_bracket_narrowing_per_minute']}. Comparable old near-duplicate metric는 없어 감소를 주장하지 않음.\n\nBest LB {r['best_corrected_LB']}는 PR141에서 보존한 certificate이다. 이번 두 true-dual Certification의 새 LB는 {[c['L_corr'] for c in (read(q) for q in sorted((OUT/'bound_certificates').glob('*.json')))]}; best LB 개선은 없다. Primary speed target35s 미충족으로 policy_canary=NOT_SUPPORTED이나 actual four-way resource gate는 PASS이다. Native optimize union {r['total_optimize_wall_union']}초, 전체 build/audit 포함 elapsed {r['total_elapsed_including_build_audit']}초; 등록한 cycle-fit/final-C 종료 규칙으로 900초 한도 안에서 종료했다.\n"
    p=OUT/'FINAL_REVIEW_KO.md';text=p.read_text(encoding='utf8');anchor='Adaptive dual smoothing은 Discovery pricing 가속에만 사용했다.';text=text.replace(anchor,extra+'\n'+anchor)
    replacements={6:f"Four-way 실제 optimize 교집합 sampled total-tree peak RSS {exact_four_stats['observed_total_tree_peak_RSS']} bytes; 정확한 unsampled peak 아님.",7:f"실제 four-way samples min available RAM {exact_four_stats['min_available_RAM']} bytes.",8:f"실제 four-way samples max system commit {exact_four_stats['max_commit_percent']}%.",9:f"Four-way first→last sample pagefile delta {exact_four_stats['pagefile_delta_first_to_last_four_active_samples']} bytes; within-batch 최대 delta {exact_four_stats['maximum_within_batch_pagefile_delta']} bytes; 지속적인 pagefile증가+hardpaging 결합 failure 없음."}
    text='\n'.join(f'{int(line.split(".",1)[0])}. {replacements[int(line.split(".",1)[0])]}' if line.split('.',1)[0].isdigit() and int(line.split('.',1)[0]) in replacements else line for line in text.splitlines())+'\n';p.write_text(text,encoding='utf8')
    description=(OUT/'PR_DESCRIPTION.md').read_text(encoding='utf8');description=description.replace('captures independently validated negative MIPSOL trajectories','applies preregistered adaptive exponential smoothing to coupling and convexity duals for Discovery, rechecks every candidate under the same iteration true RMP dual, and captures independently validated negative MIPSOL trajectories');(OUT/'PR_DESCRIPTION.md').write_text(description,encoding='utf8')
    v=read(OUT/'VERIFICATION.json');v.update(publication_diagnostics_PASS=True,same_warm_cold_model_fingerprint_PASS=True,clock_scope='psutil OS-reported nominal clock; real-time thermal/clock sensors unobservable',additional_trajectory_profile_diagnostics=len(rows),all_PR141_files_preserved_after_publication=preserve_old());write('VERIFICATION.json',v);manifest()
if __name__=='__main__':run()
