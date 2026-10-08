"""Saved child evidence only. No native optimization and no scientific edits."""
from .common import *
from .domain import child_data
from v42_b2_root_validation.certificate import verify_certificate
from v42_b2_root_validation.analysis import point_summary
from v42_physics_redesign.exact_cut import certify,construct
from .repair import repair_multiplier
from fractions import Fraction
from collections import Counter
import re

def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    prior.forbid_optimize();began=time.perf_counter()
    controller=read(REPORTS/'CONTROLLER_RESULT.json')
    contfile=REPORTS/'Z0_CONTINUATION_CONTROLLER_RESULT.json'
    continuation=read(contfile) if contfile.exists() else None
    phasefile=REPORTS/'PHASE_B_CONTROLLER_RESULT.json';phase=read(phasefile) if phasefile.exists() else None
    ledger=phase['budget'] if phase else continuation['budget'] if continuation else controller['budget']
    assert ledger['native_calls']==len(list((WORK/'children').glob('*/z*/NATIVE_CALL_STARTED.json')))
    assert not ledger['unknown_unresolved_native_charge']
    freeze=read(REPORTS/'EXECUTION_SOURCE_FREEZE.json')
    assert all(sha(ROOT/'v42_group_branching'/n)==h for n,h in freeze['modules'].items())
    assert sha(REPORTS/'SELECTED_BRANCH_VARIABLES.json')==freeze['selection_SHA256']
    assert sha(REPORTS/'PARALLEL_EXECUTION_PREREGISTRATION_KO.md')==freeze['preregistration_SHA256']
    source=read(REPORTS/'SOURCE_IDENTITY.json');assert source['PASS']
    for directory in (SOURCE187,SOURCE185):
        manifest=read(directory/'SHA256_MANIFEST.json')
        assert all(sha(directory/n)==v['sha256'] for n,v in manifest['files'].items())
        assert all(sha(ROOT/n)==v['sha256'] for n,v in manifest['source_modules'].items())
    A,d,T,AA,full=model_inputs();reader=hc.physical_reader()
    with np.load(SOURCE187/'B2_ROOT_RAW.npz') as f:baseline=f['x'].copy()
    baseline_summary=point_summary(A,d,baseline,reader)
    families=np.array([str(n).split('[')[0] for n in d['names']])
    grid=csv_rows(REPORTS/'CRITICAL_GRID_ROWS.csv');grididx=np.array([int(r['row']) for r in grid])
    selected=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected']
    bylabel={f'C{k:02d}':r for k,r in enumerate(selected,1)}
    children=[];certs={0:[],1:[]};fractions=[];phys=[];numerical=[];benchmark=[];independent=[];coverage=[]
    for label,candidate in bylabel.items():
        for value in (0,1):
            folder=WORK/'children'/label/f'z{value}'
            if continuation and label=='C01' and value==0:folder=WORK/'children/C01_CONTINUATION/z0'
            file=folder/'RESULT.json'
            if not file.exists():
                children.append(dict(candidate=label,value=value,variable=candidate['variable_name'],Status='NOT_RUN',certificate_PASS=False))
                certs[value].append(dict(candidate=label,PASS=False,status='NOT_RUN'));continue
            result=read(file);child=child_data(full,candidate['column'],value)
            identity=read(folder/'MODEL_IDENTITY.json');assert identity['PASS']
            assert identity['one_binary_bound_fix'] and identity['all_other_bounds_bit_identity']
            assert identity['objective_identity']['PASS'] and identity['all_native_types_C']
            coverage.append(dict(candidate=label,value=value,PASS=True,selected_column=candidate['column'],native_identity_SHA256=sha(folder/'MODEL_IDENTITY.json')))
            certfile=folder/'EXACT_CERTIFICATE.json';proof=read(certfile) if certfile.exists() else None
            check=None;diagnostic=False
            if result.get('certificate_PASS') and result.get('Status')==2:
                check=verify_certificate(AA,child,proof['accepted'])
                assert check['PASS'] and check['certified_LB']==result['exact_LB']
                assert check['exact_alpha']==proof['independent']['exact_alpha']
                independent.append(dict(candidate=label,value=value,**check,scope='Child LP only; full global bound requires certified sibling minimum'))
            elif result.get('Status')==9:
                # Preserve the worker's incomplete status. A saved mathematical
                # weak-duality diagnostic is never admitted to the pair/global LB.
                with np.load(folder/'RAW.npz') as f:pi=f['pi'].copy() if 'pi' in f.files else None
                if pi is not None:
                    base=certify(AA,child,np.array([],dtype=int),pi,folder/'TIMELIMIT_DIAGNOSTIC_BASE','optimality')
                    accepted=base['accepted'];basecheck=verify_certificate(AA,child,accepted)
                    with np.load(accepted['npz_path']) as f:projected=f['pi'].copy();residual=f['stationarity'].copy()
                    repaired,repairrows,target=repair_multiplier(AA,child,projected,residual)
                    save(folder/'TIMELIMIT_DIAGNOSTIC_REPAIRED_MULTIPLIER.npz',pi=repaired,raw_pi=pi,sign_cone_pi=projected)
                    table(folder/'TIMELIMIT_DIAGNOSTIC_REPAIR_ROWS.csv',repairrows)
                    fixed=construct(AA,child,np.array([],dtype=int),repaired,folder/'TIMELIMIT_DIAGNOSTIC_REPAIRED')
                    fixedcheck=verify_certificate(AA,child,fixed)
                    accepted,check=max([(accepted,basecheck),(fixed,fixedcheck)],key=lambda v:Fraction(v[0]['exact_alpha']))
                    proof=dict(PASS=True,diagnostic_only=True,eligible_for_pair=False,native_status=9,base=base,
                        accepted=accepted,independent=check,equality_repaired=fixed,equality_repaired_independent=fixedcheck,
                        selected_proof='EQUALITY_REPAIRED' if accepted is fixed else 'BASE',native_calls=0)
                    write(folder/'TIMELIMIT_DIAGNOSTIC_EXACT_CERTIFICATE.json',proof);diagnostic=True
                    independent.append(dict(candidate=label,value=value,**check,eligible_for_pair=False,
                        scope='Diagnostic mathematical Child LB; incomplete native child is excluded by user gate'))
            certs[value].append(dict(candidate=label,PASS=bool(check),scope='Original integer domain intersected with the one fixed binary',
                native_status=result.get('Status'),native_objective=result.get('ObjVal'),exact_LB=check['certified_LB'] if check else None,
                certificate_loss=result['ObjVal']-check['certified_LB'] if check else None,quality_loss_1e4_is_diagnostic_only=True,
                eligible_for_pair=not diagnostic and bool(check),diagnostic_only=diagnostic,
                original_worker_certificate=proof,postrun_independent_check=check))
            resources=read(folder/'RESOURCE_OBSERVATION.json')
            log=(folder/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
            presolve=re.search(r'Presolve time:\s+([\d.]+)s',log)
            warnings=[line for line in log.splitlines() if re.search(r'warning|numerical|scal|Markowitz',line,re.I)]
            row=dict(candidate=label,value=value,variable=candidate['variable_name'],Status=result.get('Status'),
                native_objective=result.get('ObjVal'),exact_LB=result.get('exact_LB'),certificate_loss=result.get('certificate_loss'),
                certificate_PASS=result.get('certificate_PASS'),strict_original_replay_PASS=result.get('original_C3A_primal_replay',{}).get('PASS'),
                Runtime=result.get('Runtime'),Work=result.get('Work'),BarIterCount=result.get('BarIterCount'),
                loading_seconds=result.get('data_loading_seconds'),model_build_guard_seconds=result.get('model_build_and_guard_seconds'),
                worker_wait_seconds=result.get('worker_wait_seconds'),certificate_seconds=result.get('exact_certificate_seconds'),
                worker_wall_seconds=result.get('worker_total_wall_seconds'),peak_RSS=resources['peak_RSS_observed'],CPU_seconds=resources['CPU_seconds_observed'],
                presolve_seconds=float(presolve[1]) if presolve else None,crossover_seconds=0.,Threads=1,
                memory_bandwidth='NOT_MEASURED',native_calls=result['native_calls'])
            row['execution_id']=result['candidate'];row['actual_TimeLimit']=identity['parameters']['TimeLimit']
            if diagnostic:row.update(exact_LB=check['certified_LB'],certificate_loss=result['ObjVal']-check['certified_LB'],
                mathematical_certificate_PASS=True,certificate_scope='DIAGNOSTIC_ONLY_TIME_LIMIT; NOT_PAIR_ELIGIBLE')
            children.append(row);benchmark.append(row)
            rawfile=folder/'RAW.npz'
            if not rawfile.exists():continue
            with np.load(rawfile) as f:raw={n:f[n].copy() for n in f.files}
            if 'x' not in raw:continue
            x=raw['x'];summary=point_summary(A,d,x,reader)
            row['strict_original_replay_PASS']=summary['original_relaxed_row_replay']['PASS']
            changes=[]
            for kind in sorted(set(families)):
                idx=np.flatnonzero(families==kind);delta=x[idx]-baseline[idx]
                changes.append(dict(family=kind,columns_changed_above_1e8=int((abs(delta)>1e-8).sum()),L1_change=float(abs(delta).sum()),maximum_change=float(abs(delta).max(initial=0))))
            fractions.append(dict(candidate=label,value=value,summary=summary,changes_from_B2_ROOT=changes,
                selected_binary_value=float(x[candidate['column']]),LP_vector_never_updates_UB=True))
            nodeidx=np.flatnonzero((families=='node_activity')&np.array([candidate['MESS'] in str(n) for n in d['names']]))
            order=sorted(nodeidx,key=lambda j:-abs(x[j]-baseline[j]))[:20]
            changed_locations=[dict(column=int(j),variable=str(d['names'][j]),B2=float(baseline[j]),child=float(x[j]),difference=float(x[j]-baseline[j])) for j in order]
            residual=A@x-d['rhs'];oldres=A@baseline-d['rhs'];critical=[]
            for i,desc in zip(grididx,grid):
                coefficient=abs(float(desc['rho_coefficient']))
                critical.append(dict(row=int(i),family=desc['family'],slot=int(desc['slot']),branch=desc['branch_name'],
                    B2_normalized_slack=float(-oldres[i]/coefficient),child_normalized_slack=float(-residual[i]/coefficient),
                    raw_Pi=float(raw['pi'][i]) if 'pi' in raw else None,raw_Pi_is_not_certified_shadow_price=True))
            selected_unit=next(p for p in summary['physical_trajectories'] if p['MESS']==candidate['MESS'])
            phys.append(dict(candidate=label,value=value,MESS=candidate['MESS'],slot=candidate['slot'],site=candidate['site'],
                interpretation=candidate['mode_interpretation'],selected_unit=selected_unit,changed_node_activity_top20=changed_locations,
                critical_grid_rows=critical,strict_FULL_relaxed_replay=summary['original_FULL_relaxed_row_replay'],
                values_are_fractional_LP_diagnostics=True,physical_feasible_operation_claim=False))
            diag=dict(candidate=label,value=value,warnings=warnings,attributes={n:result.get(n) for n in ('ConstrVio','BoundVio','DualVio','ComplVio','Kappa','KappaExact')},
                unavailable_attributes=result.get('missing_attributes'),scientific_tolerances_unchanged=True)
            if check:
                with np.load(proof['accepted']['npz_path']) as f:pi=f['pi'].copy();r=f['stationarity'].copy()
                endpoint=np.where(r>=0,child['lower'],child['upper']);loss=r*(x-endpoint)
                lossrows=[dict(family=k,finite_bound_loss=float(loss[families==k].sum()),max_stationarity=float(abs(r[families==k]).max())) for k in sorted(set(families))]
                lossrows.sort(key=lambda v:-v['finite_bound_loss']);bad=((child['sense']=='<')&(raw['pi']>0))|((child['sense']=='>')&(raw['pi']<0))
                diag.update(accepted_proof=proof['selected_proof'],finite_bound_loss_by_family=lossrows,
                    finite_bound_loss_sum=float(loss.sum()),row_residual_term=float(pi@(AA@x-child['rhs'])),raw_wrong_sign_count=int(bad.sum()),
                    decomposition_is_float_diagnostic_not_exact_proof=True,certificate_loss=row['certificate_loss'],diagnostic_only=diagnostic)
            numerical.append(diag)
    pairs=[];best=LB;best_label=None
    for label in bylabel:
        saved=REPORTS/f'{label}_PAIR_RESULT.json'
        if not saved.exists():pairs.append(dict(candidate=label,variable=bylabel[label]['variable_name'],status='NOT_RUN',LB_pair=None,valid_global_LB=LB,Delta_LB=0));continue
        pair=read(saved)
        local=[r for r in independent if r['candidate']==label and r.get('eligible_for_pair',True)]
        if continuation and label=='C01':
            valid=len(local)==2
            pairlb=min(r['certified_LB'] for r in local) if valid else None
            pair=dict(pair,pair_certificate_PASS=valid,LB_pair=pairlb,
                valid_global_LB=max(LB,pairlb) if valid else LB,Delta_LB=max(0.,pairlb-LB) if valid else 0.,
                latest_child0_path='children/C01_CONTINUATION/z0',reused_child1_path='children/C01/z1',
                sibling_reused_without_rerun=True,continuation_wall_seconds=continuation['wall_seconds'],
                final_pair_was_not_run_simultaneously=True,original_parallel_performance_preserved=True)
            new0=read(WORK/'children/C01_CONTINUATION/z0/RESULT.json');old1=read(WORK/'children/C01/z1/RESULT.json')
            pair.update(initial_parallel_Native_Runtime_sum=pair['Native_Runtime_sum'],initial_parallel_Work_sum=pair['Work_sum'],
                Native_Runtime_sum=new0['Runtime']+old1['Runtime'],Work_sum=new0['Work']+old1['Work'],
                C01_all_spent_Native_Runtime_sum=continuation['budget']['Native_Runtime_sum'],
                C01_all_spent_Work_sum=continuation['budget']['Native_Work_sum'])
            write(REPORTS/'C01_CONTINUED_PAIR_RESULT.json',pair)
        valid=pair['pair_certificate_PASS']
        if valid:
            assert len(local)==2
            exact=min(Fraction(r['exact_alpha']) for r in local)
            pairlb=float(exact)
            if Fraction.from_float(pairlb)>exact:pairlb=float(np.nextafter(pairlb,-np.inf))
            assert pairlb==pair['LB_pair']
            if pairlb>best:best=pairlb;best_label=label
        pairs.append(dict(candidate=label,variable=pair['variable'],status='CERTIFIED' if valid else 'UNRESOLVED',
            LB_pair=pair['LB_pair'],valid_global_LB=pair['valid_global_LB'],Delta_LB=pair['Delta_LB'],
            parallel_wall_seconds=pair['parallel_wall_seconds'],Native_Runtime_sum=pair['Native_Runtime_sum'],Work_sum=pair['Work_sum'],
            native_span_seconds=pair['native_span_seconds'],native_overlap_seconds=pair['native_overlap_seconds'],
            native_sum_over_native_span=pair['native_sum_over_native_span'],speedup=None,sequential_baseline='NO_SAME_LIMIT_COMPLETE_BASELINE',
            continuation_wall_seconds=pair.get('continuation_wall_seconds'),
            initial_parallel_Native_Runtime_sum=pair.get('initial_parallel_Native_Runtime_sum'),
            performance_note='Native sums refer to latest proof children; overlap and parallel wall refer to original concurrently executed children' if label=='C01' and continuation else 'Actual paired concurrent run'))
    budget_PASS=ledger['native_calls']<=6 and ledger['Native_Runtime_sum']<=2880
    assert budget_PASS
    validpairs=[p for p in pairs if p['status']=='CERTIFIED'];failed=[p for p in pairs if p['status']=='UNRESOLVED']
    if failed:
        classification='GROUP_BRANCHING_TIME_LIMIT' if any(r.get('Status') in (9,11) for r in children) else 'GROUP_BRANCHING_DUAL_CERT_FAIL'
    elif not ledger['native_calls']:classification='GROUP_BRANCHING_RESOURCE_PENDING'
    elif best-LB>=.001:classification='GROUP_BRANCHING_MATERIAL_LB_GAIN'
    else:classification='GROUP_BRANCHING_NONMATERIAL'
    material=bool(best-LB>=.001 and validpairs and budget_PASS)
    next_action=('인증된 최선 scalar pivot만 BranchPriority에 적용하는 full-domain canary 한 회를 별도 사전등록한다.' if material else
        '저장된 Child의 Q·PCS 등식 stationarity와 finite-bound 손실을 함께 상쇄할 수 있는 exact multiplier repair를 optimize=0으로 한 건 검증한다.')
    decision=dict(classification=classification,source_HEAD=BASE187,native_optimize_calls=ledger['native_calls'],
        Native_Runtime_sum=ledger['Native_Runtime_sum'],Work_sum=ledger['Native_Work_sum'],
        controller_wall_seconds=controller['controller_experiment_wall_seconds']+(continuation['wall_seconds'] if continuation else 0)+(phase['wall_seconds'] if phase else 0),
        initial_parallel_wall_seconds=controller['pairs'][0].get('parallel_wall_seconds'),
        additional_z0_wall_seconds=continuation['wall_seconds'] if continuation else None,
        authorized_z0_continuation_calls=1 if continuation else 0,
        phase_B_calls=2 if phase else 0,C03_not_run_reason='PAIR_WOULD_EXCEED_6_CALLS' if phase else None,
        old_global_LB=LB,new_valid_global_LB=best,Delta_LB=best-LB,old_UB=UB,new_UB=UB,
        old_global_gap_percent=100*(UB-LB)/UB,new_global_gap_percent=100*(UB-best)/UB,target_LB=UB*.995,
        best_certified_candidate=best_label,budget_PASS=budget_PASS,Material_Gate_PASS=material,
        branch_domain_complete_PASS=True,scientific_objective_identity_PASS=True,independent_exact_checks=len(independent),
        quality_loss_1e4_execution_gate_removed=True,original_quality_audit_preserved=True,
        native_objectives_are_diagnostics_only=True,M1_ACCEPTED=bool(100*(UB-best)/UB<=.5),
        BranchPriority_integration_authorized=material,production_calls=0,P2_calls=0,downstream_calls=0,
        new_integer_incumbents=0,max_workers_used=2,speedup=None,memory_bandwidth='NOT_MEASURED',
        next_action=next_action,next_action_count=1,next_action_executed=False,postprocessing_seconds=time.perf_counter()-began)
    table(REPORTS/'CHILD_LP_RESULTS.csv',children)
    table(REPORTS/'GROUP_GLOBAL_LB_COMPARISON.csv',pairs)
    initial0=[]
    if continuation:
        original=read(WORK/'children/C01/z0/RESULT.json')
        initial0=[dict(candidate='C01_INITIAL_480',value=0,Runtime=original['Runtime'],Work=original['Work'],Status=original['Status'],actual_TimeLimit=480)]
        older=csv_rows(WORK/'children/C01/z0/BARRIER_TRAJECTORY.csv');newer=csv_rows(WORK/'children/C01_CONTINUATION/z0/BARRIER_TRAJECTORY.csv')
        oldby={int(float(r['iteration'])):r for r in older};newby={int(float(r['iteration'])):r for r in newer}
        common=sorted(set(oldby)&set(newby));prefix=[]
        for it in common:
            a,b=oldby[it],newby[it]
            prefix.append(dict(iteration=it,initial_parallel_wall=float(a['wall']),fresh_single_worker_wall=float(b['wall']),
                raw_primal_difference=float(b['primal'])-float(a['primal']),raw_dual_difference=float(b['dual'])-float(a['dual']),
                elapsed_ratio=float(a['wall'])/float(b['wall']) if float(b['wall']) else None))
        table(REPORTS/'Z0_MATCHED_BARRIER_PREFIX.csv',prefix)
        write(REPORTS/'Z0_PARTIAL_PERFORMANCE_COMPARISON.json',dict(common_barrier_iterations=len(common),
            last_common_prefix=prefix[-1] if prefix else None,causal_speedup=None,
            caveats=['Different TimeLimit and termination status','Shared host with other native task','Prefix timing only, not a complete same-limit serial/parallel comparison'],native_calls=0))
    latestfile=phasefile if phase else contfile if continuation else REPORTS/'CONTROLLER_RESULT.json'
    decision['observed_experiment_elapsed_wall_seconds']=latestfile.stat().st_mtime-(WORK/'checkpoints/C01_LAUNCH_ONCE.json').stat().st_mtime
    decision['elapsed_wall_includes_user_steering_code_and_analysis_gaps']=True
    table(REPORTS/'RUNTIME_WORK_BENCHMARK.csv',[dict(candidate='PR187_HISTORICAL_ROOT',Runtime=210.226,Work=387.443,comparison='Historical diagnostic; no speedup claim'),*initial0,*benchmark])
    originalpair=controller['pairs'][0]
    write(REPORTS/'PARALLEL_LICENSE_AUDIT.json',dict(PASS=bool(originalpair.get('native_overlap_seconds',0)>0),
        two_independent_licensed_Env_Model_hold_receipt=read(WORK/'checkpoints/C01_CONCURRENT_ENV_LICENSE_CHECK.json'),
        actual_native_overlap_seconds=originalpair.get('native_overlap_seconds'),
        solver_completion_is_separate_from_license_support=True,
        original_concurrency_flag_was_also_conditioned_on_pair_certification=originalpair.get('license_native_concurrency_demonstrated')))
    write(REPORTS/'CHILD_0_EXACT_CERTIFICATES.json',dict(certificates=certs[0],native_calls=0))
    write(REPORTS/'CHILD_1_EXACT_CERTIFICATES.json',dict(certificates=certs[1],native_calls=0))
    write(REPORTS/'FRACTIONAL_SOLUTION_COMPARISON.json',dict(baseline_B2=baseline_summary,children=fractions,UB_unchanged=True))
    write(REPORTS/'PHYSICAL_INTERPRETATION_DATA.json',dict(children=phys,original_grid_rows_unchanged=True))
    write(REPORTS/'CHILD_NUMERICAL_AUDIT.json',dict(children=numerical,no_Kappa_solve=True))
    write(REPORTS/'POSTRUN_INDEPENDENT_AUDIT.json',dict(PASS=True,checks=independent,child_domain_identity=coverage,
        preserved_PR187_PR185_manifests_PASS=True,execution_frozen_sources_PASS=True,original_domain_union_PASS=True,
        actual_call_census_PASS=True,budget_PASS=budget_PASS,raw_LP_points_do_not_update_UB=True,native_calls=0))
    write(REPORTS/'FINAL_DECISION.json',decision)
    print('GROUP_SAVED_EVIDENCE_ANALYSIS_COMPLETE',json.dumps(clean(decision)),flush=True)

if __name__=='__main__':main()
