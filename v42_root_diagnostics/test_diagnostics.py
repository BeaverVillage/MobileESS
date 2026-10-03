"""A–R regressions: actual data identity and scientific quarantine, no solves."""
import inspect
from fractions import Fraction
import pytest
from . import common as c,analytics as a,census,projection,reporting,row_transport

@pytest.fixture(scope='module')
def original_arrays():
    A,d=a.cache_data('ORIGINAL')
    return A,d

def test_A_fingerprint_signed_unsigned_and_Start_state():
    with c.gp.Env(params={'OutputFlag':0}) as env:
        for kind in ['original','compact']:
            m=c.make(kind,env);assert int(m.Fingerprint)&0xffffffff==c.EXPECTED[kind][3]
            assert c.signature(m)==c.SCIENTIFIC_SIGNATURES[kind]
            with c.np.load(c.OLD/(kind.upper()+'_RECONSTRUCTED_START.npz')) as z:values=z['values'];names=z['names']
            assert c.np.array_equal(names,m.getAttr('VarName'));m.setAttr('Start',m.getVars(),values);m.update()
            assert int(m.Fingerprint)&0xffffffff=={'original':0x2d1e8813,'compact':0xbb01b0da}[kind]
            assert c.signature(m)==c.SCIENTIFIC_SIGNATURES[kind];m.dispose()

def test_B_Start_bytes_and_first_incumbent_physics():
    identity=c.read('SOURCE_MATRIX_IDENTITY.json')
    for kind in ['original','compact']:
        assert c.sha(c.OLD/(kind.upper()+'_RECONSTRUCTED_START.npz'))==identity['Start_unchanged_SHA'][kind]
        r=c.read('MIP_ROOT_METHOD2_'+kind.upper()+'_300S.json')
        assert r['Start_accepted'] and r['accepted_Start_primary_max_difference']==0 and r['accepted_Start_objective']==c.UB

@pytest.mark.parametrize('kind',['original','compact'])
def test_C_D_same_matrix_methods_and_optimal_objectives(kind):
    receipts=[c.read(f'ROOT_LP_METHOD{j}_{kind.upper()}.json') for j in [0,1,2]]
    for r in receipts:
        assert r['initial_scientific_model_signature']==c.SCIENTIFIC_SIGNATURES[kind]
        assert r['diagnostic_matrix_signature']==r['scientific_matrix_signature_before_relax']
        assert r['integer_variables_after_relaxation']==0 and r['no_Start']
        if r['terminal_optimal']:assert abs(r['objective']-c.TARGET[kind])<=1e-8
    assert c.read('ROOT_METHOD_COMPARISON.json')['objective_equivalence_PASS']

def test_E_classifier_deterministic_native_axis():
    for kind in ['original','compact']:
        x=c.row_families(kind);y=c.row_families(kind);assert c.np.array_equal(x,y)
        assert len(x)==c.EXPECTED[kind][0]
    assert c.family('response_line_correction[95,100]')=='response_line_correction'
    assert 'response_voltage_binding' not in c.row_families('original')

def test_F_census_full_matrix_exact_counts(original_arrays):
    A,d=original_arrays;families=c.row_families('original');records=a.csvread('MATRIX_FAMILY_CENSUS.csv')
    rec={r['family']:r for r in records if r['formulation']=='original'}
    entryfam=c.np.repeat(families,c.np.diff(A.indptr));values=abs(A.data)
    assert sum(int(r['nnz']) for r in rec.values())==A.nnz
    for f,r in rec.items():
        v=values[entryfam==f];assert int(r['nnz'])==len(v)
        for t in census.THRESHOLDS:assert int(r['count_abs_a_lt_'+str(t)])==int((v<t).sum())
        assert int(r['count_abs_a_gt_100'])==int((v>100).sum())
    for kind in ['original','compact']:
        assert sum(int(r['count']) for r in a.csvread('COEFFICIENT_MAGNITUDE_HISTOGRAM.csv') if r['formulation']==kind)==c.EXPECTED[kind][2]

