"""Named finite real source event run, not a campaign or real AC certificate."""
import copy,sys
import numpy as np
from .stage_common import *
from .stage_work import validate
from .stage_actual import controller_type
from .prestart_native import native_zero


def certify():
    with measured('ACTUAL_MIGRATION_EVENT_FIXTURE.json') as (report,start),native_zero() as denied:
        sys.path.insert(0,str(ROOT/'tests'))
        from test_v43_corrective import policy,request,stats
        from v43_actual.windows import OriginalKnownWindows
        from v43_corrective.reference import CorrectedReferenceScheduler
        from v43_actual.vendor.actual import run_actual
        from v42_capacity.actual import Environment
        from v44.config import KNOWN_POLICY
        cases=[]
        for arm in ('B1','B3'):
            p,*_=policy('C1');uid='V2_ADD_NAMED_KNOWN_MIGRATION'
            cap=dict(source_sha=digest('NAMED_MIGRATION_CAPABILITY'),checkpoint_authorized=True,
                allowed_destinations=['B'],gpu_type_confirmed=True,rack_gang_confirmed=True,data_residency_confirmed=True,
                wan_path='A_B',route_links=['NAMED_LINK'],bandwidth_bytes_per_second=1e6,payload_bytes=900e6,
                restart_seconds=900.,source_wait_seconds=0.,source_hold_until='transfer_start',destination_hold_from='transfer_end')
            commands={uid:dict(site='A',start_seconds=0.,migration_destination='B',physical_checkpoint_seconds=1800.,
                checkpoint_control_seconds=1800.,migration_capability=cap,
                protected_segments=[dict(resource='gpu:A',begin=0.,end=1800.,quantity=1),
                    dict(resource='gpu:B',begin=2700.,end=7200.,quantity=1)])}
            qos=OriginalKnownWindows(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('NAMED_PROVIDER'),
                windows=[dict(job_id=uid,reference_start=0,latest_start=4,allowed_starts=list(range(5)))],issue_seconds=0.)
            r=request(uid,site='A',q50=5400.,origin_unknown=False,reference_start_seconds=0.,
                Can_Checkpoint_Migrate=True,migration_capability=cap)
            args=dict(capacities={'A':1,'B':1},requests=[r],running=[],environment=Environment({uid:5400.}),
                begin=0.,end=10800.,qos_window_provider=qos,reference=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF'),
                known_schedule=commands,wan_capacities={'A_B':1e6,'LINK::NAMED_LINK':1e6})
            instances=[];source_type=controller_type(arm,known_policy=KNOWN_POLICY)
            def controller(*a,**kw):
                instance=source_type(*a,**kw);instances.append(instance);return instance
            actual=run_actual(**args,arm=arm,frozen_policy=p,controller_class=controller,expected_bindings=p.bindings)
            assert len(actual['migration_receipts'])==1
            cert,rows=validate(actual,args,allow_known_research=True);assert cert['PASS'] and cert['Source_QoS_PASS']
            history=np.asarray([r['GPU'] for r in instances[0].prefix_history])
            assert np.max(abs(history-actual['occupancy_GPU'][:len(history)]))<1e-12
            rejected=[]
            for kind in ('compute','WAN','phase'):
                changed=copy.deepcopy(actual)
                if kind=='compute':changed['compute_occupancy_GPU'][0,0]+=.1
                if kind=='WAN':changed['migration_receipts'][0]['segments'][1]['quantity']*=2
                if kind=='phase':changed['job_event_ledger']=[e for e in changed['job_event_ledger'] if e['event']!='DESTINATION_RUNNING']
                try:bad,_=validate(changed,args,allow_known_research=True);ok=not bad['PASS']
                except (AssertionError,ValueError):ok=True
                assert ok;rejected.append(kind)
            cases.append(dict(arm=arm,PASS=True,independent_work=cert,public_prefix_equals_actual_occupation=True,
                rejected_tampering=rejected,original_known_commands_unchanged=commands==instances[0].known_schedule,
                source_controller_MRO=[c.__module__+'.'+c.__name__ for c in source_type.__mro__]))
        report.update(PASS=True,cases=cases,denied_attempts=denied,scope='Named 2-site/1-job event migration and independent work/WAN/prefix IO fixture only',
            IEEE8500_AC_executed=False,official_actual120_result_claimed=False,
            source_test_helpers=[record(ROOT/'tests/test_v43_corrective.py'),record(ROOT/'tests/test_v43_actual_port.py')])


if __name__=='__main__':certify()
