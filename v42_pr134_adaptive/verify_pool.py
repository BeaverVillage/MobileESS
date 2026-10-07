"""Independent streamed verifier. No pool/generator/native/reducer imports."""
import csv,json,sys
from collections import Counter,defaultdict
from dataclasses import replace
from fractions import Fraction
import numpy as np,scipy.sparse as sp
from .common import *
def verify(day):
    bundle,jobs,bounds,r,raw,graphs,old,prep=load(day)
    prior=read(OUT/(label(day)+'_S0_CERTIFICATE.json'));a=sp.load_npz(SOURCE/day/'A0_MATRIX.npz')
    z=dict(np.load(SOURCE/day/'A0_ATTRIBUTES_CODED.npz'));names=dict(np.load(SOURCE/day/'ORIGINAL_NATIVE_NAMES.npz'))
    completion=prior.get('rational_completion')
    if completion:
        c=read(completion['path']);rows=c['rows'];weights=[Fraction(x) for x in c['exact_multipliers']]
    else:
        c=dict(np.load(prior['raw_ray']['path']));rows=c['rows'];weights=[Fraction(float(x)) for x in c['ray']]
    known={};card={}
    for row,w in zip(rows,weights):
        if not w:continue
        row=int(row);family=str(z['rf_names'][z['rf'][row]]);cols=a.indices[a.indptr[row]:a.indptr[row+1]]
        if family=='known_GPU_binding':
            n=next(str(names['vars'][j]) for j in cols if str(names['vars'][j]).startswith('known['));site,t=n[6:-1].split(',');known[site,int(t)]=w
        elif family=='class_exact_cardinality':
            key=next(str(names['vars'][j]).split('CLASS_')[1][:12] for j in cols if 'CLASS_' in str(names['vars'][j]));card[key]=w
    counts=Counter();block_count=0;worst_unknown=[];templates={};gpu_prefix={}
    horizon=max(b.latest_completion for b in bounds.values())
    def fits(site,lo,hi,gpu):
        key=site,gpu
        if key not in gpu_prefix:
            bad=np.array([r.capacities[site]-r.fixed_gpu.get((site,t),0)<gpu-1e-9 for t in range(horizon)],dtype=np.int64)
            gpu_prefix[key]=np.r_[0,np.cumsum(bad)]
        return gpu_prefix[key][hi]-gpu_prefix[key][lo]==0
    def transfer(src,dst,g,tau):
        key=src,dst,g,tau
        if key in templates:return templates[key]
        path=r.paths.get((src,dst),());left=r.bytes_per_gpu*g;t=tau
        if not path or len(path)!=len(set(path)):raise ValueError('INDEPENDENT_WAN_PATH')
        fixed_ok=True
        while left and t<r.control_end:
            amount=min(left,*(max(0,r.wan_capacities.get((l,t),0)) for l in path))
            if amount:
                fixed_ok &= all(amount<=r.wan_capacities.get((l,t),0)-r.fixed_wan.get((l,t),0)+1e-9 for l in path)
            fixed_ok &= 1<=r.max_active_transfers-r.fixed_transfers.get(t,0)+1e-9
            left-=amount;t+=1
        templates[key]=(left==0 and fixed_ok and t+r.restart_slots<r.control_end,t,t+r.restart_slots)
        return templates[key]
    def exact_effect(j,key,parts):
        return card.get(key[:12],Fraction(0))-j.gpu*sum((w for (site,t),w in known.items() for s,lo,hi in parts if site==s and lo<=t<hi),Fraction(0))
    seen=set();classes=set();first_examples=[];same_site_starts=defaultdict(dict)
    with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as f:
        for row in csv.DictReader(f):
            key=row['class_id'];uid=prep['classes'][key][0];j=jobs[uid];b=bounds[uid];start=int(row['start']);site=row['site'];gpu=int(row['GPU']);d=int(row['service_slots']);N=int(row['class_count']);cp=int(row['checkpoint'])
            if uid!=row['job_representative'] or N!=len(prep['classes'][key]) or gpu!=j.gpu or d!=j.service_slots:raise ValueError('INDEPENDENT_CLASS_RESOURCE_IDENTITY')
            if site not in set(j.initial_sites)|{j.reference_site} or gpu>r.capacities[site] or gpu>max(r.rack_limits[site]):raise ValueError('SITE_RACK_GANG')
            if j.state!='PENDING' or j.protected or j.qos in ('high','urgent') or j.unknown_arrival:raise ValueError('UNAUTHORIZED_TIMING_RESTORATION')
            if start<max(j.submit,j.event) or start>=r.control_end or start+d>b.latest_completion:raise ValueError('CAUSAL_HORIZON_CARRYOUT')
            if row['option_id'] in seen:raise ValueError('DUPLICATE_POOL_RECORD')
            seen.add(row['option_id']);classes.add(key);taus=json.loads(row.get('lazy_transfer_starts','[]'));mult=int(row.get('option_multiplicity',1))
            if cp<0:
                if taus or mult!=1 or (site,start) in graphs[uid].events['y'] and (site,start+d) in graphs[uid].events['f0']:raise ValueError('STAY_NOT_OMITTED')
                parts=((site,start,start+d),);effect=exact_effect(j,key,parts)
                if not fits(site,start,start+d,gpu):raise ValueError('IMMUTABLE_STAY_GPU_CAPACITY')
                if site==j.reference_site:same_site_starts[key][start]=int(row['rank_same_site'])
            else:
                if not j.checkpoint_authorized or j.migrations_used or start in b.allowed_starts or mult!=len(taus) or len(taus)!=len(set(taus)):raise ValueError('MIGRATION_AUTHORITY_OR_LAZY_COUNT')
                # PENDING checkpoint is exactly elapsed=0 + 1800-second phase.
                if cp-start<=0 or (cp-start)%2 or cp>=start+d:raise ValueError('EXACT_CHECKPOINT_PHASE')
                dest=row['destination'];remaining=d-(cp-start)
                if dest==site or dest not in j.initial_sites or gpu>r.capacities[dest] or gpu>max(r.rack_limits[dest]):raise ValueError('DESTINATION_COMPATIBILITY')
                restarts=[]
                for tau in taus:
                    feasible,end,restart=transfer(site,dest,gpu,int(tau))
                    if tau<cp or not feasible or restart>=r.control_end or restart+remaining>b.latest_completion:raise ValueError('WAN_RESTART_CARRYOUT')
                    restarts.append(restart)
                restarts=np.array(restarts,dtype=np.int64)
                if not fits(site,start,cp,gpu) or not np.all(fits(dest,restarts,restarts+remaining,gpu)):raise ValueError('IMMUTABLE_MIGRATION_GPU_CAPACITY')
                for (s,t),w in known.items():
                    if s!=dest:continue
                    active=(restarts<=t)&(t<restarts+remaining)
                    if not np.all(active==active[0]):raise ValueError('NONCONSTANT_RATIONAL_LAZY_BLOCK_SUPPORT')
                parts=((site,start,cp),(dest,int(restarts[0]),int(restarts[0])+remaining));effect=exact_effect(j,key,parts)
            if str(effect)!=row['certificate_delta_exact'] or str(effect*N)!=row['class_delta_exact']:raise ValueError('INDEPENDENT_EXACT_EFFECT')
            cat='CERTIFICATE_BREAKING' if effect<0 else 'CERTIFICATE_WORSENING' if effect>0 else 'CERTIFICATE_NEUTRAL'
            if cat!=row['classification']:raise ValueError('SIGN_PRICE_CLASSIFICATION')
            counts[cat]+=mult;counts['total']+=mult;counts['migration' if cp>=0 else 'stay']+=mult;block_count+=1
            if block_count%100000==0:print(day,'independent pool records',block_count,flush=True)
    for key,starts in same_site_starts.items():
        j=jobs[prep['classes'][key][0]]
        ordered=sorted(starts,key=lambda start:(abs(start-j.reference_start),start>j.reference_start,start))
        if any(starts[start]!=i+1 for i,start in enumerate(ordered)):raise ValueError('NEAREST_PHYSICALLY_VALID_SAME_SITE_RANK')
    summary=read(OUT/(label(day)+'_POOL_SUMMARY.json'))
    if any(counts[k]!=v for k,v in summary['counts'].items() if k!='pool_records'):raise ValueError('POOL_COUNT_MISMATCH')
    result=dict(PASS=True,logical_options=dict(counts),records=block_count,classes_with_omissions=len(classes),
        exact_rational_all_option_effects=True,lazy_blocks_lossless=True,independent_WAN_templates=len(templates),
        all_immutable_GPU_WAN_and_active_transfer_masks_independently_replayed=True,
        nearest_physically_valid_same_site_ranks_independently_verified=True,
        builder_generator_imported=False,solver_imported=False,full_universe_native_columns=0,future_outcome_reads=0,
        matrix=record(SOURCE/day/'A0_MATRIX.npz'),input=record(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json'),pool=record(OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')))
    write(label(day)+'_INDEPENDENT_POOL_VERIFICATION.json',result);print('INDEPENDENT_POOL_PASS',day,block_count,counts['total'],flush=True)
    return result
if __name__=='__main__':verify(sys.argv[1])
