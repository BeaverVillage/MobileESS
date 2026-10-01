"""Finish preserved preflight using exact positional MPS row aliases."""
import gurobipy as gp
from .common import *

def run():
    assert not (OUT/'MIP_START_IMPORT_AUDIT.json').exists()
    addendum=read(OUT/'SCOPE_CORRECTION_ADDENDUM.json')
    assert sha(OUT/'PREREGISTRATION.json')==addendum['original_preregistration_sha256']
    for r in addendum['existing_prepare_files_preserved']:assert sha(OUT/r['path'])==r['sha256']
    axis=load_axis();names,values=load_start();assert np.array_equal(names,axis['names'])
    planpath=PRIOR/'BEST_VALIDATED_M1_PLAN.json.gz';plan=json.loads(gzip.decompress(planpath.read_bytes()))
    assert sha(planpath)==read(PRIOR/'BEST_VALIDATED_M1_PLAN_RECEIPT.json')['plan_sha256']
    assert np.array_equal(values,exact_values(names,plan['values']))
    with np.load(PRIOR/'P_FIXED_ROUTE_SOLUTION.npz',allow_pickle=False) as z:assert np.array_equal(z['values'],values) and np.array_equal(z['names'],names)
    assert sha(LOCAL/'F3.mps')==read(PRIOR/'F3_TEMPLATE_RECEIPT.json')['sha256']
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'F3.mps'),env=env)
    assert m.getAttr('VarName')==list(names) and np.array_equal(m.getAttr('VType'),axis['original_types'])
    assert np.array_equal(m.getAttr('LB'),axis['lower']) and np.array_equal(m.getAttr('UB'),axis['upper'])
    check=matrix_validation(m,values);assert check['PASS'];objective=float(np.asarray(m.getAttr('Obj'))@values+m.ObjCon)
    assert abs(objective-START_UB)<=OBJ_TOL
    A=m.getA();rhs=np.asarray(m.getAttr('RHS'));senses=m.getAttr('Sense');mpsnames=np.asarray(m.getAttr('ConstrName'))
    assert len(mpsnames)==len(axis['rownames'])==954560
    from v42_forensic.common import base
    b=base()
    def compare(native,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        native.setObjective(objectives[0][1]);native.update();retained=data[2]['values'].copy();map_bindings(bindings,retained)
        native.setAttr('Start',[retained[n] for n in native.getAttr('VarName')]);native.update();assert b.stats(native)==b.EXPECTED
        assert native.getAttr('VarName')==list(names) and native.getAttr('ConstrName')==list(axis['rownames'])
        a=native.getA();assert np.array_equal(a.indices,A.indices) and np.array_equal(a.indptr,A.indptr) and np.array_equal(a.data,A.data)
        assert np.array_equal(native.getAttr('RHS'),rhs) and native.getAttr('Sense')==senses
        assert np.array_equal(native.getAttr('VType'),axis['original_types']) and np.array_equal(native.getAttr('LB'),axis['lower']) and np.array_equal(native.getAttr('UB'),axis['upper'])
        native.setAttr('Start',list(values));native.update();assert matrix_validation(native,values)['PASS']
        assert np.array_equal(native.getAttr('Start'),values)
        return None,dict(optimize_calls=0)
    b.build(compare)
    np.savez_compressed(OUT/'MPS_ROW_ALIAS_AXIS.npz',native_names=axis['rownames'],mps_names=mpsnames)
    dump('MPS_ROW_ALIAS_VALIDATION.json',dict(PASS=True,rows=954560,renamed_rows=int(np.sum(axis['rownames']!=mpsnames)),
        policy='Duplicate native constraint names are serialized with distinct MPS aliases. The row-index bijection preserves the entire exact ordered sparse matrix, RHS and sense; aliases do not change any physical row.',
        matrix_sparsity_exact=True,coefficient_difference=0.,RHS_difference=0.,row_senses_exact=True,native_names_match_inherited_axis=True,optimize_calls=0,
        axis_sha256=sha(OUT/'MPS_ROW_ALIAS_AXIS.npz')))
    full=original_validation(names,values);assert full['valid_new_UB']
    assert read(OUT/'MIP_START_PHYSICAL_VALIDATION.json')['PASS'] and read(OUT/'MIP_START_GRID_VALIDATION.json')['PASS']
    binary=axis['original_types']=='B';_,_,_,_,initial,_,_=inputs()
    families={u:{f:sum(str(n).startswith(f+'['+u+',') for n in names) for f in ['arc','charge_mode','Pch','Pdis','Q','SOC']} for u in sorted(initial)}
    dump('MIP_START_IMPORT_AUDIT.json',dict(PASS=True,BASE_HEAD=BASE,source_plan_sha256=sha(planpath),source_solution_sha256=sha(PRIOR/'P_FIXED_ROUTE_SOLUTION.npz'),
        exact_start_sha256=sha(OUT/'MIP_START_EXACT.npz'),model_sha256=sha(LOCAL/'F3.mps'),columns=len(names),binary_count=int(binary.sum()),families=families,
        missing_native_names=0,unique_native_axis=True,source_solution_values_bitwise_equal=True,excluded_supplemental_plan_keys=len(set(plan['values'])-set(map(str,names))),
        binary_max_fractionality=float(np.max(abs(values[binary]-np.rint(values[binary])))),objective=objective,
        recomputed_P1=read(OUT/'MIP_START_GRID_VALIDATION.json')['independently_recomputed_P1'],
        original_native_constructor_exact_matrix_domain=True,default_F3_fingerprint='0x9cfd10ec',native_build_optimize_calls=0,
        matrix=check,terminal_SOC_equalities_retained=4,original_route_domain_complete=True,all_auxiliary_values_included=True,
        row_alias_validation_sha256=sha(OUT/'MPS_ROW_ALIAS_VALIDATION.json'),preserved_prepare_files_unchanged=True,clipping=False,repair=False))
    m.dispose();env.dispose();print('EXACT MIP START + NATIVE MATRIX PASS',objective,flush=True)
if __name__=='__main__':run()
