"""User-authorized ONE fresh z=0 continuation, within the inherited total budget."""
from .common import *
from .resource import inspect
from .experiment import budget
from .continuation_worker import run_worker
import multiprocessing as mp
import psutil,queue

def main():
    label='C01_CONTINUATION';folder=WORK/'children'/label/'z0'
    assert not (folder/'NATIVE_CALL_STARTED.json').exists(),'NO_CONTINUATION_RERUN'
    assert not (WORK/'checkpoints/Z0_CONTINUATION_LAUNCH_ONCE.json').exists()
    ledger=budget();assert ledger['native_calls']==2 and not ledger['unknown_unresolved_native_charge']
    assert ledger['remaining_Native_Runtime']>=1800+10
    original=read(REPORTS/'C01_PAIR_RESULT.json');assert original['children'][0]['Status']==9
    sibling=WORK/'children/C01/z1/RESULT.json';assert read(sibling)['certificate_PASS']
    candidate=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected'][0]
    candidate=dict(candidate,candidate=label)
    prereg=REPORTS/'Z0_CONTINUATION_PREREGISTRATION_KO.md'
    prereg.write_text(f'''# 사용자 추가 지시: z=0 단일 연장 실험

사용자는 첫 480초 양방향 실행 후 "z=0 더 계속 돌려봐 그대로 끝내지 말고. 결과를 보고 싶어."라고 지시했다. 종료·dispose된 Env/Model의 tree/checkpoint를 재개했다고 주장하지 않는다. 같은 C01 charge_mode[MESS02,77]=0, 원본 C3A+B2 651행/min rho_max, 나머지 binary LP relaxation 및 모든 native scientific 설정을 재사용해 새 독립 spawn Worker 한 개에서 fresh optimize를 정확히 한 번 실행한다.

변경은 TimeLimit=480→1800뿐이다. Threads=1, Method=2, Crossover=0, 원본 tolerance 등은 그대로다. 원래 Worker source는 freeze된 상태로 보존하고 continuation_worker는 그 source에서 TimeLimit 설정/receipt 두 부분만 바꾼 복사본이다. Native API에서 실제 설정과 행·objective·bounds·axis를 다시 읽어 검사한다.

기존 소비 {ledger['Native_Runtime_sum']:.9f}초 / calls2를 보존한다. 남은 총 예산 {ledger['remaining_Native_Runtime']:.9f}초, 이번 limit1800초로 총 예상 최대2679.545초이며 전체2880초/calls6 상한을 늘리지 않는다. 자동 반복·다른 후보·z=1 추가 solve는 없다. z=1의 원시 결과와 독립 proof를 같은 scientific child domain의 sibling으로 재사용한다.

새 0 Child가 Native OPTIMAL 및 독립 exact certificate PASS이면 기존 1 Child와 min을 다시 계산한다. 미완료 또는 미인증이면 pair를 인정하지 않고 Global LB를 보존한다. UB=0.6284141956452488을 유지한다. M1_ACCEPTED=false, production/P2/downstream=0을 유지한다. 두 파일 경로와 SHA를 별도로 저장해 initial480 결과를 지우거나 덮어쓰지 않는다.

다른 May12/A-stage/M-stage 작업은 중지·수정하지 않는다. CPU 여유를 읽기 전용으로 확인하고 CPU/RSS/page fault/I/O를 관측한다. MemLimit/SoftMemLimit 및 RAM 기반 자동 종료는 없다. 최초 두 LP의 실제 병렬 결과는 그대로 보존한다. 이 연장 호출은 한 Worker이며 병렬 speedup 실험으로 표현하지 않는다.
''',encoding='utf-8')
    source=(ROOT/'v42_group_branching/worker.py').read_text(encoding='utf-8')
    expected=source.replace('from .common import *','from .common import *\nCHILD_SETTINGS=dict(CHILD_SETTINGS,TimeLimit=1800)',1).replace('TimeLimit=480,source_HEAD','TimeLimit=1800,source_HEAD')
    assert (ROOT/'v42_group_branching/continuation_worker.py').read_text(encoding='utf-8')==expected
    write(REPORTS/'Z0_CONTINUATION_SOURCE_FREEZE.json',dict(PASS=True,preregistration_SHA256=sha(prereg),
        original_worker_SHA256=sha(ROOT/'v42_group_branching/worker.py'),
        continuation_worker_SHA256=sha(ROOT/'v42_group_branching/continuation_worker.py'),
        controller_SHA256=sha(Path(__file__)),only_TimeLimit_and_TimeLimit_receipt_changed=True,
        reused_sibling_result_SHA256=sha(sibling),reused_sibling_certificate_SHA256=sha(sibling.with_name('EXACT_CERTIFICATE.json')),
        consumed_calls=ledger['native_calls'],consumed_Runtime=ledger['Native_Runtime_sum'],TimeLimit=1800))
    admission=inspect('Z0_CONTINUATION_before_spawn');assert admission['admission_PASS']
    write(WORK/'checkpoints/Z0_CONTINUATION_LAUNCH_ONCE.json',dict(maximum_new_calls=1,TimeLimit=1800,starting_budget=ledger))
    ctx=mp.get_context('spawn');messages=ctx.Queue();start=ctx.Event();cancel=ctx.Event()
    process=ctx.Process(target=run_worker,args=(candidate,0,start,cancel,messages),name='C01_z0_1800')
    begin=time.perf_counter();process.start();events=[];samples=[];released=False;done=False
    while not done:
        try:
            message=messages.get(timeout=.5);events.append(dict(wall=time.perf_counter()-begin,**message))
            if message['kind']=='ready':
                gate=inspect('Z0_CONTINUATION_model_ready',owned=[process.pid])
                if gate['admission_PASS']:start.set();released=True;print('Z0_1800_NATIVE_START',process.pid,flush=True)
                else:cancel.set()
            elif message['kind']=='worker_error':cancel.set()
            elif message['kind']=='done':done=True
        except queue.Empty:pass
        try:
            p=psutil.Process(process.pid);cpu=p.cpu_times();memory=p.memory_info()._asdict()
            samples.append(dict(wall=time.perf_counter()-begin,PID=p.pid,CPU_seconds=cpu.user+cpu.system,
                RSS=memory['rss'],page_faults=memory.get('num_page_faults'),io=p.io_counters()._asdict(),available_RAM=psutil.virtual_memory().available))
        except psutil.Error:pass
        if process.exitcode is not None:done=True
    process.join();messages.close();messages.join_thread()
    result=read(folder/'RESULT.json');assert result['native_calls']<=1
    write(REPORTS/'Z0_CONTINUATION_CONTROLLER_EVENTS.json',events)
    table(WORK/'logs/Z0_CONTINUATION_TELEMETRY.csv',samples)
    resources=dict(peak_RSS_observed=max((s['RSS'] for s in samples),default=0),
        CPU_seconds_observed=samples[-1]['CPU_seconds']-samples[0]['CPU_seconds'] if samples else None,
        CPU_sampling_excludes_process_birth_before_first_sample=True,memory_bandwidth='NOT_MEASURED',other_tasks_modified=False)
    write(folder/'RESOURCE_OBSERVATION.json',resources)
    final=budget();assert final['native_calls']<=6 and final['Native_Runtime_sum']<=2880
    write(REPORTS/'Z0_CONTINUATION_CONTROLLER_RESULT.json',dict(result=result,budget=final,
        wall_seconds=time.perf_counter()-begin,released=released,original_pair_preserved=True,
        reused_sibling_SHA256=sha(sibling),native_calls=1,automatic_further_experiments=False))
    print('Z0_1800_NATIVE_END',result.get('Status'),result.get('Runtime'),result.get('exact_LB'),flush=True)

if __name__=='__main__':main()
