"""User-revised global-bound proof policy; inherited F3 physics untouched."""
import argparse,gzip,threading
from time import perf_counter
import gurobipy as gp
import psutil
from .context import *
from .proof_telemetry import Telemetry,parse,gap,number
from .proof_context import check_proof_sources as check_sources
from v42_m1_sparse.grid import compressed_grid,map_bindings,evaluate
from v42_native.solver import assert_milp
from v42_two.contract import mess_groups,passes,P1_EPS,COMPONENT_EPS,integer_certificate
def run(label,degenmoves=-1):
    assert (label,degenmoves) in [('PROOF_AUTO',-1),('PROOF_DG0',0),('M1_PROOF',-1),('M1_PROOF',0)]
    check_sources()
    cutpasses=-1;heuristics=0
    if label=='M1_PROOF':
        policy=read(OUT/'SOLVER_POLICY_SELECTION.json');assert policy['frozen'] and policy['production_authorized'] and policy['DegenMoves']==degenmoves
    if label=='PROOF_DG0':assert read(OUT/'PROOF_DEGEN_DIAGNOSTIC_AUTHORIZATION.json')['authorized']
    folder=LOCAL/label;folder.mkdir(exist_ok=True)
    assert not (folder/'STARTED.json').exists(),'NO_RETRY:'+label
    atomic(folder/'STARTED.json',dict(label=label,CutPasses='AUTO',Heuristics=0,MIPFocus=3,DegenMoves=degenmoves))
    bundle,anchor,prior,sites,initial,routes,battery=inputs()
    values=prior['values'].copy();bindings=[];handles=[];cost=[];receipt={};sample_rows=[]
    budget=OptimizeOnlyBudget();budget.seconds=1800 if label=='M1_PROOF' else 600;budget.spent=0.
    process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event();active={}
    def sampler():
        while not stop.wait(5):
            peak[0]=max(peak[0],process.memory_info().rss)
            if active.get('start') is None:continue
            elapsed=perf_counter()-active['start'];t=active['telemetry'];state=t.latest.copy()
            observed=state.pop('seconds',None)
            r=clean(dict(label=label,component=active['component'],component_seconds=elapsed,optimize_seconds=active['spent']+elapsed,phase=t.phase,RSS_bytes=process.memory_info().rss,observation_seconds=observed,observation_age_seconds=elapsed-observed if observed is not None else None,**state))
            sample_rows.append(r);atomic(folder/'PROGRESS.json',dict(r,events=t.events.copy(),first_non_root_node_seconds=t.first_non_root))
    thread=threading.Thread(target=sampler,daemon=True);thread.start()
    def builder(m,p,q):
        levels,ctrl=compressed_grid(m,bundle,anchor,p,q,'M1-F3',bindings,cost);handles.extend(ctrl);return levels
    def optimizer(m,legacy,deadline,*args,**kwargs):
        m.update();map_bindings(bindings,values);stats=assert_milp(m)
        expected=read(OUT/'M1_F3_REBUILD_RECEIPT.json');assert expected['MIP_start']['PASS']
        assert (stats['binary'],stats['continuous'],stats['linear_constraints'],stats['nonzeros'])==tuple(expected['stats'][k] for k in ['binary','continuous','rows','nonzeros'])
        m.setObjective(legacy[0][1]);m.update();assert m.Fingerprint==expected['fingerprint']
        names=m.getAttr('VarName');m.setAttr('Start',[values[n] for n in names]);m.update()
        m.Params.Method=2;m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005;m.Params.CutPasses=cutpasses
        m.Params.Heuristics=0;m.Params.MIPFocus=3;m.Params.DegenMoves=degenmoves
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(folder/'GUROBI.log')
        assert m.Params.NodeLimit>=1e90,'NODE_LIMIT_MUST_REMAIN_UNSET'
        settings=dict(Method=m.Params.Method,Threads=m.Params.Threads,Seed=m.Params.Seed,MIPGap=m.Params.MIPGap,CutPasses=m.Params.CutPasses,Heuristics=m.Params.Heuristics,DegenMoves=m.Params.DegenMoves,Cuts=m.Params.Cuts,MIPFocus=m.Params.MIPFocus,Presolve=m.Params.Presolve,NumericFocus=m.Params.NumericFocus,NodeLimit=None,TimeLimit=budget.seconds,GPU=False,optimize_only=True)
        m.write(str(folder/'NONDEFAULT_PARAMS.prm'))
        chosen=passes(mess_groups(legacy)) if label=='M1_PROOF' else [('MAX_LINE_LOADING','rho',legacy[0][1])]
        records=[];best=None;observations=[]
        for group,component,obj in chosen:
            if deadline.remaining<=0:break
            m.setObjective(obj);m.Params.TimeLimit=deadline.remaining;m.update()
            t=Telemetry();first=[None];errors=[];begin=perf_counter()
            active.update(start=begin,spent=deadline.spent,component=component,telemetry=t)
            def callback(model,where):
                now=perf_counter()-begin
                try:
                    if where==gp.GRB.Callback.MESSAGE:t.message(now,model.cbGet(gp.GRB.Callback.MSG_STRING))
                    elif where==gp.GRB.Callback.PRESOLVE:t.events.setdefault('presolve_start_seconds',now);t.phase='PRESOLVE'
                    elif where==gp.GRB.Callback.BARRIER:
                        t.events.setdefault('root_barrier_start_seconds',now);t.phase='BARRIER'
                    elif where==gp.GRB.Callback.MIPSOL:
                        if first[0] is None:first[0]=now
                        t.observe(now,'MIPSOL',model.cbGet(gp.GRB.Callback.MIPSOL_OBJBST),model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND),model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT))
                    elif where==gp.GRB.Callback.MIP:
                        t.observe(now,'MIP',model.cbGet(gp.GRB.Callback.MIP_OBJBST),model.cbGet(gp.GRB.Callback.MIP_OBJBND),model.cbGet(gp.GRB.Callback.MIP_NODCNT),model.cbGet(gp.GRB.Callback.MIP_ITRCNT),model.cbGet(gp.GRB.Callback.MIP_CUTCNT))
                    elif where==gp.GRB.Callback.MIPNODE:
                        n=model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
                        raw=model.cbGetNodeRel(m.getVarByName('rho_max')) if n==0 and t.raw_root is None and model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)==gp.GRB.OPTIMAL else None
                        t.node(now,n,model.cbGet(gp.GRB.Callback.MIPNODE_OBJBST),model.cbGet(gp.GRB.Callback.MIPNODE_OBJBND),raw)
                except Exception as error:
                    errors.append(repr(error));model.terminate()
            m.optimize(callback);wall=perf_counter()-begin;deadline.spent+=wall;active['start']=None
            assert not errors,errors
            ub=float(m.ObjVal) if m.SolCount else None;lb=number(m.ObjBound);g=gap(ub,lb)
            t.observe(wall,'FINAL',ub,lb,m.NodeCount,m.IterCount)
            record=clean(dict(group=group,component=component,status=m.Status,incumbent=ub,bound=lb,absolute_gap=abs(ub-lb) if ub is not None and lb is not None else None,relative_gap=g,quality_PASS=g is not None and g<=.005+1e-12,solve_wall_seconds=wall,native_runtime_seconds=m.Runtime,work=m.Work,nodes=m.NodeCount,iterations=m.IterCount,barrier_iterations=m.BarIterCount,first_incumbent_seconds=first[0],telemetry=t.summary(wall),**parse(''.join(t.messages))))
            records.append(record);observations.extend(dict(r,component=component) for r in t.observations)
            atomic(folder/'PARTIAL_RESULT.json',dict(passes=records,total_optimize_seconds=deadline.spent))
            if m.SolCount:
                vv=dict(zip(names,m.getAttr('X')));best=dict(values=vv,objectives=[evaluate(e,vv) for _,_,e in chosen],scientific_objective_count=2)
                atomic(folder/'INCUMBENT.json',best)
            if not record['quality_PASS'] or label!='M1_PROOF':break
            if component=='movement_count':record['integer_exact_certificate']=integer_certificate(ub,lb)
            if len(records)<len(chosen):m.addConstr(obj<=ub+(P1_EPS if component=='rho' else COMPONENT_EPS),name='M1_lock_'+component)
        complete=label=='M1_PROOF' and len(records)==3 and all(r['quality_PASS'] for r in records)
        receipt.update(label=label,passes=records,settings=settings,complete=complete,total_optimize_seconds=deadline.spent,model_stats=stats,model_fingerprint=expected['fingerprint'],formulation='M1-F3',formulation_changed=False,A1_optimize_calls=0)
        atomic(folder/'CALLBACK_OBSERVATIONS.json',observations)
        return best,receipt
    import v42_native.mess as native
    old=native.optimize;native.optimize=optimizer
    try:best,r=native.solve('M1',budget,sites,initial,routes,battery,96,builder,incumbent=prior)
    finally:native.optimize=old;stop.set();thread.join(2)
    receipt.update(r,peak_RSS_bytes=peak[0]);assert best is not None,'VALID_START_DID_NOT_SURVIVE'
    atomic(folder/'FINAL_PLAN.json',best)
    controls=controls_from_plan(best,anchor);atomic(folder/'CONTROLS.json',controls)
    physical=validate(best,sites,routes,battery,96);extra=supplemental_physical(best,sites,battery);grid=grid_report(bundle,controls,best['values']['rho_max'])
    physical.update(extra,initial_SOC_PASS=all(abs(best['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial))
    physical['PASS']=physical['PASS'] and extra['charge_mode_and_connection_PASS'] and physical['initial_SOC_PASS']
    anchor_pass=all(controls[t][i]==anchor['controls'][t][i] for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
    assert best['domain_sha256']==prior['domain_sha256']
    receipt.update(physical_PASS=physical['PASS'],robust_grid_PASS=grid['PASS'],anchor_identity_PASS=anchor_pass,accepted=receipt['complete'] and physical['PASS'] and grid['PASS'] and anchor_pass)
    dump(label+'_PHYSICAL_VALIDATION.json',physical);dump(label+'_ROBUST_VOLTAGE_REPORT.json',grid)
    prefix='M1_PRODUCTION' if label=='M1_PROOF' else label
    dump(prefix+'_OPTIMIZATION.json',receipt)
    for component in receipt['passes']:
        sample_rows.append(dict(label=label,component=component['component'],component_seconds=component['solve_wall_seconds'],phase='FINAL',incumbent=component['incumbent'],bound=component['bound'],nodes=component['nodes'],relative_gap=component['relative_gap'],observation_age_seconds=0))
    keys=sorted(set().union(*(r.keys() for r in sample_rows)));table(prefix+'_PROGRESS.csv',[{k:r.get(k) for k in keys} for r in sample_rows])
    raw=(folder/'GUROBI.log').read_bytes();(OUT/(prefix+'_SOLVER.raw.gz')).write_bytes(gzip.compress(raw,mtime=0));(OUT/(prefix+'_SOLVER.display.txt')).write_text('\n'.join(s.rstrip() for s in raw.decode('utf8').splitlines())+'\n',encoding='utf8')
    receipt['native_log_sha256']=sha(folder/'GUROBI.log');dump(prefix+'_OPTIMIZATION.json',receipt)
    atomic(folder/'FINISHED.json',receipt);check_sources();print('FINISHED',label,receipt['passes'][0],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('label',choices=['PROOF_AUTO','PROOF_DG0','M1_PROOF']);p.add_argument('--degenmoves',type=int,choices=[-1,0],default=-1);a=p.parse_args();run(a.label,a.degenmoves)
