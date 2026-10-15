"""Causal current-state candidate AC admission on the original 11-SVR grid.

Completed past intervals establish AUTO control history. A candidate is solved
only at the current native clock; queued future tap actions are not executed.
Retrospective Fresh verification remains a separate operation.
"""
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import csv
import io
import math
from pathlib import Path
from time import perf_counter
import zipfile

import numpy as np
import pandas as pd

from .policy import digest
from .actual_validation import record,checked,read

AEST=timezone(timedelta(hours=10))


def epoch(value):
    if isinstance(value,(int,float)):return float(value)
    t=datetime.fromisoformat(str(value).replace('/','-').replace('Z','+00:00'))
    return t.replace(tzinfo=AEST).timestamp() if t.tzinfo is None else t.timestamp()


class CausalSeries:
    """Observation and source-update times both bind a read-only as-of view."""
    def __init__(self,rows,*,name,max_staleness_seconds=7200):
        self.name=name;self.max_staleness_seconds=max_staleness_seconds
        clean=[];seen={}
        for raw in rows:
            row=deepcopy(raw)
            if not all(math.isfinite(float(row[k])) for k in ('observed_seconds','available_seconds')):
                raise ValueError('CAUSAL_NONFINITE_OBSERVATION_CLOCK')
            if row['available_seconds']<row['observed_seconds']:raise ValueError('CAUSAL_AVAILABLE_BEFORE_OBSERVATION')
            if not all(math.isfinite(float(v)) for v in row['values'].values()):raise ValueError('CAUSAL_NONFINITE_VALUE')
            key=(row['observed_seconds'],row['available_seconds'])
            if key in seen and seen[key]!=row['values']:raise ValueError('CAUSAL_CONFLICTING_SOURCE_DUPLICATE')
            seen[key]=row['values'];row['row_sha']=digest(row);clean.append(row)
        self.__rows=tuple(sorted(clean,key=lambda r:(r['observed_seconds'],r['available_seconds'],r['row_sha'])))
        self.receipt_sha=digest(list(self.__rows))

    def at(self,when,*,observed_now):
        if not math.isfinite(when) or not math.isfinite(observed_now) or when>observed_now:raise ValueError('FUTURE_OBSERVATION_QUERY_FORBIDDEN')
        row=next((r for r in reversed(self.__rows) if r['observed_seconds']<=when and r['available_seconds']<=when),None)
        if row is None:raise ValueError('CAUSAL_OBSERVATION_NOT_AVAILABLE:'+self.name)
        if when-row['observed_seconds']>self.max_staleness_seconds:raise ValueError('CAUSAL_OBSERVATION_TOO_STALE:'+self.name)
        return dict(deepcopy(row),decision_seconds=when,observation_age_seconds=when-row['observed_seconds'],
            source_availability_checked=True,interpolation='NONE_ASOF_FORWARD_HOLD')


def _archive_series(paths,kind,begin,end):
    time_key,column=('SETTLEMENTDATE','TOTALDEMAND') if kind=='demand' else ('INTERVAL_DATETIME','POWER')
    rows=[];sources=[]
    lower=datetime.fromtimestamp(begin-7200,AEST).strftime('%Y/%m/%d %H:%M:%S')
    upper=datetime.fromtimestamp(end,AEST).strftime('%Y/%m/%d %H:%M:%S')
    for path in paths:
        source=record(path);sources.append(source)
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith('.csv'):continue
                with archive.open(member) as stream:
                    headers={}
                    for ordinal,line in enumerate(csv.reader(io.TextIOWrapper(stream,encoding='utf-8-sig'))):
                        key=tuple(line[1:4])
                        if line and line[0]=='I':headers[key]=line[4:]
                        elif line and line[0]=='D' and key in headers:
                            item=dict(zip(headers[key],line[4:]));stamp=item.get(time_key,'')
                            if (item.get('REGIONID')!='VIC1' or not lower<=stamp<=upper
                                    or kind=='pv' and item.get('TYPE')!='MEASUREMENT'
                                    or kind=='demand' and item.get('INTERVENTION','0')!='0'):continue
                            observed=epoch(stamp)
                            if not item.get('LASTCHANGED'):raise ValueError('AEMO_SOURCE_UPDATE_TIME_MISSING')
                            available=max(observed,epoch(item['LASTCHANGED']))
                            rows.append(dict(observed_seconds=observed,available_seconds=available,
                                values={kind+'_mw':float(item[column])},source=source,member=member,
                                source_row=ordinal,record_type=key,source_fields=item))
    return CausalSeries(rows,name=kind),sources


