"""Same-day input and lossless representation adapter for the existing M model.

Model equations come only from the existing native/F3/Compact/Presolve builders.
C3A conservatively keeps every regenerated C2 row; no historical point or
deletion packet participates in the new case.
"""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import pickle
import math
import re
import time

import numpy as np
from scipy import sparse

from v42_native.contracts import digest
from v42_integrated.matrix import arrays
from v42_m1_hybrid.blocks import matrix_sha
from v42_pr134_b1.common import atomic, record, sha, read, digest as storage_digest


@dataclass
class CampaignMCase:
    A: object
    d: dict
    original_A: object
    original_d: dict
    point: object
    graph: tuple
    case_sha: str
    identity: dict
    compact: object
    presolve: object
    bundle: dict
    anchor: dict
    planning: dict
    coefficients: object
    output: Path

    def lift(self, point):
        if np.asarray(point).shape != (self.A.shape[1],):
            raise ValueError('CURRENT_M_POINT_AXIS_DRIFT')
        return self.compact.inverse(self.presolve.inverse(point))


def _domain_sha(d):
    h = hashlib.sha256()
    for key in sorted(d):
        value = np.asarray(d[key])
        h.update(key.encode()); h.update(value.dtype.str.encode())
        h.update(np.asarray(value.shape, dtype='<i8').tobytes())
        h.update(value.tobytes())
    return h.hexdigest()


def _same(A, B):
    A, B = A.tocsr(), B.tocsr()
    return A.shape == B.shape and all(np.array_equal(getattr(A, k), getattr(B, k))
                                     for k in ('indptr', 'indices', 'data'))


def _project_row(A, rhs, i, definitions):
    """Independent exact substitution in one original row, without a solver."""
    terms = defaultdict(F); constant = F(0)
    def add(j, weight, stack=()):
        nonlocal constant
        if j in stack:
            raise ValueError('CURRENT_M_ALIAS_CYCLE')
        if j not in definitions:
            terms[j] += weight
            return
        row = definitions[j]
        constant += weight * F(float(row['constant']))
        for k, w in row['terms'].items():
            add(int(k), weight * F(float(w)), stack + (j,))
    a, b = A.indptr[i:i+2]
    for j, w in zip(A.indices[a:b], A.data[a:b]):
        add(int(j), F(float(w)))
    return {j: w for j, w in terms.items() if w}, F(float(rhs[i])) - constant


def _bound(value):
    """An original unbounded box endpoint is an extended rational infinity."""
    value=float(value)
    if math.isnan(value):raise ValueError('CURRENT_M_ORIGINAL_BOUND_NAN')
    return F(value) if math.isfinite(value) else value


def _scaled_bound(weight, endpoint):
    if not weight:return F(0)
    endpoint=_bound(endpoint)
    if isinstance(endpoint,F):return weight*endpoint
    # Do not convert the rational coefficient to float: an arbitrarily small
    # nonzero exact coefficient times infinity is still signed infinity.
    return math.inf if (weight>0)==(endpoint>0) else -math.inf


def _sum_bound(left, right):
    if isinstance(left,F) and isinstance(right,F):return left+right
    if isinstance(left,F):return right
    if isinstance(right,F):return left
    if left!=right:raise ValueError('CURRENT_M_INVALID_OPPOSITE_INFINITE_INTERVAL_ENDPOINTS')
    return left


def _transport_state_sha(compact,presolve,graph):
    """Bind every input used by the proof and the original inverse mapping."""
    state=dict(original_matrix=matrix_sha(compact.original),original_data=_domain_sha(compact.original_data),
        compact_matrix=matrix_sha(compact.A),compact_data=_domain_sha(compact.d),
        selected_matrix=matrix_sha(presolve.A),selected_data=_domain_sha(presolve.d),
        arcs=[(list(a[:4]),None if a[-1] is None else vars(a[-1])) for a in compact.arcs],
        initial=compact.initial,H=compact.H,n=compact.n,nodes=compact.nodes,
        arc_columns=[(u,k,j) for (u,k),j in sorted(compact.arc_columns.items())],
        node_columns=[(key,j) for key,j in sorted(compact.z.items())],
        incoming=[(key,value) for key,value in sorted(compact.incoming.items())],
        outgoing=[(key,value) for key,value in sorted(compact.outgoing.items())],
        parallel=sorted(compact.parallel),
        steps=presolve.steps,row_proofs=presolve.rows,bound_proofs=presolve.bound,
        row_ids=presolve.row_ids,col_ids=presolve.col_ids,initial_names=presolve.initial_names,
        graph_sites=graph[0],graph_initial=graph[1],graph_battery=vars(graph[3]))
    return storage_digest(state)


