"""One fresh A/B pair with an uninterrupted 600-second shared wall clock."""
from .common import *
import shutil
import subprocess
import sys
import time
import psutil

PR153='3d33133e0c4177cb417ee3f03a85cde21f2b43a0'
HISTORY=ROOT/'docs/v42_m1_dw_multicolumn_microbenchmark'


def prepare():
    assert OUT==HISTORY/'clean_revalidation'
    assert not (OUT/'CLEAN_PREREGISTRATION.json').exists()
    freeze=read(HISTORY/'PR152_BYTE_FREEZE.json')
    assert len(freeze['files'])==12919
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    assert read(OUT/'MULTICOLUMN_LIGHTWEIGHT_TESTS.json')['PASS']
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json')
    assert len(cp['pool'])==1604
    historical_source=read(HISTORY/'SOURCE_FREEZE.json')
    for p in ['v42_dw_harvest/adapter.py','v42_dw_harvest/selection.py','v42_dw_harvest/worker.py']:
        assert sha(ROOT/p)==historical_source['files'][p]
    for mode in ['baseline','challenger']:
        leg=OUT/mode;live=leg/'live'
        for sub in ['logs','pricing_receipts','pricing_points']:(live/sub).mkdir(parents=True,exist_ok=True)
        files=[(OLD/'DW_CHECKPOINT_LATEST.json',leg/'immutable/DW_CHECKPOINT_LATEST.json'),
            (OLD/cp['RMP']['point_file'],leg/'immutable'/Path(cp['RMP']['point_file']).name),
            (OLD/cp['smooth_file'],leg/'immutable'/Path(cp['smooth_file']).name)]
        files += [(ROOT/c['file'],leg/c['file']) for c in cp['pool']]
        files += [(HISTORY/'baseline/live'/name,live/name) for name in ['TRUE_DUAL.npz','SEARCH_DUAL.npz']]
        for src,dst in files:
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);dst.chmod(0o444)
            assert sha(src)==sha(dst)
    write(OUT/'PR152_BYTE_FREEZE.json',freeze)
    scientific=read(HISTORY/'MULTICOLUMN_SCIENTIFIC_EQUIVALENCE.json')
    assert scientific['PASS']
    write(OUT/'MULTICOLUMN_SCIENTIFIC_EQUIVALENCE.json',dict(scientific,
        clean_revalidation=True,physics_pricing_selection_worker_byte_unchanged=True,
        runtime_only_changes=['PID-bound live-call guard','continuous wall deadline','full leg wall accounting']))
    write(OUT/'CLEAN_PREREGISTRATION.json',dict(PR152=BASE,PR153_parent=PR153,
        columns_each=1604,rounds_each=1,RMP_each=1,pricing_each=4,Threads=1,
        continuous_pair_wall_cap_seconds=600,clock_includes='worker startup, both legs including freeze/admission/build/validation/cleanup and every intervening wait; no resets',
        initial_A_stage_wait_before_clock=True,pricing_cap_seconds=20,RMP_cap_seconds=200,
        secondary_native_cap_each_seconds=300,alpha=.1,K_per_MESS=8,K_per_round=32,
        primary_metric='audited upper improvement / full leg wall-second',minimum_efficiency_ratio=1.2,
        acceptance=['scientific equivalence PASS','invalid admitted=0','guard interruptions=0','both audited uppers nonincreasing','Challenger efficiency >=1.2*Baseline','continuous pair wall <=600'],
        native_conflict_requires='same live PID/create_time + engine mapped + nonblocking stack + source-bound current native call site; imports/reservations/unknown states never block',
        A_stage_barrier='all currently observed benchmark_a_stage_vnext2.py supervisor/workers terminal; no foreign process control',
        retry=False,authoritative_continuation_calls=0,Certification_calls=0,Branch_and_Price_calls=0,May_production_calls=[0,0,0]))
    sources={p.relative_to(ROOT).as_posix():sha(p) for prefix in ['v42_dw_harvest','tests/v42_dw_harvest'] for p in (ROOT/prefix).glob('*.py')}
    write(OUT/'SOURCE_FREEZE.json',dict(files=sources,preregistration_SHA=sha(OUT/'CLEAN_PREREGISTRATION.json'),
        historical_artifacts_commit=PR153,native_calls_before_freeze=0))
    print('CLEAN_IDENTICAL_READONLY_COPIES_READY',len(cp['pool']),flush=True)


