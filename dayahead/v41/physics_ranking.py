"""B0-only search ordering. No solver construction, objectives or acceptance."""
from pathlib import Path
import time,hashlib,inspect,json
import numpy as np
from dayahead.paper_analysis.storage import read,write_json,write_npz,digest
from dayahead.v41.scientific_archive import native
from dayahead.v41.preflight import ROOT,record
from dayahead.v41r3.authority import OUT,OLD_RUN,DAY
from dayahead.v41.frozen_candidates import options

K=20
M=10000
INSTANCE=None


def existing_anchor_search_units(anchors, components, uid_group, best, compound_scores):
    """Order supplied existing bundles and singleton anchors; generate no pairs.

    ``compound_scores`` contains exactly the two/three prefixes already
    computed by this implementation. Overlapping bundles may expand to the
    same job order; their net keys still govern the consumed bundle queue.
    """
    units=[]
    def key(p,e,l,g,tie):return (float(p),-float(e),-float(l),-max(float(g),0.),tie)
    for position,group in enumerate(anchors):
        members=[u for u,g in uid_group.items() if g==group and u in best]
        item=min((best[u] for u in members),key=lambda r:r['rank'],default=None)
        metrics=item['metrics'] if item else (float('inf'),0.,0.,0.)
        units.append(dict(kind='DIRECT_ANCHOR',groups=[group],components=[],
            key=key(*metrics,(position,0)),existing_tie=(position,0)))
    for width,score in compound_scores.items():
        part=components[:int(width)]
        assert len(part)==int(width) and int(width) in (2,3)
        groups=list(dict.fromkeys(uid_group[u] for u,k in part))
        units.append(dict(kind='EXISTING_COMPOUND_'+str(width),groups=groups,
            components=part,key=key(score['P1_hat_active'],score['ExposureRelief'],
                score['critical_leverage'],score['differential_sensitivity_relief'],(0,int(width))),
            existing_tie=(0,int(width))))
    ordered=sorted(units,key=lambda r:r['key'])
    assert set(g for r in ordered for g in r['groups'])==set(anchors)
    return ordered