def test_G_bounds_determinism_and_conservative_sample(monkeypatch,original_arrays):
    # Exact directed interval propagation through a triangular source fixture;
    # test containment independently using exact rational endpoint arithmetic.
    A=c.sparse.csr_matrix([[2.,-1.,1.,0.],[-.125,.5,0.,1.]])
    rules=[(2,0),(3,1)];rhs=c.np.array([3.,-2.])
    class Model:
        def getAttr(self,key):return {'LB':[-4.,-2.,-c.gp.GRB.INFINITY,-c.gp.GRB.INFINITY],'UB':[6.,3.,c.gp.GRB.INFINITY,c.gp.GRB.INFINITY]}[key]
    monkeypatch.setattr(census,'binding_rules',lambda *args:(rules,A,rhs,c.np.array([True,True,False,False])))
    x=census.conservative_bounds(Model(),[],[]);y=census.conservative_bounds(Model(),[],[]);assert c.np.array_equal(x.view(c.np.uint64),y.view(c.np.uint64))
    for target,row in rules:
        endpoints=[]
        for p in [-4,6]:
            for q in [-2,3]:endpoints.append(Fraction.from_float(float(rhs[row]))-Fraction.from_float(float(A[row,0]))*p-Fraction.from_float(float(A[row,1]))*q)
        assert Fraction.from_float(float(x[target]))>=max(map(abs,endpoints))
    actual=c.read('TINY_COEFFICIENT_PHYSICAL_IMPACT_BOUNDS.json');assert not actual['removal_authorization']
    for k,form in actual['formulations'].items():
        assert form['declared_or_equality_derived_finite_bound_columns']==c.EXPECTED[k][1]
        assert all(v['unbounded_rows']==0 for f in form['families'].values() for v in f.values())

def test_H_I_all_row_scaling_coefficients_RHS_and_identity(original_arrays):
    A,d=original_arrays;S,sd=a.cache_data('ROW_SCALED')
    with c.np.load(c.LOCAL/'ROW_SCALING.npz') as z:e=z['exponents']
    rows=c.np.repeat(c.np.arange(A.shape[0]),c.np.diff(A.indptr))
    assert c.np.array_equal(c.np.ldexp(S.data,e[rows]),A.data) and c.np.array_equal(c.np.ldexp(sd['rhs'],e),d['rhs'])
    for key in ['sense','lower','upper','types','objective','objcon']:assert c.np.array_equal(d[key],sd[key])
    with c.np.load(c.OLD/'ORIGINAL_RECONSTRUCTED_START.npz') as z:x=z['values']
    original=a.residual(A,d,x);scaled=a.residual(S,sd,x)
    assert original['objective']==scaled['objective']==c.UB
    assert original['max_row_violation']<=1e-9 and scaled['max_row_violation']<=1e-9

def test_guard_deterministic_solver_transport_and_no_deletion(original_arrays):
    A,d=original_arrays;e=row_transport.guarded_exponents(A);e2=row_transport.guarded_exponents(A)
    assert c.np.array_equal(e,e2)
    rows=c.np.repeat(c.np.arange(A.shape[0]),c.np.diff(A.indptr));v=c.np.ldexp(A.data,-e[rows])
    assert (abs(v)>=1e-13).all() and c.np.array_equal(c.np.ldexp(v,e[rows]),A.data)
    # Registered initial scale is genuinely untransportable. Preserve the fail.
    pre=c.read('ROW_SCALING_TRANSPORT_PRECHECK.json');assert pre['registered_scaled_entries_below_1e13']==342 and not pre['Gurobi_transport_retained_representative']

def test_J_K_M_projection_unique_and_only_defining_equalities_removed(original_arrays):
    A,d=original_arrays;P,pd=a.cache_data('AUX_ELIMINATED');E=c.sparse.load_npz(c.LOCAL/'AUX_RECONSTRUCTION_E.npz')
    with c.np.load(c.LOCAL/'AUX_MAP_AXES.npz') as z:keep=z['keep_columns'];rows=z['keep_rows'];removed=z['removed_columns']
    allrows=c.row_families('original');removedrows=c.np.setdiff1d(c.np.arange(A.shape[0]),rows)
    assert len(removed)==len(removedrows)==4608
    assert set(map(c.family,d['names'][removed]))=={'injection_P','injection_Q'}
    assert set(allrows[removedrows])=={'injection_P_binding','injection_Q_binding'}
    assert (P-(A@E)[rows]).nnz==0 and (E[keep]-c.sparse.eye(len(keep),format='csr')).nnz==0
    assert c.np.array_equal(d['objective'][keep],pd['objective']) and (d['objective'][removed]==0).all()
    assert c.np.array_equal(d['rhs'][rows],pd['rhs']) and c.np.array_equal(d['sense'][rows],pd['sense'])
    defining=A[removedrows]
    assert (defining[:,removed]-c.sparse.eye(len(removed),format='csr')).nnz==0
    assert (d['sense'][removedrows]=='=').all() and (d['rhs'][removedrows]==0).all()
    assert (defining@E).nnz==0
    with c.np.load(c.OLD/'ORIGINAL_RECONSTRUCTED_START.npz') as z:x=z['values']
    full=E@x[keep];audit=a.residual(A,d,full);assert audit['max_row_violation']<=1e-9 and audit['objective']==c.UB
    from v42_exact_start.common import primary_mask
    mask=primary_mask(d['names']);assert c.np.array_equal(full[mask].view(c.np.uint64),x[mask].view(c.np.uint64))