def a_stage_barrier():
    from .native_state import inspect_live
    events=[];seen_roots=set()
    while True:
        active=[]
        for p in psutil.process_iter(['pid','create_time','cmdline']):
            try:
                cmd=p.info['cmdline'] or []
                if not any('benchmark_a_stage_vnext2.py' in token for token in cmd):continue
                active.append(dict(pid=p.pid,create_time=p.info['create_time'],cmd=cmd))
                if '--out' in cmd:seen_roots.add(cmd[cmd.index('--out')+1])
            except (psutil.NoSuchProcess,psutil.AccessDenied):continue
        rows,blocked=inspect_live()
        event=dict(epoch=time.time(),state='WAIT_A_STAGE_TERMINAL' if active else 'A_STAGE_TERMINAL',
                   active_stage_processes=active,processes=rows,confirmed_heavy=blocked,
                   foreign_control_calls=0)
        events.append(event)
        receipts=[]
        for root in sorted(seen_roots):
            path=Path(root)/'STOP_RECEIPT.json'
            if path.exists():receipts.append(dict(path=str(path),SHA=sha(path),receipt=read(path)))
        # Include the completed run discovered during the initial inspection.
        initial=Path('C:/v42_microbenchmarks/vnext2_stage3/STOP_RECEIPT.json')
        if initial.exists() and not any(r['path']==str(initial) for r in receipts):
            receipts.append(dict(path=str(initial),SHA=sha(initial),receipt=read(initial)))
        write(OUT/'A_STAGE_TERMINAL_BARRIER.json',dict(PASS=not active,events=events,terminal_receipts=receipts))
        if not active:return
        if len(events)==1 or len(events)%6==0:
            print('WAIT_A_STAGE_TERMINAL',[(p['pid'],p['create_time']) for p in active],flush=True)
        time.sleep(5)


def child():
    from .benchmark import run
    run('BASELINE')
    run('CHALLENGER')


def run_pair():
    assert OUT==HISTORY/'clean_revalidation'
    assert not (OUT/'CONTINUOUS_PAIR_START.json').exists()
    freeze=read(OUT/'SOURCE_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    assert freeze['preregistration_SHA']==sha(OUT/'CLEAN_PREREGISTRATION.json')
    a_stage_barrier()
    from .resources import Monitor
    monitor=Monitor([],OUT)
    try:write(OUT/'PAIR_ADMISSION.json',monitor.gate('CLEAN_PAIR_START'))
    finally:monitor.close()
    started=time.perf_counter();deadline=started+600
    env=dict(os.environ,V42_DW_PAIR_DEADLINE_PERF=str(deadline))
    write(OUT/'CONTINUOUS_PAIR_START.json',dict(start_perf=started,deadline_perf=deadline,
        cap_seconds=600,pre_native_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()))
    hard=False;controlled=[]
    with (OUT/'CONTINUOUS_PAIR.log').open('w',encoding='utf8') as log:
        process=subprocess.Popen([sys.executable,'-X','utf8','-m','v42_dw_harvest.clean','child'],cwd=ROOT,
            env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while process.poll() is None:
            now=time.perf_counter()
            if now>=deadline-20:
                for mode in ['baseline','challenger']:
                    write(OUT/mode/'live/STOP_REQUEST.json',dict(reason='CONTINUOUS_PAIR_WALL_LIMIT'))
            if now>=deadline-10:
                # Emergency deadline control is limited to this exact Popen tree.
                try:
                    owned=psutil.Process(process.pid).children(recursive=True)
                    for p in reversed(owned):
                        try:
                            identity=dict(pid=p.pid,create_time=p.create_time())
                            p.kill();controlled.append(identity)
                        except psutil.NoSuchProcess:pass
                except psutil.NoSuchProcess:pass
                if process.poll() is None:process.kill()
                hard=True;break
            time.sleep(.25)
        process.wait(timeout=5)
    elapsed=time.perf_counter()-started
    write(OUT/'CONTINUOUS_PAIR_TERMINAL.json',dict(exit_code=process.returncode,
        continuous_wall_seconds=elapsed,continuous_wall_cap_seconds=600,
        PASS=process.returncode==0 and elapsed<=600,hard_deadline_control=hard,
        controlled_owned_descendants=controlled,foreign_process_control_calls=0,
        authoritative_continuation_calls=0,Certification_calls=0,Branch_and_Price_calls=0,
        second_round_calls=0,retry_calls=0))
    print('CLEAN_PAIR_TERMINAL',process.returncode,elapsed,hard,flush=True)


if __name__=='__main__':
    {'prepare':prepare,'run':run_pair,'child':child}[sys.argv[1]]()
