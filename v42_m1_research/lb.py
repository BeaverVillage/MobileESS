"""Finite four-fleet multi-time retained-grid research, separate from production.

The deletion-only relaxation is not advertised as a strengthening.  Original
binary types and all96-slot physical rows remain.  Route-conflict inequalities
are valid necessary conditions; their material bound power is measured rather
than inferred from a fractional-point rejection.
"""
from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from time import perf_counter
import numpy as np
from scipy import sparse
import gurobipy as gp
from .check_lb import check_retained_relaxation, check_dual_certificate, check_rational_dual_certificate, check_route_conflicts_against_graph, check_integer_count_cover

GRID = {'line_thermal_face','transformer_kVA','voltage_upper','voltage_lower'}


def family(name):
    return str(name).split('[',1)[0]


def variable_slot(name):
    """Native variable identity, never generic constraint-name inference."""
    name = str(name)
    if '[' not in name:
        return None
    f, suffix = name.split('[',1)
    axis = suffix[:-1].split(',')
    if f.startswith('response_'):
        return int(axis[0])
    if f in {'Pch','Pdis','Q','injection_P','injection_Q','node_activity','SOC','charge_mode'}:
        return int(axis[-1])
    return None


def row_slots(A, d):
    """Grid incidence through original response/injection/electrical columns."""
    slots = np.asarray([-1 if variable_slot(n) is None else variable_slot(n) for n in d['names']], dtype=int)
    result = {}
    for i, n in enumerate(d['row_names']):
        if family(n) not in GRID:
            continue
        a,b = A.indptr[i:i+2]
        times = set(map(int, slots[A.indices[a:b]])) - {-1}
        if len(times) == 1:
            result[i] = times.pop()
        elif len(times) > 1:
            raise ValueError('GRID_ROW_HAS_MULTIPLE_NATIVE_TIME_AXES')
    return result


@dataclass
class RetainedRelaxation:
    A: object
    d: dict
    retained_rows: np.ndarray
    requirements: dict
    inclusion: dict


def prepare(case, *, max_grid_rows=24, target_rho=.60):
    begin = perf_counter()
    A,d,x = case.A, case.d, case.point
    times = row_slots(A,d)
    rho = int(np.flatnonzero(d['names']=='rho_max')[0])
    residual = A @ x - d['rhs']
    # Rank requirements at the diagnostic cutoff, retaining their separate
    # original rows.  The cutoff itself is not imposed on R or original F.
    records = []
    for i,t in times.items():
        if not 66 <= t <= 95:
            continue
        coefficient = float(A[i,rho])
        sense = str(d['sense'][i])
        sg = -1 if sense == '>' else 1
        violation = sg*(float(residual[i])+coefficient*(target_rho-float(x[rho])))
        scale = max(1e-12, abs(float(d['rhs'][i])), float(np.max(np.abs(A.data[A.indptr[i]:A.indptr[i+1]]))))
        records.append((violation/scale, i, t, family(d['row_names'][i])))
    selected = []
    # Six separated critical times; no4-slot convex-hull expansion. One best
    # thermal requirement per time plus independently chosen voltage/trafo.
    anchors = (66,72,78,84,90,95)
    for t in anchors:
        options = sorted((r for r in records if r[2]==t and r[3]=='line_thermal_face'), reverse=True)
        selected += options[:2]
    for f in ('voltage_upper','voltage_lower','transformer_kVA'):
        for t in (66,78,90,95):
            options = sorted((r for r in records if r[2]==t and r[3]==f), reverse=True)
            if options:
                selected.append(options[0])
    selected = selected[:max_grid_rows]
    picked = {r[1] for r in selected}
    keep = np.asarray([i for i,n in enumerate(d['row_names']) if family(n) not in GRID or i in picked], dtype=np.int64)
    R = A[keep].tocsr()
    e = dict(d, **{k:d[k][keep].copy() for k in ('rhs','sense','row_names')})
    inclusion = check_retained_relaxation(A,d,R,e,keep,case_sha=case.case_sha,point=x)
    requirement = dict(status='ORIGINAL_SEPARATE_MULTITIME_REQUIREMENTS', case_sha=case.case_sha,
        selected_original_grid_rows=[dict(row=i,slot=t,family=f,diagnostic_score=float(score),
            sense=str(d['sense'][i]),rhs=float(d['rhs'][i]),
            original_coefficients_SHA256=sha256(A.data[A.indptr[i]:A.indptr[i+1]].tobytes()).hexdigest(),
            variables=list(map(int,A.indices[A.indptr[i]:A.indptr[i+1]]))) for score,i,t,f in selected],
        all_original_physics_rows_retained=True, retained_rows=R.shape[0], columns=R.shape[1],
        nnz=R.nnz, target_rho_diagnostic_only=target_rho,
        validated_integer_UB_for_ranking=float(d['objective']@x+float(d['constant'])),
        required_global_LB_for_half_percent=float(d['objective']@x+float(d['constant']))*.995,
        target_rho_is_not_imposed_as_original_domain_bound=True,
        scalar_grid_aggregation=False, independent_inclusion=inclusion,
        preparation_wall_seconds=perf_counter()-begin)
    return RetainedRelaxation(R,e,keep,requirement,inclusion)


