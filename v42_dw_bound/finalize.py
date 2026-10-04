"""Post-heavy read-only certificate reproduction and Korean publication."""
from .common import *
from fractions import Fraction as F
import re
import numpy as np
from v42_dw_resume.audit import prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs
from v42_dw_root.models import hash_column,subset
from v42_disjunctive.certificate import rational_bound,down

def distribution(values):
    a=np.array(values,float)
    return dict(count=len(a),median=float(np.median(a)) if len(a) else None,p95=float(np.percentile(a,95)) if len(a) else None,maximum=float(a.max()) if len(a) else None,total=float(a.sum()))
def speed():
    r=read(OUT/'DW_FINAL_RESULT.json');p=ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT);m=ledger('DW_RMP_LEDGER.csv',OUT)
    old=read(RESUME/'DW_RESUME_SPEED_AUDIT.json')['phases']['cumulative']
    optimal=[float(x['wall_seconds']) for x in p if x['classification'].startswith('OPTIMAL')];warm=[float(x['wall_seconds']) for x in m if x['warm']=='True']
    times=[dict(iteration=int(row['iteration']),seconds=float(row['wall_seconds'])+sum(float(v['wall_seconds']) for v in p if v['iteration']==row['iteration']),columns_added=sum(c['iteration']==row['iteration'] for c in ledger('DW_NEW_COLUMN_LEDGER.csv',OUT))) for row in m]
    value=dict(optimal_pricing_seconds=distribution(optimal),all_pricing_seconds=distribution([float(x['wall_seconds']) for x in p]),RMP_warm_seconds=distribution(warm),RMP_cold_seconds=distribution([float(x['wall_seconds']) for x in m if x['warm']=='False']),all_RMP_seconds=distribution([float(x['wall_seconds']) for x in m]),CG_iteration_seconds=distribution([v['seconds'] for v in times]),iteration_times=times,
       iterations_until_decision=r['new_RMP_solves'] if r['status']!='INCONCLUSIVE' else None,heavy_wall_until_decision=r['heavy_wall_until_decision'],build_seconds=r['build_seconds'],enclosure_audit_seconds=r['enclosure_audit_seconds'],elapsed_including_build_audit_seconds=r['elapsed_including_build_audit_seconds'],
       PR140_first_negative_pricing_seconds=old['pricing_solve_seconds'],PR140_RMP_seconds=old['RMP_solve_seconds'],PR140_total_RMP_calls=263,PR140_cumulative_heavy_seconds=3586.350867000059,
       new_policy='Full optimum/global-bound pricing; PR140 runtime had first-negative callback stops. Distinct endpoints are explicitly reported.',
       per_call_first_negative_observation=[dict(call=int(v['call']),first_negative_seconds=v['first_negative_observed_seconds'] or None,terminal_seconds=float(v['wall_seconds']),terminal_class=v['classification']) for v in p],
       no_overall_faster_claim_from_per_pricing_throughput=True)
    write('DW_BOUND_SPEED_AUDIT.json',value);return value
