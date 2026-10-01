from .proof_policy import degen_diagnostic_allowed,proof_gate,select,BASE_LB
def result(label='PROOF_AUTO',moves=-1,ub=.6696147314213984,lb=BASE_LB,first=None,complete=180,wall=600):
    gap=abs(ub-lb)/abs(ub)
    return dict(label=label,settings=dict(DegenMoves=moves),passes=[dict(incumbent=ub,bound=lb,relative_gap=gap,quality_PASS=gap<=.005,work=100,solve_wall_seconds=wall,telemetry=dict(first_non_root_node_seconds=first,events=dict(root_relaxation_completion_seconds=complete)))])
def test_branch_alone_does_not_authorize():assert not proof_gate(result(first=190))['PASS']
def test_primal_improvement_alone_does_not_authorize():assert not proof_gate(result(ub=.60))['PASS']
def test_certified_bound_gain_authorizes():assert proof_gate(result(lb=BASE_LB+.001))['PASS']
def test_certified_gap_authorizes():assert proof_gate(result(ub=.572))['PASS']
def test_only_long_post_LP_delay_authorizes_DG0():
    assert degen_diagnostic_allowed(result())
    assert not degen_diagnostic_allowed(result(first=200))
    assert not degen_diagnostic_allowed(result(complete=None))
def test_bound_priority_over_primal():
    a=result(ub=.60);b=result('PROOF_DG0',0,lb=BASE_LB+.001)
    assert select([a,b])['selected']=='PROOF_DG0'
