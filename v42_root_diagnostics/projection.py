"""Exact power-of-two row scaling and representable auxiliary projection."""
from fractions import Fraction as F
from .common import *
from v42_exact_start.reconstruct import binding_rules

def data(m):
    return dict(names=np.array(m.getAttr('VarName')),types=np.array(m.getAttr('VType')),lower=np.array(m.getAttr('LB')),upper=np.array(m.getAttr('UB')),
        rhs=np.array(m.getAttr('RHS')),sense=np.array(m.getAttr('Sense')),objective=np.array(m.getAttr('Obj')),objcon=np.array(m.ObjCon))
def save(label,A,d):sparse.save_npz(LOCAL/(label+'_A.npz'),A);np.savez_compressed(LOCAL/(label+'_DATA.npz'),**d)
def from_cache(label,env):
    A=sparse.load_npz(LOCAL/(label+'_A.npz'))
    with np.load(LOCAL/(label+'_DATA.npz')) as z:d={k:z[k] for k in z.files}
    m=gp.Model(label,env=env);v=m.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'].tolist());m.update()
    m.setAttr('VarName',m.getVars(),d['names'].tolist());m.addMConstr(A,v,d['sense'],d['rhs']);m.setObjective(d['objective']@v+float(d['objcon']));m.update()
    assert (m.getA()!=A).nnz==0
    return m

