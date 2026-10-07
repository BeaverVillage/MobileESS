"""Exact signed repricing of the preserved lazy universe; no native solve."""
import csv,json
from fractions import Fraction as Q
from collections import Counter,defaultdict
from .common import *

def main():
    from v42_pr134_adaptive.common import load
    OUT.mkdir(parents=True,exist_ok=True);CASE.mkdir(parents=True,exist_ok=True)
    data=load(DAY);jobs=data[1];classes=data[7]['classes']
    current=read(START/'SELECTED_DOMAIN_INPUT.json');assert len(current)==38 and len({x['class_id'] for x in current})==26
    preserved=[record(p) for p in sorted((ROOT/'docs/v42_b1_adaptive_prescreening_rescue_20261007').rglob('*')) if p.is_file()]
    preserved += [record(p) for p in sorted(START.rglob('*')) if p.is_file()]
    write('PR165_PRESERVATION_BEFORE.json',dict(base=BASE,files=preserved))
    support=read(SUPPORT/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json')
    independent=read(SUPPORT/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json');assert support['PASS'] and independent['PASS']
    coefficients={(x['site'],int(x['slot'])):Q(x['coefficient']) for x in support['known_coefficients']}
    # Current S38 may have already broken the old support contradiction. Its
    # signed rows remain valid ranking authority, never an S38 infeasibility claim.
    minima={k:Q(v['exact_minimum_per_job']) for k,v in support['all_class_minima'].items()}
    def cost(key,parts):
        j=jobs[classes[key][0]]
        return j.gpu*sum((w for (site,t),w in coefficients.items() for s,lo,hi in parts if s==site and lo<=t<hi),Q(0))
    for x in current:
        key=x['class_id'];minima[key]=min(minima[key],cost(key,json.loads(x['segments'])))
    selected_ids={x['option_id'] for x in current};affected={x['class_id'] for x in current}
    counts=Counter();candidates=defaultdict(list)
    with POOL.open(encoding='utf8',newline='') as f:
        for row in csv.DictReader(f):
            counts['all_lossless_records_read']+=1
            if row['class_id'] not in affected or row['option_id'] in selected_ids:continue
            # Original S0 effect must be useful or neutral, not merely visual load.
            if row['classification'] not in ('CERTIFICATE_BREAKING','CERTIFICATE_NEUTRAL'):continue
            key=row['class_id'];j=jobs[classes[key][0]];cp=int(row['checkpoint'])
            kind='MIGRATION' if cp>=0 else 'SAME_SITE' if row['site']==j.reference_site else 'PRESTART_SITE'
            parts=json.loads(row['segments']);signed=cost(key,parts)
            gain=max(Q(0),minima[key]-signed)*len(classes[key])
            row=dict(row,kind=kind,current_support_signed_cost_exact=str(signed),current_support_gain_exact=str(gain),
                     signed_critical_known_load_exact=str(j.gpu*sum((w for (site,t),w in coefficients.items() if t in (25,26) for s,lo,hi in parts if s==site and lo<=t<hi),Q(0))))
            if cp>=0:
                # Retain every lazy member for ranking. A selected migration is
                # one exact transfer path, never an entire block/domain opening.
                taus=json.loads(row['lazy_transfer_starts'])
                row['source_lossless_block_sha']=row['option_id']
                row['available_transfer_starts']=taus
            candidates[kind].append(row);counts[kind]+=int(row['option_multiplicity'])
    def ranking(x):
        return (int(x['abs_delta_start']),-Q(x['current_support_gain_exact']),int(x['delta_start'])>0,
                x['class_id'],x['site'],int(x['start']),x['option_id'])
    for kind in candidates:candidates[kind].sort(key=ranking)
    # S_A/B retain all S38 options and grow only these affected classes.
    domain=list(current);shells=[];used=set(selected_ids)
    for spec in SHELLS:
        available=[x for x in candidates[spec['kind']] if x['option_id'] not in used]
        added=available[:spec['batch']]
        if spec['kind']=='MIGRATION':
            from v42_boundary.generator import Generator
            from v42_job_capability import Option,checkpoint_records
            from dataclasses import asdict
            gen=Generator(data[3],max(b.latest_completion for b in data[2].values()))
            exact=[]
            for row in added:
                row=dict(row);j=jobs[classes[row['class_id']][0]];cp=int(row['checkpoint']);tau=int(row['available_transfer_starts'][0]);tr=gen.transfer(row['site'],row['destination'],j.gpu,tau)
                parts=((row['site'],int(row['start']),cp),(row['destination'],tr.restart,tr.restart+j.service_slots-(cp-int(row['start']))))
                physical=dict(checkpoint_records(j,int(row['start']),min(int(row['start'])+j.service_slots,data[3].control_end)))[cp]
                option=Option(int(row['start']),row['site'],parts,cp,physical,row['destination'],tau,tr.end,tr.restart,tr.wan)
                row.update(transfer_start=tau,transfer_end=tr.end,restart_end=tr.restart,segments=json.dumps(parts,separators=(',',':')),wan=tr.wan,
                           physical_checkpoint_seconds=option.physical_checkpoint_seconds,option_multiplicity=1,lazy_transfer_starts='[]',
                           option_id=digest(dict(class_id=row['class_id'],exact_option=asdict(option))))
                exact.append(row)
            added=exact
        used.update(x.get('source_lossless_block_sha',x['option_id']) for x in added);domain=domain+added
        atomic(CASE/(spec['name']+'_DOMAIN.json'),domain)
        shells.append(dict(spec,added_actual=len(added),total_restored_options=len(domain),expanded_classes=len({x['class_id'] for x in domain}),
                           selected_domain=record(CASE/(spec['name']+'_DOMAIN.json')),status='PREREGISTERED_NOT_EXECUTED'))
    write('MAY19_SHELLS.json',dict(starting_options=38,starting_classes=26,shells=shells,global_minimality_claimed=False,
                                 tie=['same-site/shell authority','absolute displacement','descending exact useful support gain','earlier before later','class ID','site','start','UID']))
    rows=[x for kind in ('SAME_SITE','PRESTART_SITE','MIGRATION') for x in candidates[kind]]
    fields=['kind','class_id','option_id','site','start','abs_delta_start','classification','certificate_delta_exact',
            'current_support_signed_cost_exact','current_support_gain_exact','signed_critical_known_load_exact','option_multiplicity']
    table(OUT/'MAY19_CANDIDATE_RANKING.csv',rows,fields)
    write('MAY19_BASE_IDENTITY.json',dict(base=BASE,scientific_base='52ef855a59144a7c561df44b81dc2ad265babdbd',
          original_scientific_sha=read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json')['scientific_SHA'],
          input=record(PRODUCTION/'inputs'/DAY/'NATIVE_INPUT.json'),data=record(Path('C:/v42_b1_may17_may19_repair_20261007')/DAY/'DATA.pkl'),
          S38_domain=record(START/'SELECTED_DOMAIN_INPUT.json'),S38_matrix=record(START/'EXPANDED_MATRIX.npz'),S38_result=read(START/'RESULT.json'),
          support_authority=record(SUPPORT/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json'),pool=record(POOL),affected_classes=sorted(affected),
          ranked_counts=dict(counts),S38_infeasibility_claimed=False,no_native_calls=True,LP_SETTINGS=LP_SETTINGS,MIP_SETTINGS=MIP_SETTINGS))
    print('RANKING_PREREGISTERED',dict(counts),[(x['name'],x['total_restored_options']) for x in shells],flush=True)
if __name__=='__main__':main()
