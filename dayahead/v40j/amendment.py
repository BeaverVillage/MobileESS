"""Machine evidence for user-requested amendment, before selection is unlocked."""
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
from pathlib import Path
from .contracts import ROOT, OUT, LEGACY_CACHE, SPLIT
from .data import read_frame, train_mask, block_mask
from .timestamp_firewall import *
from .firewall import sha, write

TRANSCRIPT=Path('C:/Users/kjw39/.codex/sessions/2026/09/06/rollout-2026-09-06T18-21-31-01a07605-e140-78b1-ac9f-32ceec989c7a.jsonl')

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def histories():
    current={}; versions=[]; test_discovery=None
    for raw in TRANSCRIPT.read_text(encoding='utf-8').splitlines():
        d=json.loads(raw)
        if '2 failed, 48 passed' in raw and test_discovery is None:
            test_discovery=d.get('timestamp')
        p=d.get('payload',{})
        if d.get('type')!='response_item' or p.get('type')!='custom_tool_call' or p.get('name')!='exec':continue
        code=p.get('input','')
        for m in re.finditer(r'tools\.apply_patch\(("(?:\\.|[^"\\])*")\)',code,re.S):
            patch=json.loads(m.group(1))
            lines=patch.splitlines();i=0
            while i<len(lines):
                line=lines[i]
                if not line.startswith(('*** Add File: ','*** Update File: ')):
                    i+=1;continue
                mode,path=line.split(': ',1);i+=1
                segment=[]
                while i<len(lines) and not lines[i].startswith('*** '):segment.append(lines[i]);i+=1
                if not path.endswith(('/dayahead/v40j/methods.py','/dayahead/v40j/evaluate.py')):continue
                before=current.get(path,'')
                if mode=='*** Add File':
                    after='\n'.join(s[1:] for s in segment if s.startswith('+'))+'\n'
                else:
                    after=before
                    blocks=[];block=[]
                    for s in segment+['@@']:
                        if s.startswith('@@'):
                            if block:blocks.append(block)
                            block=[]
                        else:block.append(s)
                    for b in blocks:
                        old='\n'.join(s[1:] for s in b if s.startswith((' ','-')))+'\n'
                        new='\n'.join(s[1:] for s in b if s.startswith((' ','+')))+'\n'
                        if old not in after:raise ValueError('TRANSCRIPT_PATCH_REPLAY_MISMATCH:'+path)
                        after=after.replace(old,new,1)
                current[path]=after
                versions.append({'timestamp':d['timestamp'],'path':path,'before':before,'after':after,
                   'source_sha_before':digest(before),'source_sha_after':digest(after),
                   'patch_sha256':digest(patch),'call_id':p.get('call_id')})
    for path,body in current.items():
        assert sha(path)==digest(body),'REPLAY_NOT_IDENTICAL_TO_CURRENT_SOURCE:'+path
    a=next(v for v in versions if 'if not columns:' not in v['before'] and 'if not columns:' in v['after'])
    b=next(v for v in versions if 'value=safety_metrics(y[m],row.safe.to_numpy()[m]' in v['before'] and 'value=safety_metrics(y[m],row.upper90.to_numpy()[m]' in v['after'])
    return a,b,test_discovery,current

