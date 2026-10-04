"""Post-heavy independent verification and publication artifacts."""
from .common import *
import numpy as np,re
from fractions import Fraction as F
def tests(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8');r=read(OUT/('PYTEST_'+label+'_RECEIPT.json'));n=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert r['exit_code']==0 and n and r['all_Gurobi_Threads_one'] and r['calls_nonoverlapping']
    return dict(PASS=True,passed=int(n[-1][0]),seconds=float(n[-1][1]),handled_native_traces=log.count('Windows fatal exception:'),log_SHA=sha(OUT/(label+'_TEST.log')))
def verify():
    from v42_degen.identity import inputs
    from v42_dw_root.partition import axes
    from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
    from v42_dw_root.run import exact_rc
    from v42_dw_root.models import hash_column,subset
    from v42_disjunctive.certificate import rational_bound,down
    old_count=preserve_old();commit=verify_freeze();result=read(OUT/'DW_POLICY_CANARY_FINAL.json')
    assert result['total_optimize_wall_union']<=900 and result['initial_retained_columns']==1066 and not result['old_TIME_LIMIT_retroactively_added']
    intervals=read(OUT/'DW_OPTIMIZE_INTERVALS.json');assert abs(intervals.get('carried_budget_seconds',0)+union_seconds(intervals['intervals'])-result['total_optimize_wall_union'])<1e-9
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);mask=pure_binary_equalities(A,d);points={};rmps=[];rmpspans=[]
    for row in ledger('DW_RMP_LEDGER.csv'):
        r=read(OUT/row['receipt']);rmps.append(r);rmpspans.append(r['interval'])
        if r['dual_SHA']:
            assert r['status']==2 and r['settings']['Threads']==1
            with np.load(OUT/r['point_file']) as z:
                assert corrected_rows(A,d,z['point'],False,mask)['PASS'];pi=z['pi'];alpha=z['alpha']
                assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==r['dual_SHA'] and hashlib.sha256(z['point'].tobytes()).hexdigest()==r['primal_SHA']
                points[r['dual_SHA']]=(pi,alpha)
    fullowner=np.full(A.shape[0],-1,dtype=np.int8)
    for i in range(A.shape[0]):
        deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(deps)==1 and -1 not in deps:fullowner[i]=next(iter(deps))
    full={}
    for m,b in enumerate(blocks):
        rr=np.flatnonzero(fullowner==m);cc=b.columns;matrix=A[rr][:,cc];attrs=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.));full[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs))
    prices=[read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))];checked=[]
    for p in prices:
        assert p['dual_SHA'] in points and p['full_original_domain'] and p['horizon']==96 and p['objective_transport_exact'] and p['settings']['Threads']==1 and p['no_fixing']
        s=p['settings'];assert s['FeasibilityTol']==s['IntFeasTol']==s['OptimalityTol']==EPS and s['MIPGap']==s['MIPGapAbs']==0
        assert s['TimeLimit']<=20 if p['type']=='DISCOVERY' else s['TimeLimit']<=120 if p['type']=='FINAL_CERTIFICATION' else s['TimeLimit']<=60
        pi,alpha=points[p['dual_SHA']];m=p['unit'];b=blocks[m];cost=b.d['objective']-b.B.T@pi
        assert hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest()==p['objective_SHA'] and p['ObjCon']==-float(alpha[m])
        if p['valid_point']:
            with np.load(OUT/p['point_file']) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
            matrix,attrs,route=full[m];raw=corrected_rows(matrix,attrs,x,True,route);assert b.validate(x,True)['PASS'] and raw['PASS'] and abs(float(exact_rc(b,x,pi,alpha[m]))-p['rc_inc'])<=EPS and sha(OUT/p['point_file'])==p['point_SHA']
        if p['valid_bound']:assert p['native_status'] in (2,9) and p['ObjBound'] is not None and (p['ObjVal'] is None or p['ObjBound']<=p['rc_inc']+EPS)
        assert not p['callback_first_negative_stop']
        checked.append(dict(call=p['call'],PASS=True,full_original_local_reaudit=p['valid_point'],same_dual=p['dual_SHA']))
    for c in ledger('DW_DISCOVERY_COLUMN_LEDGER.csv'):
        p=next(p for p in prices if p['call']==int(c['pricing_call']));assert p['type']=='DISCOVERY' and p['valid_point'] and p['rc_inc']<=DISCOVERY_RC and c['pricing_optimum_claimed']=='False'
        m=UNITS.index(c['MESS']);b=blocks[m]
        with np.load(OUT/c['file']) as z:assert b.validate(z['x'],True)['PASS'] and np.array_equal(b.B@z['x'],z['a']) and hash_column(z['x'],z['a'],float(z['c']))==c['SHA256']
        assert sha(OUT/c['file'])==c['file_SHA']
    g=np.flatnonzero(row_owner==-1);zcols=np.flatnonzero(owner==-1);G=B[g][:,zcols];gd=subset(e,g,zcols,native);gd['constant']=e['constant']
    with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][zcols];hi=z['upper'][zcols]
    proofs=[]
    for path in sorted((OUT/'bound_certificates').glob('*.json')):
        c=read(path);assert c['type'] in ('CERTIFICATION','FINAL_CERTIFICATION')
        if not c['certified']:continue
        pi,alpha=points[c['dual_SHA']];p=rational_bound(G,gd,pi,lo,hi);v=F(int(p['exact_bound_numerator']),int(p['exact_bound_denominator']))
        for m,file in enumerate(c['pricing_receipts']):
            r=read(OUT/file);assert r['valid_bound'] and r['dual_SHA']==c['dual_SHA'] and r['MESS']==UNITS[m];v+=F(float(alpha[m]))+min(F(0),F(down(F(float(r['ObjBound']))-F(EPS))))
        assert v==F(int(c['exact_numerator']),int(c['exact_denominator'])) and down(v)==c['L_corr'] and c['L_corr']<=c['U_RMP'];proofs.append(dict(PASS=True,file=path.relative_to(OUT).as_posix(),lower=down(v),upper=c['U_RMP']))
    for p in prices:
        for a,b in rmpspans:assert p['interval'][1]<=a or p['interval'][0]>=b,'RMP_AND_PRICING_OVERLAP'
    events=sorted([(p['interval'][0],1) for p in prices]+[(p['interval'][1],-1) for p in prices]);active=0;maximum=0
    for t,n in events:active+=n;maximum=max(maximum,active)
    assert maximum<=4
    for r in rmps:
        pp=[p for p in prices if p['round']==r['round']];assert all(p['dual_SHA']==r['dual_SHA'] for p in pp)
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=ROOT,check=True)
    write('VERIFICATION.json',dict(PASS=True,scientific_base=BASE,old_policy_stop_commit=result['old_policy_stop_commit'],old_policy_files_preserved=old_count,source_freeze_PASS=True,preopt_commit=commit,checkpoint_columns=1066,old_TIME_LIMIT_promotion=False,RMP_points_reaudited=len(points),pricing_independent_checks=checked,corrected_bound_independent_reconstructions=proofs,maximum_native_pricing_overlap=maximum,RMP_pricing_nonoverlap=True,budget_union_PASS=True,full_original_domain=True,heuristic_restrictions=False,tests={k:tests(k) for k in ('SEMANTIC','FULL')},production=[0,0,0]))
