"""Two fresh continuous LP gates, then at most one conditional M1 MIP."""
import json,time,threading
import numpy as np
import gurobipy as gp
from scipy import sparse
from .governance import OUT,write,sha
from .a1 import LOCAL
from .contract import LP_POLICY,MIP_POLICY,DEFAULTS,physical_authority,grid_audit
from .matrix import audit
from .resources import snapshot
from .monitor import Monitor,root_gate

def finite(value):
    return float(value) if np.isfinite(value) and abs(value)<gp.GRB.INFINITY else None

def model(kind):
    identity=json.loads((OUT/'M1_MODEL_IDENTITY.json').read_text(encoding='utf8'))
    path=LOCAL/(kind.upper()+'.mps')
    assert sha(path)==identity[kind+'_MPS_sha256']
    m=gp.read(str(path));m.Params.OutputFlag=1;m.Params.LogToConsole=0
    from .matrix import arrays,column_identity
    A,d=full_arrays();B,e=arrays(m)
    if kind=='reduced':
        with np.load(LOCAL/'REDUCTION_AXES.npz') as z:keep=z['keep']
        A=A[keep];d=dict(d,rhs=d['rhs'][keep],sense=d['sense'][keep])
    transport=dict(coefficients_exact_equal=np.array_equal(A.indptr,B.indptr) and np.array_equal(A.indices,B.indices) and np.array_equal(A.data,B.data),RHS_exact_equal=np.array_equal(d['rhs'],e['rhs']),senses_equal=np.array_equal(d['sense'],e['sense']),columns_equal=column_identity(d)==column_identity(e))
    signs=dict(coefficient_bytes_equal=np.array_equal(A.data.view(np.uint64),B.data.view(np.uint64)),RHS_bytes_equal=np.array_equal(d['rhs'].view(np.uint64),e['rhs'].view(np.uint64)))
    transport['PASS']=all(transport.values());write('MPS_TRANSPORT_'+kind+'.json',transport)
    write('MPS_SIGNED_ZERO_TRANSPORT_'+kind+'.json',dict(**signs,exact_numeric_values_required=True,nonzero_rounding_allowed=False))
    if not transport['PASS']:raise ValueError('MPS_SCIENTIFIC_ROUNDTRIP_FAILED')
    return m

def full_arrays():
    identity=json.loads((OUT/'M1_MODEL_IDENTITY.json').read_text(encoding='utf8'))
    assert sha(LOCAL/'FULL_DATA.npz')==identity['data_sha256']
    assert sha(LOCAL/'FULL_A.npz')==identity['matrix_sha256']
    with np.load(LOCAL/'FULL_DATA.npz') as z:d={k:z[k] for k in z.files}
    return sparse.load_npz(LOCAL/'FULL_A.npz'),d

def lp(kind):
    marker=LOCAL/('LP_'+kind+'_STARTED.json')
    if marker.exists():raise ValueError('LP_NO_RETRY')
    write('RESOURCE_LP_'+kind+'.json',snapshot())
    m=model(kind);m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
    for key,value in LP_POLICY.items():m.setParam(key,value)
    m.Params.LogFile=str(OUT/('ROOT_LP_'+kind+'.log'))
    marker.write_text(json.dumps(LP_POLICY),encoding='utf8')
    m.optimize();result=dict(status=m.Status,objective=m.ObjVal if m.SolCount else None,runtime=m.Runtime,barrier_iterations=m.BarIterCount,settings=LP_POLICY)
    if m.SolCount:
        point=np.array(m.getAttr('X'));A,d=full_arrays();result['all_full_rows_audit']=audit(A,d,point)
        result['original_unit_grid_audit']=grid_point(point,d)
        np.savez_compressed(LOCAL/('LP_'+kind+'_POINT.npz'),values=point)
    write('ROOT_LP_'+kind+'.json',result);m.dispose();print('LP_DONE',kind,result,flush=True)
    return result

def check_lp(full,reduced):
    delta=None if full['objective'] is None or reduced['objective'] is None else abs(full['objective']-reduced['objective'])
    passed=full['status']==reduced['status']==gp.GRB.OPTIMAL and delta is not None and delta<=1e-8 and reduced['all_full_rows_audit']['PASS'] and reduced['original_unit_grid_audit']['PASS']
    result=dict(PASS=passed,objective_difference=delta,full=full,reduced=reduced,scientific_model='NEW NormalAmps + zero-margin M1',MIP_allowed=passed)
    write('ROOT_LP_EQUIVALENCE.json',result);return passed

