"""Single preregistered sequential 600s ORIGINAL-M1 comparison; development only."""
from pathlib import Path
import json,time,threading,subprocess,os,traceback,csv,ctypes,math
import numpy as np
import psutil
import gurobipy as gp
from v42_degen.identity import inputs,signature
from v42_degen.common import POLICY,ENV
from v42_dw_root.partition import axes
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities,prototypes
from v42_rowgen.core import OriginalRows,separate,security_axis,TOL,row_digest
from v42_rowgen.native import build,add,transport_audit
from audit_grid_rowgen import ROOT,OUT,write,sha

def gap(ub,lb):return max(0.,ub-lb)/max(abs(ub),1e-10)
def safe_native_bound(v):
    if not math.isfinite(v) or abs(v)>=1e90:return None
    return float(np.nextafter(v-1e-8,-np.inf))

class PERF(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong)]+[(k,ctypes.c_size_t) for k in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(k,ctypes.c_ulong) for k in ('HandleCount','ProcessCount','ThreadCount')]

class PassiveMemory:
    def __init__(self,begin):self.begin=begin;self.arm='preflight';self.data=[];self.stop=threading.Event()
    def sample(self):
        p=psutil.Process().memory_info();v=psutil.virtual_memory();t=PERF();t.cb=ctypes.sizeof(t)
        ok=ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(t),t.cb)
        return dict(wall=time.perf_counter()-self.begin,arm=self.arm,RSS=p.rss,process_commit=getattr(p,'pagefile',None),free_RAM=v.available,
            system_commit=int(t.CommitTotal*t.PageSize) if ok else None,system_commit_limit=int(t.CommitLimit*t.PageSize) if ok else None)
    def run(self):
        while not self.stop.is_set():self.data.append(self.sample());self.stop.wait(1.)
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def finish(self):self.stop.set();self.thread.join(timeout=2);self.data.append(self.sample())

