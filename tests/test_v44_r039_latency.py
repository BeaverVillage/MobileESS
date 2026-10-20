import inspect,ast,textwrap
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v44_recovery_r039 import latency,operations as op
from v43_actual.controller import V43EventController
from v43_actual import compare

def fake_controller():
    seen=[]
    oracle=SimpleNamespace(observe=lambda *a:seen.append(('oracle',a)))
    policy=SimpleNamespace(oracle=oracle,observe=lambda *a:seen.append(('observe',a)),on_tick=lambda *a:seen.append(('callback',a)))
    controller=SimpleNamespace(policy=policy,_observed_prefix=lambda n:'prefix',ledger=SimpleNamespace(physical=lambda n:'physical'),
        metadata={},_admit_jobs=lambda n:['job1'],tick_wall_times=[])
    return controller,seen

def test_949_second_tick_completes_with_identical_callbacks_and_starts():
    c,seen=fake_controller();guard=[]
    tick=latency.tick(V43EventController.admit,lambda:guard.append(True))
    with patch.dict(tick.__globals__,perf_counter=iter([0,949.4157510999939]).__next__):
        assert tick(c,900)==['job1']
    assert guard==[True]
    assert [r[0] for r in seen]==['oracle','observe','observe','callback']
    assert c.tick_wall_times==[dict(time_seconds=900,wall_seconds=949.4157510999939,starts=1)]

def test_physical_slot_cadence_stays_900_seconds():
    c,seen=fake_controller();tick=latency.tick(V43EventController.admit,lambda:None)
    assert tick(c,901)==[] and seen==[] and c.tick_wall_times==[]

@pytest.mark.parametrize('actual,fresh,expected',[(True,True,True),(False,True,False),(True,False,False),(False,False,False)])
def test_pass_requires_both_actual_and_independent_fresh_even_when_latency_fails(actual,fresh,expected):
    run=latency.compare(compare.run,lambda:None)
    tree=ast.parse(textwrap.dedent(inspect.getsource(run)))
    gate=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='gate' for t in n.targets))
    env=dict(control_slots=120,variants={'C1':dict(Actual96_execution_PASS=actual,Fresh96_physical_PASS=fresh,latency_within_900_seconds=False)})
    assert eval(compile(ast.Expression(gate),'<gate>','eval'),env) is expected
    env['control_slots']=1
    assert eval(compile(ast.Expression(gate),'<gate>','eval'),env) is False
    assert 'latency_within_900_seconds=max(elapsed)<900' in inspect.getsource(run)
    assert 'fresh=oracle._probe(rows)' in inspect.getsource(run)

def test_reject_unrecognized_source_boundary():
    with pytest.raises(ValueError,match='BOUNDARY_DRIFT'):latency.replace_once('abc','missing','x')

def test_guard_prevents_unauthorized_tick():
    def denied():raise PermissionError('denied')
    c,_=fake_controller()
    with pytest.raises(PermissionError,match='denied'):latency.tick(V43EventController.admit,denied)(c,900)

def test_module_namespace_keeps_guard_through_corrective_driver_clone():
    with latency.install(lambda:None):
        assert '_r039_require' in compare.__dict__
        assert '_r039_require()' in inspect.getsource(compare.run)

def test_parent_is_certified_and_old_actual_preserved():
    folder,cp,result=op.validate_parent()
    assert result['PASS'] and cp['kind']=='COMPLETED' and folder.name=='AIDC_FROZEN'

def test_live_batch_barrier_and_cpu_pool_are_preserved():
    source=inspect.getsource(op.run_batch)
    assert '_wait_for_repair()' in source
    assert 'reserve_pool' in source
    assert 'source_sha' in source
    assert 'terminate(' not in inspect.getsource(op.dispatch)
    assert 'suspend(' not in inspect.getsource(op.dispatch)

def test_dead_repair_owner_is_rejected():
    with patch.object(op,'alive',return_value=False):
        with pytest.raises(PermissionError,match='COORDINATOR_DEAD'):op.resource_owner({})

def test_batch_clone_routes_all_future_workers_to_the_latency_overlay():
    from v44_recovery_r038 import batch
    captured={}
    def compiled(function,body,suffix,**extra):
        captured.update(extra);captured['body']=body
        return lambda:None
    old=batch.launch
    with patch.object(latency,'compile_like',side_effect=compiled):op.run_batch({},None)
    assert captured['launch'] is not old
    assert '_wait_for_repair()' in captured['body']
    assert 'if not all_prepared' in captured['body']
    assert "range" not in inspect.getsource(captured['launch'])

def test_generated_shared_driver_keeps_guard_and_complete_physical_gates(tmp_path):
    from v44.worker import driver
    from v44.svr12_policy import corrective_driver
    import v43_corrective.compare as corrective
    with latency.install(lambda:None):
        shared=SimpleNamespace(**compare.__dict__)
        shared.run=driver(compare.run,tmp_path/'SHARED.py')
        binding=SimpleNamespace(arm='B1')
        run=corrective_driver(corrective.run,shared,binding,1746280800.)
        routed=run.__globals__['original']
        assert routed._r039_require is not None
        body=inspect.getsource(routed.run)
        assert "v['Fresh96_physical_PASS']" in body
        assert "v['Actual96_execution_PASS']" in body
        assert "and v['latency_within_900_seconds']" not in body
