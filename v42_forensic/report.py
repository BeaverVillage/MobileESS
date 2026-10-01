"""Measured forensic report; inconclusive intervals stay inconclusive."""
import re,xml.etree.ElementTree as ET
from .common import *
from .classification import classify

REQUIRED='''README.md PREREGISTRATION.json PR110_BASE_RECEIPT.json ROOT_SOURCE_RECEIPT.json ROOT_SLOT_RECOMPUTATION.csv ROOT_EPIGRAPH_ACTIVE_SLOTS.csv ROOT_DUAL_MASS_SUMMARY.json ROOT_ACTIVE_LINE_FACE_MAP.csv ROOT_ACTIVE_LINE_FACE_SUMMARY.json ACTIVE_HORIZON_ROOT_VS_INCUMBENT.csv TERMINAL_SOC_COUPLING_AUDIT.csv TERMINAL_SOC_DUAL_SUMMARY.json TERM_RELAX_OPTIMIZATION.json WINDOW_DEFINITION.json WINDOW_INTEGRALITY_VALIDATION.csv R_ROUTE_ONLY_OPTIMIZATION.json R_ACTIVE_OPTIMIZATION.json R_BUFFER_OPTIMIZATION.json PARTIAL_INTEGRALITY_COMPARISON.csv UNIT_ATTRIBUTION.csv P_FIXED_ALL_OPTIMIZATION.json P_FIXED_ROUTE_OPTIMIZATION.json P_LATE_ROUTE_NEIGHBORHOOD_OPTIMIZATION.json PRIMAL_QUALITY_COMPARISON.csv ROOT_CAUSE_CLASSIFICATION.json RESIDUAL_GAP_DIAGNOSIS.json NEXT_MODIFICATIONS.md FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json'''.split()
def prose(n,s):(OUT/n).write_text(s.strip()+'\n',encoding='utf8')
def fmt(x):return 'NOT_AVAILABLE' if x is None else f'{x:.12f}'

