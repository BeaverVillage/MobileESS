"""Exact necessary support-cover selection; no optimizer and no date patch.

One complete new path per class suffices for a single class-support bound:
multiple paths lower its minimum only by their best individual value. Dynamic
programming uses exact gains and exact Pareto domination, never heuristic cuts.
Full A1/minimality acceptance still requires independent domain tests/proofs.
"""
import sys,math
from fractions import Fraction as Q
from collections import defaultdict
from .common import *

def tie(row):return (int(row['delta_start'])>0,row['site'],int(row['start']),row['option_id'])

def solve_group(rows,count,denom):
    by=defaultdict(list)
    for x in rows:by[x['class_id']].append(x)
    dp=[{} for _ in range(count+1)];dp[0][0]=(0,())
    for key,options in sorted(by.items()):
        best={}
        for x in options:
            cost=int(x['abs_delta_start']);gain=int(-Q(x['class_delta_exact'])*denom)
            if cost not in best or (-gain,tie(x))<(-best[cost][0],tie(best[cost][1])):best[cost]=(gain,x)
        curve=[];prior=-1
        for cost,(gain,x) in sorted(best.items()):
            if gain>prior:curve.append((cost,gain,x));prior=gain
        for c in range(count,0,-1):
            out=dict(dp[c])
            for oldcost,(oldgain,chosen) in dp[c-1].items():
                for cost,gain,x in curve:
                    k=oldcost+cost;value=(oldgain+gain,chosen+(x,))
                    if k not in out or value[0]>out[k][0] or value[0]==out[k][0] and tuple(sorted(tie(y) for y in value[1]))<tuple(sorted(tie(y) for y in out[k][1])):out[k]=value
            kept={};prior=-1
            for cost,value in sorted(out.items()):
                if value[0]>prior:kept[cost]=value;prior=value[0]
            dp[c]=kept
    return dp[count]

def main(day,tag):
    folder=CASE/day/tag;current=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected'];classes={x['class_id'] for x in current}
    proof=read(folder/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json')
    if proof['PASS'] is not True:raise ValueError('INDEPENDENT_SUPPORT_PROOF_REQUIRED')
    margin=Q(proof['exact_margin']);rows=read(folder/'BREAKING_SAME_SITE_STAYS.json');trace=[]
    floor=max(int(x['rank_same_site']) for x in current)
    def capacity(candidates):
        best={}
        for x in candidates:best[x['class_id']]=max(best.get(x['class_id'],Q(0)),-Q(x['class_delta_exact']))
        old=sorted((v for k,v in best.items() if k in classes),reverse=True);new=sorted((v for k,v in best.items() if k not in classes),reverse=True)
        return old,new
    for rank in sorted(set(int(x['rank_same_site']) for x in rows)):
        if rank<floor:continue
        eligible=[x for x in rows if int(x['rank_same_site'])<=rank];old,new=capacity(eligible)
        trace.append(dict(rank=rank,exact_maximum_relaxation=str(sum(old+new,Q(0))),required_margin=str(margin)))
        if sum(old+new,Q(0))>=margin:break
    else:raise ValueError('SAME_SITE_SUPPORT_COVER_NOT_AVAILABLE')
    k=next(k for k in range(len(new)+1) if sum(old+new[:k],Q(0))>=margin)
    p=next(p for p in range(k,k+len(old)+1) if sum(new[:k]+old[:p-k],Q(0))>=margin)
    current_max=max(int(x['abs_delta_start']) for x in current)
    for displacement in sorted({current_max}|{int(x['abs_delta_start']) for x in eligible if int(x['abs_delta_start'])>=current_max}):
        bounded=[x for x in eligible if int(x['abs_delta_start'])<=displacement];a,b=capacity(bounded)
        if len(b)>=k and len(a)>=p-k and sum(b[:k]+a[:p-k],Q(0))>=margin:break
    den=margin.denominator
    for x in bounded:den=math.lcm(den,Q(x['class_delta_exact']).denominator)
    olddp=solve_group([x for x in bounded if x['class_id'] in classes],p-k,den)
    newdp=solve_group([x for x in bounded if x['class_id'] not in classes],k,den);wanted=int(margin*den);answer=None
    for ca,(ga,xa) in sorted(olddp.items()):
        for cb,(gb,xb) in sorted(newdp.items()):
            if ga+gb<wanted:continue
            chosen=xa+xb;score=(ca+cb,tuple(sorted(tie(x) for x in chosen)))
            if answer is None or score<answer[0]:answer=score,chosen
    if answer is None:raise ValueError('EXACT_COVER_DP_FAILED')
    added=sorted(answer[1],key=tie);gain=-sum((Q(x['class_delta_exact']) for x in added),Q(0))
    if gain<margin or len({x['class_id'] for x in added})!=len(added):raise ValueError('EXACT_SELECTED_SUPPORT_COVER')
    result=dict(PASS=True,scope='minimal necessary batch against ONE verified support certificate in first admissible same-site rank, not full A1 minimum',
        rank=rank,earlier_rank_exact_upper_bounds=trace,additional_classes=k,added_options=p,max_abs_delta=displacement,sum_added_abs_delta=answer[0][0],
        total_expanded_classes=len(classes)+k,total_added_options=len(current)+p,total_abs_delta=sum(int(x['abs_delta_start']) for x in current)+answer[0][0],
        selected=added,exact_gain=str(gain),required_margin=str(margin),native_optimizer_calls=0,exact_Pareto_domination_only=True,
        unique_global_lex_tie_proven=False,global_full_A1_minimum_proven=False)
    atomic(folder/'EXACT_NECESSARY_SUPPORT_SELECTION.json',result);atomic(folder/'EXACT_NECESSARY_NEXT_DOMAIN.json',current+added)
    print('EXACT_NECESSARY_SUPPORT_BATCH',rank,'newclasses',k,'options',p,'max',displacement,'sum',answer[0][0],flush=True)
if __name__=='__main__':main(*sys.argv[1:])