class CausalObservations:
    def __init__(self,demand,pv,weather,*,sources=()):
        self.demand,self.pv,self.weather=demand,pv,weather;self.sources=list(sources)
        self.sha=digest(dict(demand=demand.receipt_sha,pv=pv.receipt_sha,weather=weather.receipt_sha,sources=self.sources))

    def at(self,when,*,observed_now):
        return dict(demand=self.demand.at(when,observed_now=observed_now),
            pv=self.pv.at(when,observed_now=observed_now),weather=self.weather.at(when,observed_now=observed_now),
            observation_bundle_sha=self.sha)

    @classmethod
    def load(cls,raw,*,begin,end):
        raw=Path(raw);actual=read(raw/'ACTUAL_INPUT_BUNDLE.json');provenance=read(raw/'SOURCE_PROVENANCE.json')
        series={};sources=[]
        for kind in ('demand','pv'):
            current=checked(actual['realized_inputs']['authority'][kind])
            prior=current.with_name(current.name.replace('202505010000','202504010000'))
            if prior==current or not prior.is_file():raise ValueError('PREVIOUS_MONTH_CAUSAL_ARCHIVE_MISSING:'+kind)
            series[kind],receipts=_archive_series((prior,current),kind,begin,end);sources.extend(receipts)
        weather_path=checked(provenance['daily_sources']['noaa_actual_weather.parquet']);receipt=record(weather_path)
        frame=pd.read_parquet(weather_path);rows=[]
        for ordinal,row in enumerate(frame.to_dict('records')):
            stamp=pd.Timestamp(row['ts']).timestamp()
            if begin-7200<=stamp<=end:
                rows.append(dict(observed_seconds=stamp,available_seconds=stamp,
                    values={key:float(row[key]) for key in ('t_wb_c','rh_pct')},source=receipt,source_row=ordinal,
                    availability_scope='OBSERVATION_TIME_MODEL_NOT_HISTORICAL_INGESTION_CERTIFICATE'))
        sources.append(receipt)
        return cls(series['demand'],series['pv'],CausalSeries(rows,name='weather'),sources=sources)


