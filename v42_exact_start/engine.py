"""Frozen Start acceptance probes and exactly one sequential paired canary."""
import math,re,time,sys
import gurobipy as gp
from scipy import sparse
from .common import *
from .resources import snapshot,PeakMemory
from .reconstruct import matrix_audit
from v42_monolithic.certificates import interval

CHECKPOINTS=[30,60,120,300,600]

class Monitor:
    def __init__(self,label,probe=False):
        self.label=label;self.probe=probe;self.messages=[];self.errors=[];self.trace=[];self.checkpoints={};self.events={}
        self.UB=None;self.LB=None;self.UB_t=None;self.LB_t=None;self.nodes=0.;self.open=None;self.iterations=0.;self.cuts=None
        self.first_incumbent=None;self.accepted_t=None;self.first_values=None;self.root_status='NOT_STARTED';self.last=-5.;self.notice=-60.;self.memory=None
    def __call__(self,m,where):
        if where==gp.GRB.Callback.POLLING:return
        try:
            t=float(m.cbGet(gp.GRB.Callback.RUNTIME));self.memory=clean_number(m.cbGet(gp.GRB.Callback.MAXMEMUSED))
            if where==gp.GRB.Callback.MESSAGE:
                line=m.cbGet(gp.GRB.Callback.MSG_STRING);self.messages.append(line)
                if 'Loaded user MIP start with objective' in line:
                    self.accepted_t=t
                    if self.probe:m.terminate()
                if 'Root relaxation:' in line and 'objective' in line:
                    self.events['root_relaxation_completion_time']=t;self.root_status='COMPLETED'
                if line.startswith('Root simplex log') or 'Root barrier log' in line:self.root_status='IN_PROGRESS'
            elif where==gp.GRB.Callback.MIPSOL:
                self.UB=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ));self.UB_t=t
                if self.first_incumbent is None:
                    self.first_incumbent=dict(time=t,objective=self.UB);self.first_values=np.array(m.cbGetSolution(m.getVars()))
            elif where==gp.GRB.Callback.MIP:
                self.UB=clean_number(m.cbGet(gp.GRB.Callback.MIP_OBJBST));self.LB=clean_number(m.cbGet(gp.GRB.Callback.MIP_OBJBND));self.UB_t=self.LB_t=t
                self.nodes=float(m.cbGet(gp.GRB.Callback.MIP_NODCNT));self.open=float(m.cbGet(gp.GRB.Callback.MIP_NODLFT));self.iterations=float(m.cbGet(gp.GRB.Callback.MIP_ITRCNT));self.cuts=float(m.cbGet(gp.GRB.Callback.MIP_CUTCNT))
                if self.nodes>0:self.events.setdefault('root_processing_completion_time_proxy',t)
            elif where==gp.GRB.Callback.MIPNODE:
                n=float(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT));status=int(m.cbGet(gp.GRB.Callback.MIPNODE_STATUS))
                if n==0 and status==gp.GRB.OPTIMAL:self.events.setdefault('root_relaxation_completion_time',t);self.root_status='COMPLETED'
                if n>0:self.events.setdefault('first_nonroot_node_callback_time',t)
            elif where==gp.GRB.Callback.SIMPLEX:
                self.iterations=float(m.cbGet(gp.GRB.Callback.SPX_ITRCNT))
                if 'root_relaxation_completion_time' not in self.events:self.root_status='IN_PROGRESS'
                self.events.setdefault('root_optimizer_first_callback_time',t)
            elif where==gp.GRB.Callback.BARRIER:
                if 'root_relaxation_completion_time' not in self.events:self.root_status='IN_PROGRESS'
                self.events.setdefault('root_optimizer_first_callback_time',t)
            if where in [gp.GRB.Callback.MIP,gp.GRB.Callback.MIPSOL,gp.GRB.Callback.SIMPLEX,gp.GRB.Callback.BARRIER,gp.GRB.Callback.MIPNODE]:
                hit=[s for s in CHECKPOINTS if t>=s and str(s) not in self.checkpoints]
                if t-self.last>=5 or hit:
                    self.last=t;r=self.sample(t,'callback',where);self.trace.append(r)
                    for s in hit:self.checkpoints[str(s)]=dict(r,requested_timestamp=s)
                    dump('LIVE_'+self.label+'.json',dict(trace=self.trace,checkpoints=self.checkpoints,events=self.events))
                if t-self.notice>=60:
                    self.notice=t;print(self.label,round(t,2),'solver_UB',self.UB,'raw_BestBd',self.LB,'nodes',self.nodes,'root',self.root_status,flush=True)
        except Exception as e:self.errors.append(repr(e));m.terminate()
    def sample(self,t,source,where=None):
        rawgap=None if self.UB is None or self.LB is None else max(0.,self.UB-self.LB)/abs(self.UB)
        return dict(t=float(t),source=source,callback_where=where,Incumbent_UB=self.UB,BestBd=self.LB,Gap=rawgap,Nodes=self.nodes,Open_nodes=self.open,
            Root_relaxation_status=self.root_status,root_relaxation_completion_time=self.events.get('root_relaxation_completion_time'),
            root_processing_completion_time=None,root_processing_completion_time_proxy=self.events.get('root_processing_completion_time_proxy'),
            first_branch_time=None,first_nonroot_node_callback_time=self.events.get('first_nonroot_node_callback_time'),
            first_incumbent_time=None if self.first_incumbent is None else self.first_incumbent['time'],cuts_count=self.cuts,simplex_iterations=self.iterations,
            bound_observed_at=self.LB_t,incumbent_observed_at=self.UB_t)

