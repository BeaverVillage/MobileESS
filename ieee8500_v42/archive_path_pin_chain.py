"""Preserve exact pre-correction pins; strengthen verification without reselection."""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from .common import ROOT,REPORT,read,write,receipt,sha
from .correct_path_metadata import fix_references,numeric_signature,static_original_graph

CORRECTION=REPORT/'PATH_METADATA_CORRECTION.json'
HISTORY=REPORT/'path_metadata_history/pre_correction_20261009'
CHAIN=REPORT/'PATH_METADATA_FROZEN_PIN_CHAIN.json'


def store_original(dest,raw,expected):
    if hashlib.sha256(raw).hexdigest()!=expected['sha256'] or len(raw)!=expected['bytes']:
        raise ValueError('EXACT_ORIGINAL_BYTES_RECONSTRUCTION_FAILED:'+str(dest))
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.suffix=='.gz':
        if dest.exists():
            if gzip.decompress(dest.read_bytes())!=raw:raise ValueError('HISTORICAL_ARCHIVE_CHANGED')
        else:
            with dest.open('wb') as stream:
                with gzip.GzipFile(fileobj=stream,filename='',mode='wb',mtime=0) as zipped:zipped.write(raw)
    elif dest.exists():
        if dest.read_bytes()!=raw:raise ValueError('HISTORICAL_ARCHIVE_CHANGED')
    else:dest.write_bytes(raw)
    return dict(original=expected,archive=receipt(dest),decoded_original_SHA256=expected['sha256'],decoded_original_bytes=len(raw))


