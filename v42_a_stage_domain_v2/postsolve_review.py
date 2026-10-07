"""Read-only audit of every internal native barrier attempt after diagnostics.

One optimize call may internally retry barrier. Preserve the raw first-match
telemetry; supplement it with all printed attempts and conservative maxima.
No optimizer, parameters, scientific domains or archived receipts are changed.
"""
import csv,re
from .fast_prepare import OUT,OLD
from v42_pr134_b1.common import atomic,read,record,table


def internal_attempts(text):
    result=[];current=None
    for number,line in enumerate(text.splitlines(),1):
        order=re.search(r'Ordering time:\s*([\d.]+)s',line)
        if order:
            current=dict(ordering_seconds=float(order[1]),ordering_log_line=number)
            result.append(current)
        if current is None:continue
        factor=re.search(r'Factor NZ\s*:\s*([\deE+.-]+) \(roughly ([\d.]+) (MB|GB)',line)
        if factor:
            current.update(factor_nnz=float(factor[1]),factor_memory_printed=float(factor[2]),
                factor_memory_unit=factor[3],factor_memory_GB=float(factor[2])/(1000 if factor[3]=='MB' else 1),factor_log_line=number)
        operations=re.search(r'Factor Ops\s*:\s*([\deE+.-]+)',line)
        if operations:current.update(factor_operations=float(operations[1]),factor_operations_log_line=number)
        barrier=re.search(r'Barrier (?:performed|solved model in) (\d+) iterations (?:in|and) ([\d.]+) seconds',line)
        if barrier:
            current.update(barrier_iterations=int(barrier[1]),solver_reported_elapsed_seconds=float(barrier[2]),barrier_log_line=number)
    return result


