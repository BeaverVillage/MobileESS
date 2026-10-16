"""Original signed ranking with an explicit, separately evidenced AC gate."""
from copy import deepcopy
import inspect
import math
import textwrap
from time import perf_counter

from v43_actual.controller import IssueContinuityPolicy
from v43_actual.vendor.aidc_sensitivity_runtime import SignedSensitivityPolicy
from v43_actual.vendor.policy import digest
from v43_actual.vendor.trajectory_tracking import require_tracking_public
from . import POLICY_ID
from .participation import change_authority
from .performance import PublicCalculationCache


def score_core():
    source = textwrap.dedent(inspect.getsource(SignedSensitivityPolicy._score))
    if source.count('if violations:') != 1:
        raise ValueError('SIGNED_SCORE_REUSE_BOUNDARY_DRIFT')
    source = source.replace('if violations:', 'if violations and self.affine_hard_gate:')
    # The complete numeric authority is checked on construction and after
    # execution. Avoid rehashing megabytes of unchanged rows per candidate.
    left=source.index('    authority = (')
    right=source.index('    key = ',left)
    source=source[:left]+"    authority = (self._score_authority, digest(self._current_weather(now)), instant_base.tobytes())\n"+source[right:]
    source = source.replace('affine_approximation_only=True, Fresh_AC_PASS_claimed=False)',
        'affine_approximation_only=True, Fresh_AC_PASS_claimed=False, predicted_violations=violations)')
    ns = dict(SignedSensitivityPolicy._score.__globals__)
    exec(compile(source,inspect.getfile(SignedSensitivityPolicy._score),'exec'),ns)
    return ns['_score']


