from pathlib import Path
import sys, shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *

def main():
    files={}
    for relative in ('dayahead/cache/v37_may_locked_final/electrical','dayahead/cache/v37_may_locked_final/traffic'):
        for source in sorted((OLD/relative).rglob('*')):
            if not source.is_file(): continue
            name=source.relative_to(OLD); target=REPO/name; expected=sha(source)
            if target.exists():
                if sha(target)!=expected:raise RuntimeError('INPUT_DRIFT:'+str(name))
            else:
                target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
            if sha(target)!=expected:raise RuntimeError('COPY_MISMATCH')
            files[name.as_posix()]={'sha256':expected,'bytes':source.stat().st_size}
    write(ROOT/'V40B_D1_INPUT_COPY_MANIFEST.json',{'status':'PASS','files':files,'file_count':len(files),
          'source':str(OLD),'destination':str(REPO),'old_files_modified':0,'May_outcome_reads':0})
    print('INPUT_COPY_PASS',len(files),flush=True)

if __name__=='__main__':main()