def archive():
    correction=read(CORRECTION);archives={};before_by_path={}
    for key,r in correction['csv_files'].items():
        current=Path(r['after']['path'])
        if sha(current)!=r['after']['sha256']:raise ValueError('CURRENT_CORRECTED_CSV_SHA_DRIFT')
        if r['true_before']!=0:raise ValueError('BEFORE_BYTE_RECOVERY_REQUIRES_RECORDED_ALL_FALSE_ORIGINAL')
        with current.open(encoding='utf8',newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        for row in rows:row[r['metadata_field']]='False'
        out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n')
        writer.writeheader();writer.writerows(rows);raw=out.getvalue().encode('utf8')
        relative=current.relative_to(REPORT);dest=HISTORY/relative.with_suffix(relative.suffix+'.gz')
        archives[key]=store_original(dest,raw,r['before']);before_by_path[str(current.resolve()).lower()]=r['before']
    for key,old in correction['prior_receipts'].items():
        current=Path(old['path']);value=read(current)
        value.pop('path_metadata_post_correction',None);value.pop('AC_numerics_unchanged_by_metadata_correction',None)
        value=fix_references(value,before_by_path)
        text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
        raw=text.encode('utf8')
        # Original Path.write_text on Windows translated LF to CRLF. Recover
        # whichever literal original encoding matches the already-recorded SHA.
        if hashlib.sha256(raw).hexdigest()!=old['sha256']:raw=text.replace('\n','\r\n').encode('utf8')
        archives[key]=store_original(HISTORY/current.relative_to(REPORT),raw,old)
    selected=REPORT/'joint_selection_v3/score_selection'
    binding=read(selected/'SCORE_INPUT_SHA256.json')
    pinned=str((REPORT/'joint_selection_v3/selection_scores/RECEIPT.json').relative_to(ROOT))
    if archives[pinned]['decoded_original_SHA256']!=binding['root_receipt_sha256']:
        raise ValueError('SELECTION_ORIGINAL_RECEIPT_PIN_NOT_RECOVERED')
    protected=[selected/name for name in ('SCORE_INPUT_SHA256.json','SCORING_PREREGISTRATION.json',
        'GEOMETRY_RESULT.json','SCORE_SELECTION_RESULT.json','JOINT_SERVICE_MAPPING.csv','SELECTED_CONTROLLABILITY_SCORES.csv')]
    protected+=[REPORT/'joint_selection_v3/selection_scores'/name for name in ('PREREGISTRATION.json',
        'CANDIDATE_SELECTION_SCORES.csv','STA_SCORE_MOBILITY_AND_Q.csv')]
    write(CHAIN,dict(status='EXACT_HISTORICAL_SELECTION_PIN_PRESERVED_WITH_TOPOLOGY_ONLY_AMENDMENT',
        correction=receipt(CORRECTION),archives=archives,
        selection_original_root_receipt_SHA256=binding['root_receipt_sha256'],
        current_root_receipt=receipt(REPORT/'joint_selection_v3/selection_scores/RECEIPT.json'),
        selection_mapping_score_method_and_preregistration_unchanged=True,
        original_pins_immutable=True,no_reselection=True,protected_files={str(p.relative_to(ROOT)):receipt(p) for p in protected},
        reconstruction='Exact original all-False path cells recovered; original byte count and SHA matched before-SHA recorded before correction. Original JSON receipts reversed only documented leaf refs and two amendment keys; exact original SHA checked.',
        AC_solves=0,Native_calls=0,full_model_builds=0))
    return verify_chain(ROOT)


def verify_chain(root):
    root=Path(root).resolve();report=root/'docs/ieee8500_v42_single_case'
    chain=read(report/'PATH_METADATA_FROZEN_PIN_CHAIN.json')
    correctionpath=report/'PATH_METADATA_CORRECTION.json'
    if sha(correctionpath)!=chain['correction']['sha256']:raise ValueError('PATH_AMENDMENT_SHA_DRIFT')
    correction=read(correctionpath);paths,_,_,_=static_original_graph()
    for r in chain['archives'].values():
        path=Path(r['archive']['path'])
        if sha(path)!=r['archive']['sha256']:raise ValueError('ORIGINAL_PIN_ARCHIVE_SHA_DRIFT')
        raw=gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=r['decoded_original_SHA256'] or len(raw)!=r['decoded_original_bytes']:
            raise ValueError('ARCHIVED_ORIGINAL_DECODED_BYTES_SHA_DRIFT')
    for key,r in correction['csv_files'].items():
        path=Path(r['after']['path'])
        if sha(path)!=r['after']['sha256']:raise ValueError('CURRENT_TOPOLOGY_AMENDMENT_CSV_CHANGED')
        with path.open(encoding='utf8',newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        if numeric_signature(rows,fields,r['metadata_field'])!=r['all_nonmetadata_strings_SHA256']:
            raise ValueError('NUMERIC_SCORE_INPUT_CHANGED_WITH_METADATA_AMENDMENT')
        if any(row[r['metadata_field']]!=str(row['line'].lower() in paths[row['bus'].split('.')[0].lower()]) for row in rows):
            raise ValueError('CURRENT_AMENDED_SOURCE_PATH_VALUE_INCORRECT')
    selected=report/'joint_selection_v3/score_selection';binding=read(selected/'SCORE_INPUT_SHA256.json')
    key=str((report/'joint_selection_v3/selection_scores/RECEIPT.json').relative_to(root))
    old=chain['archives'][key]
    if old['decoded_original_SHA256']!=binding['root_receipt_sha256']:
        raise ValueError('ORIGINAL_SELECTION_RECEIPT_PIN_MISMATCH')
    current=report/'joint_selection_v3/selection_scores/RECEIPT.json'
    if sha(current)!=chain['current_root_receipt']['sha256']:raise ValueError('CURRENT_ROOT_RECEIPT_CHAIN_CHANGED')
    historic=read(Path(old['archive']['path']))
    updates={str(Path(r['after']['path']).resolve()).lower():r['after'] for r in correction['csv_files'].values()}
    expected=fix_references(historic,updates)
    expected['path_metadata_post_correction']=receipt(correctionpath)
    expected['AC_numerics_unchanged_by_metadata_correction']=True
    if read(current)!=expected:raise ValueError('ROOT_RECEIPT_CHANGED_BEYOND_ALLOWED_TOPOLOGY_AMENDMENT')
    for key,r in chain['protected_files'].items():
        if sha(root/key)!=r['sha256']:raise ValueError('FROZEN_MAPPING_SCORE_METHOD_CHANGED:'+key)
    return dict(status='PASS_EXACT_ORIGINAL_SELECTION_PIN_AND_CURRENT_TOPOLOGY_AMENDMENT',
        historical_root_receipt_SHA256=binding['root_receipt_sha256'],current_root_receipt_SHA256=sha(current),
        original_mapping_scores_and_preregistration_unchanged=True,all_original_archived_bytes_SHA_PASS=True,
        all_current_path_cells_source_correct=True,all_nonmetadata_cells_unchanged=True,
        no_reselection=True,Native_calls=0,AC_solves=0)


if __name__=='__main__':print(archive()['status'])
