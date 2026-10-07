"""Lossless full native local LP blocks, including mixed fractional finishes.

Pricing aggregates IDENTICAL continuous optional lanes by their sum. This
is an exact LP projection (convexity); integer production lanes are unchanged.
The original factor/compact builders generate every hard local row. Complete
graphs are unions of compact physical indices, without path variables.
"""
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
import hashlib
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_compact.graph import Graph
from v42_root import factor
from v42_root.native import local_units
from v42_sparse.runtime import coefficient_vector
from v42_a_stage_domain_v2.domain import graph_content_hash
from v42_a_stage_domain_v2.stress_backend import snapshot_of
from v42_a_stage_domain_v2.lexstage import Objective


def bits(values):
    result = 0
    for value in values: result |= 1 << value
    return result


def indices(mask):
    while mask:
        low = mask & -mask
        yield low.bit_length()-1
        mask ^= low


def interval(a, b): return ((1 << (b-a))-1) << a if b > a else 0


def complete_graph(job, domain, retained_flow=False):
    """Enumerate every compact block; fold timestamp unions losslessly.

GPU/finish state unions use integer bitsets. Checkpoint compatibility retains
every exact (source, checkpoint, start) entry and physical timestamp. No
approximation, dominance, reference distance or skipped path prefix occurs.
"""
    events = {n: set() for n in ('y', 'q', 'w', 'f0', 'f1')}
    state = {n: defaultdict(int) for n in ('r0', 'h', 'r1')}
    compatible, physical, transfers = defaultdict(set), {}, {}
    for start, site in domain.stays:
        events['y'].add((site, start)); events['f0'].add((site, start+job.service_slots))
        state['r0'][site] |= interval(start, start+job.service_slots)
    tau_cache, grouped, transfer_masks = {}, defaultdict(int), defaultdict(int)
    for start, source, cp, timestamp, dest, gpu, taus in domain.blocks:
        events['y'].add((source, start)); events['q'].add((source, cp))
        key = source, cp, start
        if key not in physical:
            state['r0'][source] |= interval(start, cp)
            compatible[source, cp].add(start); physical[key] = timestamp
        if taus not in tau_cache: tau_cache[taus] = bits(taus)
        mask = tau_cache[taus]
        transfer_masks[source, dest] |= mask
        grouped[source, dest, job.service_slots-(cp-start)] |= mask
        state['h'][source] |= interval(cp, max(taus))
    for (source, dest), mask in sorted(transfer_masks.items()):
        for tau in indices(mask):
            key = source, dest, tau
            events['w'].add(key)
            transfers[key] = domain.cache.transfer(source, dest, job.gpu, tau)
    for (source, dest, remaining), mask in sorted(grouped.items()):
        for tau in indices(mask):
            restart = transfers[source, dest, tau].restart
            finish = restart+remaining
            events['f1'].add((dest, finish))
            state['r1'][dest] |= interval(restart, finish)
    fixed = None
    if not retained_flow and len(domain.stays) == 1 and not domain.blocks:
        from v42_job_capability import Option
        start, site = domain.stays[0]
        fixed = Option(start, site, ((site, start, start+job.service_slots),))
    graph = Graph({n: tuple(sorted(v)) for n, v in events.items()},
        {n: tuple((site, t) for site, mask in sorted(v.items()) for t in indices(mask)) for n, v in state.items()},
        {k: tuple(sorted(v)) for k, v in compatible.items()}, physical, transfers, fixed)
    graph.sha = graph_content_hash(graph)
    return graph


def variable_columns(units):
    result = []
    for unit in units:
        owned = set()
        for items in unit['v'].values():
            for x in items.values():
                if isinstance(x, gp.Var): owned.add(x.index)
                elif isinstance(x, gp.LinExpr): owned.update(x.getVar(i).index for i in range(x.size()))
        result.append((unit['class_key'], unit['id'], tuple(sorted(owned))))
    return result