def _freeze_transport(compact,presolve,graph,proof,out):
    if proof.get('PASS') is not True:raise ValueError('CURRENT_M_TRANSPORT_PROOF_NOT_PASS')
    path=Path(out)/'ORIGINAL_DOMAIN_EQUIVALENCE.json'
    atomic(path,proof)
    root=Path(__file__).resolve().parents[1]
    sources={name:record(root/name) for name in ('v42_may_campaign/m_model.py',
        'v42_supercompact/formulation.py','v42_supercompact/presolve.py')}
    return dict(state_sha=_transport_state_sha(compact,presolve,graph),sources=sources,certificate=record(path))


def verify_transport(compact, presolve):
    """Independently verify the current graph expansion and exact elimination.

No presolve producer PASS is trusted. Every eliminated equality, transported
bound, retained coefficient/objective and deleted-row implication is replayed.
"""
    original, od = compact.original.tocsr(), compact.original_data
    C, c = compact.A.tocsr(), compact.d
    n = original.shape[1]
    for data in (od,c,presolve.d):
        if (np.isnan(data['lower']).any() or np.isnan(data['upper']).any()
                or np.isposinf(data['lower']).any() or np.isneginf(data['upper']).any()
                or np.any(data['lower']>data['upper'])):
            raise ValueError('CURRENT_M_ORIGINAL_INTERVAL_BOUND_INVALID')
    if not _same(C[:original.shape[0], :n], original) or C[:original.shape[0], n:].nnz:
        raise ValueError('CURRENT_M_ORIGINAL_CSR_EXTENSION_DRIFT')
    for key in ('lower', 'upper', 'objective'):
        if not np.array_equal(c[key][:n], od[key]):
            raise ValueError('CURRENT_M_ORIGINAL_COLUMN_METADATA_DRIFT:' + key)
    for key in ('rhs', 'sense', 'row_names'):
        if not np.array_equal(c[key][:original.shape[0]], od[key]):
            raise ValueError('CURRENT_M_ORIGINAL_ROW_METADATA_DRIFT:' + key)
    if float(c['constant']) != float(od['constant']):
        raise ValueError('CURRENT_M_ORIGINAL_OBJECTIVE_CONSTANT_DRIFT')
    parsed = {}
    for j, name in enumerate(od['names']):
        match = re.fullmatch(r'arc\[([^,]+),(\d+)\]', str(name))
        if match:
            parsed[match[1], int(match[2])] = j
        elif c['names'][j] != name or c['types'][j] != od['types'][j]:
            raise ValueError('CURRENT_M_NONROUTE_DOMAIN_DRIFT')
    if parsed != compact.arc_columns:
        raise ValueError('CURRENT_M_ORIGINAL_ROUTE_AXIS_INCOMPLETE')
    endpoint_groups = defaultdict(list)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for k, arc in enumerate(compact.arcs):
        if not 0 <= arc[1] < arc[3] <= compact.H:
            raise ValueError('CURRENT_M_NONACYCLIC_ROUTE')
        endpoint_groups[tuple(arc[:4])].append(k)
    parallel = {k for group in endpoint_groups.values() if len(group) > 1 for k in group}
    for (unit, k), j in parsed.items():
        s, t, dest, end = compact.arcs[k][:4]
        outgoing[unit, s, t].append(j); incoming[unit, dest, end].append(j)
        if (od['types'][j] != 'B' or od['lower'][j] != 0 or od['upper'][j] != 1
                or c['names'][j] != f'route_flow[{unit},{k}]'
                or c['types'][j] != ('B' if k in parallel else 'C')):
            raise ValueError('CURRENT_M_ROUTE_REPRESENTATION_DRIFT')
    flow_rows=[i for i,name in enumerate(od['row_names']) if str(name).split('[',1)[0]=='flow']
    terminal_rows=[i for i,name in enumerate(od['row_names']) if str(name).split('[',1)[0]=='terminal_location']
    graph_sites=sorted({arc[0] for arc in compact.arcs}|{arc[2] for arc in compact.arcs})
    # Use the source constructor's original site order, recovered from the
    # first contiguous stay-arc block rather than an alphabetic assumption.
    graph_sites=list(dict.fromkeys(arc[0] for arc in compact.arcs if arc[-1] is None))
    cursor=0
    for unit,origin in sorted(compact.initial.items()):
        for site in graph_sites:
            for t in range(compact.H):
                expected=defaultdict(float)
                for j in outgoing[unit,site,t]: expected[j]+=1.
                for j in incoming[unit,site,t]: expected[j]-=1.
                if cursor>=len(flow_rows): raise ValueError('CURRENT_M_FLOW_ROW_COVER_INCOMPLETE')
                i=flow_rows[cursor];cursor+=1;a,b=original.indptr[i:i+2]
                actual=dict(zip(map(int,original.indices[a:b]),map(float,original.data[a:b])))
                if (actual!={j:w for j,w in expected.items() if w} or od['sense'][i]!='='
                        or od['rhs'][i]!=int(t==0 and site==origin)):
                    raise ValueError('CURRENT_M_ORIGINAL_GRAPH_FLOW_DRIFT')
    if cursor!=len(flow_rows) or len(terminal_rows)!=len(compact.initial):
        raise ValueError('CURRENT_M_FLOW_OR_TERMINAL_COVER_DRIFT')
    for index,unit in enumerate(sorted(compact.initial)):
        expected={j:1. for (u,k),j in parsed.items() if u==unit and compact.arcs[k][3]==compact.H}
        i=terminal_rows[index];a,b=original.indptr[i:i+2]
        if (dict(zip(map(int,original.indices[a:b]),map(float,original.data[a:b])))!=expected
                or od['rhs'][i]!=1 or od['sense'][i]!='='):
            raise ValueError('CURRENT_M_ORIGINAL_TERMINAL_FLOW_DRIFT')
    for offset, key in enumerate(compact.nodes):
        unit, site, t = key; j = n + offset
        expected = {j: 1.}
        for k in incoming[key] if t == compact.H else outgoing[key]:
            expected[k] = -1.
        i = original.shape[0] + offset; a, b = C.indptr[i:i+2]
        if (dict(zip(map(int, C.indices[a:b]), map(float, C.data[a:b]))) != expected
                or c['rhs'][i] != 0 or c['sense'][i] != '='
                or c['names'][j] != f'node_activity[{unit},{site},{t}]'
                or c['types'][j] != 'B' or c['lower'][j] != 0 or c['upper'][j] != 1):
            raise ValueError('CURRENT_M_NODE_ACTIVITY_LINK_DRIFT')
    # The unchanged native flow rows, nonnegative route box and strict forward
    # time DAG imply a single unit path; binary nodes give integral nonparallel
    # arcs, while parallel selectors remain binary in the existing constructor.
    definitions = {}; alias_witnesses = {}; columns_for_witness = None
    for step in presolve.steps:
        j = int(step['column'])
        if j in definitions:
            raise ValueError('CURRENT_M_ALIAS_DUPLICATE')
        i = step['defining_row']
        if i is None:
            if c['lower'][j] != c['upper'][j] or step['terms'] or step['constant'] != c['lower'][j]:
                raise ValueError('CURRENT_M_BOUND_FIX_NOT_ORIGINAL')
        else:
            terms, rhs = _project_row(C, c['rhs'], int(i), definitions)
            pivot = terms.pop(j, F(0))
            expected = {int(k): F(float(w)) for k, w in step['terms'].items() if w}
            direct = not (str(c['sense'][i]) != '=' or not pivot
                    or {k: -w/pivot for k, w in terms.items()} != expected
                    or rhs/pivot != F(float(step['constant'])))
            if not direct:
                # The existing producer also emits j=k for two identical
                # affine bindings. Its defining_row is j's binding, so the
                # independent proof must subtract k's original binding too.
                witness = None
                if (str(c['sense'][i])=='=' and pivot and step['kind']=='DUPLICATE_AUXILIARY'
                        and step['constant']==0 and len(expected)==1 and next(iter(expected.values()))==1):
                    k=next(iter(expected))
                    if columns_for_witness is None: columns_for_witness=C.tocsc()
                    a,b=columns_for_witness.indptr[k:k+2]
                    family=str(c['names'][k]).split('[',1)[0]+'_binding'
                    for candidate in columns_for_witness.indices[a:b]:
                        candidate=int(candidate)
                        if candidate==i or c['sense'][candidate]!='=' or str(c['row_names'][candidate]).split('[',1)[0]!=family: continue
                        other,value=_project_row(C,c['rhs'],candidate,definitions)
                        other_pivot=other.get(k,F(0))
                        if not other_pivot: continue
                        difference=defaultdict(F,{j:F(1)})
                        for q,w in terms.items(): difference[q]+=w/pivot
                        for q,w in other.items(): difference[q]-=w/other_pivot
                        difference={q:w for q,w in difference.items() if w}
                        if difference=={j:F(1),k:F(-1)} and rhs/pivot==value/other_pivot:
                            witness=candidate;break
                if witness is None:
                    error=ValueError('CURRENT_M_EXACT_ELIMINATION_EQUATION_DRIFT')
                    error.transport_diagnostic=dict(step=step,original_row=int(i),original_row_name=str(c['row_names'][i]),
                        pivot=str(pivot), exact_required_constant=str(rhs/pivot) if pivot else None,
                        actual_constant=str(F(float(step['constant']))),
                        exact_required_terms={str(k):str(-w/pivot) for k,w in terms.items()} if pivot else {},
                        actual_terms={str(k):str(w) for k,w in expected.items()},
                        exact_affine_duplicate_witness_not_found=True)
                    raise error
                alias_witnesses[int(i)]=witness
        definitions[j] = step
    keep = np.asarray(presolve.col_ids, dtype=np.int64)
    positions = {int(j): k for k, j in enumerate(keep)}
    if set(definitions) | set(positions) != set(range(C.shape[1])) or set(definitions) & set(positions):
        raise ValueError('CURRENT_M_INVERSE_COLUMN_COVER_DRIFT')
    # This existing presolve accepts only fixed values and unit aliases. Verify
    # each original bound is implied by the final retained original box.
    transformed = {}
    def expand(j, stack=()):
        if j in transformed:
            return transformed[j]
        if j in stack:
            raise ValueError('CURRENT_M_INVERSE_CYCLE')
        if j in positions:
            result = (F(0), {positions[j]: F(1)})
        else:
            step = definitions[j]; const = F(float(step['constant'])); terms = defaultdict(F)
            for key, weight in step['terms'].items():
                if F(float(weight)) != 1:
                    raise ValueError('CURRENT_M_UNPROVEN_NONUNIT_ALIAS')
                off, deps = expand(int(key), stack+(j,)); const += off
                for k, v in deps.items(): terms[k] += v
            result = (const, {k: v for k, v in terms.items() if v})
        transformed[j] = result
        return result
    rr, cc, vv = [], [], []; off = np.zeros(C.shape[1])
    for j in range(C.shape[1]):
        const, terms = expand(j); off[j] = float(const)
        minimum = maximum = const
        for k, weight in terms.items():
            minimum = _sum_bound(minimum,_scaled_bound(weight,presolve.d['lower'][k] if weight>0 else presolve.d['upper'][k]))
            maximum = _sum_bound(maximum,_scaled_bound(weight,presolve.d['upper'][k] if weight>0 else presolve.d['lower'][k]))
            rr.append(j); cc.append(k); vv.append(float(weight))
        if minimum < _bound(c['lower'][j]) or maximum > _bound(c['upper'][j]):
            raise ValueError('CURRENT_M_ELIMINATED_ORIGINAL_BOUND_NOT_IMPLIED')
        if c['types'][j] == 'B' and any(presolve.d['types'][k] != 'B' or weight.denominator != 1 for k, weight in terms.items()):
            raise ValueError('CURRENT_M_ELIMINATED_BINARY_DOMAIN_NOT_IMPLIED')
    T = sparse.csr_matrix((vv, (rr, cc)), shape=(C.shape[1], len(keep)))
    projected = (C @ T).tocsr(); projected.eliminate_zeros(); projected.sort_indices()
    rhs = c['rhs'] - C @ off
    kept_rows = np.asarray(presolve.row_ids, dtype=np.int64)
    B, d = presolve.A.tocsr(), presolve.d
    for key in ('names','types'):
        if not np.array_equal(c[key][keep],d[key]):
            raise ValueError('CURRENT_M_RETAINED_COLUMN_AXIS_DRIFT:'+key)
    bound_proofs={int(row['column']):row for row in presolve.bound}
    for k,j in enumerate(keep):
        if d['lower'][k]==c['lower'][j] and d['upper'][k]==c['upper'][j]: continue
        proof=bound_proofs.get(int(j))
        if proof is None or not proof['proof'].startswith('SINGLETON_EQUALITY:'):
            raise ValueError('CURRENT_M_RETAINED_BOUND_PROOF_MISSING')
        i=int(proof['proof'].split(':',1)[1]);terms,value=_project_row(C,c['rhs'],i,definitions)
        if (c['sense'][i]!='=' or set(terms)!={int(j)}
                or value/terms[int(j)]!=F(float(d['lower'][k]))
                or d['lower'][k]!=d['upper'][k]):
            raise ValueError('CURRENT_M_RETAINED_BOUND_NOT_EXACTLY_IMPLIED')
    if not np.array_equal(c['sense'][kept_rows], d['sense']) or not np.array_equal(c['row_names'][kept_rows], d['row_names']):
        raise ValueError('CURRENT_M_RETAINED_ROW_AXIS_DRIFT')
    # Exact rational fallback addresses only a sparse summation-order mismatch;
    # it never grants a numerical tolerance to scientific coefficients.
    delta = projected[kept_rows]-B; delta.eliminate_zeros()
    affected = set(map(int, np.unique(delta.tocoo().row))) | set(map(int, np.flatnonzero(rhs[kept_rows] != d['rhs'])))
    for row in affected:
        terms, value = _project_row(C, c['rhs'], int(kept_rows[row]), definitions)
        expected = {positions[j]: w for j, w in terms.items()}
        a, b = B.indptr[row:row+2]
        actual = {int(j): F(float(w)) for j, w in zip(B.indices[a:b], B.data[a:b])}
        if expected != actual or value != F(float(d['rhs'][row])):
            raise ValueError('CURRENT_M_EXACT_RETAINED_COEFFICIENT_DRIFT')
    objective = defaultdict(F); constant = F(float(c['constant']))
    for j in np.flatnonzero(c['objective']):
        const, terms = transformed[int(j)]; weight = F(float(c['objective'][j])); constant += weight*const
        for k, w in terms.items(): objective[k] += weight*w
    if constant != F(float(d['constant'])) or any(objective.get(j, F(0)) != F(float(d['objective'][j])) for j in range(len(keep))):
        raise ValueError('CURRENT_M_EXACT_OBJECTIVE_TRANSPORT_DRIFT')
    certs = {int(row['row']): row for row in presolve.rows}
    if set(certs) != set(range(C.shape[0]))-set(map(int, kept_rows)):
        raise ValueError('CURRENT_M_DELETED_ROW_CERTIFICATE_COVER_DRIFT')
    proven=set(map(int,kept_rows))
    def prove_deleted(i, stack=()):
        if i in proven:return
        if i in stack:raise ValueError('CURRENT_M_DELETED_ROW_IMPLICATION_CYCLE')
        cert=certs[i]
        terms, value = _project_row(C, c['rhs'], i, definitions); sense = str(c['sense'][i])
        if cert['kind']=='ELIMINATED_DEFINITION' and not terms and value==0:
            proven.add(i);return
        if cert['kind'] == 'EXACT_PROPORTIONAL_IMPLICATION' or (cert['kind']=='ELIMINATED_DEFINITION' and i in alias_witnesses):
            representative=int(cert['representative']) if cert['kind']=='EXACT_PROPORTIONAL_IMPLICATION' else alias_witnesses[i]
            other, bound = _project_row(C, c['rhs'], representative, definitions)
            if sense=='>': terms={j:-w for j,w in terms.items()};value=-value
            other_sense=str(c['sense'][representative])
            if other_sense=='>': other={j:-w for j,w in other.items()};bound=-bound
            if (sense=='=')!=(other_sense=='='):
                raise ValueError('CURRENT_M_PROPORTIONAL_ROW_SENSE_DRIFT')
            if not terms and not other:
                valid = value == bound if sense == '=' else value >= bound
            else:
                if set(terms) != set(other): raise ValueError('CURRENT_M_PROPORTIONAL_ROW_SUPPORT_DRIFT')
                key = next(iter(terms)); scale = terms[key]/other[key]
                valid = all(terms[j] == scale*other[j] for j in terms)
                valid = valid and (value == scale*bound if sense == '=' else scale > 0 and
                    value >= scale*bound)
            if not valid: raise ValueError('CURRENT_M_PROPORTIONAL_ROW_IMPLICATION_DRIFT')
            prove_deleted(representative,stack+(i,))
        else:
            minimum = maximum = F(0)
            for j, weight in terms.items():
                k = positions[j]
                minimum = _sum_bound(minimum,_scaled_bound(weight,d['lower'][k] if weight>0 else d['upper'][k]))
                maximum = _sum_bound(maximum,_scaled_bound(weight,d['upper'][k] if weight>0 else d['lower'][k]))
            valid = minimum == maximum == value if sense == '=' else maximum <= value if sense == '<' else minimum >= value
            if not valid: raise ValueError('CURRENT_M_DELETED_ROW_NOT_EXACTLY_IMPLIED')
        proven.add(i)
    for i in certs:prove_deleted(i)
    return dict(PASS=True, original_rows=original.shape[0], original_columns=n,
        compact_rows=C.shape[0], compact_columns=C.shape[1], retained_rows=B.shape[0],
        retained_columns=B.shape[1], exact_aliases_checked=len(definitions),
        exact_identical_affine_binding_witnesses_checked=len(alias_witnesses),
        deleted_row_implications_checked=len(certs), exact_coefficient_fallback_rows=len(affected),
        original_P1_bit_exact=True, integer_and_full_LP_domains_identical=True,
        C3A_policy='KEEP_ALL_REGENERATED_C2_ROWS', historical_proof_packets_read=0,
        Native_optimize_calls=0)


