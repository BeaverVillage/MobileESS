"""Freeze inputs and allowed source supersessions before native optimization."""
import subprocess
from v42_root.common import *
from v42_native.voltage import authority, authority_sha

BASE='bd88de5f5b79df7584519ae0e457ce67d3826b61'
ALLOWED={'.gitattributes','v42_boundary/model.py','v42_compact/native.py','v42_temporal/native.py',
         'v42_exact/validation.py','v42_native/canary.py','v42_native/grid.py',
         'v42_native/actual.py','v42_native/coordinator.py','v42_may01/prepare.py','tests/test_v42_native.py',
         'tests/test_v42_exact.py','tests/test_v42_root.py','tests/test_v42_temporal.py'}


def setup():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    OUT.mkdir(exist_ok=True,parents=True);LOCAL.mkdir(exist_ok=True)
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    baseline=ROOT.parent/'v42_two_objective_pr';files=[];changed=[]
    for path in tracked:
        old=sha(baseline/path);current=sha(ROOT/path)
        if old!=current:
            assert path in ALLOWED,path
            changed.append(dict(path=path,PR104_sha256=old,current_sha256=current,authority='explicit voltage/repair supersession'))
        files.append(dict(path=path,sha256=current,PR104_sha256=old,unchanged=old==current))
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,files=files,authorized_changes=changed,unrelated_sources_preserved=True))
    dump('PR104_BASE_RECEIPT.json',dict(head=BASE,PR=104,branch='codex/v42-two-objective-final-contract',
         P1=read(baseline/'docs/v42_final_two_objective_contract/TWO_OBJECTIVE_A1_OPTIMIZATION.json')['passes'][0],baseline_only=True,old_objective_values_locked=False))
    dump('PREREGISTRATION.json',dict(base=BASE,Planning_voltage=authority(),
         solver=dict(Threads=1,Seed=20260929,MIPGap=.005,GPU=False,A1_optimize_seconds=3600,M1_optimize_seconds=1800,build_excluded=True),
         science_groups=['MAX_LINE_LOADING','MIN_INTERVENTION'],A1_tuple=['migration_count','absolute_shift','prestart_relocation'],
         M1_tuple=['movement_energy','movement_count'],one_M1=True,STOP_before_A2=True,Problem13_final_validated=False))
    dump('PLANNING_VOLTAGE_AUTHORITY.json',dict(authority(),sha256=authority_sha()))
    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_voltage').glob('*.py'))]
    sources += [dict(path=p,sha256=sha(ROOT/p)) for p in sorted(ALLOWED|{'v42_native/voltage.py'})]
    dump('SOURCE_MANIFEST.json',dict(sources=sources,preregistration_sha256=sha(OUT/'PREREGISTRATION.json')))
    # Independent source plan validation remains separate from production decisions.
    audit=read(baseline/'docs/v42_final_two_objective_contract/MIP_START_AUTHORITY_AUDIT.json')
    dump('MIP_START_AUTHORITY_AUDIT.json',dict(audit,current_voltage_validation_required=True))
    print('PR104 baseline and tightened-source freeze ready',flush=True)


if __name__=='__main__':setup()
