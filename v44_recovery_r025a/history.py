"""Replay native state exactly, amortize historical audit work per slot.

No partial native snapshot is restored. Every chronological SolveSnap remains.
Only historical slots use this scope. Their first and last full inventory and
rating checks remain, as do all native voltages, queue, tap and solver-counter
guards. The current candidate and independent Fresh keep the r016 path.
"""
from collections import OrderedDict
from contextlib import contextmanager,ExitStack
from copy import deepcopy
from unittest.mock import patch
import pickle
import numpy as np

from .immutable import freeze


class HistoryProofs:
    def __init__(self,max_slots=120,max_bytes=128*1024*1024):
        self.slots=OrderedDict();self.costs={};self.bytes=0;self.max_slots=max_slots;self.max_bytes=max_bytes
        self.hits=0;self.misses=0;self.evictions=0

    def get(self,key,stamp):
        entry=self.slots.get(key)
        if entry is None or stamp not in entry:return None
        self.slots.move_to_end(key);self.hits+=1
        return entry[stamp][0]

    def put(self,key,stamp,value):
        frozen=freeze(value);size=len(pickle.dumps((stamp,frozen),protocol=5))
        self.misses+=1
        if size>self.max_bytes:return frozen
        entry=self.slots.setdefault(key,{})
        if stamp in entry:
            if entry[stamp][0]!=frozen:raise ValueError('PREFIX_LIVE_CONTROL_CERTIFICATE_DRIFT')
            self.bytes-=entry[stamp][1]
        entry[stamp]=(frozen,size);self.bytes+=size;self.slots.move_to_end(key)
        while self.bytes>self.max_bytes or len(self.slots)>self.max_slots:
            removed_key,removed=self.slots.popitem(last=False);self.costs.pop(removed_key,None)
            self.bytes-=sum(item[1] for item in removed.values());self.evictions+=1
        return frozen


def prefix_keys(oracle,rows):
    from v44.common import digest
    chain=digest(dict(hardware=oracle.hardware_record,scenario=oracle.scenario['scenario_SHA'],
        source=oracle.hardware['source_SHA'],mess=oracle.mess_sha,sites=oracle.sites,
        arm=getattr(oracle,'arm',None),day_start=getattr(oracle,'day_start',None),issue=getattr(oracle,'issue',None)))
    result=[]
    for row in rows:
        chain=digest(dict(previous=chain,row=row));result.append(chain)
    return result


def physical_copy(value):
    if isinstance(value,dict) and {'nodes','currents','transformers'}<=value.keys():
        return freeze(value)
    return deepcopy(value)


def native_stamp(oracle,engine):
    """Exact observed state and all complex bus voltages; no tolerances."""
    from v44.common import digest
    solution=engine.Solution
    counters=tuple(getattr(solution,name)() for name in (
        'ControlActionsDone','Converged','ControlIterations','Iterations','TotalIterations',
        'MostIterationsDone','MaxControlIterations','MaxIterations','ControlMode'))
    return (digest(oracle._state(engine)),np.asarray(engine.Circuit.AllBusVolts(),dtype=np.float64).tobytes(),counters)


@contextmanager
def scope(oracle,rows):
    if getattr(oracle,'_independent_fresh',False):
        yield {'bypassed_independent_Fresh':True};return
    from v44.svr12 import scope as hardware_scope
    import v44.svr11_ac as ac
    with hardware_scope():
        import v42_voltage_control.integration as integration
        original_controls=integration._controls
        original_ratings=integration.PhysicalScenario._ratings
        original_settle=ac.SVR11CurrentAC._settle
        original_copy=ac.deepcopy
        proofs=getattr(oracle,'_prefix_history_proofs',None)
        if proofs is None:proofs=oracle._prefix_history_proofs=HistoryProofs()
        keys=prefix_keys(oracle,rows)
        active=None
        stats=dict(historical_slots=0,historical_low_cost_bypasses=0,full_control_calls=0,reused_control_calls=0,
            full_rating_calls=0,amortized_rating_calls=0,native_solves_removed=0,
            current_candidate_checks_skipped=0,exact_boundary_control_checks=0)

        def controls(engine,scenario,authority=None):
            if active is None or engine is not active['engine']:
                return original_controls(engine,scenario,authority)
            stamp=native_stamp(oracle,engine)
            active['control_calls']+=1
            # The first call is a full live settings/inventory check in every
            # historical slot, even when an identical certificate exists.
            cached=None if active['first_control'] else proofs.get(active['key'],stamp)
            active['first_control']=False
            if cached is None:
                stats['full_control_calls']+=1
                value=proofs.put(active['key'],stamp,original_controls(engine,scenario,authority))
            else:
                stats['reused_control_calls']+=1;value=cached
            active['last_controls']=value
            return value

        def ratings(audit,engine):
            if active is None or engine is not active['engine']:
                return original_ratings(audit,engine)
            if active['rating'] is None:
                stats['full_rating_calls']+=1
                active['rating']=freeze(original_ratings(audit,engine))
            else:stats['amortized_rating_calls']+=1
            return active['rating']

        def settle(owner,engine,slot):
            nonlocal active
            if owner is not oracle or getattr(owner,'_independent_fresh',False) or slot>=len(rows)-1:
                return original_settle(owner,engine,slot)
            known_cost=proofs.costs.get(keys[slot])
            if known_cost is not None and known_cost<=3:
                stats['historical_low_cost_bypasses']+=1
                return original_settle(owner,engine,slot)
            if active is not None:raise RuntimeError('PREFIX_NESTED_SETTLE_FORBIDDEN')
            stats['historical_slots']+=1
            active=dict(engine=engine,key=keys[slot],first_control=True,last_controls=None,rating=None,control_calls=0)
            try:
                result=original_settle(owner,engine,slot)
                # End-of-slot full live guards catch static or dynamic drift.
                # Current and every slot's outer _inventory remain unchanged.
                final=original_controls(engine,owner.scenario)
                stats['full_control_calls']+=1
                if final!=active['last_controls']:
                    raise ValueError('PREFIX_FINAL_LIVE_CONTROL_CERTIFICATE_DRIFT')
                stats['exact_boundary_control_checks']+=1
                final_rating=original_ratings(owner._scenario_audit,engine)
                stats['full_rating_calls']+=1
                if active['rating'] is not None and final_rating!=active['rating']:
                    raise ValueError('PREFIX_FINAL_LIVE_RATING_CERTIFICATE_DRIFT')
                if active['key'] in proofs.slots:proofs.costs[active['key']]=active['control_calls']
                return result
            finally:active=None

        def copy_physical(value):
            if getattr(oracle,'_independent_fresh',False):return original_copy(value)
            if isinstance(value,dict) and {'nodes','currents','transformers'}<=value.keys():return freeze(value)
            return original_copy(value)

        with ExitStack() as stack:
            stack.enter_context(patch.object(integration,'_controls',controls))
            stack.enter_context(patch.object(integration.PhysicalScenario,'_ratings',ratings))
            stack.enter_context(patch.object(ac.SVR11CurrentAC,'_settle',settle))
            stack.enter_context(patch.object(ac,'deepcopy',copy_physical))
            yield stats
