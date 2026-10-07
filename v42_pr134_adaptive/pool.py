"""Generic lazy physical pool. No native model, date patch or full option storage."""
from dataclasses import replace
from fractions import Fraction
from collections import defaultdict,Counter
import csv,json
import numpy as np
from v42_job_capability import Option,validate,checkpoint_records
from v42_boundary.generator import Generator
from .common import *

def physical_starts(job,bound):
    if job.state!='PENDING' or job.protected or job.qos in ('high','urgent') or job.unknown_arrival:
        return tuple(bound.allowed_starts)
    lo=max(job.submit,job.event)
    hi=min(119,bound.latest_completion-job.service_slots)
    return tuple(sorted(set(bound.allowed_starts)|set(range(lo,hi+1))))

def options(job,bound,resources,graph,cert=None,class_id=None,gen=None):
    """All newly authorized complete paths, streamed, preserving inherited masks."""
    starts=physical_starts(job,bound)
    wide=replace(bound,allowed_starts=starts)
    gen=gen or Generator(resources,bound.latest_completion)
    initial,dests=gen.static_sites(job)
    for start in sorted(starts,key=lambda s:(abs(s-job.reference_start),s>job.reference_start,s)):
        for site in initial:
            if start+job.service_slots<=bound.latest_completion and gen.fits(site,start,job.service_slots,job.gpu):
                if (site,start) not in graph.events['y'] or (site,start+job.service_slots) not in graph.events['f0']:
                    option=Option(start,site,((site,start,start+job.service_slots),))
                    validate(job,option,wide,resources)
                    yield option,1,None
            # S0 exact support is complete at every old start. Migration paths
            # for those starts are already represented; only new starts omitted.
            if start in bound.allowed_starts or not job.checkpoint_authorized or job.unknown_arrival or job.migrations_used:
                continue
            for cp,physical in checkpoint_records(job,start,min(start+job.service_slots,resources.control_end)):
                remaining=job.service_slots-(cp-start)
                if remaining<=0 or not gen.fits(site,start,cp-start,job.gpu):continue
                for dest in dests:
                    if dest==site:continue
                    latest=min(resources.control_end-resources.restart_slots-2,bound.latest_completion-remaining-resources.restart_slots-1)
                    ids=np.arange(cp,latest+1,dtype=int)
                    feasible,restarts=gen.transfer_series(site,dest,job.gpu)
                    good=feasible[ids] & (restarts[ids]+remaining<=bound.latest_completion)
                    good &= gen.mask(remaining,job.gpu,dest)[restarts[ids]]
                    ids=ids[good]
                    if not len(ids):continue
                    # Exact quotient by certificate-support incidence. No
                    # floating residual or price is used in this partition.
                    # Python integer signatures have no arbitrary support-axis
                    # cutoff and retain every exact incidence bit.
                    signature=np.zeros(len(ids),dtype=object)
                    critical=[(t,w) for (s,t),w in cert['known'].items() if s==dest]
                    for bit,(t,w) in enumerate(critical):
                        signature+=((restarts[ids]<=t)&(t<restarts[ids]+remaining)).astype(object)*(1<<bit)
                    groups={int(sig):ids[signature==sig].tolist() for sig in np.unique(signature)}
                    # A lossless lazy block records ALL transfer starts with
                    # identical exact certificate effect. Each path's unchanged
                    # deterministic WAN template is reconstructed from Resources.
                    for groupkey,taus in groups.items():
                        tau=taus[0];tr=gen.transfer(site,dest,job.gpu,tau)
                        option=Option(start,site,((site,start,cp),(dest,tr.restart,tr.restart+remaining)),cp,physical,dest,tau,tr.end,tr.restart,tr.wan)
                        validate(job,option,wide,resources)
                        yield option,len(taus),taus