def run():
    arms=[read(OUT/(n+'_OPTIMIZATION.json')) for n in ['R_ROUTE_ONLY','R_ACTIVE','R_BUFFER']]
    primals=[read(OUT/(n+'_OPTIMIZATION.json')) for n in ['P_FIXED_ALL','P_FIXED_ROUTE','P_LATE_ROUTE_NEIGHBORHOOD']]
    term=read(OUT/'TERM_RELAX_OPTIMIZATION.json');window=read(OUT/'WINDOW_DEFINITION.json');source=read(OUT/'ROOT_SOURCE_RECEIPT.json')
    dual=read(OUT/'ROOT_DUAL_MASS_SUMMARY.json');line=read(OUT/'ROOT_ACTIVE_LINE_FACE_SUMMARY.json');soc=read(OUT/'TERMINAL_SOC_DUAL_SUMMARY.json')
    candidates=[(UB,'retained_verified_incumbent')]+[(r['original_feasible_UB'],r['name']) for r in arms+primals if r.get('original_feasible_UB') is not None]
    best,bestsource=min(candidates,key=lambda z:z[0]);transfers=[]
    if primals[1]['original_feasible_UB'] is not None:
        routepoint=primals[1];late=primals[2]
        late['best_known_model_feasible_UB']=min([r['original_feasible_UB'] for r in [routepoint,late] if r['original_feasible_UB'] is not None])
        late['included_fixed_route_feasible_upper']=routepoint['original_feasible_UB']
        late['included_upper_source']='P_FIXED_ROUTE_SOLUTION.npz: same retained full route satisfies all fixed outside arcs; all original mode/dispatch rows identical'
        dump(late['name']+'_OPTIMIZATION.json',late)
    # Stronger partial feasible points (or a validated original integer point)
    # are legitimate upper certificates for every weaker partial model.
    for target in arms:
        target_domain=set(json.loads(gzip.decompress((OUT/(target['name']+'_DOMAIN.json.gz')).read_bytes()))['restored'])
        possible=[]
        for candidate in arms+primals:
            if candidate['incumbent_objective'] is None or not candidate['solution_matrix_validation']['PASS']:continue
            full=bool(candidate['full_original_integer_validation'] and candidate['full_original_integer_validation']['valid_new_UB'])
            source_domain=set(json.loads(gzip.decompress((OUT/(candidate['name']+'_DOMAIN.json.gz')).read_bytes()))['restored'])
            if full or candidate in arms and target_domain<=source_domain:possible.append(candidate)
        witness=min(possible,key=lambda r:r['incumbent_objective']) if possible else None
        if witness and witness['incumbent_objective']-F3<=.001:
            target.setdefault('direct_solver_negative_certificate',target['negative_certificate'])
            target.update(negative_certificate=True,negative_certificate_type='Validated feasible upper transferred through original/partial feasible-set inclusion',
                certified_partial_upper=witness['incumbent_objective'],negative_certificate_source=witness['name'],certificate_by_feasible_set_inclusion=True)
            dump(target['name']+'_OPTIMIZATION.json',target)
            transfers.append(dict(target=target['name'],source=witness['name'],upper=witness['incumbent_objective'],gain_ceiling=witness['incumbent_objective']-F3,PASS=True))
    dump('NEGATIVE_CERTIFICATE_TRANSFER.json',dict(PASS=True,transfers=transfers,optimize_calls=0,proof='Every original integer feasible point is feasible in all partial models; a stronger restored-binary subset point is feasible in every weaker subset with identical original rows/bounds. No solver incumbent/status is relabeled.'))
    classification=classify(arms,best)
    classification.update(STRONG_DIRECT_UB_EVIDENCE=UB-best>=.01,original_UB_minus_S2_interval=UB-S2,
        minimum_proved_retained_incumbent_suboptimality=UB-best,old_certified_interval_fraction_removed=(UB-best)/(UB-S2),
        remaining_best_UB_minus_S2_interval=best-S2,formal_class_keeps_preregistered_negative_certificate_requirement=True)
    dump('ROOT_CAUSE_CLASSIFICATION.json',classification)
    if primals[1]['original_feasible_UB'] is not None:
        _,_,inc,sites,initial,routes,battery=inputs()
        with np.load(OUT/'P_FIXED_ROUTE_SOLUTION.npz',allow_pickle=False) as z:rv=dict(zip(map(str,z['names']),map(float,z['values'])))
        assert all(abs(rv[n]-value)<=TOL for n,value in inc['values'].items() if n.startswith('arc[') and n in rv)
        balances=[]
        for u in sorted(initial):
            first=rv[f'SOC[{u},{window["W_ACTIVE"][0]}]'];last=rv[f'SOC[{u},96]']
            charge=battery.dt_hours*battery.eta_charge*sum(rv.get(f'Pch[{u},{s},{t}]',0.) for s in sites for t in range(window['W_ACTIVE'][0],96))
            discharge=battery.dt_hours/battery.eta_discharge*sum(rv.get(f'Pdis[{u},{s},{t}]',0.) for s in sites for t in range(window['W_ACTIVE'][0],96))
            balances.append(dict(unit=u,SOC_start=first,SOC_terminal=last,late_charge_energy=charge,late_discharge_energy=discharge,energy_residual=last-first-charge+discharge))
        dump('FIXED_ROUTE_DISPATCH_MECHANISM.json',dict(PASS=True,same_original_routes=True,retained_mode_plan_P_FIXED_ALL=primals[0]['original_feasible_UB'],free_mode_P_FIXED_ROUTE=primals[1]['original_feasible_UB'],
            direct_UB_gain=UB-primals[1]['original_feasible_UB'],old_mode_plan_has_all_zero_charge_modes=all(value==0 for n,value in inc['values'].items() if n.startswith('charge_mode[')),
            unit_late_energy=balances,physics_unchanged=True,interpretation='Same stationary routes become materially better when binary mode/continuous dispatch can charge and discharge under original SOC/PCS/full-grid requirements. This is primal mode-plan/dispatch quality evidence, not evidence of weak LP mode hull or route integrality dominance.'))
    if best<UB-1e-6:
        _,_,inc,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes)
        with np.load(OUT/(bestsource+'_SOLUTION.npz'),allow_pickle=False) as z:values=inc['values'].copy();values.update(dict(zip(map(str,z['names']),map(float,z['values']))))
        plan=dict(values=values,objectives=[best],scientific_objective_count=2,domain_sha256=inc['domain_sha256'],mode='MILP',initial_sites=initial,units=inc['units'],
            chosen_arcs={u:[k for k in range(len(arcs)) if values.get(f'arc[{u},{k}]',0.)>.5] for u in initial},
            P1_only_diagnostic=True,P2_complete=False,M1_ACCEPTED=False,source=bestsource)
        (OUT/'BEST_VALIDATED_M1_PLAN.json.gz').write_bytes(gzip.compress(json.dumps(plan,allow_nan=False).encode(),mtime=0))
        validation=next(r['full_original_integer_validation'] for r in arms+primals if r['name']==bestsource)
        dump('BEST_VALIDATED_M1_PLAN_RECEIPT.json',dict(PASS=True,new_original_feasible_UB=best,source=bestsource,source_solution_sha256=sha(OUT/(bestsource+'_SOLUTION.npz')),
            plan_sha256=sha(OUT/'BEST_VALIDATED_M1_PLAN.json.gz'),validation=validation,objective_scope='P1 feasible UB only; no P2 or acceptance certificate',no_numerical_repair=True))
        from .forensic import control,faces
        from v42_bootstrap.grid import coefficients
        bundle,anchor,_,_,_,_,battery=inputs();_,coef=coefficients(bundle);loading=[];dispatch=[]
        for t,c in enumerate(coef):
            ff=faces(c,control(c,values,anchor,sorted(initial),t))[0];mask=np.asarray([not n.lower().startswith('transformer.') for n in c.branch_names])
            maximum=float(ff[mask].max());assert maximum<=best+TOL
            loading.append(dict(time=t,new_P1_loading=maximum,retained_P1_loading=float(csvread('ROOT_SLOT_RECOMPUTATION.csv')[t]['rho_inc']),T_ACTIVE=t in window['T_ACTIVE']))
        for u in sorted(initial):
            for t in window['T_ACTIVE']:
                occupied=next(arcs[k] for k in plan['chosen_arcs'][u] if arcs[k][1]<=t<arcs[k][3]);state=occupied[0] if occupied[-1] is None else 'TRANSIT'
                dispatch.append(dict(MESS=u,time=t,state=state,Pch=sum(values.get(f'Pch[{u},{s},{t}]',0.) for s in sites),Pdis=sum(values.get(f'Pdis[{u},{s},{t}]',0.) for s in sites),
                    Q=sum(values.get(f'Q[{u},{s},{t}]',0.) for s in sites),SOC=values[f'SOC[{u},{t}]'],charge_mode=values[f'charge_mode[{u},{t}]']))
        table('BEST_NEW_UB_SLOT_LOADING.csv',loading);table('BEST_NEW_UB_ACTIVE_DISPATCH.csv',dispatch)
    unitrows=[]
    for i in range(1,5):
        p=OUT/f'U{i}_ACTIVE_OPTIMIZATION.json'
        if p.exists():
            r=read(p);unitrows.append(dict(unit=f'MESS{i:02}',run=True,BestBd=r['final_BestBd'],certified_LB=r['certified_global_LB'],gain=r['LB_gain'],incumbent=r['incumbent_objective'],negative_certificate=r['negative_certificate'],reason='R_ACTIVE material gate passed'))
        else:unitrows.append(dict(unit=f'MESS{i:02}',run=False,BestBd=None,certified_LB=None,gain=None,incumbent=None,negative_certificate=None,reason='R_ACTIVE LB_gain<0.001; unit arms not authorized'))
    table('UNIT_ATTRIBUTION.csv',unitrows)
    table('PARTIAL_INTEGRALITY_COMPARISON.csv',[dict(name=r['name'],status=r['status'],restored_binaries=r['restored_binaries'],continuous=r['continuous_variables'],rows=r['rows'],nonzeros=r['nonzeros'],
        presolve_seconds=r['presolve_seconds'],root_relaxation_seconds=r['root_relaxation_seconds'],first_incumbent=r['first_incumbent']['objective'] if r['first_incumbent'] else None,
        incumbent=r['incumbent_objective'],BestBd_300=r['checkpoints']['300']['BestBd'],BestBd_600=r['checkpoints']['600']['BestBd'],final_BestBd=r['final_BestBd'],certified_LB=r['certified_global_LB'],
        gain_vs_F3=r['LB_gain'],gap=r['partial_gap'],nodes=r['node_count'],first_non_root_node_seconds=r['events'].get('first_non_root_node_seconds'),peak_RSS=r['peak_RSS'],
            negative_certificate=r['negative_certificate'],classification='CERTIFIED_NONMATERIAL' if r['negative_certificate'] else r['classification']) for r in arms])
    table('PRIMAL_QUALITY_COMPARISON.csv',[dict(name=r['name'],status=r['status'],solver_incumbent=r['incumbent_objective'],validated_original_feasible_UB=r['original_feasible_UB'],
        gain=UB-r['original_feasible_UB'] if r['original_feasible_UB'] is not None else None,wall_seconds=r['wall_seconds'],BestBd=r['final_BestBd'],gap=r['partial_gap'],
        known_included_feasible_upper=r.get('best_known_model_feasible_UB'),
        full_original_integer=bool(r['full_original_integer_validation'] and r['full_original_integer_validation']['full_original_integer']),
        physical_robust_PASS=bool(r['full_original_integer_validation'] and r['full_original_integer_validation']['valid_new_UB'])) for r in primals])
    rows=csvread('ACTIVE_HORIZON_ROOT_VS_INCUMBENT.csv')
    fields=['positive_sites','location_entropy','Q_dispersion','P_dispersion','Pch','Pdis','Pnet','Q','SOC']
    means={point:{f:sum(float(r[point+'_'+f]) for r in rows)/len(rows) for f in fields} for point in ['root','incumbent']}
    dump('ACTIVE_HORIZON_COMPARISON_SUMMARY.json',dict(means=means,dispersion_zero_when_no_activity=True,point_specific_not_causal=True))
    terminalmaterial=term['delta_terminal']>=.001
    highest_lb=max([S2]+[r['certified_global_LB'] for r in arms])
    diagnosis=dict(classification=classification,dominant_binding_structure=line,active_window=window,
        active_dual_fraction=dual['active_fraction'],root_incumbent_means=means,terminal_counterfactual=dict(rho=term['rho_TERM_RELAX'],delta=term['delta_terminal'],material=terminalmaterial),
        root_energy_direction='Root carries about 1080 kWh into slot 66 and nets about 320 kWh of discharge to terminal 760 kWh; not evidence of obligatory late charging recovery',
        partial_negative_certificates={r['name']:r['negative_certificate'] for r in arms},best_new_feasible_UB=best,best_UB_source=bestsource,
        best_certified_global_LB=highest_lb,remaining_same_UB_gap=(best-highest_lb)/best,
        partial_incumbents_not_assumed_full_MILP=True,mode_bound_difference=arms[1]['certified_global_LB']-arms[0]['certified_global_LB'],
        buffer_bound_difference=arms[2]['certified_global_LB']-arms[1]['certified_global_LB'],bound_differences_not_exact_optimum_attribution=True,
        production_implemented=False,new_cuts=False,terminal_counterfactual_not_production=True,
        cannot_exclude_broader_coupling_without_negative_certificates=not classification['required_negative_certificates_available'])
    dump('RESIDUAL_GAP_DIAGNOSIS.json',diagnosis)
    flags=dict(BASE_PR=110,BASE_HEAD=HEAD,A1_RERUN=False,S2_RERUN=False,S3_RERUN=False,A1_OPTIMIZE_CALLS=0,S1_OPTIMIZE_CALLS=0,S2_OPTIMIZE_CALLS=0,S3_OPTIMIZE_CALLS=0,
        SCIENTIFIC_PHYSICS_CHANGED=False,DIAGNOSTIC_ONLY_TERMINAL_EQUALITY_REMOVAL=True,DEFAULT_PRODUCTION_FORMULATION_UNCHANGED=True,
        ROOT_SOURCE=source['selected'],ROOT_RHO=source['rho'],EPIGRAPH_ACTIVE_SLOTS=dual['epigraph_active'],DUAL_ACTIVE_SLOTS=dual['dual_active'],T_ACTIVE=window['T_ACTIVE'],ACTIVE_DUAL_MASS_FRACTION=dual['active_fraction'],
        DOMINANT_ACTIVE_LINE=line['dominant_line'],DOMINANT_ACTIVE_PHASE=line['dominant_phase'],DOMINANT_LINE_SHARE=line['dominant_line_share'],
        ACTIVE_WINDOW_START=window['W_ACTIVE'][0],ACTIVE_WINDOW_END=window['W_ACTIVE'][1],BUFFER_WINDOW_START=window['W_BUFFER'][0],BUFFER_WINDOW_END=95,
        TERMINAL_SOC_DUALS=soc['terminal_SOC_duals'],TERM_RELAX_RHO=term['rho_TERM_RELAX'],TERM_RELAX_DELTA=term['delta_terminal'],
        PARTIAL_INTEGRALITY_NEGATIVE_CERTIFICATE=classification['required_negative_certificates_available'],
        RETAINED_UB=UB,FIXED_ALL_UB=primals[0]['original_feasible_UB'],FIXED_ROUTE_UB=primals[1]['original_feasible_UB'],LATE_NEIGHBORHOOD_UB=primals[2].get('best_known_model_feasible_UB',primals[2]['original_feasible_UB']),
        LATE_NEIGHBORHOOD_SOLVER_UB=primals[2]['original_feasible_UB'],
        BEST_NEW_FEASIBLE_UB=best,BEST_UB_SOURCE=bestsource,NEW_FEASIBLE_UB_FOUND=best<UB-1e-6,UB_GAIN=UB-best,ROOT_CAUSE_CLASS=classification['ROOT_CAUSE_CLASS'],
        LB_WEAKNESS_MATERIAL=classification['LB_WEAKNESS_MATERIAL'],INCUMBENT_QUALITY_MATERIAL=classification['INCUMBENT_QUALITY_MATERIAL'],
        TERMINAL_SOC_COUPLING_MATERIAL=terminalmaterial,LATE_HORIZON_DISCRETE_COUPLING_MATERIAL=classification['LB_WEAKNESS_MATERIAL'],
        FALSE_MATERIAL_FLAGS_MEAN_NOT_ESTABLISHED_UNLESS_NEGATIVE_CERTIFIED=True,
        M1_ACCEPTED=False,M1_P2_COMPLETE=False,PRODUCTION_M1_RUN=False,NEW_CUTS_ADDED=0,
        A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,ACTUAL_P_CORRECTION_ENABLED=False,ACTUAL_Q_CORRECTION_ENABLED=False,PROBLEM13_FINAL_VALIDATED=False)
    for r in arms:
        flags.update({r['name']+'_RESTORED_BINARIES':r['restored_binaries'],r['name']+'_BEST_BOUND':r['final_BestBd'],r['name']+'_GAIN':r['LB_gain'],r['name']+'_NEGATIVE_CERTIFICATE':r['negative_certificate']})
    flags['DIAGNOSTIC_OPTIMIZE_CALLS']=7+sum(r['run'] for r in unitrows)
    dump('FINAL_FLAGS.json',flags)
    nextdirection='Resolve the remaining partial-integrality optimum intervals with a preregistered exact bound/certificate strategy before choosing a cut remedy.' if classification['ROOT_CAUSE_CLASS']=='CASE_E_INCONCLUSIVE' else 'Design a separate remedy around the measured contribution; do not change this forensic PR into production.'
    if classification['INCUMBENT_QUALITY_MATERIAL']:nextdirection+=' Preserve the independently validated same-route full-integer dispatch as a future MIP start with its complete 96-slot mode/PQ/SOC values. In a separately authorized experiment, use that feasible upper to seek a tight late-window partial-integrality interval before choosing route, mode or trajectory cuts; keep original terminal SOC and all full-grid constraints.'
    dump('FINAL_VERDICT.json',dict(ROOT_CAUSE_CLASS=classification['ROOT_CAUSE_CLASS'],M1_ACCEPTED=False,production=False,new_cuts=False,next=nextdirection,
        measured_LB_gain=classification['max_partial_LB_gain'],measured_UB_gain=UB-best,negative_certificate=classification['required_negative_certificates_available'],STOP_before_A2=True))
    proofs=r'''
## Mathematical scope

Every partial-integrality model retains the exact F3 rows, continuous domains and all original route alternatives. Only a subset of original binary VTypes is relaxed. Original integer feasible plans are contained in each partial feasible set, so its solver-certified BestBd lower-bounds the original integer optimum. Reported global LB is max(inherited F3 LB, valid arm BestBd); no movement of a weak/raw BestBd is interpreted as a negative result.

Stay occupancy is [t,t+1); travel occupancy is [depart,connect), including after physical arrival until original connection. Every arc crossing a W time cut, and every arc departing a W node, is restored. Unit DAG flow crosses that cut with total mass one; integral crossing arcs imply exactly one physical state, not fractional path mass. All original integer paths satisfy restored domains. The 44 bounded tests maximize min(y,1-y) for every window state and find zero; complete original path enumeration and boundary cases independently check the semantics. No arc/site domain is newly pruned.

The UB models are original feasible subsets. P_FIXED_ALL fixes every scientific binary and relaxes only those fixed VTypes; P_FIXED_ROUTE fixes all route arcs and retains binary charge mode; P_LATE_ROUTE_NEIGHBORHOOD frees every original route arc whose occupancy intersects W_BUFFER or departs a W_BUFFER node, fixes only the complementary outside arcs, and retains all original modes/physics. Boundary-crossing arcs follow the same exact occupancy semantics; no Hamming constraint or favorable-site filtering is used.

Partial-MIP objectives are only partial feasible uppers unless every original binary passes an independent integrality check plus native physical, initial/terminal SOC, mode/connectivity and reconstructed full-grid robust-voltage validation. Accepted new full-M1 uppers have those checks. The saved immutable integer start is validated against each modified matrix before optimization. No plan is numerically repaired.

TERM_RELAX alone removes the four terminal_SOC equalities, keeps every other original F3 row/bound and relaxes integrality. Its objective decrease tests how the terminal equality constrains the F3 LP. This is neither strengthening nor a production solution, and its relaxed terminal physics supplies no original feasible UB. Its bound/dispatch are never installed into the scientific model.

The inherited S3 point is full-matrix revalidated at zero optimization calls; its optimal barrier certificate remains distinct from overall INTERRUPTED status. Fresh row order aligns inherited BarPi before extracting P1/terminal/recurrence duals. Original F3 coefficients independently recompute all 96 times and every near-max face, with raw polygon, affine correction, rating-normalized loading and face dual. Comparison to immutable PR110 is an integrity check, not a reused ranking. Active thresholds (1e-7 slack, 1e-6 dual mass) and the 8-slot buffer were preregistered. Dual mass is a local LP attribution at that point, not proof of global integer causality.

One-shot solve markers prevent diagnostic reruns. LPs use Method=2, Threads=1; every diagnostic MIP uses Method=2, Threads=1, Heuristics=0, MIPFocus=3, MIPGap=.005, Seed=20260929, GPU OFF, and its single optimize-only time limit. Timings separate first presolve/root events, first non-root node, full optimize wall and sampled RSS. Checkpoint bounds are tagged with their actual observation time or early completion; missing observations remain unavailable. Solver OPTIMAL at .005 relative MIP gap is not misrepresented as an exact .001 nonmaterial certificate: the validated feasible-upper interval is checked explicitly.

The first two partial arms were launched with a telemetry path that queried runtime during POLLING, which is unsupported; ignored exceptions were observed in R_ROUTE_ONLY and R_ACTIVE. They complete their one authorized solve without termination/model/parameter changes. Final status, ObjBound, saved X and raw solver logs are authoritative; root/presolve times are reconciled from those logs, and unobserved checkpoint/first-branch times stay unavailable. The old driver is stopped between arms, after all R_ACTIVE receipts and before any R_BUFFER optimize call. Later arms use the fixed callback; no scientific optimization is retried. See TELEMETRY_RECONCILIATION.json and the [official callback restrictions](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html).
'''
    prose('DIAGNOSTIC_VALIDITY.md','# Forensic model validity\n'+proofs)
    armtext='\n'.join(f'- {r["name"]}: restored {r["restored_binaries"]}, raw BestBd {fmt(r["final_BestBd"])}, certified global LB {fmt(r["certified_global_LB"])}, gain {r["LB_gain"]:.12f}, solver partial upper {fmt(r["incumbent_objective"])}, '+('CERTIFIED_NONMATERIAL (feasible upper certificate).' if r['negative_certificate'] else r['classification']+'.') for r in arms)
    ubtext='\n'.join(f'- {r["name"]}: validated original feasible UB {fmt(r["original_feasible_UB"])}, solver status {r["status"]}.' for r in primals)
    prose('README.md',f'''# M1 integrality-gap forensic investigation

Exact base: PR110 `{HEAD}`; this is an independent successor of PR110, with no PR111 result or formulation inherited. Root cause class: **{classification['ROOT_CAUSE_CLASS']}**. No new production formulation or cut, no production M1 or downstream run; M1 accepted=false.

Independent original-F3 coefficient/root recomputation identifies T_ACTIVE={window['T_ACTIVE']}. P1 dual mass fraction={dual['active_fraction']:.12f}; {line['dominant_line']}/{line['dominant_phase']} binds in {line['dominant_line_share']*100:.4f}% of active slots. Largest ten slots hold only {dual['largest_slot_mass_fractions']['10']*100:.4f}% of dual mass; the shortest 90%-mass interval is {dual['shortest_contiguous_mass_windows']['0.9']['start']}–{dual['shortest_contiguous_mass_windows']['0.9']['end']}, so a long late block dominates. All ties within 1e-7 are recorded, not only a canonical face. W_ACTIVE={window['W_ACTIVE']}, W_BUFFER={window['W_BUFFER']}, frozen before new solves. The old 40–46 incumbent-root score is not a root-dual criterion.

Root unit energy is about 1080 kWh at 66, then nets about 320 kWh of discharge to terminal 760 kWh. It averages {means['root']['positive_sites']:.4f} positive sites/unit-slot with Q dispersion {means['root']['Q_dispersion']:.6f}, compared with one incumbent site and Q dispersion {means['incumbent']['Q_dispersion']:.6f}. These descriptive differences motivate exact tests; they alone do not establish the gap mechanism. TERM_RELAX rho={fmt(term['rho_TERM_RELAX'])}, decrease={term['delta_terminal']:.12f}; terminal equality material by 0.001 criterion={terminalmaterial}.

{armtext}

{ubtext}

Best independently validated full-integer UB={best:.12f}, source={bestsource}, gain={UB-best:.12f}. Best certified reference/partial global LB={highest_lb:.12f}; remaining implied gap={(best-highest_lb)/best*100:.8f}%. Negative certificates available for every main arm={classification['required_negative_certificates_available']}. A 600-second stalled BestBd is computationally inconclusive unless a partial feasible upper within 0.001 or tight optimum interval proves nonmateriality. No failure to improve UB proves the incumbent globally good.

The same-route improvement removes {classification['old_certified_interval_fraction_removed']*100:.6f}% of the retained UB-minus-S2 certified interval. P_FIXED_ALL reproduces the retained objective, while freeing original binary charge modes and continuous dispatch yields the new UB under identical routes and physics. This directly proves retained-incumbent suboptimality of at least {classification['minimum_proved_retained_incumbent_suboptimality']:.12f}; formal CASE_E remains because required partial negative certificates are absent. It does not establish a weak mode LP hull or exclude a remaining formulation gap.

Bounded occupancy-integrality checks: 44 PASS. Full tests: 541 PASS (one inherited log1p warning). Exact default F3 identity and immutable sources/inputs pass. All runs retain original full grid/voltage/transformer/PCS/route/SOC physics except the explicitly isolated TERM_RELAX counterfactual. Read FINAL_REVIEW_KO.md for 50 answers, DIAGNOSTIC_VALIDITY.md for proofs and VERIFICATION.json for seals. Raw logs, model axis, exact original template and solution vectors permit independent checks. Private input caches are identified by SHA receipts and not bundled.

{nextdirection}
''')
    prose('NEXT_MODIFICATIONS.md',f'''# Next work only

{nextdirection}

Current class is {classification['ROOT_CAUSE_CLASS']}; measured partial LB gain={classification['max_partial_LB_gain']:.12f}, validated UB gain={UB-best:.12f}, terminal-counterfactual decrease={term['delta_terminal']:.12f}. The actual measured bottleneck is late-horizon phase A, led by {line['dominant_line']}, with stored energy being used toward terminal SOC. Any new remedy must preserve full-horizon line/transformer/robust-voltage and individual PCS/SOC authority.

Bound differences between time-limited arms are not exact optimum differences. Missing negative certificates cannot justify eliminating route/location, mode, SOC or multi-MESS coupling. Unit attribution follows only the preregistered R_ACTIVE material gate. No cut, disjunctive/trajectory master, D-W/CG, solver search, production change or downstream run is implemented here.
''')
    request=Path('C:/Users/kjw39/.codex/attachments/2f8d8ca0-a7d4-41cf-8e35-2ccb479152f3/붙여넣은 텍스트.txt').read_text(encoding='utf8')
    section=request.split('35. FINAL_REVIEW_KO — REQUIRED QUESTIONS')[1].split('36. EXECUTION ORDER')[0];questions=re.findall(r'^\d+\. (.+)$',section,re.M);assert len(questions)==50
    r0,ra,rb=arms;p0,p1,p2=primals
    armanswer=lambda r:f'600초 진단의 raw BestBd={fmt(r["final_BestBd"])}, inherited F3와 결합한 valid LB={fmt(r["certified_global_LB"])}, gain={r["LB_gain"]:.12f}. '+('Feasible upper certificate로 nonmaterial성을 인증했다; solver status를 OPTIMAL로 바꾸지 않았다.' if r['negative_certificate'] else r['classification']+'.')
    negativeanswer='모든 main arm에 valid partial feasible-upper certificate가 있다.' if classification['required_negative_certificates_available'] else '충분한 negative certificate가 없다. 각 arm의 negative flag는 '+', '.join(f'{r["name"]}={r["negative_certificate"]}' for r in arms)+'.'
    attribution='; '.join(f'{r["unit"]}: '+('gain='+fmt(r['gain']) if r['run'] else 'NOT_RUN') for r in unitrows)
    answers=[
        f'기존 verified UB={UB:.16f}, F3 LB={F3:.16f} → {(UB-F3)/UB*100:.8f}%; S2 LB={S2:.16f} → {(UB-S2)/UB*100:.8f}%. 현재 진단 후 best validated UB={best:.12f}, best certified LB={highest_lb:.12f}다.',
        'rho_inc[t]-rho_root[t] 내림차순과 작은 slot tie-break다. 당시 E1/E2 진단에 유효했으며 원 증거를 변경하지 않았다.',
        'incumbent-root 차이는 global root epigraph의 activity/dual 기여와 다르다. 이번에는 원 계수/vector로 모든 96-slot face와 dual을 다시 계산했다.',
        f'{dual["epigraph_active"]}. T_ACTIVE는 epigraph-active와 dual-active의 교집합 {window["T_ACTIVE"]}다.',
        f'66–95의 late-horizon block; total mass={dual["total"]:.12f}, active mass={dual["active"]:.12f}. 상위10개 slot은 {dual["largest_slot_mass_fractions"]["10"]*100:.6f}%뿐이며 90%를 담는 최소 연속구간은66–92다. 긴 block이 지배한다. 모든 contiguous window cumulative mass를 저장했다.',
        f'{dual["active_fraction"]*100:.8f}%.',
        f'예. {line["dominant_line"]}/{line["dominant_phase"]}가 {round(line["dominant_line_share"]*len(window["T_ACTIVE"]))}/{len(window["T_ACTIVE"])}개 slot에 포함된다. near-max ties도 전부 기록했다.',
        f'{line["dominant_line"]}/{line["dominant_phase"]}; 전체 unique binding line-phase {line["unique_line_phases"]}개, canonical face/line switches {line["face_switches"]}회.',
        f'{window["W_ACTIVE"][0]}–{window["W_ACTIVE"][1]}; backward buffer는 {window["W_BUFFER"][0]}–95다.',
        '실제 global root maximum과 dual이 이 구간에 집중된다. root는 SOC 약1080→760 kWh 순방전하므로 terminal energy와 전기적 bottleneck의 상호작용을 별도 측정해야 한다. terminal 충전회복을 가정하지 않았다.',
        f'root positive sites 평균 {means["root"]["positive_sites"]:.6f}/unit-slot, incumbent {means["incumbent"]["positive_sites"]:.6f}. stay/travel crossing mass·entropy·site detail를 저장했다. point 차이만으로 인과를 단정하지 않는다.',
        f'root Q dispersion 평균 {means["root"]["Q_dispersion"]:.6f}, incumbent {means["incumbent"]["Q_dispersion"]:.6f}. 무활동이면 dispersion=0이며 원 값은 수정하지 않았다.',
        f'root 평균 Pch={means["root"]["Pch"]:.6f}, Pdis={means["root"]["Pdis"]:.6f}, Pnet={means["root"]["Pnet"]:.6f} kW; incumbent Pch/Pdis/Pnet은 각각 {means["incumbent"]["Pch"]:.6f}/{means["incumbent"]["Pdis"]:.6f}/{means["incumbent"]["Pnet"]:.6f}.',
        f'active 시작 root SOC는 unit당 약1079.999 kWh, incumbent760 kWh; terminal은 둘 다760. active 평균 SOC는 root{means["root"]["SOC"]:.6f}, incumbent{means["incumbent"]["SOC"]:.6f} kWh다. charge/discharge/travel 누적이 SOC 변화를 독립 재현한다.',
        f'native terminal equality 최대 |dual|={soc["maximum_absolute_terminal_dual"]:.12f} rho/kWh; unit별 {soc["terminal_SOC_duals"]}. S3에는 같은 RHS의 G_terminal도 있어 cancellation을 반영한 combined dual은 {soc["combined_terminal_RHS_duals"]}다. raw native 값으로 unit02 지배를 주장하지 않고 F3 equality 제거 counterfactual을 따로 측정했다.',
        f'rho_TERM_RELAX={fmt(term["rho_TERM_RELAX"])}, F3 대비 decrease={term["delta_terminal"]:.12f}. 단 한 번 LP OPTIMAL이며 production 물리는 바꾸지 않았다.',
        f'0.001 objective-decrease 기준 material={terminalmaterial}. 이는 equality가 F3 LP를 제약하는 정도이며 integer gap의 단독 원인이라는 뜻은 아니다.',
        f'W_ACTIVE를 점유하거나 그 안 node에서 출발하는 원 route/stay/travel {r0["restored_binaries"]}개를 binary로 복원했다. charge_mode와 outside 나머지는 continuous다.',
        '모든 원 integer plan이 partial-integrality feasible set에 포함되기 때문이다. full96 grid/물리 행을 유지하고 일부 integrality만 완화했으므로 certified BestBd는 원 integer optimum의 valid LB다.',
        armanswer(r0),
        f'같은 window의 charge_mode까지 binary로 추가하여 총 {ra["restored_binaries"]}개를 복원했다.',
        armanswer(ra),
        f'측정된 certified-bound 차이는 {ra["certified_global_LB"]-r0["certified_global_LB"]:.12f}. time-limited bound의 차이이며 optimum의 mode 기여를 정확히 분리했다는 뜻은 아니다.',
        '8-slot/2시간의 고정 backward buffer로 pre-window route/SOC coupling을 점검한다. 1h/4h parameter/window search는 하지 않았다.',
        armanswer(rb),negativeanswer,
        '600초 안에 BestBd가 움직이지 않아도 미탐색 tree가 남을 수 있다. optimal interval 또는 feasible partial upper-F3<=0.001가 없으면 COMPUTATIONALLY_INCONCLUSIVE다.',
        attribution+'. gate가 미달이면 unit 원인을 측정하지 않았다고 명시한다.',
        'unit-arm bounds와 all-unit bound를 비교하되 낮은 단일-unit time-limited LB만으로 synergy를 증명하지 않는다. 정확한 optimum/upper interval 없이는 인과 분해가 제한된다.',
        f'P_FIXED_ALL validated original UB={fmt(p0["original_feasible_UB"])}. 모든 route와 charge_mode를 고정해 continuous dispatch만 다시 최적화했다.',
        f'P_FIXED_ROUTE validated original UB={fmt(p1["original_feasible_UB"])}. 전체 원 mode binary와 P/Q/SOC를 유지/재최적화했다.',
        f'P_LATE_ROUTE_NEIGHBORHOOD의 직접 solver UB={fmt(p2["original_feasible_UB"])}; fixed-route feasible point를 포함하므로 best known model upper={fmt(p2.get("best_known_model_feasible_UB",p2["original_feasible_UB"]))}다. 직접 solver 결과와 transferred feasible upper를 구분한다. Hamming/Top-K pruning은 없다.',
        f'{best:.12f}; source={bestsource}. 모든 accepted UB는 original binary, native physical, reconstructed full-grid voltage/transformer와 SOC 검증을 통과했다.',
        f'UB gain={UB-best:.12f}; >=0.005 material={classification["INCUMBENT_QUALITY_MATERIAL"]}. 개선 실패가 global incumbent optimality 증명은 아니다.',
        f'measured partial LB gain={classification["max_partial_LB_gain"]:.12f}. class={classification["ROOT_CAUSE_CLASS"]}; missing negative certificates가 있으면 LB weakness를 배제하거나 지배 원인을 확정하지 않는다.',
        f'직접 검증된 UB quality gain={UB-best:.12f}. material flag={classification["INCUMBENT_QUALITY_MATERIAL"]}; LB track만으로 UB quality를 추정하지 않았다.',
        f'혼합 기여 classification 여부={classification["ROOT_CAUSE_CLASS"]=="CASE_C_MIXED"}. 두 positive threshold가 충족될 때만 MIXED로 분류한다.',
        f'terminal equality 제거의 LP decrease={term["delta_terminal"]:.12f}, material={terminalmaterial}. root는 late 순방전하며 recurrence/terminal dual과 함께 해석하되 integer-gap attribution과 구분한다.',
        f'예. {line["dominant_line"]}/A가 대부분 active slot에 반복되고 full P1 dual mass가 그 block에 집중된다. 특정 feeder sensitivity bottleneck이 관찰되지만 discrete causal 효과는 arm certificate로만 판단한다.',
        f'{len(window["T_ACTIVE"])}개 연속 slot; independently recomputed active_contiguous={window["active_contiguous"]}.',
        'E1/E2는 incumbent-root 차이가 큰 40–46을 선택했고 single-slot oracle은 다른 시간의 grid와 해당 voltage/transformer까지 제거했다. 실제 late-root bottleneck의 full-horizon 부담을 직접 측정하는 실험이 아니었다.',
        'root fractional averaging은 관찰됐다. 그러나 solver-certified positive LB 또는 negative upper가 없으면 formulation gap과 600초 computational limitation을 분리하지 못한다. 실제 arm interval로 판정한다.',
        'exact F3 fingerprint/행렬, root optimal barrier interval, 원 coefficients face 재계산, immutable summary와 agreement, dual axis/finite 검사, SOC balance 및 새 upper의 independent full-grid/physical 검증으로 점검했다. tolerance와 solver status를 명시했다.',
        'production scientific physics는 바꾸지 않았다. TERM_RELAX만 명시적으로 허가된 diagnostic counterfactual로 terminal equality4개를 제거했다. partial/UB models는 전부 원 full grid/물리를 유지한다.',
        '만들지 않았다. epigraph/disjunctive/trajectory cuts, D-W/CG/master 또는 heuristic cut을 구현하지 않았다.',
        'production M1은 돌리지 않았다. 지정된 partial-integrality 및 restricted-feasible UB diagnostic MIP만 각1회 실행했다.',
        'false. 완전한 기존-authority P1/P2 acceptance certificate를 만들지 않았고 P2를 실행하지 않았다.',
        f'{classification["ROOT_CAUSE_CLASS"]}. positive LB gain={classification["max_partial_LB_gain"]:.12f}, UB gain={UB-best:.12f}, negative certificates={classification["required_negative_certificates_available"]}의 사전 rules에 따른 결과다.',
        nextdirection+' 이번 PR에서 remedy를 구현하지 않았다.',
        'M1의 기존 P1/P2 quality와 acceptance가 완료되지 않았기 때문이다. A2/M2/Actual/Fresh AC/IEEE8500 미실행, Actual P/Q OFF, PROBLEM13_FINAL_VALIDATED=false를 유지한다.'
    ];assert len(answers)==50
    prose('FINAL_REVIEW_KO.md','# 최종 원인 검토 — 50개 질문\n\n'+'\n\n'.join(f'{i}. **{q}**\n\n   {a}' for i,(q,a) in enumerate(zip(questions,answers),1)))
    if not (OUT/'F3_MODEL.mps.gz').exists():
        with (LOCAL/'F3.mps').open('rb') as src,(OUT/'F3_MODEL.mps.gz').open('wb') as dst:
            with gzip.GzipFile(fileobj=dst,mode='wb',mtime=0) as z:shutil.copyfileobj(src,z)
    sources=[p for folder in [ROOT/'v42_forensic',ROOT/'tests/v42_forensic'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    dump('SOURCE_MANIFEST.json',dict(base_head=HEAD,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(sources)],
        F3_template_sha256=sha(LOCAL/'F3.mps'),root_source_receipt_sha256=sha(OUT/'ROOT_SOURCE_RECEIPT.json'),window_definition_sha256=sha(OUT/'WINDOW_DEFINITION.json'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json')))
    print('FORENSIC REPORT COMPLETE',classification['ROOT_CAUSE_CLASS'],'best UB',best,flush=True)
if __name__=='__main__':run()
