"""Original case chain with a named, authenticated conditional A2 handoff."""
import inspect,textwrap
from v44 import campaign
from v44.common import read,atomic
from pathlib import Path


def run_case(request):
    source=textwrap.dedent(inspect.getsource(campaign.run_case))
    old='    from .stages import require_a2'
    assert source.count(old)==1
    source=source.replace(old,'    from v44_recovery_r028.voltage_policy import require_handoff as require_a2')
    ns=dict(campaign.run_case.__globals__);exec(compile(source,__file__+'.generated','exec'),ns)
    result=ns['run_case'](request)
    for stage in ('A1','A2'):
        path=Path(request['case_root'])/stage/'RESULT.json'
        if path.exists() and read(path).get('classification')=='PHASE_I_NATIVE_1500_LIMIT_REACHED':
            result.update(PASS=False,status='FAILED',classification='PHASE_I_NATIVE_1500_LIMIT_REACHED',failed_stage=stage)
            atomic(Path(request['case_root'])/'RESULT.json',result)
    return result
