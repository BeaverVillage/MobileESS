"""Separate attempt/source freeze over the unchanged sequential Actual driver."""
from functools import partial
from pathlib import Path
from types import FunctionType
import argparse
import inspect
import textwrap

from v43.common import ROOT,atomic,read,record,verify_records,git,now
from v43_actual import compare as original
from . import POLICY_ID
from .binding import CorrectiveBinding
from .controller import CorrectiveController
from .policy import CorrectivePolicy
from .current_ac import FullPrefixReferenceAC,CertifiedPrefixAC,ShadowCertifiedPrefixAC


def run(arm,output,*,reference_folder=None,mess_result=None,control_slots=120,correction_proof=None,
        ac_mode='SHADOW',ac_certification=None,variants=('C0',)):
    output=Path(output);freeze=output.with_name(output.name+'.CORRECTIVE_SOURCE_FREEZE.json')
    if output.exists() or freeze.exists():raise ValueError('NEW_CORRECTIVE_ACTUAL_ATTEMPT_REQUIRED')
    variants=tuple(variants)
    if variants not in (('C0',),('C0','C1')):raise ValueError('EXPLICIT_SUPPORTED_CONTROL_VARIANTS_REQUIRED')
    if control_slots not in (1,25,120):raise ValueError('SUPPORTED_CORRECTIVE_HORIZON_REQUIRED')
    if ac_mode not in ('FULL_REFERENCE','SHADOW','FAST'):raise ValueError('EXPLICIT_CURRENT_AC_MODE_REQUIRED')
    if control_slots==120 and ac_mode!='FAST':raise ValueError('NO_NEW_FULL_ACTUAL_WITH_UNCERTIFIED_FULL_PREFIX_PATH')
    if ac_mode=='FAST':
        if ac_certification is None:raise ValueError('REAL_PREFIX_AND_PAIRED_EVENT_CANARY_CERTIFICATION_REQUIRED')
        cert=read(ac_certification);verify_records([cert['optimized_source']])
        if (cert.get('production_fast_path_authorized') is not True or
                cert.get('paired_actual_UID_site_time_GPU_exact') is not True or
                cert['optimized_source']['sha256']!=record(ROOT/'v43_corrective/current_ac.py')['sha256']):
            raise ValueError('CURRENT_AC_CERTIFICATION_NOT_FOR_THIS_SOURCE')
    mess=None
    if mess_result:
        result=read(mess_result)
        if result.get('FULL_feasible') is not True or result['arm']!=arm:raise ValueError('FROZEN_ARM_FULL_MESS_REQUIRED')
        mess=result['MESS_plan']
    binding=CorrectiveBinding(arm,reference_folder,mess)
    sources=[record(p) for folder in ('v43_corrective','v43_actual','v43_arms')
        for p in sorted((ROOT/folder).rglob('*.py'))]+[record(ROOT/'v43/common.py')]
    if mess_result:sources.append(record(mess_result))
    proof=None if correction_proof is None else read(correction_proof)
    if correction_proof:sources.append(record(correction_proof))
    if ac_certification:sources.append(record(ac_certification))
    atomic(freeze,dict(UTC=now(),arm=arm,policy_version=POLICY_ID,source_commit=git('rev-parse','HEAD').decode().strip(),
        sources=sources,control_slots=control_slots,physical_bands_changed=False,
        parent_Golden003_reoptimized=False,Strict_outputs_overwritten=False,ac_mode=ac_mode,variants=variants))
    policies=[];controllers=[];oracles=[]
    def policy(*args,**kwargs):
        kwargs['evidence_scope']='REAL_V43_R1_FLEX30_CORRECTIVE'
        p=CorrectivePolicy(*args,correction_proof=proof,**kwargs);policies.append(p);return p
    def controller(*args,**kwargs):
        p=CorrectiveController(*args,**kwargs);controllers.append(p);return p
    def oracle(*args,**kwargs):
        cls={'FULL_REFERENCE':FullPrefixReferenceAC,'SHADOW':ShadowCertifiedPrefixAC,'FAST':CertifiedPrefixAC}[ac_mode]
        p=cls(*args,mess_plan=mess,day_start_seconds=1746021600.,**kwargs);oracles.append(p);return p
    namespace=dict(original.__dict__,prepare=binding.prepare,build=binding.build,
        IssueContinuityPolicy=policy,V43EventController=controller,
        OriginalCurrentAC=oracle,__selected_variants=variants)
    # Fresh always takes the independent original sequential all-measurement
    # path, even when admission uses certified historical proof reuse.
    body=textwrap.dedent(inspect.getsource(original.run))
    if body.count('fresh=oracle._probe(rows)')!=1:raise ValueError('INDEPENDENT_FRESH_REUSE_BOUNDARY_DRIFT')
    body=body.replace('fresh=oracle._probe(rows)','fresh=oracle.full_fresh_probe(rows)')
    if body.count("for variant in ('C0','C1'):")!=1:raise ValueError('EXPLICIT_VARIANT_REUSE_BOUNDARY_DRIFT')
    body=body.replace("for variant in ('C0','C1'):",'for variant in __selected_variants:')
    exec(compile(body,__file__,'exec'),namespace);function=namespace['run']
    verify_records(sources);result=function(output,control_slots=control_slots);verify_records(sources)
    atomic(output/'CORRECTIVE_POLICY_RECEIPTS.json',dict(arm=arm,policy_version=POLICY_ID,
        source_freeze=record(freeze),policies=[dict(variant=p.variant,spec=p.spec,sha=p.sha,
            current_diagnostics=p.current_diagnostics,candidate_funnel=p.funnel) for p in policies],
        controllers=[dict(variant=c.policy.variant,participation=list(c.participation.receipts.values()),
            overruns=c.overrun_observations,Known_commands_unchanged=c.known_schedule==c._frozen_known_commands)
            for c in controllers],independent_Actual_and_Fresh=record(output/'RESULT.json')))
    for index,o in enumerate(oracles):
        folder=output/variants[index]
        if not folder.exists():folder.mkdir()
        if isinstance(o,CertifiedPrefixAC):atomic(folder/'PREFIX_CERTIFICATES.json',o.certificates())
        atomic(folder/'AC_ALGORITHM_METRICS.json',dict(mode=ac_mode,Current_AC_calls=o.calls,
            counters=o.performance,equivalence=getattr(o,'equivalence',[]),
            independent_fresh_used=True,state_clone_claimed=False))
    atomic(output/'CORRECTIVE_CERTIFICATION_STATUS.json',dict(policy_version=POLICY_ID,
        PLANNING_FULL_PASS='PRESERVED_PARENT_CERTIFICATE_ONLY',PLANNING_GLOBAL_GAP_PASS='PRESERVED_PARENT_STAGE_ONLY',
        KNOWN_FROZEN_COMMAND_PASS=all(c.known_schedule==c._frozen_known_commands for c in controllers),
        UNKNOWN_REFERENCE_CORRECTION_PASS='NATIVE0_COUNTEREXAMPLES_PASS_EVENT_UID_AUDIT_REQUIRED',
        R1_FLEX30_ASSUMED=True,OVERRUN_CORRECTIVE_CONTROL_PASS='PENDING_INDEPENDENT_EVENT_AUDIT',
        ACTUAL_SERVICE_PASS='NOT_CERTIFIED_PENDING_UID_AND_GPUH_AUDIT',FRESH_AC96_PASS=result['Fresh96_PASS'],
        QOS_PASS='PENDING_INDEPENDENT_DEADLINE_AUDIT',legacy_driver_PASS_scope='EXECUTION_AND_PHYSICAL_ONLY'))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('arm');p.add_argument('output');p.add_argument('--reference-folder')
    p.add_argument('--mess-result');p.add_argument('--control-slots',type=int,default=120);p.add_argument('--correction-proof')
    p.add_argument('--ac-mode',choices=['FULL_REFERENCE','SHADOW','FAST'],default='SHADOW');p.add_argument('--ac-certification')
    a=p.parse_args();run(a.arm,a.output,reference_folder=a.reference_folder,mess_result=a.mess_result,
        control_slots=a.control_slots,correction_proof=a.correction_proof,ac_mode=a.ac_mode,ac_certification=a.ac_certification)