def latest_validated_ub(case, path):
    """Forward the already completed UB track through a fresh independent gate.

    Only a local dataclass replacement changes the witness used for ranking
    and MIP start. Scientific arrays, authority and caseSHA remain immutable.
    """
    from pathlib import Path
    from .check_ub import validate_candidate,vector_sha
    from v42_unified.audit import ROOT
    from v42_unified.storage import sha
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError('LATEST_UB_MUST_BE_D_V42_RESEARCH_OUTPUT')
    initial=float(case.d['objective']@case.point+float(case.d['constant']))
    receipt=dict(case_sha=case.case_sha,source='FROZEN_VALIDATED_ORIGINAL_INCUMBENT',
        validated_integer_UB=initial,required_global_LB_for_half_percent=initial*.995,
        point_sha256=vector_sha(case.point),native_optimize_calls=0,scientific_case_changed=False)
    if not path.exists():return case,receipt
    before=sha(path)
    with np.load(path,allow_pickle=False) as z:
        if z.files!=['point']:raise ValueError('LATEST_UB_POINT_FILE_KEYS_DRIFT')
        point=z['point'].copy()
    if sha(path)!=before:raise ValueError('LATEST_UB_POINT_CHANGED_DURING_READ')
    check=validate_candidate(case,point)
    if not check['PASS'] or check['case_sha']!=case.case_sha:
        raise ValueError('LATEST_UB_INDEPENDENT_ORIGINAL_REPLAY_FAILED')
    receipt.update(source_path=str(path),source_sha256=before,independent_original_replay=check)
    if check['objective']>initial:
        receipt['worse_candidate_not_adopted']=True
        return case,receipt
    receipt.update(source='LATEST_UB_TRACK_INDEPENDENTLY_REVALIDATED',
        validated_integer_UB=check['objective'],required_global_LB_for_half_percent=check['objective']*.995,
        point_sha256=check['point_sha256'],local_witness_replaced=True)
    return replace(case,point=point),receipt


def build_model(relaxation, *, env=None, continuous=False, cuts=()):
    begin = perf_counter()
    R,e=relaxation.A,relaxation.d
    model=gp.Model('V42_M1_JOINT_96_SLOT_RESEARCH_R',env=env)
    try:
        model.Params.OutputFlag=0
        model.Params.Threads=1
        model.Params.FeasibilityTol=1e-8
        model.Params.OptimalityTol=1e-8
        model.Params.IntFeasTol=1e-8
        model.Params.MIPGap=.005
        kind=np.full(R.shape[1],'C') if continuous else e['types']
        v=model.addMVar(R.shape[1],lb=e['lower'],ub=e['upper'],vtype=kind,obj=e['objective'])
        v.VarName=e['names'].tolist()
        model.ObjCon=float(e['constant'])
        model.addMConstr(R,v,e['sense'],e['rhs'])
        for cut in cuts:
            j,k=cut['columns']
            model.addConstr(v[int(j)]+v[int(k)]<=1,name='MULTITIME_ROUTE_CONFLICT')
        model.update()
        return model,dict(build_wall_seconds=perf_counter()-begin,rows=model.NumConstrs,columns=model.NumVars,
            binary=model.NumBinVars,nnz=model.NumNZs,continuous_relaxation=continuous,
            solver_parameters=dict(Threads=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=.005),
            finite_memory_limits=False)
    except BaseException:
        model.dispose()
        raise


