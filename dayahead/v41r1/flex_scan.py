"""Deterministic exhaustive single-job scan, with explicit scope of counts."""
from collections import Counter
import time
import numpy as np
from dayahead.paper_analysis.storage import write_json, read
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT, WORK, A0
from .flex_model import Data, ProbeModel
from .migration import state_at_d00, pending_in_day


def scan():
    d=Data();started=time.perf_counter()
    try:
        # Every frozen logical rack pool can hold the entire site's capacity.
        # Site occupancy therefore bounds every individual rack occupancy;
        # destination materialization still selects an eligible rack label.
        rackproof={s:[(p.rack_pool_id,p.historical_gpu_capacity) for p in d.ctx.capacity.rack_pools if p.aidc_id==s] for s in d.sites}
        assert all(v and all(int(cap)>=d.ctx.capacity.site_capacity[s] for _,cap in v) for s,v in rackproof.items())
        reasons=Counter();rows=[];feasible=[];best={};by_job={};negative=zero=positive=0
        nominal=read(A0/'V41R1_FULL_CANDIDATE_MANIFEST.json')
        def update(name,item):
            if name not in best or tuple(item['vector'])<tuple(best[name]['vector']):best[name]=item
        for index,uid in enumerate(sorted(d.opts)):
            a=d.opts[uid];r=d.byuid[uid];ref=d.reference_index[uid]
            migrate=a[:,3]>=0
            take=(~migrate)|(a[:,4]==np.maximum(26,a[:,3]))
            reasons['UID_SERIAL_WAN_CLOCK_WITH_OTHERS_B0']+=int((~take).sum())
            valid=np.flatnonzero(take);valid=valid[valid!=ref]
            counts=Counter();arcs=set();initial_sites=set()
            for k in valid:
                k=int(k);q,reason=d.quick({uid:k})
                reasons[reason]+=1
                if q is None:continue
                o=d.option(uid,k)
                kind='PENDING_PRESTART_ONLY' if not o.migrated else ('D00_RUNNING_MIGRATION' if state_at_d00(r)=='RUNNING' else 'PENDING_BECOMES_RUNNING_MIGRATION')
                initial=o.initial_site or (r['AIDC_site'] if o.migrated else o.site)
                item=dict(uid=uid,option_index=k,kind=kind,initial=initial,destination=o.site,
                    vector=q['vector'],delta_P1=q['vector'][0]-d.base[0],delta_P2=q['vector'][1]-d.base[1])
                feasible.append(item);counts[kind]+=1
                arcs.add((initial,o.site))
                if not o.migrated and o.site!=r['AIDC_site']:initial_sites.add(o.site)
                update('ALL',item);update(kind,item)
                if q['vector'][0]<=d.base[0]+1e-10:
                    if 'P2_NO_WORSE_P1' not in best or q['vector'][1]<best['P2_NO_WORSE_P1']['vector'][1]:best['P2_NO_WORSE_P1']=item
                if abs(item['delta_P1'])<=1e-10:zero+=1
                elif item['delta_P1']<0:negative+=1
                else:positive+=1
            by_job[uid]=dict(D00_state=state_at_d00(r),state_at_issue=r['state_at_issue'],
                nominal_options=len(a),feasible_single_job_alternatives=sum(counts.values()),
                kinds=dict(counts),alternative_initial_sites=sorted(initial_sites),
                feasible_destination_arcs=[list(p) for p in sorted(arcs)])
            if index%100==0:
                print('SINGLE_SCAN',index,len(d.opts),'feasible',len(feasible),'best',best.get('ALL',{}).get('delta_P1'),'seconds',round(time.perf_counter()-started,1),flush=True)
        result=dict(status='PASS',seconds=time.perf_counter()-started,B0=d.base,
            full_candidate_count=nominal['final_authoritative_candidates'],
            scan_scope='ALL_ORIGINAL_OPTIONS_WITH_EXACTLY_ONE_JOB_CHANGED; OTHER_JOBS_AT_B0; ORIGINAL_UID_SERIAL_WAN',
            global_multi_job_alternative_count_not_claimed=True,
            feasible_single_job_alternative_count=len(feasible),
            PENDING_jobs_with_alternative_initial_site=sum(bool(v['alternative_initial_sites']) for v in by_job.values()),
            D00_RUNNING_jobs_with_feasible_migration=sum(v['kinds'].get('D00_RUNNING_MIGRATION',0)>0 for v in by_job.values()),
            PENDING_jobs_with_feasible_checkpoint_migration=sum(v['kinds'].get('PENDING_BECOMES_RUNNING_MIGRATION',0)>0 for v in by_job.values()),
            feasible_single_job_destination_arcs=sum(len(v['feasible_destination_arcs']) for v in by_job.values()),
            rejection_reasons=dict(reasons),negative_P1=negative,zero_P1=zero,positive_P1=positive,
            best=best,job_counts=by_job,rack_site_equivalence=rackproof,
            no_candidate_pruning=True,Actual_reads=0)
        write_json(OUT/'B1_EFFECTIVE_ALTERNATIVE_SET.json',result)
        write_json(WORK/'FEASIBLE_SINGLE_MOVES.json',feasible)
        write_json(OUT/'SINGLE_MOVE_SCAN.json',dict(**{k:v for k,v in result.items() if k!='job_counts'},
            full_feasible_move_list=record(WORK/'FEASIBLE_SINGLE_MOVES.json')))
        print('SINGLE_SCAN_FINISHED',len(feasible),'best',best,flush=True)
    finally:d.close()


if __name__=='__main__':scan()
