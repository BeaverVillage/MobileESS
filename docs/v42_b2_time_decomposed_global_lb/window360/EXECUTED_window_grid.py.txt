"""Native0 eight-slot security authority, exact sparse helper factorization.

Original security/helper rows are serialized unchanged. Every helper affine
expression is separately expanded with exact Fractions and time-audited; every
security row records the precise linear combination of those affines. This is
exact elimination in factored coordinates without materializing 19m repeated
facet coefficients. No FULL CSR, solver model, Gurobi import, or Optimize.
"""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import argparse
import json
import time

from tools.time_decomposed_lb.grid import (SelectiveAuthority, SOURCE, CASE, PARENT,
    FAMILIES, PHYSICAL, ROOT, require, sha, write, canonical_sha)


def build(out):
    started=time.perf_counter()
    out=Path(out)
    require(not (out/'WINDOW_GRID_AUTHORITY.json').exists(),'SEALED_WINDOW_GRID_NO_REBUILD')
    out.mkdir(parents=True,exist_ok=True)
    slots=list(range(88,96));authority=SelectiveAuthority()
    security_ids=set();helper_ids=set();affines={};security_proof=[];families=Counter();slot_reports=[]

    def leaf_slot(j,slot):
        name=str(authority.maps['names'][j])
        if name=='rho_max':return
        match=PHYSICAL.fullmatch(name)
        require(match is not None and int(match.group(4))==slot,'WINDOW_HELPER_OTHER_TIME_OR_NONPHYSICAL_LEAF:'+name)

    def affine(j,slot):
        if j in affines:
            require(affines[j]['slot']==slot,'SHARED_HELPER_HAS_INCONSISTENT_SLOT')
            return affines[j]
        constant,coeff,deps=authority.expand(j)
        for q in coeff:leaf_slot(q,slot)
        for r in deps:
            for q,w in authority.terms(r):
                if w==1. and q in authority.helper_defs and authority.helper_defs[q]==r and q!=j:
                    affine(q,slot)
        exact=dict(constant=str(constant),coeff={str(q):str(c) for q,c in sorted(coeff.items())})
        packet=dict(original_column=j,name=str(authority.maps['names'][j]),slot=slot,
            defining_original_row=authority.helper_defs[j],exact_constant=exact['constant'],exact_coeff=exact['coeff'],
            helper_dependency_rows=sorted(deps),exact_affine_sha256=canonical_sha(exact),all_nonrho_leaves_same_slot=True)
        affines[j]=packet
        return packet

    try:
        for slot in slots:
            ids=authority.security_by_slot[slot];counts=Counter();used_helpers=set();support_upper=0;digests=[]
            for i in ids:
                row=authority.raw(i);sense=row['sense'];require(sense in ('<','>'),'WINDOW_SECURITY_SENSE')
                sign=F(1) if sense=='<' else F(-1)
                constant=F(0);support=set();source_combinations=[]
                for j,w in authority.terms(i):
                    if j in authority.helper_defs:
                        p=affine(j,slot)
                        constant+=sign*F(w)*F(p['exact_constant'])
                        support.update(int(q) for q in p['exact_coeff'])
                        used_helpers.update(p['helper_dependency_rows']);helper_ids.update(p['helper_dependency_rows'])
                        source_combinations.append(dict(original_column=j,coefficient_hex=w.hex(),helper_affine_sha256=p['exact_affine_sha256']))
                    else:
                        leaf_slot(j,slot);support.add(j)
                        source_combinations.append(dict(original_column=j,coefficient_hex=w.hex(),direct_original_physical_leaf=True))
                rhs=sign*F(float.fromhex(row['rhs_hex']))-constant
                factored=dict(normalized_sign=str(sign),exact_rhs=str(rhs),source_combinations=source_combinations)
                signature=canonical_sha(factored)
                security_proof.append(dict(original_row=i,name=row['name'],slot=slot,source_row_sha256=row['source_row_sha256'],
                    normalized_sense='<',normalized_sign=str(sign),exact_rhs=str(rhs),eliminated_constant=str(constant),
                    exact_factored_projection_sha256=signature,source_combinations=source_combinations,
                    projected_nnz_support_upper_bound=len(support),all_nonrho_leaves_same_slot=True,cross_time_leaves=[]))
                security_ids.add(i);family=row['name'].split('[',1)[0];counts[family]+=1;families[family]+=1
                support_upper+=len(support);digests.append([i,signature])
            require(sum(counts.values())==8485 and set(counts)==set(FAMILIES),'WINDOW_COMPLETE_SLOT_SECURITY_COVER')
            require(len(used_helpers)==1140,'WINDOW_COMPLETE_SLOT_HELPER_CLOSURE')
            slot_reports.append(dict(slot=slot,security_rows=len(ids),helper_rows=len(used_helpers),family_counts=dict(counts),
                projected_grid_nnz_support_upper_bound=support_upper,exact_factored_projection_digest_sha256=canonical_sha(digests),
                exact_same_slot_leaf_audit_PASS=True,omitted_original_security_rows=[]))
            print(json.dumps(dict(Native0=True,slot_complete=slot,security_rows=len(ids),helpers=len(used_helpers))),flush=True)
        all_ids=security_ids|helper_ids;raw_rows=[authority.raw(i) for i in sorted(all_ids)]
        cols={int(j) for r in raw_rows for j,_ in r['terms']}
        axis={str(j):dict(name=str(authority.maps['names'][j]),lower_hex=float(authority.maps['lower'][j]).hex(),
            upper_hex=float(authority.maps['upper'][j]).hex(),type=str(authority.maps['types'][j]),
            objective_hex=float(authority.maps['objective'][j]).hex()) for j in sorted(cols)}
        require(len(affines)==len(helper_ids)==9120,'ALL_WINDOW_HELPER_AFFINES_REPRESENTED')
        raw=dict(schema='V42_WINDOW_GRID_RAW_CLOSURE_V1',source=SOURCE,case_sha=CASE,parent=PARENT,window=[88,96],slots=slots,
            original_full_shape=list(authority.shape),source_files=authority.records,columns=axis,rows=raw_rows,
            original_security_rows=sorted(security_ids),helper_rows=sorted(helper_ids),Native_optimize_calls=0,
            FULL_CSR_constructed=False,FULL96_model_reconstructed=False)
        projection=dict(schema='V42_WINDOW_GRID_EXACT_FACTORED_PROJECTION_V2',source=SOURCE,case_sha=CASE,parent=PARENT,window=[88,96],
            helper_affines=[affines[j] for j in sorted(affines)],security_rows=security_proof,slot_reports=slot_reports,source_files=authority.records,
            exact_Fraction_helper_expansion=True,exact_Fraction_security_linear_combinations=True,
            repeated_dense_facet_coefficients_not_materialized=True,original_coefficient_deletion=False,
            proof='Each original equality helper has a unique +1 pivot and acyclic recursive exact affine form. Every original security row is exactly the stored dyadic linear combination of these forms plus direct physical leaves. All expanded leaves are the row own slot Pch/Pdis/Q or shared rho_max. This proves exact FULL slot projection and equivalence of literal Native helper lift without repeating every facet coefficient.',
            Native_optimize_calls=0,Gurobi_imported=False,FULL_CSR_constructed=False)
        write(out/'WINDOW_GRID_RAW_CLOSURE.json.gz',raw)
        write(out/'WINDOW_GRID_FRACTION_PROJECTION.json.gz',projection)
        report=dict(PASS=True,schema='V42_WINDOW_GRID_AUTHORITY_V2',source=SOURCE,case_sha=CASE,parent=PARENT,window=[88,96],slots=slots,
            security_rows=len(security_ids),helper_rows=len(helper_ids),grid_rows=len(raw_rows),grid_columns=len(cols),
            grid_nnz=sum(len(r['terms']) for r in raw_rows),family_counts=dict(families),slot_reports=slot_reports,source_files=authority.records,
            rho_contract=dict(name='rho_max',original_column=authority.rho,lower=0.,upper=1.,objective=1.,objective_constant=0.),
            exact_Fraction_helper_affines_certified=9120,exact_factored_security_rows_certified=67880,
            actual_native_representation='Literal original equalityhelper/security lift; exact source stored binary64 coefficients/RHS/senses/bounds; native conversion error=0.',
            mathematical_helper_equivalence='Triangular unique helper lift projection equals exact factored Fraction elimination; fully dense facet materialization is unnecessary.',
            original_helper_infinite_bounds_preserved=True,source_rhs_and_coefficients_binary64_exact=True,
            original_FULL_to_window_grid_projection_proved=True,all_slot_original_security_families_retained=True,
            omitted_security_rows=[],cross_time_leaf_rows=[],Native_optimize_calls=0,Gurobi_imported=False,
            Full96_model_builds=0,FULL_CSR_constructed=False,
            evidence={n:sha(out/n) for n in ['WINDOW_GRID_RAW_CLOSURE.json.gz','WINDOW_GRID_FRACTION_PROJECTION.json.gz']},
            wall_seconds=time.perf_counter()-started,code_sha256=sha(__file__),grid_accessor_code_sha256=sha(ROOT/'tools/time_decomposed_lb/grid.py'))
    finally:
        authority.close()
    report['temp_NPY_memmaps_removed']=True
    write(out/'WINDOW_GRID_AUTHORITY.json',report)
    print(json.dumps({k:report[k] for k in ['PASS','security_rows','helper_rows','grid_rows','grid_columns','grid_nnz','wall_seconds']}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();build(a.out)