def encoded_ownership(descriptor, global_variables):
    owned = {}
    for unit in descriptor['units']:
        for items in unit['v'].values():
            for e in items.values():
                ids = (e[1],) if e[0] == 'v' else e[2] if e[0] == 'e' else ()
                for j in ids:
                    j = int(j)
                    if j < global_variables: raise ValueError('GLOBAL_VARIABLE_IN_LOCAL_UNIT')
                    if j in owned and owned[j] != unit['class_key']: raise ValueError('LOCAL_CLASS_COLUMN_ALIAS')
                    owned[j] = unit['class_key']
    return owned


def row_partition(snapshot, descriptor, global_variables, explicit_coupling_rows):
    owned = encoded_ownership(descriptor, global_variables)
    if set(owned) != set(range(global_variables, snapshot.matrix.shape[1])):
        raise ValueError('EVERY_NATIVE_LOCAL_VARIABLE_REQUIRES_CLASS_IDENTITY')
    global_rows, local = [], defaultdict(list)
    forced = set(explicit_coupling_rows)
    last_local_class = None
    for row in range(snapshot.matrix.shape[0]):
        columns = snapshot.matrix.indices[snapshot.matrix.indptr[row]:snapshot.matrix.indptr[row+1]]
        classes = {owned[int(j)] for j in columns if j >= global_variables}
        if not len(columns) and last_local_class is not None and row not in forced:
            local[last_local_class].append(row)
        elif row in forced or len(classes) != 1 or np.any(columns < global_variables): global_rows.append(row)
        else:
            last_local_class = next(iter(classes))
            local[last_local_class].append(row)
    return tuple(global_rows), {key: tuple(value) for key, value in local.items()}, owned


