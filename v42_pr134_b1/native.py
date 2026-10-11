"""Four accepted PR134 objectives over independently certified LP projection.

No starts, points, bounds or native clock from an old date are loaded. Static
May01 matrix/interface artifacts are reused by SHA, not as a partial solve.
"""
import ast,inspect,types,pickle,shutil,time,gzip
from dataclasses import replace
from array import array
from collections import Counter
import scipy.sparse as sp
import gurobipy as gp
from .common import *
from v42_a_stage_domain_v2.execution import require_action_authorized,guard_model_optimize,guarded_optimize
from v42_a_stage_domain_v2.status import initial_domain_status,close_feasibility,require_production_domain_accepted
from v42_a_stage_domain_v2.telemetry import FutureRunTelemetry

_coefficient_constructor=None

def original_coefficients_for_day(original,certificate,day):
    """Keep the immutable original constructor across repeated bindings."""
    if certificate.get('schema') == 'V42_SVR11_ELECTRICAL_CERTIFICATE_V1':
        from v42_svr11.model import load_coefficients
        return load_coefficients(certificate, day)
    global _coefficient_constructor
    if _coefficient_constructor is None:
        candidate=original.native_coefficients
        if candidate.__code__.co_freevars:raise ValueError('ORIGINAL_COEFFICIENT_CONSTRUCTOR_REQUIRED')
        _coefficient_constructor=candidate
    source=_coefficient_constructor
    return types.FunctionType(source.__code__,dict(source.__globals__,DAY=day),
        argdefs=source.__defaults__)(certificate)

