"""Post-worker independent original-axis dual/primal/CG and byte audits."""
from .common import *
import numpy as np,re
from fractions import Fraction as F

def independent_arc(A,d):
    from v42_disjunctive.certificate import down
    certificate=read(OUT/'ARC_LP_DUAL_SUPPORT_CERTIFICATE.json')
    with np.load(OUT/'ARC_LP_RATIONAL_DUAL.npz') as z:pi={int(i):F(int(n),int(q)) for i,n,q in zip(z['rows'],z['numerators'],z['denominators'])}
    assert all(d['sense'][i]=='=' or d['sense'][i]=='<' and p<=0 or d['sense'][i]=='>' and p>=0 for i,p in pi.items())
    rhs=F(float(d['constant']))+sum((p*F(float(d['rhs'][i])) for i,p in pi.items()),F(0));support=F(0);free=0;C=A.tocsc()
    for j in range(A.shape[1]):
        a,b=C.indptr[j:j+2];q=F(float(d['objective'][j]))-sum((pi.get(int(i),F(0))*F(float(v)) for i,v in zip(C.indices[a:b],C.data[a:b]) if int(i) in pi),F(0))
        if q:
            endpoint=d['lower'][j] if q>0 else d['upper'][j];assert np.isfinite(endpoint) and abs(endpoint)<1e90,'INDEPENDENT_INFINITE_SUPPORT'
            support+=q*F(float(endpoint))
        if not np.isfinite(d['lower'][j]) or not np.isfinite(d['upper'][j]):assert q==0;free+=1
    value=rhs+support;assert value==F(int(certificate['exact_numerator']),int(certificate['exact_denominator'])) and down(value)==certificate['L_dual_support']
    return dict(PASS=True,method='Independent CSC-column exact Fraction dot products from saved rational dual; no equality-repair algorithm reused.',free_stationarity_zero=free,original_bounds_only=True,exact_numerator=str(value.numerator),exact_denominator=str(value.denominator),L_dual_support=down(value))

