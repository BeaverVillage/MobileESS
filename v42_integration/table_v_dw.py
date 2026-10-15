"""Route the PR191 A-source Phase I/P1 producers to the current D0 FULL model.

No pricing or optimization algorithm lives here. The source bridge's original
canary phase loop, complete local producer, exact projection and rational pricing
certificates are reused. A fresh FULL integer model remains the UB authority.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import pickle
from time import perf_counter

import numpy as np

from .a_engine import digest
from .m_engine import _write, file_record, vector_sha
from .table_v_gap_contract import AIDC_GLOBAL_GAP_TARGET


def objective_identity(model):
    """A separate objective receipt; the legacy domain SHA also includes it."""
    return digest(dict(coefficients=list(map(float, model.getAttr('Obj'))),
        constant=float(model.ObjCon), sense=int(model.ModelSense)))


def _freeze_sources(output):
    root=Path(__file__).resolve().parents[1]
    paths=('v42_integration/table_v_dw.py','v42_integration/table_v_a.py',
        'v42_b3_joint/a_source.py','v42_a_stage_canary/phase.py','v42_a_stage_canary/pricing.py',
        'v42_a_stage_canary/targeted.py','v42_a_stage_phase1/producer.py','v42_a_stage_phase1/backend.py',
        'v42_a_stage_phase1/core.py','v42_a_stage_phase1/oracle.py',
        'v42_a_stage_compact_rowgen/assembly.py','v42_a_stage_compact_rowgen/equivalence.py',
        'v42_may_build_v6/construction.py','v42_may_build_v6/compact_build.py',
        'v42_root/native.py','v42_root/factor.py','v42_a_stage_domain_v2/runtime_projection.py',
        'v42_integration/table_v_geometry_cache.py','v42_integration/table_v_compression.py',
        'v42_integration/table_v_compression_verify.py','v42_integration/table_v_compression_adapter.py',
        'v42_integration/table_v_phase_policy.py','v42_integration/table_v_phase_diagnostics.py',
        'v42_integration/table_v_global_control.py','v42_integration/pcc_definitions.py')
    records=[file_record(root/path) for path in paths]
    _write(Path(output)/'DW_SOURCE_FREEZE.json',dict(PASS=True,sources=records,Native_calls=0))
    return records


def _prepare_progress(output,phase,**values):
    """Thread-free Native0 diagnostics; no asynchronous Python stack walker."""
    try:
        import psutil
        values['RSS_bytes']=psutil.Process().memory_info().rss
        values['available_RAM_bytes']=psutil.virtual_memory().available
    except (ImportError,OSError): pass
    _write(Path(output)/'NATIVE0_PREPARATION_PROGRESS.json',dict(phase=phase,Native_calls=0,**values))
    print('TABLE_V_DW_NATIVE0',phase,flush=True)


def _checked_cache(receipt):
    if file_record(receipt['path'])!=receipt: raise ValueError('TABLE_V_DW_NATIVE0_CHECKPOINT_BYTE_DRIFT')
    with gzip.open(receipt['path'],'rb') as stream:return pickle.load(stream)


def audit_source_domain(context):
    """Reissue original E1 receipts from public records, independently of windows.

    The epoch-to-native conversion is explicitly D0 + 24 slots. Past legal E1
    slots do not become new-start permissions after D0. No model or solver runs.
    """
    from .actual_validation import load_stats
    from .experimental_qos import ExperimentalQoSProvider
    from .qos import QoSWindowProvider
    from .table_v_flex_planning import (compile_public_reference, public_e1_records,
        OFFSET, SLOT, H, require_flex_context)
    from .d0_a_planning import _canonical
    require_flex_context(context)
    state = context['state']; manifest = context['manifest']; flex = context['tablev_flex']
    stats = flex['strict_stats_record']
    if file_record(stats['path']) != stats:
        raise ValueError('TABLE_V_DW_ORIGINAL_STRICT_STATS_DRIFT')
    reference, _ = compile_public_reference(state)
    observed = public_e1_records(state, reference)
    strict = QoSWindowProvider(load_stats(stats['path']),
        case_sha=manifest['parent_basic_manifest']['identity']['case_sha'],
        provider_sha=state['provider_identifiers']['runtime_provider_sha'])
    provider = ExperimentalQoSProvider(strict, scenario='E1', participation='FLEX30',
        case_sha=manifest['identity']['case_sha'])
    initial = {r['uid']: r for key in ('running', 'pending') for r in state[key]}
    begin = state['begin_epoch_seconds']; rows = []
    for uid, job in observed.items():
        source_context = dict(verified_fields=[], source_sha=manifest['initial_record']['sha256'],
            observed_at_seconds=begin)
        provider.register_observed(uid, episode_id=initial[uid]['episode_id'], source_authority=source_context)
        issued = provider.issue(job)
        if asdict(job) != flex['known_observed_records'][uid]:
            raise ValueError('TABLE_V_DW_SOURCE_PUBLIC_RECORD_DRIFT:' + uid)
        if uid not in context['data'][1]:
            raw = context['data'][4].get(uid, {})
            if job.state != 'RUNNING' or raw.get('service_slots') != 0:
                raise ValueError('TABLE_V_DW_SOURCE_UID_MISSING:' + uid)
            continue
        actual = context['receipts'][uid].to_dict()
        if issued.to_dict() != actual:
            raise ValueError('TABLE_V_DW_SOURCE_E1_RECEIPT_DRIFT:' + uid)
        expected = ((OFFSET,) if job.state == 'RUNNING' else tuple(
            OFFSET + int((t-begin)/SLOT) for t in issued.allowed_starts_seconds if begin <= t < begin+86400))
        native = context['data'][1][uid]; boundary = context['data'][2][uid]
        eligible = issued.participant and issued.eligible_for_contract
        sites = tuple(initial[uid]['compatible_sites']) if job.state != 'RUNNING' or eligible else (initial[uid]['site'],)
        if (tuple(context['windows'][uid]) != expected or tuple(native.qos_allowed_starts) != expected
                or tuple(boundary.allowed_starts) != expected or tuple(native.initial_sites) != sites
                or native.checkpoint_authorized != eligible or native.qos_budget_seconds != issued.budget_seconds
                or not expected or any(t < OFFSET or t >= H for t in expected)):
            raise ValueError('TABLE_V_DW_SOURCE_START_SITE_CHECKPOINT_BUDGET_DRIFT:' + uid)
        source=initial[uid];remaining=(max(0.,source['q50']-source['elapsed_compute_seconds'])
            if job.state=='RUNNING' else source['q50'])
        if (native.gpu!=source['gpu'] or native.elapsed_seconds!=source['elapsed_compute_seconds']
                or native.service_slots!=math.ceil(remaining/SLOT)
                or job.state=='RUNNING' and native.reference_start!=OFFSET):
            raise ValueError('TABLE_V_DW_SOURCE_GPU_ELAPSED_FULL_SERVICE_DRIFT:'+uid)
        deadline = job.completion_deadline_seconds
        if deadline is not None and boundary.latest_completion > math.floor((deadline-(begin-OFFSET*SLOT))/SLOT):
            raise ValueError('TABLE_V_DW_SOURCE_HARD_DEADLINE_DRIFT:' + uid)
        rows.append(dict(uid=uid, state=job.state, allowed_starts=list(expected),
            participant=issued.participant, eligible=eligible, budget_seconds=issued.budget_seconds,
            initial_sites=list(sites), checkpoint=eligible, source_hard_contract=issued.hard_contract,
            service_slots=native.service_slots, boundary_sha=digest(asdict(boundary)),
            receipt_sha=digest(actual)))
    raw = context['data'][4]; resources = context['data'][3]
    holds = {u: r for u, r in raw.items() if r['state'] == 'RUNNING' and r['service_slots'] == 0}
    expected_fixed = Counter()
    for uid, row in holds.items():
        if uid not in initial or initial[uid]['site'] != row['planning_site']:
            raise ValueError('TABLE_V_DW_EXPIRED_RUNNING_PHYSICAL_HOLD_DRIFT')
        expected_fixed[row['planning_site'], OFFSET] += row['GPU_gang']
    if dict(expected_fixed) != resources.fixed_gpu or set(context['data'][1]) | set(holds) != set(initial):
        raise ValueError('TABLE_V_DW_RUNNING_OCCUPANCY_OR_COMPLETE_UID_ROSTER_DRIFT')
    return dict(PASS=True, independent_original_E1_reissue=True, scenario='E1', participation='FLEX30',
        native_calls=0, P2_calls=0, D0_epoch_seconds=begin, native_D0_slot=OFFSET,
        jobs=len(rows), PENDING_UIDs=sum(r['state']=='PENDING' for r in rows),
        PENDING_start_slots=sum(len(r['allowed_starts']) for r in rows if r['state']=='PENDING'),
        initial_RUNNING_UIDs=len(state['running']),RUNNING_service_UIDs=sum(r['state']=='RUNNING' for r in rows),
        expired_RUNNING_UIDs=len(holds), expired_RUNNING_GPU=sum(expected_fixed.values()),
        resources_sha=digest(_canonical(asdict(resources))), UID_domain_sha=digest(rows), UID_domains=rows)


def _column_permutation(original, reference, global_columns, columns):
    """Map identical original primitive expressions, using source unit IDs."""
    targets = {u['id']: u for u in reference['units']}
    if len(targets) != len(reference['units']):
        raise ValueError('TABLE_V_DW_DUPLICATE_UNIT_ID')
    mapping = dict(zip(range(global_columns), range(global_columns)))
    for unit in original['units']:
        target = targets[unit['id']]
        for family, items in unit['v'].items():
            for key, expression in items.items():
                other = target['v'][family][key]
                if expression[0] == 'v' and other[0] == 'v':
                    pairs = ((int(expression[1]), int(other[1])),)
                elif expression[0] == 'e' and other[0] == 'e':
                    if expression[1] != other[1] or not np.array_equal(expression[3], other[3]):
                        raise ValueError('TABLE_V_DW_PRIMITIVE_EXPRESSION_DRIFT')
                    pairs = zip(map(int, expression[2]), map(int, other[2]))
                elif expression[0] == 'c' and expression == other:
                    pairs = ()
                else:
                    raise ValueError('TABLE_V_DW_PRIMITIVE_ROLE_DRIFT')
                for before, after in pairs:
                    if before in mapping and mapping[before] != after:
                        raise ValueError('TABLE_V_DW_NONFUNCTIONAL_PRIMITIVE_MAPPING')
                    mapping[before] = after
    if set(mapping) != set(range(columns)) or len(set(mapping.values())) != columns:
        raise ValueError('TABLE_V_DW_INCOMPLETE_PRIMITIVE_BIJECTION')
    return np.asarray([mapping[j] for j in range(columns)], dtype=np.int64)


def _row_signatures(snapshot, permutation=None):
    """Exact binary64 coefficient equality; retain duplicates and hard empty rows."""
    counts = Counter(); matrix = snapshot.matrix
    for i in range(matrix.shape[0]):
        lo, hi = matrix.indptr[i:i+2]; js = matrix.indices[lo:hi]
        if permutation is not None: js = permutation[js]
        order = np.argsort(js, kind='stable')
        h = hashlib.sha256(str(snapshot.senses[i]).encode())
        h.update(np.float64(snapshot.rhs[i]).tobytes())
        h.update(np.asarray(js[order], dtype='<i8').tobytes())
        h.update(np.asarray(matrix.data[lo:hi][order], dtype='<f8').tobytes())
        counts[h.hexdigest()] += 1
    return counts


def verify_full_equivalence(base, descriptor, reference, reference_descriptor, global_columns):
    """Independent FULL-to-source reference equality, before any LB admission."""
    if base.matrix.shape != reference.matrix.shape:
        raise ValueError('TABLE_V_DW_ORIGINAL_FULL_ROW_COLUMN_AXIS_DRIFT')
    permutation = _column_permutation(descriptor, reference_descriptor, global_columns, base.matrix.shape[1])
    for field in ('lower', 'upper'):
        if not np.array_equal(getattr(base, field), getattr(reference, field)[permutation]):
            raise ValueError('TABLE_V_DW_ORIGINAL_FULL_BOX_DRIFT')
    before = base.objective('rho'); after = reference.objective('rho')
    if (before.constant != after.constant or {int(permutation[j]): c for j, c in before.coefficients().items()}
            != after.coefficients() or _row_signatures(base, permutation) != _row_signatures(reference)):
        raise ValueError('TABLE_V_DW_ORIGINAL_FULL_MATRIX_OBJECTIVE_DRIFT')
    return dict(PASS=True, original_FULL_integer_sha=base.fingerprint(),
        source_reference_LP_sha=reference.fingerprint(), primitive_permutation_sha=vector_sha(permutation),
        original_rows=base.matrix.shape[0], original_columns=base.matrix.shape[1],
        objective_unchanged=True, all_rows_boxes_coefficients_exact=True,
        only_integrality_relaxed=True)


def project_runtime_auxiliaries(model, base, bindings, descriptor, data):
    """Apply the existing runtime_projection.finish_count equality substitution.

    Verify each actual equality against its original class finish expressions.
    Exact rational expansion must remain representable in binary64; otherwise
    the bridge is rejected. No relaxation or approximate coefficient enters LB.
    """
    import gurobipy as gp
    import scipy.sparse as sp
    from collections import defaultdict
    from v42_a_stage_domain_v2.lexstage import Objective
    from v42_a_stage_domain_v2 import runtime_projection
    groups=defaultdict(list)
    for unit in descriptor['units']:
        for family in ('f0','f1'):
            if unit['optional'] and family=='f0': continue
            for (site,end),e in unit['v'][family].items():
                groups[unit['class_key'],site,end].append(e)
    substitutions={}; removed_rows=[];preserved_globals=[]
    equality_rows=(bindings['_runtime_equality_rows'] if model is None else
        [i for i,name in enumerate(model.getAttr('ConstrName')) if name=='exact_Runtime_finish_count'])
    by_aux={}
    for row in equality_rows:
        lo,hi=base.matrix.indptr[row:row+2]
        for j in base.matrix.indices[lo:hi]:
            by_aux.setdefault(int(j),[]).append(row)
    def expanded(expressions):
        terms=defaultdict(Fraction);constant=Fraction(0)
        for e in expressions:
            if e[0]=='v': terms[int(e[1])]+=1
            elif e[0]=='c': constant+=Fraction(float(e[1]))
            else:
                constant+=Fraction(float(e[1]))
                for j,a in zip(e[2],e[3]): terms[int(j)]+=Fraction(float(a))
        return {j:a for j,a in terms.items() if a},constant
    for key,value in bindings.get('Runtime_finish_counts',{}).items():
        if not isinstance(value,gp.Var) and not isinstance(value,int): continue
        j=value.index if isinstance(value,gp.Var) else value
        terms,constant=expanded(groups[key]);N=len(data[7]['classes'][key[0]])
        if base.lower[j]!=0 or base.upper[j]!=N or any(c<0 for c in terms.values()) or constant<0:
            raise ValueError('TABLE_V_DW_RUNTIME_FINISH_BOUND_PROOF_OBSTRUCTION')
        if any(base.lower[k]<0 for k in terms) or j in terms:
            raise ValueError('TABLE_V_DW_RUNTIME_FINISH_NONNEGATIVE_SOURCE_REQUIRED')
        rows=by_aux.get(j,[])
        if len(rows)!=1: raise ValueError('TABLE_V_DW_RUNTIME_UNIQUE_EQUALITY_REQUIRED')
        row=rows[0];lo,hi=base.matrix.indptr[row:row+2]
        actual={int(k):Fraction(float(a)) for k,a in zip(base.matrix.indices[lo:hi],base.matrix.data[lo:hi])}
        wanted={k:-a for k,a in terms.items()};wanted[j]=Fraction(1)
        if base.senses[row]!='=' or actual!=wanted or Fraction(float(base.rhs[row]))!=constant:
            raise ValueError('TABLE_V_DW_RUNTIME_ORIGINAL_FINISH_EQUALITY_DRIFT')
        if not terms:
            # The original x=constant equality remains. Substitution here can
            # round a fixed finish's binary64 Runtime RHS, so preserve x and
            # move it into the global prefix without changing any coefficient.
            preserved_globals.append(j)
        elif constant:
            raise ValueError('TABLE_V_DW_RUNTIME_MIXED_CONSTANT_PROJECTION_UNSUPPORTED')
        else:
            substitutions[j]=(terms,constant);removed_rows.append(row)
    if len(removed_rows)+len(preserved_globals)!=len(equality_rows):
        raise ValueError('TABLE_V_DW_RUNTIME_UNOWNED_EQUALITY')
    if not substitutions and not preserved_globals:
        return base,descriptor,dict(PASS=True,eliminated_auxiliaries=0,exact=True)
    owned={int(e[1]) for u in descriptor['units'] for items in u['v'].values() for e in items.values() if e[0]=='v'}
    owned.update(int(j) for u in descriptor['units'] for items in u['v'].values() for e in items.values() if e[0]=='e' for j in e[2])
    prefix=min(owned)
    keep=list(range(prefix))+sorted(preserved_globals)+[
        j for j in range(prefix,base.matrix.shape[1]) if j not in substitutions and j not in preserved_globals]
    remap={j:i for i,j in enumerate(keep)}; removed=set(removed_rows)
    original_rows=[i for i in range(base.matrix.shape[0]) if i not in removed]
    rowmap={row:i for i,row in enumerate(original_rows)}
    rr=list(keep);cc=list(range(len(keep)));vv=[1.]*len(keep)
    affected=set()
    csc=base.matrix.tocsc()
    for j,(terms,constant) in substitutions.items():
        for k,a in terms.items():rr.append(j);cc.append(remap[k]);vv.append(float(a))
        affected.update(map(int,csc.indices[csc.indptr[j]:csc.indptr[j+1]]))
    transform=sp.csr_matrix((vv,(rr,cc)),shape=(base.matrix.shape[1],len(keep)))
    matrix=(base.matrix[original_rows]@transform).tocsr();matrix.sum_duplicates();matrix.sort_indices();matrix.eliminate_zeros()
    rhs=base.rhs[original_rows].copy()
    for row in sorted(affected-removed):
        lo,hi=base.matrix.indptr[row:row+2];terms=defaultdict(Fraction);constant=Fraction(0)
        for j,a in zip(base.matrix.indices[lo:hi],base.matrix.data[lo:hi]):
            j=int(j);a=Fraction(float(a))
            if j in substitutions:
                inner,b=substitutions[j];constant+=a*b
                for k,v in inner.items(): terms[k]+=a*v
            else: terms[j]+=a
        expected={}
        for j,a in sorted(terms.items()):
            if not a: continue
            if Fraction(float(a))!=a: raise ValueError('TABLE_V_DW_RUNTIME_NONEXACT_BINARY64_COEFFICIENT')
            expected[remap[j]]=float(a)
        target=rowmap[row];a,b=matrix.indptr[target:target+2]
        if dict(zip(map(int,matrix.indices[a:b]),matrix.data[a:b]))!=expected:
            raise ValueError('TABLE_V_DW_RUNTIME_SPARSE_SUBSTITUTION_ROUNDING')
        right=Fraction(float(base.rhs[row]))-constant
        if Fraction(float(right))!=right: raise ValueError('TABLE_V_DW_RUNTIME_NONEXACT_BINARY64_RHS')
        rhs[target]=float(right)
    objectives=[]
    for objective in base.objectives:
        if any(j in substitutions for j in objective.coefficients()):
            raise ValueError('TABLE_V_DW_RUNTIME_AUXILIARY_IN_ORIGINAL_OBJECTIVE')
        objectives.append(Objective(objective.name,tuple((remap[j],a) for j,a in objective.coefficients().items()),objective.constant))
    projected=replace(base,matrix=matrix,
        lower=base.lower[keep],upper=base.upper[keep],vtypes=base.vtypes[keep],
        senses=base.senses[original_rows],rhs=np.asarray(rhs),objectives=tuple(objectives)).require()
    def shift(e):
        if e[0]=='v': return ('v',remap[int(e[1])])
        if e[0]=='e': return ('e',e[1],np.asarray([remap[int(j)] for j in e[2]]),e[3])
        return e
    translated=dict(descriptor,units=[dict(u,v={f:{key:shift(e) for key,e in items.items()}
        for f,items in u['v'].items()}) for u in descriptor['units']],
        known={key:shift(e) for key,e in descriptor['known'].items()},
        risk={key:shift(e) for key,e in descriptor['risk'].items()})
    proof=dict(PASS=True,original_FULL_sha=base.fingerprint(),projected_FULL_sha=projected.fingerprint(),
        eliminated_auxiliaries=len(substitutions),eliminated_equalities=len(removed),exact=True,
        preserved_constant_Runtime_auxiliaries=len(preserved_globals),preserved_constant_aux_global_prefix=True,
        every_original_equality_and_finish_expression_verified=True,all_runtime_boxes_original_zero_to_class_cardinality=True,
        redundant_finish_box_proof=file_record(runtime_projection.__file__),
        source_proof='Nonnegative class finishes sum to class cardinality; every grouped subset is in [0,N].',
        coefficient_rounding_allowed=False,retained_original_rows=original_rows,retained_original_columns=keep)
    return projected,translated,proof


def prepare_current_dw(context, case, built, output, *, captured=None,independent_domain_receipt=None,reference_receipt=None):
    """The PR191 source prepare sequence, using this already built FULL model."""
    if context.get('manifest',{}).get('Table_V_full_flex') is True:
        from .table_v_compression_adapter import prepare_exact_dw
        return prepare_exact_dw(context,case,built,output,captured=captured,
            independent_domain_receipt=independent_domain_receipt,reference_receipt=reference_receipt)
    from v42_pr134_sc.snapshot import capture
    from v42_a_stage_domain_v2.stress_backend import snapshot_of
    from v42_a_stage_domain_v2.fast_backend import Backend
    from v42_a_stage_domain_v2.domain import physical_domain
    from v42_a_stage_domain_v2.active import _ledger
    from v42_a_stage_phase1.producer import row_partition, native_block, complete_graph
    from v42_a_stage_phase1.backend import assemble_original, constructed_point
    from v42_a_stage_compact_rowgen.assembly import build, compact_inverse
    from v42_boundary.generator import Generator
    from v42_a_stage_domain_v2.active import cache_noop_check
    from v42_may_build_v6.construction import ReferenceReuse,routed_compact_build
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    _prepare_progress(output,'ORIGINAL_SOURCE_DOMAIN_AUDIT')
    audit = audit_source_domain(context); _write(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json', audit)
    if captured is None:
        captured=capture_current_full(context,case,built,output/'FULL_CAPTURE')
    data=captured['data'];original=captured['original'];base=captured['projected'];descriptor=captured['descriptor']
    if 'preserve_singleton_mixed_flow' not in data[7]:
        data=(*data[:7],dict(data[7],preserve_singleton_mixed_flow=[]))
    projection=captured['runtime_projection'];rawaxes=captured['coupling_rows']
    domain_sources=[file_record(Path(__file__).resolve().parents[1]/path) for path in
        ('v42_a_stage_domain_v2/domain.py','v42_boundary/generator.py','v42_job_capability.py')]
    _prepare_progress(output,'INDEPENDENT_PHYSICAL_DOMAIN_REPLAY')
    if independent_domain_receipt is None:
        independent_generator=Generator(data[3],max(b.latest_completion for b in data[2].values()))
        domains={uid:physical_domain(job,data[2][uid],data[3],gen=independent_generator) for uid,job in data[1].items()}
        independent_generator.check=cache_noop_check
        path=output/'INDEPENDENT_DOMAIN_CACHE.pkl.gz'
        with gzip.open(path,'xb',compresslevel=1) as stream:
            pickle.dump(dict(domains=domains,source_identity=context['manifest']['identity'],producer_sources=domain_sources),stream,protocol=5)
        _write(output/'INDEPENDENT_DOMAIN_CACHE_RECEIPT.json',dict(PASS=True,cache=file_record(path),Native_calls=0))
    else:
        cached=_checked_cache(independent_domain_receipt)
        if cached['source_identity']!=context['manifest']['identity'] or cached['producer_sources']!=domain_sources:
            raise ValueError('TABLE_V_DW_INDEPENDENT_DOMAIN_CHECKPOINT_AUTHORITY_DRIFT')
        domains=cached['domains']
    if set(domains)!=set(data[1]) or any(domain.cache.r!=data[3] or domain.duration!=data[1][uid].service_slots
            for uid,domain in domains.items()):
        raise ValueError('TABLE_V_DW_INDEPENDENT_DOMAIN_CHECKPOINT_ROSTER_RESOURCE_DRIFT')
    if digest({u: d.sha for u, d in sorted(domains.items())}) != data[7]['physical_domain_hash']:
        raise ValueError('TABLE_V_DW_INDEPENDENT_PHYSICAL_DOMAIN_SHA_DRIFT')
    for uid, domain in domains.items():
        graph = complete_graph(data[1][uid], domain, uid in data[7].get('preserve_singleton_mixed_flow', ()))
        if graph.sha != data[5][uid].sha:
            raise ValueError('TABLE_V_DW_ORIGINAL_COMPLETE_GRAPH_DRIFT:' + uid)
    _prepare_progress(output,'INDEPENDENT_DOMAIN_AND_COMPLETE_GRAPH_SHA_PASS')
    _write(output/'ORIGINAL_RUNTIME_AUXILIARY_PROJECTION.json',projection)
    local = [int(e[1]) for u in descriptor['units'] for items in u['v'].values() for e in items.values() if e[0]=='v']
    local += [int(j) for u in descriptor['units'] for items in u['v'].values() for e in items.values() if e[0]=='e' for j in e[2]]
    if not local: raise ValueError('TABLE_V_DW_ORIGINAL_LOCAL_PRIMITIVES_REQUIRED')
    n = min(local)
    row_remap={old:new for new,old in enumerate(projection.get('retained_original_rows',range(original.matrix.shape[0])))}
    axes = {(family.upper(), *key) if isinstance(key, tuple) else (family.upper(), '', key): row_remap[row]
        for (family, key), row in rawaxes.items()}
    grows, _, _ = row_partition(base, descriptor, n, axes.values())
    reference_reuse=ReferenceReuse(assemble_original)
    _prepare_progress(output,'ORIGINAL_REFERENCE_ASSEMBLY')
    ref_sources=[file_record(Path(__file__).resolve().parents[1]/path) for path in
        ('v42_a_stage_phase1/backend.py','v42_a_stage_phase1/producer.py','v42_root/native.py','v42_root/factor.py')]
    reference_identity=dict(base_snapshot_sha=base.fingerprint(),physical_domain_sha=data[7]['physical_domain_hash'],
        class_roster_sha=digest(data[7]['classes']),producer_sources=ref_sources)
    if reference_receipt is None:
        assembled=reference_reuse(base,grows,n,axes,data)
        path=output/'ORIGINAL_REFERENCE_CACHE.pkl.gz'
        with gzip.open(path,'xb',compresslevel=1) as stream:
            pickle.dump(dict(identity=reference_identity,assembled=assembled),stream,protocol=5)
        _write(output/'ORIGINAL_REFERENCE_CACHE_RECEIPT.json',dict(PASS=True,cache=file_record(path),Native_calls=0))
    else:
        cached=_checked_cache(reference_receipt)
        if cached['identity']!=reference_identity: raise ValueError('TABLE_V_DW_CURRENT_REFERENCE_CHECKPOINT_MATH_DRIFT')
        assembled=cached['assembled'];reference_reuse.previous=assembled;reference_reuse.data=data;reference_reuse.n=n
    ref, rdesc, G, _, _, newaxes=assembled
    _prepare_progress(output,'ORIGINAL_FULL_REFERENCE_MATH_EQUIVALENCE')
    equivalent = verify_full_equivalence(base, descriptor, ref, rdesc, n)
    equivalent.update(original_unprojected_FULL_integer_sha=original.fingerprint(),
        runtime_auxiliary_projection=file_record(output/'ORIGINAL_RUNTIME_AUXILIARY_PROJECTION.json'))
    _write(output/'ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json', equivalent)
    _prepare_progress(output,'ORIGINAL_FULL_REFERENCE_MATH_EQUIVALENCE_PASS')
    ledger = _ledger(data, domains, {})
    _prepare_progress(output,'ORIGINAL_V6_COMPACT_SOURCE_BUILD')
    state = routed_compact_build(reference_reuse)(ref,G,n,newaxes,data,domains,ledger,[])
    _write(output/'REFERENCE_REUSE_PROFILE.json',dict(reference_reuse.report(),
        prior_same_problem_reference_checkpoint_loaded=reference_receipt is not None,
        old_model_or_solution_loaded=reference_receipt is not None,
        prior_solution_or_bound_loaded=False))
    state.update(scientific_descriptor=descriptor, global_types=base.vtypes[:n].copy())
    # Atlas affects only source residual attribution/ranking. All feasibility
    # and bounds use the unchanged original FULL rows and exact coefficients.
    resource_variables = []
    for kind, site, t in newaxes:
        e = descriptor['known'].get((site,t)) if kind=='GPU' else descriptor['risk'].get((site,t)) if kind=='RUNTIME' else None
        resource_variables.append(int(e[1]) if e is not None and e[0]=='v' else -1)
    state['atlas'] = dict(rf=np.zeros(len(G),dtype=int), rf_names=np.asarray(['ORIGINAL_FULL_ROW']),
        node_names=np.asarray([]), voltage_lower_rows=np.asarray([],dtype=int), voltage_upper_rows=np.asarray([],dtype=int),
        resource_variables=np.asarray(resource_variables), domains=domains)
    _prepare_progress(output,'ORIGINAL_COMPACT_CONSTRUCTED_LOCAL_WITNESS')
    prior, _ = constructed_point(state['reference'], state['reference_descriptor'], data, n,
        range(len(G),state['reference'].matrix.shape[0]))
    state.update(prior_original=prior, prior_compact=compact_inverse(state,prior))
    roster = []; blockroot = output/'FULL_BLOCKS'; blockroot.mkdir()
    for key, members in sorted(data[7]['classes'].items()):
        uid = members[0]; graph = data[5][uid]
        snap, B, constant, encoded = native_block(data,key,graph,tuple(newaxes),averaged=True)
        path = blockroot/(key[:12]+'.pkl.gz')
        with gzip.open(path,'xb',compresslevel=1) as stream:
            pickle.dump(dict(snapshot=snap,B=B,constant=constant,units=encoded,graph=graph),stream,protocol=5)
        roster.append(dict(PASS=True,class_id=key,cardinality=len(members),external_full_block_cache=file_record(path),
            full_physical_STAY=len(domains[uid].stays),full_physical_migration=sum(len(b[-1]) for b in domains[uid].blocks),
            full_compact_blocks=len(domains[uid].blocks),complete_graph_sha256=graph.sha,
            complete_local_snapshot_sha256=snap.fingerprint()))
        if len(roster)%50==0:_prepare_progress(output,'COMPLETE_SOURCE_PRICING_ROSTER',classes=len(roster),required_classes=len(data[7]['classes']))
    if len({r['class_id'][:12] for r in roster}) != len(roster):
        raise ValueError('TABLE_V_DW_CLASS_PREFIX_COLLISION')
    _write(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(PASS=True,records=roster,
        producer='UNCHANGED_PR191_COMPLETE_NATIVE_BLOCK_PRODUCER',all_original_UIDs=sorted(data[1]),
        complete_class_roster_SHA=digest(data[7]['classes']),case_sha=case.case_sha))
    state['_table_v'] = dict(case_sha=case.case_sha, native_binding=deepcopy(built[6]['native_binding']),
        source_domain_audit_sha=digest(audit), equivalent=equivalent,
        full_physical_domain_sha=data[7]['physical_domain_hash'], classes=len(roster))
    _prepare_progress(output,'ORIGINAL_FULL_AND_COMPLETE_DW_NATIVE0_PASS',classes=len(roster))
    return state


def capture_current_full(context,case,built,output):
    """Persist sparse FULL interfaces before any later DW preparation can fail."""
    from v42_pr134_sc.snapshot import capture
    from v42_a_stage_domain_v2.stress_backend import snapshot_of
    from v42_a_stage_domain_v2.fast_backend import Backend
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    model,units,levels,controls,bindings,data,metadata=built
    original=snapshot_of(model,[('rho',dict(levels)['rho'])])
    descriptor=capture(model,units,levels,controls,bindings,output/'SCIENTIFIC_INTERFACES.pkl.gz')
    backend=Backend();backend.data=data
    rawaxes=backend._coupling_rows(model,bindings)
    from .pcc_definitions import definitions_from_native
    pcc_definitions=definitions_from_native(model,context['state']['capacities'])
    # Save the original sparse snapshot even if the equality projection fails.
    original_path=output/'ORIGINAL_FULL_SNAPSHOT.pkl.gz'
    with gzip.open(original_path,'xb',compresslevel=1) as stream:pickle.dump(original,stream,protocol=5)
    raw_packet=dict(data=data,original=original,original_descriptor=descriptor,coupling_rows=rawaxes,pcc_definitions=pcc_definitions,
        original_runtime_bindings={key:int(value.index) for key,value in bindings.get('Runtime_finish_counts',{}).items()
            if hasattr(value,'index') and isinstance(value.index,int)},
        runtime_equality_rows=[i for i,name in enumerate(model.getAttr('ConstrName')) if name=='exact_Runtime_finish_count'],
        case_sha=case.case_sha,objective_sha=objective_identity(model),native_binding=deepcopy(metadata['native_binding']),
        source_identity=deepcopy(context['manifest']['identity']),input_sha=context['input_audit']['a_input_sha'])
    raw_path=output/'ORIGINAL_FULL_CAPTURE.pkl.gz'
    with gzip.open(raw_path,'xb',compresslevel=1) as stream:pickle.dump(raw_packet,stream,protocol=5)
    _write(output/'ORIGINAL_FULL_CAPTURE_RECEIPT.json',dict(PASS=True,capture=file_record(raw_path),Native_calls=0))
    projected,translated,projection=project_runtime_auxiliaries(model,original,bindings,descriptor,data)
    packet=dict(data=data,original=original,projected=projected,descriptor=translated,pcc_definitions=pcc_definitions,
        runtime_projection=projection,coupling_rows=rawaxes,case_sha=case.case_sha,
        objective_sha=objective_identity(model),
        native_binding=deepcopy(metadata['native_binding']),source_identity=deepcopy(context['manifest']['identity']),
        input_sha=context['input_audit']['a_input_sha'])
    if getattr(case,'table_v_full_flex',False):
        from .table_v_compression_adapter import stage_binding
        packet['stage_binding']=stage_binding(context,case,packet)
    path=output/'FULL_DW_CAPTURE.pkl.gz'
    with gzip.open(path,'xb',compresslevel=1) as stream:pickle.dump(packet,stream,protocol=5)
    _write(output/'FULL_DW_CAPTURE_RECEIPT.json',dict(PASS=True,capture=file_record(path),
        original_FULL_snapshot=file_record(original_path),case_sha=case.case_sha,
        native_binding=metadata['native_binding'],objective_sha=objective_identity(model),Native_calls=0))
    return packet


class CurrentNative:
    """Only the existing stage ledger may cross Gurobi's optimize boundary."""
    def __init__(self,budget,case,output):
        self.budget=budget; self.case=case; self.output=Path(output); self.calls=[]
        self.day=getattr(case,'table_v_day',case.data[0].get('day'))
        self.native_seconds=0.; self.resources=[];self.seen_operations=set()
        self.phase_basis=None
        # The 900s Phase-I allowance also survives a source revision/resume;
        # a new adapter object must not silently reopen the same stage clock.
        refresh=getattr(budget,'_refresh',None)
        if refresh is not None:refresh()
        prior=getattr(budget,'document',{}).get('calls',[])
        self.prior_phase_seconds=sum(float(row.get('Native_Runtime') or 0.) for row in prior
            if row.get('solver')=='GUROBI' and row.get('label','').startswith('RELEASE_P1:'+case.stage+':DW:PHASE_I:')
            and all(row.get('stage_context',{}).get(key)==value for key,value in
                dict(day=self.day,arm=getattr(case,'arm',None),stage=case.stage).items()))
        freeze=self.output/'DW_SOURCE_FREEZE.json'
        self.frozen_sources=json.loads(freeze.read_text(encoding='utf8'))['sources'] if freeze.is_file() else []

    def remaining(self):
        from v42_a_stage_early.native import BudgetStop
        remaining=self.budget.remaining()
        if remaining<=0: raise BudgetStop('TABLE_V_DW_CUMULATIVE_A_STAGE_NATIVE_EXHAUSTED')
        return remaining

    def solve(self,snapshot,folder,component):
        from v42_a_stage_domain_v2.stress_backend import materialize
        from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
        from v42_b3_joint.numerical_policy import apply_native_precision
        from .table_v_phase_policy import POLICIES,allowance,progress_callback,INTEGER_RETURN_RESERVE
        import gurobipy as gp
        if component not in ('PHASE_I','ORIGINAL_P1','LOCAL_PRICING'):
            raise PermissionError('TABLE_V_DW_P1_ONLY_NATIVE_COMPONENT_REQUIRED')
        if not self.frozen_sources or any(file_record(row['path'])!=row for row in self.frozen_sources):
            raise PermissionError('TABLE_V_DW_FROZEN_SOURCE_BYTES_DRIFT')
        self.remaining();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        from .table_v_resources import admit_resources
        admit_resources(self.budget,phase='PRE_DW_MODEL_BUILD:'+component)
        model,objectives=materialize(snapshot,self.day)
        attempts=[];accepted=None;raw={}
        try:
            if any(snapshot.vtypes!='C'):raise ValueError('TABLE_V_DW_LP_ONLY')
            model.setObjective(objectives[0][1],gp.GRB.MINIMIZE)
            policy=solver_policy(gp);apply_policy(model,policy,gp)
            numerical=None
            profiles=POLICIES if component=='PHASE_I' else (None,)
            seen=self.seen_operations
            for profile in profiles:
                if component=='PHASE_I':
                    phase_used=self.prior_phase_seconds+sum(r['native_seconds'] for r in self.calls if r['component']=='PHASE_I')
                    seconds=min(profile.seconds,allowance(self.remaining(),phase_used))
                    parameters=profile.parameters();name=profile.name
                else:
                    seconds=min(120. if component=='LOCAL_PRICING' else 300.,self.remaining()-INTEGER_RETURN_RESERVE)
                    parameters=dict(OutputFlag=1,LogToConsole=0);name='ORIGINAL_PRECISE'
                    numerical=apply_native_precision(model,day=self.day,stage=self.case.stage,component=component)
                if seconds<=0:raise RuntimeError('DW_RESERVED_ORIGINAL_INTEGER_NATIVE_ALLOWANCE')
                key=(snapshot.fingerprint(),component,name)
                if key in seen:raise RuntimeError('DUPLICATE_UNCHANGED_DW_POLICY_OPERATION')
                seen.add(key);attempt=folder/name;attempt.mkdir(exist_ok=False)
                if attempts:model.reset()
                for k,v in parameters.items():model.setParam(k,v)
                basis_start=dict(installed=False,reason='NO_PRIOR_ACCEPTED_PHASE_BASIS')
                if component=='PHASE_I' and self.phase_basis is not None and not attempts:
                    from .table_v_phase_diagnostics import extend_basis,basis_admission
                    try:
                        vb,cb,proof=extend_basis(self.phase_basis[0],snapshot,self.phase_basis[1])
                        admission=basis_admission(proof)
                        path=attempt/'VERIFIED_CANDIDATE_NATIVE_BASIS.npz'
                        np.savez_compressed(path,VBasis=vb,CBasis=cb)
                        for k,v in admission['parameters'].items():model.setParam(k,v)
                        if admission['reuse']:
                            model.setAttr('VBasis',vb.tolist());model.setAttr('CBasis',cb.tolist())
                        basis_start=dict(installed=admission['reuse'],proof=proof,admission=admission,
                            retained_native_basis=file_record(path))
                    except (ValueError,AttributeError,gp.GurobiError) as error:
                        model.reset();basis_start=dict(installed=False,reason=str(error))
                model.Params.Threads=1;model.Params.LogFile=str(attempt/'NATIVE_GUROBI.log')
                _write(attempt/'MODEL_IDENTITY.json',dict(original_snapshot_sha256=snapshot.fingerprint(),
                    component=component,case_sha=self.case.case_sha,objective_name=snapshot.objectives[0].name,
                    solver_policy=policy,numerical_policy=numerical,adaptive_policy=name,parameters=parameters,
                    basis_start=basis_start,Threads=1,P2_calls=0))
                call=self.budget.solve(model,label='RELEASE_P1:'+self.case.stage+':DW:'+component+':'+name,
                    cap=seconds,callback=progress_callback(attempt,component))
                record=dict(status=int(model.Status),SolCount=int(model.SolCount),native_seconds=float(model.Runtime),
                    Work=float(model.Work),objective=float(model.ObjVal) if model.SolCount else None,
                    snapshot_sha=snapshot.fingerprint(),ledger_call=call,component=component,adaptive_policy=name,
                    source_sha=(getattr(self.budget,'context',None) or {}).get('source_sha'),case_sha=self.case.case_sha,
                    Stage_Native_cumulative=5400.-self.budget.remaining(),certified_Global_LB=None,FULL_verified_UB=None,
                    Global_Gap=None,diagnostic_objective_is_global_certificate=False)
                from .table_v_memory import memory_sample
                import psutil
                memory=psutil.Process().memory_info()
                record.update(memory=memory_sample(),process_peak_RSS_bytes=getattr(memory,'peak_wset',memory.rss),
                    process_peak_private_bytes=getattr(memory,'peak_pagefile',getattr(memory,'private',None)))
                candidate={}
                if model.SolCount:candidate['X']=np.asarray(model.getAttr('X'),float)
                if model.Status==gp.GRB.OPTIMAL:
                    candidate.update(Pi=np.asarray(model.getAttr('Pi'),float),RC=np.asarray(model.getAttr('RC'),float))
                    try:
                        vb=np.asarray(model.getAttr('VBasis'),dtype=np.int32)
                        cb=np.asarray(model.getAttr('CBasis'),dtype=np.int32)
                        if vb.shape!=(snapshot.matrix.shape[1],) or cb.shape!=(snapshot.matrix.shape[0],):
                            raise ValueError('LP_BASIS_NATIVE_AXIS_DRIFT')
                        candidate.update(VBasis=vb,CBasis=cb)
                        record['LP_basis']=dict(available=True,native_raw=True,reused_as_start=False)
                    except Exception as basis_error:
                        record['LP_basis']=dict(available=False,reason=type(basis_error).__name__,reused_as_start=False)
                if component=='PHASE_I':
                    from .table_v_phase_diagnostics import residual_report
                    diagnostics=residual_report(snapshot,candidate,attempt)
                    validation=diagnostics['numerical_1e5']
                    record['residual_comparison']=diagnostics
                else:validation=dict(PASS=model.Status==gp.GRB.OPTIMAL)
                record['independent_numerical_validation']=validation
                np.savez_compressed(attempt/'RAW_ATTRIBUTES.npz',**candidate);_write(attempt/'NATIVE_RESULT.json',record)
                self.calls.append(record);self.native_seconds+=record['native_seconds'];attempts.append(record)
                _write(self.output/'DW_NATIVE_CALLS.json',dict(calls=self.calls,Native_Runtime=self.native_seconds,P2_calls=0))
                if record['status']==2 and validation['PASS']:
                    if component=='PHASE_I' and all(k in candidate for k in ('VBasis','CBasis')):
                        self.phase_basis=(snapshot,candidate)
                    accepted=record;raw=candidate;break
                # TimeLimit is not a numerical failure. Barrier has no valid
                # partial basis to resume here; cold-starting another policy
                # would discard convergence and consume the integer reserve.
                if component=='PHASE_I' and record['status']!=gp.GRB.OPTIMAL and record['status']!=gp.GRB.NUMERIC:
                    break
            record=accepted or attempts[-1]
            # Compatibility outputs are new files; attempt Raw is never edited.
            np.savez_compressed(folder/'RAW_ATTRIBUTES.npz',**raw)
            _write(folder/'NATIVE_RESULT.json',dict(record,numerical_attempts=len(attempts),validation_accepted=accepted is not None))
            return record,raw
        finally:model.dispose()


