"""Per-arm frozen decisions, shared unchanged event/Source/control contracts."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from v43.common import DOC,ROOT,read,record,verify_records,atomic
from v43_actual.vendor.policy import digest
from v43_actual.vendor.known_commands import compile_known_commands
from v43_actual.vendor.trajectory_tracking import TrackingReference
from v43_actual.vendor.sensitivity_policy import OriginalGridPacket
from v43_actual.vendor.aidc_sensitivity_runtime import anonymous_cohort_residual
from v43_actual.case import BUNDLE,accepted


class ArmBinding:
    def __init__(self,arm,reference_folder,mess_plan=None):
        if arm not in ('B0','B2','B3'):raise ValueError('EXPLICIT_FINAL_ARM_REQUIRED')
        self.arm=arm;self.folder=Path(reference_folder);self.mess=mess_plan
        if arm in ('B2','B3') and mess_plan is None:raise ValueError('FULL_FEASIBLE_MESS_PLAN_REQUIRED')
        self.aidc=read(self.folder/'AIDC_REFERENCE.json')
        identity=self.aidc['identity']
        self.aidc['aidc_anchor']=identity['aidc_anchor']
        verify_records(identity['source']+[identity['input'],identity['windows'],identity['reference'],identity['physical']])
        with np.load(identity['physical']['path'],allow_pickle=False) as z:self.arrays={k:z[k].copy() for k in z.files}
        self.anchor=identity['aidc_anchor'];self.freeze=record(self.folder/'AIDC_REFERENCE.json')

    def prepare(self,output,*,private_service=True):
        from v43_actual.case import prepare
        import shutil
        # Shared issue initialization is an input assumption, independent of
        # AIDC/MESS decisions. Its existing source and exact capacity replay
        # are checked again by prepare/verified_initial_sites.
        existing=Path('D:/MobileESS_V43/runtime/gate_b_c0_c1_actual96_attempt001/CASE/INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json')
        target=Path(output)/'INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json'
        if existing.is_file() and not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(existing,target)
        args,case=prepare(output,private_service=private_service)
        args['arm']=self.arm
        args['known_schedule']=compile_known_commands(self.aidc['selected_jobs'],slot_zero_seconds=args['begin'],
            gpu_by_uid={r['job_uid']:r['GPU_gang'] for r in accepted()[2]['known_population']})
        case=dict(case,arm=self.arm,case_sha=digest(dict(shared_event_case=case['case_sha'],
            AIDC_reference=self.freeze,MESS=self.mess)),Known_commands_sha=digest(args['known_schedule']),
            known_commands=len(args['known_schedule']),Final_AIDC_reference=self.freeze,
            Final_MESS_plan_sha=digest(self.mess),Golden003_role='COMMON_PR189_INPUT_ONLY_NOT_ARM_OPTIMIZED_COMMANDS')
        args['qos_window_provider'].case_sha=case['case_sha']
        atomic(Path(output)/'CASE_BINDINGS.json',case)
        return args,case

    def build(self,args,case,output):
        from v42_pr134_b1.native import bind
        from v42_integrated.contract import physical_authority
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
        cert,freeze,native,windows,_=accepted()
        folder=Path(freeze['scientific_input']['NATIVE_INPUT.json']['path']).parent
        with physical_authority():_,_,coeff,power,idle,swing=bind(native,folder,output/'ORIGINAL_LOAD_ONLY')
        arrays=self.arrays;sites=tuple(map(str,arrays['sites']))
        cc4_binding=read(BUNDLE.parents[2]/'MAY_CC4_BINDING.json')
        kernel=ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv'
        timing=ROOT/'docs/v42_ts_cc4_temporal_refinement/CC4_SERVICE_TIMING_ENVELOPE.csv'
        if record(kernel)['sha256']!=cc4_binding['kernel']['sha256']:raise ValueError('ORIGINAL_CC4_KERNEL_CHANGED')
        verify_records([cc4_binding['interface']['prediction']])
        envelope=pd.read_csv(timing)
        bindings=dict(science_sha=digest(dict(original_source=cert['source_freeze'],arm_adapter=record(__file__))),
            case_sha=case['case_sha'],physical_sha=native['electrical_certificate']['sha256'],
            time_axis_sha=digest(dict(issue=args['begin'],D00=args['begin']+21600,end=args['end'],dt=900)),
            qos_sha=digest(dict(Known=freeze['scientific_input']['WINDOWS.json'],Unknown=case['source_receipts'][4])),
            cc4_sha=cc4_binding['interface']['prediction']['sha256'],runtime_sha=native['runtime_provider']['sha256'],
            response_sha=digest(sorted({c.coefficient_sha256 for c in coeff})),
            initial_state_sha=read(case['initialization']['path'])['initialization_sha'],aidc_anchor=self.anchor,
            interface_sha=digest(dict(contract='V43_PR189_PENDING_PRESITE',basic='CAUSAL_GRID_BLIND_REFERENCE',
                source_change='UID_DESTINATION_CONSENT_AND_READY_DATA',Known_commands_modified=False)))
        if self.mess is None:
            mess_sites=sorted({name.split('[',1)[1][:-1] for name in coeff[0].control_names if name.startswith('mess_')})
            mess=dict(P_by_site={s:[0.]*96 for s in mess_sites},Q_by_site={s:[0.]*96 for s in mess_sites},
                units=4,initial_sites=native['initial_MESS_sites'],authority='B0_NO_MESS_OPTIMIZATION')
            mess['plan_sha']=digest(mess)
        else:mess=self.mess
        bindings['mess_anchor']=mess['plan_sha']
        cc4_authority=dict(model_id=cc4_binding['interface']['model'],prediction_sha=bindings['cc4_sha'],
            kernel_sha=record(kernel)['sha256'],timing_envelope_sha=record(timing)['sha256'],aidc_anchor=self.anchor,
            q50_hourly_GPUh=native['C0_Q50'],q90_hourly_GPUh=native['C0_Q90'],
            forecast_modifications=0,future_Actual_or_UID_inputs_used=False)
        identity=dict(CC4_Q50=native['C0_Q50'],CC4_Q90=native['C0_Q90'],CC4_service=self.aidc['CC4_service'],
            CC4_carryout=self.aidc['CC4_carryout'],Timing_CDF_Q10=envelope.Q10.tolist(),Timing_CDF_Q90=envelope.Q90.tolist(),
            CC4_source_authority=cc4_authority,C1_Power_Model_SHA=args['power_model'].authority_sha,
            final_AIDC=self.freeze,final_MESS_sha=digest(mess),initial_state=case['initialization'])
        reference=TrackingReference(arrays['known_gpu'],arrays['cc4_served_gpu'],arrays['IT_kw'],arrays['PCC_P_kw'],
            arrays['PCC_Q_kvar'],sites=sites,begin=args['begin']+21600,commands=args['known_schedule'],identity=identity)
        authority=SimpleNamespace(voltage_lower_squared=.95**2,voltage_upper_squared=1.05**2,
            transformer_current_authority_sha256=coeff[0].transformer_current_authority_sha256)
        with physical_authority():
            packet=OriginalGridPacket(coeff,power,swing,native['capacities'],self.aidc,mess,authority,bindings,
                begin_seconds=reference.begin,known_gpu=arrays['known_gpu'],power_factor=.95,
                rack_compatibility=read(BUNDLE/'PLANNING_INPUT_BUNDLE.json')['rack_compatibility'],
                mess_validation=dict(plan_sha=mess['plan_sha'],frozen_execution_validated=True,
                    evidence=self.freeze if self.mess is None else mess.get('case_binding'),scope='FINAL_ARM_FROZEN_MESS'))
        _,cohort=anonymous_cohort_residual(reference,{},reference.begin)
        if cohort['status']!='SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS':
            raise ValueError('FINAL_ARM_CC4_REFERENCE_NOT_CERTIFIED:'+str(cohort))
        receipt=dict(PASS=True,Native_calls=0,arm=self.arm,reference_target_sha=reference.sha,bindings=bindings,
            CC4=cohort,final_AIDC=self.freeze,final_MESS_plan_sha=digest(mess),
            electrical_coefficients_regenerated=False,C1_refitted=False,UB_LB_transferred=False)
        reference.save(output/'REFERENCE.npz');atomic(output/'REFERENCE_PROOF.json',receipt)
        return reference,packet,bindings,receipt
