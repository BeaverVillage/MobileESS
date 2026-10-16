"""Attempt-local memoization of unchanged public calculations, never AC gates."""
from collections import OrderedDict
from copy import deepcopy
import inspect
import textwrap
from time import perf_counter

import numpy as np

from v43_actual.vendor.aidc_sensitivity_runtime import SignedSensitivityPolicy, anonymous_cohort_residual
from v43_actual.vendor.trajectory_tracking import service_integral
from v43_actual.vendor.reservation_state import union_job_segments


def future_core():
    source=textwrap.dedent(inspect.getsource(SignedSensitivityPolicy._public_future))
    source=source.replace('service_integral(', 'self._service_integral(')
    source=source.replace('anonymous_cohort_residual(self.reference, self.metadata, self.current[0])',
        'self._anonymous_residual()')
    ns=dict(SignedSensitivityPolicy._public_future.__globals__)
    exec(compile(source,__file__,'exec'),ns)
    return ns['_public_future']


def segments_key(rows):
    return tuple((r['resource'],r['begin'],r['end'],r['quantity']) for r in rows)


class PublicCalculationCache:
    _future_core=future_core()

    def initialize_caches(self):
        self._integrals=OrderedDict();self._residual_key=None
        self.timings=dict(reservation_seconds=0.,public_future_seconds=0.,sensitivity_seconds=0.,
            current_AC_seconds=0.,service_cache_hits=0,service_cache_misses=0,residual_recomputations=0)

    def _service_integral(self,sites,rows,begin):
        key=segments_key(rows)
        if key not in self._integrals:
            self._integrals[key]=service_integral(sites,rows,begin)
            self.timings['service_cache_misses']+=1
            if len(self._integrals)>12000:self._integrals.popitem(last=False)
        else:self.timings['service_cache_hits']+=1
        return self._integrals[key]

    def _anonymous_residual(self):
        # No event can interleave a serial admission pass. New submissions at
        # the same clock change metadata cardinality; physical starts do not
        # change the submitted-work depletion calculation.
        key=(self.current[0],len(self.metadata))
        if key!=self._residual_key:
            self._residual=anonymous_cohort_residual(self.reference,self.metadata,self.current[0])
            self._residual_key=key;self.timings['residual_recomputations']+=1
        return self._residual[0].copy(),self._residual[1]

    def _public_future(self,*args):
        began=perf_counter()
        try:
            reservations,exclude=args
            if not hasattr(reservations,'revision'):return self._future_core(*args)
            key=(self.current[0],reservations.revision,len(self.metadata),frozenset(self.boundary_completed_UIDs))
            if getattr(self,'_future_key',None)!=key:
                hard=np.zeros_like(self.reference.arrays['G_Total_Plan']);expected=hard.copy();known=hard.copy()
                contributions={};plans=reservations.known_plans;bookings=reservations.reservations
                for uid in set(bookings)|set(plans)|set(self.metadata):
                    if uid in self.boundary_completed_UIDs:continue
                    booking=bookings.get(uid,{})
                    rows=([] if booking.get('status')=='RELEASED' else booking.get('segments',[]))+plans.get(uid,[])
                    m=self.metadata.get(uid,{})
                    if m.get('state')=='COMPLETED':rows=[]
                    hp=self._service_integral(self.packet.sites,rows,self.reference.begin)
                    future=rows
                    if m.get('state')=='RUNNING':
                        remaining=max(0.,m['t50_seconds']-m.get('accumulated_compute_seconds',0))
                        hold=max(remaining,900-self.current[0]%900)
                        future=rows+[dict(resource='gpu:'+m['current_site'],begin=self.current[0],
                            end=self.current[0]+hold,quantity=m['gpu'])]
                    elif m.get('state')=='PENDING' and m.get('origin_unknown') is True and not rows:
                        site=m.get('reference_site',m.get('source_site'))
                        if site in self.packet.sites:
                            start=max(self.current[0],m['reference_start_seconds'])
                            future=[dict(resource='gpu:'+site,begin=start,end=start+max(m['t50_seconds'],1e-9),quantity=m['gpu'])]
                    ep=self._service_integral(self.packet.sites,future,self.reference.begin)
                    kp=hp if uid in plans or m.get('origin_unknown') is False else np.zeros_like(hp)
                    hard+=hp;expected+=ep;known+=kp;contributions[uid]=(hp,ep,kp)
                self._future_totals=(hard,expected,known,contributions);self._future_key=key
            h,e,k,contributions=self._future_totals
            own=contributions.get(exclude,(0.,0.,0.))
            hard=h-own[0];expected=e-own[1];known=k-own[2]
            slot=int((self.current[0]-self.reference.begin)//900)
            if 0<=slot<96:
                instant=np.array([self.current[1][s] for s in self.packet.sites],float)
                m=self.metadata.get(exclude,{})
                if m.get('state')=='RUNNING':instant[self.packet.sites.index(m['current_site'])]-=m['gpu']
                hard[slot]=np.maximum(hard[slot],instant);expected[slot]=np.maximum(expected[slot],instant)
            self.last_hard_profile=hard
            anonymous,audit=self._anonymous_residual();self.anonymous_residual_audit=audit
            if audit['status']=='SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS':
                anonymous[:max(0,slot+1)]=0;expected+=anonymous
            return expected,known
        finally:self.timings['public_future_seconds']+=perf_counter()-began


def single_resource_fit(ledger,segments,exclude):
    """Exact integer GPU interval sweep, with same-UID max union retained."""
    if getattr(ledger,'_profile_revision',None)!=ledger.revision:
        by={};ledger._merged_by_uid={}
        for uid in list(ledger.reservations)+[u for u in ledger.known_plans if u not in ledger.reservations]:
            booking=ledger.reservations.get(uid,{})
            rows=([] if booking.get('status')=='RELEASED' else booking.get('segments',[]))+ledger.known_plans.get(uid,[])
            key=segments_key(rows)
            prior=ledger._union_cache.get(uid)
            if prior is None or prior[0]!=key:
                prior=(key,union_job_segments(rows));ledger._union_cache[uid]=prior
            ledger._merged_by_uid[uid]=prior[1]
            for r in prior[1]:by.setdefault(r['resource'],[]).append((uid,r))
        ledger._resource_rows=by;ledger._resource_profiles={}
        for resource,rows in by.items():
            events={}
            for uid,r in rows:
                events[r['begin']]=events.get(r['begin'],0)+r['quantity']
                events[r['end']]=events.get(r['end'],0)-r['quantity']
            points=np.array(sorted(events),float)
            ledger._resource_profiles[resource]=(points,np.cumsum([events[t] for t in points]))
        ledger._profile_revision=ledger.revision
    s=segments[0];resource=s['resource'];a=s['begin'];b=s['end']
    if resource not in ledger.capacities:return 'NO_RESOURCE_AUTHORITY'
    points,usage=ledger._resource_profiles.get(resource,(np.array([]),np.array([])))
    own=[r for r in ledger._merged_by_uid.get(exclude,[]) if r['resource']==resource]
    check=np.unique([a,*points[(points>a)&(points<b)],
        *[v for r in own for v in (r['begin'],r['end']) if a<v<b]])
    ix=np.searchsorted(points,check,side='right')-1
    total=np.zeros(len(check))
    if len(points):total[ix>=0]=usage[ix[ix>=0]]
    for r in own:total-=r['quantity']*((check>=r['begin'])&(check<r['end']))
    total+=s['quantity']
    ledger.last_conflict=None
    bad=np.flatnonzero(total>ledger.capacities[resource]+1e-9)
    if len(bad):
        t=check[bad[0]]
        peers=[dict(r,uid=uid,role='KNOWN_FROZEN' if uid in ledger.known_plans else
            ledger.reservations[uid].get('role','COMMITTED')) for uid,r in ledger._resource_rows.get(resource,[])
            if uid!=exclude and r['begin']<=t<r['end']]
        ledger.last_conflict=dict(resource=resource,begin=float(t),end=float(check[bad[0]+1] if bad[0]+1<len(check) else b),
            capacity=ledger.capacities[resource],candidate_quantity=s['quantity'],conflicting_UIDs_roles_intervals=peers)
        return 'NO_CAPACITY'
    return None
