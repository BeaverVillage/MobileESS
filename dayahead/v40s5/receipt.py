"""Git freezes have external identities; receipts never self-hash."""
import sys
from .common import *

def stage_commit(message):
    paths=['dayahead/v40s5','dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime']
    paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tests/dayahead').glob('test_v40s5_*.py'))]
    git('add','--sparse','-f','--',*paths)
    changed=git('diff','--cached','--name-only').splitlines()
    assert changed and all(allowed(p) for p in changed),changed
    git('commit','-m',message)
    assert git('status','--porcelain')==''
    return git('rev-parse','HEAD')

def freeze(stage):
    names={'prereg':'PREREGISTRATION','selection':'SELECTION_FREEZE','preexposed':'PREEXPOSED'}
    name=names[stage]
    if stage=='prereg':assert not (OUT/'models').exists()
    if stage=='selection':guard_receipt('PREREGISTRATION_COMMIT_RECEIPT')
    if stage=='preexposed':guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT')
    assert not (OUT/'V40S5_EXPOSURE_EVENT.json').exists()
    commit=stage_commit('Freeze V40S5 '+stage+' before '+('any model fit' if stage=='prereg' else 'exposed scoring'))
    if stage=='prereg':
        paths=list((ROOT/'dayahead/v40s5').glob('*.py'))
        paths += [p for p in OUT.iterdir() if p.is_file() and p.name not in ['V40S5_COMPUTE_LEDGER.json','V40S5_MAY_FIREWALL.json']]
    elif stage=='selection':
        paths=list((OUT/'models').glob('*'))+[OUT/'V40S5_SELECTION_FREEZE.json',OUT/'V40S5_HYPERPARAMETER_FREEZE.json']
        paths += [p for p in OUT.glob('V40S5_P_*_REPORT.json')]
    else:
        paths=list((OUT/'models').glob('*'))+[OUT/'V40S5_PREEXPOSED_FREEZE.json',OUT/'V40S5_REPRODUCIBILITY_AUDIT.json']
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):file_sha(p) for p in paths}
    write(name+'_COMMIT_RECEIPT',dict(timestamp=now(),commit=commit,stage=stage,frozen_SHA256=hashes,clean_at_commit=True,
      model_fits_before_commit=0 if stage=='prereg' else len(read('COMPUTE_LEDGER')['fits']),EXPOSED_scored=False))
    print(json.dumps(dict(stage=stage,commit=commit,frozen_files=len(hashes))),flush=True)

if __name__=='__main__':freeze(sys.argv[1])
