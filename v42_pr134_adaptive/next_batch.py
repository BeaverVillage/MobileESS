"""Reprice all missing STAY candidates against a newly verified certificate."""
import csv,sys,itertools
from fractions import Fraction
from v42_job_capability import Option
from .common import *
from .pool import certificate,price
def main(day,tag):
    folder=CASE/day/tag;cert=certificate(day,folder);data=load(day);jobs=data[1];classes=data[7]['classes']
    if cert['unsupported']:raise ValueError('NEW_CERTIFICATE_EFFECT_UNSUPPORTED:'+str(cert['unsupported']))
    current=read(folder/'RESULT.json')['selected'];seen={r['option_id'] for r in current};pool=[];counts={}
    with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as f:
        for r in csv.DictReader(f):
            if int(r['checkpoint'])!=-1 or r['option_id'] in seen:continue
            j=jobs[classes[r['class_id']][0]]
            o=Option(int(r['start']),r['site'],((r['site'],int(r['start']),int(r['start'])+j.service_slots),))
            cat,delta=price(j,o,cert,r['class_id']);counts[cat]=counts.get(cat,0)+1
            if cat=='CERTIFICATE_BREAKING' and r['site']==j.reference_site:
                r.update(classification=cat,certificate_delta_exact=str(delta),class_delta_exact=str(delta*int(r['class_count'])))
                pool.append(r)
    margin=Fraction(cert['prior']['margin']);by={}
    for r in pool:
        key=r['class_id'];rank=(int(r['rank_same_site']),int(r['abs_delta_start']),int(r['delta_start'])>0,r['site'],r['option_id'])
        if key not in by or rank<by[key][0]:by[key]=(rank,r)
    ranked=sorted((x[1] for x in by.values()),key=lambda r:(int(r['rank_same_site']),int(r['abs_delta_start']),int(r['delta_start'])>0,r['site'],r['option_id']))
    new=[];reduction=Fraction(0)
    # Deterministic certificate-only batch; no claimed global lex minimum.
    for r in ranked:
        new.append(r);reduction-=Fraction(r['class_delta_exact'])
        if reduction>=margin:break
    if reduction<margin:raise ValueError('SAME_SITE_CERTIFICATE_COVER_NOT_FOUND')
    selected=current+new;atomic(CASE/day/'SELECTION_NEXT.json',selected)
    atomic(folder/'REPRICED_NEXT_BATCH.json',dict(PASS=True,counts=counts,selected=new,margin=str(margin),necessary_relaxation=str(reduction),
        global_minimum_claimed=False,new_certificate=record(folder/'INDEPENDENT_EXACT_CERTIFICATE.json')))
    print('NEXT_BATCH',len(current),'plus',len(new),'margin',float(margin),'relaxation',float(reduction),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
