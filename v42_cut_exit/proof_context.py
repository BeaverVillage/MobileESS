"""Revised contract while preserving the stopped CP0 source/evidence."""
from .context import *
def seal_proof_sources():
    sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_cut_exit').glob('proof*.py'))]
    dump('PROOF_SOURCE_MANIFEST.json',dict(base_head=BASE,sources=sources,unchanged_CP0_source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json')))
def check_proof_sources():
    check_sources()
    for row in read(OUT/'PROOF_SOURCE_MANIFEST.json')['sources']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
def revise():
    cp=read(OUT/'CP0_OPTIMIZATION.json');assert cp['passes'][0]['status']==11
    assert not (LOCAL/'CP1/STARTED.json').exists() and not (LOCAL/'M1/STARTED.json').exists()
    old=OUT/'SUPERSEDED_CP_CONTRACT';old.mkdir(exist_ok=True)
    for name in ['PREREGISTRATION.json','CUTPASS_EXPERIMENT_CONTRACT.json']:shutil.copyfile(OUT/name,old/name)
    cp['partial_diagnostic']=True;cp['stopped_at_user_request']=True;dump('CP0_PARTIAL_DIAGNOSTIC.json',cp)
    dump('CP1_OPTIMIZATION.json',dict(run=False,cancelled_at_user_request=True,optimize_calls=0,reason='User superseded CP0/CP1 comparison with global-bound-proof policy.'))
    (OUT/'CP1_PROGRESS.csv').write_text('seconds,incumbent,bound,nodes\n',encoding='utf8');(OUT/'CP1_SOLVER.display.txt').write_text('NOT RUN: user cancelled CP1.\n',encoding='utf8')
    import gzip
    (OUT/'CP1_SOLVER.raw.gz').write_bytes(gzip.compress(b'',mtime=0))
    contract=dict(base_head=BASE,revision=2,supersedes_original_CP0_CP1_sequence=True,CP0_status='INTERRUPTED partial, preserved',CP1_RUN=False,primary_goal='Accelerate exact global-bound proof and reach solver-certified P1 gap <=0.005, not force root exit',interpretation='ROOT_LOOP_POLICY_EFFECT',pure_cut_ablation=False,individual_internal_causal_claim=False,formulation='M1-F3',formulation_changed=False,Method=2,Threads=1,Seed=20260929,MIPGap=.005,CutPasses='AUTO',Cuts='AUTO',individual_cut_families='AUTO',Heuristics=0,MIPFocus=3,DegenMoves='AUTO',primary=dict(label='PROOF_AUTO',TimeLimit=600,NodeLimit=None),conditional=dict(label='PROOF_DG0',DegenMoves=0,TimeLimit=600,max_calls=1,gate='Primary root relaxation completed, P1 not certified, post-LP root delay >=120s',only_changed_parameter='DegenMoves',complete_internal_isolation=False),production=dict(max_calls=1,TimeLimit=1800,cumulative_optimize_only=True,gate='Selected canary improves solver-certified global BestBd over PR107 by >=1e-4 OR reaches certified P1 gap <=0.005',branch_entry_not_gate=True,primal_improvement_not_gate=True),acceptance=dict(P1='solver-certified relative gap <=0.005',P2='inherited movement energy then count quality remains required for full M1 acceptance',physical='independent native P/Q/route/SOC/PCS plus robust grid and fixed AIDC identity'),P1_lock=1e-7,P2_energy_lock=1e-8,baseline_reused=True,A1_optimize_calls=0,STOP_before_A2=True,heuristic_and_probing_isolation=False,preregistered_before_new_primary=True)
    dump('REVISED_PROOF_EXPERIMENT_CONTRACT.json',contract);dump('PREREGISTRATION.json',contract)
    dump('USER_STEERING_RECEIPT.json',dict(CP0_safely_interrupted=True,CP0_interrupt_status=11,CP0_seconds=cp['total_optimize_seconds'],CP1_cancelled=True,original_parent_process_stopped=35120,graceful_solver_interrupt=True,new_policy=dict(Heuristics=0,MIPFocus=3,CutPasses='AUTO',DegenMoves='AUTO'),conditional_only_DegenMoves_0=True,no_cut_family_disabled=True,heuristic_improvement_not_acceptance=True))
    seal_proof_sources();print('REVISED CONTRACT SEALED',flush=True)
if __name__=='__main__':revise()