def certificate(day,restricted_folder=None):
    import scipy.sparse as sp
    folder=Path(restricted_folder) if restricted_folder else SOURCE/day
    a=sp.load_npz(folder/('EXPANDED_MATRIX.npz' if restricted_folder else 'A0_MATRIX.npz'));z=dict(np.load(folder/('EXPANDED_ATTRIBUTES.npz' if restricted_folder else 'A0_ATTRIBUTES_CODED.npz')))
    names=dict(np.load(folder/('NATIVE_NAMES.npz' if restricted_folder else 'ORIGINAL_NATIVE_NAMES.npz')))
    prior=read(folder/'INDEPENDENT_EXACT_CERTIFICATE.json') if restricted_folder else read(PRIOR/(label(day)+'_INDEPENDENT_EXACT_CERTIFICATE.json'))
    if not prior['PASS']:raise ValueError('S0_INDEPENDENT_PROOF_REQUIRED')
    if not restricted_folder and record(folder/'A0_MATRIX.npz')!=prior['original_matrix']:raise ValueError('S0_MATRIX_IDENTITY')
    # Adapter discovers proof representation from artifact metadata, not dates.
    completion=prior.get('rational_completion')
    if completion:
        p=Path(completion['path'])
        if sha(p)!=completion['sha256']:raise ValueError('COMPLETION_SHA')
        completed=read(p);rows=completed['rows'];weights=[Fraction(s) for s in completed['exact_multipliers']]
    else:
        reference=prior.get('raw_ray',prior.get('raw'));p=Path(reference['path'])
        if sha(p)!=reference['sha256']:raise ValueError('RAW_RAY_SHA')
        raw=dict(np.load(p));rows=raw['rows'];weights=[Fraction(float(x)) for x in raw['ray']]
    known={};cardinality={};unsupported=[]
    for row,weight in zip(rows,weights):
        if not weight:continue
        row=int(row);family=str(z['rf_names'][z['rf'][row]]) if 'rf' in z else str(names['rows'][row]).split('[')[0]
        if family=='known_GPU_binding':
            cs=a.indices[a.indptr[row]:a.indptr[row+1]]
            matches=[str(names['vars'][j]) for j in cs if str(names['vars'][j]).startswith('known[')]
            if len(matches)!=1:raise ValueError('KNOWN_AXIS_BINDING')
            site,slot=matches[0][6:-1].split(',');known[site,int(slot)]=weight
        else:
            cs=a.indices[a.indptr[row]:a.indptr[row+1]]
            identifiers={str(names['vars'][j]).split('CLASS_')[1][:12] for j in cs if 'CLASS_' in str(names['vars'][j])}
            if family=='class_exact_cardinality':
                if len(identifiers)!=1:raise ValueError('CLASS_CARDINALITY_AXIS')
                cardinality[next(iter(identifiers))]=weight
            elif all(str(names['vars'][j]).startswith('Y[') for j in cs) and str(z['sense'][row])=='=':
                owners={str(names['vars'][j]).split('[')[1].split(',')[0] for j in cs}
                if len(owners)!=1:raise ValueError('SINGLETON_CARDINALITY_AXIS')
                owner=next(iter(owners));data=load(day)
                keys=[key for key,us in data[7]['classes'].items() if owner in us]
                if len(keys)!=1:raise ValueError('SINGLETON_CLASS_OWNER')
                cardinality[keys[0][:12]]=weight
            elif family not in ('CC4_CDF_U','CC4_site_nominal_partition','nominal_and_compute_headroom','voltage_upper'):
                # Remaining nonzero rows confined to immutable RUNNING units
                # do not receive columns from PENDING STAY domain restoration.
                data=load(day);running={u for u,j in data[1].items() if j.state=='RUNNING'}
                owners={str(names['vars'][j]).split('[')[1].split(',')[0].rstrip(']') for j in cs if '[' in str(names['vars'][j])}
                if not owners or not owners<=running:unsupported.append(family)
    return dict(known=known,cardinality=cardinality,unsupported=unsupported,prior=prior,rows=rows,weights=weights)

def price(job,option,cert,class_id):
    # Substitute full known-binding equality into the signed original proof.
    # Include its signed class cardinality coefficient. A newly admitted
    # nonnegative path count lowers the bound minimum exactly when c < 0.
    # Other weighted rows
    # act only on preserved global variables and hence have zero direct delta.
    if cert['unsupported']:return 'UNKNOWN',None
    def cost(segments):
        cache=cert.setdefault('_interval_cache',{})
        total=Fraction(0)
        for site,a,b in segments:
            key=site,a,b
            if key not in cache:cache[key]=sum((w for (s,t),w in cert['known'].items() if s==site and a<=t<b),Fraction(0))
            total+=cache[key]
        return -job.gpu*total
    delta=cost(option.segments)+cert['cardinality'].get(class_id[:12],Fraction(0))
    return ('CERTIFICATE_BREAKING' if delta<0 else 'CERTIFICATE_NEUTRAL' if delta==0 else 'CERTIFICATE_WORSENING'),delta

