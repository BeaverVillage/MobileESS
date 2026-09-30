"""Generate exact-safe MESS evidence; static native build has NO grid/AIDC anchor.

Run from repository root: python docs/v42_mess_graph_soc_acceleration/audit.py
--route-table may select ONLY another file with the preregistered exact SHA.
"""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from v42_native.canary import fixture, mess_grid
from v42_native.contracts import Deadline, file_sha, digest, require
from v42_native.mess import Battery, RouteArc, construct, solve
from v42_native.mess_domain import build_domain, structural
from v42_native.mess_optimizer import OptimizeBudget
from v42_native.mess_audit import BASE, baseline, baseline_build, empty_grid, exhaustive, adversarial_cases, random_cases, diagnostic_grid


def dump(name, data):
    (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(name, rows, fields):
    with (HERE / name).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def native_static(path):
    bundle_path = ROOT / 'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json'
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    expected = bundle['route_table']
    path = Path(path or expected['path'])
    require(path.is_file() and file_sha(path) == expected['sha256'], 'NATIVE_ROUTE_SHA_MISMATCH_OR_MISSING')
    table = json.loads(gzip.decompress(path.read_bytes()))
    routes, excluded = [], Counter()
    for r in table['routes']:
        source, dest, depart = r['origin_service_id'], r['destination_service_id'], r['departure_slot_15']
        arrive = depart + r['travel_slots_15min']
        connect = depart + r['connection_ready_slots_15min']
        if source == dest:
            excluded['same_site_represented_by_stay'] += 1
            continue
        if not 0 <= depart < arrive <= connect < 96:
            excluded['outside_inherited_RouteArc_time_contract'] += 1
            continue
        routes.append(RouteArc(f'{source}:{dest}:{depart}', source, dest, depart, arrive, connect,
                               r['energy_safe_kwh'], digest(r)))
    source = dict(path=str(path), sha256=file_sha(path), bytes=path.stat().st_size,
                  expected_sha256=expected['sha256'], excluded=dict(excluded), accepted_routes=len(routes),
                  mapping='depart=departure_slot_15; arrive=depart+travel_slots_15min; connect=depart+connection_ready_slots_15min; energy=energy_safe_kwh; authority=SHA256(all source record fields)',
                  synthetic_routes=False, road_path_search_calls=0,
                  scope='Native source-backed static RouteArc constructor audit, no executed native M1/M2 or grid anchor')
    return tuple(table['service_ids']), 96, Battery(**bundle['battery']), tuple(routes), bundle['initial_MESS_sites'], source


def audit_domain(label, sites, H, b, routes, initial, baseline_rows, final_rows, reductions, csv_rows, profiles):
    prepared = perf_counter()
    d = build_domain(sites, initial, routes, b, H)
    screen = perf_counter() - prepared
    reused = build_domain(sites, initial, routes, b, H) is d
    before = baseline_build(sites, initial, routes, b, H)
    model, _, _, after = construct(d, empty_grid)
    model.dispose()
    profiles[label] = dict(scope='MOBILITY_ONLY_BUILD_NO_GRID_NO_OPTIMIZE',
                           domain_prescreen_seconds=screen, object_identity_reused=reused,
                           baseline=before, reduced=after)
    baseline_vars = before['family_columns']
    reduced_vars = dict(arc=after['route_variable_count'], charge_mode=sum(len(u.charge_times) for u in d.units),
                        Pch=len(d.pq_indices), Pdis=len(d.pq_indices), Q=len(d.pq_indices), SOC=len(initial)*(H+1))
    for name in ('arc','charge_mode','Pch','Pdis','Q','SOC'):
        reductions.append(dict(case=label, metric=name, before=baseline_vars[name], after=reduced_vars[name],
                               reduction=baseline_vars[name]-reduced_vars[name]))
    for name, old, new in (('PCS16_rows', before['model_size_before_solve']['constraint_families'].get('PCS16',0), after['model_size_before_solve']['constraint_families'].get('PCS16',0)),
                           ('flow_rows', before['model_size_before_solve']['constraint_families']['flow'], after['model_size_before_solve']['constraint_families']['flow']),
                           ('total_rows', before['total_rows'], after['model_size_before_solve']['linear_constraints']),
                           ('total_columns', before['total_columns'], sum(reduced_vars.values())),
                           ('nonzeros', before['model_size_before_solve']['nonzeros'], after['model_size_before_solve']['nonzeros']),
                           ('model_build_seconds', before['model_build_seconds'], after['model_build_seconds'])):
        reductions.append(dict(case=label, metric=name, before=old, after=new, reduction=old-new))
    for u, final in zip(d.units, after['per_mess']):
        forward, _ = structural(d.arcs, (u.origin,0), {(s,H) for s in sites})
        stays = [a for a in d.arcs if a.route is None and a.tail in forward]
        travel = [a for a in d.arcs if a.route is not None and a.tail in forward]
        pq = len(stays)
        # Separate baseline build per MESS obtains actual row/nonzero counts.
        single = baseline_build(sites, {u.mess:u.origin}, routes, b, H)
        baseline_rows.append(dict(case=label,mess=u.mess,initial_site=u.origin,site_count=len(sites),horizon_slots=H,
                                  stay_arcs=len(sites)*H,travel_arcs=len(d.routes),total_arcs=len(d.arcs),
                                  forward_unreachable_arcs=len(d.arcs)-len(stays)-len(travel),
                                  route_binaries=len(stays)+len(travel),charge_mode_binaries=H,
                                  Pch=pq,Pdis=pq,Q=pq,SOC=H+1,PCS16_rows=16*pq,flow_rows=len(sites)*H,
                                  total_constraints=single['total_rows'],total_columns=single['total_columns'],
                                  total_nonzeros=single['model_size_before_solve']['nonzeros'],model_build_seconds=single['model_build_seconds']))
        reasons=Counter(reason for _,reason in u.removals)
        final_rows.append(dict(case=label,**final,initial_stay_arcs=len(sites)*H,initial_travel_arcs=len(d.routes),
                               removed_forward_unreachable=reasons['FORWARD_UNREACHABLE'],
                               removed_backward_dead_end=reasons['BACKWARD_DEAD_END'],
                               removed_forward_SOC=reasons['FORWARD_SOC_INFEASIBLE'],
                               removed_backward_SOC=reasons['BACKWARD_SOC_INFEASIBLE'],
                               removed_SOC_disjoint=reasons['SOC_FORWARD_BACKWARD_DISJOINT'],
                               removed_arc_SOC=reasons['ARC_SOC_MAPPING_EMPTY'],removed_exact_duplicates=len(d.duplicate_indices),
                               reduction_percentage=100*(1-len(u.arc_indices)/len(d.arcs)),
                               baseline_binary_reduction_percentage=100*(1-len(u.arc_indices)/(len(stays)+len(travel))) if stays or travel else 0,
                               iterations=len(u.iterations)))
        for it in u.iterations:
            prefix=dict(case=label,mess=u.mess,iteration=it.number)
            for direction, nodes in (('FORWARD',it.forward_nodes),('BACKWARD',it.backward_nodes)):
                reachable=set(nodes)
                for s in sites:
                    for t in range(H+1):csv_rows[direction].append(dict(prefix,site=s,time=t,reachable=int((s,t) in reachable)))
            for direction, intervals in (('FORWARD_SOC',it.forward_soc),('BACKWARD_SOC',it.backward_soc),('INTERSECTION',it.intersections)):
                for (s,t), I in intervals:
                    csv_rows[direction].append(dict(prefix,site=s,time=t,lower='' if I is None else I.lower,
                                                     upper='' if I is None else I.upper,empty=int(I is None)))
            removed=dict(it.removed)
            for k,possible in it.arc_mapping:
                csv_rows['ARC'].append(dict(prefix,arc=k,possible=int(possible),reason=removed.get(k,'')))
    return d


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--route-table');args=parser.parse_args()
    baseline_rows, final_rows, reductions = [], [], []
    rows={k:[] for k in ('FORWARD','BACKWARD','FORWARD_SOC','BACKWARD_SOC','INTERSECTION','ARC')}
    profiles={};domains={}
    sites,H,b,routes=fixture()
    domains['bounded_canary']=audit_domain('bounded_canary',sites,H,b,routes,{'M':'A'},baseline_rows,final_rows,reductions,rows,profiles)
    sites,H,b,routes,initial,source=native_static(args.route_table)
    domains['native_static_96']=audit_domain('native_static_96',sites,H,b,routes,initial,baseline_rows,final_rows,reductions,rows,profiles)
    print('Native static baseline/reduced builds complete', flush=True)
    for label,case in adversarial_cases().items():
        sites,H,b,routes=case
        domains[label]=audit_domain(label,sites,H,b,routes,{'M':'A'},baseline_rows,final_rows,reductions,rows,profiles)
    write_csv('MESS_BASELINE_DOMAIN_AUDIT.csv',baseline_rows,list(baseline_rows[0]))
    dump('MESS_BASELINE_MODEL_SIZE.json',profiles)
    write_csv('MESS_FINAL_DOMAIN_AUDIT.csv',final_rows,list(final_rows[0]))
    write_csv('MESS_ELECTRICAL_COLUMN_REDUCTION.csv',reductions,['case','metric','before','after','reduction'])
    for key,name in (('FORWARD','MESS_FORWARD_REACHABILITY.csv'),('BACKWARD','MESS_BACKWARD_REACHABILITY.csv')):
        write_csv(name,rows[key],['case','mess','iteration','site','time','reachable'])
    for key,name in (('FORWARD_SOC','MESS_FORWARD_SOC_ENVELOPE.csv'),('BACKWARD_SOC','MESS_BACKWARD_SOC_ENVELOPE.csv'),('INTERSECTION','MESS_SOC_INTERSECTION_AUDIT.csv')):
        write_csv(name,rows[key],['case','mess','iteration','site','time','lower','upper','empty'])
    write_csv('MESS_ARC_SOC_FEASIBILITY.csv',rows['ARC'],['case','mess','iteration','arc','possible','reason'])
    dump('MESS_EXACT_DUPLICATE_AUDIT.json',dict(signature='ALL RouteArc fields including route_id, source, destination, depart, arrive, connect, energy_kwh, authority_sha256',
         energy_dominance=False,cases={k:list(d.duplicate_indices) for k,d in domains.items()},baseline_note='PR99 already used dict.fromkeys; identical duplicates do not create incremental savings'))
    dump('MESS_FIXED_POINT_PRUNING.json',{k:{u.mess:dict(iterations=len(u.iterations),removals_by_reason=dict(Counter(reason for _,reason in u.removals)),removed_arcs=list(u.removals)) for u in d.units} for k,d in domains.items()})
    dump('MESS_SHARED_DOMAIN_AUTHORITY.json',{k:dict(domain_sha256=d.sha256,input_sha256=d.input_sha256,
         authority_hash_count=len(d.authority_hashes),PQ_index_count=len(d.pq_indices),PCS_index_count=len(d.pcs_indices),
         object_identity_reused=profiles[k]['object_identity_reused'],
         dynamic_grid_excluded=True) for k,d in domains.items()})
    write_csv('MESS_GLOBAL_SOC_BOUNDS.csv',
        [dict(case=label,mess=u.mess,time=t,lower=I.lower,upper=I.upper,
              original_lower=d.battery.minimum,original_upper=d.battery.maximum,
              tightened=int(I.lower>d.battery.minimum or I.upper<d.battery.maximum))
         for label,d in domains.items() for u in d.units for t,I in u.global_soc],
        ['case','mess','time','lower','upper','original_lower','original_upper','tightened'])
    cases=[('canary',fixture())]+list(adversarial_cases().items())+list(random_cases())
    feasible={};objectives={};adversarial={}
    for label,case in cases:
        feasible[label]=exhaustive(case)
        sites,H,b,routes=case
        old,br=baseline().solve('M1',Deadline('M1',20),sites,{'M':'A'},routes,b,H,mess_grid if label=='canary' else diagnostic_grid)
        new,nr=solve('M1',OptimizeBudget('M1',20),sites,{'M':'A'},routes,b,H,mess_grid if label=='canary' else diagnostic_grid,diagnostic=True)
        require((old is None)==(new is None),'FEASIBILITY_DRIFT')
        differences={} if old is None else {level:new['objectives'][level]-old['objectives'][level] for level in old['objectives']}
        require(all(abs(v)<=3e-7 for v in differences.values()),'OBJECTIVE_DRIFT')
        if new:require(old['lex_complete'] and new['lex_complete'],'BOUNDED_NOT_OPTIMAL')
        objectives[label]=dict(PASS=True,old=None if old is None else old['objectives'],new=None if new is None else new['objectives'],
                               differences=differences,old_status=[p['status'] for p in br['passes']],new_status=[p['status'] for p in nr['passes']])
        adversarial[label]=dict(PASS=True,fixture=dict(sites=sites,horizon=H,battery=asdict(b),routes=[asdict(r) for r in routes]),
                                enumeration=feasible[label])
    dump('MESS_FORMULATION_EQUIVALENCE.json',dict(PASS=True,scope='Bounded exhaustive fixed-path continuous SOC projection plus unchanged electrical equations',cases=feasible,
         proof='Every physical prefix/suffix energy lies in outer hull. Pruned arcs have empty necessary interval image. Every retained path inherits identical flow, departure energy balance, P/Q connection/direction/PCS16 and terminal equality. Global bounds include connected AND post-departure transit states.',
         native_full_feasible_set_enumeration=False))
    dump('MESS_OBJECTIVE_EQUIVALENCE.json',dict(PASS=True,tolerance=3e-7,MIPGap=0,cases=objectives))
    dump('MESS_ADVERSARIAL_SOC_TESTS.json',dict(PASS=True,seed=20260930,cases=adversarial))
    sites,H,b,routes=fixture();d=domains['bounded_canary']
    first,m1=solve('M1',OptimizeBudget('M1',20),sites,{'M':'A'},routes,b,H,mess_grid,diagnostic=True,domain=d)
    cold,cold_stats=solve('M2',OptimizeBudget('M2',20),sites,{'M':'A'},routes,b,H,diagnostic_grid,diagnostic=True,domain=d)
    warm,warm_stats=solve('M2',OptimizeBudget('M2',20),sites,{'M':'A'},routes,b,H,diagnostic_grid,first,diagnostic=True,domain=d)
    require(all(abs(cold['objectives'][k]-warm['objectives'][k])<=3e-7 for k in cold['objectives']),'WARM_OBJECTIVE_DRIFT')
    require(warm_stats['warm_start_accepted'],'BOUNDED_WARM_START_NOT_ACCEPTED')
    dump('MESS_WARM_START_AUDIT.json',dict(scope='ONE_BOUNDED_COLD_WARM_M2_DIAGNOSTIC_DYNAMIC_GRID_SAME_M2_PROBLEM',
         PASS=True,accepted=warm_stats['warm_start_accepted'],physical_validation=warm_stats['warm_start_physical_validation'],
         cold=dict(receipt=cold_stats,objectives=cold['objectives']),warm=dict(receipt=warm_stats,objectives=warm['objectives']),
         native_speedup_claim=False,full_physical_start=True,dynamic_grid_start_copied=False))
    for stage,stats in (('M1',m1),('M2',warm_stats)):
        dump(f'MESS_{stage}_MODEL_STATS.json',dict(native_status='NOT_RUN_AWAITING_ACCEPTED_A_BLOCK',
             native_grid_model_built=False,native_optimize_seconds=None,native_time_limit=1800,native_MIPGap=.005,
             bounded_receipt=stats,static_native_mobility_build=profiles['native_static_96']))
    native=profiles['native_static_96'];reduced=native['reduced']['model_size_before_solve']
    dump('MESS_BOTTLENECK_CLASSIFICATION.json',dict(scope='Native static construction and bounded solves only',
         native_solve_bottleneck='UNMEASURED_A1_A2_GATE_CLOSED',static_route_binaries=native['reduced']['route_variable_count'],
         static_rows=reduced['linear_constraints'],static_nonzeros=reduced['nonzeros'],
         static_route_binary_share_of_columns=native['reduced']['route_variable_count']/sum(row['total_columns'] for row in native['reduced']['per_mess']),
         bounded_M2_nodes_cold=sum(p['nodes'] for p in cold_stats['passes']),bounded_M2_nodes_warm=sum(p['nodes'] for p in warm_stats['passes']),
         bounded_M2_seconds_cold=cold_stats['solve_wall_seconds'],bounded_M2_seconds_warm=warm_stats['solve_wall_seconds'],
         mobility_BB_dominance=None,grid_security_dominance=None,continuous_coupling_dominance=None,
         interpretation='Route column count alone cannot establish branch-and-bound dominance; static row counts exclude grid. Native root/cuts/branching must be measured after genuine anchors.'))
    dump('MESS_NEXT_ALGORITHM_DECISION.json',dict(MESS_DW_TRIGGER=False,CL_MC_BD_TRIGGER=False,
         trigger_status='NOT_ESTABLISHED_WITH_AVAILABLE_MEASUREMENTS',implementation='KEEP_NETWORK_FLOW_MILP',
         next_step='Integrate genuinely accepted A1/A2 anchors; reuse frozen MESS domain; run each native optimize at 1800s/.005 and profile root/grid/security/path branching.',
         future_MESS_DW='Only if measured route/path branching dominates; route/PQ/SOC physical columns, master grid coupling',
         future_CL_MC_BD='Only if measured critical line/security coupling dominates',automatic_decomposition=False))
    dump('SOURCE_MANIFEST.json',dict(base=BASE,baseline_source_sha256=baseline().source_sha256,
         files=[dict(path=str(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json'),sha256=file_sha(ROOT/'docs/v42_may01_native_canary/MAY01_NATIVE_INPUT_BUNDLE.json'))],
         native_route_source=source,concurrent_AIDC_branch_read_or_merged=False,Actual_realization_reads=0))
    dump('FINAL_FLAGS.json',dict(MESS_PHYSICS_CHANGED=False,MESS_ROUTE_AUTHORITY_CHANGED=False,
         FORWARD_REACHABILITY_IMPLEMENTED=True,BACKWARD_REACHABILITY_IMPLEMENTED=True,FORWARD_SOC_SCREEN_IMPLEMENTED=True,
         BACKWARD_SOC_SCREEN_IMPLEMENTED=True,FALSE_FEASIBLE_PATH_PRUNED=False,OLD_NEW_FEASIBLE_SET_EQUIVALENCE_PASS=True,
         OBJECTIVE_EQUIVALENCE_PASS=True,M1_M2_SHARED_DOMAIN_IMPLEMENTED=True,M2_WARM_START_IMPLEMENTED=True,
         NATIVE_M1_RUN=False,NATIVE_M2_RUN=False,MESS_DW_TRIGGER=False,CL_MC_BD_TRIGGER=False,
         NEW_ML=False,NEW_RUNTIME_ML=False,NEW_CC4_ML=False,NEW_MESS_ML=False,NEW_TRAFFIC_ML=False,
         equivalence_scope='Analytical safety proof and exhaustive bounded tests; native solve not run'))
    dump('FINAL_VERDICT.json',dict(status='EXACT_SAFE_ENGINE_VERIFIED_NATIVE_GATED',native_M1='NOT_RUN_AWAITING_ACCEPTED_A_BLOCK',
         native_M2='NOT_RUN_AWAITING_ACCEPTED_A_BLOCK',native_solve_speed_claim=False,bounded_case_count=len(cases),
         algorithm='NETWORK_FLOW_MILP',approved_A1_available=False,approved_A2_available=False))
    print(json.dumps(dict(bounded_cases=len(cases),native_static_before=before_summary(native['baseline']),native_static_after=reduced),indent=2),flush=True)


def before_summary(receipt):
    return dict(columns=receipt['total_columns'],rows=receipt['total_rows'],nonzeros=receipt['model_size_before_solve']['nonzeros'])


if __name__=='__main__':main()
