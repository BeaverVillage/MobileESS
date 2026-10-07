"""Read-only complete-date audit. Git head alone never rejects a result."""
from .common import *

def run(root):
    expected=read(root/'MAY31_INPUT_IDENTITY.json');by={r['day']:r for r in expected['days']};cases=[];summary=[]
    runs=sorted(Path('C:/v42_b1_runs').glob('*/CHECKPOINT.json'))
    for cp in runs:
        try:
            checkpoint=read(cp);stages=checkpoint['stages'];source_freeze=read(cp.parent/'B1_PRODUCTION_FREEZE_MANIFEST.json')
        except (OSError,KeyError,ValueError):continue
        for day in DAYS:
            entries=[stages.get(day+'/'+s) or stages.get(day+'/'+('VALIDATION_FREEZE' if s=='VALIDATION' else s)) for s in STAGES]
            if not any(entries):continue
            row=dict(day=day,source_run=source_freeze.get('run_id'),root=str(cp.parent),complete=False,identities=False,payloads=False,
                input_match=False,classification='RERUN_REQUIRED',reason='NO_COMPLETE_FIVE_STAGE_PASS')
            if not all(r and r.get('status')=='PASS' for r in entries):cases.append(row);continue
            row['complete']=True;receipts=[]
            try:
                for entry in entries:
                    path=entry['receipt']
                    if sha(path)!=entry['sha256']:raise ValueError('RECEIPT_SHA')
                    receipt=read(path)
                    if not receipt.get('PASS') or not receipt.get('files'):raise ValueError('NOT_PASS_OR_OUTPUT_EMPTY')
                    if any(sha(f['path'])!=f['sha256'] for f in receipt['files']):raise ValueError('PAYLOAD_SHA')
                    receipts.append(receipt)
                row['payloads']=True
                input_sha=source_freeze['day_input_SHA'][day]
                row.update(original_input_SHA=input_sha,original_scientific_SHA=source_freeze.get('scientific_SHA'),original_Git_SHA=source_freeze.get('Git_SHA'),
                    expected_input_SHA=by[day].get('bundle',{}).get('sha256'))
                row['input_match']=by[day]['PASS'] and input_sha==by[day]['bundle']['sha256']
                if not row['input_match']:
                    row.update(classification='INCOMPATIBLE',reason='INPUT_SHA_DIFFERS_OR_EXPECTED_AUTHORITY_UNAVAILABLE')
                    original_input=cp.parent/'inputs'/day/'NATIVE_INPUT.json'
                    if original_input.is_file() and by[day]['PASS']:
                        old=read(original_input);new=read(root/'inputs'/day/'NATIVE_INPUT.json')
                        oldjobs={j['job_uid']:j for j in old['known_population']};newjobs={j['job_uid']:j for j in new['known_population']}
                        row['reference_start_differences']=sum(oldjobs[u].get('reference_start_if_authorized')!=newjobs[u].get('reference_start_if_authorized') for u in oldjobs.keys()&newjobs.keys())
                        row['timeshift_flag_differences']=sum(oldjobs[u].get('can_timeshift')!=newjobs[u].get('can_timeshift') for u in oldjobs.keys()&newjobs.keys())
                        row['job_membership_difference']=len(oldjobs.keys()^newjobs.keys())
                else:
                    # Same bytes still require a separately frozen source/model/
                    # objective/validation equivalence receipt. Never infer one
                    # from a numerical operating point or matching core filenames.
                    equivalence=cp.parent/'PR134_SCIENTIFIC_EQUIVALENCE.json'
                    if equivalence.is_file():
                        e=read(equivalence)
                        if e.get('PASS') and e.get('base')==BASE and e.get('scientific_SHA')==source_freeze.get('scientific_SHA') and e.get('input_SHA')==input_sha:
                            row.update(identities=True,classification='REUSED',reason='COMPLETE_FIVE_STAGE_PAYLOAD_AND_SOURCE_INPUT_OBJECTIVE_CHECKER_EQUIVALENCE')
                            row['receipts']=[record(r['receipt']) for r in entries]
                    if not row['identities']:row['reason']='SOURCE_MODEL_OBJECTIVE_VALIDATION_EQUIVALENCE_NOT_PROVEN'
            except Exception as error:row.update(classification='INCOMPATIBLE',reason=str(error))
            cases.append(row)
    atomic(root/'ALL_EXISTING_DATE_REUSE_CASES.json',dict(read_only=True,campaign_checkpoints_examined=len(runs),cases=cases))
    for day in DAYS:
        matches=[r for r in cases if r['day']==day];valid=[r for r in matches if r['classification']=='REUSED']
        state='REUSED' if valid else 'INCOMPATIBLE' if any(r['classification']=='INCOMPATIBLE' for r in matches) else 'RERUN_REQUIRED' if matches else 'MISSING'
        summary.append(dict(day=day,classification=state,existing_runs=len(matches),complete_PASS_cases=sum(r['complete'] for r in matches),
            new_input_ready=by[day]['PASS'],source_run=valid[0]['source_run'] if valid else '',
            reason='COMPLETE_EXACT_COMPATIBLE' if valid else 'NO_COMPLETE_EXACT_COMPATIBLE_CHECKPOINT',input_SHA=by[day].get('bundle',{}).get('sha256','')))
    table(root/'DATE_REUSE_AUDIT.csv',summary,list(summary[0]))
    atomic(root/'REUSE_IMPORT_PLAN.json',dict(days=summary,reuse=[r for r in cases if r['classification']=='REUSED'],partial_days_reused=0,
        old_partial_point_incumbent_bound_warmstart_native_clock_used=False,head_SHA_only_rejection=False))
    print('EXISTING_MAY_REUSE_AUDIT',len(runs),'checkpoints',sum(r['classification']=='REUSED' for r in summary),'reusable dates',flush=True)
    return summary

if __name__=='__main__':
    import sys
    run(Path(sys.argv[1]))
