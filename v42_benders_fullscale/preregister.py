"""No optimization: preserve base bytes, cache copies, and scope authority."""
import shutil
from .common import *

def run():
    assert git('rev-parse','HEAD')==BASE
    paths=git('ls-files').splitlines();assert len(paths)==2054
    for p in paths:
        if sha(ROOT/p)!=sha(PRIOR/p):shutil.copyfile(PRIOR/p,ROOT/p)
    receipt=[dict(path=p,sha256=sha(ROOT/p)) for p in paths]
    assert all(sha(PRIOR/r['path'])==r['sha256'] for r in receipt)
    dump('PR116_BASE_RECEIPT.json',dict(base=BASE,tracked_files=len(paths),PASS=True,files=receipt,
        inherited_tests=789,inherited_bounded_checks=44,
        bounded_receipt_sha256=sha(ROOT/'docs/v42_m1_integrality_gap_root_cause/WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')))
    for folder in ['THRESHOLD_LOCAL','V42_CERTIFICATE_LOCAL','V42_TWO_LOCAL']:
        src=PRIOR.parent/folder;dst=ROOT.parent/folder;dst.mkdir(parents=True,exist_ok=True)
        for p in src.iterdir():
            if p.is_file() and not (dst/p.name).exists():shutil.copy2(p,dst/p.name)
    dump('SCOPE_CORRECTION_ADDENDUM.json',dict(base=BASE,user_authorized_new_candidate=True,
        authority='User attachment b14e838b-1d73-4af5-b05a-358d2c2f9df3, sections 1-2, read before any optimization',
        request_sha256=sha('C:/Users/kjw39/.codex/attachments/b14e838b-1d73-4af5-b05a-358d2c2f9df3/붙여넣은 텍스트.txt'),
        historical_PR115_x='NOT_AVAILABLE',historical_x_unrecoverable=True,
        new_x_label='NEW_V2_EXPERIMENT_X0',historical_same_x_claim=False,same_x_performance_comparison=False,
        scientific_B3_feasible_set_unchanged=True,V2_engine_inherited_from_PR116=True,
        created_UTC=stamp(),optimize_calls_before_addendum=0,downstream_auto_run=False))
    dump('PREREGISTRATION.json',dict(base=BASE,created_UTC=stamp(),master_threads=1,Seed=20260929,
        Method=1,InfUnbdInfo=1,DualReductions=0,NumericFocus=1,FeasibilityTol=1e-7,OptimalityTol=1e-7,IntFeasTol=1e-7,
        recourse_thread_policy='4 if no independent heavy solve immediately before candidate evaluation, otherwise 1; unchanged within its native/Phase-I pair',
        pilot_max_candidate_recourse_evaluations=2,per_candidate_recourse_wall_seconds=1800,
        budget_interpretation='Native and any Phase-I fallback share 1800 seconds per persisted candidate, including template build and substitution. Finish terminal raw persistence/validation even at deadline, but no new optimize after deadline. Report audit overhead separately.',
        pilot_master_seconds=60,pilot_stop='witness/proof; otherwise at most recourse0/recourse1, require valid cut and distinct persisted x1',
        full_B3_wall_seconds=1800,full_restart='zero-cut clean deterministic restart; no pilot cuts reused',
        canary_wall_seconds=600,production_wall_seconds=1800,
        full_M1_gate='certified B3 witness/proof OR full B3 valid cuts>=2 and distinct persisted candidates>=3, no numerical contradiction or invalid cut',
        production_gate='valid original UB and finite certified global LB, valid cuts, no numerical ambiguity, LB>=inherited LB+1e-4 or certified gap<=.005',
        threshold=T,witness_guard=1e-6,master_binaries_B3=85744,continuous_B3=230999,
        master_binaries_full=208312,route_full=207928,mode_full=384,continuous_full=108431,
        original_UB=UB,inherited_original_LB=LB,initial_master_theta_floor='inherited S2 only for original full M1; never for zero-objective B3',
        historical_same_x='NOT_AVAILABLE',speedup_causal_claim=False,parameter_sweep=False,
        known_fixture_survival='Replay all inherited fixture certificates against all 49 feasible fixture assignments; their 7-bit axes differ from full-scale 85744-bit axis and cannot be used as full-scale points. Full-scale cuts use independent exact global proof and source separation; never embed or truncate fixture bits.',
        cut_aging=False,cut_deletion=False,cut_aggregation=False,scientific_changes=False,
        Actual_P_correction=False,Actual_Q_correction=False,P2_A2_M2='separate user approval even after accepted production P1',
        native_source_hashes=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_benders_v2').glob('*.py'))],
        fixture_receipt_sha256=sha(ROOT/'docs/v42_mess_benders_v2_native_recourse/V2_FIXTURE_EXACTNESS.json')))
    print('SCOPE ADDENDUM AND BASE RECEIPT WRITTEN; OPTIMIZE CALLS=0',flush=True)

if __name__=='__main__':run()