def test_result(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8');receipt=read(OUT/('PYTEST_'+label+'_RECEIPT.json'));matches=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert receipt['exit_code']==0 and matches and receipt['all_Gurobi_Threads_one'] and receipt['calls_nonoverlapping']
    return dict(PASS=True,passed=int(matches[-1][0]),seconds=float(matches[-1][1]),native_handled_traces=log.count('Windows fatal exception:'),raw_log_SHA=sha(OUT/(label+'_TEST.log')))
def verify():
    gate('verification');base_count=preserved();commit=verify_freeze();r=read(OUT/'DW_FINAL_RESULT.json')
    assert r['wall_budget_PASS'] and r['total_heavy_wall_seconds']<=3600 and r['old_pricing_replayed']==0 and not r['old_failed_dual_used']
    assert read(OUT/'DW_BOUND_SINGLE_THREAD_RESOURCE_SUMMARY.json')['sequential_policy_PASS']
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);mask=pure_binary_equalities(A,d);rows=ledger('DW_RMP_LEDGER.csv',OUT);points={};nonoptimal=[]
    for row in rows:
        if row['dual_SHA']:
            assert row['status']=='2'
            with np.load(OUT/row['point_file']) as z:
                check=corrected_rows(A,d,z['point'],False,mask);pi=z['pi'];alpha=z['alpha']
                assert check['PASS'] and hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==row['dual_SHA']
                assert hashlib.sha256(z['point'].tobytes()).hexdigest()==row['primal_SHA']
                points[row['dual_SHA']]=(pi,alpha)
        else:nonoptimal.append(dict(iteration=int(row['iteration']),native_status=int(row['status']),pricing_calls=0))
    prices=ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT);checks=[]
    for p in prices:
        receipt=read(OUT/p['receipt']);s=receipt['settings'];assert p['dual_SHA'] in points
        assert s['Threads']==1 and s['TimeLimit']<=300 and s['MIPGap']==s['MIPGapAbs']==0 and s['FeasibilityTol']==s['OptimalityTol']==s['IntFeasTol']==EPS
        assert not receipt['first_negative_termination'] and not receipt['callback_termination'] and receipt['full_original_domain'] and receipt['objective_transport_exact']
        pi,alpha=points[p['dual_SHA']];m=UNITS.index(p['MESS']);b=blocks[m]
        cost=b.d['objective']-b.B.T@pi
        assert hashlib.sha256(cost.tobytes()+np.array([-float(alpha[m])]).tobytes()).hexdigest()==p['objective_SHA']
        if receipt['point_file']:
            with np.load(OUT/receipt['point_file']) as z:physical=b.validate(z['x'],True);assert np.array_equal(z['axis'],b.columns)
            if p['valid_bound']=='True':assert physical['PASS']
        if p['valid_bound']=='True':assert int(p['native_status']) in (2,9) and p['ObjBound'] and receipt['ObjBound']==float(p['ObjBound'])
        checks.append(dict(call=int(p['call']),PASS=True,dual_SHA=p['dual_SHA'],classification=p['classification']))
    for c in ledger('DW_NEW_COLUMN_LEDGER.csv',OUT):
        m=UNITS.index(c['MESS']);b=blocks[m];p=next(v for v in prices if v['call']==c['pricing_call']);assert p['classification']=='OPTIMAL_NEGATIVE'
        with np.load(OUT/c['file']) as z:
            assert b.validate(z['x'],True)['PASS'] and np.array_equal(b.B@z['x'],z['a']) and hash_column(z['x'],z['a'],float(z['c']))==c['SHA256'] and np.array_equal(z['axis'],b.columns)
    globals_=np.flatnonzero(row_owner==-1);shared=np.flatnonzero(owner==-1);G=B[globals_][:,shared];gd=subset(e,globals_,shared,native);gd['constant']=e['constant']
    with np.load(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][shared];hi=z['upper'][shared]
    assert sha(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz')==read(OUT/'COORDINATE_ENCLOSURE_PROOF.json')['artifact_SHA']
    proofs=[]
    for file in sorted((OUT/'bound_certificates').glob('*.json')) if (OUT/'bound_certificates').exists() else []:
        cert=read(file)
        if not cert['certified']:continue
        pi,alpha=points[cert['dual_SHA']];proof=rational_bound(G,gd,pi,lo,hi);value=F(int(proof['exact_bound_numerator']),int(proof['exact_bound_denominator']))
        for m,pricefile in enumerate(cert['pricing_receipts']):
            p=read(OUT/pricefile);assert p['dual_SHA']==cert['dual_SHA'] and p['valid_bound'] and p['MESS']==UNITS[m]
            value+=F(float(alpha[m]))+min(F(0),F(down(F(float(p['ObjBound']))-F(EPS))))
        assert value==F(int(cert['exact_numerator']),int(cert['exact_denominator'])) and down(value)==cert['L_corr'] and cert['L_corr']<=cert['U_RMP']
        proofs.append(dict(file=file.relative_to(OUT).as_posix(),PASS=True,independent_global_rational_bound_reconstruction=True,lower=down(value),upper=cert['U_RMP']))
    if r['best_corrected_certified_LB'] is not None:assert max(p['lower'] for p in proofs)==r['best_corrected_certified_LB']
    tests={label:test_result(label) for label in ('SEMANTIC','FULL')}
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=ROOT,check=True)
    write('VERIFICATION.json',dict(PASS=True,base=BASE,base_files_preserved=base_count,execution_freeze_PASS=True,preopt_commit=commit,checkpoint1048_PASS=True,theorem_PASS=True,mixed_sense_native_PASS=True,
       new_original_RMP_points_reaudited=len(points),terminal_nonoptimal=nonoptimal,pricing_receipt_checks=checks,independent_certificate_reconstructions=proofs,tests=tests,single_worker_PASS=True,no_first_negative=True,no_heuristic=True,no_column_deletion=True,production=[0,0,0]))
