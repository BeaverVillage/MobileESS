"""Isolated model replay and independent complete assignments for diagnostics."""
import gzip
import json
import math
import re
import time
from pathlib import Path
from collections import Counter
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import DAY, OUT, WORK, RUNTIME, A0, B0, context
from .migration import state_at_d00, pending_in_day
from dayahead.v40g.domain import Option, materialize, deviation, audit
from .feasible_seed import row_audit, job_audit
from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
from dayahead.v41.reserve import diagnostics


class GridCache:
    """Vectorized evaluation of the same certified affine rows and polygons."""
    def __init__(self,ctx):
        from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters,is_dominated_mess_current_row
        from dayahead.grid_lp import LINE_POLYGON_FACES,V_MIN_SQUARED,V_MAX_SQUARED
        cs=ctx.coefficients;self.names=cs[0].branch_names
        self.li=np.array([i for i,n in enumerate(self.names) if not n.startswith('transformer.') and not is_dominated_mess_current_row(n)])
        self.ti=np.array([i for i,n in enumerate(self.names) if n.startswith('transformer.') and not is_dominated_mess_current_row(n)])
        self.ki=np.array([i for i,r in enumerate(cs[0].transformer_ratings) if r is not None])
        self.ratings=np.array([cs[0].transformer_ratings[i] for i in self.ki])
        self.pc=np.array([c.flow_p_constant for c in cs]);self.qc=np.array([c.flow_q_constant for c in cs])
        self.pm=np.array([c.flow_p_matrix[:,:12] for c in cs]);self.qm=np.array([c.flow_q_matrix[:,:12] for c in cs])
        self.vc=np.array([c.voltage_constant for c in cs]);self.vm=np.array([c.voltage_matrix[:12].T for c in cs])
        self.ic=np.array([c.current_constant for c in cs]);self.im=np.array([c.current_matrix[:12].T for c in cs])
        parameters=[anchored_polygon_parameters(c) for c in cs]
        self.bias=np.array([b for b,_,_ in parameters]);self.cm=np.array([r[:12].T for _,r,_ in parameters])
        self.cc=np.array([-r.T@c.anchor for c,(_,r,_) in zip(cs,parameters)])
        self.cos=np.cos(2*np.pi*np.arange(LINE_POLYGON_FACES)/LINE_POLYGON_FACES)
        self.sin=np.sin(2*np.pi*np.arange(LINE_POLYGON_FACES)/LINE_POLYGON_FACES)
        self.apothem=np.array([c.branch_limits for c in cs])*math.cos(math.pi/LINE_POLYGON_FACES)
        self.vlo=V_MIN_SQUARED;self.vhi=V_MAX_SQUARED;self.kfactor=math.cos(math.pi/LINE_POLYGON_FACES)

    def __call__(self,pcc):
        P=self.pc+np.einsum('tbk,tk->tb',self.pm,pcc)
        Q=self.qc+np.einsum('tbk,tk->tb',self.qm,pcc)
        poly=np.maximum.reduce([c*P+s*Q for c,s in zip(self.cos,self.sin)])
        loading=poly/self.apothem+self.bias+self.cc+np.einsum('tbk,tk->tb',self.cm,pcc)
        line=loading[:,self.li];t,j=np.unravel_index(np.argmax(line),line.shape)
        V=self.vc+np.einsum('tnk,tk->tn',self.vm,pcc)
        I=self.ic[:,self.ti]+np.einsum('tbk,tk->tb',self.im[:,self.ti],pcc)
        kva=np.hypot(P[:,self.ki],Q[:,self.ki])/self.ratings
        kvapoly=poly[:,self.ki]/(self.ratings*self.kfactor)
        counts=dict(voltage=int(((V<self.vlo-1e-9)|(V>self.vhi+1e-9)).sum()),
            line_current=int((line>1+1e-9).sum()),transformer_current=int((I>1+1e-9).sum()),
            transformer_kva=int((kva>1+1e-9).sum()),transformer_polygon=int((kvapoly>1+1e-9).sum()))
        name=self.names[self.li[j]]
        return dict(status='PASS' if not any(counts.values()) else 'FAIL',rho_max=float(line[t,j]),
            critical_slot=int(t),critical_line=name,critical_phase=name.rsplit('::',1)[-1],
            Vmin=float(np.sqrt(V.min())),Vmax=float(np.sqrt(V.max())),violations=counts,
            maximum_transformer_phase_current=float(I.max()),maximum_transformer_kVA=float(kva.max()))


