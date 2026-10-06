"""Single preregistered paired full-domain 600s development comparison."""
import os,time,json,math,threading,subprocess,traceback,gc,ctypes
from collections import Counter
import numpy as np
import psutil
import gurobipy as gp
from v42_degen.common import POLICY,ENV
from v42_degen.identity import inputs
from v42_rowgen.core import OriginalRows
from v42_rowgen.native import build,transport_audit
from v42_one_tree_bc.core import OneTree
from v42_one_tree_bc.audit import Validator
from v42_one_tree_bc.files import ROOT,OUT,write,table,sha

def gap(ub,lb):return max(0.,ub-lb)/max(abs(ub),1e-10)
def native_bound(v):
    if not math.isfinite(v) or abs(v)>=1e90:return None
    return float(np.nextafter(v-1e-8,-np.inf))
class PERF(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong)]+[(k,ctypes.c_size_t) for k in
        ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable',
         'SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[
         (k,ctypes.c_ulong) for k in ('HandleCount','ProcessCount','ThreadCount')]
class Memory:
    """Observation only. No threshold or control path."""
    def __init__(self,begin):self.begin=begin;self.arm='common';self.data=[];self.stop=threading.Event()
    def sample(self):
        p=psutil.Process().memory_info();v=psutil.virtual_memory();t=PERF();t.cb=ctypes.sizeof(t)
        ok=ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(t),t.cb)
        return dict(wall=time.perf_counter()-self.begin,arm=self.arm,RSS=p.rss,
            process_commit=getattr(p,'pagefile',None),free_RAM=v.available,
            system_commit=int(t.CommitTotal*t.PageSize) if ok else None)
    def run(self):
        while not self.stop.is_set():self.data.append(self.sample());self.stop.wait(1.)
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def finish(self):self.stop.set();self.thread.join(timeout=2);self.data.append(self.sample())

