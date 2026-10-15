"""Preserve exact previous execution sources before an explicit repair."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest

def capture(output,name):
    freeze=output/'EXECUTION_SOURCE_FREEZE.json';old=json.loads(freeze.read_text(encoding='utf8'))
    target=output/'SOURCE_REVISIONS'/name
    if target.exists():raise FileExistsError('APPEND_ONLY_SOURCE_REVISION')
    target.mkdir(parents=True)
    (target/'PARENT_EXECUTION_SOURCE_FREEZE.json').write_bytes(freeze.read_bytes())
    rows=[]
    for i,record in enumerate(old['files']):
        if file_record(record['path'])!=record:raise ValueError('PRE_REPAIR_SOURCE_DRIFT')
        p=target/(str(i).zfill(2)+'_'+Path(record['path']).name)
        p.write_bytes(Path(record['path']).read_bytes())
        copy=file_record(p)
        if (copy['sha256'],copy['bytes'])!=(record['sha256'],record['bytes']):raise ValueError('SNAPSHOT_NOT_LOSSLESS')
        rows.append(dict(original=record,snapshot=copy))
    _write(target/'SOURCE_PRESERVATION.json',dict(exact_previous_sources=rows,
        prior_freeze=file_record(target/'PARENT_EXECUTION_SOURCE_FREEZE.json'),Native_budget_reset=False))

def seal(output,name,reason):
    target=output/'SOURCE_REVISIONS'/name
    if (target/'REVISED_EXECUTION_SOURCE_FREEZE.json').exists():raise FileExistsError('ALREADY_SEALED')
    receipt=json.loads((target/'SOURCE_PRESERVATION.json').read_text(encoding='utf8'))
    if any(file_record(r['snapshot']['path'])!=r['snapshot'] for r in receipt['exact_previous_sources']):
        raise ValueError('PREVIOUS_SOURCE_SNAPSHOT_DRIFT')
    old=json.loads((target/'PARENT_EXECUTION_SOURCE_FREEZE.json').read_text(encoding='utf8'))
    files=[file_record(r['path']) for r in old['files']]
    new=dict(files=files,source_sha=digest(files),previous_source_preservation=file_record(target/'SOURCE_PRESERVATION.json'),
        reason=reason,Native_budget_reset=False,old_attempts_and_Raw_preserved=True)
    _write(target/'REVISED_EXECUTION_SOURCE_FREEZE.json',new)
    _write(output/'EXECUTION_SOURCE_FREEZE.json',new)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['capture','seal'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--revision',required=True);p.add_argument('--reason',default='')
    a=p.parse_args()
    (capture(a.output,a.revision) if a.operation=='capture' else seal(a.output,a.revision,a.reason))
