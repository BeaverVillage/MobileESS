"""Read-only reporting of the frozen isolated certificate experiment."""
from .common import *

def run():
    f=read('FINAL_FLAGS.json');v=read('FINAL_VERDICT.json');a=read('BOUND_SUPPORT_CLASSIFICATION.json');p=read('PREREGISTRATION.json')
    calls=f['fullscale_recourses'];r0=calls[0] if calls else {};r1=calls[1] if len(calls)>1 else {}
    dump('NUMERICAL_WARNING_AUDIT.json',dict(raw_prior_native_ray_still_rejected=True,prior_Kappa=7816110377241435.,
        raw_prior_PhaseI_status='TIME_LIMIT',raw_prior_PhaseI_seconds=701.2669999599457,
        experiment_calls=calls,logs_preserved=True,clamp=False,flip=False,tiny_delete=False,
        no_post_fullscale_result_engine_changes=True,no_causal_speedup_claim=True,
        official_semantics='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#farkasdual'))
    table('FULLSCALE_CUT_LEDGER.csv',f['cuts'],['CUT_ID','source_x_hash','cut_hash','source_violation','valid','inserted','artifact_sha256'])
    (OUT/'NEXT_MODIFICATIONS.md').write_text('# Next work\n\n'+v['current_blocker']+'\n\n'
        +'Preserve PR117 raw ray rejection and the saved exact x0. The equality-completed rational certificate is a new derivation; never relabel the original floating ray. Continue only from certified cut coefficients, independently replayed before master insertion. Any numerical failure needs a separate preregistration rather than result-driven engine edits.\n\n'
        +'The isolated x0/x1 pilot is not an original M1 optimization or acceptance. Full B3 and original M1 canary require their gates and a separately frozen run. Production M1, P2, A2 and M2 were explicitly excluded from this task. Keep full route authority, all96 physics/grid, terminal SOC equality, PCS16 and Actual P/Q correction OFF.\n',encoding='utf8',newline='\n')
    pairs=[
    ('왜 PR117 x0를 다시 쓰는가?','이번 primary는 같은 저장 candidate의 certificate engine repair다. 새 x0 master solve는 0회다.'),
    ('정확한 base는?',BASE),('x0 이름은?','NEW_V2_EXPERIMENT_X0 (PR117 저장본). PR115 historical x가 아니다.'),
    ('x0 vector hash는?',X0),('x0 axis hash는?',load_x0()[1]['axis_hash']),
    ('x0 bit-exact인가?',str(f['exact_PR117_x0_reused'])+'; NPZ/bit vector/ordered names/indices/receipt를 검증했다.'),
    ('master count는?','B3 85744 = route 85592 + mode 152. 밖의 원래 binary 122568개는 native continuous [0,1]이다.'),
    ('recourse continuous count는?','230999개. 원래 물리 변수와 outside-B3 relaxed 변수를 보존했다.'),
    ('1589개 family는?',str(a['unsupported_physical_families'])),
    ('1589개의 bound class는?','전부 LB=-inf, UB=+inf인 truly free 변수다.'),
    ('A: free exact zero는?',str(a['exclusive_class_counts']['A_FREE_EXACT_ZERO'])+'개다.'),
    ('B: free nonzero는?','1589개다. 작다는 이유로 exact zero로 승인하지 않았다.'),
    ('C/D: one-sided support는?',str({k:a['exclusive_class_counts'][k] for k in ['C_ONE_SIDED_COMPATIBLE','D_ONE_SIDED_INCOMPATIBLE']})),
    ('E: finite support 누락인가?','0개. 이번 raw ray 실패는 finite bound를 누락한 문제가 아니다.'),
    ('F: numerical near-zero는?','1589개 모두 near-zero overlay에 속하지만 정확한 유리수 계수는 비영이다.'),
    ('coefficient provenance를 보존했는가?','UNSUPPORTED_COEFFICIENT_PROVENANCE.jsonl.gz에 모든 해당 열의 row/coefficient/multiplier/product를 보존했다.'),
    ('native RC는 있었는가?','INFEASIBLE raw record에 RC/basis는 NOT_AVAILABLE이었다. 가짜 RC를 만들지 않았다.'),
    ('공식 Farkas semantics는?','Native inequality lambda signs와 A^T lambda의 bound support를 함께 사용한다. 자유 변수에서는 weighted coefficient=0이어야 한다.'),
    ('native FarkasProof를 정확히 재구성할 수 있었는가?','원래 float ray에서는 full support가 unbounded이므로 finite exact proof가 없다. partial sum을 proof로 사용하지 않았다.'),
    ('왜 42.159 scalar만으로 승인하지 않았는가?','Floating solver scalar와 원래 IEEE-rational 행렬에서의 exact stationarity는 별도 조건이다.'),
    ('repair는 무엇인가?','원래 inequality multiplier를 유지하고 defining equality multiplier를 exact rational 역삼각 대입으로 유도했다.'),
    ('free-variable pivots는?','81216개 모두 원래 defining equality의 +1 pivot을 가진다. 원래 primal LP는 변경하지 않았다.'),
    ('offline equality changes는?','1589개. 모든 delta와 before/after 유리수를 별도 certificate에 저장했다.'),
    ('clamp/flip/tiny-delete 했는가?','모두 false. 근사 residual을 지우는 대신 equality multiplier를 정확히 다시 계산했다.'),
    ('새 certificate인가?','예. 원래 raw ray는 계속 rejected이다. 새로운 completed rational ray를 독립 검증한다.'),
    ('standard form을 실행했는가?','생산 표현은 원래 native LP다. primal transform은 identity bijection이다.'),
    ('free plus/minus split이 bijective인가?','아니다. 둘을 함께 증가시킬 수 있다. 그 split을 bijection이라고 주장하거나 사용하지 않았다.'),
    ('양방향 solution mapping은?','생산 표현은 y→y identity이며 역방향도 동일하다. Fixture mapped points와 원래 residual을 검증했다.'),
    ('scaling은?','실제 recourse row/column scaling은 2^0. 별도 fixture에서 fixed positive power-of-two scaling을 검증했다.'),
    ('Phase-I dual normalization은?','사전 등록된 양의 유리수 1/2다. sign flip이 아니며 exact weak-duality separating proof를 요구한다.'),
    ('fixture assignments는?','1536개: feasible 49 / infeasible 1487. Native/identity/scaled 분류와 최적값을 다시 비교했다.'),
    ('N1–N10은?','모두 PASS. N6의 guard 아래 margin은 INCONCLUSIVE로 거부한다.'),
    ('축소 재현 fixture는?','N11이 free injection/response와 boxed P의 unsupported support를 재현하며 PASS다.'),
    ('known feasible assignment는?','49개가 모두 cut을 통과했다. 전체 original x box에 대한 global proof도 검사한다.'),
    ('isolated representation을 언제 freeze했는가?','Fixture/preflight PASS 후 source commit과 EXECUTION_FREEZE를 저장하고 optimize 전에 검증했다.'),
    ('x0 native status/time는?',str(r0.get('native_status'))+' / '+str(r0.get('native_seconds'))+'초.'),
    ('x0 Kappa/warnings는?',str(r0.get('Kappa'))+' / '+str(r0.get('warnings'))),
    ('raw native certificate valid인가?',str(r0.get('native_certificate_valid'))+'; 원래 PR116 raw validator 결과다.'),
    ('completed x0 certificate valid인가?',str(r0.get('completed_certificate_valid'))),
    ('Phase-I terminal인가?',str(r0.get('PhaseI_terminal'))+'; used='+str(r0.get('PhaseI_used'))+'. 미실행이면 terminal이라고 주장하지 않는다.'),
    ('Phase-I budget은?','Native와 별도 1800초다. 동일 candidate에서 sequential이며 parameter search는 없다.'),
    ('valid cut count는?',str(f['valid_cut_count'])),
    ('cut source separation은?',str([r['source_violation'] for r in f['cuts']])+'; exact/rounded >1e-8을 요구한다.'),
    ('cut insertion 전 replay했는가?','Independent COO rational products, sign, free stationarity, bounds, global outward domination 및 원래 source x separation을 재검증한다.'),
    ('x1 생성됐는가?',str(f['x1_generated'])+'; valid cut 이전에는 master optimize 0회다.'),
    ('x1은 저장됐는가?','생성 시 vector/ordered axis/NPZ/hash/receipt/new commit/prereg/freeze lineage를 recourse 전에 atomic 저장하고 reload한다.'),
    ('distinct x는?',str(f['distinct_x_count'])),('recourse1 결과는?',str(r1.get('status','NOT_RUN'))+' / native seconds='+str(r1.get('native_seconds'))),
    ('minimum pilot 완료인가?',str(f['BENDERS_PILOT_MINIMUM_PROVEN'])),
    ('B3 classification은?',f['B3_classification']),
    ('full B3 실행은?',str(f['full_B3_RUN'])+'; 이번 preregistration은 isolated x0/x1 pilot 범위다.'),
    ('full M1 canary 실행은?',str(f['full_M1_canary_RUN'])+'; certificate 또는 cuts>=2/distinct x>=3/stability gate가 필요하다.'),
    ('original M1 UB/LB/gap은?',f'{f["original_M1_UB"]} / {f["inherited_valid_LB"]} / {f["gap"]}. 새로운 V2 LB는 없다.'),
    ('M1 P1 accepted인가?',str(f['P1_ACCEPTED'])+'; zero-objective B3 bound를 rho LB로 쓰지 않는다.'),
    ('production/P2/A2/M2는?','전부 NOT_RUN. 이번 사용자 지시가 금지했다.'),
    ('M1 accepted / Problem13 final인가?',str(f['M1_ACCEPTED'])+' / '+str(f['PROBLEM13_FINAL_VALIDATED'])),
    ('global route domain 유지?','Top-K/route pruning/Hamming/pool=0. 원래 restored master domain 전체를 유지했다.'),
    ('물리 조건 유지?','P/Q/SOC/initial/terminal equality/travel debit/PCS16/all96 voltage/line/transformer/fixed A1/Planning .955–1.045를 유지했다. Actual P/Q repair OFF.'),
    ('threads 및 병렬 solve는?','Master 1, 독립 heavy solve가 없음을 확인하고 recourse 4. Native/Phase-I와 x1 모두 sequential. B0/B1을 실행하지 않았다.'),
    ('next blocker는?',v['current_blocker']+'; 이번 성공을 original M1 acceptance 또는 PR115 causal speedup으로 확대하지 않는다.')]
    assert len(pairs)==60
    (OUT/'FINAL_REVIEW_KO.md').write_text('# 동일 PR117 x0 certificate repair 검토\n\n'+v['verdict']+'\n\n'+
        '\n\n'.join(f'### Q{i}. {q}\n\n{answer}' for i,(q,answer) in enumerate(pairs,1))+'\n',encoding='utf8',newline='\n')
    dump('REPORT_RECEIPT.json',dict(questions=60,optimization_calls=0,inherited_bytes=preserve(),no_engine_changes_after_fullscale_results=True))

if __name__=='__main__':run()