def _label_grid(model, first, coefficients, cost):
    """Supply time/branch/face row identities without changing a coefficient."""
    # all_transformer_rows queues native Gurobi attribute renames and appended
    # omitted NormalAmps rows. Materialize those names before reading them.
    model.update()
    rows = model.getConstrs(); cursor = first
    selected = {(r['slot'], r['family'], r['index']): r['selected'] for r in cost}
    def label(base, axis, current=False):
        nonlocal cursor
        row = rows[cursor]; cursor += 1
        if current:
            if not row.ConstrName.startswith('NormalAmps['): raise ValueError('CURRENT_M_CURRENT_ROW_ORDER_DRIFT')
        else:
            if row.ConstrName != base: raise ValueError('CURRENT_M_GRID_ROW_ORDER_DRIFT:'+base)
            row.ConstrName = base+'['+','.join(map(str, axis))+']'
    for t, c in enumerate(coefficients):
        for k in range(len(c.voltage_constant)):
            label('voltage_lower', (t,k)); label('voltage_upper', (t,k))
        for k, name in enumerate(c.branch_names):
            dominated = re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]', name.lower()) is not None
            if not dominated:
                if name.lower().startswith('transformer.'): label('transformer_current', (t,k), current=True)
                else:
                    if selected[t,'line',k]:
                        for base in ('response_line_P_binding','response_line_Q_binding','response_line_correction_binding'): label(base,(t,k))
                    for f in range(16): label('line_thermal_face',(t,k,f))
            if c.transformer_ratings[k] is not None:
                if selected[t,'transformer_kVA',k]:
                    for base in ('response_transformer_P_binding','response_transformer_Q_binding'): label(base,(t,k))
                for f in range(16): label('transformer_kVA',(t,k,f))
    model.update()


