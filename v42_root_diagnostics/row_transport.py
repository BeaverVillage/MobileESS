"""Proposed exact row-scale transport guard, no solve; original cache preserved."""
from .common import *
from .projection import save,from_cache

def guarded_exponents(A,threshold=1e-13):
    counts=np.diff(A.indptr);mx=np.asarray(abs(A).max(axis=1).toarray()).ravel()
    exponents=np.zeros(A.shape[0],dtype=np.int32);exponents[counts>0]=np.frexp(mx[counts>0])[1]
    entryrows=np.repeat(np.arange(A.shape[0]),counts)
    # The only safeguard is representability by the solver input API. No
    # performance measurements influence the scaling factors.
    while True:
        values=np.ldexp(A.data,-exponents[entryrows]);bad=abs(values)<threshold
        if not bad.any():break
        exponents[np.unique(entryrows[bad])]-=1
    return exponents

def prepare_proposal():
    A=sparse.load_npz(LOCAL/'ORIGINAL_A.npz')
    with np.load(LOCAL/'ORIGINAL_DATA.npz') as z:d={k:z[k] for k in z.files}
    with np.load(LOCAL/'ROW_SCALING.npz') as z:initial=z['exponents']
    e=guarded_exponents(A);rows=np.repeat(np.arange(A.shape[0]),np.diff(A.indptr));S=A.copy();S.data=np.ldexp(A.data,-e[rows]);rhs=np.ldexp(d['rhs'],-e)
    assert np.array_equal(np.ldexp(S.data,e[rows]),A.data) and np.array_equal(np.ldexp(rhs,e),d['rhs'])
    assert (abs(S.data)>=1e-13).all() and np.isfinite(S.data).all()
    save('ROW_SCALED_TRANSPORT_SAFE',S,dict(d,rhs=rhs));np.savez_compressed(LOCAL/'ROW_SCALING_TRANSPORT_SAFE.npz',exponents=e)
    dump('ROW_SCALING_TRANSPORT_SAFE_PROPOSAL.json',dict(utc=stamp(),status='PROPOSED_NOT_OPTIMIZED',registered_formula_preserved=True,
        solver_input_threshold=1e-13,guard='Starting at the preregistered exponent, decrement only the exponent of rows whose scaled coefficient would be below the solver API retention threshold. Repeat until every original nonzero entry survives. Factors depend solely on frozen input coefficients and documented input transport, never observed solver performance.',
        exact_positive_binary_scalars=True,all_coefficient_and_RHS_binary_roundtrips_PASS=True,nonzero_coefficients_removed=0,
        senses_bounds_types_objective_unchanged=True,modified_scaling_rows=int((initial!=e).sum()),minimum_scaled_coefficient=float(abs(S.data).min()),
        pre_original_Method1_optimize=True,prototype_optimize_calls=0,original_failed_transport_cache_unchanged=True,
        original_proof_sha256=sha(OUT/'EXACT_ROW_SCALING_PROOF.json'),source_sha256=sha(ROOT/'v42_root_diagnostics/row_transport.py'),
        cache_files={str(LOCAL/f):sha(LOCAL/f) for f in ['ROW_SCALED_TRANSPORT_SAFE_A.npz','ROW_SCALED_TRANSPORT_SAFE_DATA.npz','ROW_SCALING_TRANSPORT_SAFE.npz']},
        required_acceptance_gate='Construct full guarded GP model and verify A/RHS/bounds/sense/types/objective exactly before optimize; then same Method1/Threads4/tolerances/300s.',
        preregistration_change='Only deterministic row-scaling transport guard; all arm ordering, budgets, solver tolerances, hypothesis rules and certificate quarantine unchanged.'))

def validate_approved():
    proposal=read('ROW_SCALING_TRANSPORT_SAFE_PROPOSAL.json');assert all(sha(Path(p))==s for p,s in proposal['cache_files'].items())
    with gp.Env(params={'OutputFlag':0}) as env:
        m=from_cache('ROW_SCALED_TRANSPORT_SAFE',env)
        with np.load(LOCAL/'ROW_SCALED_TRANSPORT_SAFE_DATA.npz') as z:d={k:z[k] for k in z.files}
        for attr,key in [('RHS','rhs'),('Sense','sense'),('LB','lower'),('UB','upper'),('VType','types'),('Obj','objective'),('VarName','names')]:assert np.array_equal(m.getAttr(attr),d[key])
        assert m.ObjCon==float(d['objcon']) and m.ModelSense==gp.GRB.MINIMIZE
        signature_value=signature(m);shape=[m.NumConstrs,m.NumVars,m.NumNZs];m.dispose()
    dump('ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json',dict(PASS=True,explicit_user_approval=True,approval_text='Transport guard 승인 후 진단 계속',utc=stamp(),
        all_GP_coefficients_RHS_bounds_senses_types_objective_and_names_exact=True,coefficients_deleted=0,solver_prototype_OPTIMIZE_calls=0,
        cache_files=proposal['cache_files'],gurobi_scientific_signature=signature_value,shape=shape,
        preserved_initial_proof_sha256=sha(OUT/'EXACT_ROW_SCALING_PROOF.json'),preserved_initial_cache_freeze_sha256=sha(OUT/'PROTOTYPE_CACHE_FREEZE.json'),
        exact_positive_scaling_and_inverse_binary_roundtrip_PASS=True,formula=proposal['guard'],modified_scaling_rows=proposal['modified_scaling_rows'],
        minimum_scaled_coefficient=proposal['minimum_scaled_coefficient'],certificate_update=False))

if __name__=='__main__':prepare_proposal()
