import shutil,subprocess
import numpy as np
from v42_root.common import *
from v42_root.data import prepare
from v42_bootstrap.m1 import native_inputs,OptimizeOnlyBudget
from v42_bootstrap.grid import grid_report
from v42_bootstrap.attribution import supplemental_physical
from v42_native.mess import validate
from v42_m1_sparse.post_validate import controls_from_plan
BASE='f8dcd7e4545108aa5ab684ab97fe2dcd99fdbca8'
PRIOR=ROOT/'docs/v42_m1_root_lp_sparse_compression'
PRIOR_LOCAL=ROOT.parent/'V42_M1_SPARSE_LOCAL'
def inputs():
    frozen()
    bundle=prepare()[0];anchor=read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json')
    plan=read(LOCAL/'PR107_M1_PLAN.json')
    sites,initial,routes,battery,_=native_inputs(bundle)
    physical=validate(plan,sites,routes,battery,96);extra=supplemental_physical(plan,sites,battery)
    controls=controls_from_plan(plan,anchor);grid=grid_report(bundle,controls,plan['values']['rho_max'])
    assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
    assert all(abs(plan['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    assert np.max(np.abs(np.array(controls)-np.array(read(LOCAL/'PR107_M1_CONTROLS.json'))))<=1e-5
    return bundle,anchor,plan,sites,initial,routes,battery
def seal_sources():
    paths=sorted((ROOT/'v42_cut_exit').glob('*.py'))
    dump('SOURCE_MANIFEST.json',dict(base_head=BASE,inherited_formulation='v42_m1_sparse.grid.compressed_grid(M1-F3)',formulation_changed=False,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in paths]))
def check_sources():
    frozen()
    for r in read(OUT/'SOURCE_MANIFEST.json')['sources']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
def setup():
    OUT.mkdir(exist_ok=True);LOCAL.mkdir(exist_ok=True)
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==BASE
    files=[dict(path=p,sha256=sha(ROOT/p)) for p in subprocess.check_output(['git','ls-files'],text=True).splitlines()]
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base_head=BASE,files=files))
    dump('PR107_BASE_RECEIPT.json',dict(PR=107,exact_head=BASE,worktree=str(ROOT),branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()))
    for name,source in [('DATA.pkl',PRIOR_LOCAL/'DATA.pkl'),('PR107_M1_PLAN.json',PRIOR_LOCAL/'M1/FINAL_PLAN.json'),('PR107_M1_CONTROLS.json',PRIOR_LOCAL/'M1/CONTROLS.json')]:shutil.copyfile(source,LOCAL/name)
    reused=[]
    for n in ['A1_AIDC_GRID_CONTROL_ANCHOR.json','A1_TO_M1_HANDOFF.json','A1_PROVISIONAL_CONTROL_TABLE.csv','A1_UNKNOWN_POLICY_TABLE.json','A1_AIDC_SITE_TIME_ANCHOR.csv']:
        shutil.copyfile(PRIOR/n,OUT/n);reused.append(dict(path=n,sha256=sha(OUT/n),PR107_sha256=sha(PRIOR/n)))
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(OUT/'A1_TO_M1_HANDOFF.json'),read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json'))
    dump('PR107_A1_ANCHOR_REUSE.json',dict(PASS=True,A1_OPTIMIZE_CALLS=0,A1_ANCHOR_REUSED=True,files=reused,data_sha256=sha(LOCAL/'DATA.pkl')))
    evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(PRIOR.rglob('*')) if p.is_file()]
    baseline=read(PRIOR/'M1_OPTIMIZATION.json')
    dump('PR107_BASELINE_REUSE.json',dict(BASELINE_REUSED=True,BASELINE_RERUN=False,files=evidence,optimization=baseline))
    dump('ROOT_PROCESSING_BASELINE.json',dict(CutPasses='AUTO',**baseline['passes'][0]))
    contract=dict(formulation='M1-F3',formulation_changed=False,Method=2,Threads=1,Seed=20260929,MIPGap=.005,GPU=False,primary=[dict(name='CP0',CutPasses=0,TimeLimit=600),dict(name='CP1',CutPasses=1,TimeLimit=600)],NodeLimit=None,conditional_H0=dict(name='CP0_H0',CutPasses=0,Heuristics=0,TimeLimit=300,only_if_both_root_stuck=True,production_eligible=False),production=dict(max_calls=1,TimeLimit=1800,cumulative_optimize_only=True),production_gate=dict(first_non_root_node_max_seconds=450,bound_gain_min=1e-4,material_gap_reduction_absolute=.001),selection='quality, higher final bound, smaller gap, earlier non-root node, tree progress, work/wall',H0_gate='Neither primary reaches a confirmed non-root node within 450s and both spend >=80% of their actual wall at root.',telemetry='MIPNODE_NODCNT>0 confirms leaving root; sparse observations are carried forward only with their timestamp/age. Missing phase evidence remains null; FINAL state is recorded separately from 600s observations.',P1_lock=1e-7,P2_energy_lock=1e-8,STOP_before_A2=True)
    contract.update(diagnostic_interpretation='ROOT_LOOP_POLICY_EFFECT',operational_root_loop_policy_comparison=True,pure_cut_ablation=False,individual_cut_causal_attribution=False,H0_complete_isolation=False,H0_limits='Heuristics=0 leaves node probing and other internal root processing uncontrolled. The goal is useful B&B/global-bound progress and P1 quality, not attribution to an internal routine.')
    dump('CUTPASS_EXPERIMENT_CONTRACT.json',contract);dump('PREREGISTRATION.json',dict(base_head=BASE,preregistered_before_canaries=True,**contract))
    bundle,anchor,plan,sites,initial,routes,battery=inputs()
    dump('PR107_MIP_START_VALIDATION.json',dict(PASS=True,source_sha256=sha(LOCAL/'PR107_M1_PLAN.json'),UB=plan['values']['rho_max'],domain_sha256=plan['domain_sha256'],physical=validate(plan,sites,routes,battery,96),supplement=supplemental_physical(plan,sites,battery),grid=grid_report(bundle,controls_from_plan(plan,anchor),plan['values']['rho_max']),MIP_start_only=True,variables_fixed=False,anchor_unchanged=True))
    seal_sources()
    print('SETUP PASS',flush=True)
if __name__=='__main__':setup()
