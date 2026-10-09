from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse
import re
import math
import psutil
from v42_b2_seed_recovery_v19.common import ROOT,read,record,sha,digest
from v42_b2_seed_recovery_v19.budget import DateBudget as OriginalDateBudget
from v42_b2_seed_recovery_v19.policy import source_files as scientific_sources,exact_prior_runtime
from v42_may_campaign_native90.a_routing import rebound

CANONICAL=Path(r'D:\MobileESS_V42')


class ReceiptDateBudget(OriginalDateBudget):
    """Return the actual persisted solve receipt required by the M algorithms.

    V19's Native implementation intentionally persists Runtime before optional
    diagnostics but has no return statement. Its inherited optimize adapter
    therefore returns None to callers expecting a receipt. Keep that complete
    implementation and accounting, exposing only its just-completed call.
    """
    def optimize(self,model,*,track,label,requested_seconds,callback=None):
        before=len(self.calls)
        result=super().optimize(model,track=track,label=label,
            requested_seconds=requested_seconds,callback=callback)
        if len(self.calls)!=before+1 or self.inflight is not None:
            raise PermissionError('M_COMPLETED_NATIVE_RECEIPT_REQUIRED')
        receipt=self.calls[-1]
        runtime=receipt.get('Native_Runtime')
        if (receipt.get('track')!=track or receipt.get('label')!=label
                or receipt.get('entered_native') is not True
                or receipt.get('runtime_unavailable') is not False
                or isinstance(runtime,bool) or not isinstance(runtime,(int,float))
                or not math.isfinite(runtime) or runtime<0
                or (result is not None and result!=receipt)):
            raise PermissionError('M_COMPLETED_NATIVE_RECEIPT_IDENTITY_DRIFT')
        # Work is an optional diagnostic. Missing Work remains unknown; no
        # synthetic measurement or change to the persisted Runtime is made.
        return dict(receipt,Native_Work=receipt.get('Native_Work'))