def supplement():
    path=OUT/'MAY19_CANARY/rho/LP_0000/NATIVE_SOLVER.log'
    attempts=internal_attempts(path.read_text(encoding='utf-8-sig'))
    result=read(path.parent/'NATIVE_RESULT.json');canary=read(OUT/'MAY19_CANARY/FAST_RESULT.json')
    receipt=dict(PASS=True,source_log=record(path),source_native_receipt=record(path.parent/'NATIVE_RESULT.json'),
        attempts=attempts,native_optimize_calls=1,internal_attempt_count=len(attempts),
        max_ordering_seconds=max(a['ordering_seconds'] for a in attempts),
        max_factor_nnz=max(a['factor_nnz'] for a in attempts),
        max_factor_memory_GB=max(a['factor_memory_GB'] for a in attempts),
        printed_barrier_iteration_total=sum(a.get('barrier_iterations',0) for a in attempts),
        native_reported_barrier_iterations=result['fill_in']['native_barrier_iterations'],
        actual_native_seconds=result['native_seconds'],Work=result['Work'],
        peak_observed_RSS_bytes=result['fill_in']['peak_RSS_bytes'],
        native_status=result['status'],restricted_LP_independent_Farkas_available=False,
        scientific_infeasibility_proven=False,solver_parameter_sweep=False,
        raw_telemetry_first_match_preserved=True,
        clock_semantics='Printed elapsed clocks retained separately; not exclusive phase durations and not summed.',
        factual_documentation='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:InfUnbdInfo',
        documentation_inference='Native FarkasDual unavailable after barrier/numerical crossover infeasibility; no valid ray is available for certified feasibility activation.',
        executed_source=read(OUT/'EXECUTED_FAST_SOURCE_PRESERVATION.json'),
        review_producer=record(__file__))
    atomic(OUT/'MAY19_CANARY/INTERNAL_BARRIER_ATTEMPTS.json',receipt)
    largest_factor=max(attempts,key=lambda a:a['factor_nnz'])
    gate=read(OUT/'SPEED_GATE.json');gate['fill_in'].update(ordering_seconds=receipt['max_ordering_seconds'],
        factor_nnz=receipt['max_factor_nnz'],factor_memory_GB=receipt['max_factor_memory_GB'],
        factor_memory_printed=largest_factor['factor_memory_printed'],
        factor_memory_unit=largest_factor['factor_memory_unit'],factor_operations=largest_factor['factor_operations'],
        factor_summary_attempt_index=attempts.index(largest_factor)+1,
        metric_scope='MAXIMUM_OVER_ALL_INTERNAL_NATIVE_BARRIER_ATTEMPTS',
        internal_attempts=receipt['attempts'])
    gate['root_outcome']='RESTRICTED_NATIVE_INFEASIBLE_WITH_FARKAS_UNAVAILABLE'
    gate['native_call_seconds']=result['native_seconds'];gate['root_completion_seconds']=None
    gate['root_time_lower_bound_speedup']=None
    gate['root_speedup_computable']=False
    gate['checks']['factor_nnz_at_most_quarter']=receipt['max_factor_nnz']<=.25*1562000000
    gate['checks']['factor_memory_at_most_quarter']=receipt['max_factor_memory_GB']<=.25*15.
    gate['checks']['ordering_improved']=receipt['max_ordering_seconds']<=.25*140.09
    assert gate['PASS'] is False and gate['classification']=='SPEED_GATE_FAIL'
    atomic(OUT/'SPEED_GATE.json',gate)
    rows=[]
    with (OUT/'FILL_IN_COMPARISON.csv').open(encoding='utf-8-sig',newline='') as handle:
        rows=list(csv.DictReader(handle))
    for row in rows:
        if row.get('date')=='2025-05-19' and row.get('variant','').startswith('FAST_ACTIVE'):
            row.update(ordering_seconds=receipt['max_ordering_seconds'],factor_nnz=receipt['max_factor_nnz'],
                factor_memory_GB=receipt['max_factor_memory_GB'],factor_memory_printed=largest_factor['factor_memory_printed'],
                factor_memory_unit=largest_factor['factor_memory_unit'],factor_operations=largest_factor['factor_operations'],
                barrier_iterations=receipt['printed_barrier_iteration_total'],
                metric_scope='MAX_OVER_INTERNAL_ATTEMPTS; iterations sum of printed attempt counts; elapsed clocks not summed')
    table(OUT/'FILL_IN_COMPARISON.csv',rows,sorted(set().union(*(r.keys() for r in rows))))
    verification=read(OUT/'VERIFICATION.json');verification['SPEED_GATE']=gate
    verification.update(May19_native_status=3,May19_FarkasDual_available=False,
        May19_feasibility_activation_completed=False,May19_global_scientific_infeasibility_proven=False,
        internal_barrier_attempt_review=record(OUT/'MAY19_CANARY/INTERNAL_BARRIER_ATTEMPTS.json'))
    atomic(OUT/'VERIFICATION.json',verification)
    status=read(OUT/'DOMAIN_STATUS_AUTHORITY.json')
    witness=read(OUT/'MAY17_CANARY/FAST_RESULT.json')['incumbent_support']
    assert witness['PASS'] is True and witness['current_original_matrix_replay']['PASS'] is True
    status['dates']['2025-05-17'].update(ACTIVE_DOMAIN_SOLUTION_VALID=True,
        solution_validity_scope='FRESH_NATIVE_MATRIX_AND_PHYSICAL_REPLAY_OF_PRIOR_VALID_INCUMBENT',
        witness_is_new_solver_optimum=False,witness_source=witness['source_schedule'],
        ACTIVE_INTEGER_SOLVED=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False,FULL_DOMAIN_ACCEPTED=False)
    atomic(OUT/'DOMAIN_STATUS_AUTHORITY.json',status)
    review=OUT/'FINAL_REVIEW_KO.md';text=review.read_text(encoding='utf8')
    text=text.replace('17. May17 제한 LP cumulative native 1.599000초;',
        '17. 수정된 May17 제한 LP native1.599000초; 보존된 첫 시도1.382000초를 합한 실제 native2.981000초;')
    text=text.replace('12. 제한 LP의 실제 Farkas ray와 원본 coupling 계수로 정확한 유리수 후보 점수를 계산합니다.',
        '12. 유효한 실제 Farkas ray가 있으면 원본 coupling 계수로 정확한 유리수 후보 점수를 계산하는 검증기를 구현했습니다. 이번 May19는 FarkasDual 회수 불가로 certifiable feasibility activation을 수행하지 못했습니다.')
    text=text.replace('20. May19 첫 제한 LP 완료 None초. 전체-domain root 시간이 아닙니다.',
        '20. May19 native 호출84.455초에서 제한 모델 INFEASIBLE status3. 수치 trouble 뒤 FarkasDual을 회수하지 못했습니다. feasible root 완료 시간은 미측정이며 과학적 전체-domain infeasible 증명도 없습니다.')
    text=text.replace('22. 제한 LP 완료 대 baseline 중단 root 시도 시간비 >=None; 전체 A1 speedup은 미측정입니다.',
        '22. 완료된 feasible root나 전체 A1의 speedup은 미측정입니다. Raw cols98.06%, rows83.87%, nnz72.30% 감소는 실제 초기 행렬 비교입니다.')
    text=text.replace('23. 새 factor NZ=685100.0, 추정메모리=0.03 GB; FILL_IN_COMPARISON.csv 참조.',
        '23. 한 native 호출 내부 barrier4회에서 관측된 최대 factor NZ25.46M, 추정메모리0.5GB. Baseline 대비 factor NZ98.37%, 메모리96.67% 감소. 최대 ordering0.81초; 첫 factor만 사용하지 않습니다.')
    supplements=(
        'May19의 원본 solver 로그·상태·first-match telemetry는 그대로 보존했습니다. INTERNAL_BARRIER_ATTEMPTS.json이 내부4회 재시도와 서로 다른 elapsed clock을 보충합니다. Gurobi는 barrier에서 infeasibility가 결정되는 경우 InfUnbdInfo=1이어도 증명 정보가 없을 수 있다고 문서화합니다. [Gurobi InfUnbdInfo](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:InfUnbdInfo). 이번 정확한 원인은 로그와 attribute 오류에 기반한 추론이며, 유효한 Farkas 증명은 확보하지 못했습니다.',
        'Farkas/전체 native LP closure가 없고 SPEED_GATE_FAIL이므로 추가300/3600초 실행이나 solver 변경 없이 중단했습니다. May12·May10은 static census만 수행했습니다. 첫 NumPy bool false rejection은 원본 source/permit/gates/결과와 별도 진단을 보존했고, 수정된 canary 예산에서 이미 쓴1.382초를 차감했습니다.',
        'May17에는 현재 native 행렬에 독립 replay된 유효한 정수 feasible witness가 있습니다. 따라서 ACTIVE_DOMAIN_SOLUTION_VALID=True이며, 새 solver가 네 lex 목적을 해결했다는 뜻은 아닙니다. ACTIVE_INTEGER_SOLVED=False 및 full closure/acceptance=False를 유지합니다.')
    for paragraph in supplements:
        if paragraph not in text:text+='\n'+paragraph+'\n'
    review.write_text(text,encoding='utf8',newline='\n')
    manifest=read(OUT/'SHA256_MANIFEST.json')
    manifest['files']=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    atomic(OUT/'SHA256_MANIFEST.json',manifest)
    return receipt

if __name__=='__main__':supplement()
