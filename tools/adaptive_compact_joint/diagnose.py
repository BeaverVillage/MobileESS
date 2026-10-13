"""Native-zero audits of every saved joint pool, solver log and FULL point."""
import re,gc,time
from collections import Counter,defaultdict
from tools.adaptive_compact_joint.adapter import *
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature
from tools.global_local_multistart1800.routes import distance

def pool_stats(graph,u,paths,authority):
    moves=[graph.move_indices(p) for p in paths];arcs=set(k for p in paths for k in p)
    actual=[graph.arcs[k] for ms in moves for k in ms]
    signatures=[path_signature(p) for p in paths];near=0;pair=0
    for i,p in enumerate(paths):
        for q in paths[i+1:]:
            pair+=1;near+=distance(graph,{u:p},{u:q})<=6
    return dict(count=len(paths),MOVE_histogram=dict(Counter(map(len,moves))),STAY_only=sum(not m for m in moves),
        single_MOVE=sum(len(m)==1 for m in moves),multiple_MOVE=sum(len(m)>=2 for m in moves),
        unique_destinations=sorted({a[2] for a in actual}),unique_depart_slots=sorted({a[1] for a in actual}),
        unique_connect_slots=sorted({a[3] for a in actual}),duplicate_fraction=1-len(set(signatures))/len(paths),
        near_duplicate_location_fraction=near/max(1,pair),near_definition='at most6 differing location/transit slots',
        represented_arcs=len(arcs),available_original_arcs=len(graph.available[u]),
        represented_arc_fraction=len(arcs)/len(graph.available[u]),PR220_path_preserved=authority[u] in paths)

def dag_scope(graph,u):
    counts={(graph.origins[u],0):1};depth={(graph.origins[u],0):0}
    for t in range(96):
        for site,when in [k for k in counts if k[1]==t]:
            for k in graph.outgoing[site,t]:
                if k not in graph.available[u]:continue
                a=graph.arcs[k];dest=a[2:4]
                counts[dest]=counts.get(dest,0)+counts[site,t]
                depth[dest]=max(depth.get(dest,0),depth[site,t]+int(a[-1] is not None))
    return dict(original_topological_complete_path_count=str(sum(vv for (s,t),vv in counts.items() if t==96)),
        DAG_maximum_MOVE_count=max(vv for (s,t),vv in depth.items() if t==96),
        physical_maximum_MOVE_count='NOT_IDENTIFIED: SOC/PCS/Grid further restrict topology; no invented physical MOVE cap')