def grid_point(point,d):
    import pickle
    from v42_bootstrap.grid import coefficients
    with (LOCAL/'DATA.pkl').open('rb') as f:bundle=pickle.load(f)[0]
    values=dict(zip(map(str,d['names']),map(float,point)))
    freeze=json.loads((OUT/'INTEGRATED_A1_FREEZE.json').read_text(encoding='utf8'));anchor=freeze['anchor']
    _,coeff=coefficients(bundle);controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for i,n in enumerate(c.control_names):
            s=n.split('[')[1][:-1]
            if n.startswith('aidc_load_kw'):row.append(anchor['controls'][t][i])
            elif n.startswith('mess_p_kw'):row.append(sum(values.get(f'Pdis[{u},{s},{t}]',0)-values.get(f'Pch[{u},{s},{t}]',0) for u in bundle['initial_MESS_sites']))
            else:row.append(sum(values.get(f'Q[{u},{s},{t}]',0) for u in bundle['initial_MESS_sites']))
        controls.append(row)
    result=grid_audit(coeff,controls,values['rho_max'])
    current_A=voltage_pu=0.
    for coefficient,x in zip(coeff,controls):
        voltage=coefficient.voltage_constant+coefficient.voltage_matrix.T@x
        voltage_pu=max(voltage_pu,float(np.maximum(.95-np.sqrt(np.maximum(voltage,0)),0).max()),float(np.maximum(np.sqrt(np.maximum(voltage,0))-1.05,0).max()))
        current=coefficient.current_constant+coefficient.current_matrix.T@x
        for k,n in enumerate(coefficient.branch_names):
            if n.lower().startswith('transformer.'):
                current_A=max(current_A,float(max(0,current[k]-1)*coefficient.current_denominators_A[k]))
    result['original_units']=dict(voltage_pu_max_violation=voltage_pu,transformer_current_A_max_violation=current_A,transformer_kVA_max_violation=result['maximum_violations']['transformer_kVA'])
    result['PASS']=result['PASS'] and max(voltage_pu,current_A,result['maximum_violations']['transformer_kVA'])<=1e-5
    return result

def physical(point,d):
    from v42_bootstrap.m1 import native_inputs
    from v42_bootstrap.grid import coefficients
    from v42_native.mess import validate
    from v42_bootstrap.attribution import supplemental_physical
    import pickle
    with (LOCAL/'DATA.pkl').open('rb') as f:bundle=pickle.load(f)[0]
    sites,initial,routes,battery,_=native_inputs(bundle)
    values=dict(zip(map(str,d['names']),map(float,point)))
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    for unit in initial:
        for k in range(len(arcs)):values.setdefault(f'arc[{unit},{k}]',0.)
        for s in sites:
            for t in range(96):
                for family in ('Pch','Pdis','Q'):values.setdefault(f'{family}[{unit},{s},{t}]',0.)
    chosen={u:[k for k in range(len(arcs)) if values[f'arc[{u},{k}]']>.5] for u in initial}
    plan=dict(values=values,chosen_arcs=chosen,initial_sites=initial,mode='MILP')
    mess=validate(plan,sites,routes,battery,96);extra=supplemental_physical(plan,sites,battery)
    freeze=json.loads((OUT/'INTEGRATED_A1_FREEZE.json').read_text(encoding='utf8'));anchor=freeze['anchor']
    _,coeff=coefficients(bundle);controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for i,n in enumerate(c.control_names):
            s=n.split('[')[1][:-1]
            if n.startswith('aidc_load_kw'):row.append(anchor['controls'][t][i])
            elif n.startswith('mess_p_kw'):row.append(sum(values[f'Pdis[{u},{s},{t}]']-values[f'Pch[{u},{s},{t}]'] for u in initial))
            else:row.append(sum(values[f'Q[{u},{s},{t}]'] for u in initial))
        controls.append(row)
    grid=grid_audit(coeff,controls,values['rho_max'])
    movement=[dict(MESS=u,source=arcs[k][0],depart=arcs[k][1],destination=arcs[k][2],connect=arcs[k][3],energy_kwh=arcs[k][-1].energy_kwh) for u in initial for k in chosen[u] if arcs[k][-1] is not None]
    result=dict(PASS=mess['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS'],MESS=mess,supplement=extra,grid=grid,movement_count=len(movement),movement_energy=sum(r['energy_kwh'] for r in movement),route=movement)
    write('M1_PHYSICAL_AUDIT.json',result);return result