def dual_packet(model, relaxation):
    """Prepare sign-safe evidence; independent checker performs all mathematics."""
    try:
        dual=np.asarray(model.getAttr('Pi'),dtype=np.float64)
    except (gp.GurobiError, AttributeError):
        return None
    if len(dual)!=relaxation.A.shape[0]:
        return None  # Newly added rows need separate independently checked axis.
    senses=relaxation.d['sense']
    clipped=int(np.sum((senses=='<')&(dual>0))+np.sum((senses=='>')&(dual<0)))
    dual[(senses=='<')&(dual>0)]=0
    dual[(senses=='>')&(dual<0)]=0
    return dual,dict(sign_clipped_rows=clipped,optimality_claimed=False,
                     source_rows=relaxation.retained_rows.tolist())


def repair_affine_equality_duals(A,d,dual):
    """Exact triangular auxiliary-column residual repair, no Native solve.

    Only original equality multipliers change. All <=/>= multipliers retain
    their signs. An independent rational checker computes the resulting bound.
    """
    begin=perf_counter()
    A=A.tocsr()
    y=np.asarray(dual,dtype=np.float64)
    if y.shape!=(A.shape[0],) or not np.isfinite(y).all():
        raise ValueError('REPAIR_DUAL_AXIS_OR_FINITE_DRIFT')
    senses=d['sense']
    y=y.copy()
    y[(senses=='<')&(y>0)]=0
    y[(senses=='>')&(y<0)]=0
    q={int(i):Fraction(float(y[i])) for i in np.flatnonzero(y)}
    vf=[family(n) for n in d['names']]
    defs={}
    for i,n in enumerate(d['row_names']):
        f=family(n)
        if not f.endswith('_binding') or d['sense'][i]!='=':continue
        a,b=A.indptr[i:i+2]
        matches=[int(j) for j in A.indices[a:b] if vf[int(j)]==f[:-8]]
        if len(matches)!=1:raise ValueError('AFFINE_REPAIR_PIVOT_NOT_UNIQUE')
        if matches[0] in defs:raise ValueError('AFFINE_REPAIR_DUPLICATE_DEFINITION')
        defs[matches[0]]=i
    # Reverse dependency elimination: a response equality changes injection
    # residuals, so responses must be repaired before injection equalities.
    used_by={j:set() for j in defs}
    dependencies={}
    for j,i in defs.items():
        a,b=A.indptr[i:i+2]
        dependencies[j]={int(k) for k in A.indices[a:b] if int(k)!=j and int(k) in defs}
        for k in dependencies[j]:used_by[k].add(j)
    ready=[j for j in defs if not used_by[j]]
    order=[]
    while ready:
        j=ready.pop();order.append(j)
        for k in dependencies[j]:
            used_by[k].remove(j)
            if not used_by[k]:ready.append(k)
    if len(order)!=len(defs):raise ValueError('AFFINE_REPAIR_DEFINITION_CYCLE')
    products={}
    for i,v in q.items():
        a,b=A.indptr[i:i+2]
        for j,w in zip(A.indices[a:b],A.data[a:b]):
            j=int(j);products[j]=products.get(j,Fraction(0))+v*Fraction(float(w))
    changed=0
    for j in order:
        i=defs[j];a,b=A.indptr[i:i+2]
        terms=list(zip(A.indices[a:b],A.data[a:b]))
        pivot=next(Fraction(float(w)) for k,w in terms if int(k)==j)
        correction=(Fraction(float(d['objective'][j]))-products.get(j,Fraction(0)))/pivot
        if not correction:continue
        q[i]=q.get(i,Fraction(0))+correction
        if not q[i]:del q[i]
        for k,w in terms:
            k=int(k);products[k]=products.get(k,Fraction(0))+correction*Fraction(float(w))
        changed+=1
    if any(products.get(j,Fraction(0))!=Fraction(float(d['objective'][j])) for j in defs):
        raise ValueError('AFFINE_REPAIR_RESIDUAL_NOT_EXACTLY_ZERO')
    return {str(i):str(v) for i,v in q.items()},dict(
        status='EXACT_EQUALITY_MULTIPLIER_REPAIR_NO_NATIVE',changed_equalities=changed,
        auxiliary_residuals_cancelled_exactly=len(defs),inequality_multiplier_signs_unchanged=True,
        independently_certified_LB='REQUIRES_INDEPENDENT_RATIONAL_CHECKER',
        repair_wall_seconds=perf_counter()-begin)


