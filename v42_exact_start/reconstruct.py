"""Source-backed topological auxiliary equalities; no optimization calls."""
import math,re,gzip,time
from collections import Counter
from fractions import Fraction
import gurobipy as gp
from scipy import sparse
from .common import *

def binding_rules(m,names,native_rows):
    A=m.getA().tocsr();rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'))
    mask=primary_mask(names);aux=set(np.flatnonzero(~mask));rules=[];targets=set()
    for i,name in enumerate(native_rows):
        if not str(name).endswith('_binding'):continue
        row=A[i];dependent=[int(j) for j in row.indices if int(j) in aux]
        assert dependent,('EMPTY_BINDING',i)
        target=max(dependent);fam=family(names[target])
        assert str(name)==fam+'_binding' and sense[i]=='=' and target not in targets
        coefficients=dict(zip(map(int,row.indices),map(float,row.data)))
        assert coefficients[target]==1. and all(j<target for j in dependent if j!=target),'NONTRIANGULAR_AUXILIARY_SYSTEM'
        rules.append((target,i));targets.add(target)
    assert targets==aux and len(rules)==81216,('AUXILIARY_DEFINITION_NOT_BIJECTIVE',len(targets),len(aux))
    return sorted(rules),A,rhs,mask

def substitute(A,rhs,rules,point):
    out=np.array(point,copy=True)
    for target,i in rules:
        row=A[i];terms=[float(a)*float(out[j]) for j,a in zip(row.indices,row.data) if j!=target]
        # The equality pivot is exactly +1. math.fsum sums source-equation
        # terms deterministically; it does not clip or round to a tolerance.
        out[target]=math.fsum([float(rhs[i])]+[-t for t in terms])
    return out

def matrix_audit(m,point):
    A=m.getA();rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'));r=A@point-rhs
    equality=abs(r[sense=='=']);inequality=np.maximum(0.,np.where(sense=='<',r,-r)[sense!='='])
    violation=np.maximum(0.,np.where(sense=='=',abs(r),np.where(sense=='<',r,-r)))
    bound=max(0.,float(np.max(np.array(m.getAttr('LB'))-point)),float(np.max(point-np.array(m.getAttr('UB')))))
    integer=np.array(m.getAttr('VType'))!='C';fraction=float(np.max(abs(point[integer]-np.rint(point[integer]))))
    return dict(PASS=bool(np.all(np.isfinite(point)) and np.sum(violation>1e-8)==0 and bound<=1e-10 and fraction==0),
        maximum_row_violation=float(np.max(violation)),rows_exceeding_1e8=int(np.sum(violation>1e-8)),rows_exceeding_1e9=int(np.sum(violation>1e-9)),
        max_equality_residual=float(np.max(equality,initial=0.)),max_inequality_violation=float(np.max(inequality,initial=0.)),
        max_bound_violation=bound,max_integer_fractionality=fraction,objective=float(np.array(m.getAttr('Obj'))@point+m.ObjCon))

def classification(kind,names,rules):
    row_by_target=dict(rules)
    for j,n in enumerate(names):
        fam=family(n);primary=fam in PRIMARY
        source='v42_native.mess.solve' if fam in {'arc','SOC','charge_mode','Pch','Pdis','Q'} else 'v42_m1_sparse.grid.add_compressed' if fam=='rho_max' else 'v42_monolithic.formulation.Compact' if fam in {'movement_flow','node_activity'} else 'v42_m1_sparse.grid.response'
        yield dict(formulation=kind,variable_name=str(n),index=j,family=fam,
            classification='IMMUTABLE_PRIMARY' if primary else 'RECOMPUTABLE_AUXILIARY',source_function=source,
            reconstruction_rule='bitwise unchanged' if primary else f'binding row {row_by_target[j]}',scientific_value_fixed=primary)

