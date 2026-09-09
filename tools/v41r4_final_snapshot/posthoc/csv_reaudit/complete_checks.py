"""Additional independent CSV, migration event and post-hoc checks."""
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import numpy as np
from reaudit import Archive,Comparisons,HERE,OUT,RUN,REV,NA,load_csvs,save,span


def ranks(values):
    return np.array([sum(v<x for v in values)+(sum(v==x for v in values)+1)/2 for x in values])


def correlation(a,b):
    if np.ptp(a)==0 or np.ptp(b)==0:return dict(Pearson=NA,Spearman=NA,N=len(a))
    return dict(Pearson=float(np.corrcoef(a,b)[0,1]),Spearman=float(np.corrcoef(ranks(a),ranks(b))[0,1]),N=len(a))


def statistics(values):
    a=np.asarray(values,dtype=float)
    return dict(N=len(a),sum=float(a.sum()),mean=float(a.mean()),median=float(np.median(a)),P90=float(np.quantile(a,.9)),min=float(a.min()),max=float(a.max()))


def main():
    archive=Archive();tables,_=load_csvs();check=Comparisons()
    units=json.loads((HERE/'terminal_units.json').read_text());u={(x['day'],x['policy']):x for x in units}
    sources=json.loads((HERE/'source_map.json').read_text());source_map={(x['day'],x['policy']):x for x in sources}
    records=json.loads((HERE/'terminal_records.json').read_text())
    byunit={key:[r for r in records if (r['day'],r['policy'])==key] for key in u}
    runtime=[];h4=[];routes={};missing=0;boundaries=[];planning_service={};all_deltas=[]
    for source in sources:
        day,policy=source['day'],source['policy'];key=(day,policy)
        jobs=archive.j(source['joint'])['decision']['AIDC_decision'];byid={str(j['job_uid']):j for j in jobs}
        power=archive.z(source['da']+'/FROZEN_AIDC_POWER.npz')
        sites=sorted({part['site'] for j in jobs for part in j['compute_segments'] if part['site']!='UNASSIGNED'})
        reconstructed=np.zeros((96,12),dtype=int)
        for j in jobs:
            for segment in j['compute_segments']:
                if segment['site']=='UNASSIGNED':continue
                site=int(segment['site'].removeprefix('AIDC'))-1
                a=max(24,int(segment['start']));b=min(120,int(segment['end']))
                if b>a:reconstructed[a-24:b-24,site]+=int(j['requested_GPU'])
        assert np.array_equal(power['gpu'],reconstructed),key
        planning_service[key]=float(reconstructed.sum()/4)
        u[key]['total_D_day_scheduled_GPUh']=planning_service[key]
        u[key]['observed_total_DA_IT_kWh']=float(power['it'].sum()/4)
        u[key]['observed_total_DA_PCC_kWh']=float(power['pcc'].sum()/4)
        u[key]['flagged_D_day_IT_energy_reduction_kWh']=NA
        if policy in ('B1','B3'):
            boundary_path=source['da']+('/A0/' if policy=='B1' else '/A1/')+'DAY_BOUNDARY_AUDIT.json'
            boundary=archive.j(boundary_path)
            assert boundary['status']=='PASS' and boundary['issue_begin']==24 and boundary['issue_end_exclusive']==120
            assert boundary['terminal_residual_constraint_active'] is False and boundary['service_neutrality_constraint_active'] is False
            boundaries.append(dict(day=day,policy=policy,path=boundary_path,sha256=archive.index[boundary_path]['sha256'],**boundary))
        for record in byunit[key]:
            job=byid[record['job_uid']];events=job['migration_events'];assert len(events)==1
            event=events[0];assert event['slot_origin']=='D_MINUS_1_ISSUE'
            for target,field in [('migration_checkpoint_slot','checkpoint'),('transfer_start_slot','transfer_start'),('transfer_end_slot','transfer_end'),('restart_complete_slot','restart_end')]:record[target]=event[field]
            cp,ts,te,re=[event[k] for k in ('checkpoint','transfer_start','transfer_end','restart_end')]
            assert 24<=cp<=ts<te<re<120 and re==te+1
            parts=job['compute_segments'];assert len(parts)==2 and parts[0]['end']==cp and parts[1]['start']==re
            record.update(checkpoint_to_transfer_wait_slots=ts-cp,WAN_transfer_slots=te-ts,restart_slots=re-te,
                interruption_slots=re-cp,wallclock_end_delay_slots=record['optimized_end']-record['reference_end'],
                slot_origin='D_MINUS_1_ISSUE',D_day_begin_issue_slot=24,D_day_end_exclusive_issue_slot=120,
                classification='PAPER_EXPORT_ADDITIONAL_INVARIANT_NOT_PART_OF_FROZEN_METHOD',
                scientific_interpretation='CONSERVED_TOTAL_SERVICE_WITH_REAL_D_DAY_TO_POST_DAY_DEFERRAL',
                D_day_IT_energy_reduction_kWh=NA)
            assert record['reference_total_compute_service_slots']==record['optimized_total_compute_service_slots']
            assert record['wallclock_end_delay_slots']==re-cp
            assert record['delta_post_day_GPUh']==record['D_day_service_reduction_GPUh']
        if policy=='B0':
            ml=archive.j(source['da']+'/ml/ML_SNAPSHOT.json');score=archive.j(source['ci']+'/H4_SCORE.json')
            replay=archive.j(source['ci']+'/ACTUAL_JOB_REPLAY.json');labels={str(j['job_uid']):j for j in replay['job_ledger']}
            for uid,pred in ml['PENDING_JOB_Q90_SECONDS'].items():
                label=labels.get(str(uid),{});y=label.get('actual_runtime_seconds')
                if label.get('state_at_issue')=='PENDING' and isinstance(y,(int,float)) and math.isfinite(y) and y>0 and label.get('actual_runtime_source')=='KESTREL_OBSERVED_END_MINUS_START':
                    runtime.append((pred,y,ml['PENDING_JOB_DURATION_SLOTS'][uid]*900))
                else:missing+=1
            p=np.array(ml['H4_RAW_R85_B2_GPUh']);c=np.array(ml['H4_ACTIONABLE_RESERVE_GPUh']);y=np.array(score['realized_H4_GPUh'])
            h4.extend(zip(p,c,y,p>ml['H4_CAP_HIST'],np.minimum(p,ml['H4_CAP_HIST'])>np.array(ml['H4_CAP_PHYS'])))
        if policy in ('B2','B3'):
            mess=archive.j(source['ci']+'/ACTUAL_MESS_AUDIT.json')
            joint=archive.j(source['joint'])['decision'];commands={(r['mess_id'],r['slot']):r for r in joint['MESS_trajectory']}
            for move in mess['moves']:
                c=commands.get((move['mess_id'],move['departure_slot']))
                if c and 'route_q50_eta_sec' in c and 'route_safe_eta_sec' in c:
                    routes[(day,move['departure_slot'],move.get('route_SHA'),move['actual_eta_seconds'])]=(c['route_q50_eta_sec'],c['route_safe_eta_sec'],move['actual_eta_seconds'])
    metrics={}
    p,y,reservation=np.array(runtime).T;err=y-p
    metrics.update(runtime_Q90_empirical_coverage=np.mean(y<=p),runtime_reservation_15min_coverage=np.mean(y<=reservation),runtime_pinball_loss_Q90=np.mean(np.where(err>=0,.9*err,-.1*err)),
        runtime_MAE_s=np.mean(abs(err)),runtime_median_AE_s=np.median(abs(err)),runtime_underprediction_rate=np.mean(err>0),runtime_mean_underprediction_s=np.mean(err[err>0]),runtime_unmatched_or_unavailable_label_count=missing)
    p,c,y,hist,phys=np.array(h4).T;short=np.maximum(y-c,0)
    metrics.update(H4_raw_coverage=np.mean(y<=p),H4_actionable_capped_coverage=np.mean(y<=c),H4_MAE_GPUh=np.mean(abs(y-p)),H4_mean_shortfall_GPUh=np.mean(short),H4_P90_shortfall_GPUh=np.quantile(short,.9),H4_historical_cap_activation_count=hist.sum(),H4_physical_cap_activation_count=phys.sum())
    p,safe,y=np.array(list(routes.values())).T
    metrics.update(route_ETA_MAE_s=np.mean(abs(y-p)),SafeETA_coverage=np.mean(y<=safe),SafeETA_mean_margin_s=np.mean(safe-y))
    for row in tables['07']:
        metric=row['metric']
        if metric in metrics:
            n=len(runtime)+(missing if metric=='runtime_unmatched_or_unavailable_label_count' else 0) if row['domain']=='runtime' else len(h4) if row['domain']=='H4' else len(routes)
            check.fields('07',(row['domain'],metric),row,dict(value=metrics[metric],N=n))
        else:assert row['value']==row['N']==NA
    for row in tables['08']:
        policy=row['policy'];sub=[x for x in units if x['policy']==policy];assert len(sub)==31
        check.cell('08',(policy,),row,'N_days',31)
        for prefix in ('P1','DA_rho','Actual_rho'):
            st=statistics([x[prefix] for x in sub])
            for name in ('mean','median','P90','min','max'):check.cell('08',(policy,),row,prefix+'_'+name,st[name])
        for field,name in [('temporal_shift_total','temporal_shift_count'),('spatial_relocation_total','spatial_relocation_count'),('checkpoint_migration_total','total_migrations'),('MESS_dispatch_slots_total','MESS_dispatch_slots'),('MESS_moves_total','MESS_move_count'),('MESS_abs_P_energy_kWh_total','MESS_abs_P_energy_kWh'),('terminal_residual_violation_jobs','affected_jobs')]:check.cell('08',(policy,),row,field,sum(x[name] for x in sub))
        check.cell('08',(policy,),row,'Actual_H4_shortfall_mean_GPUh',np.mean([x['Actual_H4_shortfall_mean_GPUh'] for x in sub]))
    for row in tables['09']:
        day=row['day']
        for measure in ('P1','DA_rho','Actual_rho'):
            for policy in ('B0','B1','B2','B3'):check.cell('09',(day,),row,policy+'_'+measure,u[day,policy][measure])
            for policy,base in [('B1','B0'),('B2','B0'),('B3','B0'),('B3','B2')]:
                a,b=u[day,policy][measure],u[day,base][measure]
                check.cell('09',(day,),row,f'{policy}_minus_{base}_{measure}',a-b)
                field=f'{policy}_'+('incremental_' if base=='B2' else '')+f'improvement_pct_vs_{base}'+('' if measure=='P1' else '_'+measure)
                check.cell('09',(day,),row,field,(b-a)/b*100 if b else math.nan)
    results={}
    for policy in ('B1','B3'):
        rows=[x for x in units if x['policy']==policy]
        values=[x['affected_GPUh'] for x in rows]
        selected=sum(x['total_selected_jobs'] for x in rows);migrations=sum(x['total_migrations'] for x in rows);affected=sum(x['affected_jobs'] for x in rows)
        stats=dict(all_31_days=statistics(values),affected_30_days=statistics([v for v in values if v>0]),affected_jobs=affected,total_selected_jobs=selected,total_migrations=migrations,
                   affected_selected_fraction=affected/selected,affected_migrated_fraction=affected/migrations,
                   extra_fraction_of_B0_scheduled_D_day_GPUh=sum(values)/sum(planning_service[x['day'],'B0'] for x in rows),
                   correlations={},affected_vs_unaffected={})
        for measure in ('P1','DA_rho','Actual_rho'):
            absolute=[u[x['day'],'B0'][measure]-x[measure] for x in rows]
            percent=[100*a/u[x['day'],'B0'][measure] for a,x in zip(absolute,rows)]
            stats['correlations'][measure+'_absolute_improvement']=correlation(values,absolute)
            stats['correlations'][measure+'_percent_improvement']=correlation(values,percent)
            for label,flag in [('affected',True),('unaffected',False)]:
                group=[i for i,x in enumerate(rows) if bool(x['affected_jobs'])==flag]
                stats['affected_vs_unaffected'][measure+'_'+label]=dict(N=len(group),mean_absolute_improvement=float(np.mean([absolute[i] for i in group])),mean_percent_improvement=float(np.mean([percent[i] for i in group])),days=[rows[i]['day'] for i in group])
        for x in rows:
            ref=u[x['day'],'B0']
            for p in ('B0','B1','B3'):
                for field in ('P1','DA_rho','Actual_rho'):x[p+'_'+field]=u[x['day'],p][field]
            x['B0_scheduled_D_day_GPUh']=ref['total_D_day_scheduled_GPUh']
            x['extra_fraction_of_B0_GPUh']=x['affected_GPUh']/ref['total_D_day_scheduled_GPUh']
            x['observed_B0_minus_policy_IT_kWh']=ref['observed_total_DA_IT_kWh']-x['observed_total_DA_IT_kWh']
            x['observed_B0_minus_policy_GPUh']=ref['total_D_day_scheduled_GPUh']-x['total_D_day_scheduled_GPUh']
            x['P1_improvement_abs']=ref['P1']-x['P1']
            x['P1_improvement_pct']=100*(ref['P1']-x['P1'])/ref['P1']
        stats['observed_total_B0_minus_policy_IT_kWh']=sum(x['observed_B0_minus_policy_IT_kWh'] for x in rows)
        stats['maximum_fraction_of_B0_D_day_GPUh']=max(x['extra_fraction_of_B0_GPUh'] for x in rows)
        results[policy]=stats
    save('terminal_records.json',records);save('terminal_units.json',units);save('posthoc_statistics.json',results)
    save('final_model_boundaries.json',boundaries)
    save('additional_crosscheck.json',dict(cells_compared=check.count,by_table=dict(check.by_table),errors=check.errors,max_absolute_float_error=check.max_float_error,ML_runtime_N=len(runtime),ML_H4_N=len(h4),ML_route_N=len(routes)))
    save('additional_sources_used.json',archive.used)
    print(json.dumps(dict(errors=len(check.errors),comparisons=check.count,B1=results['B1']['all_31_days'],B3=results['B3']['all_31_days']),indent=2))


if __name__=='__main__':main()