def diagnose_fractional(d, point, graph=None):
    if point is None:
        return dict(status='NOT_AVAILABLE',fractional_structure='NOT_PROVEN')
    x=np.asarray(point)
    binary=np.flatnonzero(d['types']=='B')
    frac=binary[np.abs(x[binary]-np.rint(x[binary]))>1e-8]
    counts=Counter(family(d['names'][j]) for j in frac)
    records=[]
    for j in frac:
        t=variable_slot(d['names'][j])
        if t is not None and 66<=t<=95:
            records.append(dict(column=int(j),name=str(d['names'][j]),value=float(x[j])))
    records.sort(key=lambda r:abs(.5-r['value']))
    return dict(status='FRACTIONAL_NATIVE_LP_DIAGNOSIS',binary_total=len(binary),
                fractional_binary_total=len(frac),fractional_families=dict(counts),
                critical_window_fractional=records[:120],
                reduction_in_fractional_count_is_not_bound_improvement=True)


def route_conflicts(case, root_point=None, *, limit=12):
    """Small exact reachability clique pilot across two critical times per unit.

    These rows may already follow from the continuous network representation;
    their validity does not imply strengthened LB. No weak cut accumulation.
    """
    if root_point is None:
        return [],dict(status='NOT_PROVEN',reason='No fractional relaxation point available')
    sites,initial,arcs,_,_=case.graph
    edges=[[a[0],int(a[1]),a[2],int(a[3])] for a in arcs]
    by_depart={}
    for s,t,dest,connect in edges:
        by_depart.setdefault(t,[]).append((s,dest,connect))
    x=np.asarray(root_point)
    candidates={u:[] for u in initial}
    for j,name in enumerate(case.d['names']):
        n=str(name)
        if n.startswith('node_activity[') and x[j]>1e-8:
            u,s,t=n[14:-1].split(',');t=int(t)
            if 66<=t<=95:candidates[u].append((float(x[j]),j,s,t))
    result=[]
    for u, entries in candidates.items():
        entries=sorted(entries,reverse=True)[:24]
        for a in entries:
            if len(result)>=limit:break
            for b in entries:
                if a[3]>=b[3]:continue
                reached={(a[2],a[3])}
                for t in range(a[3],b[3]+1):
                    for s,dest,connect in by_depart.get(t,()):
                        if (s,t) in reached:reached.add((dest,connect))
                if (b[2],b[3]) not in reached:
                    result.append(dict(unit=u,columns=[int(a[1]),int(b[1])],arcs=edges,
                        fractional_LHS=a[0]+b[0],fractional_point_violation=a[0]+b[0]>1+1e-8))
                    break
    checked=check_route_conflicts_against_graph(case.A,case.d,result,case.graph,case_sha=case.case_sha)
    checked.update(status='VALID_ROUTE_CONFLICT_PILOT_BOUND_POWER_NOT_PROVEN',
                   joint_fleet_replacements_preserved=True,scalar_support_direction=False,
                   cuts_can_be_continuous_network_redundant=True,
                   all_four_fleets_and_96_slot_SOC_retained=True,
                   adopted=False,reason_not_adopted='Conflicts already follow from continuous unit-flow path decomposition; no stronger cut claimed')
    return result,checked


