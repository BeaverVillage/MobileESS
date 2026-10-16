"""Current candidate admission on PR189's unchanged snapshot/static hardware.

Every probe starts from source initial taps, replays observed past intervals
and applies only the present candidate. No future exogenous rows or Planning
tap states are inputs. This retains the original snapshot/static control
contract; a delayed TIME-control actuation certificate is not claimed.
"""
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

import numpy as np

from v43.common import record
from .vendor.policy import digest
from .vendor.reservation_state import union_job_segments

AEST=timezone(timedelta(hours=10))


class OriginalCurrentAC:
    def __init__(self, *, issue_seconds, sites, power_model, observations, max_cache=32):
        self.issue=float(issue_seconds);self.sites=tuple(sites);self.model=power_model
        self.observations=observations;self.history=[];self.now=None
        self.cache=OrderedDict();self.max_cache=max_cache;self.audit=[];self.calls=0
        self.source=None;self._background=OrderedDict()

    def observe(self, now, history):
        if now % 900 or now < self.issue or (self.now is not None and now < self.now):
            raise ValueError('ORIGINAL_CURRENT_AC_CAUSAL_CLOCK')
        if len(history) != int((now-self.issue)/900):
            raise ValueError('COMPLETE_OBSERVED_18AEST_PREFIX_REQUIRED')
        for slot,row in enumerate(history):
            if row['slot'] != slot or row['end_seconds'] > now:
                raise ValueError('FUTURE_AC_PREFIX_FORBIDDEN')
        self.now=float(now);self.history=history

    def evaluate(self, now, gpu, *, uid=None):
        if self.now != now:
            raise ValueError('AC_CURRENT_OBSERVATION_REQUIRED')
        vector=np.asarray(gpu,float)
        if vector.shape != (len(self.sites),) or np.any(vector<0) or not np.isfinite(vector).all():
            raise ValueError('AC_WHOLE_CURRENT_GPU_VECTOR_REQUIRED')
        observed=self.observations.at(now,observed_now=now)
        physical=self.model.recompute(vector[None,:],self.sites,[observed['weather']['values']])
        row=dict(slot=len(self.history),start_seconds=now,end_seconds=now+900,
            GPU=vector.tolist(),P=physical['PCC_P_kw'][0].tolist(),Q=physical['PCC_Q_kvar'][0].tolist(),
            observations=observed)
        key=digest(dict(history=self.history,current=row,source_power=self.model.authority_sha,
            contract='PR189_ORIGINAL7_AUTO_SNAPSHOT_STATIC_NO_ADDED_SVR'))
        hit=key in self.cache
        if hit:
            proof=self.cache[key];self.cache.move_to_end(key)
        else:
            began=perf_counter();self.calls+=1
            proof=self._probe([*self.history,row])
            proof.update(AC_wall_seconds=perf_counter()-began)
            self.cache[key]=proof
            while len(self.cache)>self.max_cache:self.cache.popitem(last=False)
        receipt=dict(proof,uid=uid,time_seconds=now,input_sha=key,cache_hit=hit,
            current_candidate_added=True,baseline_PASS_is_candidate_authority=False,
            future_Actual_or_Tap_or_Completion_reads=0,
            delayed_TIME_actuation_certificate='NOT_CERTIFIED',
            scope='ORIGINAL_STATIC_CURRENT_SNAPSHOT_WITH_OBSERVED_PREFIX')
        self.audit.append(receipt)
        return receipt

    def guard(self, metadata, segments, now, observed):
        vector=np.array([observed[s] for s in self.sites],float)
        if metadata.get('state')=='RUNNING':
            vector[self.sites.index(metadata['current_site'])]-=metadata['gpu']
        for segment in union_job_segments([s for s in segments if s['resource'].startswith('gpu:')]):
            if segment['begin']<=now<segment['end']:
                vector[self.sites.index(segment['resource'][4:])]+=segment['quantity']
        proof=self.evaluate(now,vector,uid=metadata['uid'])
        return None if proof['PASS'] else 'ORIGINAL_CURRENT_AC_PHYSICAL_REJECT'

    def _probe(self, rows):
        from v42_regcontrol import authority
        from v42_regcontrol.runner import background
        from v42_integrated.contract import physical_authority
        source=authority.source()
        from dayahead.v28r2.opendss_mapping import _set_load,_set_generator
        # A 96-slot background binding is a source interface, not a forecast.
        # Unapplied shape suffixes hold the last observed value. Long 30-hour
        # prefixes use a second page without restarting the electrical engine.
        backgrounds=[]
        for first in range(0,len(rows),96):
            page=rows[first:first+96]
            padded=page+[page[-1]]*(96-len(page))
            stamps=[datetime.fromtimestamp(self.issue+(first+t+1)*900,AEST).isoformat() for t in range(96)]
            demand=[r['observations']['demand']['values']['demand_mw'] for r in padded]
            pv=[r['observations']['pv']['values']['pv_mw'] for r in padded]
            key=digest(dict(stamps=stamps,demand=demand,pv=pv))
            if key not in self._background:
                self._background[key]=background(stamps,demand,pv)
                while len(self._background)>4:self._background.popitem(last=False)
            backgrounds.append(self._background[key])
        odd,adapter,initial=authority.compile_verified()
        try:
            native=source['NativeAllocation'].from_adapter(adapter)
            native.validate_native_engine(odd)
            branches,_=source['oriented_branches'](odd)
            names=tuple(sorted(n for n in odd.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')))
            steps=[]
            with physical_authority():
                for slot,row in enumerate(rows):
                    bg=backgrounds[slot//96];t=slot%96
                    native.apply(odd,bg,t)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(odd,item['generator_name'],bg.pv_generation_kw_96[t].get(loc,0),0)
                    for j,site in enumerate(self.sites):
                        _set_load(odd,f'IDC_IDC{j+1:02d}',row['P'][j],row['Q'][j])
                    for name in odd.Generators.AllNames():
                        if name.lower().startswith('mess_dis_'):_set_generator(odd,name,0,0)
                    for name in odd.Loads.AllNames():
                        if name.lower().startswith('mess_chg_'):_set_load(odd,name,0,0)
                    authority.assert_inventory(source['inventory'](odd))
                    odd.Solution.SolveSnap()
                    authority.assert_inventory(source['inventory'](odd))
                    converged=bool(odd.Solution.Converged() and odd.Solution.ControlActionsDone())
                    voltage=np.array(source['voltage_vector'](odd,names))
                    measured=np.array([source['branch_measurement'](odd,b) for b in branches])
                    lines=np.array([b.branch_id.lower().startswith('line.') for b in branches])
                    tx=np.array([b.branch_id.lower().startswith('transformer.') for b in branches])
                    violations=dict(voltage=int(np.sum((voltage<.95)|(voltage>1.05))),
                        line_current=int(np.sum(measured[lines,1]>1)),
                        transformer_current=int(np.sum(measured[tx,1]>1)),
                        transformer_kVA=int(np.sum(measured[tx,2]>1)))
                    steps.append(dict(slot=slot,PASS=converged and not any(violations.values()),
                        converged=converged,violations=violations,voltage_min_pu=float(voltage.min()),
                        voltage_max_pu=float(voltage.max()),maximum_phase_line_loading=float(measured[lines,1].max()),
                        checked_nodes=len(names),checked_branch_phases=len(branches)))
                    if not converged:
                        break
            last=steps[-1]
            return dict(PASS=len(steps)==len(rows) and last['PASS'],
                current=last,historical_prefix_physical_PASS=all(r['PASS'] for r in steps[:-1]),
                physical_steps=steps,original_RegControl=7,added_SVR_count=0,CapControl_count=0,
                control_mode='ORIGINAL_SNAPSHOT_STATIC',PCC_power_recomputed=True,
                native_global_optimizer_calls=0)
        finally:
            odd.Basic.ClearAll()
