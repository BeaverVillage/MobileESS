"""Literal <=8-slot physical projection, with crossing arcs and free SOC.

No Gurobi is imported. No Full96 matrix is built or loaded. Certified literal
vehicle slices are read one at a time, and only the preregistered window matrix
is assembled. Original grid row counts are read from the frozen domain axes.
If the literal route binaries already exceed the window cap, the entire grid
matrix is deliberately not constructed and the partial-model scope is explicit.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gc
from pathlib import Path
import sys
import time
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.critical_grid_cg.verify import read,write,sha,npz,require,canonical_data,axis,digests

OUT=ROOT/'docs/v42_b2_time_decomposed_global_lb/window_native0'
OLD=ROOT/'docs/v42_physical_global_lb_pilot'
SOURCE=Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
SECURITY={'line_thermal_face','transformer_kVA','NormalAmps','voltage_upper','voltage_lower'}
GATES={'connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','connected_Qmax','connected_Qmin','PCS16'}


def replay(A,d,x):
    delta=A@x-d['rhs']
    residual=np.where(d['senses']=='=',abs(delta),np.where(d['senses']=='<',delta,-delta))
    binary=np.flatnonzero(d['vtypes']=='B')
    return {'max_row_violation':max(0.,float(residual.max(initial=0.))),
            'max_bound_violation':max(0.,float((d['lb']-x).max(initial=0.)),float((x-d['ub']).max(initial=0.))),
            'max_integer_error':float(abs(x[binary]-np.rint(x[binary])).max(initial=0.))}


def audit(out=OUT):
    started=time.perf_counter();pre=read(out/'WINDOW_PREREGISTRATION.json');a,b=pre['window']
    require((a,b)==(88,96) and b-a<=8,'WINDOW_PREREGISTRATION_CHANGED')
    source=read(OLD/'NATIVE0.json');proof=read(OLD/'INDEPENDENT_NATIVE0.json')
    require(source['PASS'] and proof['PASS'] and proof['all_single_owner_physical_rows_bounds_and_integer_types_retained'],
            'ORIGINAL_LITERAL_UNIT_AUTHORITY_NOT_CERTIFIED')
    p=SOURCE/'SCIENTIFIC_CASE_IDENTITY.json'
    require(sha(p)==source['source_records'][str(p)],'ORIGINAL_ROUTE_AUTHORITY_CHANGED')
    case=read(p);domain=case['physical_prescreen_authority']['proof'];graph=domain['arcs'];battery=domain['battery']
    require(case['case_sha']==source['case_sha'] and domain['horizon']==96 and domain['original_matrix_bridge']['actual_departure_energy_debit_verified'],
            'ORIGINAL_CASE_OR_DEPARTURE_DEBIT_CHANGED')
    blocks=[];packets=[];starts=[];units=[];all_sources={str(p):sha(p)}
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        spec=source['models'][unit]
        for suffix,key in (('A','matrix_sha'),('DATA','data_sha'),('AXES','axes_sha')):
            f=OLD/f'UNIT_{unit}_{suffix}.npz';require(sha(f)==spec[key],'LITERAL_UNIT_BYTES_CHANGED');all_sources[str(f)]=sha(f)
        A=sparse.load_npz(OLD/f'UNIT_{unit}_A.npz').tocsr();raw=npz(OLD/f'UNIT_{unit}_DATA.npz');d=canonical_data(raw)
        axes=npz(OLD/f'UNIT_{unit}_AXES.npz');warm=OLD/f'UNIT_{unit}_START.npz';original_x=npz(warm)['point'];all_sources[str(warm)]=sha(warm)
        names=list(map(str,d['names']));arc={int(axis(n)[1][1]):i for i,n in enumerate(names) if axis(n)[0]=='arc'}
        selected_arcs={k:c for k,c in arc.items() if graph[k][1]<b and graph[k][3]>a}
        cols=set(selected_arcs.values())
        for c,n in enumerate(names):
            fam,coordinates=axis(n)
            if fam in ('Pch','Pdis','Q') and a<=int(coordinates[2])<b:cols.add(c)
            if fam=='charge_mode' and a<=int(coordinates[1])<b:cols.add(c)
            if fam=='SOC' and a<=int(coordinates[1])<=b:cols.add(c)
        cols=np.array(sorted(cols),dtype=np.int64);mapping={int(c):j for j,c in enumerate(cols)}
        rr=[];cc=[];vv=[];rhs=[];senses=[];row_names=[];retained=[];family_count=Counter();energy_times=set()
        for r,label in enumerate(d['row_names']):
            fam=axis(label)[0]
            if fam not in GATES|{'energy_balance'}:continue
            lo,hi=A.indptr[r:r+2];oldcols=A.indices[lo:hi];values=A.data[lo:hi]
            powers=[int(c) for c in oldcols if axis(names[c])[0] in ('Pch','Pdis','Q')]
            require(powers,'PHYSICAL_ROW_WITHOUT_POWER_AXIS')
            times={int(axis(names[c])[1][2]) for c in powers}
            require(len(times)==1,'CROSS_TIME_IMMEDIATE_OR_ENERGY_ROW');t=next(iter(times))
            if not a<=t<b:continue
            require(all(int(c) in mapping for c in oldcols),'WINDOW_ROW_HAS_UNMAPPED_DEPENDENCY')
            j=len(rhs)
            for c,v in zip(oldcols,values):rr.append(j);cc.append(mapping[int(c)]);vv.append(float(v))
            rhs.append(float(d['rhs'][r]));senses.append(str(d['senses'][r]));row_names.append(f'{unit}:{fam}:{int(axes["rows"][r])}')
            retained.append(int(axes['rows'][r]));family_count[fam]+=1
            if fam=='energy_balance':energy_times.add(t)
        require(energy_times==set(range(a,b)),'WINDOW_ENERGY_RECURRENCE_INCOMPLETE')
        nodes=defaultdict(dict);entry={};exit={};cross_in=[];cross_out=[];spanning=[]
        for k,c in selected_arcs.items():
            origin,depart,dest,end,route=graph[k];j=mapping[c]
            require(0<=depart<end<=96 and d['vtypes'][c]=='B' and d['lb'][c]==0 and d['ub'][c]==1,'ORIGINAL_ARC_TIME_OR_BINARY_BOX_CHANGED')
            if a<depart<b:nodes[origin,depart][j]=1.
            if a<end<b:nodes[dest,end][j]=-1.
            if depart<=a<end:entry[j]=1.
            if depart<b<=end:exit[j]=1.
            if depart<a<end:cross_in.append(k)
            if depart<b<end:cross_out.append(k)
            if depart<a and end>b:spanning.append(k)
        for node,terms in sorted(nodes.items()):
            j=len(rhs)
            for c,v in sorted(terms.items()):rr.append(j);cc.append(c);vv.append(v)
            rhs.append(0.);senses.append('=');row_names.append(f'window_flow[{unit},{node[0]},{node[1]}]');family_count['window_flow']+=1
        for label,terms in (('window_free_entry',entry),('window_free_exit',exit)):
            require(terms,'EMPTY_WINDOW_PATH_INTERFACE');j=len(rhs)
            for c,v in sorted(terms.items()):rr.append(j);cc.append(c);vv.append(v)
            rhs.append(1.);senses.append('=');row_names.append(f'{label}[{unit}]');family_count[label]+=1
        W=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rhs),len(cols)))
        packet={key:d[key][cols] for key in ('names','lb','ub','vtypes')}
        packet.update(c=np.zeros(len(cols)),rhs=np.asarray(rhs),senses=np.asarray(senses),row_names=np.asarray(row_names),constant=np.array(0.))
        warm_x=original_x[cols];rep=replay(W,packet,warm_x)
        require(max(rep.values())<=1e-7,'ORIGINAL_U4_WINDOW_PHYSICAL_LIFT_FAILED')
        soc=[j for j,n in enumerate(packet['names']) if axis(n)[0]=='SOC']
        require(len(soc)==b-a+1 and all(packet['lb'][j]==battery['minimum'] and packet['ub'][j]==battery['maximum'] for j in soc),
                'WINDOW_FREE_SOC_INTERFACE_NOT_ORIGINAL_BOX')
        units.append({'unit':unit,'rows':W.shape[0],'columns':W.shape[1],'binary':int(np.count_nonzero(packet['vtypes']=='B')),'nnz':int(W.nnz),
                      'original_rows_retained':len(retained),'interior_original_flow_nodes':len(nodes),'row_families':dict(family_count),
                      'crossing_entry_arcs':len(cross_in),'crossing_exit_arcs':len(cross_out),'spanning_arcs':len(spanning),
                      'free_initial_and_terminal_SOC':True,'terminal_SOC_760_not_imposed':True,'original_u4_physical_lift':rep})
        blocks.append(W);packets.append(packet);starts.append(warm_x)
        del A,raw,d,axes,original_x;gc.collect()
    W=sparse.block_diag(blocks,format='csr');joined={key:np.concatenate([p[key] for p in packets]) for key in ('names','lb','ub','vtypes','c','rhs','senses','row_names')}
    joined['constant']=np.array(0.);wx=np.concatenate(starts)
    sparse.save_npz(out/'WINDOW_PHYSICS_A.npz',W);np.savez_compressed(out/'WINDOW_PHYSICS_DATA.npz',**joined);np.savez_compressed(out/'WINDOW_PHYSICS_U4.npz',x=wx)
    msha,dsha=digests(W,joined);binary=int(np.count_nonzero(joined['vtypes']=='B'))
    # Domain axes alone are sufficient for a native model-size lower bound.
    full_domain=SOURCE/'FULL_DATA.npz'
    require(sha(full_domain)==source['source_records'][str(full_domain)],'ORIGINAL_FULL_DOMAIN_BYTES_CHANGED')
    all_sources[str(full_domain)]=sha(full_domain)
    with np.load(full_domain,allow_pickle=False) as z:security_names=z['row_names']
    security_counts=Counter()
    for n in security_names:
        if str(n).split('[',1)[0] not in SECURITY:continue
        fam,coords=axis(n)
        if a<=int(coords[0])<b:security_counts[fam]+=1
    require(sum(security_counts.values())==8*8485,'WINDOW_ORIGINAL_GRID_ROW_CENSUS_CHANGED')
    gates={'binary_cap':binary<=1500,'minimum_rows_cap':W.shape[0]+sum(security_counts.values())<=100000,'partial_physics_nnz_cap':W.nnz<=1500000}
    receipt={'PASS':True,'schema':'V42_LITERAL_WINDOW_PROJECTION_NATIVE0_V1','window':[a,b],'source18r':source['base_commit'],'case_sha':source['case_sha'],
             'Native_optimize_calls':0,'Gurobi_imported':False,'FULL96_model_reconstructed':False,'FULL_CSR_loaded':False,
             'original_FULL_to_window_physical_projection_proved':True,'all_crossing_arcs_preserved':True,
             'boundary_locations_free':True,'boundary_SOC_original_box_only':True,'original_terminal_SOC_not_imposed':True,
             'departure_debit_timing_original':True,'entry_transit_power_zero_until_original_connect':True,
             'exit_arcs_and_future_outside_activity_not_restricted':True,'units':units,
             'physical_dimensions':{'rows':W.shape[0],'columns':W.shape[1],'binary':binary,'nnz':int(W.nnz)},
             'raw_original_window_grid_row_counts':dict(security_counts),'minimum_complete_rows':W.shape[0]+sum(security_counts.values()),
             'complete_window_model_constructed':False,'all_window_grid_coefficients_eliminated_and_validated':False,
             'why_complete_grid_not_built':'Literal route binary count alone exceeds the preregistered safety cap; construction stops before full grid transport or Native readback.',
             'safety_gates':gates,'Window_Native_authorized':False,'Window_Optimize_calls':0,
             'classification':'WINDOW_LITERAL_BINARY_RESOURCE_STOP' if not gates['binary_cap'] else 'WINDOW_PHYSICAL_DESIGN_ONLY',
             'physical_matrix_sha256':msha,'physical_domain_sha256':dsha,'source_records':all_sources,
             'original_u4_physical_lift':replay(W,joined,wx),'proof_scope':'Constructed literal physical window and its source projection, not a complete grid model or a global-bound certificate.',
             'proof':'An original binary unit path crosses each boundary once. Keep every arc with depart<b and connect>a. Its incidence at a<time<b is unchanged; the selected path contributes exactly one active arc at each aggregate entry/exit cut. Crossing arcs encode free transit interfaces. SOC copies E_a,...,E_b with original boxes and exact internal energy rows. Incoming travel was already debited before a, while departures in [a,b) remain in their original energy row. Connected P/Q stay gates and integer modes/PCS16 are copied unchanged. All outside flow, origin, initial/terminal SOC and future rebound restrictions are removed.',
             'file_sha256':{n:sha(out/n) for n in ('WINDOW_PHYSICS_A.npz','WINDOW_PHYSICS_DATA.npz','WINDOW_PHYSICS_U4.npz','WINDOW_PREREGISTRATION.json')},
             'wall_seconds':time.perf_counter()-started}
    write(out/'WINDOW_NATIVE0_DESIGN.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);args=p.parse_args()
    result=audit(args.out);print({k:result[k] for k in ('PASS','classification','physical_dimensions','minimum_complete_rows','wall_seconds')})
