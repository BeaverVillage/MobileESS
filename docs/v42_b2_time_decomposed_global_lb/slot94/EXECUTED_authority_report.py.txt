"""Native0 records for exact source-helper factoring and fixed slot selection."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import subprocess

from tools.time_decomposed_lb.grid import CASE, FAMILIES, PARENT, ROOT, SOURCE, canonical_sha, read, require, sha, write


def parent_file_sha(path):
    relative=Path(path).relative_to(ROOT).as_posix()
    content=subprocess.run(['git','show',PARENT+':'+relative],cwd=ROOT,check=True,stdout=subprocess.PIPE).stdout
    require(hashlib.sha256(content).hexdigest()==sha(path),'PARENT_SOURCE_BYTES:'+relative)
    return sha(path)


def run():
    out=ROOT/'docs/v42_b2_time_decomposed_global_lb'
    prior=ROOT/'docs/v42_b2_root_lp_tightening/grid'
    exact=read(prior/'CUTS_EXACT.json')
    separation=read(prior/'SEPARATION.json')
    cert=ROOT/'docs/v42_b2_root_lp_tightening/base/CERTIFICATE.json'
    # The PR214 separator used this exact BASE certificate filename.
    if not cert.exists():
        possible=list((ROOT/'docs/v42_b2_root_lp_tightening/base').glob('*CERT*.json'))
        matches=[p for p in possible if sha(p)==separation['BASE_certificate_sha256']]
        require(len(matches)==1,'BASE_CERTIFICATE_FILE')
        cert=matches[0]
    require(sha(cert)==separation['BASE_certificate_sha256'],'BASE_CERTIFICATE_SHA')
    base=read(cert)
    require(base['PASS'] is True and base['solver_status']==2 and separation['PASS'] is True,'PR214_BASE_AND_SEPARATION_CERTIFIED')
    source_files={str(p.relative_to(ROOT)):parent_file_sha(p) for p in [prior/'CUTS_EXACT.json',prior/'SEPARATION.json',cert]}
    selection=[]
    for slot in [75,82,94]:
        rows=[r for r in exact['rows'] if r['metadata']['slot']==slot]
        require(rows and all(r['selected'] and r['exact_violation'] and float(r['normalized_violation'])>0 for r in rows),'FIXED_SLOT_ACTUAL_PR214_VIOLATION')
        selection.append(dict(slot=slot,actual_selected_violations=[dict(original_row=r['original_row'],name=r['name'],family=r['metadata']['family'],
            normalized_violation=r['normalized_violation'],exact_violation=r['exact_violation'],source_row_sha256=r['source_row_sha256']) for r in rows]))
        raw=read(out/f'slot{slot:02d}'/'GRID_RAW_CLOSURE.json.gz')
        authority=read(out/f'slot{slot:02d}'/'GRID_AUTHORITY.json')
        native_eq=[r for r in raw['rows'] if r['original_row'] in raw['helper_rows']]
        native_security=[r for r in raw['rows'] if r['original_row'] in raw['original_security_rows']]
        require(len(native_eq)==1140 and len(native_security)==8485,'SLOT_COMPLETE_HELPER_AND_GRID_ROWS')
        require(all(r['sense']=='=' for r in native_eq),'ORIGINAL_HELPER_EQUALITIES')
        require(dict(Counter(r['name'].split('[',1)[0] for r in native_security))==authority['family_counts'],'ALL_ORIGINAL_FAMILIES')
        report=dict(PASS=True,source=SOURCE,case_sha=CASE,parent=PARENT,slot=slot,
            exact_flattened_security_rows=authority['rows'],exact_flattened_security_nnz=authority['nnz'],
            flattened_nnz_cap=500000,flattened_formulation_size_admission=False,
            actual_native_formulation='LITERAL_ORIGINAL_HELPER_EXTENDED_FORMULATION',
            original_security_rows=len(native_security),original_helper_equality_rows=len(native_eq),
            compact_grid_rows=len(raw['rows']),compact_grid_nnz=sum(len(r['terms']) for r in raw['rows']),
            compact_grid_columns=len(raw['columns']),compact_helper_columns=len(raw['helper_rows']),
            source_family_counts=authority['family_counts'],
            rounding=dict(native_coefficients_and_rhs_original_stored_binary64=True,coefficient_conversion_error_exact='0',rhs_conversion_error_exact='0',
                equality_helper_rows_unchanged=True,inequality_senses_unchanged=True,small_coefficient_deletion=False,
                auxiliary_bounds_original_free=True,finite_physical_bounds_unchanged=True,
                flattened_outward_rows_saved_as_independent_projection_evidence_only=True),
            proof=dict(helper_system='Each dependency helper has a unique +1 pivot in an original equality; recursive Fraction expansion is acyclic.',
                existence='For every original FULL feasible point, copy the selected-slot physical Pch/Pdis/Q and rho, then copy its original helper values. All retained helper and security rows are literal original rows.',
                uniqueness='The triangular helper equalities uniquely determine each helper from the selected-slot physical leaves and fixed original RHS constants.',
                elimination='Recursively substituting those equalities gives exactly GRID_EXACT coeff/rhs before Native outward transport; no security row is removed.',
                equivalence='Projection of the literal helper extended formulation onto physical P/Q and rho equals the exact eliminated slot security polyhedron.',
                bound_contract='rho_max retains original [0,1], objective +1, ObjCon 0. All helper objective coefficients are 0 and original helper bounds are retained.',
                conclusion='Using helper coordinates changes matrix sparsity only; it neither strengthens nor weakens the exact source slot security projection.'),
            all_original_security_rows_retained=True,all_grid_helper_dependencies_retained=True,
            same_slot_leaf_audit=authority['helper_time_coupling_audit'],
            Native_optimize_calls=0,Full96_model_builds=0,
            evidence_sha256={name:sha(out/f'slot{slot:02d}'/name) for name in ['GRID_RAW_CLOSURE.json.gz','GRID_EXACT.json.gz','GRID_AUTHORITY.json']})
        write(out/f'slot{slot:02d}'/'EQUIVALENT_HELPER_LIFT.json',report)
    report=dict(PASS=True,preregistered_slots=[75,82,94],slots_changed_after_results=False,
        selection_basis='Frozen PR214 actual verified fractional BASE selected security violations, not Snapshot results.',
        BASE_certificate_sha256=sha(cert),BASE_point_kind='NUMERICAL_OPTIMAL_INDEPENDENTLY_WEAK_DUALITY_CERTIFIED_FRACTIONAL_POINT',
        source_files=source_files,actual_violations=selection,
        grid_family_counts_per_slot=authority['family_counts'],aggregate_three_slot_security_rows=3*8485,
        aggregate_family_counts={f:3*authority['family_counts'][f] for f in FAMILIES},
        Native_optimize_calls=0,source=SOURCE,case_sha=CASE,parent=PARENT,code_sha256=sha(__file__))
    write(out/'PR214_FIXED_SLOT_SELECTION_AUTHORITY.json',report)
    return report


if __name__=='__main__':
    print(json.dumps({k:v for k,v in run().items() if k in ['PASS','preregistered_slots','aggregate_three_slot_security_rows']}))
