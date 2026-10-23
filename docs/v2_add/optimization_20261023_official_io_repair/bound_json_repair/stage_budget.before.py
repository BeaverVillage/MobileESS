"""V2_add-only measured Native budgets; frozen r043 files stay unchanged."""
from contextlib import contextmanager
from unittest.mock import patch
import ast,inspect,textwrap

A_SECONDS=7200.
JOINT_SECONDS=3600.
K48_SECONDS=300.
JOINT_CALL_CAP=300.
A_GAP=.005
M_GAP=.03

def policy():
    return dict(experiment_id='V2_add',basis='MEASURED_NATIVE_RUNTIME_ONLY',A_seconds=A_SECONDS,
        Joint_seconds=JOINT_SECONDS,K48_seconds=K48_SECONDS,Joint_call_cap=JOINT_CALL_CAP,
        A_gap=A_GAP,M_gap=M_GAP,model_build_and_independent_verification_charged_to_Native=False)

def m_result_metadata(original):
    """Correct only the historical output label, never optimizer control."""
    tree=ast.parse(textwrap.dedent(inspect.getsource(original)));changed=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.keyword) and node.arg=='operational_stage_budget_seconds':
            if not isinstance(node.value,ast.Constant) or node.value.value!=1800.:
                raise ValueError('ORIGINAL_M_RESULT_BUDGET_LABEL_DRIFT')
            node.value=ast.Constant(JOINT_SECONDS);changed.append(node)
    if len(changed)!=1:raise ValueError('ORIGINAL_M_RESULT_BUDGET_LABEL_BOUNDARY_DRIFT')
    ast.fix_missing_locations(tree);namespace=dict(original.__globals__)
    exec(compile(tree,original.__code__.co_filename,'exec'),namespace)
    return namespace[original.__name__]

def a_budget(path):
    from v42_may_campaign_native90.budget import DateBudget
    from .stage_common import read
    from .prestart_execution import atomic
    class Account(DateBudget):
        def persist(self):
            super().persist();value=read(self.path)
            value.update(policy_version='V2_ADD_A7200_MEASURED_RUNTIME',V2_add_budget_policy=policy())
            atomic(self.path,value)
    return Account(path,native_limit=A_SECONDS)

@contextmanager
def scope():
    import v44.budget as budget
    from .stage_common import read
    from .prestart_execution import atomic
    original=budget.StageBudget.persist
    def persist(self):
        original(self)
        value=read(self.path)
        value.update(policy_version='V2_ADD_A7200_K300_J3600_MEASURED_RUNTIME',V2_add_budget_policy=policy())
        atomic(self.path,value)
    # Keep the actual source class identity, solve guards and measured account.
    # Its checked constructor transformation changes only the stage ceiling.
    with patch.object(budget,'JOINT_SECONDS',JOINT_SECONDS),patch.object(budget,'JOINT_CALL_CAP',JOINT_CALL_CAP):
        constructor=budget._constructor()
        with patch.object(budget.StageBudget,'__init__',constructor),patch.object(budget.StageBudget,'persist',persist):
            yield