def validate_solution(kind,names,point,m):
    matrix=matrix_audit(m,point)
    with np.load(OLD_CACHE/'AXIS_START.npz') as z:original_names=z['original_names']
    inverse=sparse.load_npz(OLD_CACHE/'INVERSE_T.npz')@point if kind=='compact' else point
    from v42_certificate.common import original_validation
    physics=original_validation(original_names,inverse)
    # Audit actual solver incumbents independently; raw objective alone is not a UB.
    valid=bool(matrix['PASS'] and physics['valid_new_UB'])
    return dict(PASS=valid,matrix=matrix,physical=physics,validated_UB=physics['objective'] if valid else None)

def one(kind,probe):
    label=('START_ACCEPTANCE_' if probe else 'CANARY_')+kind.upper()+('' if probe else '_600S')
    assert not (OUT/(label+'.json')).exists(),'ONE_SHOT_RESULT_EXISTS'
    solver_freeze_check();assert read('RECONSTRUCTED_START_AUDIT.json')['PASS']
    resource=snapshot(label);limit=read('PREREGISTRATION.json')['Start_acceptance_seconds_max'] if probe else 600
    marker=LOCAL/(label+'_OPTIMIZE_STARTED.json');assert not marker.exists(),'ONE_SHOT_OPTIMIZE_MARKER_EXISTS'
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        before=time.perf_counter();m=model(kind,env);build=time.perf_counter()-before
        names,values=start(kind);assert np.array_equal(m.getAttr('VarName'),names)
        for k,v in SETTINGS.items():m.setParam(k,v)
        m.Params.TimeLimit=limit
        effective={k:m.getParamInfo(k)[2] for k in SETTINGS};assert effective==SETTINGS
        state=matrix_audit(m,values);assert state['PASS'] and state['objective']==UB
        before=time.perf_counter();m.setAttr('Start',m.getVars(),values.tolist());m.update();load_seconds=time.perf_counter()-before
        assert np.array_equal(m.getAttr('Start'),values)
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/(label+'.log'))
        monitor=Monitor(label,probe);marker.write_text(json.dumps(dict(utc=stamp(),label=label,solver=effective,TimeLimit=limit,start_sha256=sha(LOCAL/(kind.upper()+'_RECONSTRUCTED_START.npz')))),encoding='utf8')
        before=time.perf_counter();m.optimize(monitor);wall=time.perf_counter()-before
        log=(OUT/(label+'.log')).read_text(encoding='utf8',errors='replace');messages=[s for s in log.splitlines() if 'MIP start' in s]
        accepted=any('Loaded user MIP start with objective' in line for line in messages)
        presolve=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
        types=re.findall(r'Variable types: (\d+) continuous, (\d+) integer \((\d+) binary\)',log)
        result=dict(label=label,utc=stamp(),status=int(m.Status),solver_version=list(gp.gurobi.version()),settings=dict(effective,TimeLimit=limit),
            no_parameter_drift=True,Start_accepted=accepted,Start_acceptance_time=monitor.accepted_t,Start_load_time=load_seconds,
            worker_build_seconds=build,wall_seconds=wall,solver_runtime=m.Runtime,SolCount=m.SolCount,raw_solver_UB=attr(m,'ObjVal') if m.SolCount else None,
            raw_BestBd=attr(m,'ObjBound'),raw_solver_gap=attr(m,'MIPGap'),nodes=attr(m,'NodeCount'),open_nodes=monitor.open,
            simplex_iterations=attr(m,'IterCount'),first_incumbent=monitor.first_incumbent,events=monitor.events,
            root_relaxation_status=monitor.root_status,root_relaxation_completion_time=monitor.events.get('root_relaxation_completion_time'),
            root_processing_completion_time=None,root_processing_completion_time_proxy=monitor.events.get('root_processing_completion_time_proxy'),
            first_branch_time=None,first_nonroot_node_callback_time=monitor.events.get('first_nonroot_node_callback_time'),
            inaccessible_event_note='Exact first branch and post-root processing completion are not exposed by this callback; nonroot/processed-node proxies are labeled separately, never invented.',
            presolved_dimensions=None if not presolve else dict(zip(['rows','columns','nnz'],map(int,presolve[-1]))),
            presolved_types=None if not types else dict(zip(['continuous','integer','binary'],map(int,types[-1]))),
            peak_worker_RSS_bytes=peak.peak,peak_solver_memory_GB=monitor.memory,callback_errors=monitor.errors,
            warnings=[line for line in log.splitlines() if 'warning' in line.lower() or 'numerical trouble' in line.lower()],
            Start_messages=messages,log_sha256=sha(OUT/(label+'.log')),resource_receipt='RESOURCE_'+label+'.json',
            start_sha256=sha(LOCAL/(kind.upper()+'_RECONSTRUCTED_START.npz')),same_sealed_F3_strengthening=True,production=False,probe_terminated_on_loaded_Start_message=probe and monitor.accepted_t is not None)
        if m.SolCount:
            point=np.array(m.getAttr('X'));result['independent_validation']=validate_solution(kind,names,point,m)
            result['validated_UB']=result['independent_validation']['validated_UB']
            np.savez_compressed(LOCAL/(label+'_SOLUTION.npz'),names=names,values=point)
            if probe:
                mask=primary_mask(names);result['accepted_solution_primary_max_difference']=float(np.max(abs(point[mask]-values[mask])))
        else:result['validated_UB']=None
        certificate=interval(result['raw_BestBd'],result['validated_UB']);result['valid_interval']=certificate
        result['PASS']=bool(not monitor.errors and certificate['PASS'] and accepted and result['validated_UB'] is not None and (not probe or result['raw_solver_UB']==UB))
        monitor.UB=result['raw_solver_UB'];monitor.LB=result['raw_BestBd'];monitor.nodes=result['nodes'];monitor.iterations=result['simplex_iterations'];monitor.UB_t=monitor.LB_t=float(m.Runtime)
        terminal=monitor.sample(m.Runtime,'terminal');monitor.trace.append(terminal)
        for s in CHECKPOINTS:
            if str(s) not in monitor.checkpoints:
                monitor.checkpoints[str(s)]=dict(terminal,requested_timestamp=s,checkpoint_source='completed_before_checkpoint' if m.Runtime<s else 'terminal_observation_after_checkpoint')
        result['checkpoints']=monitor.checkpoints
        if not probe:table('CANARY_PROGRESS_'+kind.upper()+'.csv',monitor.trace,list(terminal))
        if monitor.first_values is not None:
            result['first_incumbent_independent_validation']=validate_solution(kind,names,monitor.first_values,m)
            np.savez_compressed(LOCAL/(label+'_FIRST_INCUMBENT.npz'),names=names,values=monitor.first_values)
        dump(label+'.json',result);m.dispose();preserve();print(label,'PASS',result['PASS'],'accepted',accepted,'obj',result['raw_solver_UB'],'status',result['status'],flush=True)
        return result