def main():
    if subprocess.check_output(['git','ls-tree','HEAD','--','dayahead/artifacts/v40j_runtime_redesign/V40J_PREREGISTRATION_AMENDMENT_01.json'],cwd=ROOT):
        raise RuntimeError('AMENDMENT_ALREADY_COMMITTED_IMMUTABLE')
    selection_files=['V40J_SELECTION_FREEZE.json','V40J_POINT_MODEL_COMPARISON.json',
                     'V40J_CONDITIONAL_CALIBRATION_REPORT.json','V40J_RUNTIME_METHOD_FREEZE.json']
    existence={n:(OUT/n).exists() for n in selection_files}
    assert not any(existence.values()),'SELECTION_OR_AGGREGATE_ALREADY_EXISTS'
    a,b,discovered,current=histories()
    evidence=OUT/'amendment_evidence';evidence.mkdir(exist_ok=True)
    changes=[]
    for name,v,original,problem,corrected,impact in [
      ('A',a,'Hierarchy level 4 is a pooled fallback for every query.','Empty-column pandas tuple iteration omitted pooled keys.',
       'Explicitly generate one empty tuple for every row when grouping columns are empty.','Repairs previously invalid pooled calibration. No threshold, candidate or split change.'),
      ('B',b,'Target coverage 90%; point, upper-tail calibration and robust reserve are separate layers.',
       'Early evaluator incorrectly used the selected grid reserve envelope for the coverage gate, allowing Q95 to conceal Q90 failure.',
       'Gate on native conditional Q90 itself; R3/Q95 is evaluated separately for GPU miss and conservatism.',
       'Makes acceptance stricter and restores registered layer separation. No candidate ranking had been emitted or viewed.')]:
        stem=Path(v['path']).name
        for which in ['before','after']:
            (evidence/f'{name}_{which}_{stem}').write_text(v[which],encoding='utf-8',newline='\n')
        changes.append({'id':name,'original_preregistered_rule':original,'problem_found':problem,
           'corrected_rule':corrected,'discovery_timestamp':discovered if name=='A' else v['timestamp'],
           'discovery_timestamp_basis':'first failing automated test output' if name=='A' else 'first recorded corrective tool call; earlier mental discovery time is not asserted',
           'correction_tool_timestamp':v['timestamp'],'candidate_ranking_observed_before_change':False,
           'candidate_metric_outcomes_observed_before_change':False,'baseline_reproduction_metrics_observed':True,
           'final_shadow_opened':False,'scientific_impact':impact,'affected_source_files':[v['path']],
           'source_SHA_before':v['source_sha_before'],'source_SHA_after':v['source_sha_after'],
           'patch_sha256':v['patch_sha256'],'recorded_tool_call_id':v['call_id'],
           'source_snapshot_provenance':'Exact tool patch history replayed from the local task transcript; replay of all later patches matches current file SHA.'})
    f=read_frame(OUT/'DEVELOPMENT_GPU_ROWS.parquet')
    census=timestamp_summary(f)
    split_checks={}
    original=read_frame(LEGACY_CACHE/'kestrel_preissue_normalized.parquet')
    old_counts=json.loads((OUT/'V40J_PREMAY_RUNTIME_ROW_CENSUS.json').read_text())['split_counts']
    for fold in SPLIT['folds']:
        training=f.loc[train_mask(f,fold['fit_before'])]
        assert_historical_population(training,fold['fit_before'])
        counts={'train':len(training),'calibration':int(block_mask(f,fold['calibration'],fold['validation'][0]).sum()),
                'validation':int(block_mask(f,fold['validation'],SPLIT['validation_label_deadline']).sum())}
        assert counts==old_counts[fold['id']],'NEW_TIMESTAMP_GUARD_CHANGES_TRAINED_POPULATION'
        t=pd.Timestamp(fold['fit_before'],tz='UTC')
        c0=original.loc[(original.end_time<t)&(original.end_time>=t-pd.Timedelta(days=120))&(original.submit_time<t)&original.runtime_seconds.notna()]
        assert_historical_population(c0,t)
        split_checks[fold['id']]={'counts':counts,'unchanged_from_training':True,
          'max_training_end':str(training.end_time.max()),'prediction_and_support_freeze_time':str(t),
          'C0_training_rows':len(c0),'end_time_known_before_prediction_and_support':True}
    raw=json.loads((OUT/'V40J_RAW_RUNTIME_FOOTER_CENSUS.json').read_text())
    timestamp={'canonical_timezone':CANONICAL_TIMEZONE,'local_cutoff':LOCAL_CUTOFF,'UTC_cutoff':UTC_CUTOFF,
       'fixed_AEST_equivalent':FIXED_AEST_EQUIVALENT,
       'boundary_reason':'Retain UTC calendar in immutable preregistered split. User AEST boundary was an example, not a replacement instruction.',
       'scanned_partition_count':len(raw['members']),'partition_scan_type':'footer metadata only',
       'row_scan_scope':'all 233999 development GPU rows; April shadow row payload remains locked',
       **census,'all_original_normalized_rows':timestamp_summary(original),
       'future_shadow_post_cutoff_row_count':None,'future_shadow_count_status':'NOT_SCANNED_SHADOW_LOCK',
       'split_checks':split_checks,'future_completion_leakage':False,
       'required_shadow_extraction':'Project/filter submit/end timestamps by UTC cutoff before any runtime/status row is exposed; April partition name alone never authorizes a row.'}
    write('V40J_PREMAY_TIMESTAMP_FIREWALL.json',timestamp,immutable=True)
    counters={'MAY_PATH_OR_CODE_DISCOVERY_READS':{'observed_lower_bound':1,'exact_total':None,'status':'NONZERO_NOT_FULLY_COUNTED',
        'unit':'discovery operations; includes initial rg content search and path inventories, not a falsely exact file count'},
       'MAY_METADATA_ONLY_READS':{'observed_lower_bound':1,'exact_total':None,'status':'NONZERO_NOT_FULLY_COUNTED',
        'unit':'metadata operations; central directory/path inventories and April footer boundary observation'},
       'MAY_RUNTIME_OR_STATUS_ROW_READS':0,'MAY_ACTUAL_OUTCOME_READS':0,'MAY_MODEL_BUILDING_READS':0,
       'MAY_TRAINING_READS':0,'MAY_CALIBRATION_READS':0,'MAY_MODEL_SELECTION_READS':0}
    write('V40J_FIREWALL_COUNTERS.json',{'counters':counters,'May_total_read_count_zero_claim':False,
       'scientific_counter_scope':'direct runtime/status rows, outcome artifacts and inputs used by V40J scientific processes; explicit motivation-only authority documents are separately disclosed',
       'motivation_document_reads':3,'motivation_scope':'V40I_FINAL_FORENSIC_REVIEW.md, V40I_NEXT_REVISION_DECISION.md, V40I_FINAL_FORENSIC_COMMIT_RECEIPT.json; no parameter selection from May outcomes',
       'legacy_tests':'do not reopen May outcome/row fixtures; preserve prior signed 106+80 receipt and verify unchanged protected sources',
       'canonical_boundary':UTC_CUTOFF,'timestamp_firewall':'V40J_PREMAY_TIMESTAMP_FIREWALL.json'},immutable=True)
    previous=OUT/'V40J_PREREGISTRATION_AMENDMENT_01.json'
    created=json.loads(previous.read_text())['created_at'] if previous.exists() else datetime.now(timezone.utc).isoformat()
    write('V40J_PREREGISTRATION_AMENDMENT_01.json',{'amendment_id':'V40J_01','created_at':created,
       'requested_by':'user mid-run integrity amendment','preregistration_commit':'570c653',
       'changes':changes,'candidate_registry_changed':False,'split_contract_changed':False,'target_changed':False,'support_thresholds_changed':False,
       'aggregate_or_selection_artifact_existence_before_amendment':existence,
       'candidate_ranking_observed_before_changes':False,'candidate_training_complete':True,
       'candidate_training_determinism_sha256':sha(OUT/'V40J_TRAINING_DETERMINISM.json'),
       'current_source_patch_replay_verified':True,'current_source_SHA':{p:sha(p) for p in current},
       'final_shadow_runtime_status_rows_read':0,'shadow_payload_ever_opened':False,
       'April_metadata_only_exception':'footer metadata used for range census; not shadow runtime/status row read',
       'timestamp_firewall_sha256':sha(OUT/'V40J_PREMAY_TIMESTAMP_FIREWALL.json'),
       'counter_report_sha256':sha(OUT/'V40J_FIREWALL_COUNTERS.json'),
       'evidence_files':{p.name:sha(p) for p in evidence.iterdir()},
       'ordering_enforcement':'evaluate.check_amendment_commit verifies committed amendment SHA before evaluation and again before winner selection; shadow open requires non-null frozen winner',
       'other_preselection_implementation_repairs':'zero duration grid slots and actual-start grid phase corrections logged in IMPLEMENTATION_REPAIR_LOG.md; microsecond timestamp dtype explicitly converted to nanoseconds before epoch-second division; no outcome-dependent protocol change',
       'draft_refinement_before_first_commit':True})
    print('AMENDMENT_READY',json.dumps(split_checks),flush=True)

if __name__=='__main__':main()
