"""Exact native grid-row projection; equivalent representation, never a new cut.

Eight fixed scientific rows are expressed in Pch/Pdis/Q/rho by combining their
native affine equalities. Fixed auxiliary bounds are explicit zero-width-box
equalities. An independent recombination checker verifies every coefficient
and RHS using exact rationals of stored binary64, without a Native call.
"""
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'docs/v42_m1_joint_gap_research'
FIXED_ROWS=(438197,465244,492778,520001,546995,570130,439268,548296)
TARGET={'Pch','Pdis','Q','rho_max'}


def _family(name):
    return str(name).split('[',1)[0]


def _vector(A,row):
    a,b=A.indptr[row:row+2]
    return {int(j):F(float(w)) for j,w in zip(A.indices[a:b],A.data[a:b]) if w}


def _add(total,terms,multiplier):
    for j,value in terms.items():
        total[j]=total.get(j,F(0))+multiplier*value
        if not total[j]:del total[j]


def project_rows(case):
    A,d=case.A.tocsr(),case.d
    families=[_family(n) for n in d['names']]
    definitions={}
    for i,name in enumerate(d['row_names']):
        f=_family(name)
        if not f.endswith('_binding') or str(d['sense'][i])!='=':continue
        a,b=A.indptr[i:i+2]
        pivots=[int(j) for j in A.indices[a:b] if families[int(j)]==f[:-8]]
        if len(pivots)!=1:raise ValueError('PQ_PROJECTION_NATIVE_AFFINE_PIVOT_NOT_UNIQUE')
        if pivots[0] in definitions:raise ValueError('PQ_PROJECTION_NATIVE_AFFINE_DEFINITION_DUPLICATE')
        definitions[pivots[0]]=int(i)
    result=[]
    for source in FIXED_ROWS:
        if _family(d['row_names'][source]) not in {'line_thermal_face','transformer_kVA'}:
            raise ValueError('PQ_PROJECTION_FIXED_SCIENTIFIC_ROW_ID_DRIFT')
        sign=-1 if str(d['sense'][source])=='>' else 1
        vector={j:sign*w for j,w in _vector(A,source).items()}
        rhs=sign*F(float(d['rhs'][source]));weights={};fixed={};unresolved=[]
        rounds=0
        while True:
            auxiliary=[j for j in vector if families[j] not in TARGET]
            if not auxiliary:break
            progress=False
            for j in auxiliary:
                if j not in vector:continue
                weight=vector[j]
                if j in definitions:
                    i=definitions[j];equation=_vector(A,i)
                    multiplier=-weight/equation[j]
                    _add(vector,equation,multiplier)
                    rhs+=multiplier*F(float(d['rhs'][i]))
                    weights[i]=weights.get(i,F(0))+multiplier
                    if not weights[i]:del weights[i]
                    progress=True
                elif d['lower'][j]==d['upper'][j]:
                    multiplier=-weight
                    del vector[j]
                    rhs+=multiplier*F(float(d['lower'][j]))
                    fixed[j]=fixed.get(j,F(0))+multiplier
                    if not fixed[j]:del fixed[j]
                    progress=True
            rounds+=1
            if not progress or rounds>20:
                unresolved=[dict(column=int(j),name=str(d['names'][j])) for j in vector if families[j] not in TARGET]
                break
        rho_ids=[j for j in vector if families[j]=='rho_max']
        expression=None
        if not unresolved and len(rho_ids)==1 and vector[rho_ids[0]]<0:
            rho=rho_ids[0];coefficient=vector[rho]
            expression=dict(form='rho_max >= constant + sum(coefficient * original physical Pch/Pdis/Q)',
                exact_constant=str(rhs/coefficient),
                exact_physical_coefficients={str(j):str(-w/coefficient) for j,w in sorted(vector.items()) if j!=rho})
        result.append(dict(source_row=source,source_name=str(d['row_names'][source]),
            source_normalization_sign=sign,normalized_sense='<',case_sha=case.case_sha,
            exact_projected_coefficients={str(j):str(w) for j,w in sorted(vector.items())},
            exact_projected_rhs=str(rhs),
            exact_native_equality_multipliers={str(i):str(w) for i,w in sorted(weights.items())},
            exact_fixed_native_bound_equality_multipliers={str(j):str(w) for j,w in sorted(fixed.items())},
            unresolved_auxiliary_columns=unresolved,PQ_rho_only=not unresolved,
            direct_rho_lower_requirement=expression,
            coefficient_names={str(j):str(d['names'][j]) for j in vector},
            equivalent_original_row_representation=True,new_valid_inequality_added=False,
            stronger_feasible_set_or_Global_LB_claimed=False))
    return result


