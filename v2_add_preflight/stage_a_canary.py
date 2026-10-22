"""Original A-stage prepare/Phase-I/local-pricing state, new electrical IO.

Unlike a monolithic full Job Native build, r043 prepares the complete original
Job universe as independently verified local blocks and its original active
compact kernel. This module binds that unchanged path to the static IEEE8500
global block. It does not introduce grid row generation.
"""
import ast,inspect,textwrap,types,sys
from contextlib import contextmanager
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from .stage_common import *
from .stage_aidc import power_bounds,planning_function
from .stage_a_grid import PF
from .static_coefficients import CONTROLS
from .prestart_native import native_zero

class Coefficients:
    """Immutable per-slot ranking view; no all-horizon array duplication."""
    def __len__(self):return 96
    def __getitem__(self,t):
        if not 0<=t<96:raise IndexError(t)
        with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:
            J=z['line_J'];anchor=z['anchor'];baseline=z['line']
            J=np.r_[J[:12]+PF*J[12:24],np.zeros_like(J[12:24]),J[24:]]
        return SimpleNamespace(control_names=CONTROLS,current_matrix=J,anchor=anchor,
            current_constant=baseline-J.T@anchor,transformer_current_authority_sha256=digest('SourceYY'),
            coefficient_sha256=record(RUN/'coefficients'/f'{t:02d}.npz')['sha256'])

def routed_prepare(original,verify_voltage):
    tree=ast.parse(textwrap.dedent(inspect.getsource(original)))
    cls=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='StaticModel')
    cls.body.append(ast.parse('''def addMConstr(self,*args,**kw):
    result=super().addMConstr(*args,**kw)
    family=kw.get('name','matrix_block').split('[')[0]
    if family not in label_codes:
        label_codes[family]=len(row_labels);row_labels.append(family)
    row_codes.extend([label_codes[family]]*args[0].shape[0])
    return result
''').body[0])
    replaced=[]
    class VoltageAxis(ast.NodeTransformer):
        def visit_If(self,node):
            if ast.unparse(node.test)=="len(atlas['voltage_upper_rows']) != 96 * len(node_names)":
                replaced.append(node.lineno)
                return ast.Expr(ast.Call(ast.Name('_verify_IEEE8500_static_voltage',ast.Load()),
                    [ast.Name('atlas',ast.Load()),ast.Name('model',ast.Load())],[]))
            return self.generic_visit(node)
    tree=VoltageAxis().visit(tree);ast.fix_missing_locations(tree);assert len(replaced)==1
    ns=dict(original.__globals__,_verify_IEEE8500_static_voltage=verify_voltage)
    exec(compile(tree,original.__code__.co_filename,'exec'),ns)
    return ns['prepare']

