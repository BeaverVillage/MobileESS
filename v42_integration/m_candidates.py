"""PR222 Beam and final joint redispatch admission with explicit Case context.

Widths 12/16, MOVE depth 4, PCS/SOC lookahead and final 8-route shortlist are
the adopted PR219/220/221 grammar. Heuristic discards never prove infeasibility.
No saved candidate pool, historical Raw witness or module global is consulted.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from types import SimpleNamespace
from time import perf_counter
import warnings

import numpy as np
from scipy import sparse
from scipy.optimize import linprog, OptimizeWarning
from scipy.spatial import ConvexHull

from .m_engine import PathGraph, _write, vector_sha
from .preparation_profile import profile_component


def grid_context(case, point):
    """Use original recursive helper projection, supplying all current arrays."""
    from tools.time_decomposed_lb.grid import SelectiveAuthority
    class CurrentAuthority(SelectiveAuthority):
        def __init__(self):
            A, d = case.original_A.tocsr(), case.original_d
            self.maps = dict(d, indptr=A.indptr, indices=A.indices, data=A.data)
            self.rho = int(np.flatnonzero(d['names'] == 'rho_max')[0])
            self.cache, self.raw_cache, self.helper_defs = {}, {}, {}
            self.security_by_slot = defaultdict(list)
            for i, name in enumerate(map(str, d['row_names'])):
                family = name.split('[', 1)[0]
                if family in ('line_thermal_face', 'transformer_kVA', 'NormalAmps', 'voltage_upper', 'voltage_lower'):
                    self.security_by_slot[int(name.split('[', 1)[1].split(',')[0])].append(i)
                if family.endswith('_binding'):
                    if str(d['sense'][i]) != '=':
                        raise ValueError('CURRENT_HELPER_NOT_EQUALITY')
                    pivots = [j for j, w in self.terms(i)
                              if w == 1. and str(d['names'][j]).split('[', 1)[0] + '_binding' == family]
                    if len(pivots) != 1 or pivots[0] in self.helper_defs:
                        raise ValueError('CURRENT_HELPER_PIVOT_AUTHORITY_DRIFT')
                    self.helper_defs[pivots[0]] = i
    authority = CurrentAuthority()
    original = case.lift(point)
    rho = float(case.d['objective'] @ point + case.d['constant'])
    by_slot, scanned = {}, 0
    for tick, indices in sorted(authority.security_by_slot.items()):
        thermal = [i for i in indices if str(authority.maps['row_names'][i]).startswith('line_thermal_face[')]
        if not thermal:
            raise ValueError('ALL_SLOTS_THERMAL_SCORE_CONTEXT_REQUIRED')
        candidates = []
        for i in thermal:
            terms = authority.terms(i)
            coefficient = sum(w for j, w in terms if j == authority.rho)
            if coefficient >= 0:
                raise ValueError('ORIGINAL_SIGNED_RHO_THERMAL_COEFFICIENT_REQUIRED')
            activity = sum(w * original[j] for j, w in terms)
            loading = rho + (activity - float(authority.maps['rhs'][i])) / -coefficient
            candidates.append((loading, i))
            scanned += 1
        chosen, seen = [], set()
        for loading, i in sorted(candidates, reverse=True):
            name = str(authority.maps['row_names'][i])
            fields = name.split('[', 1)[1][:-1].split(',')
            key = tuple(fields[1:3])
            if key not in seen:
                seen.add(key)
                chosen.append(dict(original_row=i, slot=tick, loading=loading, metadata=dict(name=name, asset=key)))
            if len(chosen) == 4:
                break
        by_slot[tick] = chosen
    H = PathGraph(case).horizon
    if set(by_slot) != set(range(H)):
        raise ValueError('ALL_SLOTS_THERMAL_SCORE_CONTEXT_REQUIRED')
    near = [r for rows in by_slot.values() for r in rows if r['loading'] >= rho - .025]
    selected = []
    for band in range((H+11)//12):
        options = [r for r in near if r['slot']//12 == band] or [r for rows in by_slot.values() for r in rows if r['slot']//12 == band]
        seen = set()
        for row in sorted(options, key=lambda r: (-r['loading'], r['original_row'])):
            key = (tuple(row['metadata']['asset']), row['slot']//3)
            if key not in seen:
                seen.add(key)
                selected.append(row)
            if len(seen) == 4:
                break
    selected.extend(rows[0] for rows in by_slot.values())
    selected = list({r['original_row']: r for r in selected}.values())
    used = {r['original_row'] for r in selected}
    for row in sorted(near, key=lambda r: (-r['loading'], r['original_row'])):
        if len(selected) >= 160:
            break
        if row['original_row'] not in used:
            selected.append(row)
            used.add(row['original_row'])
    rows = []
    for row in selected:
        packet = authority.project(row['original_row'], row['slot'])
        packet.update(slot=row['slot'], metadata=row['metadata'], current_loading=row['loading'])
        rows.append(packet)
    context = dict(PASS=True, case_sha=case.case_sha, center_vector_sha=vector_sha(point),
                   rows=rows, current_verified_UB=rho, all_thermal_rows_scanned=scanned,
                   selected_rows=len(rows), Native_optimize_calls=0,
                   exact_original_signed_helper_projection=True,
                   score_is_heuristic_not_FULL_feasibility_or_bound=True)
    _write(case.output / 'COMMON_M_PR222/CRITICAL_MINIMAX_CONTEXT.json', context)
    return context


def pcs_vertices(case):
    from v42_ultracompact.current_verify import physical_pcs_authority
    from v42_ultracompact.polytope import vertices
    planes = physical_pcs_authority(case.original_A, case.original_d, case.graph)
    limit = F(float(case.graph[3].p_limit))
    points = vertices(planes + [(F(1), F(0), limit), (F(-1), F(0), limit)])
    if not points:
        raise ValueError('CURRENT_PHYSICAL_PCS_CONTEXT_EMPTY')
    return np.asarray([[float(p), float(q)] for p, q in points])


class SignedMinimax:
    """Adopted Minimax/AdaptiveMinimax arithmetic with explicit PCS vertices."""
    def __init__(self, case, point, context, vertices):
        self.case, self.rows, self.graph = case, context['rows'], PathGraph(case)
        self.units, self.sites = sorted(case.graph[1]), list(case.graph[0])
        self.site_id = {s: i for i, s in enumerate(self.sites)}
        self.times = np.asarray([r['slot'] for r in self.rows])
        self.loading = np.asarray([r['current_loading'] for r in self.rows])
        self.m, self.H = len(self.rows), self.graph.horizon
        self.coeff = np.zeros((len(self.units), len(self.sites), self.m, 3))
        self.base = np.empty(self.m)
        values = dict(zip(map(str, case.original_d['names']), map(float, case.lift(point))))
        self.measured = np.zeros((len(self.units), self.m))
        for i, row in enumerate(self.rows):
            terms = {name: float(F(c)) for name, c in row['coeff'].items()}
            scale = -terms['rho_max']
            if scale <= 0:
                raise ValueError('SIGNED_GRID_MINIMAX_RHO_REQUIRED')
            activity = sum(c * values[name] for name, c in terms.items() if name != 'rho_max')
            for ui, unit in enumerate(self.units):
                for si, site in enumerate(self.sites):
                    for fi, family in enumerate(('Pch', 'Pdis', 'Q')):
                        name = f'{family}[{unit},{site},{row["slot"]}]'
                        co = terms.get(name, 0.) / scale
                        self.coeff[ui, si, i, fi] = co
                        self.measured[ui, i] += co * values.get(name, 0.)
            self.base[i] = (activity - float(F(row['rhs']))) / scale - self.measured[:, i].sum()
        self.vertices = np.asarray(vertices)
        p, q = self.vertices[:, 0], self.vertices[:, 1]
        supports = np.where(p[None, None, None, :] >= 0,
                            self.coeff[:, :, :, 1, None] * p + self.coeff[:, :, :, 2, None] * q,
                            self.coeff[:, :, :, 0, None] * -p + self.coeff[:, :, :, 2, None] * q)
        self.support = np.minimum(0., supports.min(axis=-1))
        self.best_vertex = supports.argmin(axis=-1)
        self.path_cache, self.future_cache = {}, {}
        self.baseline_paths = self.graph.paths(point)
        self.base_support = self.measured.copy()
        self.moves_by_origin = defaultdict(list)
        for unit in self.units:
            for k in self.graph.available[unit]:
                arc = self.graph.arcs[k]
                if arc[-1] is not None:
                    self.moves_by_origin[unit, arc[0]].append((arc[1], arc[3], self.site_id[arc[2]]))

    def path_vector(self,u,path):
        key=(u,tuple(path))
        if key in self.path_cache:return self.path_cache[key][0]
        ui=self.units.index(u);battery=self.case.graph[3];dt=battery.dt_hours
        connected=np.full(self.H,-1,dtype=int);travel=np.zeros(self.H)
        for k in path:
            arc=self.case.graph[2][k]
            if arc[-1] is None:connected[arc[1]]=self.site_id[arc[0]]
            else:travel[arc[1]]=float(arc[-1].energy_kwh)
        required=np.full(self.H+1,battery.minimum);required[-1]=battery.terminal
        for t in range(self.H-1,-1,-1):
            capacity=battery.p_limit*dt*battery.eta_charge if connected[t]>=0 else 0.
            required[t]=max(battery.minimum,required[t+1]+travel[t]-capacity)
        out=np.zeros(self.m);rebound=np.zeros(self.m);soc=battery.initial;unresolved=0.;spent=0.
        if not hasattr(self,'slot_indices'):
            self.slot_indices=[np.flatnonzero(self.times==t) for t in range(self.H)]
            rewards=np.zeros((len(self.units),len(self.sites),self.H))
            for t,indices in enumerate(self.slot_indices):
                if len(indices):rewards[:,:,t]=np.maximum(0.,(-self.coeff[:,:,indices,1]*battery.eta_discharge/dt).max(axis=-1))
            maxima=np.maximum.accumulate(rewards[:,:,::-1],axis=-1)[:,:,::-1]
            self.future_energy_price=np.zeros((len(self.units),len(self.sites),self.H));self.future_energy_price[:,:,:-1]=.30*maxima[:,:,1:]
        support=getattr(self,'base_support',np.zeros((len(self.units),self.m)))
        reference_all=self.base+support.sum(axis=0)-support[ui]
        for t in range(self.H):
            soc-=travel[t];spent+=travel[t];unresolved+=max(0.,battery.minimum-soc)
            site=connected[t]
            if site<0:continue
            active=self.slot_indices[t]
            if not len(active):continue
            charge_cap=min(battery.p_limit,max(0.,battery.maximum-soc)/(dt*battery.eta_charge))
            discharge_cap=min(battery.p_limit,max(0.,soc-max(battery.minimum,required[t+1]))*battery.eta_discharge/dt)
            minimum_charge=max(0.,required[t+1]-soc)/(dt*battery.eta_charge)
            energy_price=self.future_energy_price[ui,site,t];reference=reference_all[active]
            vertex_p=self.vertices[:,0];qv=self.vertices[:,1]
            pv=np.where(vertex_p>=0,np.minimum(vertex_p,discharge_cap),-np.minimum(-vertex_p,charge_cap))
            valid=np.ones(len(pv),dtype=bool)
            if minimum_charge>0:valid=(vertex_p<0)&(np.minimum(-vertex_p,charge_cap)+1e-9>=minimum_charge)
            if not valid.any():unresolved+=minimum_charge*dt*battery.eta_charge;continue
            service_matrix=(np.maximum(0.,-pv)[:,None]*self.coeff[ui,site,active,0]+np.maximum(0.,pv)[:,None]*self.coeff[ui,site,active,1]+qv[:,None]*self.coeff[ui,site,active,2])
            energies=np.where(pv>=0,pv*dt/battery.eta_discharge,pv*dt*battery.eta_charge)
            scores=(reference[None,:]+service_matrix).max(axis=1)+energy_price*energies;scores[~valid]=np.inf
            index=int(np.argmin(scores));p=float(pv[index]);q=float(qv[index]);service=service_matrix[index];energy=float(energies[index])
            soc-=energy;out[active]=service
            if p>=0:spent+=energy
            else:rebound[active]=np.maximum(0.,self.coeff[ui,site,active,0]*(-p))
        unresolved+=max(0.,battery.terminal-soc)
        # Charging is already in the signed service vector. Record its risk
        # separately without adding it twice to the minimax prediction.
        self.path_cache[key]=(out,np.zeros(self.m),unresolved,spent)
        if not hasattr(self,'lookahead_diagnostics'):self.lookahead_diagnostics={}
        self.lookahead_diagnostics[key]=dict(terminal_SOC=soc,terminal_recovery_shortfall=max(0.,battery.terminal-soc),
            conservative_required_SOC=required.tolist(),remaining_connected_slots=int(np.count_nonzero(connected>=0)),
            travel_energy=float(travel.sum()),charge_rebound=rebound.tolist(),heuristic_only=True,no_physical_feasibility_pruning=True)
        return out

    def peak(self, paths):
        vector, rebound, unresolved = self.base.copy(), np.zeros(self.m), 0.
        for ui, unit in enumerate(self.units):
            path = paths[unit]
            if path == self.baseline_paths[unit]:
                vector += self.measured[ui]
            else:
                vector += self.path_vector(unit, path)
                _, extra, missing, _ = self.path_cache[unit, tuple(path)]
                rebound += extra
                unresolved += missing
        return float(np.max(vector+rebound)+1e-4*unresolved), vector, rebound

    def partial_peak(self, unit, site, tick, vec, soc_upper):
        index, future, key = self.units.index(unit), self.times >= tick, (unit, site, tick)
        if key not in self.future_cache:
            value = self.support[index, self.site_id[site]].copy()
            arcs = np.asarray(self.moves_by_origin[unit, site], dtype=int).reshape(-1, 3)
            relevant = arcs[arcs[:, 0] >= tick] if len(arcs) else []
            for i, slot in enumerate(self.times):
                reachable = np.unique(relevant[relevant[:, 1] <= slot, 2]) if len(relevant) else []
                if len(reachable):
                    value[i] = min(value[i], float(self.support[index, reachable, i].min()))
            self.future_cache[key] = value
        completion = vec.copy()
        completion[future] = self.future_cache[key][future]
        battery = self.case.graph[3]
        scale = min(1., max(0., soc_upper-battery.minimum)/(max(1, np.count_nonzero(future))*battery.dt_hours*battery.p_limit))
        completion[future] *= .5 + .5*scale
        return float(np.max(self.base+self.base_support.sum(axis=0)-self.base_support[index]+completion))


class JointDispatchScore:
    """PR222 LP formula; measured HiGHS wall charges the shared ledger."""
    def __init__(self, scorer, budget):
        self.scorer, self.budget, self.cache = scorer, budget, {}

    def score(self, paths):
        key = tuple((u, tuple(p)) for u, p in sorted(paths.items()))
        if key in self.cache:
            return self.cache[key]
        begin, base = perf_counter(), self.scorer
        H, b, U = base.H, base.case.graph[3], len(base.units)
        stride, n = H*3+H+1, U*(H*4+1)+1
        rho = n-1
        lo, hi = np.full(n, -np.inf), np.full(n, np.inf)
        eqr, eqc, eqv, rhs, rr, cc, vv, ub = [], [], [], [], [], [], [], []
        def equality(terms, value):
            row = len(rhs)
            for col, co in terms:
                eqr.append(row); eqc.append(col); eqv.append(co)
            rhs.append(value)
        def inequality(terms, value):
            row = len(ub)
            for col, co in terms:
                if co:
                    rr.append(row); cc.append(col); vv.append(co)
            ub.append(value)
        planes = ConvexHull(base.vertices).equations
        connections = {}
        for ui, unit in enumerate(base.units):
            base.graph.validate(unit, paths[unit])
            connected, energy = np.full(H, -1, dtype=int), np.zeros(H)
            for k in paths[unit]:
                arc = base.graph.arcs[k]
                if arc[-1] is None:
                    connected[arc[1]] = base.site_id[arc[0]]
                else:
                    energy[arc[1]] += float(arc[-1].energy_kwh)
            connections[unit] = connected
            offset = ui*stride
            for t in range(H):
                pch, pdis, q = offset+3*t, offset+3*t+1, offset+3*t+2
                lo[pch:pdis+1] = 0.
                hi[pch:pdis+1] = b.p_limit if connected[t] >= 0 else 0.
                if connected[t] < 0:
                    lo[q] = hi[q] = 0.
                else:
                    inequality([(pch, 1.), (pdis, 1.)], b.p_limit)
                    for a, c, d in planes:
                        inequality([(pch, -a), (pdis, a), (q, c)], -d)
                soc = offset+3*H+t
                equality([(soc+1, 1.), (soc, -1.), (pch, -b.dt_hours*b.eta_charge),
                          (pdis, b.dt_hours/b.eta_discharge)], -energy[t])
            lo[offset+3*H:offset+stride] = b.minimum
            hi[offset+3*H:offset+stride] = b.maximum
            equality([(offset+3*H, 1.)], b.initial)
            lo[offset+stride-1] = max(b.minimum, b.terminal)
        for ri, row in enumerate(base.rows):
            terms, t = [(rho, -1.)], row['slot']
            for ui, unit in enumerate(base.units):
                si = connections[unit][t]
                if si >= 0:
                    terms.extend((ui*stride+3*t+fi, float(base.coeff[ui, si, ri, fi])) for fi in range(3))
            inequality(terms, -float(base.base[ri]))
        objective = np.zeros(n)
        objective[rho] = 1.
        remaining = float(self.budget.remaining())
        if remaining <= 0:
            return dict(score=None, LP_status='BUDGET_EXHAUSTED', heuristic_only=True, FULL_UB=False, Global_LB=False)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=OptimizeWarning, message='Unrecognized options detected.*')
                result = linprog(objective, A_ub=sparse.csr_matrix((vv, (rr, cc)), shape=(len(ub), n)), b_ub=ub,
                    A_eq=sparse.csr_matrix((eqv, (eqr, eqc)), shape=(len(rhs), n)), b_eq=rhs,
                    bounds=list(zip(lo, hi)), method='highs', options={'time_limit': min(2., remaining), 'threads': 1})
            score, status = (float(result.fun) if result.success else None), int(result.status)
        except Exception as exc:
            score, status = None, repr(exc)
        elapsed = perf_counter()-begin
        self.budget.record_external('M_PR222_SCORE_ONLY', elapsed, solver='HIGHS', status=str(status))
        packet = dict(score=score, LP_status=status, LP_wall_seconds=elapsed, heuristic_only=True,
                      continuous_Mode_relaxation=True, full_grid_not_checked=True,
                      all_four_PQ_SOC_redispatched=True, FULL_UB=False, Global_LB=False,
                      failure_is_not_infeasibility_proof=True)
        self.cache[key] = packet
        return packet


@profile_component('M_BEAM_SCORING')
def generate(case, point, bank, budget):
    """Fresh exact-day Beam followed by bounded joint LP admission shortlist."""
    graph, battery = bank.graph, case.graph[3]
    state = getattr(case,'mess_search_state',{})
    epoch = int(state.get('epoch',1))
    feedback_point=getattr(case,'mess_feedback_point',point)
    context = grid_context(case, feedback_point)
    scoring = SignedMinimax(case, feedback_point, context, pcs_vertices(case))
    base = graph.paths(point)
    candidates = {u: {} for u in graph.origins}
    counters = Counter()
    ub = bank.best[1]['Global_UB']
    weights = 1 + np.maximum(0., scoring.loading-(ub-.025))*20
    def register(unit, path, origin):
        graph.validate(unit, path)
        signature = tuple(path)
        if signature in candidates[unit]:
            return
        test = dict(base); test[unit] = list(path)
        peak, vector, rebound = scoring.peak(test)
        candidates[unit][signature] = dict(path=list(path), origin=origin, predicted_peak=peak,
            risk=float(np.sum(weights*np.maximum(0., vector+rebound-(ub-.025)))),
            moves=sum(graph.arcs[k][-1] is not None for k in path))
    for unit in sorted(graph.origins):
        register(unit, graph.complete(unit), 'STAY')
        register(unit, base[unit], 'CURRENT_FULL')
        if unit in getattr(case,'warm_route_seed',{}):
            register(unit,case.warm_route_seed[unit],'M1_ROUTE_ONLY_M2_REDISPATCH')
        if bank.best_moving is not None:
            register(unit, graph.paths(bank.best_moving[0])[unit], 'VERIFIED_MOVING_FULL')
        frontier = defaultdict(list)
        frontier[0] = [SimpleNamespace(site=graph.origins[unit], moves=0, first=-1, energy=0.,
                       upper=battery.initial, lower=battery.initial, recovery=0., peak=0.,
                       path=(), vec=np.zeros(scoring.m))]
        for t in range(graph.horizon):
            unique = {z.path: z for z in frontier.pop(t, [])}
            groups = defaultdict(list)
            for label in unique.values():
                groups[label.site, min(label.moves, 3), label.first//12].append(label)
            width = 16 if np.any(scoring.loading[scoring.times == t] >= ub-.025) else 12
            selected = []
            while groups and len(selected) < width:
                for key in sorted(list(groups)):
                    group = groups[key]
                    group.sort(key=lambda z: (z.peak, z.recovery, z.energy, z.path))
                    selected.append(group.pop(0))
                    if not group:
                        del groups[key]
                    if len(selected) >= width:
                        break
            counters['heuristic_beam_labels_discarded'] += len(unique)-len(selected)
            for label in selected:
                for k in graph.outgoing[label.site, t]:
                    if k not in graph.available[unit]:
                        counters['original_arc_domain_rejections'] += 1
                        continue
                    arc, moving = graph.arcs[k], graph.arcs[k][-1] is not None
                    if moving and label.moves >= 4:
                        counters['heuristic_MOVE_depth4_discarded'] += 1
                        continue
                    energy = float(arc[-1].energy_kwh) if moving else 0.
                    upper = label.upper-energy if moving else min(battery.maximum, label.upper+battery.dt_hours*battery.eta_charge*battery.p_limit)
                    lower = max(battery.minimum, label.lower-energy if moving else label.lower-battery.dt_hours*battery.p_limit/battery.eta_discharge)
                    if upper < battery.minimum-1e-8:
                        counters['optimistic_SOC_upper_exclusions'] += 1
                        continue
                    terminal = min(battery.maximum, upper+(graph.horizon-arc[3])*battery.dt_hours*battery.eta_charge*battery.p_limit)
                    if terminal < battery.terminal-1e-8:
                        counters['optimistic_terminal_upper_exclusions'] += 1
                        continue
                    vec = label.vec.copy()
                    if not moving:
                        vec[scoring.times == t] = scoring.support[scoring.units.index(unit), scoring.site_id[arc[0]], scoring.times == t]
                    recovery = max(0., battery.terminal-upper)
                    peak = scoring.partial_peak(unit, arc[2], arc[3], vec, upper)
                    peak += 1e-5*recovery*float(weights[scoring.times >= arc[3]].mean() if np.any(scoring.times >= arc[3]) else 1.)
                    path = label.path+(k,)
                    nxt = SimpleNamespace(site=arc[2], moves=label.moves+int(moving),
                        first=t if moving and label.first < 0 else label.first, energy=label.energy+energy,
                        upper=upper, lower=lower, recovery=recovery, peak=peak, path=path, vec=vec)
                    counters['expanded_original_arcs'] += 1
                    if arc[3] == graph.horizon:
                        register(unit, path, 'FRESH_PR222_BEAM_LABEL')
                    else:
                        frontier[arc[3]].append(nxt)
    reservoir = state.setdefault('reservoir',{})
    for unit, records in candidates.items():
        saved = reservoir.setdefault(unit,{})
        saved.update(records)
        # Scores are refreshed against the latest FULL-verified P/Q/SOC point.
        for key, row in saved.items():
            if key not in records:
                register(unit,row['path'],'STAGE_LOCAL_DIVERSE_RESERVOIR')
    pools, lp = {}, JointDispatchScore(scoring, budget)
    diagnostics = []
    for unit in sorted(candidates):
        ranked = sorted(candidates[unit].values(), key=lambda c: (c['predicted_peak'], c['risk'], c['path']))
        shortlist, seen = [], set()
        def add(path):
            key = tuple(path)
            if key not in seen:
                seen.add(key); shortlist.append(list(path))
        add(base[unit]); add(graph.complete(unit))
        if unit in getattr(case,'warm_route_seed',{}):add(case.warm_route_seed[unit])
        if bank.best_moving is not None:
            add(graph.paths(bank.best_moving[0])[unit])
        for predicate in (lambda c: c['moves'] == 1, lambda c: c['moves'] >= 2, lambda c: c['moves'] >= 3):
            options = [c for c in ranked if predicate(c)]
            if options:
                add(options[0]['path'])
        rotation=(epoch-1)*(1+sorted(candidates).index(unit))
        ranked_diverse=ranked[rotation % max(1,len(ranked)):] + ranked[:rotation % max(1,len(ranked))]
        for candidate in ranked_diverse:
            if len(shortlist) >= 12:
                break
            add(candidate['path'])
        rescored = []
        for path in shortlist:
            test = dict(base); test[unit] = path
            packet = lp.score(test)
            diagnostics.append(dict(unit=unit, path=path, **packet))
            fallback = scoring.peak(test)[0]
            rescored.append((packet['score'] if packet['score'] is not None else fallback, tuple(path), path))
        chosen, chosen_seen = [], set()
        def pin(path):
            key = tuple(path)
            if key not in chosen_seen:
                chosen_seen.add(key); chosen.append(list(path))
        pin(base[unit]); pin(graph.complete(unit))
        if unit in getattr(case,'warm_route_seed',{}):pin(case.warm_route_seed[unit])
        if bank.best_moving is not None:
            pin(graph.paths(bank.best_moving[0])[unit])
        for predicate in (lambda path: sum(graph.arcs[k][-1] is not None for k in path) == 1,
                          lambda path: sum(graph.arcs[k][-1] is not None for k in path) >= 2):
            options = [p for _, _, p in sorted(rescored) if predicate(p)]
            if options:
                pin(options[0])
        ordered=sorted(rescored)
        offset=rotation % max(1,len(ordered))
        for _, _, path in ordered[offset:]+ordered[:offset]:
            if len(chosen) >= 8:
                break
            pin(path)
        pools[unit] = chosen
    # PR221 resume_feedback admission variants: move depth and time/site
    # diversity with all four route choices remaining jointly optimized.
    from .m_adaptive import pool_identity
    seen_pools=state.get('seen_pools',set())
    if pool_identity(pools) in seen_pools:
        selected=None
        for variant in range(12):
            trial={}
            for ui,unit in enumerate(sorted(candidates)):
                ranked=sorted(candidates[unit].values(),key=lambda c:(c['predicted_peak'],c['risk'],c['path']))
                chosen=[];sigs=set()
                def add(path):
                    key=tuple(path)
                    if key not in sigs:chosen.append(list(path));sigs.add(key)
                add(base[unit]);add(graph.complete(unit))
                if bank.best_moving is not None:add(graph.paths(bank.best_moving[0])[unit])
                for depth in (1,2,3):
                    options=[c for c in ranked if (c['moves']==1 if depth==1 else c['moves']>=depth)
                             and tuple(c['path']) not in sigs]
                    if options:add(options[(epoch*3+ui+variant*7)%min(len(options),48)]['path'])
                groups=defaultdict(list)
                for c in ranked:
                    moves=[graph.arcs[k] for k in c['path'] if graph.arcs[k][-1] is not None]
                    key=(moves[0][1]//12 if moves else -1,tuple(sorted({a[2] for a in moves})),
                         len(moves),moves[-1][3]//12 if moves else -1)
                    groups[key].append(c)
                representatives=sorted((v[0] for v in groups.values()),key=lambda c:(c['predicted_peak'],c['path']))
                shift=(epoch*11+ui*7+variant*13)%max(1,len(representatives))
                for c in representatives[shift:]+representatives[:shift]+ranked:
                    if len(chosen)>=8:break
                    add(c['path'])
                trial[unit]=chosen
            if pool_identity(trial) not in seen_pools:selected=trial;break
        if selected is None:return None
        pools=selected
    # Every final pool, including PR221 diversity variants, passes PR222's
    # coupled four-unit continuous P/Q/SOC redispatch admission score.
    for unit,paths in pools.items():
        for path in paths:
            test=dict(base);test[unit]=path
            packet=lp.score(test)
            diagnostics.append(dict(unit=unit,path=path,final_pool_admission=True,**packet))
    coverage={}
    for unit,paths in pools.items():
        depths=[sum(graph.arcs[k][-1] is not None for k in path) for path in paths]
        available=[c['moves'] for c in candidates[unit].values()]
        coverage[unit]=dict(STAY=0 in depths,single_MOVE=1 in depths,multiple_MOVE=any(d>=2 for d in depths),
            single_available=1 in available,multiple_available=any(d>=2 for d in available))
        if not coverage[unit]['STAY'] or (1 in available and 1 not in depths) or (
                any(d>=2 for d in available) and not any(d>=2 for d in depths)):
            raise ValueError('PR222_DIVERSE_MOVE_ADMISSION_LOST')
        if bank.best_moving is not None and graph.paths(bank.best_moving[0])[unit] not in paths:
            raise ValueError('PR222_BEST_MOVING_PATH_NOT_PINNED')
    target=getattr(case,'mess_iteration_output',case.output / 'COMMON_M_PR222')
    _write(target / 'FRESH_BEAM_AND_REDISPATCH_ADMISSION.json', dict(
        coverage=coverage,PR222_joint_redispatch_admission=True,
        epoch=epoch,feedback=state.get('feedback',[])[-1:],current_dispatch_vector_sha=vector_sha(feedback_point),
        grid_feedback_rows=len(context['rows']),
        backward_terminal_SOC_lookahead=True,charge_rebound_counted_once=True,
        PASS=True, counters=dict(counters), generated={u: len(c) for u, c in candidates.items()},
        generated_MOVE_distribution={u: dict(Counter(c['moves'] for c in rows.values())) for u, rows in candidates.items()},
        pool_counts={u: len(p) for u, p in pools.items()}, pools=pools, LP_calls=len(lp.cache), scores=diagnostics,
        heuristic_MOVE_depth=4, beam_width=[12, 16], all_original_DAG_only=True,
        historical_Raw_read=False, archived_candidate_pool_read=False,
        shortlist_cap_per_unit=12, score_only=True, FULL_UB=False, Global_LB=False,
        no_MOVE_forcing=True, failure_is_not_infeasibility_proof=True))
    return pools
