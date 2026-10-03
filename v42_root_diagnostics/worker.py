"""One sequential heavy lane. No diagnostic result can write scientific certificates."""
import re,sys,math
from .common import *
from v42_monolithic.resources import PeakMemory

class Monitor:
    def __init__(self,label):self.label=label;self.trace=[];self.events={};self.errors=[];self.last=-10;self.notice=-60;self.peak=0.;self.first_nonroot=None;self.first_values=None
    def __call__(self,m,where):
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=float(m.cbGet(gp.GRB.Callback.RUNTIME));self.peak=max(self.peak,float(m.cbGet(gp.GRB.Callback.MAXMEMUSED)))
            if where==gp.GRB.Callback.MESSAGE:
                line=m.cbGet(gp.GRB.Callback.MSG_STRING).strip()
                if 'Loaded user MIP start with objective' in line:self.events.setdefault('Start_accepted_time',t)
                if line.startswith('Barrier statistics:'):self.events.setdefault('barrier_structure_report_time',t)
                if line.startswith('Ordering time:'):self.events.setdefault('barrier_ordering_report_time',t)
                if line.startswith('Barrier solved model'):self.events.setdefault('barrier_completion_time',t)
                if line.startswith('Crossover log'):self.events.setdefault('crossover_start_time',t)
                if line.startswith('Root relaxation:') and 'objective' in line:self.events.setdefault('root_relaxation_completion_time',t)
                if line.startswith('Solved in') and 'iterations' in line:self.events.setdefault('LP_completion_report_time',t)
                return
            sample=dict(t=t,callback=where)
            if where==gp.GRB.Callback.SIMPLEX:
                for key,field in [('iterations',gp.GRB.Callback.SPX_ITRCNT),('phase_objective',gp.GRB.Callback.SPX_OBJVAL),('primal_infeasibility',gp.GRB.Callback.SPX_PRIMINF),('dual_infeasibility',gp.GRB.Callback.SPX_DUALINF)]:sample[key]=float(m.cbGet(field))
            elif where==gp.GRB.Callback.BARRIER:
                self.events.setdefault('first_barrier_iteration_callback_time',t)
                for key,field in [('iterations',gp.GRB.Callback.BARRIER_ITRCNT),('primal_objective',gp.GRB.Callback.BARRIER_PRIMOBJ),('dual_objective',gp.GRB.Callback.BARRIER_DUALOBJ),('primal_infeasibility',gp.GRB.Callback.BARRIER_PRIMINF),('dual_infeasibility',gp.GRB.Callback.BARRIER_DUALINF)]:sample[key]=float(m.cbGet(field))
            elif where==gp.GRB.Callback.MIPNODE:
                sample['node_count']=float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))
                if sample['node_count']>0:self.events.setdefault('first_nonroot_node_callback_time',t)
                else:self.events.setdefault('first_root_node_callback_time',t)
            elif where==gp.GRB.Callback.MIP:
                sample.update(nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT)),iterations=float(m.cbGet(gp.GRB.Callback.MIP_ITRCNT)),cuts=float(m.cbGet(gp.GRB.Callback.MIP_CUTCNT)))
                if sample['nodes']>0:self.events.setdefault('processed_root_proxy_time',t)
            elif where==gp.GRB.Callback.MIPSOL:
                if self.first_values is None:
                    self.events['first_incumbent_time']=t;self.events['first_incumbent_objective']=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    self.first_values=np.array(m.cbGetSolution(m.getVars()))
                return
            else:return
            if t-self.last>=5:
                self.last=t;self.trace.append(sample);dump('LIVE_'+self.label+'.json',dict(events=self.events,trace=self.trace))
            if t-self.notice>=60:
                self.notice=t;print(self.label,sample,flush=True)
        except Exception as exc:self.errors.append(repr(exc));m.terminate()

