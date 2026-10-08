"""Adaptive original-row UB restrictions and full-domain dual-price trials."""
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
import numpy as np
import gurobipy as gp
from v42_unified.storage import sha
from v42_m1_research.ub import binary_inventory
from v42_m1_research import projection_rows
from v42_m1_hybrid import neighborhood, ub, pricing, dw, verify
from v42_m1_hybrid.final_verify import _strict_ub
from .core import ROOT,CASE,write,read

RADII=(48,96,144,192,288)
LOOKBACK=(4,8,16,24)
TOP_ROUTES=(2,3,4,6)
PROJECTION=ROOT/'docs/v42_m1_joint_gap_research/GRID_ROW_PQ_PROJECTION_PROOF.json'

def dynamic_grid(case,point,path):
    """Rank actual current source thermal rows; equivalent projection only."""
    names=np.asarray(case.d['row_names']).astype(str)
    rho=int(np.flatnonzero(case.d['names']=='rho_max')[0])
    activity=case.A@point;rhs=case.d['rhs'];sense=case.d['sense']
    slack=np.where(sense=='<',rhs-activity,np.where(sense=='>',activity-rhs,abs(activity-rhs)))
    candidates=np.flatnonzero(np.char.startswith(names,'line_thermal_face[')|np.char.startswith(names,'transformer_kVA['))
    coefficients=np.asarray(case.A[candidates,rho].toarray()).ravel()
    ranked=candidates[np.argsort(np.maximum(slack[candidates],0)/np.maximum(abs(coefficients),1e-12))]
    chosen=[];seen=set()
    for i in ranked:
        fields=names[i].split('[',1)[1][:-1].split(',');key=tuple(fields[:2])
        if key not in seen:chosen.append(int(i));seen.add(key)
        if len(chosen)==12:break
    chosen=tuple(dict.fromkeys(chosen+list(projection_rows.FIXED_ROWS)))
    with patch.object(projection_rows,'FIXED_ROWS',chosen):
        packets=projection_rows.project_rows(case)
        checked=projection_rows.verify_projection_packet(case,packets)
        write(path,dict(case_sha=CASE,exact_rows=packets,independent_checker=checked,original_rows=chosen,
                       adaptive_row_ranking_is_UB_heuristic_not_Global_LB=True))
        targets,provenance=neighborhood.grid_candidates(case,point,path)
    voltage=np.flatnonzero(np.char.startswith(names,'voltage_lower[')|np.char.startswith(names,'voltage_upper['))
    vtop=voltage[np.argsort(slack[voltage])[:8]]
    provenance['active_voltage_observations']=[dict(row=int(i),name=str(names[i]),observed_slack=float(slack[i])) for i in vtop]
    provenance['all_original_grid_rows_preserved_in_native_model']=True
    return targets,provenance

