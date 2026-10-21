"""Strict FULL acceptance adapter, shared by cached A1 and newly solved A1/A2.

An ACCEPTED label is never a feasible point. Every original option and joint
resource row is independently rechecked before publishing/reusing the point.
"""
from collections import defaultdict
from dataclasses import replace
import types
from pathlib import Path

from .prestart import digest, record

class AcceptanceError(ValueError):
    def __init__(self,certificate):
        self.certificate=certificate
        super().__init__('ORIGINAL_FULL_ACCEPTANCE_REJECTED:'+digest(certificate))

def source_domain(bundle, windows):
    """Same native_jobs constructor; only original finite WINDOWS binding.

    Clone globals to route file identity lookups without writing original OUT.
    This matches v42_pr134_b1.native.bind.load_native's domain operation.
    """
    from v42_temporal.native import native_jobs
    from v42_native.contracts import digest as original_digest
    by={r['job_id']:r for r in windows}
    ledger={u:dict(can_timeshift=r['can_timeshift'],TS_slots=r['latest_start']-r['reference_start']) for u,r in by.items()}
    # Constructor only consumes these two receipts for boundary identity. Bind
    # to actual current objects rather than misleading historical disk paths.
    identities={'TS_HIERARCHICAL_BACKOFF_AUTHORITY.json':original_digest(windows),
                'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json':original_digest(bundle)}
    ns=dict(native_jobs.__globals__,sha=lambda p:identities[Path(p).name])
    fn=types.FunctionType(native_jobs.__code__,ns,argdefs=native_jobs.__defaults__)
    jobs,bounds,seconds,resources,raw=fn(bundle,ledger)
    for uid in bounds:bounds[uid]=replace(bounds[uid],allowed_starts=tuple(by[uid]['allowed_starts']))
    return jobs,bounds,seconds,resources,raw

def certify(selected,bundle,windows,*,identity,expected_identity):
    from v42_job_capability import Option,validate,resources_used,resource_limit
    jobs,bounds,seconds,r,raw=source_domain(bundle,windows)
    violations=[];usage=defaultdict(float);checked=0
    if identity!=expected_identity:violations.append(dict(reason='DATE_INPUT_SCENARIO_ACCEPTANCE_IDENTITY_MISMATCH'))
    if set(selected)!=set(jobs):violations.append(dict(reason='FULL_JOB_ROSTER',missing=sorted(set(jobs)-set(selected)),extra=sorted(set(selected)-set(jobs))))
    for uid,x in selected.items():
        if uid not in jobs:continue
        try:
            fields=dict(x);fields['segments']=tuple(tuple(v) for v in fields['segments']);fields['wan']=tuple(tuple(v) for v in fields.get('wan',()))
            option=Option(**fields);validate(jobs[uid],option,bounds[uid],r)
            for key,v in resources_used(jobs[uid],option).items():usage[key]+=v
            checked+=1
        except (ValueError,TypeError) as e:violations.append(dict(uid=uid,reason=str(e),start=x.get('start')))
    for key,v in usage.items():
        if v>resource_limit(key,r)+1e-5:violations.append(dict(reason='JOINT_RESOURCE',key=list(key),use=v,limit=resource_limit(key,r)))
    return dict(PASS=not violations,checked_jobs=checked,total_jobs=len(jobs),violations=violations,
        domain='ORIGINAL_NATIVE_JOBS_PLUS_ORIGINAL_FULL_WINDOWS',selected_sha=digest(selected),identity=identity,
        math_source=record(Path(__file__).resolve().parents[1]/'v42_job_capability.py'),
        grid_FULL_replay_required=True,Source_customer_QoS_claim=False)

def accept(result,bundle,windows,*,identity,expected_identity,grid_certificate):
    import math
    required={'day','input_sha','scenario_sha','source_sha','acceptance_sha'}
    if not required<=set(expected_identity) or any(not expected_identity[k] for k in required):
        raise AcceptanceError(dict(reason='COMPLETE_SAME_CASE_IDENTITY_REQUIRED'))
    cert=certify(result['selected_jobs'],bundle,windows,identity=identity,expected_identity=expected_identity)
    cert['grid_FULL_PASS']=grid_certificate.get('PASS') is True and grid_certificate.get('identity')==expected_identity
    if not cert['PASS'] or not cert['grid_FULL_PASS']:raise AcceptanceError(cert)
    # Global lower bound must refer to the same mathematical case, never a
    # historical case with matching dimensions. Original gap threshold .005.
    proof=result.get('global_LB',{})
    ub=result.get('UB');lb=proof.get('value')
    gap=None if ub is None or lb is None else abs(ub-lb)/max(abs(ub),1e-12)
    if (proof.get('identity')!=expected_identity or proof.get('original_FULL') is not True or gap is None
        or not math.isfinite(ub) or not math.isfinite(lb) or lb>ub or gap>.005):
        raise AcceptanceError(dict(cert,reason='ORIGINAL_FULL_GLOBAL_LB_GAP_REQUIRED',gap=gap))
    return dict(result,accepted=True,acceptance=cert,gap=gap,acceptance_sha=digest(dict(cert=cert,LB=proof,UB=ub)))

def execute_a_stage(original_stage,*args,bundle,windows,identity,expected_identity,grid_validator,**kwargs):
    """Actual acceptance choke point after an original A1/A2 function returns."""
    result=original_stage(*args,**kwargs)
    return accept(result,bundle,windows,identity=identity,expected_identity=expected_identity,
                  grid_certificate=grid_validator(result))
