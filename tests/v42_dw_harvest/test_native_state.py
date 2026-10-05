from v42_dw_harvest.native_state import classify, call_witness


SOURCE = 'import gurobipy as gp\nmodel = gp.Model()\nmodel.optimize(callback)\n'


def row(maps=True):
    return dict(pid=123, create_time=100., native_maps=['gurobi130.dll'] if maps else [])


def stack(line=3, pid=123, extra=()):
    return [dict(pid=pid, thread_id=10, frames=[*extra,
        dict(filename='worker.py', name='solve', line=line)])]


def test_mapping_or_import_is_not_a_heavy_conflict():
    for frames in ([], stack(1), stack(2)):
        assert classify(row(), frames, lambda _: SOURCE)['optimize_state']=='UNCONFIRMED'


def test_actual_native_call_requires_pid_and_call_site_evidence():
    observed=classify(row(),stack(),lambda _:SOURCE)
    assert observed['classification']=='CONFIRMED_FOREIGN_NATIVE_SOLVE'
    assert observed['live_call_proofs'][0]['call']=='optimize'
    assert observed['live_call_proofs'][0]['sample_pid']==123
    assert observed['live_call_proofs'][0]['line']==3


def test_other_pid_stack_and_absent_native_engine_never_block():
    assert not classify(row(),stack(pid=124),lambda _:SOURCE)['live_call_proofs']
    assert classify(row(False),stack(),lambda _:SOURCE)['classification']=='NO_NATIVE_ENGINE_MAPPED'


def test_mock_scheduler_optimize_is_not_a_native_solve():
    mock=dict(filename='Lib/unittest/mock.py',name='_mock_call',line=10)
    assert classify(row(),stack(extra=[mock]),lambda _:SOURCE)['optimize_state']=='UNCONFIRMED'


def test_custom_python_scheduler_is_not_a_native_solve():
    fake=dict(filename='scheduler.py',name='optimize',line=1)
    observed=classify(row(),stack(extra=[fake]),
        lambda f:'time.sleep(10)' if f=='scheduler.py' else SOURCE)
    assert observed['optimize_state']=='UNCONFIRMED'


def test_callback_still_binds_the_outer_live_native_call():
    callback=dict(filename='callback.py',name='callback',line=1)
    observed=classify(row(),stack(extra=[callback]),
        lambda f:'print("callback")' if f=='callback.py' else SOURCE)
    assert observed['classification']=='CONFIRMED_FOREIGN_NATIVE_SOLVE'


def test_unreadable_or_idle_source_never_fabricates_native_state():
    def unavailable(_):raise OSError('not accessible')
    assert classify(row(),stack(),unavailable)['optimize_state']=='UNCONFIRMED'
    assert call_witness(dict(line=1),'print("model.optimize()")') is None


def test_live_observer_is_nonblocking_and_does_not_control_foreign_processes():
    from pathlib import Path
    import ast
    import v42_dw_harvest.native_state as module
    source=Path(module.__file__).read_text(encoding='utf8')
    assert "'--nonblocking'" in source and "'--locals'" not in source
    calls=[n.func.attr for n in ast.walk(ast.parse(source))
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    assert not {'kill','terminate','suspend','resume'} & set(calls)


def test_pid_reuse_during_live_probe_is_not_a_confirmed_conflict(monkeypatch):
    from types import SimpleNamespace
    import json
    import v42_dw_harvest.native_state as module
    class Process:
        pid=123
        info=dict(pid=123,ppid=1,name='python.exe',create_time=100.)
        def create_time(self):return 100.
        def memory_maps(self,grouped=True):return [SimpleNamespace(path='gurobi130.dll')]
        def memory_info(self):return SimpleNamespace(rss=2**30)
    monkeypatch.setattr(module.psutil,'process_iter',lambda _:iter([Process()]))
    monkeypatch.setattr(module.psutil,'Process',lambda _:SimpleNamespace(create_time=lambda:200.))
    monkeypatch.setattr(module.shutil,'which',lambda _:'py-spy.exe')
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(stack()),stderr=''))
    assert module.inspect_live()==([],[])


def test_gate_admits_an_import_reservation_without_native_call_proof(monkeypatch):
    import threading
    import v42_dw_harvest.resources as module
    monitor=module.Monitor.__new__(module.Monitor)
    monitor.phase='BUILD';monitor.deadline=float('inf');monitor.cancel=threading.Event()
    monitor.owned=[];monitor.process_lock=threading.Lock();monitor.last_process_probe=0.
    monitor.process_events=[];monitor.evidence_dir=None
    monitor.last_process_rows=[];monitor.last_blocked=[]
    snapshot=dict(UTC='fixture',available_RAM=2**30,commit_percent=10.,perf=0.,
                  pagefile_used=0,hard_page_input_pages_per_sec=0.)
    monitor.rows=[snapshot];monitor.sample=lambda:snapshot
    idle=classify(row(),stack(1),lambda _:SOURCE)
    monkeypatch.setattr(module,'inspect_live',lambda _:([idle],[]))
    assert monitor.gate('fixture')['PASS']
    assert not monitor.cancel.is_set()
