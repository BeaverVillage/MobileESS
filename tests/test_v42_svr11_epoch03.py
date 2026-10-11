"""Contract correction and audited DSS cwd admission; no campaign optimization."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v42_svr11 import authority,processes
from v42_voltage_control import integration as subject

def engine(current=100.,power=0.):
    w=[1]
    return SimpleNamespace(
        Circuit=SimpleNamespace(AllNodeNames=lambda:['a.1','a.2','a.3','b.1','b.2','b.3'],AllBusMagPu=lambda:[1.]*6,
            SetActiveElement=lambda name:None,Losses=lambda:[0.,0.]),
        Lines=SimpleNamespace(AllNames=lambda:['none']),
        Transformers=SimpleNamespace(AllNames=lambda:['tx'],Name=lambda name:None,Wdg=lambda x:w.__setitem__(0,x),
            kV=lambda:1. if w[0]==1 else .5,kVA=lambda:100.),
        Properties=SimpleNamespace(Value=lambda name:'120'),
        CktElement=SimpleNamespace(NumConductors=lambda:4,NumTerminals=lambda:2,NumPhases=lambda:3,
            NodeOrder=lambda:[1,2,3,0,1,2,3,0],
            CurrentsMagAng=lambda:[current,0.,current,0.,current,0.,0.,0.,2*current,0.,2*current,0.,2*current,0.,0.,0.],
            Powers=lambda:[power,0.,power,0.,power,0.,0.,0.]*2))

@pytest.mark.parametrize('original,current,power,passes',[(True,100.,0.,True),(True,121.,0.,False),
    (True,100.,34.,False),(False,100.,0.,False)])
def test_original_normalamps_and_kva_added_phase_guard_independent(original,current,power,passes):
    token=authority._active.set(dict(original_transformer_current_authority='COMPILED_NORMALAMPS_ONLY'))
    try:r=subject.measure_full_network(engine(current,power),set(),{'transformer.tx':{}} if original else {})
    finally:authority._active.reset(token)
    assert r['PASS'] is passes
    assert r['original_transformer_current_authority']=='COMPILED_NORMALAMPS_ONLY'
    if original and current==100. and power==0.:
        assert r['original_nominal_phase_current_diagnostic_exceedance_cells']==6
        assert r['transformer_nameplate_current_violation_cells']==0
        assert all(c['nameplate_current_loading_pu']>1 for c in r['currents'])
    if not original:assert r['added_transformer_nameplate_current_violation_cells']==6
    if current==121.:assert r['transformer_current_violation_cells']==6
    if power==34.:assert r['transformer_kva_violation_cells']==2

def test_only_exact_audited_asset_parents_permitted_during_dss_compile(tmp_path):
    root=tmp_path/'checkout';assets=SimpleNamespace(**{k:tmp_path/k/'asset.dss' for k in ('master','pcc','ratings','phase_pv')})
    with patch('v42_common_campaign.authority.ROOT',root),patch('v42_regcontrol.authority.source',return_value={'assets':assets}):
        processes.verify_worker_cwd(root,root)
        for key in ('master','pcc','ratings','phase_pv'):processes.verify_worker_cwd(getattr(assets,key).parent,root)
        with pytest.raises(PermissionError,match='CHECKOUT_DRIFT'):processes.verify_worker_cwd(tmp_path/'master'/'untrusted',root)
        with pytest.raises(PermissionError,match='CODE_ROOT_DRIFT'):processes.verify_worker_cwd(root,tmp_path/'other-epoch')

def test_migration_waits_for_healthy_predecessor_without_launch_or_termination(tmp_path):
    from v42_svr11 import migration
    from v42_pr134_b1.common import atomic,read
    m={'execution_SHA':'3'*64}
    peer={'PID':123,'day':'2025-05-01'}
    with patch.object(migration,'verify',return_value=m),patch.object(migration,'predecessors',return_value=({},
         {'execution_SHA':'2'*64},[peer],[])),patch.object(migration,'subprocess') as subprocess:
        # Contract receipt is needed only for evidence in this mocked drain.
        with patch.object(migration,'predecessors',return_value=({'manifest':{}},{'execution_SHA':'2'*64},[peer],[])):
            r=migration.check(tmp_path)
        subprocess.run.assert_not_called()
    assert r['status']=='WAITING_PREDECESSOR_DRAIN'
    assert r['healthy_workers_terminated']==r['scientific_results_promoted']==0
    assert read(tmp_path/'MIGRATION_STATUS.json')['predecessor_workers']==[peer]
