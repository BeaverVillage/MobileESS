"""Independent original-domain audits and publication, after all workers join."""
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
    preserved=preserve_old();commit=verify_freeze();r=read(OUT/'DW_THROUGHPUT_FINAL.json');assert r['total_optimize_wall_union']<=900 and r['initial_retained_columns']==1078 and not r['old_TIME_LIMIT_retroactively_added']
    budget=read(OUT/'DW_OPTIMIZE_INTERVALS.json');assert abs(union_seconds(budget['intervals'])+budget['carried_budget_seconds']-r['total_optimize_wall_union'])<1e-9
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);mask=pure_binary_equalities(A,d);rmps=[read(p) for p in sorted(OUT.glob('RMP_RECEIPT_*.json'))];points={};nonprice=[]
    for record in rmps:
        nonprice.append(record['interval'])
        if record['status']!=2:assert record['dual_SHA'] is None;continue
        assert record['settings']['Threads']==1
        with np.load(OUT/record['point_file']) as z:
            assert corrected_rows(A,d,z['point'],False,mask)['PASS'];pi=z['pi'];alpha=z['alpha'];assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==record['dual_SHA'];assert hashlib.sha256(z['point'].tobytes()).hexdigest()==record['primal_SHA']
            points[record['dual_SHA']]=(pi,alpha)
        assert sha(OUT/record['point_file'])==record['point_SHA']
    warm=read(OUT/'DW_RMP_WARM_COLD_COMPARISON.json');warm_checked=[]
    for record in warm['records']:
        nonprice.append(record['interval']);assert record['settings']['Threads']==1
        log=(OUT/record['log_file']).read_text(encoding='utf8',errors='replace')
        if record['basis_accepted']:assert 'discard basis' not in log and ('get start vectors from basis' in log or 'use basis' in log or 'crush' in log and 'warm-start' in log)
        if record['status']==2:
            with np.load(OUT/record['point_file']) as z:assert corrected_rows(A,d,z['point'],False,mask)['PASS']
            assert sha(OUT/record['point_file'])==record['point_SHA']
        warm_checked.append(dict(index=record['index'],full_original_reaudit=record['status']==2,basis_accepted=record['basis_accepted']))
    if warm['selected']:
        assert warm['objective_agreement_PASS'] and warm['median_wall_reduction']>=.30 and all(q['full_postsolve']['PASS'] for q in warm['records']) and all(q['basis_accepted'] for q in warm['records'] if q['path']=='warm')
        objectives=[q['objective'] for q in warm['records']];assert max(objectives)-min(objectives)<=EPS
    rr={m:[] for m in range(4)}
    for i in range(A.shape[0]):
        deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(deps)==1 and next(iter(deps)) in rr:rr[next(iter(deps))].append(i)
    full={}
    for m,b in enumerate(blocks):
        rows=np.array(rr[m]);cc=b.columns;matrix=A[rows][:,cc];attrs=dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.));full[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs))
    def local(m,file):
        b=blocks[m]
        with np.load(OUT/file) as z:x=z['x'];assert np.array_equal(z['axis'],b.columns)
        matrix,attrs,route=full[m];return x,b.validate(x,True),corrected_rows(matrix,attrs,x,True,route)
    prices=[read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))];captures=[];checked=[]
    for p in prices:
        assert p['true_dual_SHA'] in points and p['full_original_domain'] and p['horizon']==96 and p['objective_transport_exact'] and p['no_fixing'] and not p['callback_first_negative_stop']
        s=p['settings'];assert s['Threads']==1 and s['FeasibilityTol']==s['IntFeasTol']==s['OptimalityTol']==EPS and s['MIPGap']==s['MIPGapAbs']==0 and s['TimeLimit']<=(20 if p['type']=='DISCOVERY' else 60)
        with np.load(OUT/p['dual_file']) as z:pi=z['pi'];alpha=z['alpha']
        assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==p['dual_SHA']
        if p['type']!='DISCOVERY':assert p['dual_SHA']==p['true_dual_SHA'] and not p['stabilized_discovery']
        true_pi,true_alpha=points[p['true_dual_SHA']];m=p['unit'];b=blocks[m];cost=b.d['objective']-b.B.T@pi
        assert hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest()==p['objective_SHA'] and p['ObjCon']==-float(alpha[m])
        if p['valid_point']:
            x,physical,raw=local(m,p['point_file']);assert physical['PASS'] and raw['PASS'] and abs(float(exact_rc(b,x,pi,alpha[m]))-p['rc_inc'])<=EPS and sha(OUT/p['point_file'])==p['point_SHA']
        if p['valid_bound']:assert p['native_status'] in (2,9) and p['ObjBound'] is not None and (p['ObjVal'] is None or p['ObjBound']<=p['rc_inc']+EPS)
        assert sum(c['selected'] for c in p['candidates'])<=4
        for c in p['candidates']:
            x,physical,raw=local(m,c['point_file']);rc=float(exact_rc(b,x,true_pi,true_alpha[m]));search=float(exact_rc(b,x,pi,alpha[m]));assert hashlib.sha256(x.tobytes()).hexdigest()==c['raw_SHA'] and sha(OUT/c['point_file'])==c['point_SHA'] and b.column(x)[2]==c['column_SHA']
            valid=bool(physical['PASS'] and raw['PASS'] and abs(search-c['solver_objective'])<=EPS and search<=DISCOVERY_RC and rc<=DISCOVERY_RC);assert valid==c['valid_negative'] and abs(rc-c['rc_inc'])<=EPS and not c['pricing_optimum_claimed']
            captures.append(dict(call=p['call'],arrival=c['arrival'],PASS=True,selected=c['selected'],valid_negative=valid,full_original_local=raw['PASS'],physical=physical['PASS'],manual_rc=rc))
        checked.append(dict(call=p['call'],PASS=True,true_dual=p['true_dual_SHA'],search_dual=p['dual_SHA']))
    seen=[set() for _ in UNITS]
    for h in read(OUT/'DW_THROUGHPUT_BASE_AUDIT.json')['checks']:seen[UNITS.index(h['MESS'])].add(h['column_SHA'])
    columns=ledger('DW_DISCOVERY_COLUMN_LEDGER.csv')
    for c in columns:
        p=next(p for p in prices if p['call']==int(c['pricing_call']));m=UNITS.index(c['MESS']);b=blocks[m];assert p['type']=='DISCOVERY' and c['pricing_optimum_claimed']=='False' and c['label']=='VALID_NEGATIVE_DISCOVERY_COLUMNS'
        capture=next(q for q in p['candidates'] if q['column_SHA']==c['SHA256']);assert capture['selected'] and capture['valid_negative']
        with np.load(OUT/c['file']) as z:
            x=z['x'];a=z['a'];cost=float(z['c']);assert b.validate(x,True)['PASS'] and np.array_equal(b.B@x,a) and hash_column(x,a,cost)==c['SHA256'];assert abs(float(exact_rc(b,x,*[points[p['true_dual_SHA']][0],points[p['true_dual_SHA']][1][m]]))-float(c['rc_inc']))<=EPS
        assert c['SHA256'] not in seen[m];seen[m].add(c['SHA256']);assert sha(OUT/c['file'])==c['file_SHA']
    checkpoint=read(OUT/'DW_THROUGHPUT_CHECKPOINT_LATEST.json');assert checkpoint['total_retained_columns']==1078+len(columns)==len(checkpoint['pool'])
    g=np.flatnonzero(row_owner==-1);zcols=np.flatnonzero(owner==-1);G=B[g][:,zcols];gd=subset(e,g,zcols,native);gd['constant']=e['constant']
    with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][zcols];hi=z['upper'][zcols]
    proofs=[]
    for path in sorted((OUT/'bound_certificates').glob('*.json')):
        c=read(path);assert c['type'] in ('CERTIFICATION','FINAL_CERTIFICATION')
        if not c['certified']:continue
        pi,alpha=points[c['dual_SHA']];p=rational_bound(G,gd,pi,lo,hi);v=F(int(p['exact_bound_numerator']),int(p['exact_bound_denominator']))
        for m,file in enumerate(c['pricing_receipts']):
            q=read(OUT/file);assert q['valid_bound'] and q['dual_SHA']==c['dual_SHA']==q['true_dual_SHA'] and q['MESS']==UNITS[m];v+=F(float(alpha[m]))+min(F(0),F(down(F(float(q['ObjBound']))-F(EPS))))
        assert v==F(int(c['exact_numerator']),int(c['exact_denominator'])) and down(v)==c['L_corr'] and c['L_corr']<=c['U_RMP'];proofs.append(dict(PASS=True,file=path.relative_to(OUT).as_posix(),lower=down(v),upper=c['U_RMP']))
    for p in prices:
        for a,b in nonprice:assert p['interval'][1]<=a or p['interval'][0]>=b,'RMP_PRICING_OVERLAP'
    actual_four=overlap_seconds([p['interval'] for p in prices],4);summary=read(OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY.json');assert abs(actual_four-summary['all_native_pricing_overlap_four_seconds'])<1e-6
    timeline=ledger('DW_TRUE_4WAY_RESOURCE_TIMELINE.csv');active_samples=[t for t in timeline if sum(a<=float(t['perf'])<=b for a,b in [p['interval'] for p in prices])==4]
    if summary['PASS']:assert actual_four>0 and active_samples and all(float(t['available_RAM'])>=1024**3 and float(t['commit_percent'])<95 for t in active_samples)
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=ROOT,check=True)
    write('DW_MULTICOLUMN_VALIDATION.json',dict(PASS=True,checks=captures,all_original_local_rows=True,raw_integer_exact=True,route_PQ_SOC_init_terminal_travel_PCS16=True,accepted_columns=len(columns),no_optimum_or_rank_claims=True,dedup_bit_exact_only=True,column_pool_monotonic=True))
    write('VERIFICATION.json',dict(PASS=True,PR141_head=BASE_HEAD,PR141_files_preserved=preserved,source_freeze_PASS=True,preopt_commit=commit,initial_checkpoint_columns=1078,old_TIME_LIMIT_promotion=False,RMP_points_reaudited=len(rmps),warm_copy_checks=warm_checked,pricing_checks=checked,multicolumn_checks=len(captures),corrected_bound_independent_reconstructions=proofs,actual_four_overlap_seconds=actual_four,true_four_active_telemetry_samples=len(active_samples),RMP_pricing_nonoverlap=True,budget_union_PASS=True,full_original_domain=True,heuristic_restrictions=False,tests={k:tests(k) for k in ('SEMANTIC','FULL')},production=[0,0,0]))