def select(case,point,method,ordinal,grid):
    inventory=binary_inventory(case.d);targets,provenance=grid
    radius=RADII[(ordinal+(0 if method!='U3' else 2))%len(RADII)]
    look=LOOKBACK[ordinal%len(LOOKBACK)];top=TOP_ROUTES[ordinal%len(TOP_ROUTES)]
    moves=neighborhood._moves(case,point);ranked=[]
    for m in moves:
        score=max((r['numeric_score'] for r in targets if r['site'] in (m['source'],m['destination'])),default=0)
        ranked.append(dict(**m,score=score+m['energy_kwh']/case.graph[3].maximum+m['unavailable_slots']/96))
    ranked.sort(key=lambda m:(-m['score'],m['route_id'],m['unit']))
    offset=(ordinal//len(TOP_ROUTES))%max(1,len(ranked))
    routes=(ranked[offset:]+ranked[:offset])[:top]
    windows={};preferred_units=set(case.graph[1])
    if method in ('U1','U3'):
        for r in routes:
            for t in range(max(0,r['depart']-look),96):windows.setdefault(t,set()).update((r['source'],r['destination']))
        for r in targets[:top*4]:
            for t in range(max(0,r['slot']-look),min(96,r['slot']+look+1)):windows.setdefault(t,set()).add(r['site'])
    elif method=='U2':
        for r in targets[:max(8,top*4)]:
            for t in range(max(0,r['slot']-look),min(96,r['slot']+look+1)):windows.setdefault(t,set()).add(r['site'])
        for v in provenance['active_voltage_observations']:
            fields=v['name'].split('[',1)[1][:-1].split(',')
            try:t0=int(fields[0])
            except ValueError:continue
            for t in range(max(0,t0-look),min(96,t0+look+1)):windows.setdefault(t,set()).update(r['site'] for r in targets[:8])
    elif method=='U4':
        charges=[]
        for j,n in enumerate(case.d['names']):
            if str(n).startswith('Pch[') and point[j]>1e-6:
                u,s,t=str(n)[4:-1].split(',');charges.append((float(point[j]),s,int(t)))
        charges.sort(reverse=True)
        for _,s,t0 in charges[:max(8,top*4)]:
            for t in range(max(0,t0-look),min(96,t0+look+1)):windows.setdefault(t,set()).add(s)
        for r in targets[:top*4]:
            for t in range(max(0,r['slot']-look),96):windows.setdefault(t,set()).add(r['site'])
    else:raise ValueError('REGISTERED_UB_METHOD_REQUIRED')
    free=set()
    for r in inventory:
        if r['slot'] in windows and (r['family']=='charge_mode' or r['site'] in windows[r['slot']] or point[r['column']]==1.):free.add(r['column'])
    if not free:raise ValueError('EMPTY_ADAPTIVE_NEIGHBORHOOD')
    allbinary=set(r['column'] for r in inventory)
    return dict(method=method,description='adaptive actual-role/time/mode restriction',case_sha=CASE,
        free_binary_columns=np.asarray(sorted(free),dtype=np.int64),fixed_binary_columns=np.asarray(sorted(allbinary-free),dtype=np.int64),
        original_binary_columns=9322,hamming_radius=radius,lookback_slots=look,route_top=top,role_rotation_offset=offset,
        selected_grid_provenance=provenance,selected_route_targets=routes,
        source_seed_restricted_feasible=True,forced_route_removal=False,
        full_original_flow_route_SOC_rows_and_arcs_preserved=True,original_all_96_slot_continuous_bounds_preserved=True,
        bound_scope='UB_RESTRICTION_NEVER_GLOBAL_LB')

def ub_trial(case,point,method,ordinal,ledger,frontier,path,limit,grid):
    start=perf_counter();path.mkdir(parents=True,exist_ok=False);start_ub=frontier.ub
    with ledger.cost('UB_model_build',path.name):
        initial=ub.validate_strict(case,point)
        if not initial['PASS']:raise ValueError('CURRENT_CENTRE_NO_LONGER_STRICT')
        spec=select(case,point,method,ordinal,grid)
        with patch.object(ub,'select',lambda *args:spec):
            model,v,identity=ub.build_model(case,point,'C',path,PROJECTION,start_replay=initial)
    # Identity is generated by the unchanged original-row builder; add the
    # actual registered radius instead of the old benchmark's hardcoded label.
    pending=[];discovered=start_ub;capture_errors=[]
    def callback(m,where):
        nonlocal discovered
        if where==gp.GRB.Callback.MIPSOL:
            try:
                obj=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                if obj<float(discovered)-1e-11:
                    raw=np.asarray(m.cbGetSolution(v),dtype=np.float64).copy()
                    pending.append(dict(obj=obj,point=raw,discovery=ledger.wall(),solver_Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))))
                    pending.sort(key=lambda x:x['obj']);del pending[5:];discovered=F(obj)
            except Exception as exc:capture_errors.append(str(exc))
    records=[];best=point.copy();failures=0
    try:
        native=ledger.optimize(model,track='UB',label=path.name,requested_seconds=limit,callback=callback)
        if model.SolCount:pending.append(dict(obj=float(model.ObjVal),point=np.asarray(v.X).copy(),discovery=ledger.wall(),solver_Runtime=float(model.Runtime),final_RAW=True))
        # Strictly distinct points; discovery and later certification stay apart.
        seen=set()
        for k,item in enumerate(pending):
            raw=item.pop('point');key=ub.vector_sha(raw)
            if key in seen:continue
            seen.add(key);packet=path/f'RAW_{k:02d}.npz';np.savez_compressed(packet,point=raw)
            try:
                with ledger.cost('UB_independent_full_replay',packet.name):cert=_strict_ub(case,packet,{})
                cert.update(case_sha=CASE,discovery=item['discovery'],certificate_completion=ledger.wall())
                certpath=path/f'RAW_{k:02d}_REPLAY.json';write(certpath,cert)
                admitted=frontier.publish('UB',cert['exact_Global_UB'],cert,certpath,sha(certpath),item['discovery'])
                if admitted:best=raw.copy()
                records.append(dict(**item,path=str(packet),PASS=True,adopted=admitted,certificate=str(certpath),certificate_sha256=sha(certpath),completion=ledger.wall()))
            except ValueError as exc:
                with ledger.cost('rejected_RAW_diagnostic_replay',packet.name):failure=ub.validate_strict(case,raw)
                failures+=1;records.append(dict(**item,path=str(packet),PASS=False,reason=str(exc),
                    rejected_integer_physical_diagnostics=failure,completion=ledger.wall()))
        result=dict(method=method,ordinal=ordinal,start_UB=float(start_ub),best_validated_UB=float(frontier.ub),
            certified_gain=float(start_ub-frontier.ub),Native_Runtime=native['Native_Runtime'],Work=native['Native_Work'],
            wall_seconds=perf_counter()-start,strict_candidates=sum(r['PASS'] for r in records),validation_failures=failures,
            candidates=records,radius=spec['hamming_radius'],lookback_slots=spec['lookback_slots'],free_binaries=len(spec['free_binary_columns']),
            native_receipt=native,capture_errors=capture_errors,restricted_ObjBound_is_Global_LB=False,
            starting_incumbent_sha256=ub.vector_sha(point),ending_incumbent_sha256=ub.vector_sha(best))
        write(path/'UB_RESULT.json',result);return result,best
    finally:model.dispose()