def run_pilot(case, ledger, *, env=None, lp_seconds=300, mip_seconds=1200):
    """Two finite distinct scientific calls; never auto-certifies MIP BestBd."""
    started=perf_counter()
    case,ub_receipt=latest_validated_ub(case,ledger.path.parent/'FINAL_VALID_UB_POINT.npz')
    relaxation=prepare(case)
    relaxation.requirements['latest_validated_UB_forwarded_to_LB']=ub_receipt
    model,build=build_model(relaxation,env=env,continuous=True)
    try:
        native_lp=ledger.optimize(model,track='LB',label='JOINT_MULTITIME_R_LP',requested_seconds=lp_seconds)
        packet=dual_packet(model,relaxation)
        exact=check_dual_certificate(relaxation.A,relaxation.d,packet[0],
            source_rows=relaxation.retained_rows,case_sha=case.case_sha) if packet else dict(status='NOT_PROVEN',PASS=False,reason='No valid native LP dual vector')
        root_x=np.asarray(model.getAttr('X'),dtype=float) if model.SolCount else None
        diagnosis=diagnose_fractional(relaxation.d,root_x,case.graph)
        cuts,cover=route_conflicts(case,root_x)
    finally:
        model.dispose()
    # These reachability conflicts are already valid in the flow LP and cannot
    # exclude its point. Preserve the audit, but do not accumulate weak rows.
    model,mip_build=build_model(relaxation,env=env)
    try:
        model.setAttr('Start',model.getVars(),case.point.tolist())
        native_mip=ledger.optimize(model,track='LB',label='JOINT_MULTITIME_R_MILP',requested_seconds=mip_seconds)
        candidate=np.asarray(model.getAttr('X'),dtype=float) if model.SolCount else None
        result=dict(requirements=relaxation.requirements,inclusion=relaxation.inclusion,
            LP=dict(native=native_lp,build=build,certificate=exact),
            MILP=dict(native=native_mip,build=mip_build,
                certified_global_LB='NOT_PROVEN',native_BestBd_is_not_independent_certificate=True),
            cover=cover,fractional_diagnosis=diagnosis,
            independently_certified_R_LB=exact.get('independently_certified_LB'),
            original_global_integer_bound_from_MILP='NOT_PROVEN',
            no_local_child_or_neighborhood_bound_promoted=True,
            candidate_requires_original_full_physical_replay=True,
            phase_wall_seconds=perf_counter()-started,
            Native_Runtime_sum=float(native_lp.get('Native_Runtime',0))+float(native_mip.get('Native_Runtime',0)),
            measured_optimize_wall_seconds=float(native_lp.get('optimize_wall_seconds',0))+float(native_mip.get('optimize_wall_seconds',0)))
        result['non_native_build_validation_wall_seconds']=max(0.,result['phase_wall_seconds']-result['measured_optimize_wall_seconds'])
        result['outer_runner_cost_is_inclusive_of_native_optimize_wall']=True
        result['non_native_cost_accounting_rule']='pilot_wall_minus_sum_measured_optimize_wall; do not count inclusive outer runner context as non-native cost'
        return result,candidate,packet[0] if packet else None
    finally:
        model.dispose()


