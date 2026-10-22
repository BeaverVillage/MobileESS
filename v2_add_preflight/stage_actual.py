"""Causal Source-YY/SVR3 electrical IO for the original event controller.

The admission algorithm is inherited. Only its current-AC backend changes to
the frozen IEEE8500 hardware and native TIME queue. A new engine independently
replays observed history on each cache miss. No Planning tap replay occurs.
"""
from datetime import datetime,timedelta,timezone
import copy,math,types
import numpy as np
from .stage_common import *
from .prestart_native import native_zero
from v43_actual.current_ac import OriginalCurrentAC

AEST=timezone(timedelta(hours=10))

def source_engine(tag):
    import uuid
    from . import may01_voltage as voltage
    previous=voltage.RUN;voltage.RUN=WORK/'actual_engine'
    voltage.RUN.mkdir(parents=True,exist_ok=True)
    try:return voltage.engine('STAGE_'+tag+'_'+uuid.uuid4().hex[:8],'ACTUAL','H0_SOURCE_YY')
    finally:voltage.RUN=previous

def observed_totals(issue,rows):
    from v42_regcontrol.runner import background
    totals={k:[] for k in ('P','Q','PV')}
    for first in range(0,len(rows),96):
        page=rows[first:first+96];padded=page+[page[-1]]*(96-len(page))
        stamps=[datetime.fromtimestamp(issue+(first+t+1)*900,AEST).isoformat() for t in range(96)]
        b=background(stamps,[r['observations']['demand']['values']['demand_mw'] for r in padded],
            [r['observations']['pv']['values']['pv_mw'] for r in padded])
        for t in range(len(page)):
            totals['P'].append(math.fsum(b.gross_p_kw_96[t].values()))
            totals['Q'].append(math.fsum(b.gross_q_kvar_96[t].values()))
            totals['PV'].append(math.fsum(b.pv_generation_kw_96[t].values()))
    return {k:np.asarray(v) for k,v in totals.items()}

def bind_inputs(e,rows,issue):
    bg=observed_totals(issue,rows);n=len(rows)
    e.inputs={'ACTUAL_AIDC_P_kw':np.array([r['P'] for r in rows]),'ACTUAL_AIDC_Q_kvar':np.array([r['Q'] for r in rows]),
        'ACTUAL_PV_P_kw':bg['PV'][:,None],'ACTUAL_PV_Q_kvar':np.zeros((n,1))}
    e.bg={}
    for key,unit in (('P','kw'),('Q','kvar')):
        weights=np.array([r[unit] for r in e.loads]);weights/=math.fsum(weights)
        allocation=bg[key][:,None]*weights
        for t in range(n):allocation[t,int(weights.argmax())]+=bg[key][t]-math.fsum(allocation[t])
        e.bg['ACTUAL_'+key]=allocation
    from .correction_time100 import clock_class
    Clock,e.queue=clock_class();e.clock=Clock('ACTUAL','2025-05-01');e.clock.bind(e.d)
    e.capture=True