class Comparison:
    def __init__(self):
        os.environ.update(ENV)
        assert json.loads((OUT/'ROW_GENERATION_EXACTNESS.json').read_text())['PASS']
        assert json.loads((OUT/'ROW_GENERATION_SEPARATOR_TESTS.json').read_text())['PASS']
        assert json.loads((OUT/'ROW_GENERATION_INITIAL_MASTER_CENSUS.json').read_text())['materially_smaller']
        self.A,self.d,self.B,self.e,self.identity,self.freeze=inputs()
        self.fullgrid=security_axis(self.d)
        self.route_mask=pure_binary_equalities(self.A,self.d)
        owner,rowowner=axes();self.owner=owner
        with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
        self.blocks=prototypes(self.B,self.e,owner,rowowner,native)
        source=ROOT/'docs/v42_m1_conservative_early_bap_20261006/VALID_INTEGER_ORIGINAL_POINT.npz'
        with np.load(source) as z:self.seed=z['point'].copy()
        seedcheck=self.validate(self.seed);assert seedcheck['PASS']
        self.initial_ub=seedcheck['objective']
        frozen=json.loads((ROOT/'docs/v42_m1_conservative_early_bap_20261006/certificate/SPLIT_DUAL_GATES.json').read_text())
        assert frozen['EXACT_DUAL_AUTHORITY_FOR_BAP']
        self.initial_lb=frozen['current_certified_conservative_global_LB']
        self.commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        self.trajectory=[];self.calls=[];self.results=[]
        write('MICROBENCHMARK_INPUT_FREEZE.json',dict(source_commit=self.commit,scientific_identity=self.identity,
            source_worktree_SHA={p:sha(ROOT/p) for p in ('benchmark_grid_rowgen.py','run_grid_comparison.py','v42_rowgen/core.py','v42_rowgen/native.py')},
            signature=signature(self.B,self.e),start_point_SHA=sha(source),start_validation=seedcheck,
            inherited_floor=self.initial_lb,initial_UB=self.initial_ub,initial_gap=gap(self.initial_ub,self.initial_lb),
            Start_only=True,all_original_variables_unfixed=True,fixture_optimization_not_fullscale=True,
            shared_wall_budget=600,arm_wall_allocation=280,native_stop_request_margin=5,solver_settings=dict(POLICY,TimeLimit='remaining original arm wall minus5s'),
            original_P1_gap=.005,near_critical_threshold=None,all_violated_rows_mandatory=True))
    def validate(self,x):
        raw=corrected_rows(self.A,self.d,x,True,self.route_mask)
        grid=separate(self.A,self.d,x,self.fullgrid)
        r=dict(PASS=bool(raw['PASS'] and grid['PASS']),raw=raw,
               exhaustive_grid=dict(PASS=grid['PASS'],checked_rows=grid['checked_rows'],ambiguous_exact_checks=grid['ambiguous_exact_checks'],tolerance=TOL),
               objective=float(self.d['objective']@x+float(self.d['constant'])))
        if r['PASS']:
            physical=[b.validate(x[b.columns],True) for b in self.blocks]
            r.update(PASS=all(a['PASS'] for a in physical),MESS_route_mode_SOC_PCS=physical)
        return r
    def point_record(self,arm,when,ub,lb,kind):
        self.trajectory.append(dict(arm=arm,wall=time.perf_counter()-self.begin,arm_wall=when,UB=ub,LB=lb,gap=gap(ub,lb),kind=kind))
    def arm(self,label,rowgen):
        self.mem.arm=label;begin=time.perf_counter();deadline=min(self.begin+580,begin+280)
        rows=OriginalRows(self.B,self.e)
        if not rowgen:rows.present[:]=True
        axis=list(rows.axis);startrows=len(axis)
        m,v=build(self.B,self.e,np.asarray(axis));settings=dict(POLICY);settings.pop('TimeLimit')
        for k,w in settings.items():m.setParam(k,w)
        m.Params.LogFile=str(OUT/f'{label}.log');m.Params.LogToConsole=0
        identity=transport_audit(m,self.B,self.e,np.asarray(axis))
        variables=m.getVars();m.setAttr('Start',variables,self.seed.tolist())
        best=self.seed.copy();ub=self.initial_ub;lb=self.initial_lb;firstnew=None;firstnative=None
        iterations=[];native=0.;callback_error=[];lastcb=[-1.];nativepoints=0;transport=[identity]
        self.point_record(label,0,ub,lb,'initial inherited full-domain certificates')
        def remember(x,when,kind):
            nonlocal ub,best,firstnew,firstnative,nativepoints
            objective=float(self.e['objective']@x+float(self.e['constant']))
            if objective>ub+1e-8:return
            check=self.validate(x);nativepoints+=1
            if not check['PASS']:return
            if firstnative is None:firstnative=when
            if objective<ub-1e-8:
                ub=objective;best=x.copy()
                if firstnew is None:firstnew=when
                np.savez_compressed(OUT/f'{label}_VALID_NATIVE_{nativepoints:04d}.npz',point=x)
                write(f'{label}_VALID_NATIVE_{nativepoints:04d}.json',check)
                self.point_record(label,when,ub,lb,kind)
        def callback(model,where):
            nonlocal lb
            try:
                now=time.perf_counter()
                if now>=deadline-5:model.terminate()
                if where==gp.GRB.Callback.MIPSOL:
                    remember(np.asarray(model.cbGetSolution(variables)),now-begin,'fully validated native integer point')
                if where==gp.GRB.Callback.MIP and now-lastcb[0]>=1:
                    lastcb[0]=now;value=safe_native_bound(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
                    if value is not None:
                        if value>ub+1e-8:raise ValueError('NATIVE_BOUND_EXCEEDS_CERTIFIED_UB')
                        lb=max(lb,value)
                    self.point_record(label,now-begin,ub,lb,'original-domain/subset native bound with1e-8 safety')
            except BaseException:
                callback_error.append(traceback.format_exc());model.terminate()
        try:
            while time.perf_counter()<deadline-6:
                index=len(iterations)+1;cap=max(.001,deadline-time.perf_counter()-5)
                m.Params.TimeLimit=cap
                callstart=time.perf_counter();timer=threading.Timer(cap,m.terminate);timer.daemon=True;timer.start()
                print('FULLSCALE_NATIVE_START',label,index,'cap',round(cap,3),'rows',m.NumConstrs,flush=True)
                try:m.optimize(callback)
                finally:timer.cancel()
                native+=m.Runtime
                record=dict(arm=label,iteration=index,status=m.Status,SolCount=m.SolCount,native_runtime=m.Runtime,
                    start_wall=callstart-self.begin,end_wall=time.perf_counter()-self.begin,
                    master_rows=m.NumConstrs,objective=m.ObjVal if m.SolCount else None,
                    raw_native_bound=float(m.ObjBound) if abs(m.ObjBound)<1e90 else None,
                    native_gap=m.MIPGap if m.SolCount else None,added_rows=0,root_nodes=m.NodeCount)
                self.calls.append(record)
                if callback_error:raise ValueError(callback_error[0])
                if m.Status not in (2,9,11):raise ValueError('NATIVE_NONACCEPTABLE_STATUS_'+str(m.Status))
                value=safe_native_bound(m.ObjBound)
                if value is not None:
                    if value>ub+1e-8:raise ValueError('NATIVE_BOUND_EXCEEDS_CERTIFIED_UB')
                    lb=max(lb,value)
                if not m.SolCount:
                    iterations.append(dict(iteration=index,status=m.Status,added=0,candidate=None));break
                x=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/f'{label}_ITER_{index:03d}_RAW.npz',point=x)
                remember(x,time.perf_counter()-begin,'fully validated native terminal integer point')
                if not rowgen:
                    iterations.append(dict(iteration=index,status=m.Status,added=0,final_candidate_grid=rows.final(x)['PASS']));break
                r=rows.pending(x);fresh=rows.add(r['violated'])
                iteration=dict(iteration=index,status=m.Status,checked_omitted=r['checked_rows'],all_violated_count=len(fresh),added=len(fresh),
                    active_before=m.NumConstrs,ambiguous_exact_checks=r['ambiguous_exact_checks'])
                if len(fresh):
                    np.savez_compressed(OUT/f'{label}_ITER_{index:03d}_GENERATED_AXES.npz',original_rows=fresh)
                    record['added_rows']=len(fresh)
                    add(m,v,self.B,self.e,fresh);axis.extend(map(int,fresh))
                    transport.append(transport_audit(m,self.B,self.e,np.asarray(axis)))
                    print('ADD_ALL_VIOLATED',label,index,len(fresh),flush=True)
                else:
                    final=rows.final(x);iteration['final_candidate_grid']=final['PASS']
                    if not final['PASS']:iteration['termination']='ACTIVE_ROW_VIOLATION_REJECTED'
                    else:iteration['termination']='EXHAUSTIVE_FINAL_PASS'
                iterations.append(iteration)
                self.point_record(label,time.perf_counter()-begin,ub,lb,'post exhaustive iteration')
                if not len(fresh):break
                if gap(ub,lb)<=.005 and self.validate(best)['PASS']:break
            final=self.validate(best);assert final['PASS']
            np.savez_compressed(OUT/f'{label}_FINAL_VALID_POINT.npz',point=best)
            duration=time.perf_counter()-begin
            resources=[s for s in self.mem.data if s['arm']==label]
            result=dict(arm=label,baseline='fresh full original monolithic' if not rowgen else 'exact all-violated original-grid row generation',
                first_valid_integer_incumbent_time=0.,first_new_valid_integer_incumbent_time=firstnew,first_native_valid_integer_time=firstnative,
                starting_valid_UB=self.initial_ub,starting_valid_LB=self.initial_lb,starting_gap=gap(self.initial_ub,self.initial_lb),
                final_valid_UB=ub,final_valid_LB=lb,final_global_gap=gap(ub,lb),
                gap_reduction_per_wall_second=(gap(self.initial_ub,self.initial_lb)-gap(ub,lb))/duration,
                master_solves=len(iterations),row_generation_iterations=len(iterations) if rowgen else 0,
                rows_added=sum(i['added'] for i in iterations),rows_added_per_iteration=[i['added'] for i in iterations],
                initial_rows=startrows,final_rows=len(axis),full_original_reduced_rows=self.B.shape[0],full_unreduced_rows=self.A.shape[0],
                iterations=iterations,native_runtime=native,wall_runtime=duration,transport_audits=transport,
                exhaustive_final_separation=final['exhaustive_grid'],full_original_best_point_validation=final,
                P1_accepted=gap(ub,lb)<=.005 and final['PASS'],native_candidate_checks=nativepoints,
                peak_RSS=max((s['RSS'] for s in resources),default=None),min_free_RAM=min((s['free_RAM'] for s in resources),default=None),
                peak_process_commit=max((s['process_commit'] for s in resources if s['process_commit'] is not None),default=None),
                peak_system_commit=max((s['system_commit'] for s in resources if s['system_commit'] is not None),default=None),
                memory_policy='read-only telemetry; no stop/wait/kill/throttling/parameter change from resources')
            write(f'{label}_RESULT.json',result);print('ARM_RESULT',label,json.dumps({k:result[k] for k in ('final_valid_UB','final_valid_LB','final_global_gap','master_solves','rows_added','wall_runtime')}),flush=True)
            self.results.append(result)
        finally:m.dispose()
    def run(self):
        with (OUT/'M1_ROWGEN_BENCHMARK_ONCE.json').open('x',encoding='utf8') as f:
            json.dump(dict(pid=os.getpid(),created=psutil.Process().create_time(),source_commit=self.commit,maximum_comparisons=1,shared_wall_cap=600),f)
        self.begin=time.perf_counter();self.mem=PassiveMemory(self.begin);self.mem.start()
        try:
            self.arm('A_BASELINE',False)
            self.arm('B_ROWGEN',True)
        finally:self.mem.finish()
        duration=time.perf_counter()-self.begin
        a,b=self.results
        ratea=a['gap_reduction_per_wall_second'];rateb=b['gap_reduction_per_wall_second']
        rate_selected=rateb>0 and (ratea<=0 or rateb>=1.2*ratea)
        matched_strong_bound=b['final_valid_LB']>=a['final_valid_LB']+.01*abs(a['final_valid_UB']) and b['wall_runtime']<=a['wall_runtime']+2
        selected=bool((rate_selected or matched_strong_bound) and b['exhaustive_final_separation']['PASS'] and duration<=600)
        write('M1_ROWGEN_600S_MICROBENCHMARK.json',dict(arms=self.results,total_continuous_wall=duration,hard_shared_budget=600,
            within_budget=duration<=600,native_runtime=sum(r['native_runtime'] for r in self.results),source_commit=self.commit,
            historical_PR157_gap=.15043614552672033,historical_PR157_native=499.69799995422363,
            historical_PR157_not_paired_new_arm=True,arm_order=['A_BASELINE','B_ROWGEN'],parallel_solves=False,development_only=True))
        write('M1_DECOMPOSITION_SELECTION.json',dict(NEW_M1_DECOMPOSITION_SELECTED=selected,
            final_state='EXACT_ROW_GENERATION_SELECTED' if selected else 'NEW_DECOMPOSITION_REJECTED',
            scientific_equivalence_PASS=True,exhaustive_final_separation_PASS=b['exhaustive_final_separation']['PASS'],
            original_domains_retained=True,no_heuristic_acceptance=True,rate_improvement_gate=rate_selected,
            matched_strong_bound_gate=matched_strong_bound,baseline_rate=ratea,rowgen_rate=rateb,
            gap_target=.005,P1_accepted=b['P1_accepted'],production_canary=False,P2=False,B2_B3=False,compact_PR124_tested=False,
            reason='Exactness and full separation preserved; selection uses preregistered valid global gap progress, not iteration count.',
            paper_runtime='NOT_MEASURED_DEVELOPMENT_ONLY'))
        write('NATIVE_CALL_LEDGER.json',self.calls)
        for name,data in [('M1_ROWGEN_GAP_TRAJECTORY.csv',self.trajectory),('M1_ROWGEN_RESOURCE_LEDGER.csv',self.mem.data)]:
            with (OUT/name).open('w',newline='',encoding='utf8') as f:
                w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
        print('COMPARISON_COMPLETE',duration,'SELECTED',selected,flush=True)

if __name__=='__main__':
    try:Comparison().run()
    except BaseException:
        write('MICROBENCHMARK_ERROR.json',dict(traceback=traceback.format_exc()));raise