class CorrectivePolicy(PublicCalculationCache,IssueContinuityPolicy):
    _score = score_core()

    def __init__(self,*args,correction_proof=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.affine_hard_gate = True
        if correction_proof is not None:
            # Proof production requires independent real AC after the active
            # Strict worker terminates. A fixture is never real authority.
            expected = dict(case_sha=self.bindings['case_sha'], response_sha=self.bindings['response_sha'],
                aidc_anchor=self.bindings['aidc_anchor'], mess_anchor=self.bindings['mess_anchor'])
            if (correction_proof.get('anchors') != expected
                    or correction_proof.get('independent_current_AC_mismatch_count',0) < 1
                    or correction_proof.get('root_cause_verified') is not True
                    or correction_proof.get('physical_bands_unchanged') is not True
                    or correction_proof.get('evidence_scope') != self.evidence_scope):
                raise ValueError('EXACT_CURRENT_AFFINE_AC_CORRECTION_PROOF_REQUIRED')
            self.affine_hard_gate = False
        self.spec.update(policy_version=POLICY_ID,permission='R1_ASSUMED_ARRIVAL_HASH_30_PERCENT',
            signed_model='UNCHANGED_RANKING',signed_current_hard_gate=self.affine_hard_gate,
            correction_proof_sha=None if correction_proof is None else digest(correction_proof),
            final_execution_gate='UNCHANGED_ORIGINAL_CURRENT_AC',intentional_delay=False)
        self.sha = digest(self.spec)
        self.current_diagnostics = []
        self.initialize_caches()
        self._score_authority=(digest(self.packet.bindings),digest(self.packet.authority),
            self.spec['response_numeric_sha'])

    def current_guard(self,m,segments,now,observed):
        self.observe(now,observed,self.metadata)
        predicted = None
        if now >= self.reference.begin:
            predicted = SignedSensitivityPolicy.current_guard(self,m,segments,now,observed)
        # Always compare the independent physical gate, even if the frozen
        # forecast-affine rows reject. No guard tolerance is changed.
        began=perf_counter()
        actual = self.oracle.guard(m,segments,now,observed)
        self.timings['current_AC_seconds']+=perf_counter()-began
        self.current_diagnostics.append(dict(uid=m['uid'],time_seconds=now,
            candidate_sites=[s['resource'][4:] for s in segments if s['resource'].startswith('gpu:')],
            affine_reject=predicted,current_AC_reject=actual,
            affine_hard_gate=self.affine_hard_gate,observed_GPU_by_site=dict(observed)))
        return actual or (predicted if self.affine_hard_gate else None)

    def select(self,m,receipt,now,reservations,*,reserve=False):
        began=perf_counter();require_tracking_public(m)
        if m.get('origin_unknown') is not True:
            raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_ALLOCATOR')
        if m.get('state')!='PENDING' or m['submit_seconds']>now or m.get('is_observed') is not True:
            return self._record(m,now,dict(action='QUEUE',status='OBSERVED_PENDING_REQUIRED'),began,0,[])
        if now%900 or self.current is None or self.current[0]!=now:
            raise ValueError('CURRENT_OBSERVED_CONTROL_TICK_REQUIRED')
        lower=max(m['submit_seconds'],m.get('release_seconds') or -math.inf,
            m.get('hard_earliest_start_seconds') or -math.inf)
        if now<lower:
            return self._record(m,now,dict(action='QUEUE',status='SOURCE_RELEASE_NOT_READY'),began,0,[])
        basic=m['reference_site'];rejected=[];candidates=[]
        baseline=None
        # FIFO controls evaluation order, not a global future start barrier.
        sites=[basic]+sorted(set(m['compatible_sites'])-{basic})
        for site in sites:
            reason=None;changing=site!=basic
            stages=dict(uid=m['uid'],time_seconds=now,site=site,source_or_R1_permission_PASS=False,
                GPU_rack_QoS_PASS=False,Current_AC_PASS=False,selected=False,actual_START=False)
            if site not in m['compatible_sites']:reason='SOURCE_SITE_INCOMPATIBLE'
            elif changing:
                reason=('C0_BASIC_SITE_ONLY' if self.variant=='C0' else
                    'PREFIX_SIGNED_RESPONSE_UNAVAILABLE' if now<self.reference.begin else change_authority(m,site,now))
            stages['source_or_R1_permission_PASS']=reason is None
            if reason is None and m['gpu']>max(self.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
            end=now+max(m['t50_seconds'],1e-9)
            if reason is None and any(m.get(k) is not None and value>m[k] for k,value in
                    [('hard_latest_start_seconds',now),('completion_deadline_seconds',end)]):reason='SOURCE_HARD_WINDOW'
            segments=[dict(resource='gpu:'+site,begin=now,end=end,quantity=m['gpu'])]
            if reason is None:
                began_reservation=perf_counter()
                reason=reservations.feasible(segments,exclude=m['uid'])
                self.timings['reservation_seconds']+=perf_counter()-began_reservation
            stages['GPU_rack_QoS_PASS']=reason is None
            score=None
            if reason is None:
                if now<self.reference.begin:
                    score=dict(grid_peak=0.,loading_hours=0.,risk_GPUh=0.,profile=None,
                        checked_grid_slots=0,prefix_signed_ranking_not_certified=True)
                else:
                    if baseline is None and now>=self.reference.begin:
                        baseline,_=self._public_future(reservations,m['uid'])
                    if self.anonymous_residual_audit['status'] not in (
                            'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS','ZERO_ANONYMOUS_FORECAST'):
                        return self._record(m,now,dict(action='QUEUE',status='CC4_CONSERVATION_NOT_CERTIFIED'),began,0,[])
                    began_score=perf_counter();score,reason=self._score(m,segments,now,baseline)
                    self.timings['sensitivity_seconds']+=perf_counter()-began_score
            stages.update(sensitivity_evaluated=score is not None,
                sensitivity=None if score is None else {k:v for k,v in score.items() if k!='profile'},
                basic_site=basic,participant=m.get('r1_flex30',{}).get('participant',False))
            if reason:
                blocking=[uid for uid,other in self.metadata.items() if other.get('state')=='RUNNING'
                    and other.get('current_site')==site and other.get('accumulated_compute_seconds',0)>other['t50_seconds']]
                rejected.append(dict(site=site,reason=reason,observed_overrun_blocking_UIDs=blocking if reason in (
                    'NO_CAPACITY','PHYSICAL_CAPACITY_RUNNING_RETAINED') else []))
                self.funnel.append(dict(stages,reason=reason));continue
            key=(round(score['grid_peak'],12),score['loading_hours'],score['risk_GPUh'],0 if site==basic else 1,site)
            stages.update(reason='SCORED_FEASIBLE_NOT_SELECTED')
            self.funnel.append(stages)
            candidates.append((key,site,segments,score,stages))
        # No impossible basic-site score is ever a comparison threshold.
        # Signed ranking is computed first; actual AC confirms each candidate
        # in order. An AC-rejected winner does not hide the next feasible site.
        for key,site,segments,score,stages in sorted(candidates,key=lambda row:row[0]):
            reason=self.current_guard(m,segments,now,self.current[1])
            if reason:
                rejected.append(dict(site=site,reason=reason));stages.update(reason=reason);continue
            stages['Current_AC_PASS']=True
            if reserve:
                ok,reason=reservations.reserve(m['uid'],segments,replace=True)
                if not ok:
                    rejected.append(dict(site=site,reason=reason));continue
            decision=dict(action='START' if site==basic else 'PREPLACE',status='R1_CORRECTIVE_FEASIBLE_SELECTED',
                site=site,start_seconds=now,nominal_end_seconds=segments[0]['end'],segments=segments,
                additional_start_delay_seconds=0.,r1_authority='R1_ASSUMED',
                actual_execution_confirmed=False,tracking={k:v for k,v in score.items() if k!='profile'})
            stages.update(selected=True,reason='SIGNED_SELECTED_CURRENT_AC_PASS',selection_is_not_execution=True)
            return self._record(m,now,decision,began,len(sites),rejected)
        return self._record(m,now,dict(action='QUEUE',status='NO_HARD_FEASIBLE_CORRECTIVE_ACTION'),
            began,len(sites),rejected)