def one(label,kind,method,seconds=600,*,mip=False,variant=None,crossover=None):
    freeze_check();assert not (OUT/(label+'.json')).exists(),'ONE_SHOT_RESULT_EXISTS'
    snapshot(label);LOCAL.mkdir(exist_ok=True);marker=LOCAL/(label+'_OPTIMIZE_STARTED.json');assert not marker.exists()
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        m=make(kind,env);initial=signature(m);scientific=signature(m,False)
        if variant:
            from .projection import variant_model
            old=m;m=variant_model(variant,old,env);old.dispose()
        before_relax=signature(m,False)
        if not mip:m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update();assert m.NumIntVars==0
        policy=dict(MIP_POLICY if mip else LP_POLICY,Method=method,TimeLimit=seconds)
        if not mip and method==2:policy.update(Crossover=0 if crossover is None else crossover,PreDual=0,BarConvTol=1e-11)
        for k,v in policy.items():m.setParam(k,v)
        effective={k:m.getParamInfo(k)[2] for k in policy};assert effective==policy
        assert signature(m,False)==before_relax,'METHOD_MODIFIED_SCIENTIFIC_MATRIX'
        if mip:
            with np.load(OLD/(kind.upper()+'_RECONSTRUCTED_START.npz')) as z:names=z['names'];values=z['values']
            assert np.array_equal(names,m.getAttr('VarName'));m.setAttr('Start',m.getVars(),values.tolist());m.update();assert np.array_equal(m.getAttr('Start'),values)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'.log'))
        monitor=Monitor(label);marker.write_text(json.dumps(dict(utc=stamp(),label=label,policy=policy)),encoding='utf8')
        started=time.perf_counter();m.optimize(monitor);wall=time.perf_counter()-started
        assert not monitor.errors,monitor.errors
        log=(OUT/(label+'.log')).read_text(encoding='utf8',errors='replace')
        pre=re.findall(r'Presolve time:\s*([\d.]+)s',log)
        result=dict(label=label,formulation=kind,method=method,diagnostic_only=True,certificate_update=False,
            NON_SCIENTIFIC_DIAGNOSTIC_ONLY=bool(variant and variant.startswith('remove_')),variant=variant,utc=stamp(),status=int(m.Status),
            terminal_optimal=m.Status==gp.GRB.OPTIMAL,objective=attr(m,'ObjVal') if m.Status==gp.GRB.OPTIMAL else None,
            raw_candidate_objective=attr(m,'ObjVal') if m.SolCount else None,raw_solver_BestBd=attr(m,'ObjBound'),solver_runtime=m.Runtime,wall_seconds=wall,
            simplex_iterations=attr(m,'IterCount'),barrier_iterations=attr(m,'BarIterCount'),work_units=attr(m,'Work'),
            presolve_seconds=float(pre[-1]) if pre else None,peak_worker_RSS_bytes=peak.peak,peak_solver_memory_GB=monitor.peak,
            settings=effective,Start_accepted=any('Loaded user MIP start with objective' in s for s in log.splitlines()) if mip else None,
            no_Start=not mip,initial_scientific_model_signature=initial,scientific_matrix_signature_before_relax=scientific,
            diagnostic_matrix_signature=before_relax,integer_variables_after_relaxation=m.NumIntVars,events=monitor.events,callback_errors=monitor.errors,
            first_branch_time=None,first_branch_observed=bool(monitor.events.get('first_nonroot_node_callback_time') is not None),
            first_branch_note='Exact branch event is not directly exposed; observed nonroot-node callback proves branching occurred and is a labeled time proxy.',
            root_processing_completion_time=None,crossover_completion_time=None,rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs,
            warnings=[s for s in log.splitlines() if 'warning' in s.lower() or 'numerical trouble' in s.lower()],
            solver_version=list(gp.gurobi.version()),log_sha256=sha(OUT/(label+'.log')),basis_available=False,Kappa=None,KappaExact=None,
            KappaExact_reason='Not requested on a 954k+ row basis: factorization cost may exceed the bounded diagnostic budget. Kappa estimate requested if a terminal optimal simplex basis exists.')
        if mip:
            from v42_exact_start.common import primary_mask
            assert result['Start_accepted'] and monitor.first_values is not None,'ACCEPTED_START_NOT_REPRODUCED_STOP'
            mask=primary_mask(names);diff=float(np.max(abs(monitor.first_values[mask]-values[mask])))
            result['accepted_Start_primary_max_difference']=diff;result['accepted_Start_objective']=monitor.events['first_incumbent_objective']
            dump(label+'.json',result)
            assert diff==0 and monitor.events['first_incumbent_objective']==UB,'START_PHYSICS_DRIFT_STOP'
        if m.SolCount:
            point=np.array(m.getAttr('X'));result['point_audit']=lp_audit(m,point)
            arrays=dict(names=np.array(m.getAttr('VarName')),values=point)
            if not mip:
                arrays.update(RC=np.array(m.getAttr('RC')),slack=np.array(m.getAttr('Slack')),LB=np.array(m.getAttr('LB')),UB=np.array(m.getAttr('UB')))
                try:
                    vb=np.array(m.getAttr('VBasis'));cb=np.array(m.getAttr('CBasis'))
                    result['basis_available']=bool(m.Status==gp.GRB.OPTIMAL);arrays.update(VBasis=vb,CBasis=cb)
                    if result['basis_available']:result['Kappa']=attr(m,'Kappa')
                except gp.GurobiError:pass
            np.savez_compressed(LOCAL/(label+'_SOLUTION.npz'),**arrays);result['solution_sha256']=sha(LOCAL/(label+'_SOLUTION.npz'))
        if not mip and result['terminal_optimal'] and not result['NON_SCIENTIFIC_DIAGNOSTIC_ONLY']:
            drift=abs(result['objective']-TARGET[kind]);result['historical_target_objective_difference']=drift
            dump(label+'.json',result)
            assert drift<=1e-8,'EXACT_EQUIVALENT_OBJECTIVE_DRIFT_STOP'
        dump(label+'.json',result);table(label+'_TRAJECTORY.csv',monitor.trace or [dict(t=m.Runtime,callback='no_callback')],sorted(set().union(*(r.keys() for r in monitor.trace))) if monitor.trace else ['t','callback'])
        dump(label+'_TIMELINE.json',dict(events=monitor.events,root_processing_completion_time=None,first_branch_time=None,crossover_completion_time=None,
            note='Only literal message/callback observations; unexposed events remain null. Barrier callback start follows factorization and is not the exact optimizer start.'))
        m.dispose();print('DONE',label,result['status'],result['objective'],result['solver_runtime'],flush=True)
        return result