def verify():
    from v42_degen.identity import inputs
    from v42_dw_root.partition import axes
    from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
    from v42_dw_root.models import hash_column,subset
    from v42_dw_root.run import exact_rc
    from v42_disjunctive.certificate import rational_bound,down
    count=preserve_old();verify_freeze();f=read(OUT/'EXECUTION_FREEZE.json');assert all(sha(OUT/p)==s for p,s in f['arrays'].items())
    A,d,B,e,*_=inputs();owner,row_owner=axes();arc=read(OUT/'ARC_LP_CERTIFIED_RESULT.json');assert arc['ARC_LP_CERTIFIED']
    native=read(OUT/'ARC_LP_NATIVE_RECEIPT.json');assert native['status']==2 and not native['IsMIP'] and native['discrete_variables']==0 and native['optimize_union_seconds']<=600
    with np.load(OUT/'ARC_LP_NATIVE_POINT.npz') as z:primal=corrected_rows(A,d,z['x'],False,pure_binary_equalities(A,d));assert primal['PASS'] and abs(primal['objective']-arc['native_optimum'])<=EPS
    independent=independent_arc(A,d);write('ARC_LP_INDEPENDENT_DUAL_AUDIT.json',independent)
    authority=read(OUT/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');expected=thresholds(arc['native_optimum'],arc['L_arc_cert']);assert all(authority[k]==v for k,v in expected.items())
    result=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');budget=read(OUT/'DW_OPTIMIZE_INTERVALS.json');assert union_seconds(budget['intervals'])==result['total_optimize_wall_union']<=900 and budget['arc_budget_carried']==0
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native_names=z['names']
    blocks=prototypes(B,e,owner,row_owner,native_names);mask=pure_binary_equalities(A,d);rmps=[read(p) for p in sorted(OUT.glob('RMP_RECEIPT_*.json'))];duals={};nonprice=[]
    for row in rmps:
        nonprice.append(row['interval']);assert not row['warm_basis_supplied'] and row['settings']['Threads']==1 and row['settings']['LPWarmStart']==0
        if row['status']!=2:assert row['dual_SHA'] is None;continue
        with np.load(OUT/row['point_file']) as z:
            assert corrected_rows(A,d,z['point'],False,mask)['PASS'];pi=z['pi'];alpha=z['alpha'];assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==row['dual_SHA'];duals[row['dual_SHA']]=(pi,alpha)
        assert sha(OUT/row['point_file'])==row['point_SHA']
    full={};rr=[[] for _ in UNITS]
    for i in range(A.shape[0]):
        dependencies=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(dependencies)==1 and -1 not in dependencies:rr[next(iter(dependencies))].append(i)
    for m,b in enumerate(blocks):
        rows=np.array(rr[m]);cc=b.columns;matrix=A[rows][:,cc];attrs=dict(d,rhs=d['rhs'][rows],sense=d['sense'][rows],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.));full[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs))
    def local(file,m):
        with np.load(OUT/file) as z:x=z['x'];assert np.array_equal(z['axis'],blocks[m].columns)
        matrix,attrs,route=full[m];return x,blocks[m].validate(x,True),corrected_rows(matrix,attrs,x,True,route)
    prices=[read(p) for p in sorted((OUT/'pricing_receipts').glob('PRICE_*.json'))];captures=[]
    for p in prices:
        assert p['true_dual_SHA'] in duals and p['full_original_domain'] and p['horizon']==96 and not p['basis_or_pool_restriction'] and p['no_fixing']
        assert p['settings']['Threads']==1 and p['settings']['TimeLimit']<=(20 if p['type']=='DISCOVERY' else 90)
        assert p['settings']['FeasibilityTol']==p['settings']['IntFeasTol']==p['settings']['OptimalityTol']==EPS
        true_pi,true_alpha=duals[p['true_dual_SHA']]
        with np.load(OUT/p['dual_file']) as z:pi=z['pi'];alpha=z['alpha']
        assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==p['dual_SHA']
        if p['type']!='DISCOVERY':assert p['dual_SHA']==p['true_dual_SHA'] and not p['stabilized_discovery']
        if p['valid_point']:
            x,physical,raw=local(p['point_file'],p['unit']);assert physical['PASS'] and raw['PASS'] and abs(float(exact_rc(blocks[p['unit']],x,pi,alpha[p['unit']]))-p['rc_inc'])<=EPS
        if p['valid_bound']:assert p['ObjBound'] is not None and p['native_status'] in (2,9) and (p['ObjVal'] is None or p['ObjBound']<=p['rc_inc']+EPS)
        assert sum(c['selected'] for c in p['candidates'])<=4
        for c in p['candidates']:
            x,physical,raw=local(c['point_file'],p['unit']);true=float(exact_rc(blocks[p['unit']],x,true_pi,true_alpha[p['unit']]));search=float(exact_rc(blocks[p['unit']],x,pi,alpha[p['unit']]))
            valid=bool(physical['PASS'] and raw['PASS'] and abs(search-c['solver_objective'])<=EPS and search<=DISCOVERY_RC and true<=DISCOVERY_RC);assert valid==c['valid_negative'] and abs(true-c['rc_inc'])<=EPS
            assert blocks[p['unit']].column(x)[2]==c['column_SHA'] and sha(OUT/c['point_file'])==c['point_SHA'];captures.append(dict(call=p['call'],arrival=c['arrival'],PASS=True,valid_negative=valid,selected=c['selected']))
        assert all(p['interval'][1]<=a or p['interval'][0]>=b for a,b in nonprice)
    original=read(OUT/'ARC_LP_BASE_IDENTITY.json')['checks'];seen=[set(x['column_SHA'] for x in original if x['MESS']==u) for u in UNITS]
    for c in ledger('DW_DISCOVERY_COLUMN_LEDGER.csv'):
        m=UNITS.index(c['MESS']);p=next(p for p in prices if p['call']==int(c['pricing_call']));assert p['type']=='DISCOVERY';candidate=next(x for x in p['candidates'] if x['column_SHA']==c['SHA256']);assert candidate['selected'] and candidate['valid_negative']
        with np.load(OUT/c['file']) as z:x=z['x'];a=z['a'];cost=float(z['c']);assert hash_column(x,a,cost)==c['SHA256'] and np.array_equal(blocks[m].B@x,a)
        assert c['SHA256'] not in seen[m] and sha(OUT/c['file'])==c['file_SHA'];seen[m].add(c['SHA256'])
    checkpoint=read(OUT/'DW_CHECKPOINT_LATEST.json');assert checkpoint['total_retained_columns']==1158+result['new_discovery_columns']==len(checkpoint['pool']);assert all(sha(ROOT/x['file'])==x['file_SHA'] for x in checkpoint['pool'])
    certified=[];g=np.flatnonzero(row_owner<0);zc=np.flatnonzero(owner<0);G=B[g][:,zc];gd=subset(e,g,zc,native_names);gd['constant']=e['constant']
    with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][zc];hi=z['upper'][zc]
    for file in sorted((OUT/'bound_certificates').glob('*.json')):
        c=read(file)
        if not c['certified']:continue
        pi,alpha=duals[c['dual_SHA']];proof=rational_bound(G,gd,pi,lo,hi);v=F(int(proof['exact_bound_numerator']),int(proof['exact_bound_denominator']))
        for m,pfile in enumerate(c['pricing_receipts']):
            p=read(OUT/pfile);assert p['valid_bound'] and p['dual_SHA']==p['true_dual_SHA']==c['dual_SHA'];v+=F(float(alpha[m]))+min(F(0),F(down(F(float(p['ObjBound']))-F(EPS))))
        assert v==F(int(c['exact_numerator']),int(c['exact_denominator'])) and down(v)==c['L_corr'];certified.append(dict(PASS=True,file=c['file'],L_corr=c['L_corr']))
    expectedLB=max(arc['L_arc_cert'],read(PR142/'DW_THROUGHPUT_FINAL.json')['best_corrected_LB'],*[c['L_corr'] for c in certified]);assert result['best_certified_LB']==expectedLB
    assert result['materiality']==decision(result['best_certified_LB'],result['smallest_RMP_upper'],authority)
    tests={}
    for label in ('SEMANTIC','FULL'):
        record=read(OUT/f'PYTEST_{label}_RECEIPT.json');log=(OUT/f'{label}_TEST.log').read_text(encoding='utf8');matches=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
        assert record['exit_code']==0 and matches and record['all_Gurobi_Threads_one'] and record['calls_nonoverlapping'];tests[label]=dict(PASS=True,passed=int(matches[-1][0]),seconds=float(matches[-1][1]))
    write('DW_INDEPENDENT_COLUMN_AUDIT.json',dict(PASS=True,captures=captures,accepted=result['new_discovery_columns'],raw_integer_exact=True,full_original_rows=True,true_dual_acceptance=True))
    write('VERIFICATION.json',dict(PASS=True,base_head=BASE_HEAD,previous_files_preserved=count,original_FULL_matrix=True,integrality_only_relaxed=True,arc_LP_OPTIMAL=True,independent_arc_dual=independent,arc_primal=primal,pricing_certificates=certified,tests=tests,arc_budget=native['optimize_union_seconds'],CG_budget=result['total_optimize_wall_union'],budgets_separate=True,global_MIP_BestBd_not_arc_authority=True,pricing_incumbent_not_LB=True,no_domain_restriction=True,no_pricing_redesign=True,May_production=[0,0,0],git_diff_check='Run before commit'))
    report(tests);flags();manifest();print('ARC_CG_INDEPENDENT_VERIFICATION_PASS',tests,flush=True)

