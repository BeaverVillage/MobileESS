"""Freeze source and accepted A1 inputs; no A1 model construction or solve."""
import subprocess,shutil
from v42_root.common import *
BASE='0360f9db7a27068dc53665b263a93adfd870250f'
OLDOUT=ROOT/'docs/v42_a1_bootstrap_m1_robust'
OLDLOCAL=ROOT.parent/'V42_BOOTSTRAP_LOCAL'
def run():
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head==BASE
    paths=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths]
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base_head=BASE,files=files))
    dump('PR106_BASE_RECEIPT.json',dict(PR=106,head=head,branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),isolated_worktree=str(ROOT)))
    reuse=[]
    for n in ['A1_AIDC_GRID_CONTROL_ANCHOR.json','A1_TO_M1_HANDOFF.json','A1_PROVISIONAL_CONTROL_TABLE.csv','A1_UNKNOWN_POLICY_TABLE.json','A1_AIDC_SITE_TIME_ANCHOR.csv']:
        shutil.copyfile(OLDOUT/n,OUT/n);reuse.append(dict(path=n,sha256=sha(OUT/n),PR106_sha256=sha(OLDOUT/n)))
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(OUT/'A1_TO_M1_HANDOFF.json'),read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json'))
    shutil.copyfile(OLDLOCAL/'DATA.pkl',LOCAL/'DATA.pkl')
    shutil.copyfile(OLDLOCAL/'M1/FINAL_PLAN.json',LOCAL/'PR106_M1_PLAN.json')
    shutil.copyfile(OLDLOCAL/'M1/CONTROLS.json',LOCAL/'PR106_M1_CONTROLS.json')
    dump('PR106_A1_ANCHOR_REUSE_RECEIPT.json',dict(PASS=True,A1_OPTIMIZE_CALLS_THIS_TASK=0,A1_RERUN=False,handoff_CC4_Runtime_unchanged=True,files=reuse,data_sha256=sha(LOCAL/'DATA.pkl')))
    dump('PREREGISTRATION.json',dict(base_head=BASE,science_unchanged=True,A1_optimize_calls=0,candidates=['M1-F0','M1-F1','M1-F2','M1-F3','M1-F4','M1-FCRA'],order='baseline census, implementation, bounded equivalence, full structural census, <=3 LPs, root canary, freeze, one production',LP=dict(Threads=1,Method=1,Seed=20260929,TimeLimit=600),canary=dict(Threads=1,NodeLimit=1,TimeLimit=600),extra_CPU_diagnostic='exactly one Threads=4 Method=2 only if selected root >300s',production=dict(Seed=20260929,MIPGap=.005,TimeLimit=1800,optimize_only=True,GPU=False),physical_tolerance=1e-5,objective_tolerance=1e-7,component_lock_tolerance=1e-8,scaling='not selected without demonstrated benefit',STOP_before_A2=True))
if __name__=='__main__':run()
