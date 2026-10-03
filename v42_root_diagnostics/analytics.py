"""Post-hoc descriptive analyses. Contains no optimize or certificate writer."""
import re, math
from collections import Counter
from functools import reduce
from fractions import Fraction
from .common import *

TOLS=(1e-9,1e-8,1e-7)

def csvread(name):
    with (OUT/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def ratio(n,d):return float(n/d) if d else None

def primitive(indices,values,rhs,sense):
    """Exact primitive integer row, including RHS and inequality orientation."""
    fractions=[float(v).as_integer_ratio() for v in [*values,rhs]]
    exponent=max((d.bit_length()-1 for n,d in fractions),default=0)
    integers=[n << (exponent-(d.bit_length()-1)) for n,d in fractions]
    gcd=reduce(math.gcd,integers,0)
    if gcd:integers=[n//gcd for n in integers]
    first=next((n for n in integers if n),0)
    if first<0:
        integers=[-n for n in integers]
        sense={'<':'>','>':'<','=':'='}[str(sense)]
    return (tuple(map(int,indices)),tuple(integers),str(sense))

def duplicates_for(A,rhs,senses,families):
    seen={}; counts=Counter();nonzero_counts=Counter();constant_counts=Counter();pairfamilies=Counter();examples=[];zero=Counter();started=time.perf_counter()
    for i in range(A.shape[0]):
        a,b=A.indptr[i:i+2];inds=A.indices[a:b];vals=A.data[a:b]
        if not len(vals):zero[(str(senses[i]),float(rhs[i]).hex())]+=1
        key=primitive(inds,vals,rhs[i],senses[i]);h=hashlib.sha256(repr(key).encode()).digest()
        ref=seen.get(h)
        if ref is None:seen[h]=i;continue
        c,d=A.indptr[ref:ref+2];rv=A.data[c:d]
        assert key==primitive(A.indices[c:d],rv,rhs[ref],senses[ref]),'NORMALIZED_HASH_COLLISION'
        if str(senses[i])==str(senses[ref]) and rhs[i]==rhs[ref] and np.array_equal(vals,rv):kind='exact_duplicate'
        else:
            factor=Fraction.from_float(float(vals[0]))/Fraction.from_float(float(rv[0])) if len(vals) else Fraction.from_float(float(rhs[i]))/Fraction.from_float(float(rhs[ref]))
            kind='sign_reversed_proportional' if factor<0 else 'positive_proportional'
        counts[kind]+=1;(nonzero_counts if len(vals) else constant_counts)[kind]+=1;pairfamilies[(str(families[ref]),str(families[i]),kind)]+=1
        if len(examples)<30:
            factor=Fraction(1) if kind=='exact_duplicate' else Fraction.from_float(float(vals[0]))/Fraction.from_float(float(rv[0])) if len(vals) else Fraction.from_float(float(rhs[i]))/Fraction.from_float(float(rhs[ref]))
            examples.append(dict(row=i,representative=ref,kind=kind,exact_scalar_numerator=str(factor.numerator),exact_scalar_denominator=str(factor.denominator),constant_only=not bool(len(vals))))
    return dict(rows=A.shape[0],equivalence_classes=len(seen),redundant_rows_relative_to_first_representative=sum(counts.values()),
        counts=dict(counts),verified_hash_hits=sum(counts.values()),all_hash_hits_exactly_verified=True,
        nonzero_row_counts=dict(nonzero_counts),constant_only_row_counts=dict(constant_counts),
        zero_constant_rows=[dict(sense=s,rhs_hex=r,count=n) for (s,r),n in sorted(zero.items())],
        by_family=[dict(representative_family=x,row_family=y,kind=k,count=n) for (x,y,k),n in sorted(pairfamilies.items())],examples=examples,
        seconds=time.perf_counter()-started,proof='Exact binary64-as-dyadic-rational primitive integers including RHS and oriented sense. Each normalized hash hit is verified against exact normalized reference tuple. Counts are redundant rows relative to the first representative, not all pair combinations.',
        removal_authorized=False,near_duplicate_approximation='NOT_RUN')

def duplicate_audit():
    freeze_check();result={}
    for kind in ['original','compact']:
        with gp.Env(params={'OutputFlag':0}) as env:
            m=make(kind,env);A=m.getA().tocsr();A.sort_indices();rhs=m.getAttr('RHS');s=m.getAttr('Sense');m.dispose()
        print('EXACT_DUPLICATE_AUDIT',kind,flush=True)
        result[kind]=duplicates_for(A,rhs,s,row_families(kind))
    dump('DUPLICATE_PROPORTIONAL_ROWS.json',dict(formulations=result,certificate_adoption=False))
    return result

def degeneracy():
    results={};variables=[];active=[];candidates=[]
    for p in sorted(OUT.glob('ROOT_LP_METHOD[01]_*.json')):
        r=json.loads(p.read_text(encoding='utf8'))
        if r.get('basis_available'):candidates.append(r)
    p=OUT/'BASIS_ACQUISITION_ORIGINAL.json'
    if p.exists():
        r=read(p.name)
        if r.get('basis_available'):candidates.append(r)
    for r in candidates:
        label=r['label'];kind=r['formulation']
        with np.load(LOCAL/(label+'_SOLUTION.npz')) as z:
            x,lb,ub,rc,vb,slack,names=[z[k] for k in ['values','LB','UB','RC','VBasis','slack','names']];cb=z['CBasis']
        basic=vb==0;nonbasic=(vb==-1)|(vb==-2);superbasic=vb==-3
        vf=np.array([family(n) for n in names]);rf=row_families(kind);metrics={}
        for t in TOLS:
            at_bound=((lb>-gp.GRB.INFINITY)&(abs(x-lb)<=t))|((ub<gp.GRB.INFINITY)&(abs(x-ub)<=t))
            near=abs(rc)<=t;act=abs(slack)<=t;deg=basic&at_bound;neutral=nonbasic&near
            metrics[str(t)]=dict(basic_variables=int(basic.sum()),basic_at_bound=int(deg.sum()),primal_degenerate_basic_ratio=ratio(deg.sum(),basic.sum()),
                zero_basic_variables=int((basic&(abs(x)<=t)).sum()),nonbasic_variables=int(nonbasic.sum()),near_zero_RC_nonbasic=int(neutral.sum()),near_zero_RC_nonbasic_ratio=ratio(neutral.sum(),nonbasic.sum()),
                nonbasic_fixed_variables=int((nonbasic&(lb==ub)).sum()),nonbasic_nonfixed_near_zero_RC=int((neutral&(lb!=ub)).sum()),
                nonbasic_nonfixed_near_zero_RC_ratio=ratio((neutral&(lb!=ub)).sum(),(nonbasic&(lb!=ub)).sum()),superbasic_variables=int(superbasic.sum()),active_rows=int(act.sum()),active_row_ratio=ratio(act.sum(),len(act)))
            metrics[str(t)].update(basic_constraint_slacks=int((cb==0).sum()),basic_constraint_slacks_at_zero=int(((cb==0)&act).sum()),
                basic_constraint_slack_at_zero_ratio=ratio(((cb==0)&act).sum(),(cb==0).sum()))
            for f in sorted(set(vf)):
                mask=vf==f;variables.append(dict(label=label,formulation=kind,tolerance=t,family=f,columns=int(mask.sum()),basic=int((mask&basic).sum()),
                    basic_at_bound=int((mask&deg).sum()),zero_basic=int((mask&basic&(abs(x)<=t)).sum()),nonbasic=int((mask&nonbasic).sum()),near_zero_RC_nonbasic=int((mask&neutral).sum()),
                    primal_degenerate_basic_ratio=ratio((mask&deg).sum(),(mask&basic).sum()),near_zero_RC_nonbasic_ratio=ratio((mask&neutral).sum(),(mask&nonbasic).sum())))
            for f in sorted(set(rf)):
                mask=rf==f;active.append(dict(label=label,formulation=kind,tolerance=t,family=f,rows=int(mask.sum()),active_rows=int((mask&act).sum()),active_row_ratio=ratio((mask&act).sum(),mask.sum())))
        results[label]=dict(formulation=kind,metrics=metrics,Kappa=r['Kappa'],KappaExact=r['KappaExact'],KappaExact_reason=r['KappaExact_reason'],terminal_optimal=True,solution_sha256=r['solution_sha256'])
    dump('DEGENERACY_AUDIT.json',dict(status='MEASURED_FROM_TERMINAL_OPTIMAL_BASIS' if results else 'INCONCLUSIVE',bases=results,
        zero_step_pivot_count=None,zero_step_reason='Not exposed by Gurobi; high iteration counts alone do not establish degeneracy.',
        limitation='Terminal basis describes a measured optimal LP vertex; it does not count pivots or prove this is the sole cause of Method1 delay.',
        fallback=read('BASIS_ACQUISITION_ORIGINAL.json'),certificate_update=False))
    table('DEGENERACY_BY_VARIABLE_FAMILY.csv',variables,['label','formulation','tolerance','family','columns','basic','basic_at_bound','zero_basic','nonbasic','near_zero_RC_nonbasic','primal_degenerate_basic_ratio','near_zero_RC_nonbasic_ratio'])
    table('ACTIVE_ROW_FAMILY_AUDIT.csv',active,['label','formulation','tolerance','family','rows','active_rows','active_row_ratio'])
    return results

def residual(A,d,x):
    r=A@x-d['rhs'];v=np.where(d['sense']=='=',abs(r),np.where(d['sense']=='<',r,-r))
    return dict(max_row_violation=max(0.,float(v.max(initial=0))),rows_exceeding_1e8=int((v>1e-8).sum()),
        max_bound_violation=max(0.,float((d['lower']-x).max(initial=0)),float((x-d['upper']).max(initial=0))),
        objective=float(d['objective']@x+float(d['objcon'])),finite=bool(np.isfinite(x).all()),certificate_update=False)

def cache_data(label):
    with np.load(LOCAL/(label+'_DATA.npz')) as z:d={k:z[k] for k in z.files}
    return sparse.load_npz(LOCAL/(label+'_A.npz')),d

def reconstruct_kept_identity(E,keep,y):
    # Sparse multiplication may canonicalize -0.0 to +0.0 even on identity
    # coordinates. Copy all kept coordinates directly; substitute helpers only.
    full=E@y;full[keep]=y
    return full

def mappings():
    A,d=cache_data('ORIGINAL');S,sd=cache_data('ROW_SCALED_TRANSPORT_SAFE' if (OUT/'ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json').exists() else 'ROW_SCALED');P,pd=cache_data('AUX_ELIMINATED')
    E=sparse.load_npz(LOCAL/'AUX_RECONSTRUCTION_E.npz')
    with np.load(LOCAL/'AUX_MAP_AXES.npz') as z:keep=z['keep_columns'];rows=z['keep_rows'];removed=z['removed_columns']
    from v42_exact_start.common import primary_mask
    primary=primary_mask(d['names']);proof=read('AUXILIARY_ELIMINATION_PROOF.json');mapped=[];scale=[]
    for p in sorted(LOCAL.glob('*_SOLUTION.npz')):
        label=p.name[:-len('_SOLUTION.npz')];rp=OUT/(label+'.json')
        if not rp.exists():continue
        r=read(rp.name)
        if r.get('NON_SCIENTIFIC_DIAGNOSTIC_ONLY') or r.get('formulation')!='original' or r.get('no_Start') is not True:continue
        with np.load(p) as z:x=z['values']
        if r.get('variant')=='aux_eliminated':
            full=reconstruct_kept_identity(E,keep,x);back=full[keep];mapped.append(dict(label=label,direction='reduced_to_original',terminal_optimal=r['terminal_optimal'],
                reduced_audit=residual(P,pd,x),original_audit=residual(A,d,full),kept_roundtrip_max_difference=float(abs(back-x).max(initial=0)),
                primary_difference=float(abs(full[primary]-x[np.flatnonzero(primary[keep])]).max(initial=0)),
                objective_mapping_difference=abs(float(pd['objective']@x)-float(d['objective']@full)),
                removed_definition_residual=float(abs((A@full-d['rhs'])[np.setdiff1d(np.arange(A.shape[0]),rows)]).max(initial=0))))
        else:
            y=x[keep];full=reconstruct_kept_identity(E,keep,y);mapped.append(dict(label=label,direction='original_to_reduced',terminal_optimal=r['terminal_optimal'],
                original_audit=residual(A,d,x),reduced_audit=residual(P,pd,y),primary_roundtrip_max_difference=float(abs(full[primary]-x[primary]).max(initial=0)),
                removed_helpers_reconstruction_difference=float(abs(full[removed]-x[removed]).max(initial=0)),objective_mapping_difference=abs(float(pd['objective']@y)-float(d['objective']@x))))
        if r.get('variant')=='row_scaled' or r.get('variant') is None:scale.append(dict(label=label,terminal_optimal=r['terminal_optimal'],original_units_audit=residual(A,d,x),scaled_units_audit=residual(S,sd,x),identity_mapping=True))
    arms={label:read(label+'.json') for label in ['AUX_REFERENCE_METHOD1_300S','AUX_ELIMINATED_METHOD1_300S','AUX_ELIMINATED_METHOD2_600S'] if (OUT/(label+'.json')).exists()}
    terminal=[r['objective'] for r in arms.values() if r['terminal_optimal']]
    equivalent=all(abs(x-TARGET['original'])<=1e-8 for x in terminal) if terminal else None
    dump('AUX_ELIMINATION_DIAGNOSTIC.json',dict(prototype_scope=proof['prototype_scope'],exactness_proof_PASS=proof['solver_prototype_PASS'],
        status='NOT_RUN' if not terminal else 'MEASURED',reason='USER_STOP' if not terminal else None,
        objective_equivalence_status='NOT_EVALUATED_USER_STOP' if not terminal else 'PASS' if equivalent else 'FAIL',
        objective_equivalence_PASS=equivalent,terminal_objectives=terminal,arms=arms,mappings=mapped,removed_physical_constraints=0,removed_primary_variables=0,
        mapping_note='Removed-helper reconstruction uses IEEE arithmetic; all retained coordinates are directly copied to preserve bits, including signed zero. Exact algebraic inverse is proved separately. Numerical residuals are measured and disclosed.',certificate_update=False))
    dump('ROW_SCALING_MAPPING_AUDIT.json',dict(algebraic_proof=read('EXACT_ROW_SCALING_PROOF.json'),approved_transport_guard=read('ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json') if (OUT/'ROW_SCALING_TRANSPORT_SAFE_VALIDATION.json').exists() else None,point_mappings=scale,
        diagnostic=read('ROW_SCALED_METHOD1_DIAGNOSTIC.json'),native_reference=read('ROOT_LP_METHOD1_ORIGINAL.json'),
        note='Positive row scaling preserves the exact real feasible set; scaled tolerance residuals have different physical units. Only original-unit residuals assess physical consistency.',certificate_update=False))

_SIMPLEX=re.compile(r'^\s*(\d+)\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([\d.]+)s\s*$')

def parse_simplex(log):
    points=[]
    for line in log.splitlines():
        m=_SIMPLEX.match(line)
        if m:points.append(dict(iterations=int(m[1]),phase_objective=float(m[2]),primal_infeasibility=float(m[3]),dual_infeasibility=float(m[4]),t=float(m[5])))
    return points

def trajectory(points):
    # Logs may restart iteration counters between phases; no window crosses a restart.
    segments=[[]]
    for p in points:
        if segments[-1] and (p['iterations']<segments[-1][-1]['iterations'] or p['t']<segments[-1][-1]['t']):segments.append([])
        segments[-1].append(p)
    windows=[];spikes=[];speeds=[]
    for ss in segments:
        for a,b in zip(ss,ss[1:]):
            if b['t']>a['t']:speeds.append((b['iterations']-a['iterations'])/(b['t']-a['t']))
            if b['primal_infeasibility']>=100*max(a['primal_infeasibility'],1e-300) and b['primal_infeasibility']>0:spikes.append(dict(start=a,end=b))
        for i,a in enumerate(ss):
            for b in ss[i+1:]:
                di=b['iterations']-a['iterations']
                if di<5000:continue
                od=abs(b['phase_objective']-a['phase_objective'])/max(1,abs(a['phase_objective']))
                improvement=(a['primal_infeasibility']-b['primal_infeasibility'])/max(a['primal_infeasibility'],1e-100)
                if od<1e-6 and improvement<.01:windows.append(dict(start=a,end=b,iterations=di,seconds=b['t']-a['t'],relative_phase_objective_change=od,primal_feasibility_improvement=improvement))
    return dict(log_samples=len(points),iterations_per_second_min=min(speeds) if speeds else None,iterations_per_second_max=max(speeds) if speeds else None,
        iterations_per_second_median=float(np.median(speeds)) if speeds else None,longest_stagnation_interval=max(windows,key=lambda w:w['seconds']) if windows else None,
        stagnation_windows=len(windows),primal_infeasibility_spikes_ratio_100=spikes,first=points[0] if points else None,last=points[-1] if points else None,
        phase_objective_is_not_a_scientific_bound=True,zero_step_pivot_count=None,limitation='Sampled log endpoint windows; no unlogged pivot path or continuous stagnation claimed.')

def timelines():
    trajectories={};mips={}
    for p in sorted(OUT.glob('*.log')):
        trajectories[p.stem]=trajectory(parse_simplex(p.read_text(encoding='utf8',errors='replace')))
    for p in sorted(OLD.glob('*.log')):
        trajectories['PR126/'+p.stem]=trajectory(parse_simplex(p.read_text(encoding='utf8',errors='replace')))
    for kind in ['original','compact']:
        label='MIP_ROOT_METHOD2_'+kind.upper()+'_300S';r=read(label+'.json');events=r['events'];log=(OUT/(label+'.log')).read_text(encoding='utf8')
        barrier=events.get('barrier_completion_time');cross=events.get('crossover_start_time');root=events.get('root_relaxation_completion_time')
        root_values=re.findall(r'Root relaxation: objective\s+([-+\deE.]+)',log)
        pushes=re.findall(r'^\s*(\d+)\s+([DP]Pushes).*?([\d.]+)s\s*$',log,re.MULTILINE)
        crossover_headers=[s for s in log.splitlines() if 'crossover log' in s.lower()]
        crossover_durations=re.findall(r'Crossover time:\s*([\d.]+) seconds',log)
        push_completed=re.findall(r'Push phase complete:.*?([\d.]+)s',log)
        mips[kind]=dict(events=events,Start_accepted=r['Start_accepted'],barrier_completed=barrier is not None,crossover_observed=bool(cross is not None or crossover_headers),
            literal_crossover_headers=crossover_headers,crossover_start_callback_time=cross,
            literal_crossover_duration_seconds=float(crossover_durations[-1]) if crossover_durations else None,
            literal_push_phase_completion_logged_seconds=float(push_completed[-1]) if push_completed else None,
            first_crossover_push_logged_seconds=float(pushes[0][2]) if pushes else None,
            crossover_start_note='MIP header is Root crossover log; initial monitor recorded only Crossover log prefix. Literal header proves observation, but exact unrecorded header callback time remains null. First rounded push log time is an observation, not exact crossover start.',
            root_relaxation_completed=root is not None,root_relaxation_completion_time=root,root_processing_completion_time=None,
            crossover_completion_time=None,first_branch_time=None,first_nonroot_node_callback_time=events.get('first_nonroot_node_callback_time'),first_branch_observed=r['first_branch_observed'],
            observed_time_after_barrier_to_end=max(0,r['solver_runtime']-barrier) if barrier is not None else None,
            literal_root_relaxation_objective=float(root_values[-1]) if root_values else None,raw_solver_BestBd_at_end=r['raw_solver_BestBd'],
            crossover_push_samples=[dict(remaining=int(n),kind=k,logged_seconds=float(t)) for n,k,t in pushes],
            unresolved_phase_after_barrier='crossover / simplex cleanup / root processing; literal logs distinguish observations, exact unexposed event boundaries remain null',
            literal_root_lines=[x for x in log.splitlines() if x.startswith(('Barrier solved','Root relaxation:','Crossover log','Root crossover log','Cutting planes:','Explored '))],
            diagnostic_bounds_not_adopted=True)
    dump('ROOT_PHASE_TIMELINE.json',dict(MIP=mips,unexposed_events_remain_null=True,certificate_update=False))
    dump('ROOT_SIMPLEX_TRAJECTORY_ANALYSIS.json',dict(preregistered_definition=read('PREREGISTRATION.json')['stagnation'],arms=trajectories))

def bound_telemetry():
    observations=[]
    for p in sorted(OUT.glob('*.json')):
        r=read(p.name)
        if not isinstance(r,dict) or 'raw_solver_BestBd' not in r or 'label' not in r:continue
        obj=r['objective'];bound=r['raw_solver_BestBd']
        observations.append(dict(label=r['label'],terminal_optimal=r['terminal_optimal'],terminal_primal_objective=obj,raw_solver_ObjBound=bound,
            raw_bound_minus_primal_objective=(bound-obj) if bound is not None and obj is not None else None,
            raw_bound_above_terminal_primal_by_more_than_1e8=bool(bound is not None and obj is not None and bound>obj+1e-8),certificate_update=False))
    dump('DIAGNOSTIC_BOUND_TELEMETRY_AUDIT.json',dict(observations=observations,UB=UB,valid_retained_LB=LB,certificate_unchanged=True,
        note='Raw solver getter values are recorded without adoption. A getter bound above a terminal primal objective is explicitly flagged as numerical telemetry inconsistency, with cause unresolved. The registered equivalence gate compares terminal primal objectives and physical residuals, never infeasible-phase objective or raw getter bounds. No claim that a terminal LP result improves the stronger inherited valid LB.',
        extra_OPTIMIZE_calls=0))

def conditioning():
    census=csvread('MATRIX_FAMILY_CENSUS.csv');structure=read('MATRIX_STRUCTURAL_AUDIT.json');basis=read('DEGENERACY_AUDIT.json')['bases']
    positive_spreads={}
    for kind,path in [('original',LOCAL/'ORIGINAL_A.npz'),('compact',CACHE/'COMPACT_A.npz')]:
        A=sparse.load_npz(path);axes={}
        for name,B in [('row',A.tocsr()),('column',A.tocsc().T.tocsr())]:
            magnitudes=abs(B);norms=dict(L1=np.asarray(magnitudes.sum(axis=1)).ravel(),L2=np.sqrt(np.asarray(B.multiply(B).sum(axis=1)).ravel()),Linf=np.asarray(magnitudes.max(axis=1).toarray()).ravel())
            axes[name]={k:dict(minimum_positive=float(v[v>0].min()),maximum=float(v.max()),positive_max_min_ratio=float(v.max()/v[v>0].min()),zero_axes=int((v==0).sum())) for k,v in norms.items()}
        positive_spreads[kind]=axes
    dump('CONDITIONING_AUDIT.json',dict(matrix_structure=structure,basis_condition_estimates={k:dict(Kappa=v['Kappa'],KappaExact=v['KappaExact'],KappaExact_reason=v['KappaExact_reason']) for k,v in basis.items()},
        nonzero_axis_norm_spreads=positive_spreads,
        by_row_family=[{k:r[k] for k in ['formulation','family','axis_elements','dynamic_range','Linf_min','Linf_max','L2_min','L2_max','ratio_max',*[f'coefficient_ratio_gt_{t}' for t in [1e6,1e8,1e10,1e12]]]} for r in census],
        limitation='Coefficient spread and norm ratios are structural proxies, not a measured basis condition number. No terminal basis gives an INCONCLUSIVE basis-conditioning diagnosis.',certificate_update=False))

def grid_attribution():
    structure=read('MATRIX_STRUCTURAL_AUDIT.json');vr=csvread('DEGENERACY_BY_VARIABLE_FAMILY.csv');rr=csvread('ACTIVE_ROW_FAMILY_AUDIT.csv');basis={}
    for label in sorted(set(r['label'] for r in vr)):
        v=[r for r in vr if r['label']==label and float(r['tolerance'])==1e-8];a=[r for r in rr if r['label']==label and float(r['tolerance'])==1e-8]
        metrics={}
        for key in ['basic_at_bound','near_zero_RC_nonbasic']:
            total=sum(int(r[key]) for r in v);g=sum(int(r[key]) for r in v if GRID(r['family']));metrics[key]=dict(grid=g,total=total,share=ratio(g,total))
        total=sum(int(r['active_rows']) for r in a);g=sum(int(r['active_rows']) for r in a if GRID(r['family']));metrics['active_rows']=dict(grid=g,total=total,share=ratio(g,total));basis[label]=metrics
    formulation={k:dict(**s,grid_row_share=ratio(s['grid_rows'],s['rows']),grid_nnz_share=ratio(s['grid_nnz'],s['nnz']),grid_extreme_nnz_share=ratio(s['grid_extreme_nnz'],s['extreme_nnz'])) for k,s in structure.items()}
    isolates={p.stem:read(p.name) for p in sorted(OUT.glob('NON_SCIENTIFIC_REMOVE_*_120S.json'))}
    dump('GRID_BLOCK_ATTRIBUTION.json',dict(formulations=formulation,basis_burden=basis,auxiliary_proof=read('AUXILIARY_ELIMINATION_PROOF.json'),
        isolation=isolates,isolation_reference=read('ISOLATION_FULL_REFERENCE_120S.json') if (OUT/'ISOLATION_FULL_REFERENCE_120S.json').exists() else None,
        scope='GRID prefix includes injection, response, voltage, line and transformer. Native 81216 defined helpers = 4608 injection + 76608 response; no absent response_voltage_binding invented.',
        causal_limitation='Large structural share alone establishes burden, not exclusive causal mechanism. Invalid family removals cannot produce valid feasibility or bounds.',certificate_update=False))

def run():
    freeze_check();degeneracy();mappings();timelines();bound_telemetry();conditioning();grid_attribution();duplicate_audit();freeze_check()

if __name__=='__main__':run()