def roots():
    results=[]
    for kind in ['original','compact']:
        for method in [0,1,2]:results.append(one(f'ROOT_LP_METHOD{method}_{kind.upper()}',kind,method))
    optimal=[r['objective'] for r in results if r['terminal_optimal']]
    delta=max(optimal)-min(optimal) if optimal else None
    gate=delta is not None and delta<=1e-8 and all(any(r['formulation']==k and r['terminal_optimal'] for r in results) for k in ['original','compact'])
    dump('ROOT_METHOD_COMPARISON.json',dict(objective_equivalence_PASS=gate,maximum_optimal_objective_difference=delta,results=results,
        inherited_certificate=dict(UB=UB,LB=LB,gap=(UB-LB)/UB),certificate_update=False))
    assert gate,'ROOT_OBJECTIVE_EQUIVALENCE_NOT_ESTABLISHED_STOP'
    return results

def confirmation():
    assert read('ROOT_METHOD_COMPARISON.json')['objective_equivalence_PASS']
    for kind in ['original','compact']:one('MIP_ROOT_METHOD2_'+kind.upper()+'_300S',kind,2,300,mip=True)

def additional():
    roots=[read(f'ROOT_LP_METHOD{method}_{kind.upper()}.json') for kind in ['original','compact'] for method in [0,1]]
    if not any(r['basis_available'] for r in roots):one('BASIS_ACQUISITION_ORIGINAL','original',2,600,crossover=1)
    else:dump('BASIS_ACQUISITION_ORIGINAL.json',dict(status='NOT_RUN',reason='At least one terminal optimal M0/M1 basis already available'))
    one('ROW_SCALED_METHOD1_DIAGNOSTIC','original',1,300,variant='row_scaled')
    proof=read('AUXILIARY_ELIMINATION_PROOF.json')
    if proof['solver_prototype_PASS']:
        one('AUX_REFERENCE_METHOD1_300S','original',1,300)
        one('AUX_ELIMINATED_METHOD1_300S','original',1,300,variant='aux_eliminated')
        one('AUX_ELIMINATED_METHOD2_600S','original',2,600,variant='aux_eliminated')
    else:dump('AUX_ELIMINATION_DIAGNOSTIC.json',dict(status='NOT_RUN',reason='Exact numeric prototype proof failed; no approximate substitution authorized'))

def isolation():
    # Full response-helper elimination cannot establish complete attribution
    # when its flattened coefficients are not exactly representable.
    uncertain=not read('AUXILIARY_ELIMINATION_PROOF.json')['complete_flattened_binary64_transport_PASS']
    if uncertain:
        one('ISOLATION_FULL_REFERENCE_120S','original',1,120)
        for label,variant in [('VOLTAGE_LOWER','remove_voltage'),('LINE_THERMAL_FACE','remove_line'),('CORRECTION_BINDING','remove_bindings'),('SOC_DYNAMICS','remove_SOC')]:
            one('NON_SCIENTIFIC_REMOVE_'+label+'_120S','original',1,120,variant=variant)
    dump('ROW_FAMILY_ISOLATION_ACTIVATION.json',dict(executed=uncertain,
        reason='Full response-helper projection not numerically transportable exactly; partial injection projection cannot settle full block attribution.' if uncertain else 'Complete projection available; removal copies not required',
        physics_invalid_results_can_never_update_certificate=True,one_source_family_removed_per_copy=True))

if __name__=='__main__':{'roots':roots,'confirmation':confirmation,'additional':additional,'isolation':isolation}[sys.argv[1]]()
