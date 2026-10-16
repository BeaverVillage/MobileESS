"""Only B1/B3 opt in; baseline FCFS and all inherited Unknown methods stay intact."""
from v43_corrective.known_window import RelaxedKnownController,POLICY_ID
from v43_corrective.known_window import policy_assumption as original_assumption
from types import FunctionType


def research_assumption():
    return dict(original_assumption(),scope='NEW_V44_B1_B3_ACTUAL_EXPLICIT_OPT_IN',
        policy_id=POLICY_ID,status='IMPLEMENTED_NOT_EXECUTED')


def _submit():
    function=RelaxedKnownController.submit
    answer=FunctionType(function.__code__,dict(function.__globals__,policy_assumption=research_assumption),
        function.__name__,function.__defaults__,function.__closure__)
    answer.__kwdefaults__=function.__kwdefaults__
    return answer


class B3RelaxedKnownController(RelaxedKnownController):
    submit=_submit()
    def __init__(self,*args,**kwargs):
        if kwargs.get('arm')!='B3':raise ValueError('V44_B3_ADAPTER_ONLY')
        # The inherited constructor's arm gate is a selector, not a numerical policy.
        super().__init__(*args,**dict(kwargs,arm='B1'))
        self.arm='B3'


def controller_class(arm,policy=None):
    if arm in ('B0','B2'):
        if policy is not None:raise ValueError('BASELINE_FCFS_RESEARCH_POLICY_FORBIDDEN')
        from v43_baseline.worker import BaselineController
        return BaselineController
    if policy!=POLICY_ID:raise ValueError('V44_B1_B3_EXPLICIT_KNOWN_RESEARCH_POLICY_REQUIRED')
    if arm=='B1':return RelaxedKnownController
    if arm=='B3':return B3RelaxedKnownController
    raise ValueError('V44_ARM_AXIS')
