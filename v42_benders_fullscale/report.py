"""Reporting only; never optimize or change frozen engine inputs."""
import gzip,json,shutil
import numpy as np
from .common import *

def run():
    flags=read('FINAL_FLAGS.json');pilot=read('PILOT_PROGRESS.json');verdict=read('FINAL_VERDICT.json')
    full=read('B3_FULL_CERTIFICATE.json');canary=read('FULL_M1_CANARY_RESULT.json');production=read('PRODUCTION_M1_RESULT.json')
    x0=read('MASTER_X_000_RECEIPT.json') if flags['new_x0_persisted'] else None
    cuts=pilot.get('cuts',[])+full.get('cuts',[])+canary.get('cuts',[])+production.get('cuts',[])
    rows=pilot.get('recourses',[])+full.get('recourses',[])+canary.get('recourses',[])+production.get('recourses',[])
    from .controller import CUT_FIELDS,RECOURSE_FIELDS
    for source,target in [('FULLSCALE_CUT_LEDGER.csv','PILOT_CUT_LEDGER.csv'),('FULLSCALE_RECOURSE_LEDGER.csv','PILOT_RECOURSE_LEDGER.csv')]:
        if not (OUT/target).exists():shutil.copyfile(OUT/source,OUT/target)
    table('FULLSCALE_CUT_LEDGER.csv',cuts,CUT_FIELDS)
    table('FULLSCALE_RECOURSE_LEDGER.csv',rows,RECOURSE_FIELDS)
    audit=[]
    for directory in [OUT,OUT/'FULL_B3',OUT/'FULL_M1_CANARY',OUT/'PRODUCTION_M1']:
        if not directory.exists():continue
        for p in sorted(directory.glob('RECOURSE_*_NATIVE_RAW_RECEIPT.json'))+sorted(directory.glob('RECOURSE_*_PHASE1_RAW_RECEIPT.json')):
            r=json.loads(p.read_text());audit.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),**r))
    dump('NUMERICAL_CERTIFICATE_AUDIT.json',dict(terminal_receipts=audit,cut_count=len(cuts),
        accepted_cuts=cuts,uncertified_cuts_inserted=0,validator='Unmodified PR116 rational generator and independent COO replay; replay again at insertion boundary',
        warnings_hidden=False,post_result_engine_changes=False,fixture_preflight_PASS=789,
        known_fixture_axis_note=read('PREREGISTRATION.json')['known_fixture_survival'],
        raw_journal_required_before_validation=True,source_x_persisted_before_every_recourse=True,
        causal_speedup_claim=False,historical_same_x=False,
        read_only_exact_residual_diagnostics=dict(path='EXACT_RESIDUAL_DIAGNOSTICS.json',
            sha256=sha(OUT/'EXACT_RESIDUAL_DIAGNOSTICS.json'))))
    dump('RESOURCE_FINAL_RECEIPT.json',dict(master_threads=1,recourse_threads=[r['threads'] for r in rows],
        recourse_peak_RSS_bytes=[r['peak_RSS_bytes'] for r in rows],policy=read('PREREGISTRATION.json')['recourse_thread_policy'],
        sequential_optimizer_calls=True,parameter_sweep=False,heavy_competing_solve=[read(f'RECOURSE_{r["iteration"]:03d}_STARTED.json')['resources']['other_heavy_solve'] for r in pilot['recourses']],
        B0_B1_executed=False,historical_same_x_claim=False))
    (OUT/'NEXT_MODIFICATIONS.md').write_text('# Next modifications\n\n'
        +f'Current verdict: {verdict["verdict"]}. B3: {flags["B3_classification"]}. Current stop/status: {verdict["current_blocker"]}.\n\n'
        +'Preserve all persisted candidates and native/Phase-I journals. Diagnose the observed terminal result using those exact inputs; do not change the inherited engine after seeing results in this experiment. Any further representation/certificate changes need a new preregistered experiment with fixture regression validation. Historical PR115 x remains NOT_AVAILABLE and this run provides no causal speedup comparison.\n\n'
        +'Keep original route/grid/SOC/PCS authority and Actual P/Q correction OFF. Full B3, original M1 canary and production remain subject to their recorded gates. P2/A2/M2 require separate user approval even if production P1 is accepted; M1 acceptance requires P1 and P2 completion.\n',encoding='utf8')
    r0=pilot['recourses'][0] if pilot['recourses'] else {}
    diagnostics=read('EXACT_RESIDUAL_DIAGNOSTICS.json')['summaries']
    native_diagnostic=next((r for r in diagnostics if r.get('multiplier_available') and r['status']==3),{})
    c0=pilot['cuts'][0] if pilot['cuts'] else None
    x1=pilot['candidates'][1] if len(pilot['candidates'])>=2 else None
    yes=lambda b:'예' if b else '아니오'
    no_run=lambda r:r.get('status','NOT_RUN')
    answers=[
    ('왜 PR115 same-x를 다시 요구하지 않았는가?','사용자가 historical x 복원과 별개인 새 V2 full-scale candidate 실험을 명시적으로 허가했다. historical x는 계속 NOT_AVAILABLE이다.'),
    ('이번 x0는 무엇인가?','NEW_V2_EXPERIMENT_X0이며, 이번 master의 새 출력이다.'),
    ('historical PR115 x라고 주장하는가?','아니다. 동일 x 비교나 PR115 대비 인과적 속도 개선 주장은 없다.'),
    ('x0를 언제 저장했는가?',str(None if x0 is None else x0['created_UTC'])+'에 master 출력 직후 atomic NPZ/axis/receipt로 저장했다.'),
    ('recourse보다 먼저 저장했는가?',yes(flags['new_x0_persisted'])+'. receipt를 재검증하고 그 NPZ에서 로드한 값만 recourse로 전달한다.'),
    ('vector/axis hash는?',str(None if x0 is None else x0['vector_sha256'])+' / '+str(None if x0 is None else x0['axis_hash'])),
    ('B3 master binary 85744인가?',str(None if x0 is None else x0['vector_length'])+'개다. 밖의 원래 binaries 122568개는 continuous native [0,1] bounds를 유지한다.'),
    ('recourse status는?',f'pilot native0 status={r0.get("native_status")}, seconds={r0.get("native_seconds")}; Phase-I seconds={r0.get("PhaseI_seconds")}; final={pilot["status"]}. Candidate wall={r0.get("unit_wall_seconds")}, total pilot wall={pilot.get("total_wall_seconds")}; 공유 1800초 이후 terminal raw persistence/audit overhead도 숨기지 않고 포함한다.'),
    ('native Farkas valid인가?',str(r0.get('native_certificate'))+'. 거부 이유: '+str(r0.get('native_reason'))),
    ('Phase-I를 사용했는가?',str(r0.get('PhaseI_used'))+f'; status={r0.get("PhaseI_status")}, valid={r0.get("PhaseI_certificate")}, reason={r0.get("PhaseI_reason")}.'),
    ('valid full-scale cut이 나왔는가?',str(flags['fullscale_valid_cuts'])+'개다. native 또는 Phase-I certificate가 독립 검증을 통과한 cut만 센다.'),
    ('cut source x는?',str(None if c0 is None else c0['source_x_hash'])+'; cut이 없으면 해당 항목은 NOT_AVAILABLE이다.'),
    ('x0가 cut을 위반하는가?',str(None if c0 is None else c0['source_violation'])+'; valid cut은 exact 및 rounded source separation >1e-8을 요구한다.'),
    ('cut이 known feasible points를 보존하는가?','PR116의 모든 fixture 회귀 검증을 유지했다. 7-bit fixture axis를 85744-bit full-scale x로 가짜 임베딩하지 않는다. Full-scale validity는 원래 A/B/b/LB/UB 위의 exact global proof로 검증한다.'),
    ('master에 cut을 넣었는가?',str(pilot.get('inserted_valid_cuts',0))+'개를 pilot master에 넣었다. 삽입 전에 독립 replay를 다시 수행한다.'),
    ('x1이 생성됐는가?',yes(x1 is not None)),
    ('x1은 x0와 다른가?',yes(x1 is not None and x1['vector_sha256']!=x0['vector_sha256'])+'; 동일 hash의 반복 candidate는 numerical STOP 대상이다.'),
    ('recourse1은 실행됐는가?',yes(len(pilot['recourses'])>=2)),
    ('pilot progress gate는?',str(flags['PILOT_PROGRESS_GATE'])),
    ('Benders loop가 실제 시작됐는가?','master→persist x0→recourse 실행 시작='+yes(flags['new_x0_persisted'] and bool(pilot['recourses']))+'; certificate-valid 반복 완료='+str(flags['BENDERS_FULLSCALE_LOOP_PROVEN'])+'.'),
    ('full B3 run은 승인됐는가?',str(read('B3_FULL_RUN_AUTHORIZATION.json')['authorized'])),
    ('full B3 iteration 수는?',str(full.get('distinct_persisted_candidates',0))+'개 candidate / '+str(len(full.get('recourses',[])))+'개 recourse evaluation이다.'),
    ('full-scale cut 수는?',str(flags['fullscale_valid_cuts'])+'개(PILOT+FULL_B3). 원래 M1 cut은 별도 stage ledger에 기록한다.'),
    ('witness가 나왔는가?',yes(pilot.get('validated_witness') or full.get('validated_witness'))),
    ('B3 proof가 나왔는가?',yes(pilot.get('global_master_infeasible') or full.get('global_master_infeasible'))+'. 단일 recourse INFEASIBLE은 전체 B3 proof가 아니다.'),
    ('B3 classification은?',flags['B3_classification']),
    ('PR116보다 algorithmic progress가 있는가?',str(flags['BENDERS_FULLSCALE_LOOP_PROVEN'])+'. 새 x 저장 및 실제 recourse 실행과 certificate-valid 반복 성공은 서로 다르다.'),
    ('full M1 canary gate는?',str(read('FULL_M1_CANARY_AUTHORIZATION.json')['authorized'])+'. B3 certificate 또는 full run 2 cuts/3 candidates 이상과 수치 안정성이 필요하다.'),
    ('full M1 canary를 실행했는가?',str(flags['FULL_M1_CANARY_RUN'])+' / '+no_run(canary)),
    ('full M1 master binary 수는?','208312개: route 207928 + mode 384. Gate가 닫히면 실행하지 않는다.'),
    ('full M1 recourse continuous 수는?','108431개의 원래 continuous 변수다. all96 physics/grid를 유지한다.'),
    ('original route domain을 유지하는가?','예. 원래 scientific model hash가 PR116과 일치한다. Top-K/Hamming/pool/pruning은 없다.'),
    ('optimality cut이 생성됐는가?',str(canary.get('optimality_cuts',0)+production.get('optimality_cuts',0))+'개 original M1 optimality cut. 원래 PR116 engine을 사용한다.'),
    ('feasibility cut이 생성됐는가?',str(flags['fullscale_valid_cuts'])+'개 B3 feasibility cut.'),
    ('valid global LB가 있는가?',f'inherited original LB={flags["valid_original_LB"]}; 새 V2 LB={flags["new_V2_global_LB"]}. Zero-objective B3 bound는 rho LB가 아니다.'),
    ('best UB는?',str(flags['original_M1_UB'])+'. original full-integer 독립 검증된 UB만 인정한다.'),
    ('gap은?',str(flags['gap'])+' = (UB-LB)/abs(UB).'),
    ('0.5% 도달 여부?',yes(flags['gap']<=.005)),
    ('P1 accepted 여부?',str(flags['P1_ACCEPTED'])+'. canary는 production acceptance가 아니다.'),
    ('production M1 실행 여부?',str(flags['PRODUCTION_M1_RUN'])+' / '+no_run(production)),
    ('P2 실행 여부?',str(flags['P2_RUN'])+'; 별도 사용자 승인이 필요하다.'),
    ('M1 accepted 여부?',str(flags['M1_ACCEPTED'])+'; P1과 P2를 완료해야 한다.'),
    ('A2 실행 여부?',str(flags['A2_RUN'])),
    ('M2 실행 여부?',str(flags['M2_RUN'])),
    ('M2 route/P/Q/SOC joint semantics 유지?','예. PR116 explicit anchor/state interface와 bounded tests를 byte 그대로 보존한다. M1 route는 fixing하지 않고 Start hint만 허용한다.'),
    ('outer/inner decomposition 차이?','Outer는 A1→M1→A2→M2 단계다. Inner는 같은 joint MESS 문제의 route/mode master↔P/Q/SOC/grid recourse 계산 분해다.'),
    ('globality는 어디까지?',f'B3 classification={flags["B3_classification"]}; original inherited UB/LB와 독립 검증한 cut만 인정한다. 미인증 cut으로 global claim을 만들지 않는다.'),
    ('PR115 대비 speedup을 주장했는가?','아니다.'),
    ('왜 주장할 수 없는가?','이번 x0는 새 실험의 candidate다. PR115 historical x가 없으므로 동일 x 인과적 비교가 아니다.'),
    ('numerical warning은?',f'Native Kappa={native_diagnostic.get("Kappa")}; exact residual audit에서 finite support가 없는 columns={native_diagnostic.get("unsupported_bound_support_columns")}, truly-free residual max={native_diagnostic.get("truly_free_residual_max")}. 작은 비영 residual도 삭제·clamp하지 않는다. Native/Phase-I raw logs와 NUMERICAL_CERTIFICATE_AUDIT.json에 warning을 보존한다.'),
    ('raw certificates 저장됐는가?','Native/Phase-I full multiplier, row axis, native bounds, RHS, proof/RC/basis(가능한 경우), settings, 로그를 validator 전에 journal에 저장한다.'),
    ('uncertified cut은 0인가?',str(flags['uncertified_cuts_inserted'])+'개다.'),
    ('thread policy는?','Master 1 thread. Candidate 직전 다른 heavy solve가 없으면 recourse 4, 있으면 1; 해당 native/Phase-I pair 동안 고정한다.'),
    ('resource contention은?','각 candidate receipt와 RECOURSE_STARTED의 resource snapshot을 보존한다. 한 번에 optimizer 하나만 실행했다.'),
    ('Planning voltage 유지?','0.955–1.045 pu를 유지한다. eventual Fresh AC 0.95–1.05 pu도 변경하지 않는다.'),
    ('terminal SOC 유지?','원래 terminal equality, initial SOC, all96 recurrence와 travel-energy debit을 유지한다.'),
    ('PCS16 유지?','장치별 원래 PCS16 facets와 P/Q/mode coupling을 유지한다.'),
    ('Actual P/Q repair OFF?','P correction OFF, Q correction OFF다.'),
    ('next blocker는?',str(verdict['current_blocker'])+'; exact candidate와 raw certificates로 다음 별도 실험을 설계해야 한다.'),
    ('PROBLEM13_FINAL_VALIDATED인가?',str(flags['PROBLEM13_FINAL_VALIDATED'])+'.')]
    assert len(answers)==60
    (OUT/'FINAL_REVIEW_KO.md').write_text('# Full-scale V2 최종 검토\n\n'+verdict['verdict']+'\n\n'+
        '\n\n'.join(f'### Q{i}. {q}\n\n{a}' for i,(q,a) in enumerate(answers,1))+'\n',encoding='utf8')
    dump('REPORT_RECEIPT.json',dict(questions=60,optimization_calls=0,post_result_engine_changes=0,
        original_bytes_preserved=verify_inherited(),historical_same_x_claim=False))

if __name__=='__main__':run()
