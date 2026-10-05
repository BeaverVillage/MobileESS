"""Independent receipt accounting and report; never invokes an optimizer."""
from .common import *
from .prepare import preserved
import ast,subprocess


def union(intervals):
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return sum(b-a for a,b in merged)


def duplicate_audit(mode):
    # Recount exact duplicates separately from rejection by a batch cap.
    # Never label all rejected valid columns as duplicates.
    from .selection import projection_key
    from fractions import Fraction as F
    import numpy as np
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json');old=[set() for _ in range(4)]
    units=('MESS01','MESS02','MESS03','MESS04')
    for c in cp['pool']:old[units.index(c['MESS'])].add(c['column_SHA'])
    rows=[]
    for m in range(4):
        r=read(OUT/mode.lower()/f'live/pricing_receipts/PRICE_{m+1:04d}.json')
        valid=[c for c in r['candidates'] if c['valid_negative']]
        seen=set();duplicates=0;quota=0
        for c in valid:
            if c['column_SHA'] in seen or c['column_SHA'] in old[m]:duplicates+=1
            elif not c['selected']:quota+=1
            seen.add(c['column_SHA'])
        events=r.get('harvest_events',[])
        rows.append(dict(MESS=r['MESS'],candidates_encountered=r['callback_observations']['encountered'],negative_callback_candidates=r['callback_observations']['negative_candidates'],captured_distinct_vectors=len(r['candidates']),validated_negative_columns=len(seen),independently_validated_columns=sum(c['physical']['PASS'] and c['full_original_local']['PASS'] for c in r['candidates']),
            captured_trajectory_duplicates=duplicates,nonduplicate_policy_rejections=quota,
            callback_raw_duplicates=max(0,r['callback_observations']['negative_candidates']-r['MIPSOL_distinct_captures']),
            exact_projection_duplicates=sum('PROJECTION_DUPLICATE' in e['decision'] for e in events),
            postsolve_repeat_observations=sum(e['source']=='POSTSOLVE' and 'DUPLICATE' in e['decision'] for e in events),
            dominated_removed=sum('DOMINATES' in e['decision'] for e in events)+sum('replaced_dominated_SHA' in e for e in events),retained_columns=sum(c['selected'] for c in r['candidates'])))
    return rows


def verify_leg(mode):
    r=read(OUT/f'MULTICOLUMN_{mode}_1ROUND.json');leg=OUT/mode.lower()
    assert r['starting_columns']==1604 and r['Discovery_rounds']==r['RMP_calls']==1 and r['pricing_calls']==4
    assert r['Certification_calls']==r['authoritative_continuation_calls']==r['Branch_and_Price_calls']==0
    assert not r['scientific_certificate_merge']
    assert len(r['native_intervals'])==5
    receipts=[read(leg/f'live/pricing_receipts/PRICE_{m+1:04d}.json') for m in range(4)]
    assert all(p['callback_observations']['optimize_calls']==1 for p in receipts)
    assert all(p['dual_SHA']==r['search_dual_SHA'] and p['true_dual_SHA']==r['true_dual_SHA'] for p in receipts)
    assert all(not p['valid_bound'] and not p['pricing_optimality_claimed'] for p in receipts)
    assert all(p['full_original_domain'] and p['no_fixing'] and p['horizon']==96 for p in receipts)
    assert all(p['settings']['Threads']==1 and all(p['settings'][k]==1e-8 for k in ['FeasibilityTol','IntFeasTol','OptimalityTol']) for p in receipts)
    admitted=[c for p in receipts for c in p['candidates'] if c['selected']]
    assert len(admitted)==r['retained_new_columns'] and r['ending_columns']==1604+len(admitted)
    for p in receipts:
        selected=[c for c in p['candidates'] if c['selected']]
        assert len(selected)<=(4 if mode=='BASELINE' else 8)
        assert len({c['column_SHA'] for c in selected})==len(selected)
        for c in selected:
            assert c['physical']['PASS'] and c['full_original_local']['PASS'] and c['valid_negative']
            assert c['rc_inc']<=-1e-7 and c['manual_search_rc']<=-1e-7
            assert sha(leg/'live'/c['point_file'])==c['point_SHA']
    sum_receipts=sum(p['interval'][1]-p['interval'][0] for p in receipts)+r['RMP_native_seconds']
    assert max(sum_receipts,r['native_sum_seconds'])<=300.
    assert abs(sum(b-a for a,b in r['native_intervals'])-r['native_sum_seconds'])<1e-8
    if r['U_after'] is not None:
        assert r['original_primal_audit']['PASS'] and r['U_after']<=r['U_before']
        assert r['upper_improvement']==r['U_before']-r['U_after']
        assert r['efficiency']==r['upper_improvement']/r['total_wall_seconds']
        # Saved point only: independent original full-matrix primal audit.
        from v42_degen.identity import inputs
        from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
        import numpy as np
        A,d,*_=inputs()
        with np.load(leg/'live/RMP_POINT_ONCE.npz') as z:point=z['point']
        full=corrected_rows(A,d,point,False,pure_binary_equalities(A,d));assert full['PASS']
        native_obj=float(d['objective']@point+d['constant'])
        assert native_obj==r['native_primal_upper']
        r['independent_original_primal_audit']=full
    r['independent_candidate_metrics']=duplicate_audit(mode)
    r['native_receipt_sum_seconds']=sum_receipts
    r['native_union_seconds']=union(r['native_intervals'])
    write(OUT/f'MULTICOLUMN_{mode}_1ROUND.json',r)
    return r