class CurrentACAdmission:
    """Independent candidate prefix, bounded memoization, no baseline shortcut."""
    def __init__(self,*,begin,sites,power_model,observations,source_freeze=None,manifest=None,mess=None,
                 probe=None,max_cache=32,max_tick_seconds=840.):
        self.begin=float(begin);self.sites=tuple(sites);self.model=power_model;self.observations=observations
        self.freeze=source_freeze;self.manifest=manifest;self.mess=mess;self.probe=probe
        self.max_cache=int(max_cache);self.max_tick_seconds=float(max_tick_seconds)
        self.now=None;self.history=[];self.cache=OrderedDict();self.audit=[];self.calls=0;self.tick_began=None
        self.prediction_audit=[]
        self.prediction_calls=0
        self._background_cache=OrderedDict()

    @contextmanager
    def _hardware_context(self):
        """Reuse an already verified run scope; never waive byte checks.

        The original outer context verifies the entire historical Source graph
        before and after the run. Candidate entry checks the exact active
        context and the three immutable physical authority files again.
        """
        from .actual_validation import _validated_hardware_context
        from v42_svr11.authority import active
        from v42_voltage_control.integration import validate_scenario
        scope=active()
        if (scope is not None and self.freeze is not None and self.manifest is not None
                and scope.get('integration_validation_only') is True
                and scope.get('execution_SHA')==self.freeze['source_sha']
                and all(scope[k]==self.manifest[k] for k in ('hardware','scenario','thermal'))):
            for k in ('hardware','scenario','thermal'):checked(self.manifest[k])
            scenario=read(checked(self.manifest['scenario']));validate_scenario(scenario)
            yield scenario
        else:
            with _validated_hardware_context(self.freeze,self.manifest) as scenario:yield scenario

    def observe(self,now,history):
        if now<self.begin or now%900 or self.now is not None and now<self.now:raise ValueError('CURRENT_AC_CAUSAL_CLOCK')
        if len(history)!=int((now-self.begin)/900):raise ValueError('CURRENT_AC_COMPLETE_PAST_PREFIX_REQUIRED')
        if self.now!=now:self.tick_began=perf_counter()
        self.now=float(now);self.history=deepcopy(history)
        for slot,row in enumerate(self.history):
            if row['slot']!=slot or row['end_seconds']>now:raise ValueError('CURRENT_AC_FUTURE_HISTORY_FORBIDDEN')

    def evaluate(self,now,gpu,*,uid=None):
        if now!=self.now:raise ValueError('CURRENT_AC_ONLY_OBSERVED_TIME_ALLOWED')
        vector=np.asarray(gpu,float)
        if vector.shape!=(len(self.sites),) or not np.isfinite(vector).all() or np.any(vector<0):raise ValueError('CURRENT_AC_GPU_AXIS')
        observed=self.observations.at(now,observed_now=now)
        weather=observed['weather']['values']
        power=self.model.recompute(vector[None,:],self.sites,[weather])
        row=dict(slot=int((now-self.begin)/900),start_seconds=now,GPU=vector.tolist(),
            P=power['PCC_P_kw'][0].tolist(),Q=power['PCC_Q_kvar'][0].tolist(),observations=observed)
        key=digest(dict(current=row,prefix=self.history,power_authority=self.model.authority_sha,
            MESS=None if self.mess is None else self.mess['plan_sha']))
        hit=key in self.cache
        if hit:physical=deepcopy(self.cache[key]);self.cache.move_to_end(key)
        elif perf_counter()-self.tick_began>self.max_tick_seconds:
            physical=dict(PASS=False,status='NOT_CERTIFIED',reason='CURRENT_AC_TICK_RESOURCE_LIMIT',physical_steps=[])
        else:
            began=perf_counter();self.calls+=1
            physical=self.probe(deepcopy(self.history),deepcopy(row)) if self.probe else self._probe(self.history,row)
            physical=dict(physical,AC_wall_seconds=perf_counter()-began)
            self.cache[key]=deepcopy(physical)
            while len(self.cache)>self.max_cache:self.cache.popitem(last=False)
        receipt=dict(physical,uid=uid,time_seconds=now,candidate_GPU=vector.tolist(),candidate_P=row['P'],candidate_Q=row['Q'],
            input_sha=key,cache_hit=hit,current_candidate_added=True,baseline_PASS_is_candidate_authority=False,
            exogenous_receipt=observed,future_Actual_or_Tap_or_Completion_reads=0,
            admission_scope='EXACT_CURRENT_TIME_ONLY_NOT_FUTURE_ELECTRICAL_GUARANTEE')
        self.audit.append(deepcopy(receipt));return receipt

    def predicted_score(self,now,metadata,site,public_jobs):
        """Counterfactual AC under held current exogenous inputs, never Actual.

        Public nominal completion is a soft prediction only. Its predicted
        AUTO actions never feed back into current admission or physical GPU.
        """
        if now!=self.now:raise ValueError('PREDICTION_CURRENT_WATERMARK_REQUIRED')
        first=int((now-self.begin)/900);finish=now+max(float(metadata['t50_seconds']),1e-9)
        stop=min(96,max(first+1,math.ceil((finish-self.begin)/900)))
        obs=self.observations.at(now,observed_now=now);weather=obs['weather']['values'];rows=[]
        for t in range(first,stop):
            begin=self.begin+t*900;end=begin+900;gpu=np.zeros(len(self.sites))
            for uid,m in public_jobs.items():
                if m.get('state')!='RUNNING':continue
                nominal_end=now+max(0.,m['t50_seconds']-m.get('accumulated_compute_seconds',0.))
                if t==first or min(end,nominal_end)>max(begin,now):gpu[self.sites.index(m['current_site'])]+=m['gpu']
            if min(end,finish)>max(begin,now):gpu[self.sites.index(site)]+=metadata['gpu']
            power=self.model.recompute(gpu[None,:],self.sites,[weather])
            rows.append(dict(slot=t,start_seconds=begin,GPU=gpu.tolist(),P=power['PCC_P_kw'][0].tolist(),
                Q=power['PCC_Q_kvar'][0].tolist(),observations=obs))
        if perf_counter()-self.tick_began>self.max_tick_seconds:
            return dict(status='NOT_CERTIFIED',reason='PREDICTION_TICK_RESOURCE_LIMIT')
        # Fixture probes must implement this separate contract explicitly.
        if self.probe is not None:
            callback=getattr(self.probe,'predicted_score',None)
            result=callback(deepcopy(rows)) if callback else dict(status='NOT_CERTIFIED',reason='NO_VALIDATED_PREDICTION_PROBE')
        else:
            self.prediction_calls+=1
            proof=self._probe(self.history,rows[0],future_rows=rows)
            result=dict(status='PASS',grid_peak=max(s['maximum_phase_line_loading'] for s in proof['physical_steps']
                if s['kind'].startswith('CONDITIONAL_PUBLIC_')),physical_receipt=proof)
        result.update(checked_slots=list(range(first,stop)),projection='PUBLIC_Q50_AND_CURRENT_EXOGENOUS_HOLD',
            future_Actual_Tap_Completion_reads=0,predicted_AUTO_actions_are_not_Actual_state=True,
            current_hard_veto=False,nominal_horizon_tail_seconds=max(0.,finish-(self.begin+86400)),tail_carry_certified=False)
        self.prediction_audit.append(deepcopy(result));return result

    def _probe(self,history,current,future_rows=None):
        from .actual_validation import _validated_hardware_context,mess_service_bindings
        from v42_regcontrol import authority
        from v42_regcontrol.runner import background
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        from v42_voltage_control.svr import install
        from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
        steps=[];all_rows=[*history,*(future_rows or [current])]
        # The shape-only suffix is held current data, never future Actual.
        stamps=[datetime.fromtimestamp(self.begin+(t+1)*900,AEST).isoformat() for t in range(96)]
        demand=[];pv=[]
        for t in range(96):
            r=all_rows[t] if t<len(all_rows) else current
            demand.append(r['observations']['demand']['values']['demand_mw'])
            pv.append(r['observations']['pv']['values']['pv_mw'])
        with self._hardware_context() as scenario:
            source=authority.source();bg_key=digest(dict(stamps=stamps,demand=demand,pv=pv))
            if bg_key not in self._background_cache:
                self._background_cache[bg_key]=background(stamps,demand,pv)
                while len(self._background_cache)>2:self._background_cache.popitem(last=False)
            bg=self._background_cache[bg_key]
            from dayahead.v28r2.opendss_mapping import _set_generator,_set_load,mess_injection_mapping
            engine,adapter,initial=authority.compile_verified()
            try:
                equipment=_equipment(engine);nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
                native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
                svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL','2025-05-01');clock.bind(engine)
                assert_control_inventory(source['inventory'](engine),scenario,initial=True)
                aliases,_=mess_service_bindings(source,self.mess['P_by_site'])
                def apply(r):
                    t=r['slot'];native.apply(engine,bg,t)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[t].get(loc,0),0)
                    for j in range(len(self.sites)):_set_load(engine,f'IDC_IDC{j+1:02d}',r['P'][j],r['Q'][j])
                    for site,names in aliases.items():
                        inj=mess_injection_mapping(self.mess['P_by_site'][site][t],self.mess['Q_by_site'][site][t])
                        _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                        _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                def measure(kind):
                    physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                    ok=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS'])
                    lines=[r for r in physical['currents'] if r['element'].lower().startswith('line.')]
                    steps.append(dict(native_seconds=seconds(engine),kind=kind,PASS=ok,
                        voltage_min_pu=physical['voltage_min_pu'],voltage_max_pu=physical['voltage_max_pu'],
                        maximum_phase_line_loading=max((r['loading_pu'] for r in lines),default=0.),
                        physical_sha=digest(physical),SVR_sha=digest(hardware),
                        SVR_hardware_PASS=hardware['hardware_PASS'],SVR_voltage_PASS=hardware['added_nodes_voltage_PASS'],
                        checked_nodes=len(physical['nodes']),checked_current_rows=len(physical['currents']),
                        violations={k:v for k,v in physical.items() if 'violation' in k},
                        worst_line=max(lines,key=lambda r:r['loading_pu'],default=None)))
                for row in history:
                    apply(row);clock.settle_slot(engine,row['slot'],observer=lambda event:measure(event['kind']))
                apply(current)
                expected=current['slot']*900
                if seconds(engine)!=expected:raise ValueError('CURRENT_AC_NATIVE_CLOCK_DRIFT')
                engine.Solution.SolveSnap()
                pending=queue(engine)
                if (not engine.Solution.Converged() or not engine.Solution.ControlActionsDone()
                        or any(item['absolute_seconds']<=expected for item in pending)):
                    raise ValueError('CURRENT_AC_DUE_ACTION_OR_CONVERGENCE_FAILURE')
                measure('CURRENT_CANDIDATE_ONLY_NO_FUTURE_TAP_EXECUTION')
                assert_control_inventory(source['inventory'](engine),scenario)
                current_ok=steps[-1]['PASS'];prefix_ok=all(r['PASS'] for r in steps[:-1])
                if future_rows:
                    for row in future_rows:
                        apply(row);clock.settle_slot(engine,row['slot'],
                            observer=lambda event:measure('CONDITIONAL_PUBLIC_'+event['kind']))
                return dict(PASS=current_ok,status='PASS' if current_ok else 'PHYSICAL_FAIL',
                    historical_prefix_physical_PASS=prefix_ok,physical_steps=steps,
                    current_native_seconds=expected,future_queue_not_executed=pending,
                    original_RegControl=7,SVR_count=11,
                    future_native_Tap_actions_executed=0 if not future_rows else None,
                    conditional_predicted_AUTO_substeps=sum(s['kind'].startswith('CONDITIONAL_PUBLIC_') for s in steps),
                    prediction_is_not_Actual_Tap_observation=bool(future_rows))
            finally:engine.Basic.ClearAll()