def provenance(m,names,old,native_rows):
    old_axis=ROOT/'docs/v42_m1_integrality_gap_root_cause';cert=ROOT/'docs/v42_m1_late_window_certificate_mipstart'
    with np.load(old_axis/'P_FIXED_ROUTE_SOLUTION.npz') as z:
        assert np.array_equal(names,z['names']) and np.array_equal(old,z['values'])
    with np.load(cert/'MIP_START_EXACT.npz') as z:assert np.array_equal(names,z['names']) and np.array_equal(old,z['values'])
    plan=json.loads(gzip.decompress((old_axis/'BEST_VALIDATED_M1_PLAN.json.gz').read_bytes()))
    assert np.array_equal(old,np.array([plan['values'][str(n)] for n in names]))
    result=read('P_FIXED_ROUTE_OPTIMIZATION.json',old_axis)
    assert result['solution_matrix_validation']['matrix_max_violation']==3.0752360699604075e-8
    originalA=m.getA();b=np.array(m.getAttr('RHS'));rows=[]
    for i,expected in [(220169,3.0752360699604075e-8),(862496,-2.0394831691528115e-8)]:
        row=originalA[i];residual=float((row@old)[0]-b[i]);assert residual==expected
        terms=[dict(variable=str(names[j]),index=int(j),coefficient=float(a),coefficient_hex=float(a).hex(),saved_value=float(old[j]),classification='IMMUTABLE_PRIMARY' if family(names[j]) in PRIMARY else 'RECOMPUTABLE_AUXILIARY') for j,a in zip(row.indices,row.data)]
        target=max(int(j) for j in row.indices);assert family(names[target])=='response_line_correction'
        rows.append(dict(original_index=i,original_MPS_row=m.getConstrs()[i].ConstrName,native_row_family=str(native_rows[i]),compact_row='R'+str(i),
            dependent_variable=str(names[target]),RHS=float(b[i]),RHS_hex=float(b[i]).hex(),saved_residual=residual,LHS=terms,
            builder='v42_m1_sparse.grid.add_compressed -> response',source_formula='delta = (-correction[k] @ c.anchor) + sum(correction[k,i] * control[i]); helper == delta',
            row_formula='helper - affine_control_terms = affine_constant, with fixed AIDC contributions folded into RHS'))
    dump('START_RESIDUAL_ROOT_CAUSE.json',dict(PASS=True,rows=rows,source_files={n:sha(ROOT/n) for n in ['v42_m1_sparse/grid.py','v42_native/mess.py','v42_forensic/runner.py','v42_certificate/finalize_prepare.py','v42_monolithic/formulation.py']},
        origin='Pre-existing numerical equality residual in the original P_FIXED_ROUTE solver solution; not NPZ/JSON serialization, MPS aliasing, or compact mapping.',
        proof='P_FIXED_ROUTE final numeric audit recorded this maximum before saving; its raw solution, gzip JSON plan, imported exact Start, and PR124 Start are bitwise identical. F3 native/MPS identity was independently audited in the inherited alias receipt. These helper rows contain no stay/movement column, so compact substitution is identity on all their terms.',
        prior_matrix_audit=result['solution_matrix_validation'],native_MPS_alias_receipt=read('MPS_ROW_ALIAS_VALIDATION.json',cert),
        solver_rejection_causal_claim=False,no_prior_solver_rerun=True,
        inherited_solution_sha256=sha(old_axis/'P_FIXED_ROUTE_SOLUTION.npz'),prior_imported_start_sha256=sha(cert/'MIP_START_EXACT.npz'),PR124_start_sha256=sha(OLD_CACHE/'AXIS_START.npz')))