class CurrentAC(OriginalCurrentAC):
    def __init__(self,*args,mess_plan=None,**kw):
        super().__init__(*args,**kw);self.mess_plan=copy.deepcopy(mess_plan)
        self.mess_sha=digest(self.mess_plan)
        self.hardware_sha=read(OUT/'SOURCE_YY_HARDWARE_FREEZE.json')['hardware_sha']
    def _probe(self,rows):
        start=time.perf_counter();assert rows and len(rows)<=120
        assert self.mess_sha==digest(self.mess_plan),'FROZEN_ACTUAL_MESS_PLAN_DRIFT'
        assert self.hardware_sha==read(OUT/'SOURCE_YY_HARDWARE_FREEZE.json')['hardware_sha']
        for t,row in enumerate(rows):
            assert row['slot']==t and row['start_seconds']==self.issue+900*t
            assert row['start_seconds']<=self.now
        e=source_engine('CURRENT_'+str(self.calls));bind_inputs(e,rows,self.issue);steps=[]
        try:
            for t,row in enumerate(rows):
                guard(start)
                mess={}
                if self.mess_plan is not None and t>=24:
                    plan=self.mess_plan
                    if plan['time_axis']!=list(range(96)) or plan['P_sign']!='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch':
                        raise ValueError('ACTUAL_MESS_PLAN_AXIS_SIGN')
                    for s in plan['P_by_site']:mess[s]=(-plan['P_by_site'][s][t-24],-plan['Q_by_site'][s][t-24])
                e.apply('ACTUAL',t,2.,mess=mess)
                r,_,state,ports=e.measure('ACTUAL',t,2.)
                a=e.event_arrays[-1];v=np.asarray(a['node_voltage_pu']);line=np.asarray(a['line_rho'])
                tx=np.asarray(a['transformer_current_rho']);kva=np.asarray(a['transformer_winding_nameplate_kva_rho'])
                violations=dict(voltage=int(np.sum((v<.95-1e-8)|(v>1.05+1e-8))),
                    lines=int(np.sum(line[e.security]>1+1e-8)),transformer_current=int(np.sum(tx>1+1e-8)),transformer_kVA=int(np.sum(kva>1+1e-8)),
                    mobile_port=int(e.event_rows[-1]['port_violation_cells']))
                steps.append(dict(slot=t,PASS=bool(e.event_rows[-1]['physics_PASS']) and not any(violations.values()),violations=violations,
                    Vmin=float(v.min()),Vmax=float(v.max()),rho=float(line[e.canonical].max()),
                    queue=e.queue(e.d),state=state,native_events=len(e.event_arrays),
                    initial_or_event_voltage_violations_retained=[dict(low=int(np.sum(np.asarray(a['node_voltage_pu'])<.95)),
                        high=int(np.sum(np.asarray(a['node_voltage_pu'])>1.05))) for a in e.event_arrays]))
            e.check_parameters()
            return dict(PASS=steps[-1]['PASS'],current=steps[-1],physical_steps=steps,
                historical_prefix_physical_PASS=all(s['PASS'] for s in steps[:-1]),original_RegControl=12,added_SVR_count=3,
                hardware_sha=self.hardware_sha,control_mode='NATIVE_TIME_SOURCE_YY_SVR3',
                voltage_measurement='source settled tick; every-event excursions retained separately',
                Planning_Tap_replay=False,source_initial_state_replayed=True,future_observations_read=0,
                Native_global_optimizer_calls=0)
        finally:e.d.Basic.ClearAll()
    def evaluate(self,*args,**kw):
        result=super().evaluate(*args,**kw)
        # The inherited cache is private to a hardware/plan-bound instance.
        result.update(delayed_TIME_actuation_certificate='NATIVE_QUEUE_REPLAYED',
            scope='IEEE8500_SOURCE_YY_SVR3_CAUSAL_CURRENT_CANDIDATE',hardware_sha=self.hardware_sha)
        return result


def controller_type(arm,*,known_policy=None,initial_running=(),rack_limits=None):
    """Original dispatch; causal historical site/hold IO includes migration.

    The source prefix reader attributes a whole past interval to current_site.
    That is invalid after an observed migration. Reconstruct only past GPU
    holds from public phase receipts; no admission/ranking rule is replaced.
    """
    from v44.actual_policy import controller_class
    selected=controller_class(arm,known_policy)
    if arm in ('B0','B2'):
        def baseline(*a,**kw):return selected(*a,rack_limits=rack_limits,**kw)
        return baseline
    initial={r.uid:(site,0.) for r,site,start in initial_running}
    class Controller(selected):
        def _observed_prefix(self,now):
            from .stage_work import intervals,integrate
            oracle=self.policy.oracle;wanted=int((now-oracle.issue)/900)
            assert wanted>=0 and wanted*900==now-oracle.issue
            for slot in range(len(self.prefix_history),wanted):
                begin=oracle.issue+slot*900;end=begin+900;gpu=np.zeros((1,len(oracle.sites)))
                for uid,request in self.requests.items():
                    _,holds=intervals(uid,begin=oracle.issue,end=end,initial=initial.get(uid),events=self.events,
                        migrations=[m for m in self.migrations if m['physical_checkpoint_seconds']<=end])
                    integrate(gpu,holds,request.gpu,oracle.sites,begin)
                obs=oracle.observations.at(begin,observed_now=now)
                power=oracle.model.recompute(gpu,oracle.sites,[obs['weather']['values']])
                self.prefix_history.append(dict(slot=slot,start_seconds=begin,end_seconds=end,
                    GPU=gpu[0].tolist(),P=power['PCC_P_kw'][0].tolist(),Q=power['PCC_Q_kvar'][0].tolist(),observations=obs,
                    authority='OBSERVED_PUBLIC_EVENT_AND_MIGRATION_PHASE_HOLD_INTERVAL_INTEGRAL'))
            return self.prefix_history
    return Controller

