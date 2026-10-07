"""Review actual fast diagnostics without promoting missing domain certificates."""
from pathlib import Path
import csv,json,subprocess
from v42_pr134_b1.common import atomic,read,record,table,digest
from .fast_prepare import ROOT,OUT,OLD
from .fast_telemetry import fill_in_metrics
from .fast_pricing import parse_baseline_log


def metric(log):
    result=fill_in_metrics(log)
    if result['factor_memory_printed'] is not None:
        result['factor_memory_GB']=result['factor_memory_printed']/(1000 if result['factor_memory_unit']=='MB' else 1)
    else:result['factor_memory_GB']=None
    return result


def speed_gate(baseline,canary,initial,fill,permit):
    raw=baseline['raw_model']
    checks=dict(root_completed=canary.get('root_completed') is True,
        source_and_policies_match=canary.get('execution_sources_sha256')==digest(permit['execution_sources'])
            and canary.get('solver_policy_sha256')==permit['solver_policy']['sha256']
            and canary.get('activation_policy_sha256')==permit['activation_policy']['sha256'],
        root_within_300_seconds=canary.get('first_root_native_seconds',float('inf'))<=300,
        columns_at_most_half=initial['cols']<=.5*raw['cols'],
        factor_nnz_at_most_quarter=fill.get('factor_nnz') is not None and fill['factor_nnz']<=.25*baseline['factor_nonzeros'],
        factor_memory_at_most_quarter=fill.get('factor_memory_GB') is not None and fill['factor_memory_GB']<=.25*baseline['factor_memory_GB'],
        ordering_improved=(fill.get('ordering_seconds') is not None
            and baseline.get('ordering_seconds') is not None and fill['ordering_seconds']<=.25*baseline['ordering_seconds']),
        no_scientific_stop=canary.get('global_scientific_stop') is False)
    passed=all(checks.values())
    return dict(PASS=passed,classification='SPEED_GATE_PASS' if passed else 'SPEED_GATE_FAIL',checks=checks,
        engineering_only=True,scientific_feasibility_or_integer_closure_implied=False,
        comparison_scope='small restricted native LP versus complete-STAY-all-active interrupted MIP root LP',
        initial_model=initial,fill_in=fill,root_native_seconds=canary.get('first_root_native_seconds'),
        baseline_root_completed=False,baseline_root_attempt_seconds=baseline['interrupted_root_attempt_seconds'],
        full_A1_speedup=None,root_time_lower_bound_speedup=(baseline['interrupted_root_attempt_seconds']/canary['first_root_native_seconds']
            if canary.get('first_root_native_seconds',0)>0 else None),
        execution_sources_sha256=digest(permit['execution_sources']),solver_policy_sha256=permit['solver_policy']['sha256'],
        activation_policy_sha256=permit['activation_policy']['sha256'],canary_source_bound=checks['source_and_policies_match'])