class Benchmark:
    def __init__(self):
        self.begin=time.perf_counter();os.environ.update(ENV)
        self.commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        with (OUT/'M1_ONE_TREE_BC_BENCHMARK_ONCE.json').open('x',encoding='utf8') as f:
            json.dump(dict(pid=os.getpid(),created=psutil.Process().create_time(),
                source_commit=self.commit,continuous_wall_cap=600,maximum_comparisons=1),f)
        fixture=json.loads((OUT/'M1_ONE_TREE_BC_FIXTURE_RESULTS.json').read_text())
        assert fixture['PASS'] and fixture['exhaustive_assignments']==1536
        assert fixture['fractional_MIPNODE_original_cut_test']['PASS']
        self.freeze=json.loads((OUT/'M1_ONE_TREE_BC_INPUT_FREEZE.json').read_text())
        assert all(sha(ROOT/p)==h for p,h in self.freeze['source_files'].items())
        assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip()
        self.memory=Memory(self.begin);self.memory.start()
        self.trajectory=[];self.arms=[]
        self.A,self.d,self.B,self.e,self.identity,_=inputs()
        assert self.identity==self.freeze['scientific_identity']
        self.validator=Validator(self.A,self.d)
        path=ROOT/self.freeze['seed_file'];assert sha(path)==self.freeze['seed_SHA']
        with np.load(path) as z:self.seed=z['point'].copy()
        self.seedcheck=self.validator(self.seed);assert self.seedcheck['PASS']
        self.initial_ub=self.seedcheck['objective'];self.initial_lb=self.freeze['inherited_full_domain_LB']
        write('M1_ONE_TREE_BC_EXECUTION_FREEZE.json',dict(source_commit=self.commit,
            source_files=self.freeze['source_files'],scientific_identity=self.identity,
            inherited_files_untouched=True,shared_wall_clock_origin='worker before input/hash/fixture gate validation',
            starting_original_validation=self.seedcheck))
    def point(self,label,begin,ub,lb,kind):
        self.trajectory.append(dict(arm=label,combined_wall=time.perf_counter()-self.begin,
            arm_wall=time.perf_counter()-begin,valid_UB=ub,valid_LB=lb,valid_global_gap=gap(ub,lb),kind=kind))
    def arm(self,label,challenger):
        gc.collect();begin=time.perf_counter();self.memory.arm=label
        deadline=min(begin+280,self.begin+580)
        rows=OriginalRows(self.B,self.e)
        axis=rows.axis if challenger else np.arange(self.B.shape[0])
        t=time.perf_counter();m,v=build(self.B,self.e,axis)
        buildtime=time.perf_counter()-t
        settings=dict(POLICY);settings.pop('TimeLimit')
        settings.update(PreCrush=1,LazyConstraints=int(challenger))
        for k,w in settings.items():m.setParam(k,w)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/f'{label}.log')
        transport=transport_audit(m,self.B,self.e,axis)
        variables=m.getVars();m.setAttr('Start',variables,self.seed.tolist())
        initial_sizes=dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=m.NumNZs)
        cb=OneTree(self.B,self.e,variables,self.validator,deadline-5,begin=begin) if challenger else None
        ub=self.initial_ub;lb=self.initial_lb;best=self.seed.copy();validated=0
        firstsolver=None;firstvalid=None;firstnew=None;errors=[];callbackcount=0
        last=[-1.];consumed=[0]
        self.point(label,begin,ub,lb,'initial_same_original_authorities')
        def accept(x,when,check):
            nonlocal ub,best,firstvalid,firstnew,validated
            assert check['PASS'];validated+=1
            if firstvalid is None:firstvalid=when
            objective=check['objective']
            if objective<ub-1e-8:
                ub=objective;best=x.copy()
                if firstnew is None:firstnew=when
                self.point(label,begin,ub,lb,'new_independently_validated_full_original_incumbent')
        def observe(model,where):
            nonlocal lb
            if cb:
                while consumed[0]<len(cb.valid):
                    when,obj,x,check=cb.valid[consumed[0]];accept(x,when,check);consumed[0]+=1
            now=time.perf_counter()
            if where==gp.GRB.Callback.MIP and now-last[0]>=1:
                last[0]=now;bound=native_bound(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
                if bound is not None:
                    if bound>ub+1e-8:raise ValueError('NATIVE_BOUND_EXCEEDS_VALID_UB')
                    lb=max(lb,bound)
                self.point(label,begin,ub,lb,'full_domain_native_tree_bound')
        def baseline_callback(model,where):
            nonlocal firstsolver,callbackcount
            callbackcount+=1
            try:
                observe(model,where)
                if where==gp.GRB.Callback.MIPSOL:
                    when=time.perf_counter()-begin
                    if firstsolver is None:firstsolver=when
                    x=np.asarray(model.cbGetSolution(variables));check=self.validator(x)
                    if not check['PASS']:raise ValueError('BASELINE_NATIVE_CANDIDATE_FAILED_ORIGINAL_AUDIT:'+json.dumps(check))
                    accept(x,time.perf_counter()-begin,check)
                if time.perf_counter()>=deadline-5:model.terminate()
            except BaseException:errors.append(traceback.format_exc());model.terminate()
        if cb:cb.bound_observer=observe
        cap=max(.001,deadline-time.perf_counter()-5);m.Params.TimeLimit=cap
        timer=threading.Timer(cap,m.terminate);timer.daemon=True;timer.start()
        print('FULLSCALE_START',label,'ONE_OPTIMIZE','rows',m.NumConstrs,'wall_cap',cap,flush=True)
        t=time.perf_counter()
        try:
            m.optimize(cb if cb else baseline_callback)  # ONLY full-scale native call in this arm.
            solvewall=time.perf_counter()-t
            observe(m,-1)
            if cb and cb.error:errors.append(json.dumps(cb.error,ensure_ascii=False))
            if m.Status not in (2,9,11):errors.append('NONTERMINAL_OR_INFEASIBLE_STATUS:'+str(m.Status))
            terminal=None
            if m.SolCount:
                x=np.asarray(m.getAttr('X'));terminal=self.validator(x)
                np.savez_compressed(OUT/f'{label}_RAW_NATIVE_FINAL_POINT.npz',point=x)
                if not terminal['PASS']:errors.append('FINAL_NATIVE_INCUMBENT_INVALID')
                else:accept(x,time.perf_counter()-begin,terminal)
            if not errors:
                bound=native_bound(m.ObjBound)
                if bound is not None:
                    if bound>ub+1e-8:errors.append('FINAL_NATIVE_BOUND_EXCEEDS_VALID_UB')
                    else:lb=max(lb,bound)
            if errors:lb=self.initial_lb  # Never retain native bounds from an uncertified callback tree.
            final=self.validator(best);assert final['PASS']
            np.savez_compressed(OUT/f'{label}_FINAL_VALID_POINT.npz',point=best)
            duration=time.perf_counter()-begin
            mem=[r for r in self.memory.data if r['arm']==label]
            registry=[] if cb is None else cb.registry
            if cb:
                table('M1_ONE_TREE_BC_ROW_REGISTRY.csv',registry,
                    ['original_row_id','row_name','family','callback_type','node_number','violation','first_added_wall','original_row_SHA'])
                table('M1_ONE_TREE_BC_CALLBACK_LEDGER.csv',cb.ledger,
                    ['callback_type','node_number','start_wall','end_wall','checked_rows','violations','added','new_unique_rows','lazy_resubmissions','usercut_to_lazy_promotions','ambiguous_exact_checks','valid_full_original','full_objective','maximum_upper','error'])
                assert len({r['original_row_id'] for r in registry})==len(registry)
            counts={} if cb is None else dict(cb.counts)
            result=dict(arm=label,executed=True,optimize_calls=1,one_native_tree=True,
                source_commit=self.commit,settings=dict(settings,TimeLimit=cap),
                build_wall=buildtime,initial_sizes=initial_sizes,
                deferred_rows=598465 if challenger else 0,initial_valid_UB=self.initial_ub,
                initial_valid_LB=self.initial_lb,initial_global_gap=gap(self.initial_ub,self.initial_lb),
                final_valid_UB=ub,final_valid_LB=lb,final_global_gap=gap(ub,lb),
                gap_reduction_per_wall_second=(gap(self.initial_ub,self.initial_lb)-gap(ub,lb))/duration,
                first_solver_incumbent=cb.first_solver if cb else firstsolver,
                first_native_valid_incumbent=cb.first_valid if cb else firstvalid,
                initial_valid_point_time=0.,first_new_valid_incumbent=firstnew,
                valid_candidate_checks=validated,native_status=m.Status,SolCount=m.SolCount,
                raw_native_objective=m.ObjVal if m.SolCount else None,raw_native_bound=native_bound(m.ObjBound),
                nodes=m.NodeCount,LP_iterations=m.IterCount,barrier_iterations=m.BarIterCount,work=m.Work,
                callback_count=counts.get('callback_count',callbackcount),callback_counts=counts,
                rows_by_family=dict(Counter(r['family'] for r in registry)),
                final_active_original_rows=len(axis)+len(registry),
                final_native_NumConstrs=m.NumConstrs,
                active_row_semantics='initial plus unique submitted original rows; native cut pool can manage user cuts internally, application never deletes cuts',
                MIPNODE_unique_rows=counts.get('MIPNODE_rows_added',0),
                MIPSOL_unique_rows=counts.get('MIPSOL_rows_added',0),
                lazy_resubmissions=counts.get('lazy_resubmissions',0),
                invalid_incumbents_rejected=counts.get('invalid_incumbents_rejected',0),
                native_runtime=m.Runtime,native_optimize_wall=solvewall,wall_runtime=duration,
                peak_RSS=max((r['RSS'] for r in mem),default=None),
                peak_process_commit=max((r['process_commit'] for r in mem),default=None),
                peak_system_commit=max((r['system_commit'] for r in mem if r['system_commit'] is not None),default=None),
                minimum_available_RAM=min((r['free_RAM'] for r in mem),default=None),
                transport=transport,errors=errors,scientific_certification_PASS=not errors,
                original_final_validation=final,terminal_native_validation=terminal,
                P1_accepted=bool(not errors and gap(ub,lb)<=.005),
                memory_policy='read-only; no resource-based control or parameter changes')
            name='M1_ONE_TREE_BC_CHALLENGER_600S.json' if challenger else 'M1_ONE_TREE_BC_BASELINE_600S.json'
            write(name,result);self.arms.append(result)
            self.point(label,begin,ub,lb,'terminal_independent_full_original_audit')
            print('ARM_END',label,'UB',ub,'LB',lb,'gap',gap(ub,lb),'wall',duration,'errors',errors,flush=True)
        finally:timer.cancel();m.dispose()
    def run(self):
        try:
            self.arm('A_MONOLITHIC',False)
            self.arm('B_ONE_TREE',True)
        finally:self.memory.finish()
        a,b=self.arms;duration=time.perf_counter()-self.begin
        ratea=a['gap_reduction_per_wall_second'];rateb=b['gap_reduction_per_wall_second']
        rate_gate=rateb>0 and (ratea<=0 or rateb>=1.2*ratea)
        bound_gate=rateb>0 and b['final_valid_LB']>=a['final_valid_LB']+.01*self.initial_ub and b['wall_runtime']<=a['wall_runtime']+2
        node_gate=rateb>0 and a['nodes']<=1 and b['nodes']>=10
        certified=all(r['scientific_certification_PASS'] for r in self.arms) and duration<=600
        selected=bool(certified and (rate_gate or bound_gate or node_gate))
        state='ONE_TREE_EXACT_BC_SELECTED' if selected else ('ONE_TREE_EXACT_BC_REJECTED' if certified else 'ONE_TREE_EXACT_BC_INCONCLUSIVE')
        write('M1_ONE_TREE_BC_COMPARISON.json',dict(arms=self.arms,continuous_wall=duration,
            combined_cap=600,within_budget=duration<=600,sequential=True,concurrent_solves=False,
            source_commit=self.commit,development_only=True,rate_gate=rate_gate,bound_gate=bound_gate,node_gate=node_gate))
        write('M1_ONE_TREE_BC_SELECTION.json',dict(ONE_TREE_BC_SELECTED=selected,final_state=state,
            exactness_fixture_PASS=True,scientific_certification_PASS=certified,
            invalid_incumbent_accepted=False,baseline_rate=ratea,challenger_rate=rateb,
            rate_gate=rate_gate,bound_gate=bound_gate,node_gate=node_gate,
            both_zero_progress=(ratea==0 and rateb==0),memory_only_selection=False,
            optional_second_microexperiment=False,production_canary=False,P2=False,M2=False,B2_B3=False,
            STOP=True,reason='Preregistered positive valid-gap progress gates; no success inferred from rows, RSS or rejected candidate objective.'))
        table('M1_ONE_TREE_BC_GAP_TRAJECTORY.csv',self.trajectory)
        table('M1_ONE_TREE_BC_RESOURCE_LEDGER.csv',self.memory.data)
        print('COMPARISON_COMPLETE',duration,state,flush=True)

if __name__=='__main__':
    try:Benchmark().run()
    except BaseException:
        write('M1_ONE_TREE_BC_EXECUTION_ERROR.json',dict(traceback=traceback.format_exc()));raise
