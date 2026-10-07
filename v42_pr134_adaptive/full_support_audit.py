"""Lazy ALL-physical-universe support lower bound; no native model or solve.

Every logical migration transfer start is repriced against the new support.
Old certificate incidence blocks are not assumed constant for a new ray.
"""
import csv,json,sys,math
from fractions import Fraction as Q
from .common import *

def main(day,tag):
    folder=CASE/day/tag;proof=read(folder/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json');raw=read(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json')
    poolproof=read(OUT/(label(day)+'_INDEPENDENT_POOL_VERIFICATION.json'))
    if not proof['PASS'] or not poolproof['PASS']:raise ValueError('INDEPENDENT_AUTHORITIES_REQUIRED')
    data=load(day);r=data[3];classes=data[7]['classes'];known={(x['site'],x['slot']):Q(x['coefficient']) for x in raw['known_coefficients']}
    denominator=1
    for w in known.values():denominator=math.lcm(denominator,w.denominator)
    def exact_integer(value):
        if value.denominator!=1:raise ValueError('NONINTEGER_SCALE_WOULD_TRUNCATE')
        return value.numerator
    horizon=max(b.latest_completion for b in data[2].values());prefix={}
    for site in r.capacities:
        ps=[0]
        for t in range(horizon):ps.append(ps[-1]+exact_integer(known.get((site,t),Q(0))*denominator))
        prefix[site]=ps
    minima={k:exact_integer(Q(v['independent_safe_lower_bound'])*denominator) for k,v in proof['all_class_bounds'].items()};witness={};transfers={};options=0;records=0
    def restart(src,dst,g,tau):
        key=src,dst,g,tau
        if key not in transfers:
            left=r.bytes_per_gpu*g;t=tau;path=r.paths[src,dst]
            while left and t<r.control_end:
                left-=min(left,*(max(0,r.wan_capacities.get((l,t),0)) for l in path));t+=1
            if left:raise ValueError('AUDITED_WAN_PAYLOAD_NOT_DELIVERED')
            transfers[key]=t+r.restart_slots
        return transfers[key]
    def cost(site,lo,hi):return prefix[site][hi]-prefix[site][lo]
    with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as f:
        for x in csv.DictReader(f):
            key=x['class_id'];start=int(x['start']);site=x['site'];gpu=int(x['GPU']);duration=int(x['service_slots']);cp=int(x['checkpoint']);mult=int(x['option_multiplicity'])
            if cp<0:value=gpu*cost(site,start,start+duration);chosen=None
            else:
                remain=duration-(cp-start);source=cost(site,start,cp);taus=json.loads(x['lazy_transfer_starts']);dest=x['destination'];value=None;chosen=None
                if len(taus)!=mult:raise ValueError('LOGICAL_BLOCK_CARDINALITY')
                for tau in taus:
                    rr=restart(site,dest,gpu,int(tau));v=gpu*(source+cost(dest,rr,rr+remain))
                    if value is None or v<value:value=v;chosen=int(tau)
            if value<minima[key]:minima[key]=value;witness[key]=dict(option_id=x['option_id'],transfer_start=chosen,exact_cost=str(Q(value,denominator)))
            options+=mult;records+=1
            if records%100000==0:print('ALL_PHYSICAL_SUPPORT',records,options,flush=True)
    if options!=poolproof['logical_options']['total'] or records!=poolproof['records']:raise ValueError('FULL_PHYSICAL_UNIVERSE_NOT_COMPLETELY_REPRICED')
    before=sum((Q(v['independent_safe_lower_bound'])*len(classes[k]) for k,v in proof['all_class_bounds'].items()),Q(0))
    after=sum((Q(v,denominator)*len(classes[k]) for k,v in minima.items()),Q(0));minimum=Q(proof['exact_safe_lower_bound'])-before+after
    rhs=Q(proof['exact_rhs']);allowance=Q(proof['exact_residual_allowance']);margin=minimum-rhs
    result=dict(PASS=True,complete_physical_universe_repriced=True,logical_options=options,records=records,exact_minimum=str(minimum),exact_rhs=str(rhs),
        exact_margin=str(margin),margin_float=float(margin),original_residual_allowance=str(allowance),
        physical_universe_infeasible_proven=margin>allowance,classification='PRESCREENING_ONLY_INSUFFICIENT' if margin>allowance else 'UNRESOLVED',
        all_class_minima={k:str(Q(v,denominator)) for k,v in minima.items()},minimizing_omitted_witnesses=witness,
        optimizer_calls=0,native_columns_created=0,future_information_used=False,generator_imported=False,
        original_lossless_pool=poolproof['pool'],source_certificate=record(folder/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json'),
        proof='Every audited complete physical path is included in the support minimum. A nonpositive margin means only that this certificate cannot exclude the full universe; it is not a feasible witness.')
    atomic(folder/'FULL_PHYSICAL_UNIVERSE_SUPPORT_AUDIT.json',result);print('ALL_PHYSICAL_SUPPORT_DONE',result['classification'],float(margin),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