def execute_current_dw(context,case,built,budget,output):
    """Actually invoke the existing Phase I/P1/full-pricing loop, serially."""
    from v42_b3_joint.a_source import _stage_lock
    from v42_may_campaign_native90.a_routing import rebound
    from v42_a_stage_canary import phase,pricing,targeted
    output=Path(output)
    if output.exists(): raise FileExistsError('TABLE_V_DW_ATTEMPT_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    sources=_freeze_sources(output)
    result=dict(phase_I_status='NOT_RUN',pricing_status='NOT_RUN',Global_LB=None,LB_certified=False,
        phase_I_phi=None,full_domain_pricing_complete=False,case_sha=case.case_sha,
        native_binding=deepcopy(built[6]['native_binding']),P2_calls=0,
        reference_bridge_source='v42_b3_joint.a_source.ASourceBridge',
        executor_source='v42_integration.table_v_dw.execute_current_dw',
        phase_source='v42_a_stage_canary.phase.run',pricing_source='v42_a_stage_canary.pricing.full_pricing')
    native=CurrentNative(budget,case,output);started=perf_counter()
    try:
        state=prepare_current_dw(context,case,built,output)
        with _stage_lock:
            full_pricing=rebound(pricing.full_pricing,dict(pricing.full_pricing.__globals__,HISTORY=output))
            worker=rebound(targeted.worker,dict(targeted.worker.__globals__,_NATIVE=native,HISTORY=output))
            target=rebound(targeted.targeted,dict(targeted.targeted.__globals__,HISTORY=output,worker=worker))
            # Source run writes to OUT/day. All other algorithm code and
            # stopping/pricing/row-promotion criteria remain source-owned.
            from .table_v_phase_policy import require_exact_zero,phase_primal_replay,phase_dual_replay
            elastic_backend=rebound(phase.point_with_replay,dict(phase.point_with_replay.__globals__,
                primal_replay=phase_primal_replay(phase.primal_replay)))
            elastic_point=rebound(phase.artificial_point,dict(phase.artificial_point.__globals__,
                point_with_replay=elastic_backend))
            namespace=dict(phase.run.__globals__,OUT=output.parent,verify_zero=require_exact_zero(phase.verify_zero),
                primal_replay=phase_primal_replay(phase.primal_replay),
                verify_sign_convention=phase_dual_replay(phase.verify_sign_convention),
                artificial_point=elastic_point,
                full_pricing=full_pricing,targeted=target)
            if '_class_sum' in state:
                from .table_v_compression_adapter import complete_kernel_rebuilder
                namespace['build']=complete_kernel_rebuilder(state)
                namespace['activate']=rebound(phase.activate,namespace)
            routed=rebound(phase.run,namespace)
            state,p1_point,_,priced=routed(native,state,output.name)
            if '_class_sum' in state:
                from .table_v_compression_adapter import source_lp_replay
                source_lp_replay(state,p1_point,output)
        if any(file_record(row['path'])!=row for row in sources):
            raise PermissionError('TABLE_V_DW_SOURCE_BYTES_CHANGED_DURING_SOLVE')
        phi=json.loads((output/'PHASE_I_ZERO_CERTIFICATE.json').read_text(encoding='utf8'))
        complete=priced.get('PASS') is True and priced.get('complete_STAY_and_migration_coverage') is True and priced.get('no_negative_omitted_block_certified') is True
        if phi.get('PASS') is not True or not complete or priced.get('full_domain_phase1_lower_bound') is None:
            raise ValueError('TABLE_V_DW_COMPLETE_PHASE_I_AND_PRICING_CERTIFICATE_REQUIRED')
        lower=Fraction(priced['full_domain_phase1_lower_bound'])
        result.update(phase_I_status='PHI_ZERO_CERTIFIED',phase_I_phi=phi['Phi'],pricing_status='COMPLETE',
            Global_LB=float(lower),exact_Global_LB=str(lower),LB_certified=True,full_domain_pricing_complete=True,
            certificate=dict(phase_I=file_record(output/'PHASE_I_ZERO_CERTIFICATE.json'),
                P1=file_record(output/'P1_RESULT.json'),math_equivalence=file_record(output/'ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json'),
                source_domain=file_record(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json'),
                complete_pricing_roster=file_record(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')),
            math_identity=state['_table_v'])
    except (ValueError,RuntimeError,PermissionError,OSError,KeyError,IndexError,TypeError,AttributeError) as error:
        # Failure evidence and Native calls are durable. Incomplete restricted
        # objectives, historical May12 bounds and MILP ObjBound cannot enter LB.
        phi_path=output/'PHASE_I_ZERO_CERTIFICATE.json'
        if phi_path.is_file():
            phi=json.loads(phi_path.read_text(encoding='utf8'))
            if phi.get('PASS') is True:
                result.update(phase_I_status='PHI_ZERO_CERTIFIED',phase_I_phi=phi.get('Phi'),pricing_status='INCOMPLETE')
        if result['phase_I_status']=='NOT_RUN': result['phase_I_status']='NOT_CERTIFIED'
        result.update(error=type(error).__name__+': '+str(error),status='DW_PHASE_I_NOT_CERTIFIED'
            if result['phase_I_status']!='PHI_ZERO_CERTIFIED' else 'DW_PRICING_INCOMPLETE')
        result['structural_adapter_failure']=not (output/'ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json').is_file()
    result.update(Native_Runtime=native.native_seconds,native_calls=len(native.calls),wall_seconds=perf_counter()-started,
        Native_calls_receipt=file_record(output/'DW_NATIVE_CALLS.json') if (output/'DW_NATIVE_CALLS.json').exists() else None)
    if result['LB_certified']: result['status']='DW_GLOBAL_LB_CERTIFIED'
    _write(output/'DW_RESULT.json',result)
    budget.record_external('RELEASE_P1:'+case.stage+':DW_WALL',result['wall_seconds'],solver='WALL_DIAGNOSTIC')
    return result


def attach_global_bounds(result,dw):
    """Keep certified DW and original integer bounds under separate authority."""
    result['DW']=deepcopy(dw)
    upper=result.get('objective') if result.get('FULL_feasible') is True else None
    valid=(dw.get('LB_certified') is True and dw.get('full_domain_pricing_complete') is True
        and dw.get('case_sha')==result.get('case_sha') and dw.get('native_binding')==result.get('native_binding'))
    dw_lower=dw.get('Global_LB') if valid else None
    from .table_v_a_control import verified_integer_lower
    integer_lower=verified_integer_lower(result)
    lower=max((v for v in (dw_lower,integer_lower) if v is not None),default=None)
    result.update(AIDC_DW_Global_LB=dw_lower,AIDC_Integer_Global_Bound=integer_lower,
        AIDC_Global_LB_origins={k:v for k,v in (('DW_FULL_PRICING',dw_lower),('ORIGINAL_INTEGER_MILP',integer_lower)) if v is not None})
    finite=lambda v:type(v) in (int,float) and math.isfinite(v)
    gap=None
    if finite(upper) and finite(lower) and upper>0 and lower<=upper:
        gap=(upper-lower)/upper
    elif lower is not None and upper is not None and not (upper==lower==0):
        lower=None
        result['DW'].update(LB_certified=False,status='DW_PRICING_INCOMPLETE',
            bound_admission_error='CERTIFIED_LOWER_EXCEEDS_CURRENT_FULL_UPPER')
    result.update(AIDC_Global_LB=lower,AIDC_Global_UB=upper,AIDC_Global_Gap=gap,
        AIDC_Global_Gap_percent=None if gap is None else 100*gap,global_gap=gap,
        AIDC_Global_Gap_target=AIDC_GLOBAL_GAP_TARGET,DW_status=result['DW'].get('status'))
    return result


def native0_preflight(context,output,*,arm='B1',stage='A1',capture_receipt=None,
                      independent_domain_receipt=None,reference_receipt=None):
    """Build and check current FULL/DW inputs with all native entrypoints blocked.

    Use a fresh output directory. This runs no optimize, presolve or IIS and
    does not open or change any campaign Native ledger or historical raw file.
    """
    import gurobipy as gp
    from .table_v_flex_planning import build_flex_native_model,require_flex_context
    from .partial_canary import resource_snapshot
    from .d0_resource import native_binding
    require_flex_context(context)
    output=Path(output)
    if output.exists(): raise FileExistsError('TABLE_V_DW_NATIVE0_PREFLIGHT_FRESH_OUTPUT_REQUIRED')
    resources=resource_snapshot();memory=resources['memory']
    output.mkdir(parents=True);built=None;started=perf_counter()
    original={name:getattr(gp.Model,name) for name in ('optimize','presolve','computeIIS')}
    def forbidden(*args,**kwargs): raise PermissionError('TABLE_V_DW_PREFLIGHT_NATIVE0_ONLY')
    for name in original:setattr(gp.Model,name,forbidden)
    report=dict(status='NOT_CERTIFIED',day=context['manifest']['day'],Native_calls=0,P2_calls=0,
        Native_model_builds_this_preflight=0,resource_before=resources)
    try:
        audit=audit_source_domain(context)
        _write(output/'SOURCE_DOMAIN_EARLY_NATIVE0_AUDIT.json',audit)
        case=context['make_a_case'](stage,folder=output/'FULL',arm=arm)
        case.table_v_day=context['manifest']['day']
        report.update(case_sha=case.case_sha,source_identity=context['manifest']['identity'])
        if capture_receipt is None:
            admission=dict(status='PASS',operation='TABLE_V_FULL_FLEX_A_NATIVE0_BUILD',
                case_sha=case.case_sha,concurrent_heavy_solver=False,resource_snapshot=resources)
            built=build_flex_native_model(case,build_admission=admission)
            report['Native_model_builds_this_preflight']=1
            built[0].setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);built[0].update();built[0].Params.Threads=1
            built[6]['native_binding']=native_binding(built[0])
            report.update(native_binding=built[6]['native_binding'],objective_sha=objective_identity(built[0]))
            _write(output/'NATIVE0_FULL_MODEL_IDENTITY.json',report)
            captured=capture_current_full(context,case,built,output/'FULL_CAPTURE')
            report['capture_receipt']=file_record(output/'FULL_CAPTURE'/'FULL_DW_CAPTURE.pkl.gz')
        else:
            if file_record(capture_receipt['path'])!=capture_receipt:
                raise ValueError('TABLE_V_DW_PREFLIGHT_CAPTURE_BYTES_DRIFT')
            with gzip.open(capture_receipt['path'],'rb') as stream:captured=pickle.load(stream)
            if (captured['source_identity']!=context['manifest']['identity'] or captured['case_sha']!=case.case_sha
                    or captured['input_sha']!=context['input_audit']['a_input_sha']
                    or captured['runtime_projection']['original_FULL_sha']!=captured['original'].fingerprint()
                    or captured['runtime_projection']['projected_FULL_sha']!=captured['projected'].fingerprint()):
                raise ValueError('TABLE_V_DW_PREFLIGHT_CAPTURE_SAME_PROBLEM_REQUIRED')
            report.update(capture_receipt=capture_receipt,native_binding=captured['native_binding'],
                objective_sha=captured['objective_sha'],saved_sparse_FULL_capture_reused=True)
        state=prepare_current_dw(context,case,[None]*6+[{'native_binding':captured['native_binding']}],
            output/'DW',captured=captured,independent_domain_receipt=independent_domain_receipt,
            reference_receipt=reference_receipt)
        report.update(status='PASS',math_identity=state['_table_v'],source_preparation_only=True,
            phase_I_status='NOT_RUN',pricing_status='NOT_RUN',Global_LB=None,
            FULL_integer_UB=None,Global_Gap=None)
    except Exception as error:
        report.update(error=type(error).__name__+': '+str(error))
        raise
    finally:
        if built is not None:built[0].dispose()
        for name,method in original.items():setattr(gp.Model,name,method)
        report.update(wall_seconds=perf_counter()-started,resource_after=resource_snapshot())
        _write(output/'NATIVE0_DW_PREFLIGHT_RESULT.json',report)
    return report
