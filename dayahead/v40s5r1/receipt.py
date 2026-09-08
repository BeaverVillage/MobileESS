"""Separate committed preregistration and pre-exposed candidate freezes."""
import sys
from .common import *

def commit(message):
    paths=['dayahead/v40s5r1','dayahead/artifacts/v40s5r1_rolling_origin_runtime']
    paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'tests/dayahead').glob('test_v40s5r1_*.py')]
    git('add','--sparse','-f','--',*paths)
    staged=git('diff','--cached','--name-only').splitlines();assert staged and all(allowed(p) for p in staged)
    git('commit','-m',message);assert git('status','--porcelain')==''
    return git('rev-parse','HEAD')

def main(stage):
    if stage=='prereg':
        assert not (OUT/'models').exists()
        name='PREREGISTRATION';paths=list((ROOT/'dayahead/v40s5r1').glob('*.py'))
        paths += [p for p in OUT.iterdir() if p.is_file() and p.name!='V40S5R1_PREREGISTRATION_COMMIT_RECEIPT.json']
    else:
        assert stage=='selection';guard('PREREGISTRATION_COMMIT_RECEIPT');name='SELECTION_FREEZE'
        assert not any(v['role']=='EXPOSED_EVALUATION' for v in pd.read_parquet(OUT/'V40S5R1_DAILY_TRAINING_LEDGER.parquet').merge(
          pd.DataFrame(read('PENDING_PANEL_IDENTITY_AUDIT')['issues']).assign(issue_time=lambda d:pd.to_datetime(d.issue_time,utc=True)),on='issue_time').to_dict('records'))
        paths=[OUT/'V40S5R1_SELECTION_FREEZE.json',OUT/'V40S5R1_DEV_CAL_RESULTS.json']
        for directory in ['models','predictions','scored','membership','events','daily','repeats','permutation']:
            paths += [p for p in (OUT/directory).rglob('*') if p.is_file()]
    c=commit('Freeze V40S5R1 '+stage+(' before first rolling fit' if stage=='prereg' else ' before rolling exposed evaluation'))
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_sha(p) for p in paths}
    write(name+'_COMMIT_RECEIPT',dict(timestamp=now(),commit=c,stage=stage,frozen_SHA256=hashes,clean_at_commit=True,EXPOSED_started=False))
    print(json.dumps(dict(stage=stage,commit=c,frozen_files=len(hashes))),flush=True)

if __name__=='__main__':main(sys.argv[1])
