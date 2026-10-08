"""Resume the originally authorized next candidate after certified z=0 continuation."""
from .common import *
from .experiment import pair,budget

def main():
    first=read(REPORTS/'C01_CONTINUED_PAIR_RESULT.json');assert first['pair_certificate_PASS']
    ledger=budget();assert ledger['native_calls']==3 and ledger['remaining_Native_Runtime']>=960
    assert ledger['native_calls']+2<=6 and not ledger['unknown_unresolved_native_charge']
    candidate=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected'][1]
    assert candidate['variable_name']=='node_activity[MESS01,STA12,67]'
    prereg=REPORTS/'PHASE_B_RESUMPTION_PREREGISTRATION_KO.md'
    prereg.write_text(f'''# 원래 조건부 Phase B: C02 한 pair

사용자 추가 z=0 실행이 OPTIMAL 및 independent certificate PASS로 종료했다. 동일 scientific 모델의 기존 z=1 완료 certificate와 합친 C01 partition 증명이 완료되어 원래 "첫 후보 정상 인증 후 기존 선정 후보 최대2개 추가 검증" 조건을 충족한다. z=0 continuation은 그 단일 호출로 끝났고 자동 반복하지 않았다.

원래 frozen C02 node_activity[MESS01,STA12,67]의 0/1 LP 두 개만 독립 spawn Process/Env/Model로 동시에 실행한다. 원래 Threads=1/TimeLimit=480/Method=2/Crossover=0 및 모든 scientific 설정을 재사용한다. 이 경우 총 calls3→5, 실제 기존 Runtime {ledger['Native_Runtime_sum']:.9f}초+최대960초로 총2155.585초이며 원래2880초/6calls 상한을 늘리지 않는다. 각 Worker TimeLimit overshoot는 모두 합산한다.

C03은 pair를 실행하면 총7calls가 되어 상한을 넘으므로 NOT_RUN_CALL_BUDGET로 고정한다. 재실행·다른 후보·cuts·MILP·P2·downstream은 없다. 원래 과학 원본과 별도 May12 작업은 변경·중단하지 않는다. 수치 손실1e-4는 diagnostic-only이며 Native 완료 및 independent exact proof PASS가 pair 조건이다. 실패 또는 미완료이면 기존Global LB를 보존한다.
''',encoding='utf-8')
    freeze=read(REPORTS/'EXECUTION_SOURCE_FREEZE.json')
    assert all(sha(ROOT/'v42_group_branching'/n)==h for n,h in freeze['modules'].items())
    write(REPORTS/'PHASE_B_SOURCE_FREEZE.json',dict(PASS=True,controller_SHA256=sha(Path(__file__)),
        original_worker_SHA256=sha(ROOT/'v42_group_branching/worker.py'),
        selection_SHA256=sha(REPORTS/'SELECTED_BRANCH_VARIABLES.json'),preregistration_SHA256=sha(prereg),
        existing_Runtime=ledger['Native_Runtime_sum'],maximum_new_calls=2,TimeLimit=480,C03='NOT_RUN_CALL_BUDGET'))
    began=time.perf_counter();result=pair(dict(candidate,candidate='C02'));final=budget()
    assert final['native_calls']<=6 and final['Native_Runtime_sum']<=2880
    write(REPORTS/'PHASE_B_CONTROLLER_RESULT.json',dict(pairs=[result],budget=final,
        wall_seconds=time.perf_counter()-began,C03='NOT_RUN_CALL_BUDGET',automatic_further_experiments=False))
    print('CONDITIONAL_PHASE_B_END',result.get('pair_certificate_PASS'),final['native_calls'],flush=True)

if __name__=='__main__':main()