def mix_duals(best,new,alpha):
    a=F(alpha)
    if not 0<=a<=1:raise ValueError('CONVEX_DUAL_WEIGHT_REQUIRED')
    return {k:str(q) for k in sorted(set(best)|set(new),key=int)
            if (q:=(1-a)*F(best.get(k,'0'))+a*F(new.get(k,'0')))}

def lp_round(case,decomp,dual,ledger,frontier,path,method,kind='LP_ONLY'):
    start=perf_counter();start_lb=frontier.lb
    with ledger.cost('exact_price_build',path.name):prices=pricing.make_prices(case,decomp,dual)
    with ledger.cost('full96_prices',path.name):
        if kind=='MILP_AND_LP':result=pricing.run_pricing(case,decomp,prices,ledger,path,seconds_per_unit=75,lp_seconds=45)
        else:result=pricing.run_lp_prices(case,decomp,prices,ledger,path,lp_seconds=45)
    selected=read(path/'SELECTED_UNIT_DUALS_EXACT.json')
    with ledger.cost('independent_exact_Global_LB',path.name):
        certificate=verify.verify_global_lagrangian_bound(case,decomp,prices.coupling_dual,selected,nonunit_dual=prices.seed_nonunit_dual)
    full=certificate.pop('canonical_sparse_original_row_rational_dual')
    fullpath=path/'INDEPENDENT_FULL_ORIGINAL_DUAL_EXACT.json';write(fullpath,full)
    certificate.update(case_sha=CASE,dual_path=str(fullpath),dual_sha256=sha(fullpath),actual_certificate_completion_time=ledger.wall())
    certpath=path/'INDEPENDENT_GLOBAL_LB_CERTIFICATE.json';write(certpath,certificate)
    adopted=frontier.publish('LB',certificate['exact_Global_LB'],certificate,certpath,sha(certpath))
    if F(result['exact_global_certificate']['exact_bound'])!=F(certificate['exact_Global_LB']):raise ValueError('PRICE_PRODUCER_AND_INDEPENDENT_BOUND_DIFFER')
    if kind=='MILP_AND_LP':
        # Native status is diagnostic. Exact integer closure needs an exact
        # primal witness and equal exact lower/upper price certificates.
        differences={}
        for u in decomp.units:
            packet=path/(u+'_MILP_RAW_COLUMN.npz')
            if packet.is_file():
                with np.load(packet,allow_pickle=False) as z:raw=z['point'].copy()
                priced=sum((q*F(float(raw[j])) for j,q in prices.exact_objectives[u].items()),F(0))
                beta=F(result['local_exact_certificates'][u]['selected']['exact_bound'])
                differences[u]=dict(exact_integer_RAW_price_objective=str(priced),exact_complete_domain_LP_lower_bound=str(beta),
                    exact_price_primal_minus_lower=str(priced-beta),hard_exact_primal_rows_NOT_checked=True,
                    Native_integer_optimality_status_is_not_exact_certificate=True)
        write(path/'INTEGER_PRICING_CERTIFICATION.json',dict(case_sha=CASE,status='NOT_PROVEN',
            reason='No exact rational primal row/optimality proof or full branch certificate; Native OPTIMAL does not supply it',
            exact_price_upper_lower_diagnostics=differences,
            native_MILP_records=[r for r in result['records'] if r['kind']=='MILP'],Native_ObjBound_used_as_exact=False))
    row=dict(method=method,start_LB=float(start_lb),certified_LB=float(frontier.lb),candidate_LB=float(F(certificate['exact_Global_LB'])),
        adopted=adopted,certified_gain=float(frontier.lb-start_lb),wall_seconds=perf_counter()-start,
        certificate=str(certpath),certificate_sha256=sha(certpath),full_dual=str(fullpath),full_dual_sha256=sha(fullpath),
        pricing_result=str(path/'PRICING_RESULT.json'),Native_Runtime=sum(r['native']['Native_Runtime'] for r in result['records']),
        integer_hull_or_full_closure='NOT_PROVEN')
    write(path/'LB_RESULT.json',row);return row,full if adopted else None,result