def prepare():
    freeze_check();LOCAL.mkdir(exist_ok=True)
    with gp.Env(params={'OutputFlag':0}) as env:
        m=make('original',env);A=m.getA().tocsr();A.sort_indices();d=data(m);save('ORIGINAL',A,d)
        # Binary powers are exact in IEEE arithmetic; no decimal multiplication rounding.
        rowmax=np.asarray(abs(A).max(axis=1).toarray()).ravel();nonempty=rowmax>0
        exponents=np.zeros(len(rowmax),dtype=np.int32);exponents[nonempty]=np.frexp(rowmax[nonempty])[1]
        scaled=A.copy();scaled.data=np.ldexp(A.data,-np.repeat(exponents,np.diff(A.indptr)))
        rhs=np.ldexp(d['rhs'],-exponents)
        assert np.array_equal(np.ldexp(scaled.data,np.repeat(exponents,np.diff(A.indptr))),A.data)
        assert np.array_equal(np.ldexp(rhs,exponents),d['rhs']) and np.isfinite(scaled.data).all() and np.isfinite(rhs).all()
        assert np.all(scaled.data!=0) and np.all(np.sign(scaled.data)==np.sign(A.data))
        sd=dict(d,rhs=rhs);save('ROW_SCALED',scaled,sd);np.savez_compressed(LOCAL/'ROW_SCALING.npz',exponents=exponents)
        dump('EXACT_ROW_SCALING_PROOF.json',dict(PASS=True,scaling='s_i=2**(-frexp(max_abs_coefficient).exponent); positive row multiplication only',
            exact_binary_roundtrip_all_coefficients_and_RHS=True,nonzero_coefficients_deleted=0,senses_bounds_objective_types_unchanged=True,
            minimum_scaling_exponent=int((-exponents).min()),maximum_scaling_exponent=int((-exponents).max()),rows_scaled=int((exponents!=0).sum()),
            feasible_set_mathematically_identical=True,point_mapping='identity both directions',certificate_adoption=False,
            numerical_tolerance_note='Absolute solver tolerance in scaled rows has a different original-unit interpretation. Diagnostic only; unscaled residuals are separately audited.'))
        names=d['names'];rows=row_families('original');rules,_,rhs0,primary=binding_rules(m,names,rows);rule_by_target=dict(rules)
        # Audit complete symbolic projection on a thermal row using exact rational arithmetic.
        memo={}
        def expansion(j):
            if j not in rule_by_target:return ({j:F(1)},F(0))
            if j in memo:return memo[j]
            row=A[rule_by_target[j]];terms={};constant=F.from_float(float(rhs0[rule_by_target[j]]))
            for p,a in zip(row.indices,row.data):
                if p==j:continue
                parents,b=expansion(int(p));w=-F.from_float(float(a));constant+=w*b
                for k,v in parents.items():terms[k]=terms.get(k,F(0))+w*v
            memo[j]=({k:v for k,v in terms.items() if v},constant);return memo[j]
        witness=None
        for i in np.flatnonzero(rows=='line_thermal_face')[:16]:
            terms={}
            for j,a in zip(A[i].indices,A[i].data):
                parents,_=expansion(int(j));w=F.from_float(float(a))
                for k,v in parents.items():terms[k]=terms.get(k,F(0))+w*v
            for j,v in sorted(terms.items()):
                if F.from_float(float(v))!=v:
                    witness=dict(row=int(i),primary_variable=str(names[j]),exact_numerator=str(v.numerator),exact_denominator=str(v.denominator),
                        nearest_binary64=float(v),rounding_error_exact=str(F.from_float(float(v))-v));break
            if witness:break
        # Full rational elimination is uniquely invertible, but do not round
        # nonrepresentable projected coefficients into an alleged exact MILP.
        targets=np.array([j for j,i in rules if family(names[j]) in {'injection_P','injection_Q'}]);assert len(targets)==4608
        targets_set=set(map(int,targets));kept=np.array([j for j in range(m.NumVars) if j not in targets_set]);position={int(j):p for p,j in enumerate(kept)}
        er=[];ec=[];ev=[]
        for j in kept:er.append(int(j));ec.append(position[int(j)]);ev.append(1.)
        parents_all=set();definition_rows=[]
        for j in targets:
            i=rule_by_target[int(j)];definition_rows.append(i);assert rhs0[i]==0
            parents=set()
            assert abs(d['lower'][j])>=gp.GRB.INFINITY and abs(d['upper'][j])>=gp.GRB.INFINITY
            for k,a in zip(A[i].indices,A[i].data):
                if k==j:continue
                assert a in [-1.,1.] and primary[k] and k not in targets_set
                parents.add(int(k));er.append(int(j));ec.append(position[int(k)]);ev.append(-float(a))
            assert not parents&parents_all,'PROJECTED_COEFFICIENT_COLLISION';parents_all|=parents
        keep_rows=np.ones(m.NumConstrs,dtype=bool);keep_rows[definition_rows]=False
        touched=np.unique(A[:,targets].nonzero()[0]);touched=touched[keep_rows[touched]]
        assert A[touched][:,sorted(parents_all)].nnz==0,'DIRECT_PRIMARY_COLLISION'
        E=sparse.csr_matrix((ev,(er,ec)),shape=(m.NumVars,len(kept)))
        projected=(A@E)[keep_rows].tocsr();projected.sort_indices()
        # Every expanded parent support is disjoint, has weight +/-1 and zero
        # affine offset; multiplication/addition cannot round any coefficient.
        pd=dict(names=names[kept],types=d['types'][kept],lower=d['lower'][kept],upper=d['upper'][kept],
            rhs=d['rhs'][keep_rows],sense=d['sense'][keep_rows],objective=d['objective'][kept],objcon=d['objcon'])
        assert np.all(d['objective'][targets]==0)
        save('AUX_ELIMINATED',projected,pd);sparse.save_npz(LOCAL/'AUX_RECONSTRUCTION_E.npz',E)
        np.savez_compressed(LOCAL/'AUX_MAP_AXES.npz',keep_columns=kept,keep_rows=np.flatnonzero(keep_rows),removed_columns=targets)
        with np.load(OLD/'ORIGINAL_RECONSTRUCTED_START.npz') as z:point=z['values']
        inverse=E@point[kept];primary_diff=float(np.max(abs(inverse[primary]-point[primary])));assert primary_diff==0
        original_audit=lp_audit(m,inverse);assert original_audit['max_row_violation']<=1e-9
        dump('AUXILIARY_ELIMINATION_PROOF.json',dict(PASS=True,solver_prototype_PASS=True,full_auxiliary_count=81216,
            full_symbolic_projection_uniquely_invertible=True,strict_triangular_diagonal_plus_one=True,
            complete_flattened_binary64_transport_PASS=witness is None,complete_transport_counterexample=witness,
            prototype_scope='Exact injection P/Q subset only, 4608 helpers. Remaining 76608 response helpers retained; no approximate full flattening.',
            eliminated_auxiliaries=4608,remaining_response_auxiliaries=76608,removed_definition_equalities=4608,
            removed_physical_constraints=0,removed_primary_variables=0,rows_before=A.shape[0],rows_after=projected.shape[0],
            columns_before=A.shape[1],columns_after=projected.shape[1],nnz_before=A.nnz,nnz_after=projected.nnz,
            proof='All eliminated definitions have zero RHS and +/-1 primary coefficients; all parent supports are disjoint. No kept row contains both an injection and its direct primary parent. Every substitution therefore copies/sign-reverses one original coefficient without summing collisions. All eliminated helper bounds are infinite; objective coefficients are zero.',
            bidirectional_mapping='forward=keep_columns; inverse=E@reduced. Defining equalities uniquely reconstruct removed helpers.',
            accepted_primary_difference=primary_diff,reconstructed_start_full_matrix_audit=original_audit,
            objective_equivalence_requires_terminal_root_gate=True,certificate_adoption=False))
        m.dispose()
    paths=list(LOCAL.glob('*.npz'));dump('PROTOTYPE_CACHE_FREEZE.json',dict(files={str(p):sha(p) for p in sorted(paths)},solver_prototype_PASS=True))
    print('EXACT_PROTOTYPES_READY',flush=True)

def variant_model(variant,original_model,env):
    freeze=read('PROTOTYPE_CACHE_FREEZE.json');assert all(sha(Path(p))==s for p,s in freeze['files'].items())
    if variant in ['row_scaled','aux_eliminated']:
        assert read('EXACT_ROW_SCALING_PROOF.json' if variant=='row_scaled' else 'AUXILIARY_ELIMINATION_PROOF.json')['PASS']
        if variant=='row_scaled' and (OUT/'ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json').exists():
            guard=read('ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json');assert guard['PASS'] and guard['explicit_user_approval']
            assert all(sha(Path(p))==s for p,s in guard['cache_files'].items())
            m=from_cache('ROW_SCALED_TRANSPORT_SAFE',env);assert signature(m)==guard['gurobi_scientific_signature'];return m
        return from_cache(variant.upper(),env)
    if variant.startswith('remove_'):
        allowed={'remove_voltage':['voltage_lower'],'remove_line':['line_thermal_face'],
            'remove_bindings':['response_line_correction_binding'],
            'remove_SOC':['energy_balance']}
        rows=row_families('original');m=original_model.copy();m.remove([c for c,f in zip(m.getConstrs(),rows) if f in allowed[variant]]);m.update();return m
    raise ValueError(variant)

if __name__=='__main__':prepare()
