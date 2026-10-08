"""Central spawn controller: independent paired LPs, no shared solver objects."""
from .common import *
from .resource import inspect
from .worker import run_worker
import multiprocessing as mp
import queue
import psutil

def budget():
    entries=[]
    for p in sorted((WORK/'children').glob('*/z*/RESULT.json')):
        r=read(p);entries.append(dict(candidate=r['candidate'],value=r['value'],calls=r['native_calls'],
            Runtime=r.get('Runtime'),Work=r.get('Work'),certificate_PASS=r['certificate_PASS']))
    started=list((WORK/'children').glob('*/z*/NATIVE_CALL_STARTED.json'))
    calls=len(started);seconds=sum(r['Runtime'] or 0 for r in entries)
    unknown=any(not (p.parent/'RESULT.json').exists() or read(p.parent/'RESULT.json').get('Runtime') is None for p in started)
    ledger=dict(native_calls=calls,Native_Runtime_sum=seconds,Native_Work_sum=sum(r['Work'] or 0 for r in entries),
        maximum_calls=6,maximum_Native_Runtime=2880,remaining_Native_Runtime=2880-seconds,
        unknown_unresolved_native_charge=unknown,entries=entries)
    write(WORK/'checkpoints/NATIVE_BUDGET_LEDGER.json',ledger);return ledger

def register():
    repair=read(REPORTS/'DUAL_CERTIFICATION_REPAIR_AUDIT.json');assert repair['independent']['PASS']
    selected=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json');assert selected['PASS']
    write(REPORTS/'REVISED_EXECUTION_GATE.json',dict(execution_allowed=True,
        independent_exact_certificate_PASS=True,loss_threshold_is_diagnostic_only=True,
        preserved_old_repair_audit_SHA256=sha(REPORTS/'DUAL_CERTIFICATION_REPAIR_AUDIT.json'),
        preserved_old_quality_gate_PASS=repair['certification_pilot_gate_PASS'],
        authority='User continuation removed 1e-4 execution blocking condition; all scientific and Material gates unchanged',
        diagnostic_native_minus_exact=repair['native_minus_certificate'],diagnostic_threshold=1e-4,native_calls_at_revision=0))
    p=REPORTS/'PARALLEL_EXECUTION_PREREGISTRATION_KO.md'
    if not p.exists():p.write_text('''# Spawn 양방향 LP 실행 사전등록 — 사용자 재개 지시 반영

PR187 exact HEAD e67ecfa827e4262c2f2df17c226d6442656af18b 위 저장 작업을 이어간다. 기존 repair의 1e-4 품질 FAIL은 보존하고, 사용자의 후속 지시에 따라 1e-4를 실행 차단 조건에서 제거한다. 독립 exact weak-duality certificate PASS이면 실행할 수 있다. 원본 objective=min rho_max, 651개 기존 B2 행, 원래 변수·물리·bounds·types authority 및 모든 scientific tolerance는 보존한다.

9,322개 전수 매핑과 사전등록 점수로 고른 SELECTED_BRANCH_VARIABLES의 최상위 후보부터 진행한다. 한 scalar original binary의 bounds만 0/0 또는 1/1로 고정한다. 나머지 binary는 child LP에서만 C로 완화하며 원래 continuous는 그대로다. 전체 그룹 고정이나 추가 논리 고정, 새 cut/threshold/domain 제한은 없다.

각 pair는 multiprocessing.get_context('spawn')의 독립 Python Process 두 개다. Worker마다 독립 Env/Model을 만들고 닫는다. Env/Model을 IPC로 전달하지 않는다. 각 child TimeLimit=480, Threads=1, Method=2, NodeMethod=1, Crossover=0, MIPFocus=3, MIPGap=.005, FeasibilityTol=OptimalityTol=IntFeasTol=BarConvTol=1e-8, Seed=20260929, DegenMoves=0이다. 실제 native API에서 모두 읽어 검증한다. MemLimit/SoftMemLimit은 default infinity, RAM은 관측만 한다.

첫 pair는 두 Env/Model이 동시에 license를 획득하고 원본 transport 검증 후 READY를 보내야 시작한다. Controller가 자원을 다시 검사하고 공통 start event를 보내 두 native 호출을 동시에 시작한다. License 실패 시 우회·자동 재시도 없이 종료한다. 런타임의 실제 native overlap도 저장해 license 지원을 결과로 확인한다. 모델 로딩·build·worker wait·native·certificate·parallel wall은 분리한다.

Native optimize는 worker당 정확히 한 번, 전부 최대 6회, Runtime 합계 최대 2880초다. 각각 before-launch에서 남은 budget≥960초를 요구하며 실제 TimeLimit overshoot도 모두 차감한다. 미확정 소비나 실패한 pair가 있으면 다음 후보를 실행하지 않는다. 첫 pair 양쪽의 완료·독립 인증이 정상일 때만 나머지 사전 선정 후보 두 개를 같은 2-worker 방식으로 평가한다. 3~4 worker 확대는 이번에 하지 않는다. Sequential 반복은 하지 않으며 speedup은 미측정으로 기록한다.

별도 worker 폴더에 원시 X/Pi/RC/Slack·log·identity·tmp·dual proof를 먼저 보존한다. Raw 잘못된 sign은 거부하고 별도 sign-cone/equality multiplier로 all 306,040 finite-bound 항을 재계산한다. CSR 독립 checker를 worker마다 적용한다. 두 유효 certificate 중 강한 값은 해당 child 하한에만 쓴다. 완료되지 않은 child는 unresolved다. Native INFEASIBLE은 independent Farkas proof가 없으면 +infinity가 아니다.

Controller만 pair를 합친다. LB_pair=min(LB_z0,LB_z1), 최종 LB=max(0.5687116104049206, 완료·인증된 pair들의 LB)다. UB=0.6284141956452488은 유지한다. Native 목적값과 raw fractional point를 global bound/UB로 채택하지 않는다. Material ΔLB≥.001, M1_ACCEPTED=false 및 production/P2/downstream 금지는 그대로다.

각 실행 직전 PID·creation·command·cwd·CPU와 실제 solver 여부를 읽기 전용으로 확인한다. 다른 worker를 중지하거나 수정하지 않는다. 두 own Worker의 CPU/RSS/page-fault/I/O 및 system memory를 샘플링한다. 실제 memory-bandwidth 하드웨어 counter가 없으면 NOT_MEASURED이며 RSS/I/O를 bandwidth라고 부르지 않는다. Native Runtime 합계/실제 native span은 overlap 지표이며 순차 baseline 없는 speedup이 아니다.
''',encoding='utf-8')
    sources={p.name:sha(p) for p in (ROOT/'v42_group_branching').glob('*.py')}
    write(REPORTS/'EXECUTION_SOURCE_FREEZE.json',dict(source_HEAD=BASE187,modules=sources,
        selection_SHA256=sha(REPORTS/'SELECTED_BRANCH_VARIABLES.json'),preregistration_SHA256=sha(p),native_calls=0))