def prepare_count_disjunction(case,root_point):
    """Choose one finite complete jointfleet count split from a root point."""
    x=np.asarray(root_point,dtype=float)
    if x.shape!=(case.A.shape[1],):raise ValueError('COUNT_ROOT_POINT_AXIS_DRIFT')
    units=sorted(case.graph[1])
    by_group={}
    for j,n in enumerate(case.d['names']):
        n=str(n)
        if n.startswith('node_activity['):
            u,s,t=n[14:-1].split(',');t=int(t)
            if 66<=t<=95 and str(case.d['types'][j])=='B':by_group.setdefault((s,t),{})[u]=j
    choices=[]
    for group,mapping in by_group.items():
        if set(mapping)==set(units):
            cols=[mapping[u] for u in units]
            val=float(np.sum(x[cols]))
            fractional=sum(abs(x[j]-round(x[j]))>1e-8 for j in cols)
            if fractional:choices.append((fractional,abs(val-round(val)),group,cols,val))
    choices=sorted(choices,reverse=True)[:80]
    best=None
    for a in choices:
        for b in choices:
            if b[2][1]<=a[2][1] or abs(a[2][1]-b[2][1])<6:continue
            count=a[4]+b[4]
            loss=abs(count-round(count))
            if loss<=1e-7 or not 0<count<8:continue
            score=(loss,a[0]+b[0],abs(a[2][1]-b[2][1]))
            if best is None or score>best[0]:best=(score,a,b,count)
    if best is None:
        return [],dict(status='NOT_PROVEN',reason='No fractional four-fleet two-time integer count found; no fallback single-binary branch')
    _,a,b,count=best
    columns=a[3]+b[3]
    split=int(np.floor(count))
    row=sparse.csr_matrix((np.ones(8),(np.zeros(8,dtype=int),columns)),shape=(1,case.A.shape[1]))
    B=sparse.vstack([case.A,row],format='csr')
    leaves=[]
    for k,sense in enumerate(('<','>')):
        e=dict(case.d,rhs=np.r_[case.d['rhs'],float(split+k)],
            sense=np.concatenate([case.d['sense'],np.asarray([sense],dtype=case.d['sense'].dtype)]),
            row_names=np.concatenate([case.d['row_names'],np.asarray(['CNT'],dtype=case.d['row_names'].dtype)]))
        # The last axis denotes the independently proved count halfspace.
        axis=np.r_[np.arange(case.A.shape[0],dtype=np.int64),np.int64(-1-k)]
        leaves.append(RetainedRelaxation(B,e,axis,{},{}))
    cover=check_integer_count_cover(case.A,case.d,leaves,columns,split,units=units,case_sha=case.case_sha)
    cover.update(selected_root_fractional_count=count,fractional_count_removed_by_union=True,
        root_point_violates_both_integer_halfspaces=True,root_point_selection_is_not_a_validity_proof=True,
        full_96_slot_route_SOC_mode_PCS_grid_in_each_leaf=True,
        scalar_grid_requirements_aggregation=False,
        material_LB_strengthening='NOT_PROVEN_UNTIL_ALL_LEAF_CERTIFICATES_CHECKED')
    for leaf in leaves:leaf.inclusion=cover
    return leaves,cover


def run_count_disjunction(case,ledger,root_point,parent_dual,*,env=None,leaf_seconds=300,repair=True,parent_rational=None):
    """Complete joint-fleet disjunction; minALLleafcerts only, never childBestBd."""
    leaves,cover=prepare_count_disjunction(case,root_point)
    if not leaves:return dict(cover=cover,status='NOT_PROVEN'),{}
    parent=np.asarray(parent_dual,dtype=float)
    if parent.shape!=(case.A.shape[0],):raise ValueError('COUNT_PARENT_DUAL_AXIS_DRIFT')
    # Parent certificates are valid in each leaf after appending a zero
    # multiplier. Missing child duals therefore never invalidate completeness.
    parent=parent.copy()
    parent[(case.d['sense']=='<')&(parent>0)]=0
    parent[(case.d['sense']=='>')&(parent<0)]=0
    checked_parent=check_dual_certificate(case.A,case.d,parent,case_sha=case.case_sha)
    leaf_reports=[]
    artifacts={}
    for index,leaf in enumerate(leaves):
        leaf_started=perf_counter()
        model,build=build_model(leaf,env=env,continuous=True)
        try:
            native=ledger.optimize(model,track='LB',label=f'JOINT_FOUR_FLEET_COUNT_LEAF_{index}',requested_seconds=leaf_seconds)
            certificates=[]
            extended=np.r_[parent,0.]
            fallback=check_dual_certificate(leaf.A,leaf.d,extended,source_rows=leaf.retained_rows,case_sha=case.case_sha)
            certificates.append(dict(kind='CHECKED_PARENT_DUAL_ZERO_EXTENSION',certificate=fallback))
            artifacts[f'leaf_{index}_parent_dual']=extended
            if parent_rational is not None:
                stronger=check_rational_dual_certificate(leaf.A,leaf.d,parent_rational,source_rows=leaf.retained_rows,case_sha=case.case_sha)
                certificates.append(dict(kind='CHECKED_PARENT_RATIONAL_DUAL_ZERO_EXTENSION',certificate=stronger))
            packet=dual_packet(model,leaf)
            if packet:
                cert=check_dual_certificate(leaf.A,leaf.d,packet[0],source_rows=leaf.retained_rows,case_sha=case.case_sha)
                certificates.append(dict(kind='INDEPENDENT_NATIVE_CHILD_DUAL',certificate=cert))
                artifacts[f'leaf_{index}_native_dual']=packet[0]
                if repair:
                    rational,receipt=repair_affine_equality_duals(leaf.A,leaf.d,packet[0])
                    fixed=check_rational_dual_certificate(leaf.A,leaf.d,rational,source_rows=leaf.retained_rows,case_sha=case.case_sha)
                    certificates.append(dict(kind='EXACT_AFFINE_EQUALITY_REPAIRED_CHILD_DUAL',certificate=fixed,repair=receipt))
                    artifacts[f'leaf_{index}_repaired_rational_dual']=rational
            chosen=max(certificates,key=lambda r:r['certificate']['independently_certified_LB'])
            leaf_reports.append(dict(leaf=index,native=native,build=build,certificates=certificates,
                independently_certified_leaf_LB=chosen['certificate']['independently_certified_LB'],
                selected_certificate_kind=chosen['kind'],native_child_BestBd_promoted=False,
                non_native_build_validation_wall_seconds=max(0.,perf_counter()-leaf_started-float(native.get('optimize_wall_seconds',0)))))
        finally:
            model.dispose()
    bound=min(r['independently_certified_leaf_LB'] for r in leaf_reports)
    return dict(status='COMPLETE_COVER_ALL_LEAF_EXACT_BOUNDS_CERTIFIED',cover=cover,
        parent_exact_certificate=checked_parent,leaves=leaf_reports,
        independently_certified_global_LB=bound,
        gain_over_independently_checked_parent=bound-checked_parent['independently_certified_LB'],
        material_gain_at_least_0_001=bound-checked_parent['independently_certified_LB']>=.001,
        integer_count_fractional_point_excluded_is_not_bound_success=True,
        no_native_BestBd_promoted=True),artifacts


