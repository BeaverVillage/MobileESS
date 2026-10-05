"""Real overlap observation must not become permission to select timings."""
import v42_m1_accel_vnext.resources as resources


def test_observe_policy_runs_but_excludes_overlapping_timing(monkeypatch):
    blocked=[{'pid':12345,'optimize_state':'CONFIRMED_NATIVE_OPTIMIZE'}]
    monkeypatch.setattr(resources,'inspect_live',lambda excluded:(blocked,blocked))
    monkeypatch.setattr(resources,'resource_failures',lambda row,rows:[])
    written={}
    monkeypatch.setattr(resources,'write',lambda path,value:written.update({path.name:value}))
    monkeypatch.setattr(resources,'table',lambda *args:None)
    guard=resources.Guard('MOCK_OBSERVE',[],foreign_policy='observe')
    guard.gate()
    assert written['MOCK_OBSERVE_RESOURCE_ADMISSION.json']['state']=='ADMITTED'
    assert guard.foreign_seen and not guard.cancel.is_set()
    terminal=guard.close()
    assert terminal['failures']==['CONFIRMED_FOREIGN_NATIVE_OVERLAP']
    assert written['MOCK_OBSERVE_PROCESS_PROOFS.json']['guard_interruptions']==0
    assert written['MOCK_OBSERVE_PROCESS_PROOFS.json']['foreign_control_calls']==0


def test_observe_policy_keeps_physical_resource_failures(monkeypatch):
    blocked=[{'pid':12345}]
    monkeypatch.setattr(resources,'inspect_live',lambda excluded:(blocked,blocked))
    monkeypatch.setattr(resources,'resource_failures',lambda row,rows:['RAM_FLOOR'])
    monkeypatch.setattr(resources,'write',lambda *args:None)
    monkeypatch.setattr(resources,'table',lambda *args:None)
    guard=resources.Guard('MOCK_RESOURCE',[],foreign_policy='observe')
    assert guard.sample(True)==['RAM_FLOOR']
    assert guard.close()['failures']==['RAM_FLOOR','CONFIRMED_FOREIGN_NATIVE_OVERLAP']