def build_case(payload, request, progress=None):
    import gurobipy as gp
    from v42_bootstrap.m1 import native_inputs
    import v42_native.mess as native
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage, voltage_for, authority_sha
    from v42_integrated.contract import physical_authority, all_transformer_rows
    from v42_m1_sparse.grid import response, add_compressed
    from v42_pr134_b1.native import original_coefficients_for_day
    import v42_may01.prepare as original
    from v42_temporal.native import load_power
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    day=request['day']; out=Path(request['output']).resolve(); out.mkdir(parents=True,exist_ok=True)
    if out.drive.upper()!='D:': raise ValueError('CURRENT_M_D_OUTPUT_REQUIRED')
    bundle=payload['bundle']; planning=payload['planning']
    if bundle['day']!=day or payload['identity']['day']!=day: raise ValueError('CURRENT_M_SAME_DAY_INPUT_REQUIRED')
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
           [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    cert,_,_,_=load_power(bundle); coeff=original_coefficients_for_day(original,cert,day)
    if len(coeff)!=96 or any(c.slot!=t for t,c in enumerate(coeff)): raise ValueError('CURRENT_M_96_COEFFICIENT_AXIS_REQUIRED')
    pcc=np.asarray(planning['PCC_P_kw'],dtype=float); aidc_sites=list(map(str,planning['sites']))
    if pcc.shape!=(96,12) or len(set(aidc_sites))!=12 or set(aidc_sites)!=set(bundle['capacities']) or not np.isfinite(pcc).all():
        raise ValueError('CURRENT_M_INDEPENDENT_AIDC_PCC_AXIS_REQUIRED')
    columns=list(coeff[0].control_names); controls=[]
    for t,c in enumerate(coeff):
        if list(c.control_names)!=columns: raise ValueError('CURRENT_M_CONTROL_AXIS_DRIFT')
        row=[]
        for name in columns:
            site=name.split('[',1)[1][:-1]
            if name.startswith('aidc_load_kw'): row.append(float(pcc[t,aidc_sites.index(site)]))
            elif name.startswith(('mess_p_kw','mess_q_kvar')): row.append(0.)
            else: raise ValueError('CURRENT_M_UNKNOWN_CONTROL')
        controls.append(row)
    captured=[]; bindings=[]; cost=[]; thermal=[]; binding_families=set()
    anchor=dict(day=day,controls=controls,control_names=columns,
        fixed_AIDC_control_columns=[i for i,n in enumerate(columns) if n.startswith('aidc_load_kw')],
        independent_AIDC_identity=payload['identity'])
    class ConstructionDeadline:
        stage='M1'
        sampled=0.
        def check(self):
            budget=request.get('_budget')
            if budget is not None:
                budget.check()
            if progress and time.perf_counter()-self.sampled>=1:
                self.sampled=time.perf_counter();progress(dict(phase='M_ORIGINAL_MODEL_BUILD',day=day,arm='B2'))
    def grid(model,p,q):
        pp={key:response(model,f'injection_P[{key[0]},{key[1]}]',v,bindings) for key,v in p.items()}
        qq={key:response(model,f'injection_Q[{key[0]},{key[1]}]',v,bindings) for key,v in q.items()}
        actual=[]
        for t,c in enumerate(coeff):
            row=[]
            for i,name in enumerate(c.control_names):
                site=name.split('[',1)[1][:-1]
                row.append(controls[t][i] if name.startswith('aidc_load_kw') else pp[site,t] if name.startswith('mess_p_kw') else qq[site,t])
            actual.append(row)
        voltage=voltage_for(Stage.M1)
        ga=GridAuthority(cert['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
            digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),voltage.lower_squared,voltage.upper_squared,
            True,stage=Stage.M1,transformer_current_authority_sha256=coeff[0].transformer_current_authority_sha256)
        model.update();first=model.NumConstrs
        builder=lambda m,c,x,a:add_compressed(m,c,x,a,'M1-F3',bindings,cost)
        rho=all_transformer_rows(builder,thermal)(model,coeff,actual,ga)
        _label_grid(model,first,coeff,cost)
        return [('rho',rho),('reserve_shortfall',0.)]
    def capture(model,objectives,deadline,*args,**kwargs):
        if [n for n,_ in objectives]!=['rho','reserve_shortfall','movement_kwh','movement_count','tie']:
            raise ValueError('CURRENT_M_ORIGINAL_OBJECTIVE_INTERFACE_DRIFT')
        model.setObjective(objectives[0][1],gp.GRB.MINIMIZE);model.update()
        binding_families.update(v.VarName.split('[',1)[0] for v,_ in bindings)
        captured.append(model.copy())
        return None,dict(Native_optimize_calls=0,P1_only=True,P2_calls=0)
    with physical_authority():
        anchor['voltage_authority_sha256']=authority_sha(Stage.A1)
        with patch.object(native,'optimize',capture):
            native.solve('M1',ConstructionDeadline(),sites,initial,routes,battery,96,grid)
    model=captured[0]
    try: A,d=arrays(model)
    finally: model.dispose()
    families={str(n).split('[',1)[0] for n in d['names']}
    if not families <= {'arc','charge_mode','Pch','Pdis','Q','SOC','rho_max'}|binding_families:
        raise ValueError('CURRENT_M_AIDC_OPTIMIZATION_VARIABLE_PRESENT')
    from v42_svr11.authority import active
    if len(thermal)!=(153 if active() is not None else 120)*96: raise ValueError('CURRENT_M_ALL_TRANSFORMER_PHASE_ROWS_REQUIRED')
    if progress: progress(dict(phase='M_EXISTING_COMPACT_STATIC_PRESOLVE',day=day,arm='B2'))
    compact=Compact(A,d,graph[2],initial,96)
    presolve=Presolve(compact.A,compact.d);B,e=presolve.run()
    try:
        proof=verify_transport(compact,presolve)
    except Exception as error:
        # Preserve the exact producer objects before any new case is rebuilt.
        # This is a diagnostic representation, never a point/bound/start input.
        diagnostic=out/'TRANSPORT_DIAGNOSTIC_STATE.pkl'
        with diagnostic.open('wb') as stream:
            pickle.dump(dict(compact=compact,presolve=presolve),stream,pickle.HIGHEST_PROTOCOL)
        atomic(out/'TRANSPORT_FAILURE_DIAGNOSTIC.json',dict(PASS=False,error=str(error),day=day,
            Native_optimize_calls=0,details=getattr(error,'transport_diagnostic',{}),state=record(diagnostic)))
        raise
    transport_authority=_freeze_transport(compact,presolve,graph,proof,out)
    identity=dict(schema='V42_CURRENT_DATE_B2_M_CASE_V1',day=day,arm='B2',input_identity=payload['identity'],
        bundle_sha=digest(bundle),anchor_sha=digest(anchor),route_table_sha=bundle['route_table']['sha256'],
        original_matrix_sha=matrix_sha(A),original_domain_sha=_domain_sha(d),
        selected_matrix_sha=matrix_sha(B),selected_domain_sha=_domain_sha(e),
        binary_count=int(np.count_nonzero(e['types']=='B')),slots=96,units=4,sites=24,
        objective='min rho_max',C3A_policy='KEEP_ALL_REGENERATED_C2_ROWS',transport=proof,transport_authority=transport_authority,
        AIDC_optimization_calls=0,P2_calls=0,historical_bounds_points_columns_read=0)
    case=CampaignMCase(B,e,A,d,None,graph,digest(identity),identity,compact,presolve,bundle,anchor,planning,coeff,out)
    sparse.save_npz(out/'FULL_A.npz',A);np.savez_compressed(out/'FULL_DATA.npz',**d)
    sparse.save_npz(out/'C3A_A.npz',B);np.savez_compressed(out/'C3A_DATA.npz',**e)
    np.savez_compressed(out/'CURRENT_C2_AXES.npz',rows=presolve.row_ids,columns=presolve.col_ids)
    atomic(out/'CURRENT_C2_ALIASES.json',presolve.steps);atomic(out/'CURRENT_C2_ROW_PROOFS.json',presolve.rows)
    atomic(out/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**identity))
    atomic(out/'FIXED_AIDC_ANCHOR.json',anchor)
    atomic(out/'INPUT_AND_SOURCE_IDENTITY.json',dict(day=day,case_sha=case.case_sha,input_identity=payload['identity'],
        route_table=record(bundle['route_table']['path']),electrical_certificate=record(bundle['electrical_certificate']['path'])))
    return case