class Data:
    def __init__(self):
        self.ctx=context();self.sites=tuple(self.ctx.capacity.aidc_ids)
        self.si={s:i for i,s in enumerate(self.sites)};self.si['UNASSIGNED']=-1;self.si['']=-1
        self.refs=read(RUNTIME/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
        self.byuid={r['job_uid']:r for r in self.refs}
        self.cohorts=read(A0/'EXACT_JOB_EQUIVALENCE_AUDIT.json')['cohorts']
        self.uidgroup={u:i for i,c in enumerate(self.cohorts) for u in c['members']}
        with np.load(B0/'dayahead/FROZEN_AIDC_POWER.npz') as z:
            self.base_power={k:z[k].copy() for k in z.files}
        self.base=read(B0/'dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
        self.cap=np.array([self.ctx.capacity.site_capacity[s] for s in self.sites])
        self.opts={}
        cache=WORK/'candidate_arrays.npz'
        if not cache.exists():
            with gzip.open(A0/'FULL_CANDIDATES.jsonl.gz','rt',encoding='utf-8') as stream:
                for line in stream:
                    x=json.loads(line)
                    self.opts[x['job_id']]=np.array([[self.si[o[0]],*o[1:6],self.si[o[6]]] for o in x['options']],dtype=np.int32)
            np.savez_compressed(cache,**self.opts)
        else:
            with np.load(cache) as z:self.opts={k:z[k] for k in z.files}
        self.reference_index={u:int(np.flatnonzero((o[:,0]==self.si[self.byuid[u]['AIDC_site']])&(o[:,3]<0))[0]) for u,o in self.opts.items()}
        self.grid=GridCache(self.ctx)
        check=self.grid(self.base_power['pcc'])
        assert abs(check['rho_max']-self.base[0])<1e-12 and check['status']=='PASS'

    def close(self):
        self.ctx.electrical.voltage.close();self.ctx.electrical.current.close()

    def option(self,uid,k):
        o=self.opts[uid][k]
        return Option('UNASSIGNED' if o[0]<0 else self.sites[o[0]],*map(int,o[1:6]),'' if o[6]<0 else self.sites[o[6]])

    def gpu(self,choices):
        g=self.base_power['gpu'].copy()
        for uid,k in choices.items():
            row=self.byuid[uid];opt=self.option(uid,k);n=row['requested_GPU']
            lo=max(24,row['start_slot'])-24;hi=min(120,row['end_slot'])-24
            if lo<hi:g[lo:hi,self.si[row['AIDC_site']]]-=n
            for s,a,b in opt.segments(row):
                lo=max(24,a)-24;hi=min(120,b)-24
                if lo<hi:g[lo:hi,self.si[s]]+=n
        return g

    def quick(self,choices,*,grid=True):
        # This is an exact single/multi-change substitution into the inherited
        # UID-serial WAN clock, not a relaxed network-capacity approximation.
        cursor=26
        for uid in sorted(choices):
            o=self.option(uid,choices[uid])
            if o.migrated:
                if o.transfer_start!=max(cursor,o.checkpoint):return None,'UID_SERIAL_WAN_CLOCK'
                cursor=o.transfer_end
        g=self.gpu(choices)
        if (g<0).any() or (g>self.cap).any():return None,'GPU_CAPACITY'
        p=np.column_stack([self.ctx.tables[s][np.arange(96),g[:,i]] for i,s in enumerate(self.sites)])
        reserve=diagnostics(self.ctx.v41_ml_snapshot,self.ctx.capacity,g)
        gr=self.grid(p) if grid else None
        if gr and gr['status']!='PASS':return None,'PLANNING_HARD_PHYSICS'
        if gr and gr['rho_max']>self.base[0]+1e-6+1e-9:return None,'ORIGINAL_RHO_UPPER_BOUND'
        vec=list(self.base);vec[0]=gr['rho_max'] if gr else None;vec[1]=reserve['mean_xi_GPUh']
        for uid,k in choices.items():
            o=self.option(uid,k);gidx=self.uidgroup[uid];rank=self.cohorts[gidx]['frozen_P5_rank']+1
            vec[2]+=int(o.migrated);vec[3]+=deviation(self.byuid[uid],o)
            vec[4]+=rank*(k-self.reference_index[uid])
        return dict(vector=vec,gpu=g,pcc=p,grid=gr,reserve=reserve),'PASS'

    def rows(self,choices):
        return [materialize(r,self.option(r['job_uid'],choices[r['job_uid']]),self.ctx.capacity,self.ctx.wan)
                if r['job_uid'] in choices else r for r in self.refs]


class ProbeModel:
    def __init__(self,data):
        self.d=data
        path=WORK/'original.mps'
        if not path.exists():
            with gzip.open(A0/'PRIMARY_MODEL.mps.gz','rb') as a,path.open('wb') as b:
                for block in iter(lambda:a.read(8*1024*1024),b''):b.write(block)
        self.m=gp.read(str(path));self.vs=self.m.getVars()
        self.names=self.m.getAttr('VarName',self.vs);self.ni={n:i for i,n in enumerate(self.names)}
        with np.load(A0/'POLICY_FEASIBLE_SEED.npz') as z:
            assert z['names'].tolist()==self.names
            self.seed=z['values'].copy()
        self.lb=np.array(self.m.getAttr('LB',self.vs));self.ub=np.array(self.m.getAttr('UB',self.vs))
        self.groups={};self.varparts={};self.choices={};self.placement={};self.routes={};self.arrivals={}
        for i,n in enumerate(self.names):
            hit=re.match(r'^(choice|placement|migration_route|migration_arrival)\[(\d+),(.+)\]$',n)
            if not hit:continue
            kind,g,tail=hit.groups();g=int(g);self.groups.setdefault(g,[]).append(i)
            self.varparts[i]=(kind,g,tail)
            target={'choice':self.choices,'placement':self.placement,'migration_route':self.routes,'migration_arrival':self.arrivals}[kind]
            target.setdefault(g,{})[tail]=i
        self.ids=np.array(sorted(i for ids in self.groups.values() for i in ids),dtype=int)
        self.dv=[self.vs[i] for i in self.ids]
        self.m.Params.OutputFlag=1;self.m.Params.LogToConsole=0;self.m.Params.Threads=4
        self.m.Params.Seed=20260905;self.m.Params.Method=1;self.m.Params.MIPGap=0
        self.m.Params.MIPGapAbs=0;self.m.Params.FeasibilityTol=1e-9;self.m.Params.IntFeasTol=1e-9;self.m.Params.OptimalityTol=1e-9
        self.m.Params.NodefileStart=.5;self.m.Params.NodefileDir=str(WORK)
        self.m.setAttr('Start',self.vs,self.seed.tolist());self.temporary=[]
        self.rho=self.vs[self.ni['rho_max']]
        self.xi=[v for v in self.vs if v.VarName.startswith('V41_H4_shortfall_GPUh[')]

    def close(self):self.m.dispose()

    def reset(self,groups=None):
        if self.temporary:self.m.remove(self.temporary);self.temporary=[]
        free=set(self.groups if groups is None else groups)
        opened=np.array([self.varparts[i][1] in free for i in self.ids])
        self.m.setAttr('LB',self.dv,np.where(opened,self.lb[self.ids],np.rint(self.seed[self.ids])).tolist())
        self.m.setAttr('UB',self.dv,np.where(opened,self.ub[self.ids],np.rint(self.seed[self.ids])).tolist())
        self.m.setObjective(self.rho,GRB.MINIMIZE);self.m.update()
        return free

    def set_assignment(self,choices):
        x=self.seed.copy()
        for uid,k in choices.items():
            g=self.d.uidgroup[uid];o=self.d.option(uid,k)
            refk=self.d.reference_index[uid]
            if g in self.choices:
                x[self.choices[g][str(refk)]]-=1;x[self.choices[g][str(k)]]+=1
            else:
                x[self.placement[g][str(refk)]]=0
                if not o.migrated:x[self.placement[g][str(k)]]=1
                else:
                    source=o.initial_site or self.d.byuid[uid]['AIDC_site']
                    x[self.routes[g][source+','+o.site]]=1
                    x[self.arrivals[g][o.site+','+str(o.transfer_end+1)]]=1
                    x[self.ni[f'migration_source[{g},{source}]']]=1
        quick,why=self.d.quick(choices)
        if quick is None:raise ValueError(why)
        power=quick['pcc'];gpu=quick['gpu'];controls=controls_from_trajectory(self.d.ctx.coefficients,power,())
        from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters
        for t,c in enumerate(self.d.ctx.coefficients):
            u=controls[t];_,corr,_=anchored_polygon_parameters(c)
            values={'v_squared':c.voltage_constant+c.voltage_matrix.T@u,
                'line_p':c.flow_p_constant+c.flow_p_matrix@u,
                'line_q':c.flow_q_constant+c.flow_q_matrix@u,'line_delta':corr.T@(u-c.anchor)}
            values['tx_p']=values['line_p'];values['tx_q']=values['line_q']
            for i,s in enumerate(self.d.sites):
                x[self.ni[f'GPU[{t},{s}]']]=gpu[t,i];x[self.ni[f'PCC[{t},{s}]']]=power[t,i]
            for prefix,vals in values.items():
                for i,v in enumerate(vals):
                    idx=self.ni.get(f'{prefix}[{t},{i}]')
                    if idx is not None:x[idx]=v
        x[self.ni['rho_max']]=quick['vector'][0]
        for k,v in enumerate(quick['reserve']['xi_GPUh']):x[self.ni[f'V41_H4_shortfall_GPUh[{k}]']]=v
        cursor=26
        for uid in sorted(self.d.byuid):
            if 'WAN_ready_'+uid not in self.ni:continue
            row=self.d.byuid[uid];o=self.d.option(uid,choices.get(uid,self.d.reference_index[uid]))
            ready=max(cursor,row['r1_first_valid_checkpoint'])
            x[self.ni['WAN_ready_'+uid]]=ready
            x[self.ni['WAN_selected_'+uid]]=int(o.migrated)
            if o.migrated:
                assert o.transfer_start==ready
                cursor=o.transfer_end
            x[self.ni['WAN_cursor_'+uid]]=cursor
        return x,quick

    def decode(self,values):
        selected={}
        for g,cohort in enumerate(self.d.cohorts):
            uids=sorted(cohort['members'])
            if g in self.choices:
                indices=[int(k) for k,i in self.choices[g].items() for _ in range(int(round(values[i])))]
            elif g in self.placement:
                indices=[int(k) for k,i in self.placement[g].items() if values[i]>.5]
                if not indices:
                    source,dest=next(k.split(',') for k,i in self.routes[g].items() if values[i]>.5)
                    destination,restart=next(k.split(',') for k,i in self.arrivals[g].items() if values[i]>.5)
                    assert destination==dest
                    a=self.d.opts[uids[0]]
                    idx=np.flatnonzero((a[:,0]==self.d.si[dest])&(a[:,6]==self.d.si[source])&(a[:,5]==int(restart)-1))
                    assert len(idx)==1;indices=[int(idx[0])]
            else:indices=[self.d.reference_index[u] for u in uids]
            assert len(indices)==len(uids)
            for u,k in zip(uids,indices):
                if k!=self.d.reference_index[u]:selected[u]=k
        return selected

    def certify(self,choices,label):
        self.reset()
        x,quick=self.set_assignment(choices)
        rows=self.d.rows(choices)
        state=audit(self.d.refs,rows,self.d.ctx.capacity,self.d.ctx.wan)
        physical,power=job_audit(rows,self.d.ctx)
        assert np.array_equal(power['gpu'],quick['gpu']) and np.array_equal(power['pcc'],quick['pcc'])
        independent_grid=evaluate_grid(self.d.ctx.coefficients,controls_from_trajectory(self.d.ctx.coefficients,power['pcc'],()),self.d.ctx.nodes)
        assert abs(independent_grid['rho_max']-quick['vector'][0])<1e-12
        quick['grid']=independent_grid;quick['vector'][0]=independent_grid['rho_max']
        algebra=row_audit(self.m,x)
        result=dict(status='PASS' if algebra['status']==physical['status']==state['status']=='PASS' else 'FAIL',
            choices=choices,vector=quick['vector'],delta=[a-b for a,b in zip(quick['vector'],self.d.base)],
            original_model_row_audit=algebra,physical=physical,service=state,grid=quick['grid'],
            original_model=record(A0/'PRIMARY_MODEL.mps.gz'),Actual_reads=0,production_modified=False)
        folder=WORK/'witnesses'/label;folder.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(folder/'ASSIGNMENT.npz',values=x)
        np.savez_compressed(folder/'POWER.npz',**power)
        write_json(folder/'JOBS.json',rows)
        result['assignment']=record(folder/'ASSIGNMENT.npz');result['power']=record(folder/'POWER.npz');result['jobs']=record(folder/'JOBS.json')
        write_json(OUT/(label+'.json'),result)
        return result,x

    def solve(self,label,groups,*,seconds=180,objective='P1',different=False,p1=None,p2=None,cross=None,only=None,start=None):
        opened=self.reset(groups)
        if p1 is not None:self.temporary.append(self.m.addConstr(1000*self.rho<=1000*p1,name='DIAGNOSTIC_P1_LOCK'))
        if p2 is not None:self.temporary.append(self.m.addConstr(gp.quicksum(self.xi)/81<=p2,name='DIAGNOSTIC_P2_LOCK'))
        if different:
            stay=[self.vs[i] for g in opened for i in self.groups[g] if self.seed[i]>0]
            self.temporary.append(self.m.addConstr(gp.quicksum(stay)<=sum(self.seed[v.index] for v in stay)-1,name='DIAGNOSTIC_NOT_B0'))
        if cross is not None:
            vars=[]
            for g in opened:
                row=self.d.byuid[self.d.cohorts[g]['members'][0]];src=row['AIDC_site']
                for tail,i in self.choices.get(g,{}).items():
                    o=self.d.option(row['job_uid'],int(tail))
                    if cross[src]!=cross[o.site]:vars.append(self.vs[i])
                for tail,i in self.placement.get(g,{}).items():
                    o=self.d.option(row['job_uid'],int(tail))
                    if cross[src]!=cross[o.site]:vars.append(self.vs[i])
                for tail,i in self.routes.get(g,{}).items():
                    a,b=tail.split(',')
                    if cross[src]!=cross[a] or cross[a]!=cross[b]:vars.append(self.vs[i])
            self.temporary.append(self.m.addConstr(gp.quicksum(vars)>=1,name='DIAGNOSTIC_CROSS_REGION'))
        if only:
            for i,(kind,g,tail) in self.varparts.items():
                if g not in opened:continue
                uid=self.d.cohorts[g]['members'][0];row=self.d.byuid[uid]
                forbidden=False
                if kind=='choice':
                    o=self.d.option(uid,int(tail))
                    forbidden=(only=='placement' and o.migrated) or (only=='migration' and (not o.migrated and o.site!=row['AIDC_site']))
                elif kind in ('migration_route','migration_arrival'):forbidden=only=='placement'
                elif kind=='placement':forbidden=only=='migration' and int(tail)!=self.d.reference_index[uid]
                if only=='migration' and kind=='migration_route':forbidden=tail.split(',')[0]!=row['AIDC_site']
                if forbidden:self.vs[i].UB=0
        self.m.setObjective(0 if objective=='feasibility' else gp.quicksum(self.xi)/81 if objective=='P2' else self.rho,GRB.MINIMIZE)
        self.m.update();self.m.setAttr('Start',self.vs,(self.seed if start is None else start).tolist())
        self.m.Params.TimeLimit=seconds;self.m.Params.WorkLimit=GRB.INFINITY
        self.m.Params.LogFile=str(OUT/(label+'.log'))
        began=time.perf_counter();self.m.optimize();elapsed=time.perf_counter()-began
        result=dict(status=int(self.m.Status),runtime=elapsed,solution_count=int(self.m.SolCount),
            objective=objective,bound=float(self.m.ObjBound),bound_scope='OPENED_NEIGHBORHOOD_ONLY',
            opened_groups=sorted(opened),opened_jobs=sum(len(self.d.cohorts[g]['members']) for g in opened),
            free_discrete_variables=sum(len(self.groups[g]) for g in opened),full_destinations_retained=True,
            temporary_conditions=dict(different=different,P1=p1,P2=p2,cross_region=cross is not None,ablation=only),
            start_vector=self.d.base,choices=None)
        if self.m.SolCount:
            result['raw_row_audit']=row_audit(self.m,self.m.getAttr('X',self.vs))
            chosen=self.decode(np.array(self.m.getAttr('X',self.vs)));result['choices']=chosen
            # Reconstruct all auxiliaries independently; remove every diagnostic
            # condition before validating the witness in the original model.
            cert,assignment=self.certify(chosen,label+'_ORIGINAL_MODEL_WITNESS')
            result['original_model_witness']=record(OUT/(label+'_ORIGINAL_MODEL_WITNESS.json'))
            result['best_vector']=cert['vector'];result['original_feasible']=cert['status']=='PASS'
        write_json(OUT/(label+'.json'),result)
        print('PROBE_FINISHED',label,{k:result.get(k) for k in ('status','runtime','solution_count','best_vector','original_feasible')},flush=True)
        return result
