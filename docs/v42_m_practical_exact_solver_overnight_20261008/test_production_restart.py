"""Exact production recovery and deterministic ranking fixtures; optimize=0."""
from practical_support import *
import tempfile,copy
from fractions import Fraction as F
import external_controller as c
core=c.core;ExactBB=core.ExactBB
def run():
    identity=dict(fixture='interrupted and unresolved root coverage')
    bb=ExactBB(identity,'1/2','1',dict(fixture_integer=True));n=bb.select();bb.begin(n)
    result=dict(identity=identity,fixing_hash=n['fixing_hash'],proof_checked=True,LP_status='UNRESOLVED',certified_LB=None,optimal_LP_certificate_PASS=False,exact_infeasibility_PASS=False,witness=None,branch_variable=None)
    bb.apply(0,result);before=bb.audit()
    with tempfile.TemporaryDirectory() as temp:
        oldrun=c.RUN;c.RUN=Path(temp)
        p=c.RUN/'external_nodes/0000';p.mkdir(parents=True);atomic(p/'OPTIMIZE_ONCE.json',dict(optimize_calls=1));atomic(p/'RESULT.json',result)
        archive=c.recover_unresolved(bb,0)
        assert bb.audit()['OPEN']==before['OPEN'] and bb.audit()['global_OPEN_min_LB_exact']==before['global_OPEN_min_LB_exact'] and bb.select()['id']==0
        assert len(bb.state['failed_attempt_history'])==1 and (c.RUN/archive['archive']/'RESULT.json').exists() and not p.exists()
        checkpoint=c.RUN/'OPEN_CHECKPOINT.json';bb.save(checkpoint);restored=ExactBB.load(checkpoint,identity);assert core.digest(bb.state)==core.digest(restored.state)
        # A failure in an in-flight root is an attempt restart, preserving the domain.
        restored.begin(restored.select());restored.save(checkpoint);restored=ExactBB.load(checkpoint,identity);c.recover_unresolved(restored,0)
        assert restored.audit()['OPEN']==[0] and restored.audit()['global_OPEN_min_LB_exact']=='1/2'
        c.RUN=oldrun
    crash_checks=[]
    for crash_stage in ['AFTER_INTENT','AFTER_ARCHIVE','AFTER_CHECKPOINT']:
        with tempfile.TemporaryDirectory() as temp:
            oldrun=c.RUN;c.RUN=Path(temp)
            trial=ExactBB(identity,'1/2','1',dict(fixture_integer=True));trial.begin(trial.select());trial.apply(0,result)
            p=c.RUN/'external_nodes/0000';p.mkdir(parents=True);atomic(p/'OPTIMIZE_ONCE.json',dict(optimize_calls=1));atomic(p/'RESULT.json',result)
            before=trial.audit();original_files={q.name:sha(q) for q in p.iterdir()}
            def injected(stage):
                if stage==crash_stage:raise RuntimeError('INJECTED_PROCESS_CRASH_'+stage)
            try:c.recover_unresolved(trial,0,injected)
            except RuntimeError as exc:assert str(exc)=='INJECTED_PROCESS_CRASH_'+crash_stage
            else:raise AssertionError('CRASH_NOT_INJECTED')
            c.finish_pending_recoveries();restored=ExactBB.load(c.RUN/'OPEN_CHECKPOINT.json',identity);after=restored.audit()
            assert after['OPEN']==before['OPEN'] and after['global_OPEN_min_LB_exact']==before['global_OPEN_min_LB_exact'] and restored.select()['id']==0
            archived=c.RUN/restored.state['failed_attempt_history'][0]['archive']['archive'];assert original_files=={q.name:sha(q) for q in archived.iterdir()}
            prior=core.digest(restored.state);c.finish_pending_recoveries();assert core.digest(ExactBB.load(c.RUN/'OPEN_CHECKPOINT.json',identity).state)==prior
            crash_checks.append(dict(stage=crash_stage,PASS=True,OPEN_retained=True,archive_bytes_identical=True,recovery_idempotent=True))
            c.RUN=oldrun
    exact=ExactBB(identity,'1/2','1',dict(fixture_integer=True));node=exact.select();exact.begin(node)
    optimal=dict(result,LP_status='OPTIMAL',certified_LB='3/5',optimal_LP_certificate_PASS=True,branch_variable=3,branch_is_original_binary=True,raw_fractional_branch_value=.4)
    exact.apply(0,optimal);assert exact.audit()['OPEN']==[1,2] and {exact.state['nodes'][str(i)]['branch_value'] for i in [1,2]}=={0,1}
    d=dict(names=np.array(['route[0]','route[1]','charge_mode[0]','node_activity[0]']))
    x=np.array([.5,.25,.5,.5]);choose=c.chooser(exact,d);assert choose([0,1,2,3],x)==2
    assert all(choose([0,1,2,3],x)==2 for _ in range(5));assert exact.audit()['OPEN']==[1,2]
    from unittest.mock import patch
    import psutil
    class Owned:
        def __init__(self,*a):pass
        def cmdline(self):return ['python.exe','docs/external_bb.py']
        def cwd(self):return str(ROOT)
    class Other(Owned):
        def cwd(self):return str(ROOT.parent/'unrelated_A_stage')
    observed=c.existing_m0_alive()
    with patch.object(psutil,'Process',Owned):assert c.existing_m0_alive(),'OWNED_M0_MUST_BLOCK_NEW_ROOT'
    with patch.object(psutil,'Process',Other):assert not c.existing_m0_alive(),'UNRELATED_PROCESS_MUST_NOT_BE_TARGETED'
    incumbent_checks=[]
    with tempfile.TemporaryDirectory() as temp:
        oldrun=c.RUN;c.RUN=Path(temp);x=np.zeros(239827);x[239826]=.75
        p=c.RUN/'incumbent.npz';rp=c.RUN/'incumbent.REPLAY.json';point_save(p,x);atomic(rp,dict(PASS=True))
        inc=dict(point=p.name,SHA256=sha(p),replay=rp.name,replay_SHA256=sha(rp));trial=ExactBB(identity,'1/2','3/4',inc)
        A=sparse.csr_matrix((1,len(x)));d=dict(types=np.full(len(x),'C'))
        with patch.object(c,'full_replay',return_value=dict(PASS=True)):c.audit_checkpoint(trial,A,d)
        def rejected(label):
            before=trial.audit()
            with patch.object(c,'full_replay',return_value=dict(PASS=label!='FRESH_REPLAY_FAILURE')):
                try:c.audit_checkpoint(trial,A,d)
                except AssertionError:pass
                else:raise AssertionError('INCUMBENT_TAMPER_ACCEPTED_'+label)
            assert before==trial.audit();incumbent_checks.append(dict(case=label,rejected=True,OPEN_unchanged=True))
        x[239826]=.7;point_save(p,x);rejected('POINT_SHA_TAMPER')
        trial.state['incumbent']['SHA256']=sha(p);rejected('RHO_UB_MISMATCH')
        x[239826]=.75;point_save(p,x);trial.state['incumbent']['SHA256']=sha(p)
        atomic(rp,dict(PASS=False));rejected('REPLAY_SHA_TAMPER')
        trial.state['incumbent']['replay_SHA256']=sha(rp);rejected('STORED_REPLAY_FAIL')
        atomic(rp,dict(PASS=True));trial.state['incumbent']['replay_SHA256']=sha(rp);rejected('FRESH_REPLAY_FAILURE')
        c.RUN=oldrun
    atomic(OUT/'PRODUCTION_RESTART_TESTS.json',dict(PASS=True,optimize_calls=0,unresolved_recovery_keeps_OPEN_domain=True,failed_attempt_bytes_archived=True,inflight_recovery_keeps_OPEN_domain=True,checkpoint_reload_identical=True,crash_safe_recovery_intent_tests=crash_checks,incumbent_identity_tests=incumbent_checks,both_children_always_preserved=True,deterministic_pseudocost_rank=True,ranking_does_not_prune=True,live_M0_duplicate_guard_PASS=True,owned_M0_observed_alive_at_test=observed,unrelated_A_stage_excluded=True,UTC=stamp()))
    print('PRODUCTION_RESTART_TESTS_PASS_OPTIMIZE_0')
if __name__=='__main__':run()