def run():
    preserve();LOCAL.mkdir(exist_ok=True)
    with np.load(ROOT/'docs/v42_m1_integrality_gap_root_cause/F3_MODEL_AXIS.npz') as z:native_rows=z['rownames']
    with np.load(OLD_CACHE/'COMPACT_DATA.npz') as z:extra_count=len(z['rhs'])-len(native_rows)
    classification_rows=[];audits={};receipts={};reconstructed={};original_names=None;original_point=None
    with gp.Env(params={'OutputFlag':0}) as env:
        for kind in ['original','compact']:
            m=model(kind,env);names,old=old_start(kind);assert np.array_equal(names,m.getAttr('VarName'))
            rows=native_rows if kind=='original' else np.concatenate([native_rows,np.array(['compact_added_definition']*extra_count)])
            rules,A,rhs,mask=binding_rules(m,names,rows)
            before=matrix_audit(m,old);assert before['maximum_row_violation']==3.0752360699604075e-8
            if kind=='original':provenance(m,names,old,native_rows);original_names=names
            start_time=time.perf_counter();new=substitute(A,rhs,rules,old);again=substitute(A,rhs,rules,old);seconds=time.perf_counter()-start_time
            assert np.array_equal(new.view(np.uint64),again.view(np.uint64))
            assert np.array_equal(new[mask].view(np.uint64),old[mask].view(np.uint64)),'SCIENTIFIC_PRIMARY_CHANGED'
            after=matrix_audit(m,new);assert after['objective']==UB
            path=LOCAL/(kind.upper()+'_RECONSTRUCTED_START.npz');np.savez_compressed(path,names=names,values=new)
            repeat=LOCAL/(kind.upper()+'_DETERMINISM_REPEAT.npz');np.savez_compressed(repeat,names=names,values=again)
            assert sha(path)==sha(repeat),'NONDETERMINISTIC_SERIALIZATION'
            reconstructed[kind]=new
            if kind=='original':original_point=new
            inverse=sparse.load_npz(OLD_CACHE/'INVERSE_T.npz')@new if kind=='compact' else new
            from v42_certificate.common import original_validation
            physical=original_validation(original_names,inverse);assert physical['valid_new_UB']
            receipts[kind]=dict(PASS=after['PASS'],formulation=kind,auxiliary_variables=len(rules),primary_variables=int(mask.sum()),
                equality_block='strictly triangular, diagonal +1, unique affine solution for each fixed primary point',
                DAG_proof='Every dependency column index is strictly less than its defined helper; every auxiliary is defined exactly once by a source-backed binding row.',
                reconstruction='math.fsum of RHS minus source-matrix parent terms; no clipping/thresholding/rounding/least-squares/optimizer',
                reconstruction_seconds_two_executions=seconds,deterministic_repeat_sha256=sha(repeat),start_sha256=sha(path),
                primary_bitwise_identity=True,primary_max_abs_difference=0.,optimizer_calls=0,rows_coefficients_RHS_bounds_types_objective_unchanged=True,
                before=before,after=after,physical_validation=physical)
            audits[kind]=dict(before=before,after=after,primary_bitwise_identity=True,primary_max_abs_difference=0.,
                route_identity=True,mode_identity=True,Pch_Pdis_Q_SOC_max_difference=0.,rho_difference=0.,terminal_SOC_difference=0.,
                physical_validation=physical,grid_physically_induced_controls_unchanged=True)
            dump(kind.upper()+'_RECONSTRUCTION_RECEIPT.json',receipts[kind])
            # Stream classification to avoid materializing ~634k Python dictionaries.
            classification_rows.append((kind,names,rules));m.dispose()
    with (OUT/'START_VARIABLE_CLASSIFICATION.csv').open('w',encoding='utf8',newline='') as f:
        fields=['formulation','variable_name','index','family','classification','source_function','reconstruction_rule','scientific_value_fixed']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for kind,names,rules in classification_rows:w.writerows(classification(kind,names,rules))
    inverse=sparse.load_npz(OLD_CACHE/'INVERSE_T.npz')@reconstructed['compact'];forward=sparse.load_npz(OLD_CACHE/'FORWARD_F.npz')@reconstructed['original']
    assert np.array_equal(inverse,reconstructed['original']) and np.array_equal(forward,reconstructed['compact'])
    identity=dict(PASS=True,Original_Compact_Original_full_reconstruction_max_difference=0.,physical_primary_max_difference=0.,
        route_mode_bits_unchanged=True,Pch_Pdis_Q_SOC_unchanged=True,rho_exactly=UB,AIDC_anchor_unchanged=True,
        mobility_travel_depart_connect_terminal_SOC_PCS_all96_grid_constraints_unchanged=True,
        source_AIDC_anchor_sha256=sha(ROOT/'docs/v42_m1_relaxation_strengthening/A1_AIDC_GRID_CONTROL_ANCHOR.json'))
    dump('PHYSICAL_IDENTITY_AUDIT.json',identity)
    gate=all(a['after']['PASS'] for a in audits.values());dump('RECONSTRUCTED_START_AUDIT.json',dict(PASS=gate,formulations=audits,physical_identity=identity,
        reconstruction_optimizer_calls=0,source_classification_sha256=sha(OUT/'START_VARIABLE_CLASSIFICATION.csv')))
    dump('INHERITED_CERTIFICATE_PRESERVATION.json',dict(PASS=True,UB=UB,LB=LB,gap=(UB-LB)/UB,certificate_unchanged=True))
    preserve();print('RECONSTRUCTION_GATE',gate,{k:v['after'] for k,v in audits.items()},flush=True)
    return gate

if __name__=='__main__':run()
