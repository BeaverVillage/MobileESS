"""Independent necessary cover audit; does not import the selector/solver."""
import sys
from fractions import Fraction as Q
from collections import defaultdict
from .common import *

def verify(day,tag):
    folder=CASE/day/tag;certificate=read(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json');proof=read(folder/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json')
    if not proof['PASS']:raise ValueError('INDEPENDENT_SUPPORT_NOT_VALID')
    result=read(folder/'EXACT_NECESSARY_SUPPORT_SELECTION.json');current=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected']
    existing={x['class_id'] for x in current};pool=read(folder/'BREAKING_SAME_SITE_STAYS.json');data=load(day);known={(x['site'],x['slot']):Q(x['coefficient']) for x in certificate['known_coefficients']}
    cache={}
    for x in pool:
        key=x['class_id'];j=data[1][data[7]['classes'][key][0]];start=int(x['start']);axis=x['site'],start,j.service_slots,j.gpu
        if axis not in cache:cache[axis]=j.gpu*sum((w for (s,t),w in known.items() if s==x['site'] and start<=t<start+j.service_slots),Q(0))
        effect=min(Q(0),cache[axis]-Q(certificate['all_class_minima'][key]['exact_minimum_per_job']))*len(data[7]['classes'][key])
        if effect!=Q(x['class_delta_exact']) or effect>=0 or x['site']!=j.reference_site:raise ValueError('INDEPENDENT_NEW_SUPPORT_EFFECT')
    margin=Q(result['required_margin']);rank=result['rank'];eligible=[x for x in pool if int(x['rank_same_site'])<=rank]
    def best(rows):
        b={}
        for x in rows:b[x['class_id']]=max(b.get(x['class_id'],Q(0)),-Q(x['class_delta_exact']))
        return sorted((w for k,w in b.items() if k in existing),reverse=True),sorted((w for k,w in b.items() if k not in existing),reverse=True)
    floor=max(int(x['rank_same_site']) for x in current)
    for r in range(floor,rank):
        old,new=best([x for x in pool if int(x['rank_same_site'])<=r])
        if sum(old+new,Q(0))>=margin:raise ValueError('EARLIER_SUPPORT_RANK_CAN_COVER')
    k=result['additional_classes'];p=result['added_options'];old,new=best(eligible)
    if k and sum(old+new[:k-1],Q(0))>=margin:raise ValueError('FEWER_CLASSES_SUPPORT_COVER')
    if p>k and sum(new[:k]+old[:p-k-1],Q(0))>=margin:raise ValueError('FEWER_OPTIONS_SUPPORT_COVER')
    limit=result['max_abs_delta'];oldmax=max(int(x['abs_delta_start']) for x in current)
    if limit>oldmax:
        a,b=best([x for x in eligible if int(x['abs_delta_start'])<limit])
        if len(a)>=p-k and len(b)>=k and sum(a[:p-k]+b[:k],Q(0))>=margin:raise ValueError('SMALLER_MAX_DELTA_SUPPORT_COVER')
    bounded=[x for x in eligible if int(x['abs_delta_start'])<=limit];cap=result['sum_added_abs_delta']-1
    # Independent bounded-cost DP. No Pareto routine from the selector is used.
    def dp(rows,count):
        groups=defaultdict(list)
        for x in rows:groups[x['class_id']].append(x)
        states={(0,0):Q(0)}
        for rows in groups.values():
            nxt=dict(states)
            for (c,cost),gain in states.items():
                if c==count:continue
                for x in rows:
                    cc=cost+int(x['abs_delta_start'])
                    if cc>cap:continue
                    key=c+1,cc;nxt[key]=max(nxt.get(key,Q(-1)),gain-Q(x['class_delta_exact']))
            states=nxt
        return {cost:gain for (c,cost),gain in states.items() if c==count}
    a=dp([x for x in bounded if x['class_id'] in existing],p-k);b=dp([x for x in bounded if x['class_id'] not in existing],k)
    if any(ca+cb<=cap and ga+gb>=margin for ca,ga in a.items() for cb,gb in b.items()):raise ValueError('SMALLER_SUM_DELTA_SUPPORT_COVER')
    selected=result['selected'];ids={x['option_id']:x for x in bounded}
    if any(x['option_id'] not in ids for x in selected) or len({x['class_id'] for x in selected})!=p:raise ValueError('SELECTED_CLASS_OPTION_MEMBERSHIP')
    gain=-sum((Q(x['class_delta_exact']) for x in selected),Q(0))
    if gain<margin or sum(int(x['abs_delta_start']) for x in selected)!=result['sum_added_abs_delta']:raise ValueError('SELECTED_COVER_GAIN_COST')
    audit=dict(PASS=True,all_same_site_breaking_effects_checked=len(pool),earlier_rank_class_option_max_and_sum_bounds_proven=True,
        optimizer_calls=0,selector_imported=False,physical_support_builder_imported=False,unique_lex_tie_proven=False,
        full_A1_minimum_proven=False,scope='Exact zero-residual single-certificate necessary cover only; original numeric acceptance/minimum still separately gated',
        selection=record(folder/'EXACT_NECESSARY_SUPPORT_SELECTION.json'))
    atomic(folder/'INDEPENDENT_EXACT_SUPPORT_SELECTION.json',audit);print('INDEPENDENT_SUPPORT_COVER_PASS',len(pool),flush=True)
if __name__=='__main__':verify(*sys.argv[1:])