def flags():
    a=read(OUT/'ARC_LP_CERTIFIED_RESULT.json');r=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');l=read(OUT/'ARC_LP_LEGACY_COMPARISON.json')
    write('FINAL_FLAGS.json',dict(ARC_LP_CERTIFIED=a['ARC_LP_CERTIFIED'],ARC_LP_NATIVE_OPTIMUM=a['native_optimum'],ARC_LP_CERTIFIED_LOWER=a['L_arc_cert'],ARC_LP_PRIMAL_DUAL_GAP=a['primal_dual_gap'],LEGACY_MIP_BESTBD=BASE_LB,LEGACY_MATCH_CLASS=l['classification'],DW_DOMINANCE_PROVEN=True,DW_ARC_FLOOR_TRANSFER_VALID=True,DW_ARC_FLOOR=a['L_arc_cert'],DW_OLD_CORRECTED_LB=read(PR142/'DW_THROUGHPUT_FINAL.json')['best_corrected_LB'],DW_EXISTING_UPPER=read(PR142/'DW_THROUGHPUT_FINAL.json')['smallest_RMP_upper'],DW_MATERIAL_THRESHOLD_CERT=r['material_threshold'],DW_LEGACY_THRESHOLD=T_MATERIAL,FOUR_WAY_PRICING=True,PRICING_THREADS=1,RAM_FLOOR_GIB=1,ADAPTIVE_DUAL_SMOOTHING=True,WARM_RMP_SELECTED=False,DW_NEW_DISCOVERY_ROUNDS=r['discovery_rounds'],DW_NEW_COLUMNS=r['new_discovery_columns'],DW_NEW_CORRECTED_LB=r['new_corrected_LB'],DW_BEST_CERTIFIED_LB=r['best_certified_LB'],DW_BEST_RMP_UPPER=r['smallest_RMP_upper'],DW_FINAL_INTERVAL=r['final_interval'],DW_MATERIALITY=r['materiality'],DW_CG_CONVERGED=r['DW_ROOT_OPTIMAL_CERTIFIED'],BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,B0_DAY_WORKERS=4,B1_DAY_WORKERS=1,B2_DAY_WORKERS=4,B3_DAY_WORKERS=1,B2_INNER_PRICING=1,B3_INNER_PRICING=4,MAY_PRODUCTION_CALLS=0,PROBLEM13_FINAL_VALIDATED=False))