def enumerate_day(day):
    bundle,jobs,bounds,r,raw,graphs,old,prep=load(day);cert=certificate(day)
    write(label(day)+'_S0_CERTIFICATE.json',dict(cert['prior'],source_proof=record(PRIOR/(label(day)+'_INDEPENDENT_EXACT_CERTIFICATE.json')),
        S0_unchanged=True,reproduced_by_original_matrix_exact_certificate=True,new_native_solve=False,
        scope='Fixed S0 domain only; no claim about the enlarged physical scheduling domain'))
    fields=['class_id','class_count','job_representative','option_id','action','site','start','reference_start','delta_start','abs_delta_start','segments','checkpoint','destination','transfer_start','service_slots','GPU','classification','certificate_delta_exact','class_delta_exact','rank_same_site','option_multiplicity','lazy_transfer_starts']
    totals=Counter();classcounts=Counter();rank_counts=Counter();breaking=[]
    poolfile=OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv');effectsfile=OUT/(label(day)+'_CERTIFICATE_OPTION_EFFECT.csv')
    gen=Generator(r,max(b.latest_completion for b in bounds.values()))
    with poolfile.open('w',encoding='utf8',newline='') as uf,effectsfile.open('w',encoding='utf8',newline='') as ef:
        uw=csv.DictWriter(uf,fields,lineterminator='\n');ew=csv.DictWriter(ef,fields,lineterminator='\n');uw.writeheader();ew.writeheader()
        for index,(key,us) in enumerate(sorted(prep['classes'].items())):
            uid=us[0];j=jobs[uid];b=bounds[uid];g=graphs[uid]
            for u in us:
                if replace(j,uid=u)!=jobs[u] or b!=bounds[u] or g.sha!=graphs[u].sha:raise ValueError('CLASS_PHYSICAL_OPTION_UNIFORMITY')
            omitted_same=sorted(set(physical_starts(j,b))-set(b.allowed_starts),key=lambda s:(abs(s-j.reference_start),s>j.reference_start,s))
            ranks={s:i+1 for i,s in enumerate(omitted_same)}
            for option,multiplicity,taus in options(j,b,r,g,cert,key,gen):
                category,delta=price(j,option,cert,key)
                optionid=digest(dict(class_id=key,option=option.__dict__,lazy_transfer_starts=taus))
                row=dict(class_id=key,class_count=len(us),job_representative=uid,option_id=optionid,action=option.action(j),site=option.initial_site,start=option.start,
                    reference_start=j.reference_start,delta_start=option.start-j.reference_start,abs_delta_start=abs(option.start-j.reference_start),
                    segments=json.dumps(option.segments,separators=(',',':')),checkpoint=option.checkpoint,destination=option.destination,transfer_start=option.transfer_start,
                    service_slots=j.service_slots,GPU=j.gpu,classification=category,certificate_delta_exact=str(delta) if delta is not None else '',
                    class_delta_exact=str(len(us)*delta) if delta is not None else '',rank_same_site=ranks.get(option.start,0),option_multiplicity=multiplicity,lazy_transfer_starts=json.dumps(taus or [],separators=(',',':')))
                uw.writerow(row);ew.writerow(row);totals[category]+=multiplicity;totals['total']+=multiplicity;totals['migration' if option.migrated else 'stay']+=multiplicity;totals['pool_records']+=1
                if category=='CERTIFICATE_BREAKING' and not option.migrated:breaking.append(row)
            classcounts['classes']+=1
            if index%10==0:print(day,'priced classes',index+1,'options',totals['total'],flush=True)
    write(label(day)+'_POOL_SUMMARY.json',dict(PASS=True,counts=dict(totals),classes=len(prep['classes']),jobs=len(jobs),
        pool=record(poolfile),effects=record(effectsfile),model_columns_created=0,fully_priced=totals['UNKNOWN']==0,
        physical_start_contract='causal issue release; unchanged original completion ceiling; preserved protection and action authority',
        old_reference_lower_filter_is_prescreen=True,CC4_changed=False,capacities_changed=False,Runtime_changed=False,service_changed=False,future_data_reads=0))
    folder=CASE/day;folder.mkdir(parents=True,exist_ok=True);atomic(folder/'BREAKING_STAYS.json',breaking)
    print(day,'POOL',dict(totals),flush=True)
    return breaking

if __name__=='__main__':
    import sys
    OUT.mkdir(parents=True,exist_ok=True)
    enumerate_day(sys.argv[1])