def test_L_terminal_aux_objective_equivalence():
    r=c.read('AUX_ELIMINATION_DIAGNOSTIC.json')
    assert r['objective_equivalence_PASS']
    for x in r['terminal_objectives']:assert abs(x-c.TARGET['original'])<=1e-8
    assert all(x['objective_mapping_difference']<=1e-12 for x in r['mappings'])

def test_N_O_P_diagnostic_quarantine_tolerances_domains():
    for p in c.OUT.glob('*.json'):
        r=c.json.loads(p.read_text(encoding='utf8'))
        if isinstance(r,dict) and r.get('label') and 'settings' in r:
            assert r['diagnostic_only'] and r['certificate_update'] is False
            assert r['settings']['FeasibilityTol']==r['settings']['OptimalityTol']==1e-8 and r['settings']['Threads']==4
            if r.get('NON_SCIENTIFIC_DIAGNOSTIC_ONLY'):assert r['variant'].startswith('remove_')
    proof=c.read('AUXILIARY_ELIMINATION_PROOF.json');assert proof['removed_physical_constraints']==proof['removed_primary_variables']==0
    assert c.read('FINAL_VERDICT.json')['certificate']==dict(UB=c.UB,LB=c.LB,gap=(c.UB-c.LB)/c.UB,unchanged=True,diagnostic_LP_objective_not_adopted=True)

def test_Q_R_no_decomposition_or_downstream():
    flags=c.read('FINAL_FLAGS.json');assert flags['Benders_calls']==flags['new_decompositions']==0
    assert not flags['M1_ACCEPTED'] and not flags['COMPACT_M1_PRODUCTION_AUTHORIZED'] and not flags['PROBLEM13_FINAL_VALIDATED']
    for k in ['PRODUCTION_1800S','P2','A2','M2','Actual','Fresh_AC']:assert flags[k]=='NOT_RUN'
    for module in [a,census,projection,row_transport,reporting]:assert '.optimize(' not in inspect.getsource(module)

def test_exact_duplicate_proportional_RHS_and_sense_coverage():
    A=c.sparse.csr_matrix([[1.,2.],[1.,2.],[2.,4.],[-1.,-2.],[2.,4.],[-1.,-2.],[0.,0.]])
    rhs=[3.,3.,6.,-3.,7.,-3.,0.];senses=['<','<','<','>','<','<','='];f=['test']*7
    r=a.duplicates_for(A,rhs,senses,f)
    assert r['counts']==dict(exact_duplicate=1,positive_proportional=1,sign_reversed_proportional=1)
    assert r['all_hash_hits_exactly_verified'] and r['redundant_rows_relative_to_first_representative']==3
    assert a.primitive([0],[.1],.2,'=')!=a.primitive([0],[.3],.6,'=') or Fraction.from_float(.1)/Fraction.from_float(.3)==Fraction.from_float(.2)/Fraction.from_float(.6)

def test_stagnation_does_not_fabricate_bounds_or_pivots():
    points=[dict(iterations=0,phase_objective=1.,primal_infeasibility=100.,dual_infeasibility=1.,t=0.),dict(iterations=6000,phase_objective=1.,primal_infeasibility=99.5,dual_infeasibility=0.,t=10.)]
    r=a.trajectory(points);assert r['longest_stagnation_interval']['seconds']==10 and r['zero_step_pivot_count'] is None and r['phase_objective_is_not_a_scientific_bound']
    points[-1]['primal_infeasibility']=90;assert a.trajectory(points)['longest_stagnation_interval'] is None
    points[-1]['iterations']=1;assert a.trajectory(points)['longest_stagnation_interval'] is None

def test_classifiers_obey_basis_and_terminal_method_gates():
    m1=dict(terminal_optimal=False);m2=dict(terminal_optimal=True,historical_target_objective_difference=0.)
    assert reporting.classify_method(m1,m2,False,False)=='STRONGLY_SUPPORTED'
    assert reporting.classify_method(m1,m2,True,False)=='CONFIRMED'
    assert reporting.classify_degeneracy({})=='INCONCLUSIVE'

def test_preserved_original_freeze_STOP_and_approved_fingerprint_receipts():
    assert c.preserve()==2536;c.freeze_check()
    assert c.read('STOP_RECEIPT.json')['phase']=='census'
    assert c.read('PREFLIGHT_STOP_RESOLUTION.json')['optimizer_calls']==0
    parent=c.read('PARENT_SOURCE_MATRIX_IDENTITY.json');assert parent['optimizer_calls']==0
    assert all(v['parent_scientific_signature']==c.SCIENTIFIC_SIGNATURES[k] for k,v in parent['results'].items())
