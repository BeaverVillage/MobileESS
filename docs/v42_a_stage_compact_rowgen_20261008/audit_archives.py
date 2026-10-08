"""Read-only source-epoch archive audit; never invokes a native solve."""
import hashlib,json,zipfile,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from v42_pr134_b1.common import read,record,atomic
def run():
    results=[]
    for path in sorted(OUT.glob('*SOURCE_FREEZE.json')):
        manifest=read(path);archive=manifest['source_archive'];valid=record(archive['path'])==archive;bad=[]
        with zipfile.ZipFile(archive['path']) as z:
            names=set(z.namelist())
            for i,r in enumerate(manifest['source_files']):
                p=Path(r['path']);key='repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name
                if key not in names:bad.append(dict(source=r['path'],reason='ARCHIVE_ENTRY_MISSING',entry=key));continue
                b=z.read(key)
                if hashlib.sha256(b).hexdigest()!=r['sha256'] or len(b)!=r['bytes']:bad.append(dict(source=r['path'],reason='ARCHIVED_EXECUTED_SOURCE_BYTES_DIFFER'))
        results.append(dict(manifest=record(path),archive=archive,PASS=valid and not bad,source_files=len(manifest['source_files']),failures=bad))
    result=dict(PASS=all(r['PASS'] for r in results),epochs=results,native_solve_calls=0,
        current_files_may_change_after_completed_epochs=True,archived_executed_source_checked_independently=True)
    atomic(OUT/'EXECUTED_SOURCE_ARCHIVE_AUDIT.json',result);print(json.dumps({k:result[k] for k in ('PASS','native_solve_calls')}),len(results))
    return result
if __name__=='__main__':run()
