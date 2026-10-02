"""Honest terminal reporting: same-x absence closes every large-run gate."""
import copy,csv,gzip,json
from collections import Counter
import numpy as np
import gurobipy as gp
from .common import *
from .gates import isolated_gate,progress_gate,production_gate,classify_b3

def numerical_audit():
    from .representation import from_model
    from v42_benders.fixtures import build,CASES
    from .independent import verify
    from .certificates import create
    from v42_benders.certificates import Uncertifiable
    records=[];warnings=[];env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    try:
        for case in CASES:
            m=build(env,case);n=from_model(m)
            accepted={(a['assignment'],'phase1' if a['kind']=='phase1' else 'native') for a in read('NATIVE_FARKAS_CERTIFICATE_AUDIT.json')['records'] if a['case']==case}
            accepted.update((a['assignment'],'phase1') for a in read('PHASE1_CERTIFICATE_AUDIT.json')['records'] if a['case']==case)
            for path in ['native','phase1']:
                with gzip.open(OUT/'RAW_FINAL'/case/path/'raw_certificates.jsonl.gz','rt') as f:raws=[json.loads(l) for l in f]
                for idx,r in enumerate(raws):
                    warnings.extend(dict(case=case,assignment=idx,path=path,warning=w) for w in r['warnings'])
                    w=np.asarray(r['multipliers']);a=np.asarray(n.A.T@w);x=np.array(r['source_x'])
                    sign_bad=np.sum(w[n.sense=='<']*(1 if r['status']==3 else -1)<0)+np.sum(w[n.sense=='>']*(1 if r['status']==3 else -1)>0)
                    rc=None if r['reduced_costs'] is None else np.array(r['reduced_costs'])[:len(n.yi)]
                    dual=None if rc is None else float(np.max(abs((np.zeros(len(n.yi)) if path=='phase1' else n.c)-a-rc),initial=0))
                    primal=None if r['primal'] is None else (n.residual(x,np.array(r['primal'])[:len(n.yi)]) if path=='native' else None)
                    records.append(dict(case=case,assignment=idx,path=path,status=r['status'],Kappa=r['Kappa'],
                        primal_residual=primal,dual_reduced_cost_residual=dual,sign_violation_count=int(sign_bad),
                        native_weighted_column_max=float(np.max(abs(a),initial=0)) if r['status']==3 else None,
                        FarkasProof=r['farkas_proof'],PhaseI_optimum=r['objective'] if path=='phase1' else None,
                        raw_certificate_sha256=r['vector_sha256'],independent_cut_certified=(idx,path) in accepted,
                        bound_completed_stationarity=0. if (idx,path) in accepted else None))
            m.dispose()
        # N10 explicitly mutates the certificate from the N10 model, without optimization.
        from .adversarial import build as nb
        m=nb(env,10);n=from_model(m);d=OUT/'NUMERICAL_RAW_FINAL/N10/phase1'
        with gzip.open(d/'raw_certificates.jsonl.gz','rt') as f:r=json.loads(f.readline())
        import hashlib
        payload=json.dumps(r,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
        r['persistence']=dict(journal=str(d/'raw_certificates.jsonl.gz'),record=1,payload_sha256=hashlib.sha256(payload).hexdigest(),persisted_before_validation=True,raw_log=str(d/'raw_solver.log'))
        c=create(n,r,'phase1');assert verify(n,c)['PASS'];bad=copy.deepcopy(c);bad['raw']['multipliers']=[-v for v in bad['raw']['multipliers']]
        rejected=False
        try:verify(n,bad)
        except Uncertifiable as e:rejected=True;reason=str(e)
        assert rejected
        dump('N10_SIGN_MUTATION_REPLAY.json',dict(PASS=True,rejected=True,reason=reason,original_cut_hash=c['record']['cut_hash'],
            raw_vector_sha256=c['record']['raw_vector_sha256'],optimization_calls=0,mutated_input=bad['raw']['multipliers']))
        m.dispose()
    finally:env.dispose()
    table('NUMERICAL_RESIDUAL_CENSUS.csv',records,list(records[0]))
    native=read('NATIVE_FARKAS_CERTIFICATE_AUDIT.json')
    dump('NUMERICAL_WARNING_AUDIT.json',dict(full_scale_V2_status='NOT_RUN',full_scale_V2_Kappa=None,
        inherited_V1_Kappa=5.11554e15,V2_fixture_warnings=warnings,
        rejected_native_count=len(native['rejected_native']),reasons=dict(Counter(r['reason'] for r in native['rejected_native'])),
        stationarity_interpretation='Native weighted columns need not be zero. Existing finite bounds complete the certificate; exact residual after bound completion is zero for accepted cuts. No small coefficients are deleted.',
        native_reconstruction_vs_FarkasProof_required=True,bound_support_residual_for_accepted=0,
        strict_margin_guard=1e-8,N6='Solver tolerance may classify the 5e-9 infeasibility as feasible; no exact certificate or production acceptance is claimed.',
        speedup_claim=False,causal_Kappa_claim=False,full_scale_certificate_claim=False))

def run():
    fixture=read('V2_FIXTURE_EXACTNESS.json');first=read('PR115_FIRST_X_RECEIPT.json')
    assert fixture['PASS'] and fixture['agreement']==1536 and not first['restored']
    reason='PR115_FIRST_X_NOT_PERSISTED; exact same candidate cannot be reconstructed from available evidence. User forbids substituting a new master candidate.'
    isolated=dict(status='NOT_RUN',same_x_verified=False,independent_valid_cut=False,independent_physics_witness=False,
        reason=reason,build_seconds=None,presolve_seconds=None,LP_seconds=None,iterations=None,Kappa=None,
        peak_RSS_bytes=None,Farkas_residual=None,certificate_valid=None,PhaseI_fallback_used=False,
        first_x_receipt_sha256=sha(OUT/'PR115_FIRST_X_RECEIPT.json'))
    assert not isolated_gate(first,fixture,isolated)
    dump('SAME_X_V2_RECOURSE_RESULT.json',isolated)
    table('SAME_X_NUMERICAL_COMPARISON.csv',[
        dict(version='V1_PR115',status='INFEASIBLE',LP_seconds=1433.5810000896454,Kappa=5.11554e15,certificate='REJECTED_MULTIPLIER_SIGN',cut_valid=False,same_x='source vector unavailable'),
        dict(version='V2',status='NOT_RUN',LP_seconds=None,Kappa=None,certificate='NOT_RUN',cut_valid=None,same_x='UNRECOVERABLE')],
        ['version','status','LP_seconds','Kappa','certificate','cut_valid','same_x'])
    dump('B3_V2_AUTHORIZATION.json',dict(authorized=False,status='NOT_RUN',isolated_gate_PASS=False,reason=reason,
        fixture_PASS=True,budget_seconds=1800,threshold=.5732125039436496,master_binaries=85744,
        source_receipts=[sha(OUT/'V2_FIXTURE_EXACTNESS.json'),sha(OUT/'SAME_X_V2_RECOURSE_RESULT.json')]))
    b3=dict(status='NOT_RUN',classification=classify_b3(),reason=reason,iterations=0,independent_valid_cuts=0,
        native_Farkas_cuts=0,PhaseI_cuts=0,validated_witness=False,global_master_infeasible=False,
        numerical_contradiction=False,uncertified_cuts_used=0,progress_gate_PASS=False)
    assert not progress_gate(False,b3);dump('B3_V2_CERTIFICATE.json',b3)
    table('B3_V2_PROGRESS.csv',[],['iteration','master_status','master_seconds','recourse_status','recourse_seconds','cut_hash','reason'])
    table('B3_V2_CUT_LEDGER.csv',[],['iteration','kind','cut_hash','source_x_hash','source_hash','raw_vector_sha256','independent_valid'])
    table('B3_V2_RECOURSE_LEDGER.csv',[],['iteration','status','seconds','Kappa','certificate_valid','reason'])
    dump('FULL_M1_CANARY_AUTHORIZATION.json',dict(authorized=False,status='NOT_RUN',reason='B3_PROGRESS_GATE_NOT_PASS',
        budget_seconds=600,original_master_binaries=208312,route_binaries=207928,mode_binaries=384,
        original_continuous=108431,source_sha256=sha(OUT/'B3_V2_CERTIFICATE.json')))
    canary=dict(status='NOT_RUN',reason='B3_PROGRESS_GATE_NOT_PASS',cut_validity=False,independent_original_UB=False,
        global_LB_valid=False,numerical_stability=None,upper=None,lower=None,gap=None,uncertified_cuts_used=0)
    assert not production_gate(canary);dump('FULL_M1_CANARY_RESULT.json',canary)
    dump('M1_PRODUCTION_AUTHORIZATION.json',dict(authorized=False,status='NOT_RUN',reason='CANARY_NOT_RUN',budget_seconds=1800,
        meaningful_progress_definition=read('PREREGISTRATION.json')['production_progress'],source_sha256=sha(OUT/'FULL_M1_CANARY_RESULT.json')))
    flags=dict(P1_ACCEPTED=False,M1_ACCEPTED=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,PROBLEM13_FINAL_VALIDATED=False,
        Actual_P_correction=False,Actual_Q_correction=False,B0_B1_RUN=False,full_scale_valid_cuts=0,
        B3_classification='B3_INCONCLUSIVE',full_M1_canary_run=False,production_P1_RUN=False,
        original_M1_UB=.5912812634331275,inherited_valid_original_LB=.5722125039436496,
        inherited_gap=(.5912812634331275-.5722125039436496)/.5912812634331275,
        new_V2_global_LB=None,PhaseI_diagnostic_used=True,PhaseI_full_scale_fallback_used=False,
        downstream_separate_user_approval_required=True)
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(verdict='INCONCLUSIVE',fixture_exactness='PASS_1536_OF_1536',
        numerical_N1_N10='PASS_GUARDS_AND_VALID_CERTIFICATES; N6_INCONCLUSIVE_NEAR_ZERO',
        same_x='NOT_RUN_UNRECOVERABLE_X',B3='B3_INCONCLUSIVE',P1_ACCEPTED=False,M1_ACCEPTED=False,
        PROBLEM13_FINAL_VALIDATED=False,current_blocker=reason,performance_speedup_claim=False))
    numerical_audit()
    (OUT/'NEXT_MODIFICATIONS.md').write_text('''# Next steps
The blocking artifact is PR115's first B3 x vector with its original ordered axis and authentic provenance. Neither the raw master log nor a different feasible incumbent identifies those 85,744 bits. Do not rerun the master and describe its output as the historical same x.
If an authentic archived x is recovered, verify exact bytes/axis/hash, then perform the preregistered isolated native recourse (Phase-I only after rejected native certificate). Otherwise a differently scoped benchmark using a new, explicitly labelled candidate requires a new user scope correction; the present same-x gate remains closed.
Only isolated PASS authorizes full B3; only real B3 progress authorizes full M1 canary. Keep downstream P2/A2/M2 behind separate user approval. Investigate native FarkasProof discrepancies with the preserved raw vectors and original bounds without changing sign or weakening validators. No cause of full-scale Kappa has been identified.
''',encoding='utf8')
    questions=[
    ('PR115에서 정확히 무엇이 실패했는가?','첫 B3 recourse가 1433.581초 뒤 INFEASIBLE이었지만 multiplier sign validator에서 거부되어 cut 0개로 STOP했다.'),
    ('Benders 자체가 틀린 것인가?','아니다. 분해의 fixture exactness는 유지된다. 대규모 numerical certificate는 아직 입증되지 않았다.'),
    ('Kappa 5.1e15의 의미는?','PR115 solver의 매우 큰 condition 경고다. cut의 유효성 또는 전체 B3 infeasibility 증명이 아니다.'),
    ('원인을 단정했는가?','아니다. 행 수, bounds 확장, equality 복제와 dynamic range를 측정했고 단독 인과 원인은 미확인이다.'),
    ('V1 canonical representation은 무엇인가?','모든 row를 <=로 바꾸고 equality를 양방향 복제하며 finite continuous bounds를 별도 row로 표현한다. y는 free다.'),
    ('V2 native-bound representation은 무엇인가?','원래 <=, >=, = sense와 native LB/UB를 그대로 사용한다. 원래 모든 행을 유지한다.'),
    ('equality duplication을 왜 줄이는가?','동일 equality의 원래 표현을 보존하고 추가 representation 행을 피한다. 실측 속도 개선은 주장하지 않는다.'),
    ('native bounds를 왜 유지하는가?','scientific bounds를 API LB/UB로 보존하면서 bound contribution을 certificate에서 직접 검증한다.'),
    ('feasible set은 동일한가?','fixture 1536개 전수 classification과 actual full/B3 matrix inverse audit가 통과했다.'),
    ('scientific physics는 바뀌었는가?','아니다. 기존 tracked 1615개 파일의 bytes와 full route/grid/SOC authority를 보존한다.'),
    ('Farkas ray raw vector를 저장하는가?','검증 전에 gzip journal에 full multiplier, RHS, status, proof, axis/bounds hash와 로그를 저장한다. 거부된 입력도 보존한다.'),
    ('sign convention은 어떻게 검증하는가?','Farkas는 <=에 nonnegative, >=에 nonpositive, equality unrestricted다. minimization Pi는 반대 inequality sign이다.'),
    ('variable bounds는 certificate에 어떻게 반영되는가?','weighted y coefficient의 양수는 LB, 음수는 UB를 사용해 최소 bound support를 exact rational로 계산한다.'),
    ('clamp/flip을 했는가?','하지 않았다. 작은 multiplier 삭제, ray sign flip, invented bound도 없다.'),
    ('Phase-I는 physics relaxation인가?','certificate auxiliary LP에만 artificial violation variable을 추가한다.'),
    ('왜 production relaxation이 아닌가?','원래 recourse와 witness에는 artificial variable이 전혀 없고 양의 auxiliary slack을 feasible M1으로 인정하지 않는다.'),
    ('Phase-I optimum=0 의미는?','수학적으로 원래 feasible recourse다. numerical near-zero에서는 원래 primal rows와 bounds를 따로 확인한다.'),
    ('Phase-I optimum>0 의미는?','infeasible candidate다. independently validated separating dual cut 없이는 master에 아무것도 추가하지 않는다.'),
    ('Phase-I cut은 valid한가?','fixture에서 1487개 dual feasibility cut을 exact bound support와 independent COO rational replay로 검증했다.'),
    ('fixture 1536개 결과는?','1536/1536 classification agreement, feasible 49개, infeasible 1487개다.'),
    ('V1/V2 classification은 일치하는가?','전부 일치한다. feasible assignment는 모든 검증 cut에서 살아남는다.'),
    ('monolithic과 일치하는가?','12개 case 모두 enumeration optimum, monolithic MILP와 V2 Benders optimum 또는 infeasibility가 일치한다.'),
    ('numerical adversarial 결과는?','N1–N10 guard 검증이 통과했다. N6의 5e-9 margin은 인증하지 않고 INCONCLUSIVE_NEAR_ZERO로 보존한다.'),
    ('same PR115 master candidate를 재사용했는가?','아니다. PR115는 첫 x를 저장하지 않았으며 available evidence에서 복원할 수 없어 NOT_RUN이다.'),
    ('왜 동일 candidate 비교가 필요한가?','representation 효과를 x 변화와 분리하려면 historical exact x가 필요하다. 새 master로 대체하지 않았다.'),
    ('V1 recourse 1433.581s와 비교 결과는?','V1 1433.581초, V2 NOT_RUN이다. 속도 비율을 계산할 근거가 없다.'),
    ('V2 terminal status는?','same-x 대규모 LP는 NOT_RUN이다. fixture terminal status와 혼동하지 않는다.'),
    ('V2 Kappa warning은?','대규모 V2 값은 없다. fixture 경고와 Kappa는 별도 residual census에 기록했다.'),
    ('valid certificate를 얻었는가?','bounded fixtures에서 얻었다. native Farkas 1248개와 optimality 49개; 거부 native 239개는 validated Phase-I로 대체했다.'),
    ('full-scale cut을 만들었는가?','0개다. fixture cut은 대규모 B3 cut으로 세지 않는다.'),
    ('B3 iteration은 몇 회인가?','V2 full B3는 0회다. PR115의 1회 기록은 보존한다.'),
    ('feasibility cut은 몇 개인가?','V2 full-scale 0개다. fixture 분류용 certificate는 별도 audit에 기록했다.'),
    ('Phase-I cut은 몇 개인가?','diagnostic fixture 1487개, full-scale 0개다. V2 fixture loop에서 fallback 호출 4회가 있었다.'),
    ('B3 witness가 나왔는가?','V2 full-scale witness는 없다.'),
    ('B3 proof가 나왔는가?','V2 full-scale proof는 없다. inherited solver INFEASIBLE은 전체 B3 proof가 아니다.'),
    ('B3 classification은?','B3_INCONCLUSIVE다. same-x gate가 닫혀 새 decomposition을 실행하지 않았다.'),
    ('PR115보다 progress가 있는가?','representation, raw persistence, bounded certificate 검증은 개선했다. full-scale algorithmic progress gate는 FAIL이다.'),
    ('full M1 canary를 실행했는가?','NOT_RUN이다. 유효한 full-scale B3 cut/witness/proof가 없다.'),
    ('Full M1 UB는?','inherited independently validated original-M1 UB 0.5912812634331275를 보존한다. 새 V2 UB는 없다.'),
    ('Full M1 LB는?','inherited original S2 LB 0.5722125039436496를 보존한다. 새 V2 master LB는 없다.'),
    ('gap은?','inherited (UB-LB)/abs(UB)=0.03224989640084286, 약 3.22499%다.'),
    ('0.5%에 도달했는가?','아니다. 새 global bound progress가 없다.'),
    ('P1 accepted인가?','false다.'),
    ('M1 accepted인가?','M1_ACCEPTED=false다.'),
    ('P2를 실행했는가?','false다. P1 수락 후에도 별도 사용자 승인이 필요하다.'),
    ('A2/M2를 실행했는가?','둘 다 false다. 새 downstream 자동 실행은 없다.'),
    ('M2 joint decision interface는 보존되는가?','기존 explicit anchor/state interface와 bounded tests를 byte 그대로 보존했다. route/mode/P/Q/SOC joint semantics는 변하지 않는다.'),
    ('outer/inner decomposition 차이는?','outer A1→M1→A2→M2는 단계 구조다. inner M-stage master↔recourse는 같은 joint MESS 문제의 계산 분해다.'),
    ('globality는 어디까지 주장 가능한가?','bounded fixtures의 exact equivalence와 inherited original UB/LB만이다. 대규모 V2 optimality는 주장하지 않는다.'),
    ('original route domain은 완전한가?','full 207928 route binaries와 384 modes를 보존한다. Top-K/Hamming/pool/pruning은 없다.'),
    ('Planning voltage는 그대로인가?','0.955–1.045 pu다. eventual Fresh AC 0.95–1.05 pu도 바꾸지 않았다.'),
    ('terminal SOC는 그대로인가?','all96 recurrence, initial SOC와 terminal equality를 그대로 유지한다.'),
    ('PCS16은 그대로인가?','각 장치의 원래 PCS16 linear facets와 P/Q coupling을 유지한다.'),
    ('Actual P/Q repair는 OFF인가?','P correction OFF, Q correction OFF다. clipping/repair 실행도 없다.'),
    ('uncertified cut이 사용됐는가?','0개다. insertion boundary에서 independent replay를 다시 수행한다.'),
    ('solver numerical warning을 성공으로 숨겼는가?','아니다. raw warnings, rejected proof, 개발 중 중단 기록과 numerical residual census를 보존한다.'),
    ('performance speedup을 주장할 근거가 있는가?','없다. matrix build 시간은 same-x LP solve 시간 비교가 아니다.'),
    ('current blocker는 무엇인가?','PR115 첫 B3 x vector가 저장되지 않아 historical candidate equivalence를 입증할 수 없다.'),
    ('다음 단계는?','authentic x archive를 복구하거나 별도 사용자 scope correction으로 새 candidate 실험을 정의해야 한다. 현재 gate는 닫힌 상태다.'),
    ('PROBLEM13_FINAL_VALIDATED인가?','false다. 최종 verdict는 INCONCLUSIVE다.')]
    assert len(questions)==60
    (OUT/'FINAL_REVIEW_KO.md').write_text('# V2 native recourse 최종 검토\n\n최종 판정: INCONCLUSIVE. Exact base PR115를 보존했다.\n\n'+'\n\n'.join(f'### Q{i}. {q}\n\n{a}' for i,(q,a) in enumerate(questions,1))+'\n',encoding='utf8')
    dump('REPORT_GENERATION_RECEIPT.json',dict(questions=60,optimization_calls=0,
        original_bytes_preserved=all(sha(ROOT/r['path'])==r['sha256'] for r in read('PR115_BASE_RECEIPT.json')['files'])))

if __name__=='__main__':run()