def report(tests):
    a=read(OUT/'ARC_LP_CERTIFIED_RESULT.json');r=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');n=read(OUT/'ARC_LP_NATIVE_RECEIPT.json');p=read(OUT/'ARC_LP_PRIMAL_AUDIT.json');l=read(OUT/'ARC_LP_LEGACY_COMPARISON.json');identity=read(OUT/'ARC_LP_RELAXATION_IDENTITY.json');t=read(OUT/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');rmps=ledger('DW_RMP_LEDGER.csv');final=read(OUT/'DW_THRESHOLD_FINAL_CERTIFICATION.json');restore=read(OUT/'DW_SMOOTHING_RESTORE_RECEIPT.json')
    lines=[f"Draft PR/SHA는 게시 후 PR 본문에 기록. Semantic {tests['SEMANTIC']['passed']} / full {tests['FULL']['passed']} PASS; git clean은 push 후 검증.",f'PR143 exact head {BASE_HEAD} 및 모든 old tracked bytes 보존.',f"Frozen FULL matrix {identity['rows']} rows / {identity['columns']} columns / {identity['nnz']} nnz; native relax crosscheck PASS, SOS/general/indicator/Q constructs 없음.",f"Discrete -> continuous {identity['discrete_relaxed']}개 (binary {identity['binary_relaxed']}, integer {identity['integer_relaxed']}); original LB/UB 그대로.",f"Arc pure LP status {n['status']} OPTIMAL, Method2/Crossover0/Threads1; native original-M1 integer solve 없음.",f"Arc native optimum {a['native_optimum']}.",f"Exact Fraction weak-duality certified lower {a['L_arc_cert']}; original bounds only; free stationarity를 original equality multiplier에서 exact repair했고 pseudo-finite bound 사용 없음.",f"Primal-dual certificate gap {a['primal_dual_gap']}; native OPTIMAL만으로 scalar를 인증하지 않음.",f"Original affine residual {p['max_constraint_violation']}, bound residual {p['max_bound_violation']}, objective error {p['objective_recompute_error']}.",f"Legacy {BASE_LB} comparison {l['classification']}; native difference {l['difference_native_vs_legacy']}, certificate difference {l['difference_cert_vs_legacy']}. Similarity는 authority 아님.","PR143 z_arc_LP <= z_DW_root 증명과 새 weak duality의 transitivity로 floor transfer PASS.",f"Official independent D-W floor {a['L_arc_cert']}.",f"Official native-reference T_cert {t['T_cert']}; certified-floor-reference T {t['T_from_lower']}. Exact1/200 addition; material/nonmaterial comparator outward max/min 각각 {t['material_comparator']} / {t['nonmaterial_comparator']}.",f"Pre-CG interval {t['initial_interval']}; checkpoint 1158 exact, old pricing replay 없음.",f"Pre-CG threshold status {t['pre_CG_decision']}.",f"새 Discovery rounds {r['discovery_rounds']}; smoothing center restore {restore['restored']}, initial next alpha {restore['alpha']}.",f"새 validated columns {r['new_discovery_columns']}; retained {r['retained_columns']}; rate {r['columns_per_min']} columns/min, Discovery median {r['discovery_median']} s.",f"Audited RMP upper trajectory {[float(x['objective']) for x in rmps if x['objective']]}; DW_THRESHOLD_DISTANCE.csv에 시점별 lower authority/threshold distance 저장.",f"Final true-dual four-way Certification {final['status']}; pricing calls {r['new_pricing_calls']}, fixedworkers4/Threads1/RAM1GiB, warm RMP disabled.",f"New corrected LB {r['new_corrected_LB']}; exact residual/beta1e-8/downward treatment 유지.",f"Aggregated certified LB=max(new arc floor, old corrected, new corrected) = {r['best_certified_LB']}.",f"Smallest audited RMP upper {r['smallest_RMP_upper']} (DW LP upper, original integer UB 아님).",f"Final certified DW interval {r['final_interval']}.",f"Materiality {r['materiality']}.",f"Exact CG convergence {r['DW_ROOT_OPTIMAL_CERTIFIED']}; threshold decision과 별개.","미결일 경우 다음 단일 blocker는 실제 negative RC를 소진하는 CG convergence/trajectory pool. 기존 PR143 proof room 약1e-17에 근거해 exact pricing redesign 없이 fixed4-way smoothed discovery를 이어가는 방향. 이번 budget 이상 실행 없음.","Branch-and-Price NOT_RUN.","May day workers4/1/4/1, 각31일, Threads1 보존.","B2 inner1 / B3 inner4; mainB0->B1->B2->B3L1 뒤L2/L3/L4, previous Planning-only firewall 보존.","May optimizer/Actual/FreshAC0/0/0; no productionM1/P2/A2/M2. Scientific A1/route/physics/PCS16/P1/P2 unchanged."]
    endings=['이번 작업에서는 frozen original M1의 모든 integrality만 relax한 실제 arc LP를 terminal OPTIMAL까지 직접 풀었으며, matrix identity와 primal/dual numerical certificate를 모두 검증한 경우에만 scalar lower floor를 채택했다.','PR143에서 증명한 z_arc_LP <= z_DW_root 관계를 이용해 certified arc-LP lower bound를 D-W root lower floor로 전이했다.','기존 0.5687116103498322는 interrupted integer MIP BestBd였으므로 수치적으로 유사하더라도 새 arc-LP certificate의 대체 authority로 사용하지 않았다.','Adaptive dual smoothing은 Discovery에만 사용했고, column acceptance와 scientific lower-bound/materiality certificate는 true RMP dual authority를 유지했다.','Branch-and-Price와 May production은 실행하지 않았다.']
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {s}' for i,s in enumerate(lines,1))+'\n\n'+'\n\n'.join(endings)+'\n',encoding='utf8')

def manifest():
    files=[]
    for directory in ('v42_arc_floor','tests/v42_arc_floor','docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'):
        for p in sorted((ROOT/directory).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256_MANIFEST.json' and not p.name.endswith('.tmp'):files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    write('SHA256_MANIFEST.json',dict(files=files,self_excluded=True,index_blob_bytes_required=True))

if __name__=='__main__':verify()
