"""Independent support certificate replay; no generator or optimizer imports.

Uses a superset of all paths represented by the frozen S0 graph. Immutable
occupancy pruning is relaxed, so the computed minimum is a safe lower bound.
An exact positive margin is required after the original residual allowance.
"""
import sys,pickle
from fractions import Fraction as Q
from collections import defaultdict
import numpy as np,scipy.sparse as sp
from .common import *

def verify(day,tag):
    folder=CASE/day/tag;p=read(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json')
    a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'));names=dict(np.load(folder/'NATIVE_NAMES.npz'))
    for item in (p['global_proof']['matrix'],p['global_proof']['raw_ray']):
        if sha(item['path'])!=item['sha256']:raise ValueError('CERTIFICATE_SHA_CHANGED')
    c=defaultdict(Q);rhs=Q(0);norm=Q(0)
    for ri,w in p['global_proof']['weights'].items():
        i=int(ri);w=Q(w);s=str(z['sense'][i]);n=str(names['rows'][i])
        if s=='<' and w<0 or s=='>' and w>0:raise ValueError('SIGNED_ROW_NOT_VALID')
        if not n.startswith(('CC4_','nominal_and_compute_headroom','RT_reserve_target','voltage_','transformer_','line_thermal_face','NormalAmps','physical_ACTIVE')):raise ValueError('NON_GLOBAL_PHYSICAL_ROW')
        rhs+=w*Q(float(z['rhs'][i]));norm+=abs(w)
        lo,hi=a.indptr[i:i+2]
        for j,v in zip(a.indices[lo:hi],a.data[lo:hi]):c[int(j)]+=w*Q(float(v))
    known={};other=Q(0)
    for j,w in c.items():
        if not w:continue
        name=str(names['vars'][j])
        if name.startswith('known['):
            site,t=name[6:-1].split(',');known[site,int(t)]=w;continue
        b=float(z['lb'][j] if w>0 else z['ub'][j])
        if not np.isfinite(b) or abs(b)>=1e100:raise ValueError('NONZERO_UNBOUNDED_COEFFICIENT')
        other+=w*Q(b)
    expected={(x['site'],x['slot']):Q(x['coefficient']) for x in p['known_coefficients']}
    if expected!=known or rhs!=Q(p['exact_rhs']):raise ValueError('EXACT_GLOBAL_RECONSTRUCTION')
    old=load(day);jobs,bounds,r,graphs,classes=old[1],old[2],old[3],old[5],old[7]['classes']
    added=defaultdict(list)
    for row in read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected']:added[row['class_id']].append(row)
    cache={}
    def value(site,start,end):
        key=site,start,end
        if key not in cache:cache[key]=sum((w for (s,t),w in known.items() if s==site and start<=t<end),Q(0))
        return cache[key]
    minimum=other+sum((w*Q(float(r.fixed_gpu.get(k,0))) for k,w in known.items()),Q(0));audits={};paths=0
    for key,us in sorted(classes.items()):
        uid=us[0];j=jobs[uid];b=bounds[uid];g=graphs[uid]
        if not any(k in known for n in ('r0','r1') for k in g.states[n]):
            costs=[Q(0)];scope='all represented old compute states have zero support overlap'
        else:
            costs=[];scope='complete graph path superset, immutable occupancy filters relaxed only in lower bound'
            outgoing=defaultdict(list)
            for (src,dst,tau),tr in g.transfers.items():outgoing[src].append((dst,tau,tr.restart))
            for site,start in g.events['y']:
                if (site,start+j.service_slots) in g.events['f0']:costs.append(j.gpu*value(site,start,start+j.service_slots));paths+=1
                for (src,cp),starts in g.compatible.items():
                    if src!=site or start not in starts:continue
                    rem=j.service_slots-(cp-start)
                    if rem<=0:continue
                    src_cost=value(site,start,cp)
                    for dst,tau,restart in outgoing[src]:
                        if tau<cp or restart+rem>b.latest_completion or (dst,restart+rem) not in g.events['f1']:continue
                        costs.append(j.gpu*(src_cost+value(dst,restart,restart+rem)));paths+=1
        for row in added[key]:
            start=int(row['start']);costs.append(j.gpu*value(row['site'],start,start+j.service_slots))
        if not costs:raise ValueError('NO_GRAPH_PATH_SUPPORT')
        lower=min(costs);claimed=Q(p['all_class_minima'][key]['exact_minimum_per_job'])
        if lower>claimed:raise ValueError('INDEPENDENT_RELAXATION_EXCLUDES_BUILDER_PATH')
        minimum+=len(us)*lower
        audits[key]=dict(independent_safe_lower_bound=str(lower),builder_minimum=str(claimed),count=len(us),scope=scope)
    allowance=Q(1e-5)*(norm+sum(abs(w) for w in c.values())+sum(abs(w) for w in known.values()))
    margin=minimum-rhs
    result=dict(PASS=margin>allowance,exact_safe_lower_bound=str(minimum),exact_rhs=str(rhs),exact_margin=str(margin),
        margin_float=float(margin),exact_residual_allowance=str(allowance),all_class_bounds=audits,explicit_path_superset_count=paths,
        optimizer_calls=0,generator_imported=False,physical_support_builder_imported=False,ignored_residuals=0,
        lower_bound_relaxation_is_only_in_certificate=True,model_changes=0,certificate=record(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json'))
    atomic(folder/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json',result)
    print('INDEPENDENT_SUPPORT_PASS',result['PASS'],float(margin),float(allowance),flush=True)
    if not result['PASS']:raise ValueError('PHYSICAL_SUPPORT_INDEPENDENT_CERTIFICATE_FAILED')
    return result
if __name__=='__main__':verify(*sys.argv[1:])