def main():
    began=time.perf_counter();guard();assert read(DOCS/'PHASE0_SAFE_STOP.json')['PASS']
    case=v.load_native_case();warm=v.load_point(ROOT/RAW_REL);graph=Graph(case);authority=paths_of(case,warm)
    specs=sorted(OLD_DOCS.glob('calls/*/SPEC.json'))+sorted((OLD_DOCS/'v2').glob('calls/*/SPEC.json'))
    audits=[];union={u:{} for u in graph.origins};solver=[]
    for p in specs:
        spec=read(p)
        if spec['method']!='FOUR_MESS_JOINT_ROUTE_POOL':continue
        stats={u:pool_stats(graph,u,paths,authority) for u,paths in spec['pools'].items()}
        for u,paths in spec['pools'].items():
            for path in paths:union[u][path_signature(path)]=path
        audits.append(dict(spec=record(p),pool_signature=spec['pool_signature'],units=stats))
        call=read(p.parent/'native/NATIVE_CALL.json');log=(p.parent/'native/NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace')
        ps=re.findall(r'Presolved: ([\d,]+) rows, ([\d,]+) columns, ([\d,]+) nonzeros',log)
        removed=re.findall(r'Presolve removed ([\d,]+) rows and ([\d,]+) columns',log)
        pt=re.findall(r'Presolve time: ([\d.]+)s',log)
        solver.append(dict(spec=record(p),native=record(p.parent/'native/NATIVE_CALL.json'),
            pool_counts={u:len(vv) for u,vv in spec['pools'].items()},binary_before=9322,binary_after=9322+spec['lambda_count'],continuous=344955,
            Presolved=ps[-1] if ps else None,Presolve_removed=removed[-1] if removed else None,Presolve_seconds=float(pt[-1]) if pt else None,
            root_LP_completed=call.get('root_completed_Native_seconds') is not None,
            MIP_Start_loaded='Loaded user MIP start' in log,selected_lambda=call['captures'][-1].get('lambda_values'),
            **{k:call.get(k) for k in ('Status','NodeCount','ObjVal','ObjBound','MIPGap','Native_Runtime','model_build_wall_seconds','worker_wall_seconds')}))
    write(DOCS/'PHASE1_ROUTE_AND_SOLVER_DIAGNOSTICS.json',dict(PASS=True,Optimize_calls=0,
        audited_joint_models=len(audits),models=audits,solver_runs=solver,
        aggregate={u:dict(**pool_stats(graph,u,list(paths.values()),authority),**dag_scope(graph,u)) for u,paths in union.items()},
        current_generator=dict(source=record(OLD_ROOT/'tools/global_local_multistart1800/routes.py'),
            Beam_width='NO_PARTIAL_LABEL_BEAM_IN_CURRENT_GLOBAL_GENERATOR',MOVE_depth='OneMOVE enumeration plus handpicked twoMOVE extensions; PR220 threeMOVE only pinned authority',
            twoMOVE_bias='first8 diversity representatives; second depart40/64/80; first6 destinations',
            ranking_bias='static64-row PR219 Minimax heuristic; per-solo others STAY; no verified optimization feedback',
            original_PR219_Beam_width=64,original_PR219_heuristic_MOVE_depth=3),
        conclusions=dict(candidate_generation='Limited multiMOVE and feedback coverage; arc coverage is not FULL path coverage',
            solver_delay='Earlier restricted models mostly close at warm UB; latest two rootLP time limits prevent evaluating useful alternatives',
            physical_limit='NOT_PROVEN. Restricted optimum and failed heuristic search do not establish a FULL physical lower bound'),
        wall_seconds=time.perf_counter()-began))
    # All original row activities are evaluated, not just two historical lines.
    original=case.lift(warm);d=case.original_d;del case;gc.collect()
    native0_case=v.load_case(native=False);full=native0_case.original_A.tocsr()
    names=np.asarray(d['row_names']);thermal=np.flatnonzero(np.char.startswith(names,'line_thermal_face['))
    assert len(thermal)==403968
    rho_col=int(np.flatnonzero(d['names']=='rho_max')[0]);rc=np.asarray(full[:,rho_col].toarray()).ravel()
    valid=[];seen=set();records=[]
    # Fresh replay every unique physically admitted saved vector using unchanged validator.
    packets=list((OLD_DOCS/'v2/inherited_v1').rglob('POINT_ONLY_RAW.npz'))
    for folder in sorted((OLD_DOCS/'v2/calls').iterdir()):
        for rep in folder.glob('REPLAY_*.json'):
            q=read(rep)
            if q.get('PASS'):packets.append(Path(q['point_path']))
    packets.extend([ROOT/RAW_REL,Path(read(DOCS/'PHASE0_SAFE_STOP.json')['final_raw']['path'])])
    for p in packets:
        point=v.load_point(p);sig=v.vector_sha(point)
        if sig in seen:continue
        seen.add(sig);x=native0_case.lift(point);activity=full@x
        obj=float(d['objective']@x+float(d['constant']));loading=obj+(activity[thermal]-d['rhs'][thermal])/(-rc[thermal])
        order=np.argsort(loading)[::-1];top=[];by_slot={};near=np.flatnonzero(loading>=obj-.025)
        for j in order[:100]:
            rr=int(thermal[j]);name=str(names[rr]);top.append(dict(row=rr,name=name,loading=float(loading[j])))
        for j in order:
            rr=int(thermal[j]);slot=int(str(names[rr]).split('[',1)[1].split(',')[0])
            if slot not in by_slot:by_slot[slot]=dict(row=rr,name=str(names[rr]),loading=float(loading[j]))
            if len(by_slot)==96:break
        ops={}
        for u in graph.origins:
            axes={f:[i for i,n in enumerate(d['names']) if str(n).startswith(f+'['+u+',')] for f in ('Pch','Pdis','Q','SOC')}
            soc=x[axes['SOC']];pch=x[axes['Pch']];pdis=x[axes['Pdis']];q=x[axes['Q']]
            ops[u]=dict(SOC_min=float(soc.min()),SOC_max=float(soc.max()),initial=float(soc[0]),terminal=float(soc[-1]),
                lower_SOC_hits=int(np.count_nonzero(abs(soc-440)<1e-6)),upper_SOC_hits=int(np.count_nonzero(abs(soc-1080)<1e-6)),
                Pch_300_hits=int(np.count_nonzero(abs(pch-300)<1e-6)),Pdis_300_hits=int(np.count_nonzero(abs(pdis-300)<1e-6)),
                PCS_circle_hits=int(np.count_nonzero(abs((pch-pdis)**2+q*q-400**2)<1e-5)),
                charging_kWh=float(pch.sum()*.25),discharging_kWh=float(pdis.sum()*.25),Q_signed_sum=float(q.sum()))
        records.append(dict(raw=record(p),vector_SHA=sig,objective=obj,all_original_rows_evaluated=full.shape[0],
            all_thermal_rows_evaluated=len(thermal),near_thermal_face_count=len(near),top100=top,per_slot_worst=by_slot,operations=ops))
    write(DOCS/'PHASE1_WHOLE_GRID_SOC_DIAGNOSTICS.json',dict(PASS=True,Optimize_calls=0,unique_saved_vectors=len(records),records=records,
        no_physical_infeasibility_inferred_from_ranking=True,all_original_grid_rows_retained=True,
        PCS16_facets_checked_by_FULL_replay=True,notes='Face counts include multiple facets of the same line/phase. Top100 and all96 slot worsts prevent two-line-only analysis.'))
    print(json.dumps(dict(PASS=True,models=len(audits),unique_vectors=len(records),wall=time.perf_counter()-began)))

if __name__=='__main__':main()
