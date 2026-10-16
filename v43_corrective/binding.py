"""Keep per-arm Planning decisions; version only the corrective Actual case."""
from copy import deepcopy
from pathlib import Path
import shutil

from v43.common import atomic,record,ROOT
from v43_actual.vendor.policy import digest
from v43_actual import case as original_case
from v43_actual import planning_reference
from v43_arms.actual import ArmBinding
from . import POLICY_ID
from .reference import CorrectedReferenceScheduler


class CorrectiveBinding:
    def __init__(self,arm,reference_folder=None,mess_plan=None):
        if arm not in ('B0','B1','B2','B3'):raise ValueError('MAY01_FINAL_ARM_REQUIRED')
        self.arm=arm;self.mess=mess_plan
        self.base=None if arm=='B1' else ArmBinding(arm,reference_folder,mess_plan)
        if arm=='B1' and mess_plan is not None:raise ValueError('B1_MESS_MUST_REMAIN_ZERO')

    def prepare(self,output,*,private_service=True):
        output=Path(output)
        source=Path('D:/MobileESS_V43/runtime/gate_b_c0_c1_actual96_attempt001/CASE/INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json')
        target=output/'INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json'
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        factory=original_case.prepare if self.base is None else self.base.prepare
        args,case=factory(output,private_service=private_service)
        from .public_metadata import build as request_metadata,attach
        descriptors=request_metadata(ROOT/'docs/v43/V43_R1_RECORDED_REQUEST_DESCRIPTOR_CACHE.json')
        attach(args,descriptors)
        old=args['reference'];state=deepcopy(old.to_dict())
        atomic(output/'UNCORRECTED_REFERENCE_SEED.json',state)
        reference=CorrectedReferenceScheduler.from_dict(state)
        reference.reference_sha=digest(dict(original=old.reference_sha,policy=POLICY_ID,
            fixed_Known_commands=digest(args['known_schedule']),rule='SITE_LOCAL_NOMINAL_RESERVATIONS_NO_GLOBAL_START_BARRIER'))
        reference.reservations={s:[] for s in reference.capacities}
        initial_running={r.uid for r,s,t in args['running']}
        for uid,row in reference.assigned.items():
            row['reference_sha']=reference.reference_sha
            if uid in initial_running:
                reference.reservations[row['reference_site']].append((args['begin'],row['nominal_release_seconds'],
                    next(r.gpu for r,s,t in args['running'] if r.uid==uid)))
        for uid,command in args['known_schedule'].items():
            if uid in initial_running:continue
            for s in command.get('protected_segments',[]):
                if s['resource'].startswith('gpu:'):
                    reference.reservations[s['resource'][4:]].append((s['begin'],s['end'],s['quantity']))
        args['reference']=reference
        case=dict(case,strict_parent_case_sha=case['case_sha'],policy_version=POLICY_ID,
            case_sha=digest(dict(parent=case['case_sha'],policy=POLICY_ID,
                request_descriptors=record(ROOT/'docs/v43/V43_R1_RECORDED_REQUEST_DESCRIPTOR_CACHE.json'),
                current_C1_model=args['power_model'].authority_sha,
                corrective_sources=[record(ROOT/'v43_corrective'/name) for name in (
                    '__init__.py','binding.py','reference.py','participation.py','policy.py',
                    'controller.py','current_ac.py','compare.py','public_metadata.py','performance.py')])),
            reference_sha=reference.reference_sha,Known_commands_sha=digest(args['known_schedule']),
            future_Known_global_Unknown_start_barrier=False,Strict_parent_raw_modified=False,
            R1='ASSUMED_ARRIVAL_HASH30',R2='HOLD',Actual96_PASS=False,Fresh96_PASS=False)
        args['qos_window_provider'].case_sha=case['case_sha']
        atomic(output/'CASE_BINDINGS.json',case)
        return args,case

    def build(self,args,case,output):
        return (planning_reference.build if self.base is None else self.base.build)(args,case,output)
