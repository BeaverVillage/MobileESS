"""Whole-horizon thermal critical selection and exact original helper projection."""
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import numpy as np
from tools.minimax_beam1800.adapter import *
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
        # Add distinct near-binding slots in score order, capped at64.
        used={r['original_row'] for r in selected}
        for row in sorted(near,key=lambda r:(-r['loading'],r['original_row'])):
            if row['original_row'] not in used:selected.append(row);used.add(row['original_row'])
            if len(selected)>=64:break
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
            selection='Time-band / asset / phase / slot coverage then near-binding; at most64 original rows',
            raw_source_closure=record(path/'RAW_SOURCE_CLOSURE.json'),Native_optimize_calls=0,
            score_is_heuristic_not_FULL_feasibility_or_bound=True)
        write(path/'CRITICAL_MINIMAX_CONTEXT.json',context)
        return context,path/'CRITICAL_MINIMAX_CONTEXT.json'
    finally:authority.close()

class Minimax:
    def __init__(self,case,point,context):
        self.case=case;self.context=context;self.rows=context['rows'];self.m=len(self.rows)
        self.units=sorted(case.graph[1]);self.sites=list(case.graph[0]);self.site_id={s:i for i,s in enumerate(self.sites)}
        self.times=np.asarray([r['slot'] for r in self.rows]);self.loading=np.asarray([r['current_loading'] for r in self.rows])
        self.coeff=np.zeros((4,24,self.m,3));self.base=np.empty(self.m)
        original=case.lift(point);values=dict(zip(map(str,case.original_d['names']),map(float,original)))
        for i,row in enumerate(self.rows):
            terms={n:float(F(c)) for n,c in row['coeff'].items()};scale=-terms['rho_max'];assert scale>0
            all_activity=sum(c*values[name] for name,c in terms.items() if name!='rho_max')
            mess=0.
            for u_i,u in enumerate(self.units):
                for s_i,s in enumerate(self.sites):
                    for f_i,f in enumerate(('Pch','Pdis','Q')):
                        name=f'{f}[{u},{s},{row["slot"]}]';co=terms.get(name,0.)/scale
                        self.coeff[u_i,s_i,i,f_i]=co;mess+=co*values.get(name,0.)
            self.base[i]=(all_activity-float(F(row['rhs'])))/scale-mess
        vertices=np.asarray([[float(F(p)),float(F(q))] for p,q in read(DOCS/'SIGNED_SELECTION_CONTEXT.json')['PCS16_vertices_exact']])
        p=vertices[:,0];q=vertices[:,1]
        # Static instantaneous PCS envelope is a ranking ingredient only.
        supports=np.where(p[None,None,None,:]>=0,
            self.coeff[:,:,:,1,None]*p+self.coeff[:,:,:,2,None]*q,
            self.coeff[:,:,:,0,None]*(-p)+self.coeff[:,:,:,2,None]*q)
        self.support=np.minimum(0.,supports.min(axis=-1));self.vertices=vertices
        self.best_vertex=np.argmin(supports,axis=-1)
        self.path_cache={}
        self.baseline_paths=current_paths(case,point)
        self.base_support=np.vstack([self.path_vector(u,self.baseline_paths[u]) for u in self.units])
        self.optimistic=np.minimum(self.support.min(axis=1),self.base_support)
        self.future_cache={};self.moves_by_origin=defaultdict(list)
        names={str(n):j for j,n in enumerate(case.original_d['names'])}
        for u in self.units:
            for k,a in enumerate(case.graph[2]):
                j=names.get(f'arc[{u},{k}]')
                if a[-1] is not None and j is not None and case.original_d['upper'][j]>=1.:
                    self.moves_by_origin[u,a[0]].append((a[1],a[3],self.site_id[a[2]]))

    def path_vector(self,u,path):
        key=(u,tuple(path))
        if key in self.path_cache:return self.path_cache[key][0]
        index=self.units.index(u);out=np.zeros(self.m);battery=self.case.graph[3]
        soc=battery.initial;spent=0.;rebound=np.zeros(self.m)
        critical=set(map(int,self.times));stays=[self.case.graph[2][k] for k in path if self.case.graph[2][k][-1] is None]
        # Low-loading connected windows include precharge and terminal recovery.
        trough={a[1] for a in sorted(stays,key=lambda a:(max([0.]+[self.loading[i] for i in range(self.m) if self.times[i]==a[1]]),a[1]))[:16]}
        for k in path:
            a=self.case.graph[2][k]
            if a[-1] is not None:soc-=float(a[-1].energy_kwh);spent+=float(a[-1].energy_kwh);continue
            t=a[1];site=self.site_id[a[0]];mask=self.times==t
            if t in critical:
                # Worst active row chooses one PCS vertex for this vehicle,
                # then the current SOC envelope limits active power. Ranking
                # uses the actual efficiency, rather than an unlimited sum.
                active=np.flatnonzero(mask);i=active[np.argmax(self.base[active])]
                p,q=self.vertices[self.best_vertex[index,site,i]].copy()
                if p>=0:
                    p=min(p,max(0.,soc-battery.minimum)*battery.eta_discharge/battery.dt_hours)
                    soc-=p*battery.dt_hours/battery.eta_discharge;spent+=p*battery.dt_hours/battery.eta_discharge
                    out[mask]=self.coeff[index,site,mask,1]*p+self.coeff[index,site,mask,2]*q
                else:
                    charge=min(-p,max(0.,battery.maximum-soc)/battery.dt_hours/battery.eta_charge)
                    soc+=charge*battery.dt_hours*battery.eta_charge
                    out[mask]=self.coeff[index,site,mask,0]*charge+self.coeff[index,site,mask,2]*q
            elif t in trough:
                charge=min(battery.p_limit,max(0.,battery.maximum-soc)/battery.dt_hours/battery.eta_charge)
                soc+=charge*battery.dt_hours*battery.eta_charge
            soc=min(battery.maximum,max(battery.minimum,soc)) # Heuristic only; no raw point is changed.
        # Recovery estimate is charged to connected windows inside96. Missing
        # terminal recovery capacity worsens ranking; it is never exact pruning.
        need=max(0.,battery.terminal-soc)
        recovery=[a for a in stays if a[1] in trough]
        power=min(battery.p_limit,need/(battery.eta_charge*battery.dt_hours*max(1,len(recovery))))
        for a in recovery:
            mask=self.times==a[1];rebound[mask]+=self.coeff[index,self.site_id[a[0]],mask,0]*power
        unresolved=max(0.,need-len(recovery)*battery.dt_hours*battery.eta_charge*power)
        self.path_cache[key]=(out,rebound,unresolved,spent)
        return out

    def peak(self,paths):
        vector=self.base.copy();rebound=np.zeros(self.m);unresolved=0.
        for u,path in paths.items():
            vector+=self.path_vector(u,path)
            _,extra,unserved,_=self.path_cache[u,tuple(path)];rebound+=extra;unresolved+=unserved
        # Minimax, including the combined effect of every selected vehicle.
        return float(np.max(vector+rebound)+1e-4*unresolved),vector.tolist(),rebound.tolist()

    def partial_peak(self,u,site,t,vec,soc_upper,remaining_stays):
        index=self.units.index(u);future=self.times>=t
        completion=vec.copy()
        # Optimistic future envelopes help look ahead beyond accrued relief.
        # Reachability and SOC are deliberately optimistic, not dominance.
        key=(u,site,t)
        if key not in self.future_cache:
            value=self.support[index,self.site_id[site]].copy()
            arcs=np.asarray(self.moves_by_origin[u,site],dtype=int).reshape(-1,3)
            if len(arcs):
                relevant=arcs[arcs[:,0]>=t]
                for i,slot in enumerate(self.times):
                    reachable=np.unique(relevant[relevant[:,1]<=slot,2]) if len(relevant) else []
                    if len(reachable):value[i]=min(value[i],float(self.support[index,reachable,i].min()))
            self.future_cache[key]=value
        completion[future]=self.future_cache[key][future]
        available=max(0.,soc_upper-self.case.graph[3].minimum)
        active=int(np.count_nonzero(future));energy_scale=min(1.,available/(max(1,active)*self.case.graph[3].dt_hours*self.case.graph[3].p_limit))
        completion[future]*=.5+.5*energy_scale
        return float(np.max(self.base+self.base_support.sum(axis=0)-self.base_support[index]+completion))
