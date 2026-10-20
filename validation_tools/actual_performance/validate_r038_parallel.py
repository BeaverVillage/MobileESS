"""Seven isolated native TIME/Fresh processes, shared row-store collision check."""
from pathlib import Path
import argparse,sys,subprocess,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

def child(out,shared,arm,logical,gate=None):
    import psutil
    psutil.Process().cpu_affinity([logical])
    import v44_recovery_r029
    from v44.common import read,record,atomic,now,digest
    from contextlib import ExitStack
    from unittest.mock import patch
    from v44_actual_bank_gate import install as bank_install
    from v44_actual_control_key import install as control_install
    from v44_actual_record_light import SharedControlEncoding
    from v44_actual_content_store import install as content_install
    from v44_audit_chunk_store import install as chunk_install,ChunkStore
    from v44_actual_queue_light import clock_scope
    from v44_recovery_r029 import history
    from v44_recovery_r029.current_ac_performance import live_read_scope
    from v44_recovery_r029.fresh_performance import live_fresh_scope
    helper=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/validate_r009_final_repeated.py')
    setup=helper.read_text(encoding='utf-8').split('import v44_recovery_r009.current_ac_performance as performance')[0]
    setup=setup.replace('out=Path(sys.argv[1]);out.mkdir(exist_ok=False)','')
    ns={};exec(compile(setup,str(helper),'exec'),ns)
    import v44.svr11_ac as ac
    out.mkdir();atomic(out/'READY.json',dict(pid=psutil.Process().pid,affinity=psutil.Process().cpu_affinity()))
    if gate:
        deadline=time.monotonic()+120
        while not gate.exists():
            if time.monotonic()>deadline:raise RuntimeError('VALIDATION_BARRIER_TIMEOUT')
            time.sleep(.05)
    engine=ns['oracle'](arm);encoding=SharedControlEncoding();checks=[]
    with ns['native_zero']() as denied:
        for step in ('initial','changed_candidate','Fresh'):
            rows=list(ns['rows'][:25])
            if step=='changed_candidate':
                rows[-1]=dict(rows[-1],P=rows[-1]['P'].copy());rows[-1]['P'][0]+=.5
            fresh=step=='Fresh';engine._independent_fresh=fresh
            with ExitStack() as stack:
                stack.enter_context(bank_install());stack.enter_context(control_install())
                if not fresh:
                    stack.enter_context(clock_scope());stack.enter_context(content_install(shared));stack.enter_context(chunk_install(shared))
                stack.enter_context(ns['scope']());stack.enter_context(patch.object(ac,'RUNTIME',shared))
                stack.enter_context(live_fresh_scope(engine) if fresh else live_read_scope(encoding,engine))
                stack.enter_context(history.scope(engine,rows));value=engine._probe(rows)
                audit=read(value['physical_audit']['path'])
                def raw_sha(ref):
                    import hashlib
                    return record(ref['path'])['sha256'] if fresh else hashlib.sha256(ChunkStore(shared).restore(ref['path'])).hexdigest()
                checks.append(dict(step=step,verdict=value['PASS'],physical_steps_sha=digest(value['physical_steps']),
                    slots_sha=raw_sha(audit['slots_receipt']),events_sha=raw_sha(audit['physical_solve_events_receipt']),
                    native_solves=audit['total_physical_SolveSnap_count']))
        assert not denied
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,arm=arm,checks=checks,affinity=psutil.Process().cpu_affinity(),Native_optimizer_calls=0))

def parent(out):
    import v44_recovery_r029
    from v44.common import read,record,atomic,now
    from v44_recovery_r038.cpu import placement
    from v44_recovery_r029.cpu_placement import windows_cpu_sets
    out.mkdir(exist_ok=False);plan=placement(windows_cpu_sets());baseline={}
    for arm in ('B1','B3'):
        folder=out/('SERIAL_'+arm)
        subprocess.run([sys.executable,'-X','utf8',__file__,'--child',str(folder),'--shared',str(out/'SHARED_ROWS'),
            '--arm',arm,'--logical','10'],check=True,capture_output=True)
        baseline[arm]=read(folder/'RESULT.json')['checks']
    processes=[];gate=out/'GO.json'
    for i,slot in enumerate(plan['slots']):
        folder=out/f'WORKER{i+1}';arm='B1' if i%2==0 else 'B3'
        log=(out/f'worker{i+1}.log').open('ab')
        process=subprocess.Popen([sys.executable,'-X','utf8',__file__,'--child',str(folder),'--shared',str(out/'SHARED_ROWS'),
            '--arm',arm,'--logical',str(slot['logical']),'--gate',str(gate)],stdout=log,stderr=log)
        log.close();processes.append((process,folder,arm))
    deadline=time.monotonic()+120
    while not all((p/'READY.json').exists() for _,p,_ in processes):
        if any(proc.poll() is not None for proc,_,_ in processes):raise RuntimeError('PARALLEL_VALIDATION_CHILD_EXITED')
        if time.monotonic()>deadline:raise RuntimeError('PARALLEL_VALIDATION_READY_TIMEOUT')
        time.sleep(.1)
    atomic(gate,dict(UTC=now(),seven_processes_ready=True));results=[]
    for proc,folder,arm in processes:
        assert proc.wait(timeout=120)==0,folder
        value=read(folder/'RESULT.json');assert value['checks']==baseline[arm],folder
        results.append(value)
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,workers=7,cpu_placement=plan,
        independent_native_CONTEXT_and_Fresh_checks=21,serial_and_parallel_results_byte_identical=True,
        shared_chunk_store_concurrent_write_PASS=True,Native_optimizer_calls=0,
        production_case_modified=False,full_Actual120_runs_claimed=False,results=results,source=record(__file__)))
    print(dict(PASS=True,workers=7,checks=21,Native_optimizer_calls=0),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--child',type=Path);p.add_argument('--shared',type=Path);p.add_argument('--arm');p.add_argument('--logical',type=int);p.add_argument('--gate',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
    if a.child:child(a.child,a.shared,a.arm,a.logical,a.gate)
    else:parent(a.out)