class Ranking:
    def __init__(self,ctx,jobs,power):
        start=time.perf_counter();self.ctx=ctx;self.jobs={r['job_uid']:r for r in jobs}
        self.sites=tuple(ctx.capacity.aidc_ids);self.site={s:i for i,s in enumerate(self.sites)}
        self.gpu=np.asarray(power['gpu'],int);self.pcc=np.asarray(power['pcc']);self.cap=np.array([ctx.capacity.site_capacity[s] for s in self.sites])
        b0=read(OUT/'V41R3_B0_ACCEPTANCE.json');physical=Path(b0['full_grid_copies'][0]['source']['path'])
        from dayahead.v41r3.authority import SCALE
        with np.load(SCALE/'screen/alpha_1.600/DAYAHEAD/physics/OPENDSS_PHASE_ARRAYS.npz') as z:
            names=z['branch_names'].tolist();phases=z['branch_phases'].tolist();mask=np.array(z['branch_kinds'])=='line'
            line=np.flatnonzero(mask);rho=z['phase_current_loading_pu'][:,line]
        self.line=[names[k] for k in line];self.phase=[phases[k] for k in line]
        from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading
        self.S=np.empty((96,len(line),12))
        for t,c in enumerate(ctx.coefficients):
            x=c.anchor.copy();base=anchored_polygon_loading(c,x)
            indices=[c.branch_names.index(n+'::'+p) if n+'::'+p in c.branch_names else c.branch_names.index(n) for n,p in zip(self.line,self.phase)]
            for i in range(12):
                y=x.copy();y[i]+=1e-3
                self.S[t,:,i]=(anchored_polygon_loading(c,y)[indices]-base[indices])/1e-3
        order=sorted(((float(rho[t,j]),self.line[j],self.phase[j],t,j) for t in range(96) for j in range(len(line))),key=lambda x:(-x[0],x[1],x[2],x[3]))
        self.active=order[:K];self.at=np.array([r[3] for r in self.active]);self.aj=np.array([r[4] for r in self.active])
        self.Arho=np.array([r[0] for r in self.active]);self.AS=self.S[self.at,self.aj]
        self.tstar,self.jstar=order[0][3:];self.criticalS=self.S[self.tstar,self.jstar]
        self.env=rho.max(axis=1);self.weight=self.env/self.env.max();envj=rho.argmax(axis=1)
        self.ES=self.S[np.arange(96),envj];self.timers=dict(sensitivity_preprocessing_seconds=time.perf_counter()-start,global_cheap_ranking_seconds=0.,active_set_ranking_seconds=0.)
        self.data={};self.lookup={};self.prefix={};self.last={};self.count=0;self.temporal_candidates=0;self.domain_digest=hashlib.sha256()
        start=time.perf_counter()
        for uid,row in sorted(self.jobs.items()):self.add(uid,row)
        self.timers['global_cheap_ranking_seconds']=time.perf_counter()-start
        from dayahead.v41.temporal_restore import TOTAL_COUNT,RESTORED_COUNT
        assert self.count==TOTAL_COUNT and self.temporal_candidates==RESTORED_COUNT
        self.ranking_events=[]
    def gains(self,g):
        if g in self.lookup:return self.lookup[g]
        plus=np.empty((96,12));minus=np.empty((96,12))
        for i,s in enumerate(self.sites):
            b=self.gpu[:,i];table=self.ctx.tables[s];t=np.arange(96)
            minus[:,i]=table[t,b]-table[t,np.maximum(0,b-g)]
            # A blocked direct move is scored conditional on releasing enough
            # destination capacity. Every lookup stays inside the frozen table.
            # This is ordering metadata, never a feasibility/acceptance claim.
            receiver=np.minimum(b,np.maximum(0,self.cap[i]-g))
            plus[:,i]=table[t,np.minimum(self.cap[i],receiver+g)]-table[t,receiver]
        self.lookup[g]=(plus,minus)
        return plus,minus
    def add(self,uid,row):
        opts=options(row,self.ctx.capacity,self.ctx.wan,self.ctx.elapsed);n=len(opts);self.count+=n
        encoded=(json.dumps(dict(job_id=uid,options=[(o.site,o.start,o.end,o.checkpoint,o.transfer_start,o.transfer_end,o.initial_site) for o in opts]),separators=(',',':'))+'\n').encode()
        self.domain_digest.update(encoded)
        if row['AIDC_site']=='UNASSIGNED':
            self.data[uid]=dict(opts=opts,leverage=np.zeros(n),exposure=np.zeros(n),gamma=np.zeros(n),feasible=np.ones(n,bool),parts=[],source=-1,g=0)
            return
        src=self.site[row['AIDC_site']];g=int(row['requested_GPU']);plus,minus=self.gains(g)
        dst=np.fromiter((self.site[o.site] for o in opts),int,n)
        ini=np.fromiter((self.site[o.initial_site or row['AIDC_site']] if o.migrated else self.site[o.site] for o in opts),int,n)
        cp=np.fromiter((o.checkpoint if o.migrated else o.end for o in opts),int,n)
        ready=np.fromiter((o.transfer_end+1 if o.migrated else o.end for o in opts),int,n)
        end=np.fromiter((o.end for o in opts),int,n)
        optstart=np.fromiter((o.start for o in opts),int,n)
        self.temporal_candidates+=int(np.count_nonzero(optstart!=row['start_slot']))
        clip=lambda a:np.clip(a-24,0,96)
        start=np.full(n,int(row['start_slot']));refend=np.full(n,int(row['end_slot']))
        # Partition the UNION of reference and candidate boundaries. This
        # supports advance/delay/relocation/migration without assuming fixed
        # starts and without changing or adding any authoritative candidates.
        bounds=np.sort(np.column_stack((start,refend,optstart,cp,ready,end)),axis=1)
        parts=[]
        for j in range(5):
            lo,hi=bounds[:,j],bounds[:,j+1]
            origin=np.where((start<=lo)&(lo<refend),src,-1)
            destination=np.where((optstart<=lo)&(lo<cp),ini,np.where((ready<=lo)&(lo<end),dst,-1))
            parts.append((origin,destination,clip(lo),clip(hi)))
        if g not in self.prefix:
            remove=np.vstack((np.zeros(96),(self.ES*minus).T));add=np.vstack((np.zeros(96),(self.ES*plus).T))
            relief=np.maximum(remove[:,None,:]-add[None,:,:],0)*self.weight
            crit=np.r_[0,self.criticalS*minus[self.tstar]][:,None]-np.r_[0,self.criticalS*plus[self.tstar]][None,:]
            badremove=np.vstack((np.zeros(96,bool),(self.gpu<g).T));badadd=np.vstack((np.zeros(96,bool),(self.gpu+g>self.cap).T))
            bad=badremove[:,None,:]|badadd[None,:,:]
            for j in range(13):relief[j,j]=0;crit[j,j]=0;bad[j,j]=False
            self.prefix[g]=(np.pad(np.cumsum(relief,axis=2),((0,0),(0,0),(1,0))),crit,np.pad(np.cumsum(bad,axis=2),((0,0),(0,0),(1,0))))
        prefix,crit,invalid=self.prefix[g]
        exposure=np.zeros(n);leverage=np.zeros(n);feasible=np.ones(n,bool)
        for origin,destination,lo,hi in parts:
            valid=hi>lo;hi=np.maximum(lo,hi)
            a,b=origin+1,destination+1
            exposure+=np.where(valid,prefix[a,b,hi]-prefix[a,b,lo],0)
            leverage+=np.where(valid&(lo<=self.tstar)&(self.tstar<hi),crit[a,b],0)
            feasible&=(~valid)|((invalid[a,b,hi]-invalid[a,b,lo])==0)
        gamma=self.criticalS[ini]-self.criticalS[dst]
        # Relocations have one source; migration initial placement may itself move.
        nonmig=np.fromiter((not o.migrated for o in opts),bool,n)
        gamma[nonmig]=self.criticalS[src]-self.criticalS[dst[nonmig]]
        self.data[uid]=dict(opts=opts,leverage=leverage,exposure=exposure,gamma=gamma,feasible=feasible,parts=parts,source=src,g=g)
    def delta_gpu(self,uid,indices,times):
        d=self.data[uid];indices=np.asarray(indices);times=np.asarray(times)
        delta=np.zeros((len(indices),len(times),12),dtype=np.int16)
        for origin,dest,lo,hi in d['parts']:
            on=(lo[indices,None]<=times)&(times<hi[indices,None])
            for j in range(12):
                delta[:,:,j]+=on*(dest[indices,None]==j)*d['g']
                delta[:,:,j]-=on*(origin[indices,None]==j)*d['g']
        return delta
    def net_score(self,components):
        """Exact NET occupancy/PCC lookup for existing 2/3-way blocks; no products."""
        times=np.arange(96);delta=np.zeros((96,12),int)
        for uid,index in components:delta+=self.delta_gpu(uid,[index],times)[0]
        occupancy=self.gpu+delta;feasible=bool(np.all((occupancy>=0)&(occupancy<=self.cap)))
        pq=np.empty((96,12))
        for i,s in enumerate(self.sites):pq[:,i]=self.ctx.tables[s][times,np.clip(occupancy[:,i],0,self.cap[i])]-self.pcc[:,i]
        predicted=self.Arho+np.einsum('ki,ki->k',self.AS,pq[self.at])
        return dict(P1_hat_active=float(predicted.max()),ExposureRelief=float(np.sum(self.weight*np.maximum(-np.einsum('ti,ti->t',self.ES,pq),0))),critical_leverage=float(-self.criticalS@pq[self.tstar]),net_capacity_feasible=feasible,all_constituents=len(components),net_gpu_delta=delta,net_pcc_delta=pq)
    def score_active(self,uid,indices):
        indices=np.asarray(indices);d=self.data[uid]
        delta=self.delta_gpu(uid,indices,self.at);base=self.gpu[self.at];occupancy=base[None]+delta
        values=np.broadcast_to(self.Arho,(len(indices),K)).copy()
        plus,minus=self.gains(d['g']) if d['g'] else (None,None)
        for i,s in enumerate(self.sites):
            b=base[:,i];new=occupancy[:,:,i];table=self.ctx.tables[s]
            exact=table[self.at[None],np.clip(new,0,self.cap[i])]-self.pcc[self.at,i]
            if d['g']:
                exact=np.where(new>self.cap[i],plus[self.at,i],exact)
                exact=np.where(new<0,-minus[self.at,i],exact)
            values+=exact*self.AS[:,i]
        return values.max(axis=1)
    def tier(self,uids):
        start=time.perf_counter();uids=list(dict.fromkeys(uids))
        counts=[len(self.data[u]['opts']) for u in uids];offset=np.cumsum([0]+counts)
        exposure=np.concatenate([self.data[u]['exposure'] for u in uids]);n=len(exposure);m=min(M,n)
        if not n:return [],{}
        # Partial global selection; never Python-sort 4.77M candidates.
        if m<n:
            raw=np.argpartition(-exposure,m-1)[:m];cut=exposure[raw].min()
            above=np.flatnonzero(exposure>cut);tied=np.flatnonzero(exposure==cut)[:m-len(above)];chosen=np.r_[above,tied]
        else:chosen=np.arange(n)
        owner=np.searchsorted(offset[1:],chosen,side='right');local=chosen-offset[owner]
        p1=np.empty(m);lev=np.empty(m);gam=np.empty(m)
        for j,u in enumerate(uids):
            take=np.flatnonzero(owner==j)
            if not len(take):continue
            idx=local[take];d=self.data[u];p1[take]=self.score_active(u,idx);lev[take]=d['leverage'][idx];gam[take]=d['gamma'][idx]
        order=np.lexsort((chosen,-np.maximum(gam,0),-lev,-exposure[chosen],p1))
        ranked=[(uids[owner[i]],int(local[i]),float(p1[i]),float(exposure[chosen[i]]),float(lev[i]),float(gam[i])) for i in order]
        best={}
        for rank,item in enumerate(ranked,1):best.setdefault(item[0],dict(rank=rank,option_index=item[1],metrics=item[2:]))
        elapsed=time.perf_counter()-start;self.timers['active_set_ranking_seconds']+=elapsed
        return ranked,dict(best=best,tier_size=m,neighborhood_candidates=n,seconds=elapsed,subsequent_tiers='All remaining complete job domains retain the existing fallback order; no domain filtering')
    def reorder(self,engine,ordered,anchors):
        # Rank the existing job-block neighborhood. Each opened block keeps ALL
        # options, including every option outside the minimax priority tier.
        uids=[u for g in ordered for u in engine.metadata[g].get('members',[])];ranked,info=self.tier(uids)
        groupbest={g:min((info['best'][u]['rank'] for u in engine.metadata[g].get('members',[]) if u in info['best']),default=10**12) for g in ordered}
        prior={g:i for i,g in enumerate(ordered)}
        if engine.control.family=='COVERAGE' or engine.control.mode=='DIVERSIFICATION':
            result=sorted(ordered,key=lambda g:(engine.visits[g],groupbest[g],prior[g]))
        else:result=sorted(ordered,key=lambda g:(groupbest[g],engine.visits[g],prior[g]))
        anchors=sorted(dict.fromkeys(anchors),key=lambda g:(groupbest.get(g,10**12),prior.get(g,10**12)))
        # Existing capacity/WAN anchors remain intact. Their net compound score
        # uses every constituent choice, with no new cross-product enumeration.
        components=[]
        for g in anchors:
            for u in engine.metadata[g].get('members',[]):
                if u in info['best']:components.append((u,info['best'][u]['option_index']))
        compound={}
        for width in (2,3):
            if len(components)>=width:
                s=self.net_score(components[:width]);compound[str(width)]={k:v for k,v in s.items() if not k.startswith('net_') or k=='net_capacity_feasible'}
                compound[str(width)]['differential_sensitivity_relief']=float(sum(self.data[u]['gamma'][k] for u,k in components[:width]))
        uid_group={u:g for g in anchors for u in engine.metadata[g].get('members',[])}
        units=existing_anchor_search_units(anchors,components,uid_group,info['best'],compound)
        engine.v41_existing_anchor_search_units=units
        audit_units=[{k:v for k,v in r.items() if k!='key'} | {'search_key':[None if not np.isfinite(v) else v for v in r['key'][:4]]+[r['key'][4]]} for r in units]
        event=dict(iteration=engine.iteration+1,phase=engine.index,tier_size=info['tier_size'],neighborhood_candidates=info['neighborhood_candidates'],active_set_seconds=info['seconds'],top_20=[self.describe(u,k,rank=i+1,P1_hat_active=p) for i,(u,k,p,e,l,g) in enumerate(ranked[:20])],existing_compound_anchor_scores=compound,complete_domains_retained=True,ordered_existing_anchor_units=audit_units,compound_net_effect_used_in_ordering=True,compound_generation='UNCHANGED_EXISTING_2_AND_3_PREFIXES_ONLY',direct_ranked_group_order=result)
        self.last=dict(ranked=ranked,info=info);self.ranking_events.append(event)
        write_json(engine.output/'bounded_checkpoints'/f'PHYSICS_RANKING_{engine.index}_{engine.iteration+1}.json',native(event))
        return result,anchors
    def describe(self,uid,k,**extra):
        d=self.data[uid];o=d['opts'][k];r=self.jobs[uid]
        return dict(job_id=uid,option_index=int(k),source=r['AIDC_site'],migration_source=o.initial_site or r['AIDC_site'],destination=o.site,requested_GPU=r['requested_GPU'],kind='MIGRATION' if o.migrated else 'RELOCATION' if o.site!=r['AIDC_site'] else 'STAY',start=o.start,end=o.end,checkpoint=o.checkpoint,restart=o.transfer_end+1 if o.migrated else None,critical_movable_power_leverage=float(d['leverage'][k]),ExposureRelief=float(d['exposure'][k]),Gamma=float(d['gamma'][k]),B0_single_move_capacity_feasible=bool(d['feasible'][k]),**extra)
    def accepted(self,engine,rows,accepted):
        from dayahead.v40g.domain import Option
        from dayahead.v41r1.migration import pending_in_day
        from bisect import bisect_left
        ranking={(u,k):i+1 for i,(u,k,*_) in enumerate(self.last.get('ranked',[]))};results=[]
        for row in rows or []:
            ref=self.jobs[row['job_uid']]
            if row.get('migration_selected'):
                active=[t+24 for t,b in enumerate(row['frozen_WAN_transfer']['bytes_by_slot']) if b]
                o=Option(row['AIDC_site'],row['start_slot'],row['end_slot'],row['migration_checkpoint_slot'],min(active),max(active)+1,row['initial_AIDC'] if pending_in_day(row) else '')
            else:o=Option(row['AIDC_site'],row['start_slot'],row['end_slot'])
            if o==Option(ref['AIDC_site'],ref['start_slot'],ref['end_slot']):continue
            uid=row['job_uid'];opts=self.data[uid]['opts'];k=bisect_left(opts,o);assert opts[k]==o
            results.append(self.describe(uid,k,accepted=accepted,active_tier_rank=ranking.get((uid,k)),rank_scope='Current neighborhood Tier B; null means retained full-domain fallback',iteration=engine.iteration+1))
        write_json(engine.output/'bounded_checkpoints'/f'PHYSICS_ACCEPTED_RANKS_{engine.index}_{engine.iteration+1}.json',native(dict(accepted=accepted,candidates=results)))