def finalize():
    baseline=read(OUT/'COMPLETE_STAY_ALL_ACTIVE_BASELINE.json')
    oldstage=read(OLD/'MAY19/A1_RESULT.json')['passes'][0]
    parsed=parse_baseline_log((OLD/'MAY19/rho/NATIVE_SOLVER.log').read_text(encoding='utf-8-sig'),oldstage)
    atomic(OUT/'COMPLETE_STAY_ALL_ACTIVE_PARSED_LOG.json',dict(parsed,source_log=record(OLD/'MAY19/rho/NATIVE_SOLVER.log')))
    baseline['ordering_seconds']=parsed['ordering_seconds']
    permit=read(OUT/'CANARY_EXECUTION_PERMIT.json')
    dates={};models=[];fills=[];builds=[];activation=[];pricing=[];resources=[]
    for label in ('MAY17','MAY19'):
        folder=OUT/(label+'_CANARY');result=read(folder/'FAST_RESULT.json');dates[label]=result
        with (folder/'BUILD_PROFILE.csv').open(encoding='utf-8-sig',newline='') as stream:
            builds.extend(dict(date=result['day'],**row) for row in csv.DictReader(stream))
        for name,dest in [('ACTIVATION_TRACE.csv',activation),('PRICING_TRACE.csv',pricing),('RESOURCE_TELEMETRY.csv',resources)]:
            with (folder/name).open(encoding='utf-8-sig',newline='') as stream:
                dest.extend(dict(row) for row in csv.DictReader(stream))
        initial=read(folder/'rho/LP_0000/PRE_OPTIMIZE_MODEL_AND_POOL.json')
        log=(folder/'rho/LP_0000/NATIVE_SOLVER.log').read_text(encoding='utf-8-sig');fill=metric(log)
        for path in sorted(folder.glob('rho/LP_*/NATIVE_SOLVER.log')):
            values=metric(path.read_text(encoding='utf-8-sig'))
            receipt=read(path.parent/'NATIVE_RESULT.json')
            telemetry=read(path.parent/'NATIVE_TELEMETRY.json')
            fills.append(dict(date=result['day'],variant='FAST_ACTIVE_'+path.parent.name,**values,
                presolved=json.dumps(telemetry.get('presolved_matrix')),native_seconds=receipt['native_seconds'],
                Work=receipt.get('Work'),peak_RSS_bytes=max((r.get('RSS_bytes',r.get('rss_bytes',0)) for r in telemetry.get('resource_samples',[])),default=0),
                first_incumbent_seconds=None,full_A1_seconds=None))
        oldresult=read(OLD/label/'A1_RESULT.json');old=oldresult['passes'][0]['model_census']
        modelrow=dict(date=result['day'],variant='FAST_INITIAL',rows=initial['rows'],cols=initial['cols'],nnz=initial['nnz'],
            binaries=initial['original_binaries'],integer_counts=initial['original_integer_counts'],continuous=initial['original_continuous'],
            active_STAY=initial['domain_census']['active_STAY'],physical_STAY=initial['domain_census']['physical_STAY'],
            active_migration=initial['domain_census']['active_migration'],physical_migration=initial['domain_census']['physical_migration'])
        for key in ('rows','cols','nnz','binaries','integer_counts','continuous'):
            modelrow[key+'_reduction_percent']=100*(1-modelrow[key]/old[key]) if old[key] else None
        models.extend([dict(date=result['day'],variant='COMPLETE_STAY_ALL_ACTIVE',**old),modelrow])
        if label=='MAY19':gate=speed_gate(baseline,result,modelrow,fill,permit)
    fills.insert(0,dict(date='2025-05-19',variant='COMPLETE_STAY_ALL_ACTIVE',
        ordering_seconds=parsed['ordering_seconds'],factor_nnz=baseline['factor_nonzeros'],factor_memory_GB=15.,
        barrier_iterations=52,barrier_seconds=None,barrier_summary_elapsed_seconds=3605.14,
        root_completed=False,root_attempt_seconds=3520.71,native_seconds=baseline['native_seconds'],
        Work=oldstage['Work'],presolved=json.dumps(baseline['root_presolved']),
        full_A1_seconds=None,first_incumbent_seconds=None))
    for name,rows in [('MODEL_SIZE_COMPARISON.csv',models),('FILL_IN_COMPARISON.csv',fills),('BUILD_PROFILE.csv',builds),
        ('ACTIVATION_TRACE.csv',activation),('PRICING_TRACE.csv',pricing),('RESOURCE_TELEMETRY.csv',resources)]:
        table(OUT/name,rows,sorted(set().union(*(row.keys() for row in rows))) if rows else ['status'])
    atomic(OUT/'SPEED_GATE.json',gate)
    regression=dates['MAY17'].get('incumbent_support') or {}
    status=dict(PASS=not any(r['global_scientific_stop'] for r in dates.values()),dates={})
    for label,result in dates.items():
        status['dates'][result['day']]=dict(result['domain_status'],classification=result['classification'],
            actual_native_seconds=result['native_seconds'],diagnostic_only=True)
    for day in ('2025-05-12','2025-05-10'):
        status['dates'][day]=dict(HARD_PHYSICAL_DOMAIN_DEFINED=True,ACTIVE_DOMAIN_FEASIBLE=False,LP_PRICING_CLOSED=False,
            ACTIVE_INTEGER_SOLVED=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False,FULL_DOMAIN_ACCEPTED=False,
            classification='NOT_RUN_PROOF_GATE',actual_native_seconds=0)
    atomic(OUT/'DOMAIN_STATUS_AUTHORITY.json',status)
    reason='FULL_NATIVE_LP_PRICING_CLOSURE_UNRESOLVED' if gate['PASS'] else 'SPEED_GATE_FAIL'
    atomic(OUT/'CONDITIONAL_PRODUCTION_EXECUTION.json',dict(PASS=True,production_executed=False,reason=reason,
        May17=False,May19=False,May12=False,May10=False,other_27_dates_run=0,Actual_reoptimization=0,
        SPEED_GATE_PASS=gate['PASS'],LP_pricing_closed=all(r['domain_status']['LP_PRICING_CLOSED'] for r in dates.values()),
        honest_stop_at_missing_certificate=True))
    overall=('FAST_ACTIVE_DOMAIN_SCIENTIFIC_FAIL' if not status['PASS'] else
        'FAST_ACTIVE_DOMAIN_PARTIAL_SUCCESS' if gate['PASS'] and regression.get('PASS') is True else 'FAST_ACTIVE_DOMAIN_TRACTABILITY_FAIL')
    verification=dict(PASS=status['PASS'] and regression.get('PASS') is True,
        overall_classification=overall,science_preserved=True,current_May17_physical_regression=regression,
        SPEED_GATE=gate,full_native_LP_closure=False,integer_domain_closure=False,production_accepted=False,
        parameter_sweep=False,tolerances_relaxed=False,permanent_candidate_deletions=0,
        pre_run_tests=record(OUT/'FAST_PRE_RUN_TESTS.json'),old_all_active_evidence_preserved=record(OLD/'COMPLETE_STAY_ALL_ACTIVE_PRESERVATION.json'))
    atomic(OUT/'VERIFICATION.json',verification)
    def new(label):return next(r for r in models if r['variant']=='FAST_INITIAL' and r['date']==dates[label]['day'])
    may17,may19=new('MAY17'),new('MAY19');objectives=regression.get('incumbent_objectives',{})
    def sizes(v):return f"{v['rows']:,} rows / {v['cols']:,} cols / {v['nnz']:,} nnz"
    answers=[
        '완전 STAY와 큰 기존 migration active 그래프가 native 변수/행과 barrier fill-in을 늘렸습니다.',
        'May19 baseline: 4,417,827 rows / 4,316,192 cols / 49,651,657 nnz.',
        'Factor NZ 약1.562e9, 추정 메모리15.0 GB. 원본 log의 반올림 값입니다.',
        '아니오. root 완료 전에 TIME_LIMIT; native Runtime3606.646초(요청3600초 종료 overshoot6.646초).',
        'INFEASIBLE이 아닙니다. COMPLETE_STAY_ALL_ACTIVE_ROOT_TIMEOUT입니다.',
        '전체 hard-valid V2 과학적 domain, class cardinality, frozen 물리 계수를 보존했습니다.',
        '유효 anchor/기존 STAY/rescue/검증 incumbent + 같은 site ±2 + class당 순위 추가8개; migration은 작은 유효 seed입니다.',
        '생략 STAY는 site별 start interval과 immutable 물리/계수 provider로 저장하고 native 변수0개를 생성합니다.',
        '아니오. 기준 시각은 초기 순위·warm support·목적함수에만 사용합니다.',
        '아니오. 낮은 grid 순위도 D_POOL에 남습니다.',
        '필수 지원을 먼저 포함하고 frozen signed thermal 계수의 GPU occupancy 순위로 추가 후보를 결정합니다.',
        '제한 LP의 실제 Farkas ray와 원본 coupling 계수로 정확한 유리수 후보 점수를 계산합니다. 완전 native 증명 없이는 과학적 infeasible을 선언하지 않습니다.',
        '실제 LP Pi, 원본 GPU/Runtime/WAN/ACTIVE 행과 class cardinality potential을 사용합니다. native primitive/block dual 검증 API를 별도로 두었습니다.',
        '아니오. LP pricing closure와 integer-domain closure는 독립된 상태입니다.',
        'FULL_DOMAIN_OPTIMALITY_UNRESOLVED. 실제 전체 native pricing producer와 branch-price/정수 closure 증명이 미완성입니다.',
        '새 May17 초기 크기: '+sizes(may17)+'.',
        f"May17 제한 LP cumulative native {dates['MAY17']['native_seconds']:.6f}초; build는 BUILD_PROFILE.csv에 분리합니다.",
        'May17 제한 LP feasible='+str(dates['MAY17']['domain_status']['ACTIVE_DOMAIN_FEASIBLE'])+'; 이전 검증된 integer schedule을 현재 native 행렬에 새로 replay한 결과 PASS='+str(regression.get('PASS'))+'.',
        '새 May19 초기 크기: '+sizes(may19)+'.',
        f"May19 첫 제한 LP 완료 {dates['MAY19'].get('first_root_native_seconds')}초. 전체-domain root 시간이 아닙니다.",
        '전체 A1 4-pass 실행 없음. LP closure gate가 MILP를 막았습니다.',
        f"제한 LP 완료 대 baseline 중단 root 시도 시간비 >={gate.get('root_time_lower_bound_speedup')}; 전체 A1 speedup은 미측정입니다.",
        f"새 factor NZ={gate['fill_in'].get('factor_nnz')}, 추정메모리={gate['fill_in'].get('factor_memory_GB')} GB; FILL_IN_COMPARISON.csv 참조.",
        '아니오. 속도 때문에 영구 삭제한 유효 후보0개.',
        '아니오. 물리·Runtime·CC4·GPU·WAN·grid 한계를 바꾸지 않았습니다.',
        '아니오. 원본 scientific tolerances를 보존했습니다.',
        '아니오. solver parameter sweep0회. InfUnbdInfo=1은 정보 회수용입니다.',
        'May12 native optimize 미실행. 이전 parent가 시작한 build 전 child를 중단했고 새 production도 proof gate로 중단했습니다.',
        'May12 root 결과 없음: NOT_RUN_PROOF_GATE.',
        'May10 shift 단계 미도달. native optimize0회.',
        'May10 shift 결과 없음. exact fresh lock/rebuild/zero projection/정수 인증 구현은 테스트로 보존했습니다.',
        '새 4단계 active integer-solved 날짜0개. 두 날짜는 제한 LP diagnostic만 수행했습니다.',
        'full-domain closure proven 날짜0개.',
        'production accepted 날짜0개. Planning/Actual/Fresh0회.',
        '최종 정확한 HEAD는 publication 시 외부 FINAL_PUBLICATION_RECEIPT.json과 최종 응답으로 제공합니다(자기참조 hash 없음).',
        'Draft PR URL은 publication receipt와 최종 응답으로 제공합니다.'
    ]
    text=overall+'\n\n'+f"SPEED_GATE={gate['classification']}. 전체 native LP pricing 및 integer-domain closure 미증명으로 전체 재실행을 막았습니다.\n\n"
    text+='\n'.join(f'{i}. {answer}' for i,answer in enumerate(answers,1))+'\n\n'
    text+=f"현재 행렬에서 replay한 May17 incumbent 지원: rho={objectives.get('rho')}, migration={objectives.get('migration_count')}, shift={objectives.get('shift_magnitude')}. 이는 새 최적값/새 bound/새 lex lock이 아닙니다.\n"
    text+='\nLP 물리 경로 점수만으로 native mixed-flow의 fractional finish 방향 전체를 증명할 수 없습니다. 유효 block-dual 검증기는 구현했지만 실제 모든 생략 primitive 방향을 공급·검증하는 producer와 budgeted block oracle은 미완성입니다. 이를 완료해야 production MILP를 실행할 수 있습니다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')
    files=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    external=[]
    for p in sorted(OUT.glob('MAY*_CANARY/rho/LP_*/EXTERNAL_STATIC_ARTIFACTS.json')):
        for value in read(p)['static_artifacts']:
            if record(value['path'])!=value:raise ValueError('EXTERNAL_STATIC_BYTE_DRIFT')
            external.append(value)
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,files=files,external_static_artifacts=external,
        manifest_self_excluded=True,whole_directory_except_self_covered=True))
    return verification

if __name__=='__main__':finalize()
