"""Import every native variable value, without clipping or scientific repair."""
import shutil
import gurobipy as gp
from .common import *

def run():
    assert not (OUT/'MIP_START_IMPORT_AUDIT.json').exists()
    if (OUT/'MIP_START_EXACT.npz').exists():
        from .finalize_prepare import run as finish_preserved
        finish_preserved();return
    assert read(PRIOR/'BEST_VALIDATED_M1_PLAN_RECEIPT.json')['PASS']
    authority=PRIOR/'BEST_VALIDATED_M1_PLAN.json.gz'
    assert sha(authority)==read(PRIOR/'BEST_VALIDATED_M1_PLAN_RECEIPT.json')['plan_sha256']
    plan=json.loads(gzip.decompress(authority.read_bytes()));axis=load_axis();names=axis['names']
    assert len(set(names))==len(names)
    missing=[str(n) for n in names if n not in plan['values']];assert not missing,missing[:10]
    values=exact_values(names,plan['values'])
    with np.load(PRIOR/'P_FIXED_ROUTE_SOLUTION.npz',allow_pickle=False) as z:
        assert np.array_equal(z['names'],names) and np.array_equal(z['values'],values)
    binary=axis['original_types']=='B';fractionality=float(np.max(abs(values[binary]-np.rint(values[binary]))));assert fractionality<=TOL
    bound=max(0.,float((axis['lower']-values).max()),float((values-axis['upper']).max()));assert bound<=TOL
    np.savez_compressed(OUT/'MIP_START_EXACT.npz',names=names,values=values)
    modelpath=LOCAL/'F3.mps'
    if not modelpath.exists():
        with modelpath.open('wb') as f:f.write(gzip.decompress((PRIOR/'F3_MODEL.mps.gz').read_bytes()))
    assert sha(modelpath)==read(PRIOR/'F3_TEMPLATE_RECEIPT.json')['sha256']
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(modelpath),env=env)
    assert m.getAttr('VarName')==list(names) and np.array_equal(m.getAttr('VType'),axis['original_types'])
    check=matrix_validation(m,values);assert check['PASS']
    _,_,_,_,initial,_,_=inputs();families={}
    for u in sorted(initial):
        families[u]={f:sum(str(n).startswith(f+'['+u+',') for n in names) for f in ['arc','charge_mode','Pch','Pdis','Q','SOC']}
        assert families[u]['charge_mode']==96 and families[u]['SOC']==97
    c=np.asarray(m.getAttr('Obj'));objective=float(c@values+m.ObjCon)
    assert abs(objective-START_UB)<=OBJ_TOL and np.count_nonzero(c)==1 and c[list(names).index('rho_max')]==1
    from v42_forensic.forensic import control,faces
    from v42_bootstrap.grid import coefficients
    bundle,anchor,_,_,_,_,_=inputs();_,coef=coefficients(bundle);loads=[];v=dict(zip(map(str,names),map(float,values)))
    for t,co in enumerate(coef):
        ff=faces(co,control(co,v,anchor,sorted(initial),t))[0];mask=np.asarray([not n.lower().startswith('transformer.') for n in co.branch_names])
        loads.append(dict(time=t,rho=float(ff[mask].max())))
    rho=max(r['rho'] for r in loads);assert abs(rho-objective)<=OBJ_TOL
    table('MIP_START_RECOMPUTED_P1.csv',loads)
    validation=original_validation(names,values);assert validation['valid_new_UB']
    dump('MIP_START_PHYSICAL_VALIDATION.json',dict(PASS=True,original_binary_max_fractionality=fractionality,physical=validation['physical'],mode_PCS_connectivity=validation['extra'],initial_SOC_PASS=validation['initial_SOC_PASS'],matrix=check,no_repair=True))
    dump('MIP_START_GRID_VALIDATION.json',dict(PASS=True,grid=validation['robust_grid'],objective=objective,independently_recomputed_P1=rho,full96=True,robust_voltage=[.955,1.045],anchor_unchanged=True,no_repair=True))
    # Rebuild the actual native constructor without optimization and compare exact matrix/domain.
    from v42_forensic.common import base
    b=base();A=m.getA();rhs=np.asarray(m.getAttr('RHS'));sense=m.getAttr('Sense');row_names=m.getAttr('ConstrName')
    def compare(native,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        native.setObjective(objectives[0][1]);native.update()
        # Inherited fingerprint also binds the retained Start attribute.
        retained=data[2]['values'].copy();map_bindings(bindings,retained)
        native.setAttr('Start',[retained[n] for n in native.getAttr('VarName')]);native.update()
        observed=b.stats(native);assert observed==b.EXPECTED,(observed,b.EXPECTED)
        a=native.getA();assert np.array_equal(a.indices,A.indices) and np.array_equal(a.indptr,A.indptr) and np.array_equal(a.data,A.data)
        assert native.getAttr('VarName')==list(names) and native.getAttr('ConstrName')==list(axis['rownames'])
        assert np.array_equal(native.getAttr('RHS'),rhs) and native.getAttr('Sense')==sense
        assert np.array_equal(native.getAttr('VType'),axis['original_types']) and np.array_equal(native.getAttr('LB'),axis['lower']) and np.array_equal(native.getAttr('UB'),axis['upper'])
        native.setAttr('Start',list(values));native.update();assert matrix_validation(native,values)['PASS']
        return None,dict(optimize_calls=0)
    b.build(compare)
    np.savez_compressed(OUT/'MPS_ROW_ALIAS_AXIS.npz',native_names=axis['rownames'],mps_names=np.asarray(row_names))
    dump('MPS_ROW_ALIAS_VALIDATION.json',dict(PASS=True,rows=len(row_names),renamed_rows=int(np.sum(axis['rownames']!=np.asarray(row_names))),
        matrix_sparsity_exact=True,coefficient_difference=0.,RHS_difference=0.,row_senses_exact=True,optimize_calls=0,
        axis_sha256=sha(OUT/'MPS_ROW_ALIAS_AXIS.npz')))
    extra=set(plan['values'])-set(map(str,names))
    dump('MIP_START_IMPORT_AUDIT.json',dict(PASS=True,BASE_HEAD=BASE,source_plan_sha256=sha(authority),source_solution_sha256=sha(PRIOR/'P_FIXED_ROUTE_SOLUTION.npz'),
        exact_start_sha256=sha(OUT/'MIP_START_EXACT.npz'),model_sha256=sha(modelpath),columns=len(names),binary_count=int(binary.sum()),families=families,
        missing_native_names=0,unique_native_axis=True,source_solution_values_bitwise_equal=True,excluded_supplemental_plan_keys=len(extra),
        supplemental_keys_policy='Full native axis only; inherited serialized supplemental/unreachable keys are not extra native variables.',
        binary_max_fractionality=fractionality,bound_max_violation=bound,objective=objective,recomputed_P1=rho,
        original_native_constructor_exact_matrix_domain=True,default_F3_fingerprint='0x9cfd10ec',native_build_optimize_calls=0,
        matrix=check,terminal_SOC_equalities_retained=4,original_route_domain_complete=True,all_auxiliary_values_included=True,clipping=False,repair=False))
    m.dispose();env.dispose();print('EXACT MIP START IMPORT PASS',objective,flush=True)
if __name__=='__main__':run()