def pair(candidate):
    label=candidate['candidate'];token=WORK/'checkpoints'/f'{label}_LAUNCH_ONCE.json'
    assert not token.exists(),'NO_AUTOMATIC_PAIR_RERUN'
    ledger=budget();assert not ledger['unknown_unresolved_native_charge'] and ledger['native_calls']+2<=6 and ledger['remaining_Native_Runtime']>=960
    admission=inspect(label+'_before_spawn')
    if not admission['admission_PASS']:return dict(candidate=label,executed=False,reason='RESOURCE_PENDING',pair_certificate_PASS=False)
    write(token,dict(source_HEAD=BASE187,maximum_new_calls=2,TimeLimit_per_worker=480,max_workers=2,start_method='spawn'))
    ctx=mp.get_context('spawn');messages=ctx.Queue();start=ctx.Event();cancel=ctx.Event()
    begin=time.perf_counter();workers=[ctx.Process(target=run_worker,args=(candidate,v,start,cancel,messages),name=f'{label}_z{v}') for v in (0,1)]
    for p in workers:p.start()
    records=[];events=[];ready=set();done=set();released=False;first_cpu={};last_cpu={};peak={};failure=False
    while len(done)<2:
        try:
            message=messages.get(timeout=.25);events.append(dict(controller_wall=time.perf_counter()-begin,**message))
            if message['kind']=='ready':ready.add(message['value'])
            elif message['kind']=='done':done.add(message['value'])
            elif message['kind']=='worker_error':failure=True;cancel.set()
            if len(ready)==2 and not released:
                final=inspect(label+'_both_models_ready',owned=[p.pid for p in workers])
                if not final['admission_PASS']:failure=True;cancel.set()
                else:
                    write(WORK/'checkpoints'/f'{label}_CONCURRENT_ENV_LICENSE_CHECK.json',dict(PASS=True,
                        evidence='Two distinct spawn processes simultaneously hold their own licensed Env/Model before either optimize',
                        PIDs=[p.pid for p in workers],native_calls_at_gate=ledger['native_calls'],shared_Env_or_Model=False))
                    released=True;start.set();print('PAIR_NATIVE_START',label,candidate['variable_name'],[p.pid for p in workers],flush=True)
        except queue.Empty:pass
        for v,p in enumerate(workers):
            try:
                proc=psutil.Process(p.pid);cpu=proc.cpu_times().user+proc.cpu_times().system;memory=proc.memory_info()._asdict()
                first_cpu.setdefault(v,cpu);last_cpu[v]=cpu;peak[v]=max(peak.get(v,0),memory['rss'])
                records.append(dict(wall=time.perf_counter()-begin,child=v,PID=p.pid,cpu_seconds=cpu,RSS=memory['rss'],
                    num_threads=proc.num_threads(),available_RAM=psutil.virtual_memory().available,
                    page_faults=memory.get('num_page_faults'),process_io=proc.io_counters()._asdict()))
            except psutil.Error:pass
            if p.exitcode is not None and v not in done:
                file=WORK/'children'/label/f'z{v}'/'RESULT.json'
                if file.exists():done.add(v)
                else:failure=True;cancel.set();done.add(v)
        if failure and not released:cancel.set()
    for p in workers:p.join()
    messages.close();messages.join_thread()
    pairwall=time.perf_counter()-begin
    table(WORK/'logs'/f'{label}_WORKER_TELEMETRY.csv',records)
    write(REPORTS/f'{label}_CONTROLLER_EVENTS.json',events)
    results=[]
    for value in (0,1):
        file=WORK/'children'/label/f'z{value}'/'RESULT.json'
        r=read(file) if file.exists() else dict(candidate=label,value=value,executed=False,native_calls=0,certificate_PASS=False,reason='WORKER_CRASH')
        stats=dict(peak_RSS_observed=peak.get(value),CPU_seconds_observed=last_cpu.get(value,0)-first_cpu.get(value,0),
            CPU_sampling_excludes_process_birth_before_first_sample=True,memory_bandwidth='NOT_MEASURED',
            shared_objects='Events and Queue only; no Env/Model')
        write(WORK/'children'/label/f'z{value}'/'RESOURCE_OBSERVATION.json',stats)
        results.append(dict(**r,resources=stats))
    valid=not failure and all(r.get('certificate_PASS') and (r.get('Status')==2 or r.get('infeasibility_certificate_PASS')) for r in results)
    bounds=[math.inf if r.get('infeasibility_certificate_PASS') else r.get('exact_LB') for r in results]
    pairlb=min(bounds) if valid else None
    if valid:assert pairlb<math.inf and pairlb<=UB+1e-8
    starts=[r.get('native_start_epoch') for r in results];ends=[r.get('native_end_epoch') for r in results]
    span=max(ends)-min(starts) if all(v is not None for v in starts+ends) else None
    overlap=max(0.,min(ends)-max(starts)) if span is not None else None
    total=sum(r.get('Runtime',0) for r in results);work=sum(r.get('Work',0) for r in results)
    summary=dict(candidate=label,column=candidate['column'],variable=candidate['variable_name'],executed=released,
        pair_certificate_PASS=valid,children=results,LB_pair=pairlb,valid_global_LB=max(LB,pairlb) if valid else LB,
        Delta_LB=max(0.,pairlb-LB) if valid else 0,parallel_wall_seconds=pairwall,Native_Runtime_sum=total,Work_sum=work,
        native_span_seconds=span,native_overlap_seconds=overlap,native_sum_over_native_span=total/span if span else None,
        causal_speedup=None,sequential_baseline='NOT_RUN',workers=2,worker_start_method='spawn',
        other_tasks_modified=False,memory_bandwidth='NOT_MEASURED',license_native_concurrency_demonstrated=bool(overlap and overlap>0 and valid))
    write(REPORTS/f'{label}_PAIR_RESULT.json',summary);budget()
    print('PAIR_COMPLETE',label,'valid',valid,'LB_pair',pairlb,'Runtime_sum',total,'wall',pairwall,flush=True)
    return summary

def main():
    register();assert read(REPORTS/'PREFLIGHT_TESTS.json')['PASS']
    began=time.perf_counter();selected=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected'];pairs=[]
    for k,row in enumerate(selected,1):
        label=f'C{k:02d}';saved=REPORTS/f'{label}_PAIR_RESULT.json'
        if saved.exists():result=read(saved)
        else:
            ledger=budget()
            if ledger['unknown_unresolved_native_charge'] or ledger['remaining_Native_Runtime']<960:break
            result=pair(dict(row,candidate=label))
        pairs.append(result)
        if not result['pair_certificate_PASS']:break
    final=budget();assert final['native_calls']<=6
    write(REPORTS/'CONTROLLER_RESULT.json',dict(pairs=pairs,budget=final,max_workers_used=2,
        controller_experiment_wall_seconds=time.perf_counter()-began,production_calls=0,P2_calls=0,downstream_calls=0))
    print('GROUP_PILOT_NATIVE_END',final['native_calls'],final['Native_Runtime_sum'],flush=True)

if __name__=='__main__':main()