def fresh_handler(day,arrays,plan,folder):
    """New engine twice; evaluate actual adopted Job P/Q and MESS, not B0 AC."""
    from . import full_days
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    if set(arrays)=={'P','Q'}:
        from .full_weather import observations
        obs=observations(day,day['axis']['issue_seconds'],day['axis']['end_seconds'])
        bg=full_days.background_totals(day,'ACTUAL',obs)
        arrays=dict(PLANNING_AIDC_site=np.array([f'AIDC{i:02d}' for i in range(1,13)]),
            ACTUAL_AIDC_P_kw=arrays['P'],ACTUAL_AIDC_Q_kvar=arrays['Q'],
            ACTUAL_BG_P=bg['P'],ACTUAL_BG_Q=bg['Q'],ACTUAL_PV_P_kw=bg['PV'][:,None],ACTUAL_PV_Q_kvar=np.zeros((120,1)))
    assert arrays['ACTUAL_AIDC_P_kw'].shape==arrays['ACTUAL_AIDC_Q_kvar'].shape==(120,12)
    engines=[]
    def engine(tag,role):
        if role!='ACTUAL':raise ValueError('ACTUAL_FRESH_ROLE')
        e=source_engine('FRESH_'+tag);engines.append(e);old=e.apply
        def apply(role,t,beta,mess=None,aidc_delta=None):
            fixed={} if t<24 or plan is None else {s:(-plan['P_by_site'][s][t-24],-plan['Q_by_site'][s][t-24]) for s in plan['P_by_site']}
            return old(role,t,beta,mess=fixed,aidc_delta=aidc_delta)
        e.apply=apply;return e
    def isolated_table(name,rows):
        import csv
        path=folder/(name+'.csv')
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,engine=engine,guard=guard,table=isolated_table),argdefs=full_days.run.__defaults__)
    fn.__kwdefaults__=full_days.run.__kwdefaults__
    try:
        actual=fn(day,'ACTUAL',arrays);fresh=fn(day,'ACTUAL',arrays,fresh=True)
        results=[];paths=[]
        for receipt in (actual,fresh):
            path=Path(receipt['files']['AC.npz']['path']).parent;paths.append(path)
            events=read(path/'EVENTS.json');clock=read(path/'CLOCK.json')
            with np.load(path/'AC.npz') as z:slots=z['event_slot']
            final=[events[int(np.flatnonzero(slots==t)[-1])] for t in range(120)]
            assert all(e['physical_seconds']==clock[t]['last_solve_seconds'] for t,e in enumerate(final))
            results.append(dict(PASS=all(e['physics_PASS'] for e in final),
                prefix24_PASS=all(e['physics_PASS'] for e in final[:24]),
                evaluation96_PASS=all(e['physics_PASS'] for e in final[24:]),
                Vmin=min(e['Vmin'] for e in final[24:]),Vmax=max(e['Vmax'] for e in final[24:]),
                rho_global=max(e['rho_global'] for e in final[24:]),
                complete_all_terminal_transformer_port_balance_queue_checks=True))
        errors={}
        with np.load(paths[0]/'AC.npz') as aa,np.load(paths[1]/'AC.npz') as ff:
            assert aa.files==ff.files
            for key in aa.files:
                a,b=aa[key],ff[key]
                errors[key]=float(np.max(abs(a-b))) if a.shape==b.shape else None
        state_equal=read(paths[0]/'STATES.json')==read(paths[1]/'STATES.json')
        queue_equal=read(paths[0]/'CLOCK.json')==read(paths[1]/'CLOCK.json')
        equal=state_equal and queue_equal and all(v is not None and v<1e-9 for v in errors.values())
        return dict(PASS=all(r['PASS'] for r in results) and equal,actual=actual,fresh=fresh,
            settled_tick_results=results,independent_engine=True,independent_new_engine=True,
            Fresh_max_error=errors,states_equal=state_equal,queues_equal=queue_equal,
            adopted_P_sha=digest(arrays['ACTUAL_AIDC_P_kw'].tolist()),adopted_Q_sha=digest(arrays['ACTUAL_AIDC_Q_kvar'].tolist()),
            MESS_plan_sha=None if plan is None else plan['plan_sha'],source_settled_contract_required=True,
            event_envelope_diagnostics_preserved=True,optimization_outcome_claim=False)
    finally:
        for e in engines:e.d.Basic.ClearAll()

