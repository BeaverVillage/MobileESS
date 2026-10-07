from pathlib import Path
import subprocess,gzip,pickle,zipfile,xml.etree.ElementTree as ET
import numpy as np
from v42_pr134_b1.common import atomic,read,record,sha
from v42_a_stage_phase1.setup import load_initial,STATIC as OLD_STATIC
from v42_a_stage_phase1.producer import row_partition
from v42_a_stage_phase1.core import elastic_master
from .policy import ROOT,OUT,STATIC,HISTORY,DAY,POLICY
from . import BASE

def prepare():
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    atomic(OUT/'EARLY_ACTIVATION_POLICY.json',POLICY)
    atomic(OUT/'BASE_IDENTITY.json',dict(PASS=True,exact_base=BASE,base_PR=172,
        old_manifest=record(HISTORY/'SHA256_MANIFEST.json'),historical_600_seconds_immutable=True))
    (OUT/'PREREGISTRATION.md').write_text('''# May19 Early Activation V2 preregistration

Exact base PR172: 92b8cc679e115673e0a29c71d0797013c4e08e57. Only May19 auxiliary Phase-I, local pricing LPs, and original P1 LP are authorized. No other dates, full four-objective A1, Planning, Actual or Fresh follow this task.

The unchanged PR172 complete physical domain, fast matrix producer, all four scientific objectives, hard local physics, frozen elastic weights, tolerances and Method2/Threads1 solver policy are reused byte for byte. The execution backstop gains a separate, source-bound May19 continuous-model permit for the newly authorized 900s experiment; historical permits and receipts remain immutable.

For each frozen master dual, classes are sorted by ID; the next iteration resumes after the prior consumed class prefix. Stop at 16 independently valid negative concrete class columns or 24 fully priced classes. Activate min(16, count), ranked by exact rational rc then class/site/start/path identity. Validate one best negative physical assignment per class. Each class column assigns every member to the same original hard-valid STAY/migration path. Its normalization coefficient is 1; the potential is the certified current native local row/box lower bound under the frozen global Pi. This is an equivalent class-column pricing certificate, not a claim about an individual primitive variable's native RC. Physical couplings, native B times the separately constructed physical point, and the exact reduced cost must agree. Full mixed fractional LP directions are retained in block pricing and final closure. A fractional negative direction alone is never activated.

Recovery scans all omitted STAY scores and physical migration paths supported by the positive oracle events. Only the best candidate is independently validated and counted. Missing concrete recovery is NEGATIVE_BLOCK_UNMATERIALIZED, never infeasibility or closure. Such classes remain in the complete pool for later exact recovery. No unselected candidate is deleted.

At most four process workers, each with a separate native environment and Threads1. Waves are consumed in canonical order; any executed lookahead is logged and charged even if the early prefix ends before it. Master solves are sequential. A real 1-worker versus 4-worker exact fixture precedes execution; failures force one worker. Canonical results exclude timing/process metadata.

The single budget is max(elapsed wall since RUN_STARTED, sum of every real native Runtime), limited to 900 seconds. Wall includes model building, source checks, pricing, exact recovery, validation and activation during execution. Initial static scientific reconstruction and synthetic qualification occur before RUN_STARTED. Parallel waves reserve remaining native seconds equally across launched workers, and share the absolute wall deadline. No reset, continuation extension or automatic rerun. Raw arrays are persisted before assertions even at a timeout; final persistence/cleanup may create a measured soft-stop overshoot, never a new solve.

At most 12 Phase-I master solves. Three consecutive relative reductions below 1% with valid negatives stop as stagnation. Material Phi increases above 1e-8 stop for investigation. Size limits remain original active cols200000, new cols/round10000, STAY50%, migration2M, factor250M/2GB; compare every actual auxiliary matrix with half the old complete-active row/column/nnz regime. Engineering stops never imply scientific infeasibility. Partial success requires at least 1% observed Phi reduction; certified zero requires raw original artificial-free replay at unchanged1e-6.

After zero, solve original rho-only P1 without artificials. Incremental P1 uses the same16/24 policy. A complete no-improvement incremental class cycle must stabilize before a final150/150 exact native STAY/migration/mixed fractional closure. Full bound gap and complete receipts are required; LP closure does not imply integer closure. Success stops this task and recommends a separately authorized next canary.
''',encoding='utf8',newline='\n')
    base,descriptor,data,domains,ledger,axes,n=load_initial()
    grows,lrows,owned=row_partition(base,descriptor,n,axes.values())
    master=elastic_master(base,grows)
    previous=read(HISTORY/'PHASE1_CONSTRUCTION_VERIFICATION.json')
    if master.snapshot.fingerprint()!=previous['phase1_snapshot_sha256']:raise ValueError('PR172_PHASE1_CHANGED')
    weights=np.load(previous['weights']['path'])
    if not np.array_equal(weights['weights'],np.asarray(list(map(float,master.weights)))):raise ValueError('FROZEN_WEIGHTS_CHANGED')
    state=STATIC/'INITIAL_STATE.pkl.gz'
    with gzip.open(state,'wb',compresslevel=1) as f:pickle.dump((base,descriptor,data,domains,ledger,axes,n,grows,lrows,owned),f,protocol=5)
    atomic(OUT/'INITIAL_VERIFICATION.json',dict(PASS=True,state=record(state),original_snapshot_sha256=base.fingerprint(),
        phase1_snapshot_sha256=master.snapshot.fingerprint(),PR172_construction=record(HISTORY/'PHASE1_CONSTRUCTION_VERIFICATION.json'),
        frozen_weights=previous['weights'],qualified_full_blocks=record(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json'),
        census=ledger['receipt'],native_calls=0,scientific_coefficients_changed=False))
    print('EARLY_STATIC_PREPARED',base.matrix.shape,state.stat().st_size,flush=True)

def freeze():
    if (OUT/'SOURCE_FREEZE.json').exists():raise PermissionError('SOURCE_FREEZE_EXISTS')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    old=read(HISTORY/'PHASE1_SOURCE_FREEZE_CONTINUATION_001.json')
    old_root=Path(old['source_files'][0]['path'])
    # Recover repository-relative producer paths from the previous archive;
    # arbitrary external dependencies remain at their original absolute paths.
    prior_root=ROOT.parent/'a-stage-phase1-pricing'
    sources=[];changes=[];filtered=[]
    for prior in old['source_files']:
        p=Path(prior['path'])
        if p.is_relative_to(prior_root):p=ROOT/p.relative_to(prior_root)
        if p.name in ('execution.py','.gitattributes') and sha(p)!=prior['sha256']:
            changes.append(dict(path=str(p),reason='separate narrow900 May19 LP execution hook / new namespace byte policy'))
        elif record(p)['sha256']!=prior['sha256'] or record(p)['bytes']!=prior['bytes']:
            rel=p.relative_to(ROOT).as_posix()
            base_blob=subprocess.check_output(['git','rev-parse',BASE+':'+rel],cwd=ROOT,text=True).strip()
            actual_blob=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if actual_blob!=base_blob:raise PermissionError('INHERITED_PR172_HEAD_SOURCE_CHANGED:'+str(p))
            changes.append(dict(path=str(p),reason='unchanged exact PR172 final HEAD; postsolve reporter differed from its earlier executed archive'))
        sources.append(p)
    sources+=list((ROOT/'v42_a_stage_early').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_early.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources))
    for p in sources:
        if not p.is_relative_to(ROOT):continue
        rel=p.relative_to(ROOT).as_posix()
        committed=subprocess.check_output(['git','show',head+':'+rel],cwd=ROOT)
        if committed!=p.read_bytes():
            blob=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            expected=subprocess.check_output(['git','rev-parse',head+':'+rel],cwd=ROOT,text=True).strip()
            if blob!=expected:raise PermissionError('UNCOMMITTED_SOURCE:'+str(p))
            filtered.append(rel)
    archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    gate_paths=[OUT/'INITIAL_VERIFICATION.json',OUT/'SYNTHETIC_TESTS.json',OUT/'PARALLEL_PRICING_EQUIVALENCE.json',OUT/'CONCRETE_RECOVERY_QUALIFICATION.json']
    old_fast=ROOT/'docs/v42_a_stage_fast_active_domain_20261007/CANARY_EXECUTION_PERMIT.json'
    gate_paths += [Path(r['path']) for r in read(old_fast)['gate_receipts'].values()]
    if not all(read(p).get('PASS') is True for p in gate_paths):raise PermissionError('PRE_RUN_GATE_FAIL')
    atomic(OUT/'SOURCE_FREEZE.json',dict(PASS=True,schema='MAY19_EARLY_LP_900_V2',git_head=head,exact_base=BASE,
        day=DAY,continuous_components=['PHASE_I','LOCAL_PRICING','ORIGINAL_P1'],budget900=True,
        execution_sources={str(p):sha(p) for p in sources},source_files=[record(p) for p in sources],source_archive=record(archive),
        gate_receipts=[record(p) for p in gate_paths],intentional_engineering_source_extensions=changes,
        legacy_checkout_filter_paths=filtered,solver_policy=record(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'),
        policy=record(OUT/'EARLY_ACTIVATION_POLICY.json'),historical600_not_extended=True))
    from .execution import verify
    verify();print('EARLY_FROZEN',head,len(sources),flush=True)

if __name__=='__main__':
    import sys
    {'prepare':prepare,'freeze':freeze}[sys.argv[1]]()