def campaign():
    from v42_campaign.plan import build_plan
    from v42_dw_bound.common import REF
    plan=build_plan();assert plan==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json') and len(plan['nodes'])==1458
    write('CAMPAIGN_ORCHESTRATOR_PRESERVATION.json',dict(PASS=True,unchanged_nodes=1458,plan_SHA=sha(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json'),arm_order=['B0','B1','B2','B3(L1)','B3(L2)','B3(L3)','B3(L4)'],B3='A1->M1->A2->M2',next_Planning='previous Planning only',Actual_feedback_to_Planning=False))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(optimizer=0,Actual=0,Fresh_AC=0,Branch_and_Price=False,production_M1=False,P2=False,A2=False,M2=False))
    p=read(OUT/'CAMPAIGN_WORKER_POLICY.json');r=read(OUT/'DW_THROUGHPUT_FINAL.json');p['B3_INNER_PRICING_WORKERS']=4 if r['true_4way_resource_PASS'] else r['workers'];p['B3_RESOURCE_CANARY_PASS']=r['resource_PASS'];write('CAMPAIGN_WORKER_POLICY.json',p)
def report():
    r=read(OUT/'DW_THROUGHPUT_FINAL.json');v=read(OUT/'VERIFICATION.json');w=read(OUT/'DW_RMP_WARM_COLD_COMPARISON.json');s=read(OUT/'DW_TRUE_4WAY_RESOURCE_SUMMARY.json');campaign();pub=read(OUT/'PUBLICATION.json') if (OUT/'PUBLICATION.json').exists() else {}
    read_old=read(POLICY/'DW_POLICY_CANARY_FINAL.json');minutes=r['total_elapsed_including_build_audit']/60
    write('DW_THROUGHPUT_SPEED_AUDIT.json',dict(PR141_columns_per_minute=.80998069224726,new_columns_per_minute=r['new_columns_per_minute'],PR141_discovery_median=88.07946670003003,new_discovery_median=r['median_discovery_round_wall'],PR141_certification_median=222.48962115001632,new_certification_median=r['median_certification_round_wall'],RMP_rounds_per_minute=r['new_RMP_solves']/minutes,certified_interval_narrowing_per_minute=((read_old['final_interval'][1]-read_old['final_interval'][0])-(r['final_interval'][1]-r['final_interval'][0]))/minutes,warm_canary_included_in_elapsed_and_budget=True,throughput_scope='New accepted distinct columns / total experiment elapsed including build, native canaries, postsolve audits, checkpoints; no causal speed claim from one run',targets=dict(discovery_median_at_most_35=r['median_discovery_round_wall'] is not None and r['median_discovery_round_wall']<=35,columns_per_minute_at_least_2=r['new_columns_per_minute']>=2,warm_reduction_at_least_30_percent=w.get('median_wall_reduction',-1)>=.30 if w.get('median_wall_reduction') is not None else False)))
    flags=dict(DUAL_SMOOTHING_ENABLED=True,DUAL_SMOOTHING_MODE='adaptive_exponential',DUAL_SMOOTHING_ALPHA_INITIAL=.30,DUAL_SMOOTHING_ALPHA_MIN=.10,DUAL_SMOOTHING_ALPHA_MAX=.80,DUAL_SMOOTHING_DISCOVERY_ONLY=True,TRUE_DUAL_REQUIRED_FOR_COLUMN_ACCEPTANCE=True,TRUE_DUAL_REQUIRED_FOR_CERTIFICATION=True,BOX_STABILIZATION_RUN=False,PROXIMAL_STABILIZATION_RUN=False,TRUST_REGION_STABILIZATION_RUN=False,DUAL_SMOOTHING_COLUMNS_PROPOSED=r['smoothing_proposed'],DUAL_SMOOTHING_COLUMNS_TRUE_NEGATIVE=r['smoothing_true_negative'],DUAL_SMOOTHING_COLUMNS_REJECTED_AFTER_TRUE_RC=r['smoothing_rejected_after_true_RC'],DUAL_SMOOTHING_SELECTED=True,SMOOTHING_STAGNATION=r['SMOOTHING_STAGNATION'],M1_MODEL_PRESERVED=True,RAM_GATE_GIB=1,ACTUAL_4WAY_PRICING_ATTEMPTED=s['actual_4way_attempted'],ACTUAL_4WAY_PRICING_CALLS=s['actual_4way_pricing_calls'],TRUE_4WAY_RESOURCE_PASS=s['PASS'],PRICING_THREADS=1,B3_INNER_PRICING_WORKERS=4 if s['PASS'] else r['workers'],MULTICOLUMN_DISCOVERY=True,MAX_COLUMNS_PER_MESS_PER_DISCOVERY=4,RMP_WARMSTART_TESTED=w['tested'],RMP_WARMSTART_SELECTED=w['selected'],DUAL_STABILIZATION_TESTED=r['dual_stabilization_tested'],DUAL_STABILIZATION_SELECTED=r['dual_stabilization_selected'],PR141_COLUMNS_PER_MIN=.80998069224726,NEW_COLUMNS_PER_MIN=r['new_columns_per_minute'],PR141_DISCOVERY_MEDIAN=88.07946670003003,NEW_DISCOVERY_MEDIAN=r['median_discovery_round_wall'],DW_BEST_CORRECTED_LB=r['best_corrected_LB'],DW_BEST_RMP_UPPER=r['smallest_RMP_upper'],DW_MATERIALITY=r['materiality'],BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,B2_INNER_PRICING_WORKERS=1,MAY_PRODUCTION_CALLS=0,MAY_PRODUCTION_OPTIMIZER_CALLS=0,MAY_ACTUAL_CALLS=0,MAY_FRESH_AC_CALLS=0,PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    four=[c for c in s['attempts'] if c['workers']==4 and c.get('actual_four_overlap_seconds',0)>0];peak=max((c['observed_total_tree_peak_RSS'] for c in four),default=None);minimum=min((c['min_available_RAM'] for c in four),default=None);commit=max((c['max_commit_percent'] for c in four),default=None);page=max((c['pagefile_delta_bytes'] for c in four),default=None)
    discovery=[p for p in (read(q) for q in sorted((OUT/'pricing_receipts').glob('*.json'))) if p['type']=='DISCOVERY'];per=[sum(c['selected'] for c in p['candidates']) for p in discovery];osc=ledger('DW_DUAL_OSCILLATION_AUDIT.csv')
    lines=[f"Draft PR {pub.get('PR','publication pending')}, final SHA {pub.get('final_commit','publication pending')}; semantic {v['tests']['SEMANTIC']['passed']}, full {v['tests']['FULL']['passed']} PASS; 최종 clean/remote 검증은 PUBLICATION.json.",f'PR141 exact head {BASE_HEAD}: PASS.', 'Checkpoint 1078개, 제외된 old TIME_LIMIT/interrupted/uncertified points 승격 없음.','RAM floor 1 GiB; old8GiB/15% superseded.',f"실제 four-way native optimize overlap {s['all_native_pricing_overlap_four_seconds']}초; PASS {s['PASS']}.",f'Four-way sampled total-tree peak RSS {peak} bytes (정확한 unsampled peak 아님).',f'Four-way min available RAM {minimum} bytes.',f'Four-way max system commit {commit}%.',f'Four-way 최대 batch pagefile delta {page} bytes; sustained combined thrashing failure는 resource attempts 참조.',f"선택 pricing concurrency {r['workers']}.",f"Discovery rounds {r['discovery_rounds']}.",f"Pricing calls {r['new_pricing_calls']} (four-way {s['actual_4way_pricing_calls']}).",f"Validated added columns {r['new_discovery_columns']}; retained {r['retained_columns']}.",f'선택한 multi-column/call mean {float(np.mean(per)) if per else None}, max {max(per) if per else None}; 전역 optimum/top4/rank 주장 없음.',f"Columns/min PR141 .80998069224726 → {r['new_columns_per_minute']}.",f"Discovery median PR14188.07946670003003 → {r['median_discovery_round_wall']}초 (warm canary와 감사 포함).",f"Cold RMP median {w.get('cold_median_wall')}초.",f"Warm RMP median {w.get('warm_median_wall')}초.",f"Warm basis accepted {[q['basis_accepted'] for q in w['records'] if q['path']=='warm']}.",f"Warm median wall reduction {w.get('median_wall_reduction')}; selected {w['selected']}.",f'연속 dual L1/L2/Linf·normalizedL2·grid variation·turnover·near-duplicate·RC variance {len(osc)}행: DW_DUAL_OSCILLATION_AUDIT.csv.',f"Stabilization tested {r['dual_stabilization_tested']}, selected {r['dual_stabilization_selected']}; mandatory adaptive smoothing, alpha initial.30 / final {r['smoothing_alpha_final']}; box/proximal/trust-region 실행 없음.",f"Best corrected LB {r['best_corrected_LB']}.",f"Min audited RMP upper {r['smallest_RMP_upper']} (D-W LP upper).",f"Final interval {r['final_interval']}.",f"Materiality {r['materiality']}; T {T_MATERIAL}; root optimum/convergence {r['DW_ROOT_OPTIMAL_CERTIFIED']}.",'May day workers B0/B1/B2/B3 =4/1/4/1, 각31일; original1458-node plan/feedback firewall 유지.',f"B3 inner workers {flags['B3_INNER_PRICING_WORKERS']}, Threads1, B2 inner1.",'Branch-and-Price·productionM1·P2/A2/M2 실행 안 함.','May optimizer/Actual/FreshAC =0/0/0.']
    end=['Adaptive dual smoothing은 Discovery pricing 가속에만 사용했다.','Smoothed dual에서 발견된 trajectory는 동일 iteration의 unstabilized true RMP dual로 reduced cost를 재계산한 뒤 true reduced cost가 음수인 경우에만 column으로 추가했다.','Scientific lower-bound, materiality, no-negative 및 CG convergence certificate는 모두 unstabilized true RMP dual과 global pricing BestBd를 사용했다.','따라서 dual smoothing은 exact feasible domain이나 scientific global certificate를 변경하지 않았다.','이번 task에서는 1 GiB available-RAM floor를 사용해 실제 4-way pricing optimize concurrency를 시험했으며, old 8 GiB gate를 이유로 pricing 시작 전에 실패 판정하지 않았다.','Discovery에서 여러 negative trajectory를 한 pricing solve에서 수집했지만, 모든 trajectory는 full original pricing domain에서 feasible하고 manual reduced-cost audit을 통과한 경우에만 D-W column으로 사용했다.','Scientific lower-bound/materiality certificate는 unstabilized true RMP dual과 global pricing BestBd를 사용하는 exact Certification layer에서만 생성했다.','May production과 Branch-and-Price는 실행하지 않았다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+'\n\n'.join(end)+'\n',encoding='utf8')
    (OUT/'PR_DESCRIPTION.md').write_text(f"PR141's 8 GiB gate stopped four-worker residency before any four-way pricing optimize. This computational-policy canary starts from its exact1078-column checkpoint, uses a1 GiB floor plus commit/thrashing/OOM safeguards, and captures independently validated negative MIPSOL trajectories in the unchanged full pricing domain.\n\nActual four-way resource PASS: {s['PASS']}; native overlap {s['all_native_pricing_overlap_four_seconds']:.3f}s; pricing calls {r['new_pricing_calls']}; new columns {r['new_discovery_columns']}. Columns/min .80998 → {r['new_columns_per_minute']:.5f}; discovery median88.079s → {r['median_discovery_round_wall']}. Warm RMP selected: {w['selected']}.\n\nUnstabilized same-dual corrected certification remains unchanged. Materiality {r['materiality']}, bracket {r['final_interval']}; no CG convergence/root optimality claim. Heavy union {r['total_optimize_wall_union']:.3f}s <=900s, including warm/cold copies. PR141 files byte-preserved; semantic {v['tests']['SEMANTIC']['passed']} / full {v['tests']['FULL']['passed']} pass, Threads1 with no overlapping test optimize. May/Actual/FreshAC=0/0/0; no B&P/production M1/P2/A2/M2.\n",encoding='utf8')
def manifest():
    paths=[]
    for directory in (ROOT/'v42_dw_throughput',ROOT/'tests/v42_dw_throughput',OUT):paths += [p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='SHA256_MANIFEST.json']
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)]))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()
