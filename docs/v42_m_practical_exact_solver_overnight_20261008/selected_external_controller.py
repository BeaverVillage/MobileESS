"""Evidence-selected external production tail, unchanged exact proof policy."""
from practical_support import *
import cold_barrier_external_controller as base
from proof_audit_cache import CertificateAuditCache
from owned_solver_guard_v4 import owned_controller_alive
import argparse,traceback
import re

def run(args):
    assert args.resume and not args.recover_node,'PRODUCTION_TAIL_CONTINUES_UNPROCESSED_OPEN_LEAVES'
    assert not base.existing_m0_alive() and owned_controller_alive() is None,'OWNED_SOLVER_STILL_RUNNING_NO_DUPLICATE'
    registration=read(OUT/'SELECTED_EXTERNAL_PRODUCTION_REGISTRATION.json')
    assert registration['PASS'] and registration['source_SHA256']==sha(Path(__file__))
    assert registration['immutable_deadline_SHA256']==sha(OUT/'IMMUTABLE_DEADLINE.json')
    assert registration['proof_audit_cache_source_SHA256']==sha(OUT/'proof_audit_cache.py')
    assert registration['base_controller_source_SHA256']==sha(OUT/'cold_barrier_external_controller.py')
    assert registration['exact_math_source_SHA256']==sha(Path(hc.exact_bound_module.__file__))
    assert read(OUT/'PROOF_AUDIT_CACHE_TESTS.json')['PASS']
    assert re.fullmatch(r'[a-z0-9_]+',args.session),'INVALID_REGISTERED_SESSION_NAME'
    session=registration['sessions'][args.session]
    assert sha(base.RUN/'OPEN_CHECKPOINT.json')==session['starting_checkpoint_SHA256'],'REGISTERED_OPEN_QUEUE_CHANGED_BEFORE_START'
    marker=base.RUN/(args.session+'.ONCE.json')
    assert not marker.exists(),'REGISTERED_PRODUCTION_SESSION_ALREADY_STARTED_NO_DUPLICATE'
    choice=registration['oracle']
    assert choice in ['cold_barrier_child_oracle','accuracy_barrier_child_oracle']
    oracle_code=module('selected_production_oracle',OUT/(choice+'.py'))
    assert registration['oracle_source_SHA256']==sha(OUT/(choice+'.py'))
    cache=CertificateAuditCache(hc.exact_bounded_lagrangian)
    original_audit=base.audit_checkpoint
    def checked_audit(bb,A,d):
        with cache.audit_scope(hc):original_audit(bb,A,d)
        p=base.RUN/'RESTART_AUDIT.json';r=read(p)
        r['independent_certificate_math_cache']=cache.stats()
        r['certificate_recomputation_policy']='Independent original-array exact arithmetic once per identical hashed input in this process; no persisted PASS cache trusted; all receipt/proof/fixing hashes and primal replays still checked'
        atomic(p,r)
    base.audit_checkpoint=checked_audit
    start_receipt=dict(UTC=stamp(),session=args.session,source_commit=git('rev-parse','HEAD'),oracle=choice,registration_SHA256=sha(OUT/'SELECTED_EXTERNAL_PRODUCTION_REGISTRATION.json'),new_root_optimize_calls=0,starting_checkpoint_SHA256=sha(base.RUN/'OPEN_CHECKPOINT.json'))
    atomic(marker,start_receipt);atomic(base.RUN/'SELECTED_EXTERNAL_ONCE.json',start_receipt)
    oracle=oracle_code.LPOracle()
    bb=base.start_queue(oracle,args);checkpoint=base.RUN/'OPEN_CHECKPOINT.json'
    begin=time.perf_counter();start_count=bb.state['processed']
    oracle.checkpoint_hook=lambda:bb.save(checkpoint)
    oracle.retry_basis_for_node=lambda node:base.retry_basis_source(bb,node)
    stop_reason='IMMUTABLE_DEADLINE_OR_REGISTERED_WINDOW'
    try:
        while remaining(900)>0 and time.perf_counter()-begin<args.seconds:
            if args.max_nodes is not None and bb.state['processed']-start_count>=args.max_nodes:break
            node=bb.select()
            if node is None:break
            assert node['parent'] is not None,'NO_FRESH_ROOT_IN_PRODUCTION_TAIL'
            oracle.choose_branch=base.chooser(bb,oracle.d);bb.begin(node);bb.save(checkpoint)
            result=oracle.solve(node)
            bb=base.consume_checked(bb,node['id'],result,oracle.A,oracle.d)
            bb.state['ledger'][-1]['accepted_UTC']=stamp();bb.save(checkpoint)
            atomic(base.RUN/'OPEN_COVERAGE.json',bb.audit());atomic(base.RUN/'NODE_LEDGER.json',bb.state['ledger'])
            table(base.RUN/'NODE_LEDGER.csv',[{k:r.get(k) for k in ['node_id','parent','depth','LP_status','certified_LB','effective_LB','Runtime','Work','basis_supplied','basis_accepted','fractional_binary_count','branch_name','state','prune_reason','accepted_UTC']} for r in bb.state['ledger']])
            atomic(base.RUN/'PSEUDOCOSTS.json',base.pseudocosts(bb))
            if bb.audit()['global_gap']<=.005:stop_reason='P1_GAP_TARGET_REACHED';break
            import check_primal_gate
            check_primal_gate.run()
            if read(OUT/'PRIMAL_GATE.json')['PASS']:
                stop_reason='M4_ELIGIBLE_CLEAN_NODE_BOUNDARY';break
        checked_audit(bb,oracle.A,oracle.d)
        final=dict(UTC=stamp(),session=args.session,stop_reason=stop_reason,coverage=bb.audit(),processed=bb.state['processed'],processed_this_session=bb.state['processed']-start_count,LP_calls_this_session=len(oracle.calls),wall_seconds=time.perf_counter()-begin,restartable_OPEN_queue=True,oracle=choice,child_Method=2,child_Crossover=0,child_BarConvTol=1e-12 if choice.startswith('accuracy') else 1e-8,pruning_counts={reason:sum(r['prune_reason']==reason for r in bb.state['ledger']) for reason in ['EXACT_LP_INFEASIBILITY','CERTIFIED_LB_AT_LEAST_VALIDATED_UB','INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM']},independent_certificate_math_cache=cache.stats(),unresolved_domains_retained=True,new_root_optimize_calls=0)
        atomic(base.RUN/'RESULT.json',final);atomic(OUT/'session_results'/(args.session+'_result.json'),final)
    finally:
        bb.save(checkpoint);oracle.close();base.audit_checkpoint=original_audit

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--center',required=True);p.add_argument('--seconds',type=float,required=True);p.add_argument('--initial-lb',type=float,default=INITIAL_LB);p.add_argument('--resume',action='store_true');p.add_argument('--max-nodes',type=int);p.add_argument('--session',default='production_tail_1')
    a=p.parse_args();a.import_m0=False;a.recover_node=None;a.recover_all_unresolved=False;a.reuse_archived_root=False
    try:run(a)
    except BaseException:atomic(base.RUN/'EXECUTION_ERROR.json',dict(UTC=stamp(),error=traceback.format_exc()));raise
