"""Freeze the authorized successor sources and preserve PR105 evidence."""
import subprocess
from v42_root.common import *
from v42_native.voltage import Stage,authority,authority_sha

BASE='7ec7006eda9fb5ca7a1952c48391949844aef223'
ALLOWED={'v42_native/voltage.py','v42_native/grid.py','v42_boundary/model.py','v42_compact/native.py',
         'v42_temporal/native.py','v42_exact/native.py','v42_exact/validation.py','v42_root/native.py','v42_root/certify.py',
         'v42_may01/prepare.py','v42_voltage/grid.py','v42_voltage/preservation.py',
         'tests/test_v42_native.py','contract_tests/test_voltage_margin.py'}

def setup():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    OUT.mkdir(exist_ok=True,parents=True);LOCAL.mkdir(exist_ok=True)
    baseline=ROOT.parent/'v42_voltage_margin_pr';pr104=ROOT.parent/'v42_two_objective_pr'
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    inherited={r['path']:r for r in read(baseline/'docs/v42_voltage_margin_a1_m1/LEGACY_PRESERVATION_AUDIT.json')['authorized_changes']}
    files=[];changed=[];preserved=[]
    for path in tracked:
        previous=sha(baseline/path);current=sha(ROOT/path)
        assert previous==current or path in ALLOWED,path
        files.append(dict(path=path,sha256=current,PR105_sha256=previous,unchanged=current==previous))
        if path in ALLOWED or path in inherited:
            historical={previous}
            if (pr104/path).is_file():historical.add(sha(pr104/path))
            if path in inherited:historical.add(inherited[path]['PR104_sha256'])
            changed.append(dict(path=path,current_sha256=current,PR105_sha256=previous,historical_sha256=sorted(historical),
                                changed_from_PR105=previous!=current,authority='explicit stage-voltage successor or inherited PR105 repair/preservation supersession'))
        if path.startswith('docs/v42_voltage_margin_a1_m1/'):
            assert current==previous
            preserved.append(dict(path=path,sha256=current))
    assert sha(ROOT/'v42_native/actual.py')==sha(baseline/'v42_native/actual.py')
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,files=files,authorized_changes=changed,PR105_evidence_byte_identical=True))
    dump('PR105_INFEASIBILITY_PRESERVATION.json',dict(PASS=True,certificate_remains_valid=True,rows=145,
         condition='A1 with zero MESS P/Q and robust 0.955–1.045',files=preserved,certificate_error=False))
    dump('PR105_BASE_RECEIPT.json',dict(PR=105,head=BASE,branch='codex/v42-voltage-margin-a1-m1',old_result_preserved=True))
    dump('PREREGISTRATION.json',dict(base=BASE,stage_voltages={s.value:authority(s) for s in Stage},
         solver=dict(Threads=1,Seed=20260929,MIPGap=.005,GPU=False,A1_optimize_seconds=3600,M1_optimize_seconds=1800,build_excluded=True),
         objectives=['MAX_LINE_LOADING','MIN_INTERVENTION'],A1_P2=['migration_count','absolute_shift','prestart_relocation'],
         M1_P2=['movement_energy','movement_count'],one_M1=True,preflight_required=True,STOP_before_A2=True,
         FINAL_ROBUST_PLANNING_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    dump('STAGE_VOLTAGE_AUTHORITY.json',{s.value:dict(authority(s),sha256=authority_sha(s)) for s in Stage})
    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_bootstrap').glob('*.py'))]
    sources.extend(dict(path=p,sha256=sha(ROOT/p)) for p in sorted(ALLOWED))
    dump('SOURCE_MANIFEST.json',dict(sources=sources,preregistration_sha256=sha(OUT/'PREREGISTRATION.json')))
    dump('MIP_START_AUTHORITY_AUDIT.json',read(baseline/'docs/v42_voltage_margin_a1_m1/MIP_START_AUTHORITY_AUDIT.json'))
    (OUT/'PR105_SUPERSESSION_SCOPE.md').write_text('PR105 certificate remains valid, byte-identical, for A1 + zero MESS P/Q + 0.955–1.045. The explicitly authorized architecture changes A1 to 0.95–1.05 bootstrap. M1/A2/M2 retain 0.955–1.045, Actual retains 0.95–1.05 and no repair. A1 is provisional, not final robust Planning. Problem 13 remains unvalidated.\n',encoding='utf8')
    print('PR105 preserved; stage-aware successor freeze ready',flush=True)

if __name__=='__main__':setup()
