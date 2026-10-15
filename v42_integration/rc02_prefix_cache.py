"""Additive exact-prefix observation cache for Original current AC.

Every candidate still gets a fresh verified engine and re-executes *all*
chronological solves/automatic actions. Only repeated past full-network
measurement/EventLog copying is replaced with a source-bound prior proof.
No RC01 code bytes are modified and no physical FAIL is erased.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
import math
from pathlib import Path

from .current_ac_admission import CurrentACAdmission, AEST
from .actual_validation import record
from .unified_contract import digest


class ExactPrefixProofCache:
    def __init__(self, material_records, *, max_entries=8):
        if not material_records or type(max_entries) is not int or max_entries<1:
            raise ValueError('PREFIX_CACHE_MATERIAL_AUTHORITY_AND_POSITIVE_BOUND_REQUIRED')
        self.material=deepcopy(material_records)
        self.max_entries=max_entries
        self.entries=OrderedDict()
        self.verify()

    def verify(self):
        for receipt in self.material:
            actual=record(receipt['path'])
            if any(actual[k]!=receipt[k] for k in ('sha256','bytes')):
                raise ValueError('PREFIX_CACHE_MATERIAL_SOURCE_BYTES_DRIFT')

    def key(self, *, history, current_slot, current_observations, source_sha, MESS_plan_sha):
        self.verify()
        if (type(current_slot) is not int or current_slot<0 or len(history)!=current_slot or any(
                not math.isfinite(float(row[k])) for row in history for k in ('start_seconds','end_seconds')) or
                any(row['slot']!=t or row['start_seconds']!=history[0]['start_seconds']+t*900 or
                    row['end_seconds']!=row['start_seconds']+900 for t,row in enumerate(history))):
            raise ValueError('PREFIX_CACHE_EXACT_CAUSAL_HISTORY_REQUIRED')
        return digest(dict(history=history,current_slot=current_slot,current_observations=current_observations,
            source_sha=source_sha,MESS_plan_sha=MESS_plan_sha,material=self.material,
            semantics='ORIGINAL_ALL_SOLVES_CLOCK_CONVERGENCE_DUE_QUEUE_PRESERVED'))

    def put(self,key,steps):
        proof=dict(physical_steps=deepcopy(steps),historical_prefix_physical_PASS=all(s['PASS'] for s in steps))
        proof['proof_sha']=digest(proof)
        self.entries[key]=proof
        self.entries.move_to_end(key)
        while len(self.entries)>self.max_entries:self.entries.popitem(last=False)

    def get(self,key):
        self.verify()
        proof=self.entries.get(key)
        if proof is None:return None
        if proof['proof_sha']!=digest({k:v for k,v in proof.items() if k!='proof_sha'}):
            raise ValueError('PREFIX_CACHE_PROOF_BYTES_DRIFT')
        self.entries.move_to_end(key)
        return deepcopy(proof)


class PrefixCachedCurrentAC(CurrentACAdmission):
    """Same current candidate physics, with a bounded past observation cache."""
    def __init__(self,*args,proof_records,**kwargs):
        super().__init__(*args,**kwargs)
        records=list(proof_records)+[record(__file__),record(Path(__file__).with_name('current_ac_admission.py'))]
        self.prefix_proofs=ExactPrefixProofCache(records)
        self.prefix_hits=0
        self.conditional_proofs=OrderedDict()
        self.conditional_proof_hits=0
        self.conditional_engine_calls=0

    def _probe(self,history,current,future_rows=None):
        memory_gate()
        if future_rows:
            # Exact repeated *conditional* predictions can share their whole
            # proof. This never skips the separately required fresh current
            # candidate AC, nor turns predicted AUTO state into Actual state.
            prefix_key=self.prefix_proofs.key(history=history,current_slot=current['slot'],
                current_observations=current['observations'],source_sha=self.freeze['source_sha'],
                MESS_plan_sha=self.mess['plan_sha'])
            key=digest(dict(prefix_key=prefix_key,current=current,conditional_rows=future_rows))
            if key in self.conditional_proofs:
                value=self.conditional_proofs[key]
                if value['proof_sha']!=digest(value['result']):raise ValueError('CONDITIONAL_PROOF_CACHE_DRIFT')
                self.conditional_proofs.move_to_end(key);self.conditional_proof_hits+=1
                result=deepcopy(value['result']);result['conditional_proof_cache_hit']=True
                return result
            self.conditional_engine_calls+=1
            result=super()._probe(history,current,future_rows=future_rows)
            self.conditional_proofs[key]=dict(result=deepcopy(result),proof_sha=digest(result))
            while len(self.conditional_proofs)>16:self.conditional_proofs.popitem(last=False)
            result['conditional_proof_cache_hit']=False
            return result
        key=self.prefix_proofs.key(history=history,current_slot=current['slot'],
            current_observations=current['observations'],source_sha=self.freeze['source_sha'],
            MESS_plan_sha=self.mess['plan_sha'])
        proof=self.prefix_proofs.get(key)
        if proof is None:
            result=super()._probe(history,current)
            self.prefix_proofs.put(key,result['physical_steps'][:-1])
            result.update(prefix_proof_cache_hit=False,prefix_proof_key=key)
            return result
        self.prefix_hits+=1
        result=self._replay_current(history,current)
        result['physical_steps']=proof['physical_steps']+result['physical_steps']
        result.update(historical_prefix_physical_PASS=proof['historical_prefix_physical_PASS'],
            prefix_proof_cache_hit=True,prefix_proof_key=key,prefix_proof_sha=proof['proof_sha'],
            past_physical_FAIL_not_erased=True,all_original_prefix_solves_executed=True,
            repeated_past_fullnetwork_measurement_omitted=True)
        return result

    def _replay_current(self,history,current):
        from .actual_validation import mess_service_bindings
        from v42_regcontrol import authority
        from v42_regcontrol.runner import background
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        from v42_voltage_control.svr import install
        from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
        rows=[*history,current]
        stamps=[datetime.fromtimestamp(self.begin+(t+1)*900,AEST).isoformat() for t in range(96)]
        demand=[rows[t]['observations']['demand']['values']['demand_mw'] if t<len(rows) else
                current['observations']['demand']['values']['demand_mw'] for t in range(96)]
        pv=[rows[t]['observations']['pv']['values']['pv_mw'] if t<len(rows) else
            current['observations']['pv']['values']['pv_mw'] for t in range(96)]
        with self._hardware_context() as scenario:
            source=authority.source();bg_key=digest(dict(stamps=stamps,demand=demand,pv=pv))
            if bg_key not in self._background_cache:
                self._background_cache[bg_key]=background(stamps,demand,pv)
                while len(self._background_cache)>2:self._background_cache.popitem(last=False)
            bg=self._background_cache[bg_key]
            from dayahead.v28r2.opendss_mapping import _set_generator,_set_load,mess_injection_mapping
            engine,adapter,_=authority.compile_verified()
            try:
                equipment=_equipment(engine)
                nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
                native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
                svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
                assert_control_inventory(source['inventory'](engine),scenario,initial=True)
                aliases,_=mess_service_bindings(source,self.mess['P_by_site'])
                def apply(row):
                    t=row['slot'];native.apply(engine,bg,t)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[t].get(loc,0),0)
                    for j in range(len(self.sites)):_set_load(engine,f'IDC_IDC{j+1:02d}',row['P'][j],row['Q'][j])
                    for site,names in aliases.items():
                        inj=mess_injection_mapping(self.mess['P_by_site'][site][t],self.mess['Q_by_site'][site][t])
                        _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                        _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                for row in history:
                    apply(row)
                    clock.settle_slot(engine,row['slot'],capture_events=False)
                apply(current)
                expected=current['slot']*900
                if seconds(engine)!=expected:raise ValueError('PREFIX_CACHE_CURRENT_NATIVE_CLOCK_DRIFT')
                engine.Solution.SolveSnap();pending=queue(engine)
                if (not engine.Solution.Converged() or not engine.Solution.ControlActionsDone()
                        or any(r['absolute_seconds']<=expected for r in pending)):
                    raise ValueError('PREFIX_CACHE_DUE_QUEUE_OR_CONVERGENCE_FAILURE')
                physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                assert_control_inventory(source['inventory'](engine),scenario)
                ok=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS'])
                lines=[r for r in physical['currents'] if r['element'].lower().startswith('line.')]
                step=dict(native_seconds=seconds(engine),kind='CURRENT_CANDIDATE_ONLY_NO_FUTURE_TAP_EXECUTION',
                    PASS=ok,voltage_min_pu=physical['voltage_min_pu'],voltage_max_pu=physical['voltage_max_pu'],
                    maximum_phase_line_loading=max((r['loading_pu'] for r in lines),default=0.),
                    physical_sha=digest(physical),SVR_sha=digest(hardware),
                    SVR_hardware_PASS=hardware['hardware_PASS'],SVR_voltage_PASS=hardware['added_nodes_voltage_PASS'],
                    checked_nodes=len(physical['nodes']),checked_current_rows=len(physical['currents']),
                    violations={k:v for k,v in physical.items() if 'violation' in k},
                    worst_line=max(lines,key=lambda r:r['loading_pu'],default=None))
                return dict(PASS=ok,status='PASS' if ok else 'PHYSICAL_FAIL',physical_steps=[step],
                    current_native_seconds=expected,future_queue_not_executed=pending,
                    original_RegControl=7,SVR_count=11,future_native_Tap_actions_executed=0,
                    conditional_predicted_AUTO_substeps=0,prediction_is_not_Actual_Tap_observation=False,
                    executed_prefix_physical_solves=clock.total_physical_solve_count)
            finally:engine.Basic.ClearAll()


def memory_gate():
    """Fast read-only Win32 counters, before each independently compiled engine."""
    import ctypes
    import os
    import psutil
    available=psutil.virtual_memory().available
    percent=None
    if os.name=='nt':
        class Performance(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in (
                'CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
                'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
                ('HandleCount',ctypes.c_ulong),('ProcessCount',ctypes.c_ulong),('ThreadCount',ctypes.c_ulong)]
        values=Performance();values.cb=ctypes.sizeof(values)
        if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(values),values.cb):
            raise RuntimeError('PREFIX_CACHE_WIN32_COMMIT_COUNTER_UNAVAILABLE')
        percent=100*values.CommitTotal/values.CommitLimit
    if available<8*1024**3 or percent is not None and percent>=75:
        raise RuntimeError('PREFIX_CACHE_RAM_8GB_COMMIT_75_GATE')
    return dict(available_RAM_bytes=available,commit_percent=percent)