def verify_projection_packet(case,packets):
    """Independent stored-rational recombination; does not call projection code."""
    packets=list(packets)
    if any(not isinstance(packet,dict) or packet.get('case_sha')!=case.case_sha for packet in packets):
        raise ValueError('PQ_PROJECTION_CASE_IDENTITY_DRIFT')
    # Certify this preregistered packet of eight rows, not an empty, repeated or
    # substituted subset that happens to contain individually valid identities.
    if (any(not isinstance(packet.get('source_row'),(int,np.integer))
            or isinstance(packet.get('source_row'),(bool,np.bool_)) for packet in packets)
            or tuple(int(packet['source_row']) for packet in packets)!=FIXED_ROWS):
        raise ValueError('PQ_PROJECTION_FIXED_ROW_PACKET_COVER_INCOMPLETE_OR_DUPLICATED')
    A,d=case.A.tocsr(),case.d;checked=[]
    for packet in packets:
        i=int(packet['source_row']);sg=int(packet['source_normalization_sign'])
        expected_sign=-1 if str(d['sense'][i])=='>' else 1
        if sg!=expected_sign or str(d['sense'][i]) not in {'<','>'}:
            raise ValueError('PQ_PROJECTOR_ORIGINAL_INEQUALITY_SIGN_DRIFT')
        total={};a,b=A.indptr[i:i+2]
        for j,value in zip(A.indices[a:b],A.data[a:b]):total[int(j)]=sg*F(float(value))
        rhs=sg*F(float(d['rhs'][i]))
        for key,value in packet['exact_native_equality_multipliers'].items():
            row=int(key);multiplier=F(value)
            if str(d['sense'][row])!='=':raise ValueError('PQ_PROJECTION_MULTIPLIER_ROW_IS_NOT_NATIVE_EQUALITY')
            a,b=A.indptr[row:row+2]
            for j,coefficient in zip(A.indices[a:b],A.data[a:b]):
                j=int(j);total[j]=total.get(j,F(0))+multiplier*F(float(coefficient))
            rhs+=multiplier*F(float(d['rhs'][row]))
        for key,value in packet['exact_fixed_native_bound_equality_multipliers'].items():
            j=int(key);multiplier=F(value)
            if not np.isfinite(d['lower'][j]) or d['lower'][j]!=d['upper'][j]:
                raise ValueError('PQ_PROJECTION_FIXED_BOUND_NOT_NATIVE_EQUALITY')
            total[j]=total.get(j,F(0))+multiplier
            rhs+=multiplier*F(float(d['lower'][j]))
        total={j:w for j,w in total.items() if w}
        received={int(j):F(w) for j,w in packet['exact_projected_coefficients'].items()}
        if total!=received or rhs!=F(packet['exact_projected_rhs']):
            raise ValueError('PQ_PROJECTION_EXACT_COEFFICIENT_OR_RHS_MISMATCH')
        remaining=[j for j in total if _family(d['names'][j]) not in {'Pch','Pdis','Q','rho_max'}]
        expression=packet['direct_rho_lower_requirement']
        if expression:
            rho=[j for j in total if str(d['names'][j])=='rho_max']
            if len(rho)!=1 or total[rho[0]]>=0 or remaining:raise ValueError('PQ_PROJECTION_RHO_REARRANGEMENT_INVALID')
            divisor=total[rho[0]]
            if F(expression['exact_constant'])!=rhs/divisor or {int(j):F(w) for j,w in expression['exact_physical_coefficients'].items()}!={j:-w/divisor for j,w in total.items() if j!=rho[0]}:
                raise ValueError('PQ_PROJECTION_RHO_REARRANGEMENT_COEFFICIENT_DRIFT')
        slots=set();units=set();sites=set()
        for j in total:
            name=str(d['names'][j])
            if name.startswith(('Pch[','Pdis[','Q[')):
                u,s,t=name.split('[',1)[1][:-1].split(',');units.add(u);sites.add(s);slots.add(int(t))
        checked.append(dict(source_row=i,PASS=True,PQ_rho_only=not remaining,
            exact_native_binding_rows_used=len(packet['exact_native_equality_multipliers']),
            exact_fixed_bound_equalities_used=len(packet['exact_fixed_native_bound_equality_multipliers']),
            physical_term_count=sum(_family(d['names'][j]) in {'Pch','Pdis','Q'} for j in total),
            units=sorted(units),sites=sorted(sites),slots=sorted(slots),
            all_original_integer_plans_preserved=True,
            interpretation='Exact original grid row plus native equalities; no stronger relaxation and no new cut'))
    return dict(PASS=True,status='EXACT_EQUIVALENT_ORIGINAL_GRID_ROW_REPRESENTATIONS_VERIFIED',
        rows=checked,Native_optimize_added_calls=0,Native_Runtime_added_seconds=0,
        new_cut_or_LB_strengthening=False,coefficient_rounding=False,
        original_96_slot_feasible_set_unchanged=True)


