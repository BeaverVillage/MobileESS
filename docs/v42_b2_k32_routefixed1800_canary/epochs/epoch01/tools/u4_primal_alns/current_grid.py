"""Fresh original-FULL critical rows for each validated Primal center.

Original NPZ rows are scanned in bounded per-slot strips, never assembled as a
FULL CSR or solver model. Exact dyadic helper elimination is used only for
signed neighborhood selection. It adds no cut, bound, or objective coefficient.
"""
from __future__ import annotations
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import time
import numpy as np
from tools.time_decomposed_lb.grid import SelectiveAuthority, sha, write

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/v42_b2_u4_primal_alns_600x3'
SOURCE_SHA = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE_SHA = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
INITIAL_SHA = 'c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d'
COEFFICIENTS = Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\COEFFICIENTS.npz')
COEFFICIENTS_SHA = 'b3370e37a375d6b358ba0695feeb5bad26da4d043447669f5d2d3024ad20eba8'
QUOTA = dict(line_thermal_face=12,transformer_kVA=4,NormalAmps=2,voltage_upper=4,voltage_lower=4)


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _vector_sha(point):
    return hashlib.sha256(np.ascontiguousarray(point,dtype='<f8').tobytes()).hexdigest()


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _receipt(case, center_sha, context, kind, selected, wall):
    return dict(PASS=True,source=SOURCE_SHA,case_sha=case.case_sha,
        center_point_vector_sha256=center_sha,selection_kind=kind,
        all_original_security_rows_scanned=814560,omitted_from_current_grid_scan=0,
        source_family_counts={f:context['current_U4_grid_scan'][f]['rows'] for f in QUOTA},
        critical_rows=[dict(original_row=r['original_row'],name=r['name'],slot=r['slot'],family=r['family']) for r in selected],
        selection_rule='Top normalized signed FULL residuals per family; unique slot/asset/phase; quotas12/4/2/4/4.',
        original_model_projection='Source18r certified inverse lift of this center; direct bounded ORIGINAL FULL rows.',
        original_helper_elimination='Exact stored binary64 interpreted as Fractions; all response/injection/fixed correction constants retained.',
        source_context_canonical_sha256=_canonical_sha(context),
        score_packets_do_not_change_Native_matrix_bounds_objective=True,
        new_center_requires_independent_FULL_replay=True,FULL_CSR_constructed=False,
        Gurobi_imported=False,Native_optimize_calls=0,wall_seconds=wall)