def certify_current_fixture():
    with measured('ACTUAL_CURRENT_AC_AND_QOS_HANDLER_CERTIFICATION.json') as (report,start),native_zero() as denied:
        day=day_inputs()
        from .full_jobs import prepare
        args=prepare(day,'STAGE_CURRENT_AC_FIXTURE')
        # Source request preparation writes its receipts in its legacy default
        # directory. It is invoked with a unique tag; no old result overwritten.
        # Reuse exact source frozen C1 with public, causally observed weather.
        from .full_weather import observations
        issue=day['axis']['issue_seconds'];obs=observations(day,args['begin'],args['end'])
        from v43_actual.case import power_model
        model,sources=power_model(read(day['files']['power_authority']['path']),args['capacities'])
        sites=tuple(args['capacities']);gpu=np.zeros(12);results=[]
        for independent in range(2):
            oracle=CurrentAC(issue_seconds=issue,sites=sites,power_model=model,observations=obs)
            history=[]
            for t in range(2):
                now=issue+900*t;oracle.observe(now,history);proof=oracle.evaluate(now,gpu,uid='FINITE_NATIVE0_ADMISSION_FIXTURE')
                results.append(dict(independent=independent,slot=t,current=proof['current'],source=proof['hardware_sha']))
                observed=obs.at(now,observed_now=now);p=model.recompute(gpu[None,:],sites,[observed['weather']['values']])
                history.append(dict(slot=t,start_seconds=now,end_seconds=now+900,GPU=gpu.tolist(),P=p['PCC_P_kw'][0].tolist(),
                    Q=p['PCC_Q_kvar'][0].tolist(),observations=observed))
        errors={k:max(abs(results[t]['current'][k]-results[t+2]['current'][k]) for t in range(2)) for k in ('Vmin','Vmax','rho')}
        assert max(errors.values())<1e-9
        report.update(PASS=False,current_AC_backend_implemented=True,current_AC_two_tick_Fresh_fixture_PASS=True,
            two_tick_measured_results=results,independent_Fresh_max_error=errors,source_C1=sources,Fresh_actual120_backend_implemented=True,
            original_controller=record(ROOT/'v43_actual/controller.py'),source_event_engine=record(ROOT/'v43_actual/vendor/actual.py'),
            original_current_guard=record(ROOT/'v43_actual/current_ac.py'),
            Known_Unknown_controller_production_binding_PASS=False,independent_migration_work_WAN_PASS=False,
            fixture_preparation_complete=True,denied_attempts=denied,
            reason='Backend admission must be tested with the source frozen-policy/observation API and complete migration phase replay before production certification')

if __name__=='__main__':certify_current_fixture()
