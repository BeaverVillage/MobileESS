"""Performance-only native engine implementation; frozen search is unchanged."""
import os,time,gc
import numpy as np
from common import Path,save,digest
import qsafe as authoritative
from dayahead.v28r2 import opendss_backend as backend
from dayahead.v28r2.opendss_mapping import REGULATORS,CAPACITORS
from dayahead.run_v16_3_voltage_candidate import _enable_native_controls

STATE_SETTERS=('Hour','Seconds','Year','Frequency','LoadMult','GenMult','MaxIterations','MinIterations','MaxControlIterations','Convergence','Algorithm','LoadModel','StepSize','Number')

class CachedPrefixEngine(authoritative.PrefixEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.odd=None;self.slot=-1;self.start=None;self.last_q=None;self.cached_trial_count=0
        self.fallback=False;self.fallback_reason=None;self.state_records=[]

    def _compile(self):
        cwd=Path.cwd();self.odd,adapter=backend.compile_clean_engine(self.assets)
        self.odd.Basic.AllowChangeDir(False);self.odd.Basic.DataPath(str(self.folder));os.chdir(cwd)
        self.adapter=adapter;self.compile_count+=1;self.version=str(self.odd.Basic.Version())

    def _apply(self,t,q):
        prior=self.trajectory.mess_q_kvar[t].copy();self.trajectory.mess_q_kvar[t]=q
        try:backend.apply_trajectory_slot(self.odd,self.adapter,self.context,self.trajectory,t)
        finally:self.trajectory.mess_q_kvar[t]=prior

    def _capture(self,t):
        d=self.odd;taps,caps=backend._native_state(d);regs=[]
        for name in d.RegControls.AllNames():
            d.RegControls.Name(name)
            regs.append(dict(name=name,tap_number=d.RegControls.TapNumber(),reversible=d.RegControls.IsReversible(),delay=d.RegControls.Delay(),tap_delay=d.RegControls.TapDelay(),forward_vreg=d.RegControls.ForwardVreg(),forward_band=d.RegControls.ForwardBand(),reverse_vreg=d.RegControls.ReverseVreg(),max_tap_change=d.RegControls.MaxTapChange()))
        loads=[];generators=[]
        for name in d.Loads.AllNames():d.Loads.Name(name);loads.append([name,d.Loads.kW(),d.Loads.kvar()])
        for name in d.Generators.AllNames():d.Generators.Name(name);generators.append([name,d.Generators.kW(),d.Generators.kvar()])
        return dict(slot=t,physical_timestamp_local=f'{self.trajectory.day}T{t//4:02}:{t%4*15:02}:00+10:00',solution_mode=int(d.Solution.Mode()),control_mode=int(d.Solution.ControlMode()),solution={k:getattr(d.Solution,k)() for k in STATE_SETTERS},control_actions_done=d.Solution.ControlActionsDone(),control_iterations=d.Solution.ControlIterations(),taps=taps,capacitors=caps,regcontrols=regs,queue_size=d.CtrlQueue.QueueSize(),queue=d.CtrlQueue.Queue(),action_count=d.CtrlQueue.NumActions(),solution_initialized=d.YMatrix.SolutionInitialized(),loads_need_update=d.YMatrix.LoadsNeedUpdating(),iteration=d.YMatrix.Iteration(),node_voltages=d.YMatrix.getV(),node_currents=d.YMatrix.getI(),node_order=d.Circuit.YNodeOrder(),native_loads=loads,native_generators=generators,fixed_P=self.trajectory.mess_p_kw[t].tolist(),locations=self.trajectory.mess_locations_96x4[t].tolist(),AIDC_P=self.trajectory.pcc_p_kw[t].tolist(),AIDC_Q=self.trajectory.pcc_q_kvar[t].tolist())

    def _restore_and_solve(self,t,q):
        d=self.odd;s=self.start
        d.CtrlQueue.ClearQueue();d.CtrlQueue.ClearActions()
        for name in d.RegControls.AllNames():d.RegControls.Name(name);d.RegControls.Reset()
        for name,tap in zip(REGULATORS,s['taps']):d.Transformers.Name(name);d.Transformers.Wdg(2);d.Transformers.Tap(tap)
        for name,cap in zip(CAPACITORS,s['capacitors']):d.Capacitors.Name(name);d.Capacitors.States([cap])
        for key,value in s['solution'].items():getattr(d.Solution,key)(value)
        d.Solution.ControlMode(s['control_mode'])
        self._apply(t,q)
        d.Solution.BuildYMatrix(2,True)
        assert d.Circuit.YNodeOrder()==s['node_order'],'CACHED_NODE_ORDER_DRIFT'
        vp=d.YMatrix.VVector();ip=d.YMatrix.IVector()
        for i,v in enumerate(s['node_voltages']):vp[i]=v
        for i,v in enumerate(s['node_currents']):ip[i]=v
        d.YMatrix.SolutionInitialized(s['solution_initialized']);d.YMatrix.LoadsNeedUpdating(s['loads_need_update']);d.YMatrix.Iteration(s['iteration'])
        d.Solution.ControlActionsDone(s['control_actions_done']);d.Solution.ControlIterations(s['control_iterations'])
        assert backend._native_state(d)==(s['taps'],s['capacitors']),'CACHED_START_NATIVE_STATE_DRIFT'
        _enable_native_controls(d);d.Solution.SolveSnap();self.solve_count+=1
        assert d.Solution.Converged(),'CACHED_DSS_NONCONVERGENCE'
        self.last_q=np.asarray(q).copy()

    def _start_slot(self,t,q):
        if self.odd is None:
            self._compile()
            # Standalone difficult-slot regressions can enter at t>0. Production
            # enters at zero; its approved prefix is carried sequentially.
            for s in range(t):
                self._apply(s,self.trajectory.mess_q_kvar[s])
                if s==0:backend.apply_frozen_native_state(self.odd,self.voltage,0)
                _enable_native_controls(self.odd);self.odd.Solution.SolveSnap();self.solve_count+=1
                assert self.odd.Solution.Converged() and backend._native_state(self.odd)[0]==self.accepted_taps[s]
        elif t!=self.slot:
            assert t==self.slot+1,'NONSEQUENTIAL_CACHED_SLOT'
            # On unresolved search the last tested Q need not be the accepted
            # baseline. Commit only the Q that the frozen runner accepted.
            accepted=self.trajectory.mess_q_kvar[self.slot]
            if not np.array_equal(self.last_q,accepted):self._restore_and_solve(self.slot,accepted)
            assert backend._native_state(self.odd)[0]==self.accepted_taps[-1],'UNACCEPTED_NATIVE_STATE_PROPAGATION'
        self._apply(t,q)
        if t==0:backend.apply_frozen_native_state(self.odd,self.voltage,0)
        self.slot=t;self.start=self._capture(t)
        s=self.start
        # Unsupported hidden/dynamic control situations retain full-prefix replay.
        if s['queue_size'] or s['action_count'] or s['solution_mode']!=0 or any(r['reversible'] for r in s['regcontrols']):
            self.fallback=True;self.fallback_reason='UNSUPPORTED_QUEUE_DYNAMIC_OR_REVERSIBLE_CONTROL_STATE'
        expected=self.voltage['regulator_taps'][0].tolist() if t==0 else self.accepted_taps[t-1]
        assert s['taps']==expected and s['capacitors']==self.voltage['capacitor_states'][t].tolist()
        save(self.folder/'SLOT_START_CACHE'/f'{t:02}.json',s)
        self.state_records.append(dict(slot=t,state_SHA=digest(s),fallback=self.fallback))

    def evaluate(self,t,q):
        if self.fallback:return super().evaluate(t,q)
        try:
            if t!=self.slot:self._start_slot(t,q)
            if self.fallback:return super().evaluate(t,q)
            self._restore_and_solve(t,q)
        except Exception as error:
            # No failed fast trial state propagates. All subsequent trials use
            # the original exact engine and approved prefix, without rule changes.
            self.fallback=True;self.fallback_reason=repr(error)
            save(self.folder/'PERFORMANCE_FALLBACK.json',dict(slot=t,reason=self.fallback_reason,authoritative_prefix_retained=True))
            return super().evaluate(t,q)
        odd=self.odd
        v=backend._voltage_vector(odd,self.nodes);m=np.asarray([backend._branch_measurement(odd,b) for b in self.branches]);losses=np.asarray(odd.Circuit.Losses())[:2]/1000;taps,caps=backend._native_state(odd)
        expected={}
        for j,location in enumerate(self.trajectory.mess_locations_96x4[t]):
            if str(location).startswith('TRANSIT_'):continue
            ep=expected.setdefault(str(location).upper(),[0.,0.]);ep[0]+=self.trajectory.mess_p_kw[t,j];ep[1]+=q[j]
        delivered=[];maxerr=0.
        for prefix in ('IDC','STA'):
            for i in range(1,13):
                service=f'{prefix}{i:02d}';odd.Generators.Name('MESS_DIS_'+service);gp=float(odd.Generators.kW());gq=float(odd.Generators.kvar());odd.Loads.Name('MESS_CHG_'+service);lp=float(odd.Loads.kW());lq=float(odd.Loads.kvar());ep,eq=expected.get(service,[0.,0.]);maxerr=max(maxerr,abs(gp-lp-ep),abs(gq-lq-eq));delivered.append(dict(service=service,P_EXEC_set=gp-lp,Q_EXEC_set=gq-lq))
        for i in range(12):odd.Loads.Name(f'IDC_IDC{i+1:02d}');maxerr=max(maxerr,abs(odd.Loads.kW()-self.trajectory.pcc_p_kw[t,i]),abs(odd.Loads.kvar()-self.trajectory.pcc_q_kvar[t,i]))
        assert maxerr<1e-9,'CACHED_ENGINE_SETPOINT_BINDING'
        r=dict(v=v,ia=m[:,0],ipu=m[:,1],kva=m[:,2],losses=losses,taps=taps,caps=caps,converged=True,readback=delivered,readback_max_error=maxerr)
        self.trace.append(dict(slot=t,Q=np.asarray(q).tolist(),start_taps=self.start['taps'],final_taps=taps,max_actual_slot_applied=t,Vmin=float(v.min()),Vmax=float(v.max()),max_current=float(m[:,1].max()),max_tx_kva=float(np.nanmax(m[:,2])),feasible=authoritative.feasible(r),engine_PQ_setpoint_max_error=maxerr,cached_slot_start=True))
        self.cached_trial_count+=1
        return r

    def result(self,rows,elapsed):
        save(self.folder/'PERFORMANCE_IMPLEMENTATION_AUDIT.json',dict(version='EXACT_SLOT_STATE_CACHE_V1',cached_Q_trials=self.cached_trial_count,compiled_engines=self.compile_count,native_solves=self.solve_count,slot_states=self.state_records,full_prefix_fallback=self.fallback,fallback_reason=self.fallback_reason,search_rules_unchanged=True))
        result=super().result(rows,elapsed)
        if self.odd is not None:self.odd.Basic.ClearAll();self.odd=None;gc.collect()
        return result