def refresh(case, point):
    """Return dynamic context and proof receipt; cache only identical centers.

    The caller must supply its own independently FULL-validated center. The
    exact initial point can reuse its full scan. Every different vector forces
    a new original-FULL scan, including rows absent from the old26 selection.
    """
    started=time.perf_counter()
    x=np.asarray(point)
    _require(case.case_sha==CASE_SHA and x.dtype==np.dtype('float64') and x.shape==(354277,)
        and np.isfinite(x).all(),'CURRENT_FULL_CENTER_CASE_AXIS')
    center_sha=_vector_sha(x)
    initial=_read(DOCS/'SIGNED_SELECTION_CONTEXT.json')
    _require(initial['source']==SOURCE_SHA and initial['case_sha']==CASE_SHA
        and initial['initial_point_sha256']==INITIAL_SHA,'FROZEN_INITIAL_GRID_AUTHORITY')
    if center_sha==INITIAL_SHA:
        diagnostic=_read(DOCS/'U4_K32_SIGNED_DIAGNOSTICS.json')
        _require(diagnostic['PASS'] and diagnostic['initial_point_sha256']==center_sha
            and diagnostic['full_security_rows_scanned']==814560,'IDENTICAL_INITIAL_FULL_SCAN_REQUIRED')
        receipt=_receipt(case,center_sha,initial,'IDENTICAL_VERIFIED_INITIAL_CENTER_FULL_SCAN_REUSE',
            initial['critical_exact_rows'],time.perf_counter()-started)
        receipt['frozen_initial_context_file_sha256']=sha(DOCS/'SIGNED_SELECTION_CONTEXT.json')
        receipt['frozen_initial_raw_file_sha256']=sha(DOCS/'SIGNED_SELECTION_SOURCE_RAW.json')
        _require(receipt['frozen_initial_raw_file_sha256']==initial['source_raw_packet_sha256'],
            'INITIAL_RAW_PACKET_DRIFT')
        initial_audit=DOCS/'SIGNED_SELECTION_INDEPENDENT_NATIVE0.json'
        proof=_read(initial_audit)
        _require(proof['PASS'] and proof['context_sha256']==receipt['frozen_initial_context_file_sha256']
            and proof['source_raw_sha256']==receipt['frozen_initial_raw_file_sha256'],
            'INITIAL_SIGNED_INDEPENDENT_AUDIT_REQUIRED')
        receipt['independent_exact_source_audit']=dict(path=str(initial_audit),sha256=sha(initial_audit),PASS=True)
        return initial,receipt
    out=DOCS/'adaptive_grid'/center_sha
    context_path,raw_path,receipt_path=(out/n for n in ('CURRENT_GRID_CONTEXT.json','CURRENT_GRID_SOURCE_RAW.json','CURRENT_GRID_RECEIPT.json'))
    if receipt_path.exists():
        cached=_read(receipt_path)
        _require(cached['PASS'] and cached['center_point_vector_sha256']==center_sha
            and cached['source']==SOURCE_SHA and cached['case_sha']==CASE_SHA
            and cached['context_file_sha256']==sha(context_path)
            and cached['raw_file_sha256']==sha(raw_path)
            and cached['independent_exact_source_audit']['PASS']
            and sha(cached['independent_exact_source_audit']['path'])==cached['independent_exact_source_audit']['sha256'],
            'DYNAMIC_GRID_CACHE_SHA_DRIFT')
        return _read(context_path),cached
    # A is never loaded here. The exact inverse transport already exists on
    # case; its original helper values belong to this FULL-validated point.
    original=case.lift(x)
    _require(original.shape==(344967,) and np.isfinite(original).all(),'CURRENT_ORIGINAL_LIFT')
    _require(sha(COEFFICIENTS)==COEFFICIENTS_SHA,'SIGNED_METADATA_COEFFICIENT_AUTHORITY')
    with np.load(COEFFICIENTS,allow_pickle=False) as z:
        coefficients={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}
    from tools.u4_primal_alns.diagnostics import scan
    authority=SelectiveAuthority()
    try:
        # Every original Security row is considered, including presolve-removed
        # redundant rows and rows outside the old selected time intervals.
        grid,candidates=scan(authority,original,coefficients)
        _require(sum(r['rows'] for r in grid.values())==814560,'COMPLETE_CURRENT_GRID_SCAN')
        selected=[]
        for family,count in QUOTA.items():
            seen=set()
            for row in candidates[family]:
                key=(row['slot'],row['metadata']['asset'],row['metadata']['phase'])
                if key not in seen:
                    selected.append(row);seen.add(key)
                if len(seen)>=count:break
        name_to_column={str(n):int(j) for j,n in enumerate(authority.maps['names'])}
        packets=[];raw_ids=set()
        for row in selected:
            p=authority.project(row['original_row'],row['slot'])
            packet=dict(name=p['name'],original_row=row['original_row'],family=row['family'],slot=row['slot'],
                rhs=p['rhs'],coeff={str(name_to_column[n]):v for n,v in p['coeff'].items()},
                priority_scale=str(F(row['priority_scale'])),helper_rows=p['helper_rows'],source_row_sha256=p['source_row_sha256'],
                eliminated_constant=p['eliminated_constant'],metadata=row['metadata'],source_sense=p['original_sense'],
                source_rhs_hex=p['original_rhs_hex'])
            packets.append(packet);raw_ids.add(row['original_row']);raw_ids.update(p['helper_rows'])
        initial_raw=_read(DOCS/'SIGNED_SELECTION_SOURCE_RAW.json')
        pcs_ids=initial_raw['PCS16_original_rows'];raw_ids.update(pcs_ids)
        raw_rows=[authority.raw(i) for i in sorted(raw_ids)]
        columns={j for row in raw_rows for j,v in row['terms']}
        raw=dict(source=SOURCE_SHA,case_sha=CASE_SHA,source_files=authority.records,
            center_point_vector_sha256=center_sha,rows=raw_rows,PCS16_original_rows=pcs_ids,
            columns={str(j):dict(name=str(authority.maps['names'][j]),lower_hex=float(authority.maps['lower'][j]).hex(),
                upper_hex=float(authority.maps['upper'][j]).hex(),type=str(authority.maps['types'][j])) for j in sorted(columns)},
            Native_optimize_calls=0,FULL_CSR_constructed=False)
        write(raw_path,raw)
        context=dict(source=SOURCE_SHA,case_sha=CASE_SHA,initial_point_sha256=INITIAL_SHA,
            center_point_sha256=center_sha,original_rho_column=authority.rho,critical_exact_rows=packets,
            PCS16_vertices_exact=initial['PCS16_vertices_exact'],source_raw_packet_sha256=sha(raw_path),
            current_U4_grid_scan=grid,exact_helpers_and_all_source_coefficients_preserved=True,
            metadata_coefficients_sha256=COEFFICIENTS_SHA,Native_optimize_calls=0)
        write(context_path,context)
        from tools.u4_primal_alns.signed_verify import audit
        audit_path=out/'CURRENT_GRID_INDEPENDENT_NATIVE0.json'
        proof=audit(context_path,raw_path,center_sha,audit_path)
        _require(proof['PASS'],'FRESH_CURRENT_SIGNED_SOURCE_INDEPENDENT_AUDIT_FAILED')
        receipt=_receipt(case,center_sha,context,'FRESH_ALL_ORIGINAL_FULL_SECURITY_ROW_SCAN',packets,time.perf_counter()-started)
        receipt.update(context_file=str(context_path),context_file_sha256=sha(context_path),
            raw_file=str(raw_path),raw_file_sha256=sha(raw_path),source_files=authority.records,
            new_original_rows_vs_initial=sorted(set(r['original_row'] for r in packets)-
                set(r['original_row'] for r in initial['critical_exact_rows'])),
            original_native_domain_constraints_removed=0,selected_family_counts=dict(Counter(r['family'] for r in packets)))
        receipt['independent_exact_source_audit']=dict(path=str(audit_path),sha256=sha(audit_path),PASS=True)
        write(receipt_path,receipt)
        return context,receipt
    finally:
        authority.close()
