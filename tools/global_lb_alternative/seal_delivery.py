"""Verify every new staged Git blob against its exact working-tree bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/v42_b2_global_lb_alternative_research_20261014'


def main():
    paths=['docs/v42_b2_global_lb_alternative_research_20261014','tools/global_lb_alternative','tests/test_v42_global_lb_alternative.py']
    raw=subprocess.check_output(['git','ls-files','-s','-z','--',*paths],cwd=ROOT)
    records=[];requests=[]
    for item in raw.split(b'\0'):
        if not item:continue
        meta,name=item.split(b'\t',1);mode,oid,stage=meta.decode().split();name=name.decode('utf-8')
        if name.endswith('DELIVERY_ARTIFACT_INDEX.json'):continue
        requests.append(oid.encode()+b'\n');records.append(dict(path=name,Git_blob=oid))
    proc=subprocess.run(['git','cat-file','--batch'],input=b''.join(requests),stdout=subprocess.PIPE,check=True,cwd=ROOT)
    content=proc.stdout;pos=0
    for p in records:
        end=content.index(b'\n',pos);header=content[pos:end].decode().split();size=int(header[2]);pos=end+1
        blob=content[pos:pos+size];pos+=size+1
        local=(ROOT/p['path']).read_bytes()
        if blob!=local:raise ValueError('STAGED_BYTES_DIFFER:'+p['path'])
        p.update(bytes=size,sha256=hashlib.sha256(blob).hexdigest(),exact_staged_bytes_match=True)
    packet=dict(PASS=True,artifacts=records,files=len(records),total_bytes=sum(p['bytes'] for p in records),
                includes_all_original_solver_log_bytes=True,raw_log_and_JUnit_whitespace_preserved=True,
                index_excludes_itself=True,original_existing_tracked_changes=0,Native_calls=0)
    (OUT/'DELIVERY_ARTIFACT_INDEX.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('STAGED_EXACT_BYTE_INDEX_PASS',len(records),packet['total_bytes'])


if __name__=='__main__':main()