def verify_case(case):
    if matrix_sha(case.original_A)!=case.identity['original_matrix_sha'] or _domain_sha(case.original_d)!=case.identity['original_domain_sha']:
        raise ValueError('CURRENT_M_ORIGINAL_CASE_BYTES_DRIFT')
    if matrix_sha(case.A)!=case.identity['selected_matrix_sha'] or _domain_sha(case.d)!=case.identity['selected_domain_sha']:
        raise ValueError('CURRENT_M_SELECTED_CASE_BYTES_DRIFT')
    if digest(case.identity)!=case.case_sha or digest(case.bundle)!=case.identity['bundle_sha'] or digest(case.anchor)!=case.identity['anchor_sha']:
        raise ValueError('CURRENT_M_CASE_BINDING_DRIFT')
    authority=case.identity.get('transport_authority')
    if authority is None:return verify_transport(case.compact,case.presolve)
    if authority['state_sha']!=_transport_state_sha(case.compact,case.presolve,case.graph):
        raise ValueError('CURRENT_M_TRANSPORT_STATE_BYTES_DRIFT')
    root=Path(__file__).resolve().parents[1]
    expected_sources={'v42_may_campaign/m_model.py','v42_supercompact/formulation.py','v42_supercompact/presolve.py'}
    if set(authority['sources'])!=expected_sources or any(sha(root/name)!=receipt['sha256'] for name,receipt in authority['sources'].items()):
        raise ValueError('CURRENT_M_TRANSPORT_PROOF_SOURCE_DRIFT')
    receipt=authority['certificate']; path=Path(receipt['path'])
    if (path.resolve()!=(case.output/'ORIGINAL_DOMAIN_EQUIVALENCE.json').resolve()
            or sha(path)!=receipt['sha256'] or read(path)!=case.identity['transport']
            or case.identity['transport'].get('PASS') is not True):
        raise ValueError('CURRENT_M_TRANSPORT_PROOF_PACKET_DRIFT')
    return dict(case.identity['transport'],proof_reused_after_all_transport_state_SHA_checks=True,
        same_case_transport_certificate=receipt)
