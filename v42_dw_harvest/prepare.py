"""Read-only PR152 freeze and identical isolated development snapshots."""
from .common import *
import shutil,subprocess
import numpy as np


def prepare():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    assert not (OUT/'PR152_BYTE_FREEZE.json').exists()
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    frozen={p:sha(ROOT/p) for p in paths if p}
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json');r=read(OLD/'DW_CONTINUATION_FINAL_RESULT.json')
    assert cp['type']=='TERMINAL' and len(cp['pool'])==1604 and cp['pool_SHA']==read(OLD/'AUTHORITATIVE_TERMINAL_FREEZE.json')['pool_SHA']
    files=[OLD/'DW_CHECKPOINT_LATEST.json',OLD/cp['RMP']['point_file'],OLD/cp['smooth_file']]
    for mode in ['BASELINE','CHALLENGER']:
        leg=OUT/mode.lower();immutable=leg/'immutable';live=leg/'live'
        for d in ['logs','pricing_receipts','pricing_points']:(live/d).mkdir(parents=True,exist_ok=True)
        for file in files:
            dest=immutable/file.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,dest);dest.chmod(0o444)
            assert sha(file)==sha(dest)
        for c in cp['pool']:
            file=ROOT/c['file'];dest=leg/c['file'];dest.parent.mkdir(parents=True,exist_ok=True)
            assert sha(file)==c['file_SHA'];shutil.copyfile(file,dest);dest.chmod(0o444);assert sha(dest)==c['file_SHA']
        with np.load(OLD/cp['RMP']['point_file']) as z:tp=z['pi'].copy();ta=z['alpha'].copy()
        with np.load(OLD/cp['smooth_file']) as z:sp=z['pi'].copy();sa=z['alpha'].copy()
        assert cp['alpha_next']==.1
        # Same next Discovery smoothing update in both copies, not a new RMP.
        sp=.1*tp+.9*sp;sa=.1*ta+.9*sa
        np.savez_compressed(live/'TRUE_DUAL.npz',pi=tp,alpha=ta)
        np.savez_compressed(live/'SEARCH_DUAL.npz',pi=sp,alpha=sa)
        for n in ['TRUE_DUAL.npz','SEARCH_DUAL.npz']:(live/n).chmod(0o444)
    write(OUT/'PR152_BYTE_FREEZE.json',dict(base=BASE,files=frozen,pool_SHA=cp['pool_SHA'],columns=1604,upper=r['smallest_RMP_upper'],lower=r['best_certified_LB'],threshold=r['material_threshold']))
    stage=Path('C:/v42_microbenchmarks/may11_vnext_20261005/STOP_RECEIPT.json');stage_receipt=read(stage)
    assert stage_receipt['worker_dead'] and stage_receipt['worker_exit_code']==0
    write(OUT/'MULTICOLUMN_PREREGISTRATION.json',dict(BASE=BASE,OLD_CG_BASELINE_AUTHORITY=BASE,columns=1604,alpha=.1,
        legs=['BASELINE','CHALLENGER'],rounds_each=1,RMP_each=1,pricing_workers=4,Threads=1,pricing_cap_seconds=20,
        RMP_cap_seconds=200,native_budget_each=300,total_native_budget=600,budget_accounting='Sum of ALL native call wall durations, including concurrent workers; also report union. More conservative than wall-union.',
        no_automatic_extension=True,K_MAX_PER_MESS=8,K_MAX_PER_ROUND=32,
        policy='Up to4 strongest true-negative RC then up to4 maximin master support/projection diversity; early-stop at8 new useful nondominated candidates. Terminal incumbent rechecked too.',
        acceptance='Both valid, challenger useful retained/native pricing minute improves, audited upper nonincreasing, and improvement/wall-second strictly better with upper decrease >1e-8. Otherwise do not select.',
        seed=20260929,Certification_unchanged=True,authoritative_continuation_calls=0,Branch_and_Price=0,
        A_stage_terminal_receipt=stage_receipt,A_stage_receipt_SHA=sha(stage),history_budget_consumption=0))
    print('PR152_FROZEN_COPIES',len(frozen),len(cp['pool']),flush=True)


def preserved():
    f=read(OUT/'PR152_BYTE_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in f['files'].items())
    return len(f['files'])


if __name__=='__main__':prepare()