def campaign():
    from v42_campaign.plan import build_plan
    plan=build_plan();assert plan==read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json') and len(plan['nodes'])==1458
    write('CAMPAIGN_ORCHESTRATOR_PRESERVATION.json',dict(PASS=True,unchanged_nodes=1458,plan_SHA=sha(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json'),main='B0->B1->B2->B3(L1), Planning then Actual/Fresh AC before next arm; then B3 L2/L3/L4 each Actual/Fresh AC',B3='A1->M1->A2->M2',next_Planning='previous Planning only',Actual_feedback_to_Planning=False))
    write('CAMPAIGN_NO_EXECUTION_RECEIPT.json',dict(optimizer=0,Actual=0,Fresh_AC=0,branch_and_price=False,production_M1=False,P2=False,A2=False,M2=False))
def report():
    r=read(OUT/'DW_FINAL_RESULT.json');v=read(OUT/'VERIFICATION.json');s=speed();campaign();pub=read(OUT/'PUBLICATION.json') if (OUT/'PUBLICATION.json').exists() else {}
    flags=dict(M1_BASE_MODEL_PRESERVED=True,DW_CHECKPOINT_COLUMNS=1048,DW_CORRECTED_DUAL_THEOREM_PASS=True,DW_DUAL_SIGN_PROOF_PASS=True,DW_PRICING_FULL_DOMAIN=True,DW_FIRST_NEGATIVE_EARLY_STOP=False,DW_HEURISTIC_PRICING=False,
      ARC_ROOT_LB=BASE_LB,DW_MATERIAL_THRESHOLD=T_MATERIAL,DW_BEST_CERTIFIED_CORRECTED_LB=r['best_corrected_certified_LB'],DW_BEST_RMP_UPPER_ON_DW_ROOT=r['smallest_RMP_upper'],DW_ROOT_INTERVAL_LOWER=r['final_interval'][0],DW_ROOT_INTERVAL_UPPER=r['final_interval'][1],DW_MATERIALITY=r['status'],DW_ROOT_OPTIMAL_CERTIFIED=r['DW_ROOT_OPTIMAL_CERTIFIED'],DW_ROOT_LB=r['DW_ROOT_LB'],DW_NEW_RMP_SOLVES=r['new_RMP_solves'],DW_NEW_PRICING_CALLS=r['new_pricing_calls'],DW_NEW_COLUMNS=r['new_columns'],DW_HEAVY_WALL_TO_CERTIFICATE=r['heavy_wall_until_decision'],BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,MAY_PRODUCTION_OPTIMIZER_CALLS=0,MAY_ACTUAL_CALLS=0,MAY_FRESH_AC_CALLS=0,PROBLEM13_FINAL_VALIDATED=False)
    write('FINAL_FLAGS.json',flags)
    lines=[f"Draft PR {pub.get('url','게시 전')}; 결과 commit {pub.get('result_commit','게시 전')}; semantic {v['tests']['SEMANTIC']['passed']} / full {v['tests']['FULL']['passed']} PASS. 최종 SHA/remote/clean은 최종 응답에서 확인.",
      f"PR140 scientific identity PASS; 원본 {v['base_files_preserved']}개 파일 바이트 보존.",'복원 checkpoint 4+1044=1048개. 과거 pricing 재실행 및 failed terminal dual 재사용 없음.',
      'Corrected-dual theorem PASS. 실제 lower bound는 exact global dual 잔차·box term·pricing1e-8 safety를 포함; native z_RMP를 lower bound에 직접 대입하지 않음.',
      'Bounded enumeration 10개 PASS: full trajectory/vertex Fraction 열거, negative/zero/positive/equality/free/transit/PCS/terminal SOC 및 convergence equality.',
      'Mixed-sense native Pi/convexity/ObjCon/ObjBound/RC proof PASS. 실제 RMP global/retained RC와 전체 원본 행 독립 감사 PASS.',
      f"첫 RMP 목적값 {r['first_RMP_objective']}; D-W root LP upper이며 original integer UB 아님.",f"첫 corrected certified LB {r['first_corrected_LB']}.",f"첫 D-W root interval {r['first_interval']}.",
      f"Pricing OPTIMAL {r['pricing_OPTIMAL']}회.",f"TIME_LIMIT_WITH_VALID_BOUND {r['pricing_TIME_LIMIT_WITH_VALID_BOUND']}회; incumbent column 추가 없음.",f"Pricing UNCERTIFIED {r['pricing_UNCERTIFIED']}회.",
      f"Optimal pricing median/p95/max: {s['optimal_pricing_seconds']}.",f"Warm RMP median/p95/max: {s['RMP_warm_seconds']}; cold: {s['RMP_cold_seconds']}.",
      f"새 RMP {r['new_RMP_solves']}회.",f"새 pricing {r['new_pricing_calls']}회.",f"새 validated most-negative columns {r['new_columns']}개.",
      f"Best corrected certified LB {r['best_corrected_certified_LB']}.",f"Smallest RMP upper {r['smallest_RMP_upper']}.",f"최종 D-W root interval {r['final_interval']}.",f"Arc root LB {BASE_LB}.",f"Certified improvement lower bound {r['certified_improvement_lower']}.",f"Material threshold {T_MATERIAL}.",
      f"Materiality {r['status']}; stop {r['stop_reason']}.",f"Exact CG convergence {r['DW_ROOT_OPTIMAL_CERTIFIED']}.",f"Converged certified D-W root LB {r['DW_ROOT_LB']}.",
      f"Decision heavy wall {r['heavy_wall_until_decision']}; 총 native optimize wall {r['total_heavy_wall_seconds']}/3600초; build/audit 포함 elapsed {r['elapsed_including_build_audit_seconds']}초.",
      f"PR140 RMP263회/3586.350867초 대비 새 RMP {r['new_RMP_solves']}회. First-negative와 terminal optimal/global-bound pricing runtime은 별도 비교; 전수렴 속도 향상 주장 없음.",
      'Branch-and-Price NOT_RUN; production M1/P2/A2/M2/Actual/Fresh AC NOT_RUN.',
      'May production optimizer/Actual/Fresh AC=0/0/0. 1458-node B3 계획 및 Actual feedback firewall 보존.']
    ending='''이번 작업에서는 pricing을 첫 negative reduced-cost trajectory에서 중단하지 않고 full-domain global bound까지 계산했다.

Restricted master objective는 full D-W root optimum의 upper bound이고, pricing global bounds를 이용한 corrected dual objective는 full D-W root optimum의 lower bound로 독립 검증했다.

따라서 full CG convergence 전에도 [L_corr, z_RMP]의 certified D-W root interval을 구성했다.

Top-K, route pool, Hamming restriction, site pruning, heuristic pricing은 사용하지 않았다.

Branch-and-Price, production M1, P2, A2, M2, Actual, Fresh AC 및 May production campaign은 실행하지 않았다.
'''
    if r['best_corrected_certified_LB'] is None:ending=ending.replace('full-domain global bound까지 계산했다.','full-domain global bound 확보를 시도했다.').replace('독립 검증했다.','검증하는 정책을 적용했으나 이번 실제 run의 lower bound는 미인증이다.').replace('certified D-W root interval을 구성했다.','certified interval 구성 조건을 검사했으나 이번 실제 run에서는 미인증이다.')
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+ending,encoding='utf8')
    (OUT/'PR_DESCRIPTION.md').write_text(f"""PR140 exhausted its root-CG budget before convergence, leaving its restricted objectives uncertified as global lower bounds. This new preregistered experiment restores all1048 validated columns and solves full-domain pricing to terminal OPTIMAL or a finite terminal global BestBd, without first-negative callback termination.

The corrected convexity-dual theorem is proved algebraically and by exhaustive rational bounded fixtures. Actual mixed-sense Pi, global-variable residual box terms, ObjCon and pricing ObjBound conventions are independently checked. Exact Fraction weak duality and fixed1e-8 pricing-bound safety yield a lower bound; an OPTIMAL, independently audited restricted master supplies the D-W LP upper under the registered numerical contract, never an original integer UB.

Result: {r['status']}; interval {r['final_interval']}; certified improvement lower {r['certified_improvement_lower']} versus arc root {BASE_LB}; threshold {T_MATERIAL}. New RMP {r['new_RMP_solves']}, pricing {r['new_pricing_calls']}, columns {r['new_columns']}; heavy optimize wall {r['total_heavy_wall_seconds']:.6f}/3600s. Materiality certificate stops the experiment immediately. Full CG convergence={r['DW_ROOT_OPTIMAL_CERTIFIED']}.

Validation: restored checkpoint and scientific identity PASS,10 exhaustive fixture cases and native mixed-sense/BestBd confirmation PASS, independent rational certificate reconstruction PASS; semantic {v['tests']['SEMANTIC']['passed']} / full pytest {v['tests']['FULL']['passed']} PASS with one worker and fresh actual ASCII basetemp. All PR140 files and failure history are preserved byte-for-byte. No Branch-and-Price, downstream or May production; optimizer/Actual/Fresh AC=0/0/0.
""",encoding='utf8')
def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in p.parts and p.suffix!='.pyc']
    for directory in ('v42_dw_bound','tests/v42_dw_bound'):paths += [p for p in (ROOT/directory).iterdir() if p.is_file() and (p.suffix=='.py' or p.name=='.gitattributes')]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],self_excluded=True,ignored_runtime_bytecode_excluded=True,base_byte_freeze_SHA=sha(OUT/'BASE_BYTE_FREEZE.json')))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()