def date_route(function):
    if getattr(function,'_v42_dynamic_bundle_day_routed',False):return function
    tree=ast.parse(inspect.getsource(function));changed=[]
    class Route(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value=='2025-05-01T00:00:00+10:00':
                changed.append(node.lineno)
                return ast.copy_location(ast.parse("bundle['day']+'T00:00:00+10:00'",mode='eval').body,node)
            return node
    tree=Route().visit(tree);ast.fix_missing_locations(tree)
    if len(changed)!=1:raise ValueError('DATE_ROUTING_SOURCE_SHAPE')
    ns=dict(function.__globals__);exec(compile(tree,inspect.getfile(function),'exec'),ns)
    routed=ns[function.__name__];routed._v42_dynamic_bundle_day_routed=True
    return routed

def bind(bundle,input_folder,output):
    import v42_root.common as common
    common.OUT=common.LOCAL=output
    import v42_root.data as data
    import v42_root.native as native
    import v42_boundary.model as boundary
    import v42_temporal.native as temporal
    import v42_exact.validation as validation
    import v42_may01.prepare as original
    common.OUT=data.OUT=native.OUT=output;common.LOCAL=data.LOCAL=native.LOCAL=output
    # Original accepted C1 and power implementation, constants, weather hashes.
    certificate,power,idle,swing=temporal.load_power(bundle)
    coeff=original_coefficients_for_day(original,certificate,bundle['day'])
    temporal.native_coefficients=original.native_coefficients=lambda _certificate:coeff
    boundary.load_power=lambda _bundle:(certificate,power,idle,swing)
    boundary.native_coefficients=lambda _certificate:coeff
    boundary.planning_grid=date_route(boundary.planning_grid)
    import v42_compact.native as compact
    compact.frozen_a1_grid=boundary.planning_grid
    validation.check=date_route(validation.check)
    atomic(output/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json',bundle)
    shutil.copyfile(ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv',output/'CC4_EXECUTION_LAG_KERNEL.csv')
    boundary.OLD=temporal.OLD=output
    boundary.planning_grid.__globals__['OLD']=output
    def load_native():
        windows={r['job_id']:r for r in read(input_folder/'WINDOWS.json')}
        ledger={u:dict(can_timeshift=r['can_timeshift'],TS_slots=r['latest_start']-r['reference_start']) for u,r in windows.items()}
        jobs,bounds,seconds,resources,raw=temporal.native_jobs(bundle,ledger)
        for uid in bounds:bounds[uid]=replace(bounds[uid],allowed_starts=tuple(windows[uid]['allowed_starts']))
        return bundle,jobs,bounds,seconds,resources,raw
    data.load_native=load_native
    atomic(output/'DATE_NAMESPACE_AUDIT.json',dict(PASS=True,day=bundle['day'],scientific_base=BASE,
        allowed_changes=['date timestamp constant','bundle/ledger hash and output routing','same-day source certificate/weather'],
        scientific_input_producer='v42_pr134_b1.inputs: original PR134 R0 + frozen Q50 + original known_window',
        C1_from_original_electrical_authority=True,operational_PR150_C1_override=False,coefficients_changed=False))
    return data,native,coeff,power,idle,swing

def sc_namespace(output):
    import v42_pr134_sc.common as common
    common.LOCAL=common.OUT=output
    from v42_pr134_sc import reduce,verify,materialize
    for mod in (reduce,verify,materialize):mod.LOCAL=mod.OUT=output
    return common,reduce,verify,materialize

def objective_list(levels):
    result=[]
    for n,e in levels:
        if isinstance(e,gp.Var):indices=[e.index];co=[1.];const=0.
        elif isinstance(e,gp.LinExpr):indices=[e.getVar(i).index for i in range(e.size())];co=[e.getCoeff(i) for i in range(e.size())];const=e.getConstant()
        else:indices=[];co=[];const=float(e)
        result.append(dict(name=n,indices=indices,coefficients=co,constant=const))
    return result

def build_static(bundle,input_folder,output,progress):
    from v42_pr134_sc.snapshot import capture
    from v42_two.contract import aidc_groups,passes
    data_module,native,coeff,power,idle,swing=bind(bundle,input_folder,output)
    import builtins
    def graph_report(*values,**kw):
        builtins.print(*values,**kw)
        if values and values[0]=='complete support':
            progress(dict(phase='COMPLETE_DOMAIN_GRAPHS',jobs_complete=int(values[1]),jobs_required=sum(j['planning_eligible'] and j['service_slots']>0 for j in bundle['known_population']),
                classes_complete=int(values[3]),seconds=float(values[5])))
    data_module.print=graph_report
    progress(dict(phase='CAUSAL_DATA_AND_COMPLETE_DOMAINS'))
    sc,reduce,verify,materialize=sc_namespace(output)
    primary_local=ROOT/'.pr134_sc_local'
    if bundle['day']=='2025-05-01':
        # Full original interfaces/matrices were already independently rebuilt
        # from exact PR134. Their frozen SHA is checked again before use.
        expected=read(SC_OUT/'PR134_BASE_IDENTITY.json')
        if sha(input_folder/'NATIVE_INPUT.json')!=expected['bundle']['sha256']:raise ValueError('MAY01_ACCEPTED_INPUT_SHA')
        static=['DATA.pkl','A0_MATRIX.npz','A0_ATTRIBUTES_CODED.npz','SCIENTIFIC_INTERFACES.pkl.gz']
        refs={r['path']:r for r in read(SC_OUT/'SHA256_MANIFEST.json')['files']}
        for name in static:
            p=primary_local/name
            if name=='DATA.pkl':authority=expected['original_data']
            elif name=='SCIENTIFIC_INTERFACES.pkl.gz':authority=read(SC_OUT/'SCIENTIFIC_INTERFACE_CAPTURE_AUDIT.json')['descriptor']
            elif name=='A0_MATRIX.npz':authority=expected['matrix']
            else:authority=expected['attributes']
            if sha(p)!=authority['sha256']:raise ValueError('FROZEN_STATIC_ARTIFACT_DRIFT:'+name)
            shutil.copyfile(p,output/name)
        # No ACCEPTED_POINT or candidate point/start is copied into production.
        data=data_module.prepare()
        from v42_pr134_sc import common as original_artifact
        prior=original_artifact.OUT;original_artifact.OUT=SC_OUT
        active=original_artifact.read_artifact('ACTIVE_OBJECTIVE_HIERARCHY.json')
        legacy=original_artifact.read_artifact('CURRENT_OBJECTIVE_HIERARCHY.json');original_artifact.OUT=prior
        atomic(output/'CURRENT_OBJECTIVE_HIERARCHY.json',legacy)
        a=sp.load_npz(output/'A0_MATRIX.npz');z=sc.attributes()
    else:
        data=data_module.prepare();rows=array('H');labels=[];codes={};model_class=gp.Model
        class ObservedModel(model_class):
            def addConstr(self,*args,**kw):
                import sys
                name=kw.get('name',args[1] if len(args)>1 else '');frame=sys._getframe(1)
                family=name.split('[')[0] if name else 'row_'+Path(frame.f_code.co_filename).parent.name+'_'+str(frame.f_lineno)
                if family not in codes:codes[family]=len(labels);labels.append(family)
                rows.append(codes[family]);return super().addConstr(*args,**kw)
            def optimize(self,*args,**kw):
                guard_model_optimize(self)
                raise PermissionError('STATIC_MODEL_OPTIMIZE_FORBIDDEN')
        gp.Model=ObservedModel
        from v42_integrated.contract import all_transformer_rows
        import v42_boundary.model as boundary
        old=boundary.add_grid;boundary.add_grid=all_transformer_rows(old)
        boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
        class Context:
            folder=output
            def check(self):pass
            def progress(self,value):progress(dict(value,phase='MODEL_BUILD'))
        try:m,units,levels,controls,bindings=native.build(Context(),data,'F2-CRA')
        finally:gp.Model=model_class;boundary.add_grid=old;boundary.planning_grid.__globals__['add_grid']=old
        m.setObjective(levels[0][1]);m.update();a=m.getA();names=m.getAttr('VarName')
        vf_names,vf=np.unique([n.split('[')[0] for n in names],return_inverse=True)
        z=dict(lb=np.array(m.getAttr('LB')),ub=np.array(m.getAttr('UB')),rhs=np.array(m.getAttr('RHS')),sense=np.array(m.getAttr('Sense')),
            vtype=np.array(m.getAttr('VType')),obj=np.array(m.getAttr('Obj')),vf=vf.astype(np.uint16),vf_names=vf_names,
            rf=np.asarray(rows,dtype=np.uint16),rf_names=np.array(labels))
        sp.save_npz(output/'A0_MATRIX.npz',a);np.savez_compressed(output/'A0_ATTRIBUTES_CODED.npz',**z)
        atomic(output/'CURRENT_OBJECTIVE_HIERARCHY.json',objective_list(levels))
        active=[dict(group=group,**e) for (group,_,_),e in zip(passes(aidc_groups(levels,units,data)),objective_list([(name,expr) for _,name,expr in passes(aidc_groups(levels,units,data))]))]
        capture(m,units,levels,controls,bindings,output/'SCIENTIFIC_INTERFACES.pkl.gz');m.dispose();z=sc.attributes()
    progress(dict(phase='EXACT_COMPRESSION',original_rows=a.shape[0],original_columns=a.shape[1]))
    reduce.candidate('A2SC',True)
    progress(dict(phase='INDEPENDENT_EXACT_VERIFIER'))
    verification=verify.verify('A2SC')
    if not verification['PASS']:raise ValueError('COMPRESSION_EXACTNESS_FAILED')
    mapping=sc.proof_data('A2SC')['mapping'];projected=[]
    from fractions import Fraction
    for e in active:
        terms={}
        for j,c in zip(e['indices'],e['coefficients']):
            k=int(mapping[j])
            if k>=0:terms[k]=terms.get(k,Fraction(0))+Fraction(float(c))
        if any(Fraction(float(v))!=v for v in terms.values()):raise ValueError('NONEXACT_OBJECTIVE_PROJECTION')
        projected.append(dict(e,indices=list(terms),coefficients=[float(v) for v in terms.values()]))
    atomic(output/'ACTIVE_ORIGINAL_OBJECTIVES.json',active)
    atomic(output/'ACTIVE_OBJECTIVES.json',projected)
    with gzip.open(output/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:descriptor=pickle.load(f)
    atomic(output/'BUILD_RECEIPT.json',dict(PASS=True,day=bundle['day'],original_matrix=record(output/'A0_MATRIX.npz'),
        attributes=record(output/'A0_ATTRIBUTES_CODED.npz'),compressed_matrix=record(output/'A2SC_MATRIX.npz'),proof=record(output/'A2SC_PROOF.npz'),
        original_rows=a.shape[0],original_columns=a.shape[1],original_nnz=a.nnz,compressed=read(output/'A2SC_MODEL_CENSUS.json'),
        objective_semantics=['rho','migration_count','shift_magnitude','prestart_relocation'],verification=verification,
        previous_native_runtime_loaded=0,old_start_loaded=False,optimization_calls=0))
    return data,descriptor,a,z,mapping,projected,coeff,power,idle,swing,materialize

def run_a1(bundle,input_folder,output,progress):
    require_action_authorized(bundle,'A1')
    domain_status=initial_domain_status(authority='PR134_HISTORICAL')
    from v42_integrated.contract import physical_authority
    from v42_pr134_sc.build import replay
    from v42_pr134_sc.snapshot import certify
    with physical_authority():
        data,descriptor,a,z,mapping,objectives,coeff,power,idle,swing,materialize=build_static(bundle,input_folder,output,progress)
        domain_status=initial_domain_status(hard_physical_domain_defined=data[7].get('domain_authority')=='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2',
            authority=data[7].get('domain_authority','PR134_HISTORICAL'))
        progress(dict(phase='MATERIALIZE_COMPRESSED_NATIVE'))
        m=materialize.model('A2SC',day=bundle['day']);variables=m.getVars();spent=0.;results=[];locks=[];last_point=None;selected=None;controls=None
        diagnostics=FutureRunTelemetry(m,day=bundle['day'])
        m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(output/'A1_SOLVE.log')
        for k,v in SETTINGS.items():m.setParam(k,v)
        for i,e in enumerate(objectives):
            remaining=BUDGET-spent
            if remaining<=0:raise ValueError('DATE_TIMEOUT')
            expr=gp.LinExpr(e['coefficients'],[variables[j] for j in e['indices']])+e['constant']
            m.setObjective(expr);m.Params.TimeLimit=remaining;last=[-1.];callback_errors=[]
            diagnostics.begin_objective(e['name'],group=e.get('group'),remaining_seconds=remaining)
            def callback(model,where):
                try:
                    diagnostics.callback(model,where,gp.GRB)
                    if where==gp.GRB.Callback.POLLING:return
                    elapsed=float(model.cbGet(gp.GRB.Callback.RUNTIME))
                    if elapsed-last[0]<1:return
                    last[0]=elapsed;value=dict(phase=e['name'],objective_pass=i+1,objective_passes_required=4,solver_status='OPTIMIZING',
                        cumulative_native_runtime=spent+elapsed,incumbent=None,BestBd=None,gap=None,node_count=None,report_UTC=now())
                    if where==gp.GRB.Callback.MIP:
                        ub=float(model.cbGet(gp.GRB.Callback.MIP_OBJBST));lb=float(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
                        value.update(incumbent=ub if abs(ub)<1e90 else None,BestBd=lb if abs(lb)<1e90 else None,node_count=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT)))
                        if abs(ub)<1e90 and abs(lb)<1e90 and abs(ub)>1e-12:value['gap']=abs(ub-lb)/abs(ub)
                    progress(value)
                except Exception as error:callback_errors.append(str(error))
            guarded_optimize(m,bundle,callback);spent+=m.Runtime
            diagnostics.finish_objective(m)
            def attr(name):
                try:return float(getattr(m,name))
                except (AttributeError,gp.GurobiError):return None
            result=dict(component=e['name'],status=m.Status,native_runtime=m.Runtime,cumulative_native_runtime=spent,Work=attr('Work'),
                node_count=attr('NodeCount'),objective=attr('ObjVal') if m.SolCount else None,bound=attr('ObjBound'),gap=attr('MIPGap') if m.SolCount else None,
                valid_UB=None,valid_LB=attr('ObjBound'),callback_errors=callback_errors,TimeLimit=remaining,solver=SETTINGS)
            if m.SolCount:
                raw=np.array(m.getAttr('X'));np.savez_compressed(output/f'PASS_{i+1}_RAW_POINT.npz',values=raw)
                point=np.zeros(a.shape[1]);mask=mapping>=0;point[mask]=raw[mapping[mask]]
                original=replay(a,z,point)
                try:cert,selected,controls,globals=certify(descriptor,data,point,original,coeff)
                except Exception as error:cert=dict(PASS=False,error=str(error),type=type(error).__name__)
                lock_vio=max((sum(c*point[j] for j,c in zip(lock['original_indices'],lock['original_coefficients']))+lock['constant']-lock['rhs'] for lock in locks),default=0.)
                result.update(original_rows=original,physical=cert,prior_lock_max_violation=max(0,lock_vio),raw_point=record(output/f'PASS_{i+1}_RAW_POINT.npz'))
                if original['PASS'] and cert['PASS'] and lock_vio<=1e-5:result['valid_UB']=result['objective'];last_point=point
            if result.get('valid_UB') is not None:domain_status=close_feasibility(domain_status,result['physical'])
            result['domain_status']=dict(domain_status)
            result['scientific_full_domain_optimal']=False
            results.append(result);atomic(output/f'PASS_{i+1}_RECEIPT.json',result)
            atomic(output/'A1_SOLVE_RESULT.json',dict(accepted=False,domain_status=domain_status,scientific_full_domain_optimal=False,
                future_run_diagnostics=diagnostics.receipt(),passes=results,total_runtime=spent,total_TimeLimit=BUDGET))
            if callback_errors:raise ValueError('CALLBACK_IMPLEMENTATION_FAILURE:'+str(callback_errors[0]))
            if m.Status==gp.GRB.TIME_LIMIT:raise ValueError('DATE_TIMEOUT')
            if m.Status in (gp.GRB.INFEASIBLE,gp.GRB.INF_OR_UNBD):raise ValueError('NATIVE_INFEASIBLE_NOT_INDEPENDENTLY_PROVEN')
            if m.Status!=gp.GRB.OPTIMAL:raise ValueError('NATIVE_NUMERICAL_OR_SOLVER_FAILURE:'+str(m.Status))
            if result['valid_UB'] is None:raise ValueError('NATIVE_POINT_CERTIFICATE_FAIL')
            if result['gap'] is not None and result['gap']>.005:raise ValueError('NATIVE_GAP_AUTHORITY_FAIL')
            epsilon=1e-7 if e['name']=='rho' else 1e-8;rhs=m.ObjVal+epsilon
            m.addConstr(expr<=rhs,name='single_thread_A1_lock_'+e['name']);m.update()
            # Lock uses exactly the original objective (constant included).
            original_active=read(output/'ACTIVE_ORIGINAL_OBJECTIVES.json')
            source=original_active[i]
            locks.append(dict(original_indices=source['indices'],original_coefficients=source['coefficients'],constant=source['constant'],rhs=rhs))
            atomic(output/'OBJECTIVE_LOCKS.json',locks)
        sites=sorted(bundle['capacities']);caps=np.array([bundle['capacities'][s] for s in sites]);known=np.zeros((96,len(sites)))
        for uid,o in selected.items():
            for site,start,end in o['segments']:
                for t in range(max(start,24),min(end,120)):known[t-24,sites.index(site)]+=data[1][uid].gpu
        pcc=np.array([[controls[t][coeff[t].control_names.index('aidc_load_kw['+s+']')] for s in sites] for t in range(96)])
        slopes=np.array([[power[s,t].slope for s in sites] for t in range(96)]);intercepts=np.array([[power[s,t].intercept_kw for s in sites] for t in range(96)])
        it=(pcc-intercepts)/slopes;total=(it-idle*caps)/swing;q=pcc*np.tan(np.arccos(.95))
        if np.any(total>caps+1e-5) or np.any(total<known-1e-5):raise ValueError('PLANNING_GPU_POWER_IDENTITY')
        np.savez_compressed(output/'PLANNING_PHYSICAL.npz',sites=np.array(sites),PCC_P_kw=pcc,PCC_Q_kvar=q,IT_kw=it,GPU=total,known_GPU=known)
        atomic(output/'A1_ACTIVE_DOMAIN_RESULT.json',dict(PASS=True,accepted=False,arm='B1',day=bundle['day'],selected_jobs=selected,physical=results[-1]['physical'],passes=results,
            domain_status=domain_status,scientific_full_domain_optimal=False,future_run_diagnostics=diagnostics.receipt(),
            cumulative_native_runtime=spent,all_MESS_PQ_zero=True,old_partial_start_used=False,scientific_base=BASE,compression_exactness=True))
        atomic(output/'A1_SOLVE_RESULT.json',dict(accepted=False,domain_status=domain_status,scientific_full_domain_optimal=False,
            future_run_diagnostics=diagnostics.receipt(),passes=results,total_runtime=spent,total_TimeLimit=BUDGET));m.dispose()
        # Four restricted native optima never close an omitted migration pool.
        # A later accepted proof interface is required before any plan freeze.
        require_production_domain_accepted(domain_status)
        return dict(PASS=True,accepted=True,domain_status=domain_status,folder=str(output),physical=results[-1]['physical'],passes=results)