def feedback_master(case,decomp,point,ledger,path):
    start=perf_counter();case.point=point.copy();columns={u:[] for u in decomp.units}
    for u,b in decomp.units.items():
        packet=ROOT/f'docs/v42_m1_fast_hybrid_20261008/artifacts/pricing_initial/{u}_MILP_RAW_COLUMN.npz'
        with np.load(packet,allow_pickle=False) as z:raw=z['point'].copy()
        replay=pricing.validate_local_column(case,b,raw)
        columns[u].append(dict(path=str(packet),sha256=sha(packet),unit=u,admission=replay))
        # Explicitly validate newest globally strict trajectory as a local column.
        current=pricing.validate_local_column(case,b,point[b.original_columns])
        if not current['PASS']:raise ValueError('LATEST_UB_TRAJECTORY_NOT_IN_ORIGINAL_LOCAL_DOMAIN')
    result=dw.run(case,decomp,columns,ledger,path,seconds=30)
    write(path/'LATEST_UB_FEEDBACK_AUDIT.json',dict(case_sha=CASE,PASS=True,latest_strict_UB_vector_sha256=ub.vector_sha(point),
        every_latest_unit_in_catalog=True,column_counts=result['identity']['column_count_by_unit'],
        restricted_RMP_objective_not_Global_LB=True,wall_seconds=perf_counter()-start))
    return result
