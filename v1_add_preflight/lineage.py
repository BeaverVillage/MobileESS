"""Recursively verify source receipts reachable from frozen May01 authorities.

Only explicit references are followed; no directory crawl, source mutation,
campaign entrypoint, AC, or optimizer is used. Other dates in the seven-day
manifest are not substituted into the May01 operating input.
"""
from collections import deque,Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import psutil
import pickle
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record
sys.path.insert(0,str(ROOT))


def main():
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    from v44.inputs import resolve_receipt
    manifest=ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json'
    day=next(r for r in read(manifest)['days'] if r['day']=='2025-05-01')
    assert day['axis']['prefix_slots']==24 and day['axis']['evaluation_slots']==96
    seeds=[(str(manifest),'$May01_only',day)]
    for name in ['v44/inputs.py','v44/daily.py','v44/worker.py','v44/planning.py','v44/svr12.py',
                 'v44/svr11_ac.py','v43_actual/current_ac.py','v43_actual/case.py','v43_actual/observations.py']:
        seeds.append(('frozen_commit_source','$'+name,record(ROOT/name)))
    # Historical readback evidence and pure C1/job replay receipts are inputs to
    # this audit, not Greensboro electrical results.
    seeds.append((str(RUN/'jobs/REPLAY_RECEIPT.json'),'$',read(RUN/'jobs/REPLAY_RECEIPT.json')))
    seeds.append((str(DOC/'IEEE123_INPUT_AUTHORITY_AUDIT.json'),'$',read(DOC/'IEEE123_INPUT_AUTHORITY_AUDIT.json')))
    queue=deque(seeds);visited=set();contents=set();rows=[];missing=[];parsed=0;start=time.monotonic();cache={};boundaries=[]
    def scoped_json(path):
        dates=set(re.findall(r'20\d\d-\d\d-\d\d',Path(path).as_posix()))
        if dates and not dates.intersection({'2025-05-01','2025-04-30'}):
            boundaries.append(dict(path=str(path),status='REFERENCED_FILE_SHA_CHECKED_OTHER_DATE_PATH',dates=sorted(dates)))
            return None
        value=read(path)
        if isinstance(value,dict):
            dayvalue=value.get('day',value.get('operating_day'))
            if isinstance(dayvalue,str) and re.fullmatch(r'20\d\d-\d\d-\d\d',dayvalue) and dayvalue!='2025-05-01':
                boundaries.append(dict(path=str(path),status='REFERENCED_FILE_SHA_CHECKED_NOT_MAY01_OPERATING_INPUT',day=dayvalue))
                return None
            for key in ('days','day_sources','cases'):
                if key in value and isinstance(value[key],list) and any(isinstance(r,dict) and 'day' in r for r in value[key]):
                    excluded=[r.get('day') for r in value[key] if isinstance(r,dict) and 'day' in r and r['day']!='2025-05-01']
                    value=dict(value);value[key]=[r for r in value[key] if not isinstance(r,dict) or 'day' not in r or r['day']=='2025-05-01']
                    if excluded:boundaries.append(dict(path=str(path),field=key,other_days_excluded=sorted(set(excluded))))
        return value
    content_roots=[ROOT,Path('D:/MobileESS_V42'),Path('D:/MobileESS_V43'),Path('D:/MobileESS_V44')]
    content_roots += [Path('D:/codex_mobileess_workspace')/n for n in
        ('MobileESS_v41r3_scale_rebalance','MobileESS_v41r2_780gpu_capacity_rebase','MobileESS_v40a_bounded_iterative_coopt')]
    content_roots += [Path('D:/ChatGPT/Mobile ESS 2')/n for n in
        ('ieee123_per_mess_pr','pr_workspaces/ieee8500_may01_mess6','v41r4_final_results_pr','v41r4_alpha_screen_pr')]
    observed_files={}
    def resolve(value,parent=None):
        key=(value['path'],value['sha256'],value.get('bytes'))
        original=Path(value['path'])
        if not original.is_absolute():key=(*key,parent)
        if key in cache:
            result=cache[key]
            if isinstance(result,Exception):raise result
            return result
        try:
            # Only byte-identical, SHA-checked relocations are accepted.
            try:result=resolve_receipt(value) if 'bytes' in value else None
            except Exception:result=None
            if result is None:
                text=Path(value['path']).as_posix();candidates=[Path(text)]
                if text.startswith('C:/codex_mobileess_workspace/'):
                    candidates.append(Path('D:/codex_mobileess_workspace/'+text.split('C:/codex_mobileess_workspace/',1)[1]))
                if text.startswith('/home/jaewon/'):
                    candidates.append(Path('//wsl.localhost/Ubuntu-MobileESS-D'+text))
                if text.startswith('/mnt/c/'):
                    candidates.append(Path('C:/'+text[len('/mnt/c/'):]))
                if not original.is_absolute():
                    if parent and Path(parent).is_file():
                        candidates.extend(p/original for p in list(Path(parent).parents)[:-1])
                    candidates.extend(p/original for p in content_roots)
                for marker in ('dayahead/','docs/','tests/'):
                    if marker in text:
                        suffix=text[text.index(marker):]
                        candidates.extend(p/suffix for p in content_roots)
                        break
                parts=[s for s in text.split('/') if s]
                for i,part in enumerate(parts):
                    if part=='docs' or part=='v44' or part.startswith(('v42_','v43_')):
                        suffix=Path(*parts[i:])
                        for root in (ROOT,Path('D:/MobileESS_V42'),Path('D:/MobileESS_V43'),Path('D:/MobileESS_V44')):
                            candidates.append(root/suffix)
                        break
                for p in candidates:
                    if p.is_file() and ('bytes' not in value or p.stat().st_size==value['bytes']):
                        filekey=str(p.resolve()).lower()
                        if filekey not in observed_files:observed_files[filekey]=record(p)
                        rr=observed_files[filekey]
                        if rr['sha256']==value['sha256']:result=rr;break
            if result is None:raise FileNotFoundError('No byte-identical SHA-verified source or known relocation')
            cache[key]=result;return result
        except Exception as error:
            cache[key]=error;raise
    def inspect_value(source,field,value):
        if isinstance(value,dict):
            if 'path' in value and re.fullmatch('[0-9a-fA-F]{64}',str(value.get('sha256',''))):
                expected=value['sha256'].lower();p=Path(value['path']);edge=dict(parent=source,field=field,
                    original_path=str(p),expected_sha256=expected,expected_bytes=value.get('bytes'))
                try:
                    rr=resolve(value,source)
                    edge.update(resolved_path=rr['path'],actual_sha256=rr['sha256'],actual_bytes=rr['bytes'],status='PASS')
                    key=str(Path(rr['path']).resolve()).lower()
                    if key not in visited:
                        visited.add(key)
                        if Path(rr['path']).suffix.lower()=='.json' and expected not in contents:
                            contents.add(expected)
                            try:
                                queue.append((rr['path'],'$',None))
                            except (ValueError,UnicodeError) as e:edge['parse_note']=str(e)
                except Exception as e:
                    edge.update(resolved_path='',actual_sha256='',actual_bytes='',status='NOT_VERIFIED',reason=type(e).__name__+':'+str(e)[:300]);missing.append(edge)
                rows.append(edge)
                # Receipt metadata is still inspected for nested authorities.
            for k,v in value.items():inspect_value(source,field+'.'+str(k),v)
        elif isinstance(value,list):
            for i,v in enumerate(value):inspect_value(source,field+'['+str(i)+']',v)
    def stream_receipts(path):
        sys.path.insert(0,str(RUN/'audit_dependencies'))
        import ijson
        stack=[]
        with Path(path).open('rb') as f:
            if f.read(3)!=b'\xef\xbb\xbf':f.seek(0)
            for prefix,event,value in ijson.parse(f):
                if event=='start_map':stack.append(dict(prefix=prefix,fields={},key=None))
                elif event=='map_key':stack[-1]['key']=value
                elif event in ('string','number','boolean','null') and stack:
                    name=stack[-1]['key']
                    if name in ('path','sha256','bytes'):stack[-1]['fields'][name]=value
                    if prefix in ('day','operating_day') and isinstance(value,str) and re.fullmatch(r'20\d\d-\d\d-\d\d',value) and value!='2025-05-01':
                        boundaries.append(dict(path=str(path),status='OTHER_DATED_REFERENCED_ARTIFACT',day=value));return
                elif event=='end_map':
                    item=stack.pop();d=item['fields']
                    if 'path' in d and 'sha256' in d:inspect_value(str(path),'$.'+item['prefix'],d)
    checkpoint=RUN/'LINEAGE_CHECKPOINT.pkl'
    if checkpoint.exists():
        restored=pickle.loads(checkpoint.read_bytes())
        queue,visited,contents,rows,missing,parsed,cache,boundaries=restored
        print('resume',parsed,'documents; queued',len(queue),flush=True)
        # Earlier failed bare receipts may use doubled Windows separators.
        # Recheck all unresolved receipts against normalized, SHA-checked aliases.
        retried={};remaining=[]
        for edge in missing:
            v=dict(path=edge['original_path'],sha256=edge['expected_sha256'])
            if edge.get('expected_bytes') is not None:v['bytes']=edge['expected_bytes']
            key=(v['path'],v['sha256'],v.get('bytes'))
            if key not in retried:
                if isinstance(cache.get(key),Exception):cache.pop(key,None)
                try:retried[key]=resolve(v,edge['parent'])
                except Exception:retried[key]=None
            rr=retried[key]
            if rr:
                edge.update(resolved_path=rr['path'],actual_sha256=rr['sha256'],actual_bytes=rr['bytes'],status='PASS')
                edge.pop('reason',None)
                k=str(Path(rr['path']).resolve()).lower()
                if k not in visited:
                    visited.add(k)
                    if Path(rr['path']).suffix.lower()=='.json' and v['sha256'] not in contents:
                        contents.add(v['sha256']);queue.append((rr['path'],'$',None))
            else:remaining.append(edge)
        missing=remaining
        print('normalized relocation recheck: remaining edges',len(missing),flush=True)
    def seal_checkpoint():
        checkpoint.write_bytes(pickle.dumps((queue,visited,contents,rows,missing,parsed,cache,boundaries),protocol=5))
    while queue:
        if psutil.virtual_memory().available<4_000_000_000:
            (RUN/'LINEAGE_RESOURCE_STOP.json').write_text(json.dumps(dict(queued=len(queue),documents=parsed,reason='Protect production free memory')))
            seal_checkpoint();raise RuntimeError('RESOURCE_PROTECTION: no further ancestry expansion')
        parent,field,value=queue.popleft()
        try:
            if value is None:
                if Path(parent).stat().st_size>8*1024*1024:stream_receipts(parent)
                else:
                    value=scoped_json(parent)
                    if value is not None:inspect_value(parent,field,value)
            else:inspect_value(parent,field,value)
        except (ValueError,UnicodeError) as error:
            boundaries.append(dict(path=parent,status='JSON_DESCENDANTS_NOT_VERIFIED',reason=str(error)[:300]))
        parsed+=1
        if parsed%50==0:
            print('lineage JSON',parsed,'queued',len(queue),'edges',len(rows),'unverified',len(missing),flush=True)
            (RUN/'LINEAGE_PROGRESS.json').write_text(json.dumps(dict(documents=parsed,queued=len(queue),edges=len(rows),unverified=len(missing))))
            seal_checkpoint()
    csvout('SOURCE_LINEAGE_RECURSIVE.csv',rows,
        ['parent','field','original_path','expected_sha256','expected_bytes','resolved_path','actual_sha256','actual_bytes','status','reason','parse_note'])
    save('SOURCE_LINEAGE_RECURSIVE.json',dict(schema='V44_R043_MAY01_RECURSIVE_RECEIPT_AUDIT_V1',
        pinned_commit='affc7226a519adbe072d7debbc3ae25ea71c3487',
        status='PASS' if not missing else 'NOT_VERIFIED',edges=len(rows),
        verified=sum(r['status']=='PASS' for r in rows),unverified=len(missing),
        unique_verified_paths=len(visited),JSON_documents_processed=parsed,
        May01_scope_boundaries=boundaries,
        manifest=record(manifest),axis=day['axis'],unverified_receipts=missing,
        other_dates_not_substituted=True,AC_calls=0,optimizer_calls=0,wall_seconds=time.monotonic()-start,
        limitation='Explicit path+sha256 recursion over May01 execution inputs and shared static authorities. Other dated study documents are SHA-checked as referenced artifacts, not recursively promoted to May01 operating inputs. Bare paths, semantic digests and archive member IDs are handled separately; no claim that a bare path is SHA-certified.'))
    print('complete',parsed,'documents',len(rows),'edges',len(missing),'unverified',flush=True)


if __name__=='__main__':main()