def campaign():
    from v42_campaign.plan import build_plan
    plan=build_plan();from v42_dw_bound.common import REF
    assert plan==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json') and len(plan['nodes'])==1458
    write('CAMPAIGN_ORCHESTRATOR_PRESERVATION.json',dict(PASS=True,unchanged_nodes=1458,plan_SHA=sha(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json'),arm_order=['B0','B1','B2','B3(L1)','B3(L2)','B3(L3)','B3(L4)'],B3='A1->M1->A2->M2',next_Planning='previous Planning only',Actual_feedback_to_Planning=False))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(optimizer=0,Actual=0,Fresh_AC=0,Branch_and_Price=False,production_M1=False,P2=False,A2=False,M2=False))
    p=read(OUT/'CAMPAIGN_WORKER_POLICY.json');r=read(OUT/'DW_POLICY_CANARY_FINAL.json');p['B3_INNER_PRICING_WORKERS']=r['workers'] if r['resource_PASS'] else 1;p['B3_RESOURCE_CANARY_PASS']=r['resource_PASS'];write('CAMPAIGN_WORKER_POLICY.json',p)
def report():
    r=read(OUT/'DW_POLICY_CANARY_FINAL.json');v=read(OUT/'VERIFICATION.json');a=read(OUT/'DW_POLICY_RESUME_CHECKPOINT_AUDIT.json');campaign();old=read(PREVIOUS/'DW_BOUND_SPEED_AUDIT.json');pub=read(OUT/'PUBLICATION.json') if (OUT/'PUBLICATION.json').exists() else {}
    write('DW_POLICY_SPEED_COMPARISON.json',dict(old_source_SHA=sha(PREVIOUS/'DW_BOUND_SPEED_AUDIT.json'),old_exact_optimal_policy=old,old_partial_result_SHA=sha(PREVIOUS/'DW_FINAL_RESULT.json'),old_columns_per_minute=r['old_columns_per_minute'],new_columns_per_minute=r['new_columns_per_minute'],throughput_scope='Accepted columns divided by observed experiment elapsed including build/audit. Old elapsed ends at last preserved telemetry sample; unreceipted active call timing is not claimed exact.',new_rounds=ledger('DW_DISCOVERY_ITERATION_LEDGER.csv')+ledger('DW_CERTIFICATION_ITERATION_LEDGER.csv'),new_RMP_iterations_per_minute=r['new_RMP_solves']/(r['total_elapsed_including_build_audit']/60),new_optimize_wall_union=r['total_optimize_wall_union'],new_sum_native_optimize_wall=r['sum_native_optimize_wall'],new_first_certificate_time=r['time_to_first_new_certified_LB'],materiality_decision_time=r['heavy_wall_to_materiality_decision'],old_bracket=[read(PREVIOUS/'DW_FINAL_RESULT.json')['first_interval'],read(PREVIOUS/'DW_FINAL_RESULT.json')['final_interval']],new_bracket=[r['best_corrected_LB'],r['smallest_RMP_upper']],bracket_narrowing_per_minute_new=((read(PREVIOUS/'DW_FINAL_RESULT.json')['final_interval'][1]-read(PREVIOUS/'DW_FINAL_RESULT.json')['final_interval'][0])-(r['smallest_RMP_upper']-r['best_corrected_LB']))/(r['total_elapsed_including_build_audit']/60),no_unsupported_causal_speedup_claim=True))
    flags=dict(OLD_POLICY_RUN_STOPPED_FOR_REDESIGN=True,OLD_POLICY_HISTORY_PRESERVED=True,OLD_POLICY_SCIENTIFIC_RESULT='INCONCLUSIVE',RESUMED_FROM_LATEST_ACCEPTED_COLUMN_CHECKPOINT=True,TIME_LIMIT_OLD_POLICY_INCUMBENTS_RETROACTIVELY_ADDED=False,DISCOVERY_PRICING_SECONDS=20,CERTIFICATION_PRICING_SECONDS=60,POLICY_CANARY_BUDGET_SECONDS=900,PRICING_THREADS=1,PRICING_WORKERS_SELECTED=r['workers'],PRICING_RESOURCE_CANARY_PASS=r['resource_PASS'],DW_HEURISTIC_DOMAIN_RESTRICTION=False,DW_DISCOVERY_COLUMNS_VALID=True,DW_BEST_CORRECTED_LB=r['best_corrected_LB'],DW_BEST_RMP_UPPER=r['smallest_RMP_upper'],DW_MATERIAL_THRESHOLD=T_MATERIAL,DW_MATERIALITY=r['materiality'],POLICY_CANARY=r['policy_canary'],BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,B2_INNER_PRICING_WORKERS=1,B3_INNER_PRICING_WORKERS=r['workers'] if r['resource_PASS'] else 1,MAY_PRODUCTION_OPTIMIZER_CALLS=0,MAY_ACTUAL_CALLS=0,MAY_FRESH_AC_CALLS=0,PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    first4=next((c for c in read(OUT/'DW_PRICING_CONCURRENCY_CANARY.json')['attempts'] if c['workers']==4),{})
    lines=[f"Old-policy STOP SHA {r['old_policy_stop_commit']}; POLICY_EXPERIMENT_PARTIAL / scientific INCONCLUSIVE. 정상 native terminal receipt가 없는 중단 call21 제외.",'Old-policy preregistration, source, receipts, certificates, logs, columns, tests 모두 바이트 보존.',f"Checkpoint retained columns {a['total_retained_columns']}=4+1044+18.",f"Old TIME_LIMIT incumbent {a['excluded_TIME_LIMIT_incumbents']}개 제외; call21도 제외.",f"새 policy preregistration commit {r['preopt_commit']}.",f"Pricing concurrency {r['workers']}; resource PASS {r['resource_PASS']}.",f"4-way observed peak pricing RSS {first4.get('observed_total_pricing_peak_RSS')}; parent {first4.get('observed_parent_peak_RSS')}; min available RAM {first4.get('min_available_RAM')} bytes. 정확한 unsampled peak는 주장하지 않음.",'Discovery pricing cap20초.','Certification cap60초; final cap최대120초.',f"Discovery rounds {r['discovery_rounds']}.",f"Certification rounds {r['certification_rounds']} (final 포함).",f"새 RMP solves {r['new_RMP_solves']}.",f"새 pricing calls {r['new_pricing_calls']}.",f"Validated discovery columns {r['new_discovery_columns']}.",f"Median discovery round wall {r['median_discovery_round_wall']}초.",f"Median certification round wall {r['median_certification_round_wall']}초.",f"Columns/min old {r['old_columns_per_minute']} vs new {r['new_columns_per_minute']}; build/audit 포함 observed elapsed 기준, 인과 speedup 주장 없음.",f"첫 새 corrected certified LB까지 elapsed {r['time_to_first_new_certified_LB']}초; optimize {r['heavy_to_first_new_certified_LB']}초.",f"Best corrected LB {r['best_corrected_LB']} (old inherited certificate 포함).",f"Smallest RMP upper {r['smallest_RMP_upper']}; original integer UB 아님.",f"최종 certified interval {r['final_interval']}.",f"Scientific materiality {r['materiality']}; threshold {T_MATERIAL}.",f"Policy canary {r['policy_canary']}; optimize wall union {r['total_optimize_wall_union']}/900초; stop {r['stop_reason']}.",'Branch-and-Price NOT_RUN.','May day workers B0/B1/B2/B3=4/1/4/1, Threads1.',f"B2 inner1 / B3 inner {flags['B3_INNER_PRICING_WORKERS']}, resource gate 이후만 허용.",'May optimizer/Actual/Fresh AC=0/0/0; scientific1458-node계획/firewall 보존.',f"Semantic {v['tests']['SEMANTIC']['passed']} / full {v['tests']['FULL']['passed']} PASS. Draft PR {pub.get('url','게시 전')}; result SHA {pub.get('result_commit','게시 전')}; 최종 SHA/remote/clean은 최종 응답에서 확인."]
    ending='''기존 exact-optimal-pricing-every-round 실험은 계산정책 병목이 확인되어 사용자 지시에 따라 중단했으며, 그 partial scientific result는 INCONCLUSIVE로 보존했다. 중단된 활성 call은 정상 native terminal receipt를 확인하지 못해 인증에서 제외했다.

새 Discovery round의 time-limited pricing은 full original pricing domain을 유지하고 valid negative trajectory만 column으로 추가했으며, pricing optimality를 주장하지 않았다.

Global D-W lower-bound 및 materiality certificate는 same-dual pricing global BestBd를 사용하는 Certification round에서만 증명했다. 이번 materiality 결과가 INCONCLUSIVE이면 material/nonmaterial 판정이 증명됐다는 뜻은 아니다.

B0/B1/B2/B3 May main campaign worker policy는 각각4/1/4/1 day-workers, Gurobi Threads=1로 동결했으며, B2는 outer-day 병렬화를 우선하고 B3는 resource canary 통과 시 inner four-MESS pricing 병렬화를 사용할 수 있도록 분리했다.

이번 task에서 May production, Branch-and-Price, production M1/P2/A2/M2/Actual/Fresh AC는 실행하지 않았다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+ending,encoding='utf8')
    (OUT/'PR_DESCRIPTION.md').write_text(f"The previous full-domain exact-optimal-every-round policy was stopped by the user for computational redesign. Its partial scientific result is INCONCLUSIVE and all completed evidence is preserved at {r['old_policy_stop_commit']}. Active call21 had no normal native terminal receipt after the session interrupt, so no partial bound or incumbent is certified.\n\nThis separately preregistered canary restores1066 actually accepted columns, excludes old TIME_LIMIT incumbents, and repeats three20s discovery rounds followed by one60s certification round. Discovery adds only independently audited original-domain negative incumbents with manual rc<=-1e-7, without claiming pricing optimality. Certification uses four same-dual terminal global ObjBounds, the unchanged exact rational global residual correction, fixed1e-8 safety and the prior proved theorem. Domains, physical bounds and the1e-8/1e-6 contracts are unchanged.\n\nResult: scientific {r['materiality']}, policy {r['policy_canary']}, interval {r['final_interval']}; workers {r['workers']}, discovery columns {r['new_discovery_columns']}, discovery/certification rounds {r['discovery_rounds']}/{r['certification_rounds']}; optimize wall union {r['total_optimize_wall_union']:.6f}/900s. No automatic extension. Observed columns/min {r['old_columns_per_minute']:.6f} old vs {r['new_columns_per_minute']:.6f} new; no causal speedup claim.\n\nValidation: semantic {v['tests']['SEMANTIC']['passed']} and full {v['tests']['FULL']['passed']} PASS; all original RMP/pricing rows, physical patterns, accepted column SHAs, same-dual binding, parallel-process overlap and independent Fraction certificates audited. Prior experiment files remain byte-identical. Future May workers4/1/4/1, B2 inner1 and gated B3 inner<=4 are frozen; production optimizer/Actual/Fresh AC0/0/0. No Branch-and-Price or downstream production.\n",encoding='utf8')
def manifest():
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in p.parts and p.suffix!='.pyc']
    for directory in ('v42_dw_policy','tests/v42_dw_policy'):files += [p for p in (ROOT/directory).glob('*') if p.is_file()]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(files)],self_excluded=True))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()