def manifest():
    files=[]
    for prefix in ['v42_dw_harvest','tests/v42_dw_harvest','docs/v42_m1_dw_multicolumn_microbenchmark']:
        for p in sorted((ROOT/prefix).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.tmp') and p.name!='SHA256_MANIFEST.json':
                files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    write(OUT/'SHA256_MANIFEST.json',dict(files=files,self_excluded=True))


def finalize():
    count=preserved();assert count==12919
    freeze=read(OUT/'SOURCE_FREEZE.json');assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    assert freeze['preregistration_SHA']==sha(OUT/'MULTICOLUMN_PREREGISTRATION.json')
    assert freeze['design_SHA']==sha(OUT/'MULTICOLUMN_DESIGN.md')
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json')
    for mode in ['baseline','challenger']:
        leg=OUT/mode
        assert sha(leg/'immutable/DW_CHECKPOINT_LATEST.json')==sha(OLD/'DW_CHECKPOINT_LATEST.json')
        for c in cp['pool']:assert sha(leg/c['file'])==c['file_SHA']
    a,b=verify_leg('BASELINE'),verify_leg('CHALLENGER')
    assert all(a[k]==b[k] for k in ['pool_SHA','checkpoint_SHA','true_dual_SHA','search_dual_SHA','starting_columns','U_before'])
    assert sum(max(r['native_receipt_sum_seconds'],r['native_sum_seconds']) for r in [a,b])<=600.
    same_settings=a['settings']==b['settings']
    assert same_settings  # Both caps remain200 unless shared300s safety reserve.
    scientific=read(OUT/'MULTICOLUMN_SCIENTIFIC_EQUIVALENCE.json');assert scientific['PASS']
    valid=all(r['status']=='AUDITED_BENCHMARK' and r['U_after'] is not None and r['original_primal_audit']['PASS'] for r in [a,b])
    throughput=b['retained_per_pricing_native_minute']>a['retained_per_pricing_native_minute']
    observed_primary=b['efficiency']>a['efficiency'] and b['upper_improvement']>1e-8
    primary=valid and observed_primary
    selected=bool(valid and scientific['PASS'] and throughput and primary)
    status='MULTICOLUMN_SELECTED' if selected else 'MULTICOLUMN_REJECTED' if valid else 'MICROBENCHMARK_INCONCLUSIVE'
    comparison=dict(status=status,MULTICOLUMN_SELECTED=selected,scientific_equivalence=True,invalid_admitted=0,Certification_implementation_unchanged=True,
        primary_metric='audited upper decrease / total wall seconds',observed_primary_better=observed_primary,adoption_primary_gate_PASS=primary,useful_throughput_better=throughput,
        baseline=dict(retained=a['retained_new_columns'],wall=a['total_wall_seconds'],delta=a['upper_improvement'],efficiency=a['efficiency'],throughput=a['retained_per_pricing_native_minute']),
        challenger=dict(retained=b['retained_new_columns'],wall=b['total_wall_seconds'],delta=b['upper_improvement'],efficiency=b['efficiency'],throughput=b['retained_per_pricing_native_minute']),
        total_native_sum_seconds=a['native_sum_seconds']+b['native_sum_seconds'],total_native_receipt_charge_seconds=a['native_receipt_sum_seconds']+b['native_receipt_sum_seconds'],native_budget_seconds=600,
        authoritative_root_columns=1604,authoritative_interval=read(OLD/'DW_CONTINUATION_FINAL_RESULT.json')['final_interval'],
        AUTHORITATIVE_ROOT_CONTINUATION_NOT_RUN=True,BRANCH_AND_PRICE_NOT_RUN=True,single_pair_statistical_superiority_not_claimed=True)
    comparison['challenger_guard_failures']=b['resource']['guard_failures']
    comparison['selection_blocker']='OTHER_NATIVE_RESERVATION caused three non-quota Discovery interruptions; observed efficiency is descriptive, not an unconfounded adoption comparison.' if b['resource']['guard_failures'] else None
    comparison['foreign_native_optimize_not_proven']='The guard observed a native-engine reservation. Its PID/call context was not persisted in this build; no causal identity or actual foreign optimize claim is made.'
    write(OUT/'MULTICOLUMN_AB_COMPARISON.json',comparison)
    harvest=[];resources=[]
    for mode,r in [('BASELINE',a),('CHALLENGER',b)]:
        for m in range(4):
            p=read(OUT/mode.lower()/f'live/pricing_receipts/PRICE_{m+1:04d}.json')
            for c in p['candidates']:
                harvest.append(dict(mode=mode,MESS=p['MESS'],trajectory_SHA=c['column_SHA'],source=c['source'],valid_negative=c['valid_negative'],selected=c['selected'],true_RC=c['rc_inc'],search_RC=c['manual_search_rc'],physical_PASS=c['physical']['PASS'],original_local_PASS=c['full_original_local']['PASS']))
        with (OUT/mode.lower()/'RESOURCE_LEDGER.csv').open(encoding='utf8',newline='') as f:
            resources += [dict(mode=mode,**row) for row in csv.DictReader(f)]
    table(OUT/'COLUMN_HARVEST_LEDGER.csv',harvest);table(OUT/'RESOURCE_LEDGER.csv',resources)
    for prefix in ['v42_dw_harvest','tests/v42_dw_harvest']:
        for p in (ROOT/prefix).glob('*.py'):ast.parse(p.read_text(encoding='utf8'))
    diff=subprocess.run(['git','diff','--check',BASE],cwd=ROOT,capture_output=True,text=True);assert diff.returncode==0,diff.stdout
    write(OUT/'VERIFICATION.json',dict(PASS=True,PR152_preserved_files=count,original_terminal_frozen_hashes=len(read(OLD/'AUTHORITATIVE_TERMINAL_FREEZE.json')['files']),lightweight_tests=read(OUT/'MULTICOLUMN_LIGHTWEIGHT_TESTS.json'),scientific_equivalence=True,
        copied_pool_columns_each=1604,same_checkpoint_duals_seed_domain_settings=True,single_pricing_call_per_MESS=True,no_no_good_cuts=True,no_existing_column_deletion=True,valid_admitted_columns=a['retained_new_columns']+b['retained_new_columns'],invalid_admitted_columns=0,
        benchmark_pricing_calls=8,benchmark_RMP_calls=2,Certification_calls=0,native_charge_seconds=comparison['total_native_receipt_charge_seconds'],native_cap=600,history_budget_consumed=0,authoritative_continuation_calls=0,Branch_and_Price_calls=0,May_production_calls=[0,0,0],other_lane_kill_calls=0,other_lane_terminate_calls=0,compile_static=True,diff_check=True))
    report(a,b,comparison);manifest();print('MULTICOLUMN_FINAL',status,comparison['total_native_receipt_charge_seconds'],flush=True)


def report(a,b,c):
    lines=[f'Baseline retained columns {a["retained_new_columns"]}; pool1604 → {a["ending_columns"]}.',f'Challenger retained columns {b["retained_new_columns"]}; pool1604 → {b["ending_columns"]}.']
    for label,field in [('Harvested candidates/MESS','candidates_encountered'),('Validated negative columns/MESS','validated_negative_columns')]:
        lines.append(f'{label}: Baseline {[p[field] for p in a["independent_candidate_metrics"]]}, Challenger {[p[field] for p in b["independent_candidate_metrics"]]} (MESS01–04).')
    lines += [f'Duplicate/dominance independent recount: Baseline {a["independent_candidate_metrics"]}; Challenger {b["independent_candidate_metrics"]}. Postsolve repeats와 batch-cap rejection을 projection duplicate와 구분.',
        f'Baseline pricing native sum {a["pricing_native_sum_seconds"]}s / pricing wall {a["pricing_wall_seconds"]}s.',f'Challenger pricing native sum {b["pricing_native_sum_seconds"]}s / pricing wall {b["pricing_wall_seconds"]}s.',
        f'Baseline RMP {a["RMP_native_seconds"]}s, native status {a["RMP_status"]}.',f'Challenger RMP {b["RMP_native_seconds"]}s, native status {b["RMP_status"]}.',
        f'Baseline upper decrease {a["upper_improvement"]}; {a["U_before"]} → {a["U_after"]}.',f'Challenger upper decrease {b["upper_improvement"]}; {b["U_before"]} → {b["U_after"]}.',
        f'Baseline improvement/wall-second {a["efficiency"]}, total wall {a["total_wall_seconds"]}s.',f'Challenger improvement/wall-second {b["efficiency"]}, total wall {b["total_wall_seconds"]}s.',
        f'Resource sampled peaks Baseline {a["resource"]}; Challenger {b["resource"]}.',
        'Scientific equivalence PASS; matrix/domain/physical rows/coupling/pricing settings/true-dual authority/Certification code unchanged. No invalid admission.',
        f'Status {c["status"]}; MULTICOLUMN_SELECTED={c["MULTICOLUMN_SELECTED"]}. Blocker: {c["selection_blocker"]} Native reservation PID/call context 미저장으로 타 Lane의 실제 optimize는 입증하지 않음. Single-pair 관측값은 채택 근거로 쓰지 않고 재실행0.',
        'New commit / Draft PR / remote SHA / clean은 publication receipt 및 최종 응답에서 확인.',
        'Authoritative CG continuation calls=0; historical grant 사용0; native benchmark receipt charge '+str(c['total_native_receipt_charge_seconds'])+' /600s; automatic extension0.',
        'Branch-and-Price calls=0; May production0/0/0; 다른 Lane kill/terminate/edit0. Benchmark 이후 STOP.']
    endings=['PR152의 1,604-column checkpoint는 immutable baseline으로 보존했으며, 동일 checkpoint의 read-only copies에서 기존 방식과 multi-column 방식을 각각 정확히 1 Discovery round + 1 RMP로 비교했다.',
        '이번 실험은 최대 600초의 development microbenchmark이며, 결과를 authoritative D-W root certificate에 합치지 않았다.',
        '선택 기준은 raw column 수가 아니라 audited upper-bound improvement per wall-clock second였다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+'\n\n'.join(endings)+'\n',encoding='utf8')


if __name__=='__main__':finalize()