def generate(case=None):
    from .escape_audit import _load_case_read_only,_npz_blob
    from v42_unified.audit import write
    started=perf_counter();case=_load_case_read_only() if case is None else case
    packets=project_rows(case)
    check=verify_projection_packet(case,packets)
    root,receipt=_npz_blob('docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz')
    point=root['x'];rho=int(np.flatnonzero(case.d['names']=='rho_max')[0])
    diagnostics=[]
    for packet in packets:
        projected=sum((F(w)*F(float(point[int(j)])) for j,w in packet['exact_projected_coefficients'].items()),F(0))-F(packet['exact_projected_rhs'])
        i=packet['source_row'];a,b=case.A.indptr[i:i+2]
        original=packet['source_normalization_sign']*(sum((F(float(w))*F(float(point[j])) for j,w in zip(case.A.indices[a:b],case.A.data[a:b])),F(0))-F(float(case.d['rhs'][i])))
        expression=packet['direct_rho_lower_requirement']
        required=None
        if expression:required=F(expression['exact_constant'])+sum((F(w)*F(float(point[int(j)])) for j,w in expression['exact_physical_coefficients'].items()),F(0))
        diagnostics.append(dict(source_row=i,stored_ROOT_rho=float(point[rho]),
            exact_original_row_point_residual=str(original),exact_projected_row_point_residual=str(projected),
            weighted_native_equality_point_residual_exact=str(projected-original),
            projected_rho_requirement_at_this_stored_fractional_point=None if required is None else float(required),
            requirement_at_one_point_is_not_Global_LB=True,
            stored_point_numerical_binding_residual_is_not_algebraic_identity_failure=True))
    mutation= json.loads(json.dumps(packets))
    mutation[0]['exact_projected_rhs']=str(F(mutation[0]['exact_projected_rhs'])+F(1,1000))
    try:verify_projection_packet(case,mutation)
    except ValueError:rejected=True
    else:rejected=False
    if not rejected:raise ValueError('PQ_PROJECTION_RHS_MUTATION_NOT_REJECTED')
    result=dict(schema='V42_OPTIMIZE_ZERO_ORIGINAL_GRID_PQ_PROJECTION_V1',case_sha=case.case_sha,
        performed=True,status='PQ_RHO_ONLY_EQUIVALENT_REPRESENTATION' if all(p['PQ_rho_only'] for p in packets) else 'PQ_ONLY_PROJECTION_NOT_PROVEN',
        fixed_scientific_rows=list(FIXED_ROWS),Native_optimize_added_calls=0,Native_Runtime_added_seconds=0,
        source_scientific_matrix_sha256=case.identity['C3A_matrix_sha256'],
        source_scientific_data_sha256=case.identity['C3A_data_sha256'],
        exact_rows=packets,independent_recombination_checker=check,point_diagnostics=diagnostics,
        ROOT_point_source_receipt=receipt,rhs_mutation_rejected=rejected,
        new_cut_added=False,new_model_or_solver_settings_added=False,
        actual_Global_LB_improvement='NOT_CLAIMED_ORIGINAL_ROW_REPRESENTATION_ONLY',
        all_96_slot_route_SOC_PCS_grid_and_objective_preserved=True,
        audit_wall_seconds=perf_counter()-started)
    write(REPORTS/'GRID_ROW_PQ_PROJECTION_PROOF.json',result)
    return result


if __name__=='__main__':
    r=generate()
    print('EXACT_GRID_PQ_PROJECTION',r['status'],'rows',len(r['exact_rows']),'Native=0')