def mip():
    if not json.loads((OUT/'ROOT_LP_EQUIVALENCE.json').read_text())['PASS']:raise ValueError('ROOT_LP_GATE_REQUIRED')
    marker=LOCAL/'M1_MIP_STARTED.json'
    if marker.exists():raise ValueError('ONE_MIP_ONLY')
    write('M1_RESOURCE_RECEIPT.json',snapshot());m=model('reduced')
    defaults={k:m.getParamInfo(k)[2] for k in DEFAULTS}
    assert defaults==dict(Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0,PreSparsify=-1)
    for key,value in MIP_POLICY.items():m.setParam(key,value)
    m.Params.LogFile=str(OUT/'M1_SOLVE.log')
    start=json.loads((OUT/'M1_START_COMPATIBILITY.json').read_text())
    if start['reused']:
        with np.load(LOCAL/'M1_START.npz') as z:m.setAttr('Start',m.getVars(),z['values'].tolist())
    marker.write_text(json.dumps(dict(policy=MIP_POLICY,other_defaults=defaults)),encoding='utf8')
    monitor=Monitor();begin=time.perf_counter();stop=threading.Event();checkpoint_request=[]
    def checkpoint_watch():
        while not stop.wait(.25):
            elapsed=time.perf_counter()-begin
            if elapsed>=600:
                if root_gate(monitor.times)=='FAIL':
                    checkpoint_request.append(elapsed);monitor.early_stop=True;m.terminate()
                    write('M1_ROOT_CHECKPOINT_REQUEST.json',dict(termination_requested_at_wall_seconds=elapsed,clock='monotonic wall elapsed since optimize invocation',timestamps_observed=dict(monitor.times),reason='All literal root completion / nonroot / branch observations absent at checkpoint'))
                return
    watcher=threading.Thread(target=checkpoint_watch,daemon=True);watcher.start()
    try:m.optimize(monitor)
    finally:stop.set();watcher.join(timeout=1)
    wall=time.perf_counter()-begin
    A,d=full_arrays();physical_result=None;matrix=None
    if m.SolCount:
        point=np.array(m.getAttr('X'));matrix=audit(A,d,point,integral=True,tolerance=1e-8)
        physical_result=physical(point,d)
        np.savez_compressed(LOCAL/'M1_FINAL_POINT.npz',names=d['names'],values=point)
    bound=finite(m.ObjBound);ub=finite(m.ObjVal) if m.SolCount else None
    gap=abs(ub-bound)/abs(ub) if ub is not None and bound is not None and ub!=0 else None
    gate=root_gate(monitor.times)
    result=dict(status=m.Status,status_name={gp.GRB.OPTIMAL:'OPTIMAL',gp.GRB.TIME_LIMIT:'TIME_LIMIT',gp.GRB.INTERRUPTED:'INTERRUPTED',gp.GRB.INFEASIBLE:'INFEASIBLE'}.get(m.Status,str(m.Status)),incumbent_exists=bool(m.SolCount),UB=ub,LB=bound,gap=gap,solver_gap=m.MIPGap if m.SolCount else None,node_count=m.NodeCount,explored_nodes=m.NodeCount,runtime=m.Runtime,optimize_wall_seconds=wall,first_incumbent_time=monitor.first_incumbent,first_branch_time=monitor.times['first_branch'],root_objective=monitor.root_objective,root_runtime=monitor.root_runtime,barrier_iterations=m.BarIterCount,simplex_iterations=m.IterCount,matrix_audit=matrix,physical_audit=physical_result,early_stop_at_root_checkpoint=monitor.early_stop,checkpoint_termination_request_wall_seconds=checkpoint_request[0] if checkpoint_request else None,root_path_gate=gate,settings=MIP_POLICY,other_defaults=defaults,one_MIP_call=True,old_certificate_used=False,model_identity=json.loads((OUT/'M1_MODEL_IDENTITY.json').read_text()),callback_errors=monitor.errors)
    write('M1_ROOT_PATH_TIMELINE.json',dict(timestamps=monitor.times,events=monitor.events,trace=monitor.trace,time_origin='Solver optimize elapsed seconds; model_ready=0 by definition',first_branch_exact_timestamp_exposed=False,nulls_are_unobservable_not_inferred=True,root_completion_directly_proven_by_nonroot=monitor.times['first_nonroot_node'] is not None,root_path_gate=gate,early_stop=monitor.early_stop))
    write('M1_SOLVE_RESULT.json',result)
    from .certificate import make
    write('M1_CERTIFICATE.json',make(result['model_identity'],result))
    m.dispose();print('M1_DONE',result['status_name'],ub,bound,gap,gate,flush=True);return result

def run():
    from .import_guard import selected_imports
    with selected_imports(),physical_authority():
        full=lp('full');reduced=lp('reduced')
        if check_lp(full,reduced):mip()

if __name__=='__main__':run()
