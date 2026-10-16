"""Selective invocation of the unchanged sequential C0/C1 event comparison."""
from functools import partial
from pathlib import Path
from types import FunctionType
import sys

from v43.common import ROOT,read,record,verify_records,atomic,git,now
from v43_actual import compare as original
from .actual import ArmBinding
from .current_ac import ArmCurrentAC
from .controller import UniformArmController


def run(arm,reference_folder,output,mess_result=None):
    output=Path(output)
    sources=[record(p) for folder in ('v43_arms','v43_actual') for p in sorted((ROOT/folder).rglob('*.py'))]
    sources += [record(ROOT/'v43/common.py')]
    mess=None
    if mess_result is not None:
        result=read(mess_result)
        if result.get('FULL_feasible') is not True or not result.get('MESS_plan'):
            raise ValueError('ACTUAL_REQUIRES_CURRENT_FULL_FEASIBLE_FROZEN_MESS')
        if result['arm']!=arm:raise ValueError('FINAL_MESS_ARM_DRIFT')
        mess=result['MESS_plan'];sources.append(record(mess_result))
    binding=ArmBinding(arm,reference_folder,mess)
    freeze=output.with_name(output.name+'.ARM_SOURCE_FREEZE.json')
    if output.exists() or freeze.exists():raise ValueError('NEW_ARM_ACTUAL_ATTEMPT_REQUIRED')
    atomic(freeze,dict(UTC=now(),arm=arm,source_commit=git('rev-parse','HEAD').decode().strip(),
        sources=sources,AIDC_reference=binding.freeze,MESS_sha=binding.mess and binding.mess['plan_sha'],
        shared_worker=record(original.__file__),source_namespace_adaptations=['prepare','planning reference','frozen MESS Current AC']))
    from .planning_ac import run as planning_replay
    # The same shared locks serialize this fresh planning check before Actual.
    planning_replay(binding,output.with_name(output.name+'.PLANNING_AC96.json'))
    # Reuse the exact comparison body and all event/controller/lock/Native0
    # algorithms. Only the explicit frozen-arm inputs and AC mapper differ.
    namespace=dict(original.__dict__,prepare=binding.prepare,build=binding.build,
        V43EventController=UniformArmController,
        OriginalCurrentAC=partial(ArmCurrentAC,mess_plan=mess,
            day_start_seconds=__import__('datetime').datetime.fromisoformat('2025-05-01T00:00:00+10:00').timestamp()))
    function=FunctionType(original.run.__code__,namespace,original.run.__name__,original.run.__defaults__,original.run.__closure__)
    function.__kwdefaults__=original.run.__kwdefaults__
    verify_records(sources)
    result=function(output,control_slots=120)
    verify_records(sources)
    atomic(output/'ARM_BINDING_RESULT.json',dict(arm=arm,source_freeze=record(freeze),
        final_AIDC_reference=binding.freeze,final_MESS_plan_sha=None if mess is None else mess['plan_sha'],
        Actual96_PASS=result['Actual96_PASS'],Fresh96_PASS=result['Fresh96_PASS'],
        shared_actual_result=record(output/'RESULT.json')))
    return result


if __name__=='__main__':run(*sys.argv[1:])