def native_block(data, class_id, graph, coupling_axes, *, averaged=True):
    """Reuses native local builders, exactly the F2-CRA switches and Runtime.

Returns all hard rows and all coupling primitive coefficients; no grid-score
surrogate. Electrical/CC4 effects pass through unchanged known/risk rows.
"""
    bundle, jobs, bounds, resources, raw, graphs, old, prep = data
    members = prep['classes'][class_id]; uid = members[0]; job = jobs[uid]; count = len(members)
    m = gp.Model('PHASE1_FULL_NATIVE_LOCAL_'+class_id[:12]); m.Params.OutputFlag = 0
    options = dict(eliminate_depart=False, eliminate_arrive=False, share_links=False,
        eliminate_f0=True, eliminate_state=True, byte_scale=2.**20)
    retain = uid in prep.get('preserve_singleton_mixed_flow', ())
    if not averaged:
        subjobs = {u: jobs[u] for u in members}; subbounds = {u: bounds[u] for u in members}
        subgraphs = {u: graph for u in members}
        class NoopContext:
            def progress(self, value): pass
        units = local_units(m, subjobs, subbounds, resources, subgraphs, {class_id: members}, 'F2-CRA', NoopContext(),
            preserve_singleton_mixed_flow=(uid,) if retain else ())
        for unit in units: unit['multiplier'] = 1
    elif count == 1 or graph.fixed:
        units = []
        for u in members:
            v = factor.add_job(m, jobs[u], graph, resources, preserve_stay_flow=retain, **options)
            units.append(dict(uid=u, id=u, v=v, optional=False, stay_count=False, class_key=class_id, multiplier=1))
    else:
        sj = replace(job, uid='CLASS_'+class_id[:12])
        # Identical native generator.fits predicate, rather than a new cut.
        from v42_boundary.generator import Generator
        gen = Generator(resources, max(b.latest_completion for b in bounds.values()))
        starts = tuple((k, s) for k, s in graph.events['y'] if s+job.service_slots <= bounds[uid].latest_completion
                       and gen.fits(k, s, job.service_slots, job.gpu))
        sv = factor.stay(m, sj, graph, count, starts=starts, eliminate_f0=True, eliminate_state=True)
        units = [dict(uid=uid, id=sj.uid+'_STAY', v=sv, optional=False, stay_count=True, class_key=class_id, multiplier=1)]
        amount = gp.quicksum(sv['y'].values())
        if graph.events['w']:
            m.update(); first_column, first_row = m.NumVars, m.NumConstrs
            lj = replace(job, uid=sj.uid+'_SUM_LANE')
            lv = factor.add_job(m, lj, graph, resources, optional=True, **options)
            m.update()
            # Sum projection: A is unchanged, RHS and original boxes become
            # N*b,N*l,N*u. Coupling coefficients remain the ORIGINAL binary64
            # coefficients, so N*a floating multiplication cannot change them.
            def exact_scale(value):
                if abs(value) >= 1e100: return value
                wanted = Fraction(float(value))*count
                scaled = float(wanted)
                if Fraction(scaled) != wanted: raise ValueError('NONEXACT_DYADIC_LANE_SUM_SCALING')
                return scaled
            for row in m.getConstrs()[first_row:]: row.RHS = exact_scale(row.RHS)
            for column in m.getVars()[first_column:]:
                column.LB = exact_scale(column.LB); column.UB = exact_scale(column.UB)
            units.append(dict(uid=uid, id=lj.uid, v=lv, optional=True, stay_count=False,
                class_key=class_id, multiplier=1, summed_identical_continuous_lanes=count))
            amount += lv['migration_selected']['selected']
        m.addConstr(amount == count, name='class_exact_cardinality')
    m.update()
    constants = defaultdict(float)
    coefficients = {key: defaultdict(float) for key in coupling_axes}
    def attach(key, x, coefficient):
        coefficient = float(coefficient)
        if key not in coefficients: raise ValueError('MISSING_ORIGINAL_COUPLING_AXIS')
        if isinstance(x, gp.Var): coefficients[key][x.index] += coefficient
        elif isinstance(x, gp.LinExpr):
            for i in range(x.size()):
                coefficients[key][x.getVar(i).index] += coefficient*x.getCoeff(i)
            constants[key] += coefficient*x.getConstant()
        else: constants[key] += coefficient*x
    for unit in units:
        v, scale = unit['v'], unit['multiplier']
        for family in ('r0', 'r1'):
            for (site, slot), x in v[family].items(): attach(('GPU', site, slot), x, -job.gpu*scale)
        for family in ('f0', 'f1'):
            if unit['optional'] and family == 'f0': continue
            for (site, end), x in v[family].items():
                for (target_site, slot), value in coefficient_vector(job, raw[uid], site, end, bundle):
                    attach(('RUNTIME', target_site, slot), x, -value*scale)
        if 'pair' in v:
            for (link, slot), x in v['link_bytes'].items(): attach(('WAN', link, slot), x, scale/2.**20)
            for slot, x in v['wan_active'].items(): attach(('ACTIVE', '', slot), x, scale)
        else:
            for key, x in v['w'].items():
                transfer = graph.transfers[key]
                for link, slot, value in transfer.wan: attach(('WAN', link, slot), x, scale*value/2.**20)
                for slot in range(key[2], transfer.end): attach(('ACTIVE', '', slot), x, scale)
    m.update()
    full = snapshot_of(m, [('local_price', 0.)])
    rr, cc, vv = [], [], []
    for i, key in enumerate(coupling_axes):
        for j, value in sorted(coefficients[key].items()):
            if value: rr.append(i); cc.append(j); vv.append(value)
    B = sp.csr_matrix((vv, (rr, cc)), shape=(len(coupling_axes), full.matrix.shape[1]))
    snapshot = replace(full, vtypes=np.full(full.matrix.shape[1], 'C'))
    from v42_pr134_sc.snapshot import encode
    units = [dict(unit, v={n: {key: encode(x) for key, x in items.items()}
                          for n, items in unit['v'].items()}) for unit in units]
    m.dispose()
    return snapshot.require(), B, np.asarray([constants[key] for key in coupling_axes]), units


def price_snapshot(snapshot, B, pi):
    coefficients = -(B.T @ np.asarray(pi))
    return replace(snapshot, objectives=(Objective('local_price', tuple(
        (j, Fraction(float(x))) for j, x in enumerate(coefficients) if x), Fraction(0)),)).require()