def accept():
    if not read('RECONSTRUCTED_START_AUDIT.json')['PASS']:return False
    a=one('original',True)
    if not a['PASS']:
        dump('START_ACCEPTANCE_COMPACT.json',dict(status='NOT_RUN',PASS=False,reason='Original Start failed; scientific STOP'));return False
    b=one('compact',True);return bool(a['PASS'] and b['PASS'])

def canaries():
    assert all(read('START_ACCEPTANCE_'+k+'.json')['PASS'] for k in ['ORIGINAL','COMPACT']),'START_GATE_FAILED'
    one('original',False);one('compact',False)
    return compare()

def compare():
    a=read('CANARY_ORIGINAL_600S.json');b=read('CANARY_COMPACT_600S.json')
    # Conservative absent-incumbent handling: no indexing conditionally absent fields.
    ia=interval(a.get('raw_BestBd'),a.get('validated_UB'));ib=interval(b.get('raw_BestBd'),b.get('validated_UB'))
    baseline=(UB-LB)/UB;reduction=(baseline-ib['valid_global_gap'])/baseline;gain=ib['valid_retained_LB']-LB
    pair_reduction=(ia['valid_global_gap']-ib['valid_global_gap'])/ia['valid_global_gap'] if ia['valid_global_gap']>0 else 0.
    material=reduction>=.20 or gain>=.001
    prerequisites=bool(a.get('PASS') and b.get('PASS') and ia['PASS'] and ib['PASS'])
    result=dict(PASS=prerequisites,original=ia,compact=ib,inherited_gap=baseline,relative_global_gap_reduction=reduction,valid_LB_gain=gain,
        material_gate_PASS=bool(material and prerequisites),COMPACT_M1_PRODUCTION_AUTHORIZED=bool(material and prerequisites),
        pair_relative_gap_reduction=pair_reduction,pair_valid_LB_gain=ib['valid_retained_LB']-ia['valid_retained_LB'],
        reference='Inherited valid UB/LB per explicit follow-up instruction. C0 versus C1 pair metrics reported separately.',
        production_1800='NOT_RUN',no_node_speed_gate=True,no_absolute_historical_speedup_claim=True)
    dump('CANARY_COMPARISON.json',result);return result

if __name__=='__main__':
    if sys.argv[1]=='accept':print(accept(),flush=True)
    elif sys.argv[1]=='canaries':print(canaries(),flush=True)
    elif sys.argv[1]=='compare':print(compare(),flush=True)
    else:raise ValueError(sys.argv[1])