def proof_routes(request):
    """Route proof packets only to this sealed date/attempt's output subtree.

    Validator/source modules retain their original ROOT. The copied function
    namespaces change filesystem routing only; all original code objects,
    integer gates, FULL rows, physical replay and exact arithmetic remain.
    """
    from v42_m1_hybrid import final_verify
    from v42_m1_anytime import core
    root=Path(request['root']).resolve()
    day,attempt_id=request['day'],request['attempt_id']
    if (root.drive.upper()!='D:' or request.get('arm')!='B2'
            or not re.fullmatch(r'2025-05-(0[1-9]|[12][0-9]|3[01])',day)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',attempt_id)):
        raise PermissionError('SCOPED_PROOF_REQUEST_IDENTITY_REQUIRED')
    output=Path(request['output']).resolve()
    expected=root/'dates/B2'/day/'attempts'/attempt_id/'output'
    if output!=expected or not output.is_relative_to(root):
        raise PermissionError('SCOPED_PROOF_OWN_OUTPUT_REQUIRED')

    def owned(path):
        value=Path(path).resolve()
        if value.drive.upper()!='D:' or not value.is_relative_to(output):
            raise ValueError('SCOPED_PROOF_OTHER_ATTEMPT_OR_INPUT_FORBIDDEN')
        return value

    original_under=final_verify._under
    labels=frozenset(('EVIDENCE','RECORDED_PACKET','RECORDED_PATH','LP_DUAL','OUTPUT'))
    def scoped_under(path,parent,label):
        if label in labels and Path(parent).resolve()==final_verify.ROOT.resolve():
            return owned(path)
        return original_under(path,parent,label)

    namespace=dict(vars(final_verify),_under=scoped_under)
    for name in ('_raw','_json','_packet','_output','_strict_ub'):
        namespace[name]=rebound(getattr(final_verify,name),namespace)

    def output_directory(path):
        value=owned(path);value.mkdir(parents=True,exist_ok=True);return value

    # The original writer's D: and containment tests remain active against the
    # exact owned output. Other core globals, source reads and scheduler stay.
    write=rebound(core.write,dict(core.write.__globals__,ROOT=output))
    return dict(output=output,owned=owned,final=namespace,
                write=write,output_directory=output_directory)


@contextmanager
def proof_scope(request,manifest):
    from v42_may_campaign_native90 import m_stage,operations
    from v42_m1_anytime import core,algorithms
    from v42_m1_hybrid import blocks,pricing,dw,final_verify
    from v42_b2_seed_recovery_v18 import certificate_box
    from v42_b2_seed_recovery_v19.common import atomic
    from . import canonical_stream,dw_native,pricing_box,f1_state
    from v42_b2_seed_recovery_v19 import initialization
    routes=proof_routes(request);output=routes['output']
    folder=Path(request['input_folder']).resolve()
    # These pre-existing producer receipts must stay read-only. No new input
    # generation is authorized by the proof-path adapter.
    for name in ('B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz','NATIVE_INPUT.json'):
        if not (folder/name).is_file():raise PermissionError('SCOPED_PROOF_FROZEN_INPUT_REQUIRED:'+name)
    inputs={str(p.resolve()):record(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    if any(not Path(p).is_relative_to(folder) for p in inputs):
        raise PermissionError('SCOPED_PROOF_INPUT_LINK_ESCAPE')
    bundle=read(folder/'NATIVE_INPUT.json')
    for key in ('route_table','electrical_certificate'):
        receipt=bundle[key]
        if sha(receipt['path'])!=receipt['sha256']:
            raise PermissionError('SCOPED_PROOF_FROZEN_LINKED_INPUT_SHA_DRIFT:'+key)
        inputs[str(Path(receipt['path']).resolve())]=record(receipt['path'])
    source_receipts={name:record(ROOT/name) for name in (
        'v42_m1_hybrid/final_verify.py','v42_m1_research/check_ub.py',
        'v42_m1_research/check_lb.py','v42_m1_hybrid/blocks.py',
        'v42_m1_anytime/core.py','v42_m1_anytime/algorithms.py',
        'v42_may_campaign_native90/operations.py','v42_m1_hybrid/dw.py','v42_m1_hybrid/bound.py',
        'v42_m1_hybrid/pricing.py',
        'v42_b2_seed_recovery_v18/certificate_box.py','v42_pr134_b1/common.py')}
    output.mkdir(parents=True,exist_ok=True)
    receipt=dict(schema='V42_B2_SCOPED_PROOF_PATH_AUTHORITY_V22',
        run_id=request['run_id'],day=request['day'],attempt_id=request['attempt_id'],
        manifest=record(request['manifest']),execution_SHA=manifest['execution_SHA'],
        owned_output=str(output),proof_read_write_roots=[str(output)],
        input_receipts_read_only=list(inputs.values()),original_sources=source_receipts,
        original_validator_ROOT=str(final_verify.ROOT),
        original_validator_code_objects_retained=True,scientific_arithmetic_changed=False,
        historical_candidate_point_admission=False,Native_optimize_calls=0,
        certificate_proof_serialization='V42_B2_CANONICAL_STREAM_V24',
        restricted_master_native_rows='V42_B2_RMP_EXACT_POWER_OF_TWO_ROWS_V25',
        pricing_nonunit_box='V42_B2_PRICING_FULL_CASE_PROJECTION_BOX_V26',
        current_attempt_F1_state='V42_V27_CURRENT_ATTEMPT_F1_FULL_LP_START',
        status='ROUTING_ADMITTED')
    atomic(output/'SCOPED_PROOF_PATH_AUTHORITY.json',receipt)
    def proof_atomic(path,value):
        return canonical_stream.atomic(routes['owned'](path),value)
    with ExitStack() as stack:
        # Importing f1_state above freezes the original code objects before
        # these aliases are routed. Full source/request I/O stays lazy, so a
        # routing-only scope does not construct scientific state.
        saved_f1 = initialization.validated_start
        saved_full_lp = m_stage._fresh_lp_dual
        current_f1_state = [None]
        def state():
            if current_f1_state[0] is None:
                current_f1_state[0] = f1_state.Scope(request,ROOT)
            return current_f1_state[0]
        def current_f1(case,budget,progress=None):
            return state().capture(saved_f1,case,budget,progress)
        def current_full_lp(case,budget,progress=None):
            return state().full_lp_adapter(saved_full_lp,case,budget,progress)
        stack.enter_context(patch.object(initialization,'validated_start',current_f1))
        stack.enter_context(patch.object(m_stage,'_fresh_lp_dual',current_full_lp))
        # Limit the memory-saving serialization adapter to this proof producer.
        # Global common functions and all certificate arithmetic stay original.
        stack.enter_context(patch.object(certificate_box,'digest',canonical_stream.digest))
        stack.enter_context(patch.object(certificate_box,'atomic',proof_atomic))
        for module in (m_stage,algorithms):
            stack.enter_context(patch.object(module,'_strict_ub',routes['final']['_strict_ub']))
        for module in (core,algorithms):
            stack.enter_context(patch.object(module,'write',routes['write']))
        for module in (blocks,pricing,dw):
            stack.enter_context(patch.object(module,'output_directory',routes['output_directory']))
        stack.enter_context(patch.object(dw,'build_master',dw_native.scoped_builder(
            dw.build_master,routes['output_directory'],routes['write'])))
        stack.enter_context(patch.object(dw,'write',routes['write']))
        stack.enter_context(patch.object(pricing,'run_pricing',pricing_box.scoped_pricing(
            pricing.run_pricing,pricing.local_exact_price_bound,routes['output_directory'])))
        # Operations uses D-only routing already; also bind its sole output
        # entry to this request while source ROOT and source SHA checks stay.
        stack.enter_context(patch.object(operations,'d_path',routes['owned']))
        try:yield routes
        finally:
            if any(record(p)!=r for p,r in inputs.items()):
                raise PermissionError('SCOPED_PROOF_READ_ONLY_INPUT_CHANGED')
            if any(record(ROOT/name)!=r for name,r in source_receipts.items()):
                raise PermissionError('SCOPED_PROOF_ORIGINAL_VALIDATOR_SOURCE_CHANGED')
            receipt.update(status='ROUTING_SCOPE_CLOSED',read_only_inputs_unchanged=True,
                           original_validator_sources_unchanged=True)
            atomic(output/'SCOPED_PROOF_PATH_AUTHORITY.json',receipt)

def sources():
    return dict(scientific_sources(),**{p.relative_to(ROOT).as_posix():sha(p)
        for p in sorted((ROOT/'v42_autonomous_b2').glob('*.py'))})

def verify_request(request):
    root=Path(request['root']).resolve();m=read(request['manifest'])
    if (Path(request['manifest']).parent.resolve()!=root or m['schema']!='V42_AUTONOMOUS_B2_V20'
        or m['execution_sources']!=sources() or m['execution_SHA']!=digest(sources())
        or request['manifest_SHA']!=sha(request['manifest']) or request['implementation_SHA']!=m['execution_SHA']
        or request['attempt_id'] not in m.get('attempt_ids',[m['attempt_id']]) or request['run_id']!=m['run_id']
        or request['arm']!='B2' or request['day'] not in m['input_folders']
        or request['Threads']!=1 or request['P2_calls']!=0 or request['target_gap']!=.03
        or request['native_budget_seconds']!=5400 or request['wall_budget_seconds'] is not None
        or m['initialization_native_limit_seconds']!=5400):
        raise PermissionError('B2_DEPLOYMENT_OR_REQUEST_SEAL_DRIFT')
    attempt=root/'dates/B2'/request['day']/'attempts'/request['attempt_id']
    for k,n in [('result','RESULT.json'),('output','output'),('progress','progress.json'),('error','error.json')]:
        if Path(request[k]).resolve()!=attempt/n:raise PermissionError('FRESH_ATTEMPT_PATH_DRIFT')
    if Path(request['input_folder']).resolve()!=Path(m['input_folders'][request['day']]).resolve():
        raise PermissionError('INPUT_FOLDER_DRIFT')
    for relative,s in m['builder_original_sources'].items():
        if sha(ROOT/relative)!=s:raise PermissionError('ORIGINAL_SCIENCE_SOURCE_DRIFT:'+relative)
    # Canonical provenance is admitted only for the byte-identical frozen source.
    if sha(ROOT/'v42_capacity/reference.py')!=sha(CANONICAL/'v42_capacity/reference.py'):
        raise PermissionError('CANONICAL_INPUT_PROVENANCE_SOURCE_DRIFT')
    for r in m['inherited_B1_results'].values():
        if record(r['path'])!=r:raise PermissionError('B1_RESULT_SHA_DRIFT')
    for day,r in m['prior_attempts'].items():exact_prior_runtime(r,root=root,day=day)
    return m

def assert_peers(request):
    seen={request['day']};slots={request['worker_slot']}
    for p in psutil.process_iter(['name']):
        if p.pid==psutil.Process().pid or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
        try:
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module=='v42_autonomous_b2.worker':
                peer=read(args[-1]);peer_manifest=read(peer['manifest'])
                # Different repaired deployments may coexist on different
                # dates. Verify each against its own immutable source root.
                if (peer['run_id']!=request['run_id'] or peer['manifest_SHA']!=sha(peer['manifest'])
                    or peer['implementation_SHA']!=peer_manifest['execution_SHA']):
                    raise PermissionError('PEER_SOURCE_OR_RUN_IDENTITY_DRIFT')
                peer_root=Path(p.cwd())
                if any(sha(peer_root/n)!=s for n,s in peer_manifest['execution_sources'].items()):
                    raise PermissionError('PEER_OWN_IMMUTABLE_SOURCE_DRIFT')
                if peer['day'] in seen or peer['worker_slot'] in slots:raise PermissionError('DUPLICATE_B2_DAY_OR_SLOT')
                seen.add(peer['day']);slots.add(peer['worker_slot'])
            elif module.endswith('.worker') and module.startswith(('v42_may','v42_b2','v42_m1','v42_a_stage','v42_autonomous_b3')):
                raise PermissionError('OTHER_SCIENTIFIC_WORKER_ACTIVE')
        except psutil.Error:continue
    if len(slots)>3:raise PermissionError('B2_MAX_THREE_WORKERS')

@contextmanager
def worker_scope(request):
    from v42_b2_seed_recovery_v19 import execution
    from v42_may_campaign import execution as legacy
    manifest=verify_request(request)
    # Budget creation is the first action after admission, before peer-sensitive
    # Native entry. A denied peer guard therefore still has measured accounting.
    token=legacy._active.set(dict(request=dict(request),manifest=manifest,
        manifest_sha=request['manifest_SHA'],worker_slot=request['worker_slot']))
    before=legacy.guard
    with patch.object(execution,'assert_peers',assert_peers):
        legacy.guard=execution.guard
        try:
            with proof_scope(request,manifest):yield manifest
        finally:legacy.guard=before;legacy._active.reset(token)

def run(path):
    from v42_b2_seed_recovery_v19 import worker as original
    from v42_may_campaign_native90 import inputs
    # The original generator compares its immutable provenance record including
    # absolute path. Its arithmetic, input bytes and all checks stay unchanged.
    generated=rebound(inputs.generate_b2,dict(inputs.generate_b2.__globals__,ROOT=CANONICAL))
    with patch.object(inputs,'generate_b2',generated):
        return rebound(original.run,dict(original.run.__globals__,verify_request=verify_request,
            worker_scope=worker_scope,DateBudget=ReceiptDateBudget))(path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('request');a=p.parse_args();raise SystemExit(run(a.request))