def support_graph(active, complete, units, point, *, job, threshold=0.):
    """Activate full-native primitive support, not a guessed physical path.

Every new index is from the independently produced complete graph. Zero
variables can be removed; the rebuilt native block is independently replayed
before claiming it contains this LP direction. No rounded primal is accepted.
"""
    events = {n: set(v) for n, v in active.events.items()}
    states = {n: set(v) for n, v in active.states.items()}
    pairs, starts, ends, departures, arrivals, active_slots, link_slots = set(), set(), set(), set(), set(), set(), set()
    for unit in units:
        for family, items in unit['v'].items():
            for key, x in items.items():
                value = float(point[x[1]]) if x[0] == 'v' else float(x[1]+sum(
                    c*point[j] for j, c in zip(x[2], x[3]))) if x[0] == 'e' else float(x[1])
                if value <= threshold: continue
                if family in events: events[family].add(key)
                if family in states: states[family].add(key)
                if family == 'pair': pairs.add(key)
                if family == 'wan_start': starts.add(key)
                if family == 'wan_final': ends.add(key)
                if family == 'depart': departures.add(key)
                if family == 'arrive': arrivals.add(key)
                if family in ('wan_active','sent'): active_slots.add(key)
                if family == 'link_bytes': link_slots.add(key)
    for key, tr in complete.transfers.items():
        if (key[0], key[1]) in pairs and key[2] in starts: events['w'].add(key)
    # Fractional pair/start/finish LP directions need not correspond to one
    # physical path. Retain a canonical physical timing-envelope witness for
    # every positive native primitive, including unused pair/time envelopes.
    requirements=[]
    # Native byte quantum/rate rows depend on the pair roster, including
    # zero-valued pairs. Preserve that authority with a canonical envelope
    # for each pair; deleting a pair could rescale a positive sent/remaining
    # coordinate even though its own point value was zero.
    requirements += [lambda key,tr,p=p:(key[0],key[1])==p
                     for p in sorted({(k,d) for k,d,t in complete.events['w']})]
    requirements += [lambda key,tr,p=p:(key[0],key[1])==p for p in sorted(pairs)]
    requirements += [lambda key,tr,t=t:key[2]==t for t in sorted(starts)]
    requirements += [lambda key,tr,t=t:tr.end-1==t for t in sorted(ends)]
    requirements += [lambda key,tr,k=k:key[0]==k[0] and key[2]==k[1] for k in sorted(departures)]
    requirements += [lambda key,tr,k=k:key[1]==k[0] and tr.restart==k[1] for k in sorted(arrivals)]
    requirements += [lambda key,tr,t=t:key[2]<=t<tr.end for t in sorted(active_slots)]
    requirements += [lambda key,tr,k=k:any((l,t)==k for l,t,n in tr.wan if n>0) for k in sorted(link_slots)]
    for test in requirements:
        if any(test(key,complete.transfers[key]) for key in events['w']): continue
        hit=next((key for key,tr in sorted(complete.transfers.items()) if test(key,tr)),None)
        if hit is None: raise ValueError('FULL_NATIVE_POSITIVE_PRIMITIVE_MISSING_PHYSICAL_ENVELOPE')
        events['w'].add(hit)
    # Count histograms induce all physically valid STAYs at admitted Y starts.
    for site,start in tuple(events['y']):
        finish=(site,start+job.service_slots)
        if finish in complete.events['f0']:
            events['f0'].add(finish)
            states['r0'].update((site,t) for t in range(start,finish[1]))
    compatible = {key: tuple(start for start in values if (key[0], start) in events['y'])
                  for key, values in complete.compatible.items() if key in events['q']}
    physical = {key: value for key, value in complete.physical.items()
                if (key[0], key[1]) in events['q'] and (key[0], key[2]) in events['y']}
    transfers = {key: complete.transfers[key] for key in events['w']}
    result = Graph({n: tuple(sorted(v)) for n, v in events.items()},
        {n: tuple(sorted(v)) for n, v in states.items()}, compatible, physical, transfers, None)
    result.sha = graph_content_hash(result)
    return result
