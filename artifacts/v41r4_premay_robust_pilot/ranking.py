"""Scenario-aware ordering of the existing single/compound candidate domain."""
from pathlib import Path
import ast,inspect,time
import numpy as np
import calibrate as c
import support
from dayahead.v41 import physics_ranking as original

class Ranking(original.Ranking):
    def __init__(self,contexts,jobs,power):
        original.K=10
        super().__init__(contexts['S0'],jobs,power)
        self.scenario=[]
        self.robust_started=time.perf_counter()
        for label,ctx in contexts.items():
            with np.load(support.RUN/'B0'/label/'physics/OPENDSS_PHASE_ARRAYS.npz') as z:
                li=np.flatnonzero(z['branch_kinds']=='line');rho=z['phase_current_loading_pu'][:,li]
                names=z['branch_names'][li].tolist();phases=z['branch_phases'][li].tolist()
            indices=[ctx.coefficients[0].branch_names.index(n+'::'+p) for n,p in zip(names,phases)]
            # The anchored polygon is constructed to have this exact tangent.
            sens=np.array([x.current_matrix[:12,indices].T for x in ctx.coefficients])
            rows=sorted(((float(rho[t,j]),names[j],phases[j],t,j) for t in range(96) for j in range(len(li))),key=lambda r:(-r[0],r[1],r[2],r[3]))
            active=rows[:10];at=np.array([r[3] for r in active]);aj=np.array([r[4] for r in active])
            env=rho.max(axis=1);tj=rho.argmax(axis=1);tstar,jstar=rows[0][3:]
            self.scenario.append(dict(label=label,S=sens,active=active,at=at,AS=sens[at,aj],Arho=np.array([r[0] for r in active]),
                ES=sens[np.arange(96),tj],weight=env/env.max(),env=env,tstar=tstar,jstar=jstar,criticalS=sens[tstar,jstar],line=names,phase=phases))
        worst=max(self.scenario,key=lambda r:r['env'].max())
        for key in ('S','ES','weight','env','tstar','jstar','criticalS','line','phase'):setattr(self,key,worst[key])
        self.active=[r for s in self.scenario for r in s['active']]
        self.at=np.concatenate([s['at'] for s in self.scenario]);self.AS=np.concatenate([s['AS'] for s in self.scenario]);self.Arho=np.concatenate([s['Arho'] for s in self.scenario])
        prefixes={}
        for uid,d in self.data.items():
            n=len(d['opts']);g=d['g']
            if not g:d['gamma_s']=np.zeros((3,n));continue
            plus,minus=self.gains(g)
            if g not in prefixes:
                rows=[]
                for s in self.scenario:
                    remove=np.vstack((np.zeros(96),(s['ES']*minus).T));add=np.vstack((np.zeros(96),(s['ES']*plus).T))
                    relief=np.maximum(remove[:,None,:]-add[None,:,:],0)*s['weight']
                    crit=np.r_[0,s['criticalS']*minus[s['tstar']]][:,None]-np.r_[0,s['criticalS']*plus[s['tstar']]][None,:]
                    for i in range(13):relief[i,i]=0;crit[i,i]=0
                    rows.append((np.pad(np.cumsum(relief,axis=2),((0,0),(0,0),(1,0))),crit))
                prefixes[g]=rows
            exposure=[];leverage=[];gammas=[]
            for s,(prefix,crit) in zip(self.scenario,prefixes[g]):
                e=np.zeros(n);lev=np.zeros(n)
                for origin,dst,lo,hi in d['parts']:
                    valid=hi>lo;hi=np.maximum(lo,hi);a,b=origin+1,dst+1
                    e+=np.where(valid,prefix[a,b,hi]-prefix[a,b,lo],0)
                    lev+=np.where(valid&(lo<=s['tstar'])&(s['tstar']<hi),crit[a,b],0)
                gamma=np.fromiter((s['criticalS'][self.site[o.initial_site or self.jobs[uid]['AIDC_site']]]-s['criticalS'][self.site[o.site]] for o in d['opts']),float,n)
                exposure.append(e);leverage.append(lev);gammas.append(gamma)
            d['exposure']=np.min(exposure,axis=0);d['leverage']=np.min(leverage,axis=0);d['gamma_s']=np.array(gammas);d['gamma']=d['gamma_s'].min(axis=0)
        self.timers['robust_metadata_seconds']=time.perf_counter()-self.robust_started

    def score_active(self,uid,indices):
        indices=np.asarray(indices);d=self.data[uid]
        delta=self.delta_gpu(uid,indices,self.at);base=self.gpu[self.at];occupancy=base[None]+delta
        values=np.broadcast_to(self.Arho,(len(indices),len(self.at))).copy()
        plus,minus=self.gains(d['g']) if d['g'] else (None,None)
        for i,site in enumerate(self.sites):
            new=occupancy[:,:,i];table=self.ctx.tables[site]
            exact=table[self.at[None],np.clip(new,0,self.cap[i])]-self.pcc[self.at,i]
            if d['g']:
                exact=np.where(new>self.cap[i],plus[self.at,i],exact)
                exact=np.where(new<0,-minus[self.at,i],exact)
            values+=exact*self.AS[:,i]
        return values.max(axis=1)

    def net_score(self,components):
        delta=sum((self.delta_gpu(u,[k],np.arange(96))[0] for u,k in components),np.zeros((96,12),int))
        occupancy=self.gpu+delta;feasible=bool(np.all((occupancy>=0)&(occupancy<=self.cap)))
        pq=np.column_stack([self.ctx.tables[s][np.arange(96),np.clip(occupancy[:,i],0,self.cap[i])]-self.pcc[:,i] for i,s in enumerate(self.sites)])
        per=[]
        for i,s in enumerate(self.scenario):
            per.append(dict(P1=float((s['Arho']+np.einsum('ki,ki->k',s['AS'],pq[s['at']])).max()),
                exposure=float(np.sum(s['weight']*np.maximum(-np.einsum('ti,ti->t',s['ES'],pq),0))),
                leverage=float(-s['criticalS']@pq[s['tstar']]),
                gamma=float(sum(self.data[u]['gamma_s'][i,k] for u,k in components))))
        return dict(P1_hat_active=max(s['P1'] for s in per),ExposureRelief=min(s['exposure'] for s in per),
            critical_leverage=min(s['leverage'] for s in per),differential_sensitivity_relief=min(s['gamma'] for s in per),
            net_capacity_feasible=feasible,all_constituents=len(components),net_gpu_delta=delta,net_pcc_delta=pq,per_scenario=per)

