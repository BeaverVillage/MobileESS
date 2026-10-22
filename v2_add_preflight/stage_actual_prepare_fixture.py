"""Instantiate real same-date source case/controller/policy IO, no Actual run."""
import uuid
from .stage_common import *
from v42_native.contracts import digest
from .prestart_native import native_zero


def certify():
    with measured('ACTUAL_SOURCE_POLICY_PREPARATION.json') as (report,start),native_zero() as denied:
        from .stage_reference import prepare
        from .stage_actual_handler import binding
        from .stage_actual import CurrentAC,controller_type
        from .full_weather import observations
        from v43_corrective.policy import CorrectivePolicy
        from v44.config import KNOWN_POLICY
        folder=WORK/('ACTUAL_PREPARE_FIXTURE_'+uuid.uuid4().hex[:8]);folder.mkdir()
        reference_folder=folder/'R0';prepare(reference_folder)
        adapter=binding('B1',reference_folder,fixture=True)
        args,case=adapter.prepare(folder/'CASE')
        reference,packet,bindings,proof=adapter.build(args,case,folder/'POLICY')
        obs=observations(day_inputs(),args['begin'],args['end'])
        oracle=CurrentAC(issue_seconds=args['begin'],sites=reference.sites,power_model=args['power_model'],observations=obs)
        policy=CorrectivePolicy(reference,packet,variant='C1',oracle=oracle,bindings=bindings,expected_bindings=bindings,evidence_scope='REAL_V2_ADD_SOURCE_YY_PREPARATION')
        policy.spec.pop('original_7_RegControl_hardware_required',None)
        policy.spec.update(hardware=packet.authority['hardware'],original_RegControl=12,additional_serial_SVR_banks=3)
        policy.sha=digest(policy.spec)
        policy.bind_observed_c1(args['power_model'],current_weather_provider=lambda when:obs.at(when,observed_now=oracle.now)['weather']['values'])
        policy.require_bindings(bindings)
        classes={a:controller_type(a,known_policy=KNOWN_POLICY if a in ('B1','B3') else None,
            initial_running=args['running'],rack_limits=packet.rack_compatibility) for a in ('B0','B1','B2','B3')}
        rejected=False
        try:binding('B1',reference_folder)
        except ValueError as e:
            assert str(e)=='ACCEPTED_FULL_AIDC_REQUIRED';rejected=True
        assert rejected
        report.update(PASS=True,fixture_reference_not_accepted_as_production_A1=True,
            source_case_jobs=len(args['requests'])+len(args['running']),case_sha=case['case_sha'],
            source_tracking_reference=reference.sha,bindings=bindings,CC4=proof['CC4'],
            original_controller_classes={a:c.__module__+'.'+c.__name__ for a,c in classes.items()},
            actual_CurrentAC_type=type(oracle).__module__+'.'+type(oracle).__name__,
            frozen_power_authority=args['power_model'].authority_sha,policy=policy.spec,
            output=str(folder),denied_attempts=denied,Actual_event_runs=0,Fresh120_runs=0,
            scope='Real dated full input and source policy/controller construction; no optimized B1/B3 physical outcome claimed')


if __name__=='__main__':certify()
