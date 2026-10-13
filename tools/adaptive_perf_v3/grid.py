"""Whole96-slot critical coverage with original signed source projections."""
from collections import defaultdict
from fractions import Fraction as F
import numpy as np
from tools.minimax_beam1800.adapter import *
from tools.adaptive_perf_v3.bootstrap import *
from tools.time_decomposed_lb.grid import SelectiveAuthority
from tools.b2_root_lp_tightening.fractional_grid_oracle import metadata
def refresh(case,point,epoch):
    original=case.lift(point);rho=float(case.d['objective']@point+float(case.d['constant']))
    authority=SelectiveAuthority();selected=[];scanned=0;by_slot={}
    with np.load(g.COEFFICIENTS,allow_pickle=False) as z:axes={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}
    try:
        for t,ids in sorted(authority.security_by_slot.items()):
            thermal=[i for i in ids if str(authority.maps['row_names'][i]).startswith('line_thermal_face[')]
            lo,hi=min(thermal),max(thermal)+1;starts=np.asarray(authority.maps['indptr'][lo:hi+1],dtype=np.int64)
            left,right=int(starts[0]),int(starts[-1]);activity=np.add.reduceat(authority.maps['data'][left:right]*original[authority.maps['indices'][left:right]],starts[:-1]-left)
            top=[]
            for i in thermal:
                terms=authority.terms(i);rc=sum(w for j,w in terms if j==authority.rho);assert rc<0
                loading=rho+(float(activity[i-lo])-float(authority.maps['rhs'][i]))/(-rc)
                top.append((loading,i));scanned+=1
            top.sort(reverse=True);unique=set();slot_rows=[]
            for loading,i in top:
                md=metadata(str(authority.maps['row_names'][i]),axes);key=(md['asset'],md['phase'])
                if key in unique:continue
                unique.add(key);slot_rows.append(dict(original_row=i,slot=t,loading=loading,metadata=md))
                if len(slot_rows)==4:break
            by_slot[t]=slot_rows
        assert scanned==403968
        near=[row for rows in by_slot.values() for row in rows if row['loading']>=rho-.025]
        # Round-robin by 12-slot time band and asset/phase. A secondary closest
        # row per band covers future charging rebound even below near-binding.
        groups=defaultdict(list)
        for row in near:groups[row['slot']//12].append(row)
        for band in range(8):
            choices=groups[band] or [r for t,rows in by_slot.items() if t//12==band for r in rows]
            choices.sort(key=lambda r:(-r['loading'],r['original_row']))
            assets=set();count=0
            for row in choices:
                key=(row['metadata']['asset'],row['metadata']['phase'],row['slot']//3)
                if key in assets:continue
                assets.add(key);selected.append(row);count+=1
                if count==4:break
        # Every slot contributes its actual worst row, including charging windows.
        selected.extend(rows[0] for rows in by_slot.values())
        unique_selected={row['original_row']:row for row in selected}
        selected=list(unique_selected.values())
        # Add distinct near-critical phase/asset rows, capped at160.
        used={r['original_row'] for r in selected}
        for row in sorted(near,key=lambda r:(-r['loading'],r['original_row'])):
            if row['original_row'] not in used:selected.append(row);used.add(row['original_row'])
            if len(selected)>=160:break
        packets=[]
        for row in selected:
            packet=authority.project(row['original_row'],row['slot']);packet.update(metadata=row['metadata'],current_loading=row['loading'],slot=row['slot'])
            packets.append(packet)
        raw_ids={r['original_row'] for r in packets}|{i for r in packets for i in r['helper_rows']}
        raw=[authority.raw(i) for i in sorted(raw_ids)]
        columns={j for row in raw for j,_ in row['terms']}
        closure=dict(source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,source_files=authority.records,rows=raw,
            columns={str(j):dict(name=str(authority.maps['names'][j]),lower_hex=float(authority.maps['lower'][j]).hex(),
                upper_hex=float(authority.maps['upper'][j]).hex(),type=str(authority.maps['types'][j])) for j in sorted(columns)})
        path=DOCS/f'grid/epoch{epoch:02d}';path.mkdir(parents=True,exist_ok=False)
        write(path/'RAW_SOURCE_CLOSURE.json',closure)
        context=dict(PASS=True,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,center_vector_sha=v.vector_sha(point),
            current_verified_UB=rho,near_binding_margin=.025,all_thermal_rows_scanned=scanned,
            selected_rows=len(packets),rows=packets,near_binding_candidates=len(near),
            selection='Time-band / asset / phase / slot coverage then near-binding; all96 slots plus near-critical rows, at most160 original rows',
            raw_source_closure=record(path/'RAW_SOURCE_CLOSURE.json'),Native_optimize_calls=0,
            score_is_heuristic_not_FULL_feasibility_or_bound=True)
        write(path/'CRITICAL_MINIMAX_CONTEXT.json',context)
        return context,path/'CRITICAL_MINIMAX_CONTEXT.json'
    finally:authority.close()