# Retain the exact existing anchor construction and consumed ordering, changing
# only the compound differential score from a sum of minima to a joint minimum.
tree=ast.parse(inspect.getsource(original.Ranking.reorder).lstrip())
changes=0
for node in ast.walk(tree):
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.slice,ast.Constant) and t.slice.value=='differential_sensitivity_relief' for t in node.targets):
        node.value=ast.parse("s['differential_sensitivity_relief']",mode='eval').body;changes+=1
assert changes==1
ast.fix_missing_locations(tree)
ns=dict(vars(original));exec(compile(tree,__file__,'exec'),ns);Ranking.reorder=ns['reorder']

def prepare(contexts,jobs,power):
    started=time.perf_counter();r=Ranking(contexts,jobs,power);original.INSTANCE=r
    ranked,info=r.tier(sorted(r.jobs))
    expected=c.read(c.OUT/'V41R4_V41R3_RANKING_PREREQUISITE.json')
    assert r.count==expected['candidate_count'] and r.domain_digest.hexdigest()==expected['candidate_set_SHA']
    # Numerical compound checks use actual options but do not solve a policy.
    unique=[]
    for u,k,*_ in ranked:
        if u not in [x[0] for x in unique]:unique.append((u,k))
        if len(unique)==3:break
    tests=[]
    for width in (2,3):
        part=unique[:width];x=r.net_score(part)
        assert x['all_constituents']==width
        brute=sum((r.delta_gpu(u,[k],np.arange(96))[0] for u,k in part),np.zeros((96,12),int))
        assert np.array_equal(brute,x['net_gpu_delta'])
        assert x['P1_hat_active']==max(v['P1'] for v in x['per_scenario'])
        assert x['ExposureRelief']==min(v['exposure'] for v in x['per_scenario'])
        tests.append({k:v for k,v in x.items() if k not in ('net_gpu_delta','net_pcc_delta')})
    audit=dict(status='PASS',candidate_count=r.count,candidate_set_SHA=r.domain_digest.hexdigest(),
        K_per_scenario=10,scenario_active_constraints={s['label']:[dict(rho=x[0],line=x[1],phase=x[2],slot=x[3]) for x in s['active']] for s in r.scenario},
        timeshifting_active=True,restored_temporal_candidates=r.temporal_candidates,
        COMPOUND_NET_EFFECT_COMPUTED='YES',COMPOUND_NET_EFFECT_USED_IN_ORDERING='YES',
        compound_regression=tests,existing_compound_construction='Unchanged 2-/3-prefix anchor bundles only',
        new_candidates=0,removed_candidates=0,scenario_specific_candidates=0,new_ranking_solver_variables=0,new_ranking_solver_constraints=0,
        ranking_OpenDSS_calls=0,ranking_optimizer_calls=0,full_time_indexed_PCC_delta=True,
        hierarchy=['lower max_s max_top10 predicted rho','larger min_s critical-window relief','larger min_s power leverage','larger min_s differential relief','existing deterministic tie'],
        hierarchy_scope='Existing hierarchical 10000-candidate shortlist; all remaining full job domains retained in fallback',
        no_learned_or_tuned_weights=True,search_order_only=True,P2_CHANGED=False,P3_CHANGED=False,P4_CHANGED=False,P5_CHANGED=False,
        preparation_seconds=time.perf_counter()-started,initial_top20=[dict(job=u,option=k,p1=p,exposure=e,leverage=l,gamma=g) for u,k,p,e,l,g in ranked[:20]],source=c.record(__file__))
    c.save('V41R4_ROBUST_RANKING_AUDIT.json',audit)
    return r,audit