@contextmanager
def scope(tag='A1',mess=None,fresh_data_cache=None,m1_result=None,fixture=False,adapter_root=None,output_root=None,grid_certificate=None):
    from v42_pr134_b1 import native as source_bind
    from v42_may_campaign_native90 import a_stage
    from v42_a_stage_canary import prepare as inherited
    from v42_native.voltage import Stage
    from .stage_aidc import power_bounds
    import v42_native.voltage as voltage
    original_bind=source_bind.bind;folder=WORK/tag if adapter_root is None else Path(adapter_root)
    folder.mkdir(parents=True,exist_ok=True);coeff=Coefficients();bundle=read(day_inputs()['files']['native']['path'])
    from shutil import copyfile
    kernel=ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv'
    destination=folder/kernel.name
    if destination.exists():assert record(destination)['sha256']==record(kernel)['sha256']
    else:copyfile(kernel,destination)
    (folder/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json').write_text(json.dumps(bundle),encoding='utf-8')
    _,power=power_bounds(bundle);stage=Stage.A1 if tag=='A1' else Stage.A2
    if mess is None:
        assert tag=='A1';mess=np.zeros((96,48))
    if tag=='A2':
        if fixture:
            from .stage_a2_fixture import unit_arrays
            unit_dispatch=unit_arrays();m1_sha=digest(mess.tolist())
        else:
            from v44.stages import require_m1
            if m1_result is None:raise PermissionError('A2_ACCEPTED_CURRENT_M1_REQUIRED')
            plan=require_m1(m1_result,'2025-05-01');m1_sha=plan['plan_sha']
            services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
            expected=np.array([[plan['P_by_site'][s][t] for s in services]+[plan['Q_by_site'][s][t] for s in services] for t in range(96)])
            assert np.array_equal(mess,expected)
            unit_dispatch={k:np.array([plan[k][u] for u in sorted(INITIAL)]).T for k in ('P_kW','Q_kvar')}
    def bind(b,inputs,output):
        assert digest(b)==digest(bundle)
        # The original binder retains finite WINDOWS, data/rack/domain and C1
        # authorities; only its electrical constructor is replaced.
        fn=types.FunctionType(original_bind.__code__,dict(original_bind.__globals__,
            original_coefficients_for_day=lambda *a:coeff),argdefs=original_bind.__defaults__)
        answer=fn(b,inputs,output)
        if fresh_data_cache is not None and not (Path(output)/'DATA.pkl').exists():
            # Reuse only this attempt's independently generated complete data,
            # never an accepted point or the historical START_WINDOW cache.
            import pickle,shutil
            from dataclasses import asdict
            cache=Path(fresh_data_cache)
            with cache.open('rb') as stream:cached=pickle.load(stream)
            bb,jobs,bounds,seconds,resources,raw=answer[0].load_native()
            assert cached[0]==bb and cached[1]==jobs and cached[2]==bounds
            assert asdict(cached[3])==asdict(resources) and cached[4]==raw
            shutil.copyfile(cache,Path(output)/'DATA.pkl')
            put(tag+'_FRESH_DATA_CACHE_REUSE.json',dict(PASS=True,source=record(cache),
                destination=record(Path(output)/'DATA.pkl'),all_jobs_and_original_windows_exact=True,
                resources_and_raw_runtime_authority_exact=True,accepted_point_loaded=False,
                original_prepare_reverifies_all_semantic_classes=True))
        import v42_boundary.model as boundary
        import v42_compact.native as compact
        f=planning_function(folder/'grid',power,mess,stage)
        def planning(m,b,k,r,**kw):return f(m,b,k,r,stage=stage)
        planning._v42_dynamic_bundle_day_routed=True
        boundary.planning_grid=compact.frozen_a1_grid=planning
        return answer
    def paths(request):
        assert request['day']=='2025-05-01' and request['arm']==('B1' if tag=='A1' else 'B3')
        inputs=Path(request['input_folder']).resolve();out=Path(request['output']).resolve()
        if not out.is_relative_to((WORK if output_root is None else Path(output_root)).resolve()):raise PermissionError('ISOLATED_STAGE_WORKSPACE_REQUIRED')
        return request['day'],inputs,out
    @contextmanager
    def physical():
        old=dict(voltage._MAPPING)
        for s in (Stage.A1,Stage.A2):voltage._MAPPING[s]=voltage.Voltage('SOURCE_YY',.95,1.05,.95**2,1.05**2)
        try:yield read(OUT/'SOURCE_YY_HARDWARE_FREEZE.json')
        finally:voltage._MAPPING.clear();voltage._MAPPING.update(old)
    def verify_voltage(atlas,model):
        assert len(atlas['node_names'])==8603 and len(model._v2_add_grid)==96
        certificate=read(OUT/(tag+'_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json') if grid_certificate is None else grid_certificate)
        assert certificate['PASS'] and len(certificate['records'])==96
        assert all(r['exact_defining_equations'] and r['independent_safety_implication_PASS'] for r in certificate['records'])
    # The original electrical certificate remains the C1 input identity. This
    # metadata read is explicitly rebound to the new physical grid sidecar.
    original_read=inherited.read;electrical=Path(bundle['electrical_certificate']['path'])
    axisfile=folder/'IEEE8500_NODES.npz';np.savez_compressed(axisfile,node_names=read(OUT/'SOURCE_YY_GRID_AXES.json')['nodes'])
    def metadata_read(p):
        value=original_read(p)
        if Path(p)==electrical:value=dict(value,outputs=dict(value['outputs'],voltage=record(axisfile)))
        return value
    prepared=routed_prepare(inherited.prepare,verify_voltage)
    prepared.__globals__.update(physical_authority=physical,all_transformer_rows=lambda f:f,read=metadata_read)
    from .stage_a_validation import scope as validation_scope
    # Supply the user's original finite source WINDOW input, rather than
    # treating r043's wider physical-start universe as customer authority.
    import v42_a_stage_domain_v2.active as active_source
    from .stage_source_windows import physical_domain as source_window_domain
    # The source export guard means zero MESS, not zero AIDC reactive load.
    export=textwrap.dedent(inspect.getsource(a_stage._planning))
    assert export.count("if not name.startswith('aidc_load_kw')")==1
    export=export.replace("if not name.startswith('aidc_load_kw')","if name.startswith('mess_')")
    assert export.count('np.zeros((96, 4))')==2
    export=export.replace('np.zeros((96, 4))','np.zeros((96, _MESS_UNITS))')
    ns=dict(a_stage._planning.__globals__,_MESS_UNITS=len(INITIAL));exec(compile(export,a_stage.__file__,'exec'),ns)
    from contextlib import ExitStack
    routes={}
    if tag=='A2':
        from v44.frozen.v43_a2 import adapter as original_a2
        def require_controls(coeff,controls):
            controls=np.asarray(controls,float)
            assert np.array_equal(controls[:,24:],mess),'A2_CURRENT_M1_DISPATCH_DRIFT'
            assert np.max(abs(controls[:,12:24]-PF*controls[:,:12]))<1e-8
        namespace=dict(a_stage.__dict__,read=metadata_read,_v43_A2_contract=original_a2.a2_contract,
            _v43_A2_bind_proof=lambda proof:dict(proof,arm='B3',stage='A2',fixed_M1_plan_sha=m1_sha),
            _v43_M1_zero=lambda:bool(np.all(mess==0.)),_v43_M1_unit_array=lambda key:unit_dispatch[key],
            _v43_require_M1_controls=require_controls)
        for name in ('_prepare','prepare','verify_case','_native','_physical','_planning','run'):
            routes[name]=original_a2.routed_function(a_stage,name,namespace,{})[0]
        namespace['_paths']=paths
    else:routes['_planning']=ns['_planning']
    source_physical=routes.get('_physical',a_stage._physical)
    def physical_with_original_windows(*args,**kwargs):
        Physical,power=source_physical(*args,**kwargs);verify=Physical.verify
        def checked(self,point):
            result=verify(self,point)
            if result.get('PASS'):
                from .prestart_acceptance import certify
                proof=certify(result['selected_jobs'],bundle,read(day_inputs()['files']['windows']['path']),
                    identity={},expected_identity={})
                result=dict(result,PASS=proof['PASS'],independent_original_finite_WINDOWS=proof)
            return result
        Physical.verify=checked;return Physical,power
    routes['_physical']=physical_with_original_windows
    if tag=='A2':namespace['_physical']=physical_with_original_windows
    with ExitStack() as stack:
        stack.enter_context(validation_scope(tag,folder/'grid'))
        for obj,key,value in [(source_bind,'bind',bind),(a_stage,'_paths',paths),(a_stage,'read',metadata_read),(inherited,'prepare',prepared)]:
            stack.enter_context(patch.object(obj,key,value))
        stack.enter_context(patch.object(active_source,'physical_domain',source_window_domain))
        for key,value in routes.items():stack.enter_context(patch.object(a_stage,key,value))
        yield a_stage

def prepare(tag='A1'):
    report_name=tag+'_ORIGINAL_P1_FULL_PREPARATION.json'
    with measured(report_name) as (report,start),native_zero() as denied:
        base=WORK/tag/'ORIGINAL_P1';folder=base;row=day_inputs();attempt=1
        while folder.exists() and any(folder.iterdir()):
            attempt+=1;folder=base.with_name(base.name+f'_ATTEMPT{attempt:02d}')
        cache=WORK/'A1/ORIGINAL_P1/STATIC/DATA/DATA.pkl'
        mess=None
        if tag=='A2':
            from .stage_a2_fixture import parameter
            mess,witness=parameter();report.update(M1_fixture=witness,production_M1_acceptance_claimed=False)
        if not read(OUT/(tag+'_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json'))['PASS']:
            raise PermissionError('VARIABLE_GRID_PROOF_REQUIRED')
        with scope(tag,mess=mess,fresh_data_cache=cache if cache.exists() else None,fixture=tag=='A2') as original:
            budget=SimpleNamespace(check=lambda:guard(start),wall=lambda:__import__('time').perf_counter()-start,native_used=0.)
            state=original.prepare(dict(day='2025-05-01',arm='B1' if tag=='A1' else 'B3',input_folder=str(Path(row['files']['native']['path']).parent),output=str(folder),_budget=budget),
                progress=lambda value:print('ORIGINAL P1',tag,value.get('phase'),value.get('classes_complete',''),flush=True))
            verification=original.verify_case(state)
        report.update(PASS=verification['PASS'],verification=verification,state=state['_campaign']['state_receipt'],
            original_PhaseI_P1_local_pricing_and_integer_control_prepared=True,denied_attempts=denied,
            new_grid_row_generation=False,fixture_does_not_claim_optimizer_gap=True,
            source=record(ROOT/'v42_may_campaign_native90/a_stage.py'))

if __name__=='__main__':prepare(sys.argv[1] if len(sys.argv)>1 else 'A1')
