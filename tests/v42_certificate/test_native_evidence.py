"""Actual sealed native matrix tests, including deliberate invalid points."""
import gurobipy as gp
import numpy as np
import pytest
from v42_certificate.common import OUT,PRIOR,LOCAL,START_UB,OBJ_TOL,TOL,load_axis,load_start,matrix_validation,read,sha

@pytest.fixture(scope='module')
def native():
    assert read(OUT/'MIP_START_IMPORT_AUDIT.json')['PASS']
    # Resolve the read-only historical fixture junction before the native API,
    # which cannot open this workspace's Unicode path on Windows.
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str((LOCAL/'F3.mps').resolve()),env=env)
    names,v=load_start();axis=load_axis()
    yield m,names,v,axis
    m.dispose();env.dispose()

def test_exact_native_variable_axis_and_fidelity(native):
    m,n,v,a=native
    with np.load(PRIOR/'P_FIXED_ROUTE_SOLUTION.npz',allow_pickle=False) as z:assert np.array_equal(z['names'],n) and np.array_equal(z['values'],v)
    assert m.getAttr('VarName')==list(n) and np.array_equal(m.getAttr('VType'),a['original_types'])
    assert np.max(abs(v[a['original_types']=='B']-np.rint(v[a['original_types']=='B'])))==0
def test_original_bounds_and_entire_grid_rows(native):
    m,n,v,a=native
    assert (m.NumConstrs,m.NumVars,m.NumNZs)==(954560,316743,8282350)
    assert np.array_equal(m.getAttr('LB'),a['lower']) and np.array_equal(m.getAttr('UB'),a['upper'])
    assert matrix_validation(m,v)['PASS']
def test_original_P1_objective_and_reproduction(native):
    m,n,v,a=native;c=np.asarray(m.getAttr('Obj'))
    assert m.ModelSense==1 and np.count_nonzero(c)==1 and c[list(n).index('rho_max')]==1
    assert abs(c@v+m.ObjCon-START_UB)<=OBJ_TOL
    r=read(OUT/'MIP_START_GRID_VALIDATION.json');assert r['no_repair'] and abs(r['independently_recomputed_P1']-START_UB)<=OBJ_TOL
def test_terminal_SOC_rows_preserved_and_bad_terminal_rejected(native):
    m,n,v,a=native;rows=a['terminal_rows'];assert len(rows)==4
    assert all(m.getConstrs()[int(i)].Sense=='=' and m.getConstrs()[int(i)].RHS==760 for i in rows)
    bad=v.copy();bad[list(n).index('SOC[MESS01,96]')]+=1
    assert not matrix_validation(m,bad)['PASS']
def test_broken_route_continuity_rejected(native):
    m,n,v,a=native;i=next(i for i,k in enumerate(n) if k.startswith('arc[') and v[i]==1)
    bad=v.copy();bad[i]=0;assert not matrix_validation(m,bad)['PASS']
def test_PCS16_violation_is_detected_inside_individual_power_bounds(native):
    m,n,v,a=native;index={str(x):i for i,x in enumerate(n)}
    p=next(str(k) for k in n if str(k).startswith('Pdis['));suffix=p[5:]
    bad=v.copy();bad[index[p]]=300;bad[index['Pch['+suffix]]=0;bad[index['Q['+suffix]]=400
    resid=m.getA()@bad-np.asarray(m.getAttr('RHS'));mask=a['rownames']=='PCS16'
    assert resid[mask].max()>TOL
def test_prepare_and_preregistration_history_not_overwritten():
    add=read(OUT/'SCOPE_CORRECTION_ADDENDUM.json');assert sha(OUT/'PREREGISTRATION.json')==add['original_preregistration_sha256']
    for r in add['existing_prepare_files_preserved']:assert sha(OUT/r['path'])==sha(OUT/'prepare_before_scope_correction'/r['path'])==r['sha256']
def test_native_duplicate_row_alias_is_only_a_bijection(native):
    m,n,v,a=native
    with np.load(OUT/'MPS_ROW_ALIAS_AXIS.npz',allow_pickle=False) as z:
        assert np.array_equal(z['native_names'],a['rownames']) and list(z['mps_names'])==m.getAttr('ConstrName')
    r=read(OUT/'MPS_ROW_ALIAS_VALIDATION.json');assert r['coefficient_difference']==r['RHS_difference']==0 and r['row_senses_exact']
def test_full_96_slot_physics_and_no_Actual_repair():
    p=read(OUT/'MIP_START_PHYSICAL_VALIDATION.json');g=read(OUT/'MIP_START_GRID_VALIDATION.json')
    assert p['PASS'] and g['PASS'] and p['no_repair'] and g['no_repair'] and g['full96']
    assert g['robust_voltage']==[.955,1.045] and g['anchor_unchanged']
def test_exact_inherited_binary_subsets_without_pruning():
    r=read(OUT/'NESTING_DOMAIN_VALIDATION.json');assert r['PASS'] and r['counts']==dict(B1=67316,B2=67436,B3=85744)
    assert r['original_integer_start_feasible_in_every_subset'] and r['restored_domains_exactly_match_PR112'] and r['route_graph_no_pruning']
    with np.load(OUT/'NESTING_DOMAIN_AXIS.npz',allow_pickle=False) as z:assert np.all(~z['B1']|z['B2']) and np.all(~z['B2']|z['B3'])
