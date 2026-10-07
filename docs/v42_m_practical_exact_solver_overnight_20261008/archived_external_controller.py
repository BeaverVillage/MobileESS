"""Deadline-bounded, proof-only external queue; production OPEN restart.

The registered M0 process must finish or be explicitly stopped before handoff.
Numerically unresolved domains remain OPEN. Recovery is an explicit new attempt,
with the failed attempt preserved, never a claim of a resumed solver tree.
"""
from practical_support import *
from fractions import Fraction as F
import argparse,copy,shutil,traceback
import archived_root_child_oracle as oracle_code
core=oracle_code.core;ExactBB=core.ExactBB
RUN=OUT/'external_production'

def existing_m0_alive():
    import psutil
    try:
        p=psutil.Process(read(OUT/'IMMUTABLE_DEADLINE.json')['existing_M0_process_PID'])
        return 'external_bb.py' in ' '.join(p.cmdline()) and Path(p.cwd()).resolve()==ROOT.resolve()
    except (psutil.NoSuchProcess,psutil.AccessDenied):return False

def archive_plan(node_id):
    source=(RUN/'external_nodes'/f'{node_id:04d}').resolve();base=RUN.resolve()
    assert source.is_relative_to(base) and source.parent==base/'external_nodes'
    if not source.exists():return None
    archives=base/'failed_attempts'/f'{node_id:04d}';archives.mkdir(parents=True,exist_ok=True)
    target=(archives/f'{sum(1 for p in archives.iterdir() if p.is_dir()):04d}').resolve()
    assert target.is_relative_to(base) and not target.exists()
    files={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
    return dict(archive=target.relative_to(RUN).as_posix(),files=files,UTC=stamp())

def complete_recovery_transaction(transaction,crash_hook=None):
    """Replay an intent durably before loading the OPEN queue; idempotent."""
    journal=transaction/'INTENT.json';intent=read(journal)
    if intent['committed']:return
    checkpoint=RUN/'OPEN_CHECKPOINT.json';prepared=transaction/'AFTER_CHECKPOINT.json'
    assert sha(prepared)==intent['after_SHA256']
    assert sha(checkpoint) in (intent['before_SHA256'],intent['after_SHA256']),'RECOVERY_CHECKPOINT_CONFLICT'
    archive=intent['archive']
    if archive:
        source=(RUN/'external_nodes'/f"{intent['node_id']:04d}").resolve();target=(RUN/archive['archive']).resolve();base=RUN.resolve()
        assert source.is_relative_to(base) and target.is_relative_to(base) and source.parent==base/'external_nodes'
        if source.exists():
            assert not target.exists(),'RECOVERY_ARCHIVE_CONFLICT'
            assert archive['files']=={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
            source.rename(target)
        assert target.exists() and archive['files']=={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    if crash_hook:crash_hook('AFTER_ARCHIVE')
    # Preserve the staged envelope's exact bytes, including Windows newlines.
    tmp=checkpoint.with_name(checkpoint.name+'.recovery.tmp')
    with tmp.open('wb') as f:f.write(prepared.read_bytes());f.flush();os.fsync(f.fileno())
    os.replace(tmp,checkpoint);assert sha(checkpoint)==intent['after_SHA256']
    if crash_hook:crash_hook('AFTER_CHECKPOINT')
    intent['committed']=True;intent['committed_UTC']=stamp();atomic(journal,intent)

def finish_pending_recoveries():
    for journal in sorted((RUN/'recovery_transactions').glob('*/INTENT.json')):
        complete_recovery_transaction(journal.parent)

def recover_unresolved(bb,node_id,crash_hook=None):
    n=bb.state['nodes'][str(node_id)];assert n['state']=='OPEN'
    before=bb.audit();checkpoint=RUN/'OPEN_CHECKPOINT.json';bb.save(checkpoint);before_hash=sha(checkpoint);archive=archive_plan(node_id)
    if n['processed']:
        rows=[r for r in bb.state['ledger'] if r['node_id']==node_id];assert len(rows)==1 and rows[0]['prune_reason']=='UNRESOLVED_PROOF_RETAINED_OPEN'
        bb.state.setdefault('failed_attempt_history',[]).append(dict(result=rows[0],archive=archive,recovery_UTC=stamp()))
        bb.state['ledger']=[r for r in bb.state['ledger'] if r['node_id']!=node_id];bb.state['processed']-=1
        n['processed']=False;n['prune_reason']=None;n.pop('result_digest',None);n.pop('receipt',None)
    else:bb.state.setdefault('failed_attempt_history',[]).append(dict(node_id=node_id,in_flight_interruption=True,archive=archive,recovery_UTC=stamp()))
    bb.state['in_flight']=None
    after=bb.audit();assert before['OPEN']==after['OPEN'] and before['global_OPEN_min_LB_exact']==after['global_OPEN_min_LB_exact']
    transactions=RUN/'recovery_transactions';transactions.mkdir(parents=True,exist_ok=True)
    transaction=transactions/f"{sum(p.is_dir() for p in transactions.iterdir()):04d}";transaction.mkdir()
    prepared=transaction/'AFTER_CHECKPOINT.json';bb.save(prepared)
    atomic(transaction/'INTENT.json',dict(node_id=node_id,before_SHA256=before_hash,after_SHA256=sha(prepared),archive=archive,committed=False,UTC=stamp()))
    if crash_hook:crash_hook('AFTER_INTENT')
    complete_recovery_transaction(transaction,crash_hook)
    return archive

def pseudocosts(bb):
    stats={};nodes=bb.state['nodes']
    for r in bb.state['ledger']:
        if r['parent'] is None or r['LP_status']!='OPTIMAL':continue
        parent=nodes[str(r['parent'])];j=nodes[str(r['node_id'])]['branch_variable'];value=nodes[str(r['node_id'])]['branch_value']
        parent_rows=[q for q in bb.state['ledger'] if q['node_id']==parent['id']]
        if not parent_rows:continue
        parent_row=parent_rows[-1];v=float(parent_row['raw_fractional_branch_value']);distance=abs(value-v)
        if distance<=1e-8:continue
        uplift=max(0.,float(F(r['effective_LB'])-F(parent_row['effective_LB'])))/distance
        stats.setdefault(j,{0:[],1:[]})[value].append(uplift)
    return stats

def chooser(bb,d):
    stats=pseudocosts(bb);all_means=[float(np.mean(v)) for by_value in stats.values() for v in by_value.values() if v]
    default=float(np.mean(all_means)) if all_means and max(all_means)>0 else 1.
    def choose(eligible,x):
        material=[j for j in eligible if min(abs(float(x[j])),abs(1-float(x[j])))>1e-8];candidates=material or eligible
        def rank(j):
            v=float(x[j]);s=stats.get(j,{0:[],1:[]});down=(float(np.mean(s[0])) if s[0] else default)*abs(v);up=(float(np.mean(s[1])) if s[1] else default)*abs(1-v)
            score=min(down,up)+.1*max(down,up);family=0 if str(d['names'][j]).startswith(('node_activity[','charge_mode[')) else 1
            return (-score,-min(abs(v),abs(1-v)),family,j)
        return min(candidates,key=rank)
    return choose

def retry_basis_source(bb,node):
    for failed in reversed(bb.state.get('failed_attempt_history',[])):
        result=failed.get('result',{});archive=failed.get('archive');partial=result.get('partial_basis')
        if result.get('node_id')!=node['id'] or not partial or not archive:continue
        assert result['fixing_hash']==node['fixing_hash'] and partial['not_a_certificate']
        p=(RUN/archive['archive']/partial['file']).resolve();assert p.is_relative_to(RUN.resolve())
        assert sha(p)==partial['SHA256']==archive['files'][partial['file']]
        return p
    return None

def audit_checkpoint(bb,A,d):
    CSC=A.tocsc();binary=set(map(int,np.flatnonzero(d['types']=='B')));checks=[]
    for failed in bb.state.get('failed_attempt_history',[]):
        archived=failed.get('archive')
        if archived:
            folder=RUN/archived['archive']
            assert archived['files']=={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()},'FAILED_ATTEMPT_ARCHIVE_CHANGED'
    incumbent=bb.state['incumbent'];point=(RUN/incumbent['point']).resolve();assert point.is_relative_to(RUN.resolve())
    with np.load(point) as z:incumbent_x=z['x'].copy()
    expected=incumbent.get('SHA256')
    if expected is None:
        matches=[r for r in bb.state['ledger'] if r.get('witness')==incumbent];assert len(matches)==1
        expected=read(RUN/Path(matches[0]['receipt']).parent/'LB_CERTIFICATE.json')['proof_vector_SHA256']
    assert sha(point)==expected,'INCUMBENT_POINT_CHANGED'
    replay_path=RUN/incumbent['replay'];assert sha(replay_path)==incumbent['replay_SHA256']
    assert read(replay_path)['PASS'] and full_replay(A,d,incumbent_x)['PASS'],'INCUMBENT_REPLAY_FAILURE'
    assert F.from_float(float(incumbent_x[239826]))==F(bb.state['UB']),'INCUMBENT_UB_IDENTITY_FAILURE'
    for ledger in bb.state['ledger']:
        node=bb.state['nodes'][str(ledger['node_id'])];p=RUN/ledger['receipt'];r=read(p);folder=p.parent
        assert core.digest(r)==node['result_digest'] and r['identity']==bb.state['identity'] and r['fixing_hash']==node['fixing_hash']
        e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
        for j,v in node['fixings']:assert j in binary and v in (0,1);e['lower'][j]=e['upper'][j]=v
        assert hashlib.sha256(e['lower'].tobytes()+e['upper'].tobytes()).hexdigest()==r['bounds_SHA256']
        if r['LP_status']=='OPTIMAL':
            cert=read(folder/'LB_CERTIFICATE.json');assert sha(folder/'LB_CERTIFICATE.json')==r['LB_certificate_SHA256'] and sha(folder/'LP_POINT_PROOF.npz')==cert['proof_vector_SHA256']
            with np.load(folder/'LP_POINT_PROOF.npz') as z:x=z['x'];pi=z['Pi']
            computed,_,_,_=hc.exact_bounded_lagrangian(CSC,e,pi);assert computed['exact_rational']==cert['exact_rational']==r['certified_LB'] and r['native_status']==2
            if r.get('archived_origin'):
                assert r['archived_origin']['archived_completed_OPTIMAL'] and r['archived_origin']['new_root_optimize_calls']==0 
                if r['basis_output_SHA256'] is not None:
                    assert sha(folder/'BASIS.npz')==r['basis_output_SHA256']==r['archived_origin']['saved_same_domain_basis_origin']['SHA256']
                    assert r['archived_origin']['saved_same_domain_basis_origin']['same_original_root_domain'] and r['archived_origin']['saved_same_domain_basis_origin']['not_node_proof']
                assert sha(hc.HISTORY/'PURE_LP_RESULT.json')==r['archived_origin']['source_result_SHA256'] and read(hc.HISTORY/'PURE_LP_RESULT.json')['Status']==2
            else:assert sha(folder/'BASIS.npz')==r['basis_output_SHA256']
            if r.get('branch_variable') is not None:
                j=r['branch_variable'];assert j in binary and j not in dict(node['fixings']) and float(x[j])==r['raw_fractional_branch_value'] and x[j] not in (0,1)
        elif r['LP_status']=='INFEASIBLE':
            cert=read(folder/'INFEASIBILITY_CERTIFICATE.json');assert sha(folder/'INFEASIBILITY_CERTIFICATE.json')==r['infeasibility_certificate_SHA256']
            with np.load(folder/'FARKAS_PROOF.npz') as z:ray=z['FarkasDual']
            computed,_,_,_=hc.exact_bounded_lagrangian(CSC,dict(e,objective=np.zeros_like(d['objective']),constant=np.array(0.)),-ray)
            assert computed['exact_rational']==cert['exact_rational'] and r['exact_infeasibility_PASS']==(F(computed['exact_rational'])>0)
        if r.get('partial_basis'):
            assert r['LP_status']=='UNRESOLVED' and r['partial_basis']['not_a_certificate']
            assert sha(folder/r['partial_basis']['file'])==r['partial_basis']['SHA256']
        if r.get('unresolved_point'):
            partial=r['unresolved_point'];assert partial['not_a_certificate'] and partial['not_an_incumbent'] and r['LP_status']=='UNRESOLVED'
            assert sha(folder/partial['file'])==partial['SHA256']
            with np.load(folder/partial['file']) as z:partial_x=z['x']
            assert hc.replay(A,dict(e,types=np.full(A.shape[1],'C')),partial_x,False)==r['unresolved_relaxed_replay']
        if r.get('witness'):
            with np.load(RUN/r['witness']['point']) as z:x=z['x']
            assert full_replay(A,d,x)['PASS']
        checks.append(dict(node_id=node['id'],PASS=True,LP_status=r['LP_status']))
    atomic(RUN/'RESTART_AUDIT.json',dict(PASS=True,UTC=stamp(),certificates_independently_recomputed=True,coverage=bb.audit(),node_checks=checks,audit_optimize_calls=0))

def start_queue(oracle,args):
    finish_pending_recoveries()
    checkpoint=RUN/'OPEN_CHECKPOINT.json'
    ledger=read(OUT/'GLOBAL_BOUND_LEDGER.json');assert ledger['initial']['LB']==INITIAL_LB and ledger['initial']['UB']==INITIAL_UB
    bounds=[INITIAL_LB]
    for event in ledger['events']:
        source=(OUT/event['source']).resolve();assert source.is_relative_to(OUT.resolve()) and sha(source)==event['source_SHA256']
        receipt=read(source);audit=source.parent/'INDEPENDENT_AUDIT.json'
        assert sha(audit)==event['independent_audit_SHA256'] and read(audit)['PASS']
        assert not receipt['restricted'] and receipt['bound_authority']['PASS'] and receipt['global_LB']==event['LB'] and receipt['valid_UB']==event['UB']
        bounds.append(event['LB'])
    registered=max(bounds)
    assert F.from_float(args.initial_lb)<=F.from_float(registered),'INITIAL_LB_EXCEEDS_REGISTERED_GLOBAL_AUTHORITY'
    with np.load(Path(args.center)) as z:center=z['x'].copy()
    replay=full_replay(oracle.A,oracle.d,center);assert replay['PASS']
    key=hashlib.sha256(center.tobytes()).hexdigest();point=RUN/'incumbents'/f'{key}.npz';replay_path=point.with_suffix('.REPLAY.json')
    if not point.exists():point_save(point,center)
    else:
        with np.load(point) as z:assert np.array_equal(z['x'],center)
    if not replay_path.exists():atomic(replay_path,replay)
    incumbent=dict(point=point.relative_to(RUN).as_posix(),SHA256=sha(point),replay=replay_path.relative_to(RUN).as_posix(),replay_SHA256=sha(replay_path))
    if args.resume:
        bb=ExactBB.load(checkpoint,oracle.identity);audit_checkpoint(bb,oracle.A,oracle.d)
        if F.from_float(float(center[239826]))<=F(bb.state['UB']):bb.state['UB']=str(F.from_float(float(center[239826])));bb.state['incumbent']=incumbent
        if bb.state['in_flight'] is not None:
            n=bb.state['nodes'][str(bb.state['in_flight'])];p=RUN/'external_nodes'/f"{n['id']:04d}"/'RESULT.json'
            if p.exists():bb.apply(n['id'],read(p))
            else:assert args.recover_node==n['id'],'EXPLICIT_INFLIGHT_RECOVERY_REQUIRED'
    elif args.import_m0:
        assert not checkpoint.exists() and not existing_m0_alive(),'REGISTERED_M0_STILL_RUNNING_NO_DUPLICATE'
        original=ExactBB.load(OLD/'OPEN_CHECKPOINT.json',oracle.identity)
        if original.state['in_flight'] is not None:
            node=original.state['nodes'][str(original.state['in_flight'])];result=OLD/'external_nodes'/f"{node['id']:04d}"/'RESULT.json'
            if result.exists():original.apply(node['id'],read(result))
            else:
                assert len(original.state['nodes'])==1 and original.state['processed']==0,'MULTINODE_INFLIGHT_HANDOFF_NEEDS_EXPLICIT_RECOVERY'
                atomic(RUN/'M0_UNRESOLVED_HANDOFF.json',dict(UTC=stamp(),original_checkpoint_SHA256=sha(OLD/'OPEN_CHECKPOINT.json'),domain_fixing_hash=node['fixing_hash'],root_domain_unchanged=True,former_inflight_retained_as_same_root=True,old_receipts_unchanged=True))
                original.state['in_flight']=None
        if (OLD/'external_nodes').exists():
            assert not (RUN/'external_nodes').exists();shutil.copytree(OLD/'external_nodes',RUN/'external_nodes')
        bb=original
        if F.from_float(float(center[239826]))>F(bb.state['UB']):
            previous=bb.state['incumbent']
            with np.load(OLD/previous['point']) as z:previous_x=z['x'].copy()
            previous_replay=full_replay(oracle.A,oracle.d,previous_x);assert previous_replay['PASS'] and F.from_float(float(previous_x[239826]))==F(bb.state['UB'])
            key=hashlib.sha256(previous_x.tobytes()).hexdigest();p=RUN/'incumbents'/f'{key}.npz';rp=p.with_suffix('.REPLAY.json')
            if not p.exists():point_save(p,previous_x)
            if not rp.exists():atomic(rp,previous_replay)
            bb.state['incumbent']=dict(point=p.relative_to(RUN).as_posix(),SHA256=sha(p),replay=rp.relative_to(RUN).as_posix(),replay_SHA256=sha(rp))
        else:bb.state['UB']=str(F.from_float(float(center[239826])));bb.state['incumbent']=incumbent
        if len(bb.state['nodes'])==1 and bb.state['nodes']['0']['state']=='OPEN':
            root=bb.state['nodes']['0'];floor=str(max(F(root['inherited_LB']),F.from_float(args.initial_lb)))
            root['inherited_LB']=floor;root['LB']=str(max(F(root['LB']),F(floor)))
            atomic(RUN/'INHERITED_GLOBAL_BOUND.json',dict(LB_exact=floor,global_bound_ledger_SHA256=sha(OUT/'GLOBAL_BOUND_LEDGER.json'),authority='Previously accepted full original native MILP bound; applies to the same entire original root domain',not_new_LP_certificate=True))
        # An unresolved root is retried under the registered recovery algorithm;
        # its domain remains identical and its prior attempt is archived.
        for n in list(bb.state['nodes'].values()):
            if n['state']=='OPEN' and (n['processed'] or (RUN/'external_nodes'/f"{n['id']:04d}"/'OPTIMIZE_ONCE.json').exists()):recover_unresolved(bb,n['id'])
        if F.from_float(float(center[239826]))<=F(bb.state['UB']):bb.state['UB']=str(F.from_float(float(center[239826])));bb.state['incumbent']=incumbent
        audit_checkpoint(bb,oracle.A,oracle.d)
    else:
        assert not checkpoint.exists() and not existing_m0_alive(),'REGISTERED_M0_STILL_RUNNING_NO_DUPLICATE'
        bb=ExactBB(oracle.identity,str(F.from_float(args.initial_lb)),str(F.from_float(float(center[239826]))),incumbent)
    if args.recover_node is not None:recover_unresolved(bb,args.recover_node)
    # A saved in-flight receipt is independently recomputed before it can
    # affect the next node choice or the global proof ledger.
    audit_checkpoint(bb,oracle.A,oracle.d)
    bb.save(checkpoint);return bb

def run(args):
    assert not existing_m0_alive(),'REGISTERED_M0_STILL_RUNNING_NO_DUPLICATE'
    from owned_controller_guard import owned_controller_alive
    assert owned_controller_alive() is None,'OWNED_EXTERNAL_CONTROLLER_STILL_RUNNING_NO_DUPLICATE'
    RUN.mkdir(exist_ok=True);oracle=oracle_code.LPOracle();bb=start_queue(oracle,args);checkpoint=RUN/'OPEN_CHECKPOINT.json';begin=time.perf_counter();start_count=bb.state['processed']
    oracle.checkpoint_hook=lambda:bb.save(checkpoint)
    oracle.retry_basis_for_node=lambda node:retry_basis_source(bb,node)
    if args.reuse_archived_root:
        assert args.resume and args.recover_node==0 and len(bb.state['nodes'])==1
        assert (RUN/'NUMERIC_STABILITY_RECOVERY_ONCE.json').exists(),'REGISTERED_NUMERIC_RECOVERY_MUST_BE_CONSUMED_FIRST'
        from import_archived_root import receipt
        atomic(RUN/'ARCHIVED_ROOT_IMPORT_ONCE.json',dict(UTC=stamp(),root_optimize_calls=0,same_scientific_domain=True))
        node=bb.select();assert node['id']==0;bb.begin(node);bb.save(checkpoint);oracle.choose_branch=chooser(bb,oracle.d)
        imported=receipt(oracle,node,RUN);bb.apply(0,imported);bb.save(checkpoint);audit_checkpoint(bb,oracle.A,oracle.d)
    try:
        while remaining(900)>0 and time.perf_counter()-begin<args.seconds:
            if args.max_nodes is not None and bb.state['processed']-start_count>=args.max_nodes:break
            node=bb.state['nodes'][str(bb.state['in_flight'])] if bb.state['in_flight'] is not None else bb.select()
            if node is None:break
            oracle.choose_branch=chooser(bb,oracle.d);bb.begin(node);bb.save(checkpoint)
            result=oracle.solve(node)
            from node_proof_guards import conflicts_with_known_witness
            with np.load(RUN/bb.state['incumbent']['point']) as z:known=z['x']
            if conflicts_with_known_witness(node,result,known):
                atomic(RUN/'EXACT_NODE_INFEASIBILITY_VS_KNOWN_WITNESS.json',dict(node_id=node['id'],fixings=node['fixings'],full_original_incumbent_replay_PASS=True,infeasibility_receipt=result,claim_accepted=False,domain_retained_OPEN=True));raise AssertionError('EXACT_NODE_PROOF_CONTRADICTS_VALIDATED_INCUMBENT_RETAIN_OPEN_STOP')
            bb.apply(node['id'],result);bb.save(checkpoint)
            atomic(RUN/'OPEN_COVERAGE.json',bb.audit());atomic(RUN/'NODE_LEDGER.json',bb.state['ledger'])
            table(RUN/'NODE_LEDGER.csv',[{k:r.get(k) for k in ['node_id','parent','depth','LP_status','certified_LB','effective_LB','Runtime','Work','basis_supplied','basis_accepted','fractional_binary_count','branch_name','state','prune_reason']} for r in bb.state['ledger']])
            atomic(RUN/'PSEUDOCOSTS.json',pseudocosts(bb))
            if result['LP_status']=='UNRESOLVED':
                # Retain the certified inherited floor in OPEN. The core selects
                # the best-bound unprocessed leaf next, allowing its unsolved
                # sibling to be measured without resolving this failed LP.
                continue
            if bb.audit()['global_gap']<=.005:break
        audit_checkpoint(bb,oracle.A,oracle.d)
        atomic(RUN/'RESULT.json',dict(UTC=stamp(),coverage=bb.audit(),processed=bb.state['processed'],processed_this_session=bb.state['processed']-start_count,wall_seconds=time.perf_counter()-begin,LP_calls_this_session=len(oracle.calls),restartable_OPEN_queue=True,pruning_counts={reason:sum(r['prune_reason']==reason for r in bb.state['ledger']) for reason in ['EXACT_LP_INFEASIBILITY','CERTIFIED_LB_AT_LEAST_VALIDATED_UB','INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM']},strong_branching='Not performed: current measured LP cost does not justify extra probes',root_recovery_Method='ARCHIVED_OPTIMAL_PROOF_IMPORT_WITHOUT_NEW_ROOT_SOLVE',child_Method=1,heuristic_branch_rank='deterministic measured pseudocost with fractionality and original family tie-break',unresolved_domains_retained=True))
    finally:bb.save(checkpoint);oracle.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--center',required=True);p.add_argument('--seconds',type=float,default=10800);p.add_argument('--initial-lb',type=float,default=INITIAL_LB);p.add_argument('--resume',action='store_true');p.add_argument('--import-m0',action='store_true');p.add_argument('--recover-node',type=int);p.add_argument('--max-nodes',type=int);p.add_argument('--reuse-archived-root',action='store_true');a=p.parse_args();assert not(a.resume and a.import_m0)
    try:run(a)
    except BaseException:atomic(RUN/'EXECUTION_ERROR.json',dict(UTC=stamp(),error=traceback.format_exc()));raise