def run_joint_disjunction(case,ledger,output,*,leaf_seconds=300,env=None):
    """Durable runner adapter; imports only the last completed immutable M HEAD.

    The full ROOT archive is checked without a new baseline optimization.
    Exactly two full-domain disjunctive LP calls follow, with separate artifacts.
    """
    from pathlib import Path
    from .case import committed_file
    from v42_unified.audit import ROOT,write
    from v42_unified.storage import sha
    from v42_integrated.matrix import audit
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT.resolve()):raise ValueError('D_V42_RESEARCH_OUTPUT_REQUIRED')
    with ledger.cost('archive_and_validation','C3A_COMPLETED_ARCHIVE_EXACT_DUAL','LB'):
        path,receipt=committed_file('docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz')
        expected='7c7e2db497b6f7d41d978a42eb492baa2249138615fc3360f62143f37b8e2325'
        if sha(path)!=expected:raise ValueError('COMPLETED_C3A_ROOT_ARCHIVE_SHA_DRIFT')
        with np.load(path,allow_pickle=False) as z:
            if set(z.files)!={'x','Pi','RC'}:raise ValueError('COMPLETED_C3A_ROOT_ARCHIVE_KEYS_DRIFT')
            root_point=z['x'].copy();parent_dual=z['Pi'].copy();rc=z['RC'].copy()
        if root_point.shape!=(case.A.shape[1],) or parent_dual.shape!=(case.A.shape[0],) or rc.shape!=root_point.shape:
            raise ValueError('COMPLETED_C3A_ROOT_ARCHIVE_AXIS_DRIFT')
        root_audit=audit(case.A,case.d,root_point,integral=False,tolerance=1e-6)
        if not root_audit['PASS']:raise ValueError('ARCHIVED_ROOT_POINT_ORIGINAL_C3A_REPLAY_FAILED')
        parent_dual[(case.d['sense']=='<')&(parent_dual>0)]=0
        parent_dual[(case.d['sense']=='>')&(parent_dual<0)]=0
        raw=check_dual_certificate(case.A,case.d,parent_dual,case_sha=case.case_sha)
        rational,repair_receipt=repair_affine_equality_duals(case.A,case.d,parent_dual)
        repaired=check_rational_dual_certificate(case.A,case.d,rational,case_sha=case.case_sha)
        diagnosis=diagnose_fractional(case.d,root_point,case.graph)
        source=dict(case_sha=case.case_sha,source_receipt=receipt,root_point_original_C3A_replay=root_audit,
            native_ROOT_LP_objective_diagnostic=float(case.d['objective']@root_point+float(case.d['constant'])),
            native_ROOT_LP_objective_is_not_certified_LB=True,raw_exact_certificate=raw,
            repaired_exact_certificate=repaired,equality_repair=repair_receipt,
            new_baseline_native_optimize_calls=0,fractional_diagnosis=diagnosis,
            independently_certified_parent_LB=max(raw['independently_certified_LB'],repaired['independently_certified_LB']))
        np.savez_compressed(output/'C3A_CHECKED_ROOT_DUAL.npz',dual=parent_dual,point=root_point)
        write(output/'C3A_REPAIRED_RATIONAL_DUAL.json',rational)
        source['raw_dual_evidence']=dict(path=str(output/'C3A_CHECKED_ROOT_DUAL.npz'),sha256=sha(output/'C3A_CHECKED_ROOT_DUAL.npz'),npz_key='dual')
        source['repaired_dual_evidence']=dict(path=str(output/'C3A_REPAIRED_RATIONAL_DUAL.json'),sha256=sha(output/'C3A_REPAIRED_RATIONAL_DUAL.json'),format='SPARSE_ORIGINAL_ROW_EXACT_RATIONAL_MULTIPLIERS')
        write(output/'C3A_ROOT_SOURCE_AND_EXACT_CERTIFICATE.json',source)
    report,artifacts=run_count_disjunction(case,ledger,root_point,parent_dual,
        env=env,leaf_seconds=leaf_seconds,repair=True,parent_rational=rational)
    with ledger.cost('artifact_write','JOINT_COUNT_DUAL_AND_ROW_PROOF','LB'):
        for name,value in artifacts.items():
            if isinstance(value,dict):write(output/(name+'.json'),value)
            else:np.savez_compressed(output/(name+'.npz'),dual=value)
        write(output/'JOINT_COUNT_COMPLETE_ROW_PROOF.json',report['cover'])
        for leaf in report.get('leaves',[]):
            index=leaf['leaf']
            leaf['original_C3A_domain_plus_one_count_row']=dict(
                case_sha=case.case_sha,original_rows=case.A.shape[0],original_columns=case.A.shape[1],
                added_columns=report['cover']['original_binary_columns'],
                added_coefficients=[1.]*8,
                added_sense=report['cover']['exact_leaf_rows'][index]['sense'],
                added_rhs=report['cover']['exact_leaf_rows'][index]['rhs'],
                all_original_rows_bounds_types_objective_unchanged=True)
            for entry in leaf['certificates']:
                kind=entry['kind']
                if kind=='CHECKED_PARENT_RATIONAL_DUAL_ZERO_EXTENSION':
                    entry['dual_evidence']=source['repaired_dual_evidence']
                else:
                    suffix={'CHECKED_PARENT_DUAL_ZERO_EXTENSION':'parent_dual',
                        'INDEPENDENT_NATIVE_CHILD_DUAL':'native_dual',
                        'EXACT_AFFINE_EQUALITY_REPAIRED_CHILD_DUAL':'repaired_rational_dual'}[kind]
                    path=output/(f'leaf_{index}_{suffix}'+('.json' if 'RATIONAL' in kind or 'REPAIRED' in kind else '.npz'))
                    entry['dual_evidence']=dict(path=str(path),sha256=sha(path),
                        format='SPARSE_ORIGINAL_ROW_EXACT_RATIONAL_MULTIPLIERS' if path.suffix=='.json' else 'BINARY64_SIGN_SAFE_ROW_MULTIPLIERS',
                        npz_key='dual' if path.suffix=='.npz' else None)
        report['row_proof_evidence']=dict(path=str(output/'JOINT_COUNT_COMPLETE_ROW_PROOF.json'),sha256=sha(output/'JOINT_COUNT_COMPLETE_ROW_PROOF.json'))
    report['original_full_ROOT_source']=source
    report['baseline_independently_certified_global_LB']=source['independently_certified_parent_LB']
    if 'independently_certified_global_LB' in report:
        report['model_disjunction_gain_over_best_certified_original_ROOT']=report['independently_certified_global_LB']-source['independently_certified_parent_LB']
        report['material_global_gain_over_best_certified_original_ROOT']=report['model_disjunction_gain_over_best_certified_original_ROOT']>=.001
    return report
