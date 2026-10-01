from .policy import select,meaningful,isolation_allowed,BASE_LB,BASE_GAP
from .telemetry import Telemetry,parse
def receipt(label,first=None,bound=BASE_LB,nodes=1,gap=BASE_GAP):
    return dict(label=label,settings=dict(CutPasses=int(label[-1])),passes=[dict(status=9,quality_PASS=gap<=.005,bound=bound,relative_gap=gap,nodes=nodes,work=10,solve_wall_seconds=600.2,telemetry=dict(first_non_root_node_seconds=first,checkpoints={'600':dict(bound=bound,relative_gap=gap)}))])
def test_early_tree_entry_authorizes():
    result=select(receipt('CP0',250),receipt('CP1'))
    assert result['selected']=='CP0' and result['production_authorized']
def test_bound_rank_precedes_node_volume():
    result=select(receipt('CP0',250,nodes=1000),receipt('CP1',350,bound=BASE_LB+.01,nodes=10))
    assert result['selected']=='CP1'
def test_root_stuck_does_not_authorize_production():
    a,b=receipt('CP0'),receipt('CP1')
    assert isolation_allowed(a,b) and not select(a,b)['production_authorized']
def test_one_prompt_primary_blocks_H0():
    assert not isolation_allowed(receipt('CP0',299),receipt('CP1'))
def test_bound_improvement_gate_without_branch():
    assert meaningful(receipt('CP0',bound=BASE_LB+.0002))['PASS']
def test_material_gap_gate():
    assert meaningful(receipt('CP0',gap=BASE_GAP-.002))['PASS']
    assert not meaningful(receipt('CP0',gap=BASE_GAP-.00001))['PASS']
def test_checkpoint_does_not_use_future_observation():
    t=Telemetry();t.observe(290,'MIP',1,.5,0);t.observe(301,'MIP',1,.8,2)
    s=t.checkpoint(300,600)
    assert s['bound']==.5 and s['observation_age_seconds']==10
def test_early_completion_has_no_fabricated_600_state():
    assert not Telemetry().checkpoint(600,250)['reached']
def test_post_root_gain_from_native_callbacks():
    t=Telemetry();t.message(190,'Root relaxation: objective 0.5, 1 iterations, 180 seconds\n');t.node(191,0,1,.5,.5);t.node(220,0,1,.6);t.node(240,1,1,.6)
    result=t.summary(600)
    assert result['post_lp_root_seconds']==50 and abs(result['root_cut_bound_gain']-.1)<1e-12
def test_all_cut_families_preserved():
    r=parse('Cutting planes:\n  MIR: 1818\n  BQP: 643\n\nExplored 1 nodes')
    assert r['cut_counts']==dict(MIR=1818,BQP=643)