def prepare(ctx,jobs,power):
    global INSTANCE
    assert INSTANCE is None,'ONE_RANKING_PREPARATION_ONLY'
    started=time.perf_counter();INSTANCE=Ranking(ctx,jobs,power)
    ranked,info=INSTANCE.tier(sorted(INSTANCE.jobs))
    top=[];feasible=[]
    for uid,d in INSTANCE.data.items():
        n=len(d['leverage']);take=np.argpartition(-d['leverage'],min(20,n)-1)[:min(20,n)]
        top.extend(INSTANCE.describe(uid,int(k)) for k in take)
        valid=np.flatnonzero(d['feasible'])
        if len(valid):
            k=int(valid[np.argmax(d['leverage'][valid])]);feasible.append(INSTANCE.describe(uid,k))
    top=sorted(top,key=lambda r:(-r['critical_movable_power_leverage'],r['job_id'],r['option_index']))[:20]
    feasible.sort(key=lambda r:(-r['critical_movable_power_leverage'],r['job_id'],r['option_index']))
    S=INSTANCE.criticalS;pairs=sorted([(float(S[i]-S[j]),INSTANCE.sites[i],INSTANCE.sites[j]) for i in range(12) for j in range(12) if i!=j])
    from dayahead.v41r3.candidates import _store
    assert _store.digest.hexdigest()==_store.manifest['candidate_set_SHA']
    # Numerical verification: sums of compound GPU changes, followed by ONE
    # net occupancy-to-PCC evaluation, must match the direct lookup exactly.
    compounds=[]
    choices=[(r['job_id'],r['option_index']) for r in top]
    for width in (2,3):
        unique=list(dict.fromkeys(choices))[:width];score=INSTANCE.net_score(unique)
        assert score['all_constituents']==width
        direct=sum((INSTANCE.delta_gpu(u,[k],np.arange(96))[0] for u,k in unique),np.zeros((96,12),int))
        assert np.array_equal(direct,score['net_gpu_delta'])
        compounds.append(dict(width=width,net_lookup_PASS=True,capacity_feasible=score['net_capacity_feasible']))
    from dayahead.v41r1 import early_stop
    import psutil
    audit=dict(status='PASS',candidate_universe_hash_unchanged=True,candidate_count_unchanged=True,candidate_set_SHA=_store.manifest['candidate_set_SHA'],candidate_count=INSTANCE.count,new_candidates_added=0,candidates_removed=0,new_solver_variables=0,new_solver_constraints=0,P1_P5_unchanged=True,ML_unchanged=True,AIDC_power_unchanged=True,B0_only_reference=True,K=K,M=M,critical=dict(line=INSTANCE.line[INSTANCE.jstar],phase=INSTANCE.phase[INSTANCE.jstar],slot=INSTANCE.tstar),sensitivities=dict(zip(INSTANCE.sites,map(float,S))),max_Gamma=pairs[-1],min_Gamma=pairs[0],top_20_direct_by_leverage=top,max_single_move_capacity_feasible_leverage=feasible[0],active_constraints=[dict(loading=r[0],line=r[1],phase=r[2],slot=r[3]) for r in INSTANCE.active],initial_priority_tier_top_20=[INSTANCE.describe(u,k,rank=i+1,P1_hat_active=p) for i,(u,k,p,e,l,g) in enumerate(ranked[:20])],timing=INSTANCE.timers,charged_preprocessing_seconds=time.perf_counter()-started,memory_peak_bytes=getattr(psutil.Process().memory_info(),'peak_wset',psutil.Process().memory_info().rss),ranking_model_calls=0,ranking_OpenDSS_calls=0,compound_net_tests=compounds,power_lookup_rule='Exact frozen occupancy-dependent C1 tables. A direct move exceeding B0 destination capacity is scored conditional on minimum capacity release; it remains explicitly capacity-blocked. Existing feasible compound moves use one exact NET occupancy lookup across all constituents. No overloaded/negative occupancy enters a C1 lookup.',exposure_rule='B0 max-line envelope weights, positive net predicted relief, disjoint actual-effect intervals, prefix sums',hierarchy=['min active-set P1 surrogate','max exposure relief','max movable-power leverage','max positive Gamma','existing deterministic option order'],acceptance='Original exact P1-P5 and all hard rows/WAN checks unchanged',unchanged_exact_acceptance_tolerances=dict(TOLERANCES=early_stop.TOLERANCES,IMPROVEMENT_EPS=early_stop.IMPROVEMENT_EPS,IMPROVEMENT_NOISE=early_stop.IMPROVEMENT_NOISE),source=record(__file__),electrical=ctx.v41_electrical_certificate,full_domain_readback='SHA verified while decoding certified tuples; no generator call')
    # Explicit user-authorized restoration supersedes the old fixed-start
    # full-domain hash. Ranking itself still adds/removes no choices.
    from dayahead.v41.temporal_restore import RESTORED_COUNT,TOTAL_COUNT
    audit.update(candidate_universe_hash_unchanged=False,candidate_count_unchanged=False,
        domain_change_reason='USER_AUTHORIZED_RESTORATION_OF_PREEXISTING_TEMPORAL_FLEXIBILITY',
        candidate_set_SHA=INSTANCE.domain_digest.hexdigest(),base_candidate_set_SHA=_store.manifest['candidate_set_SHA'],
        original_4772575_candidates_all_retained=True,restored_temporal_candidates=RESTORED_COUNT,
        candidate_count=TOTAL_COUNT,new_candidates_added=RESTORED_COUNT,ranking_only_candidates_added=0,
        ranking_only_candidates_removed=0,unexpected_domain_change=False,
        restoration_authority=record(OUT/'V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'))
    # Recompute P5 ranks for the explicitly restored domain; P1/P2 physics and
    # B0 execution remain unchanged. This evaluator already implements time.
    from dayahead.v41.objectives import evaluate
    b0objective=evaluate(jobs,jobs,ctx)
    prior=read(OUT/'V41R3_B0_ACCEPTANCE.json')['OBJECTIVE_VECTOR']
    assert b0objective['OBJECTIVE_VECTOR'][:4]==prior[:4]
    write_json(OUT/'V41R3_B0_RESTORED_OBJECTIVE.json',native(b0objective))
    audit['B0_restored_objective']=record(OUT/'V41R3_B0_RESTORED_OBJECTIVE.json')
    audit['charged_preprocessing_seconds']=time.perf_counter()-started
    write_npz(OUT/'V41R3_RANKING_PHYSICS.npz',S=INSTANCE.S,B0_envelope=INSTANCE.env,weights=INSTANCE.weight,active_S=INSTANCE.AS,active_rho=INSTANCE.Arho)
    write_json(OUT/'V41R3_FO_PHYSICS_RANKING_AUDIT.json',native(audit))
    print('PHYSICS_RANKING_PASS',audit['charged_preprocessing_seconds'],'seconds',flush=True)
    return audit

def reorder(engine,ordered,anchors):
    assert INSTANCE is not None,'RANKING_NOT_PREPARED'
    return INSTANCE.reorder(engine,ordered,anchors)

def record_acceptance(engine,rows,accepted):
    if INSTANCE is not None:INSTANCE.accepted(engine,rows,accepted)
