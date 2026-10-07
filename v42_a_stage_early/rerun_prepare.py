"""Versioned, one-shot PR174 rerun preparation; no scientific reconstruction change."""
from pathlib import Path
import gzip, pickle, shutil, subprocess, zipfile, hashlib
import numpy as np
from v42_pr134_b1.common import atomic, read, record, sha
from v42_a_stage_phase1.core import elastic_master
from .policy import ROOT, OUT, STATIC, DAY, POLICY
from . import BASE

PR174_ROOT = ROOT.parent/'a-stage-phase1-early'
PR174_OUT = PR174_ROOT/'docs/v42_a_stage_phase1_early_activation_20261007'

def prepare():
    OUT.mkdir(parents=True, exist_ok=True); STATIC.mkdir(parents=True, exist_ok=True)
    if (OUT/'RUN_STARTED.json').exists(): raise PermissionError('ONE_RUN_ONLY')
    initial=read(PR174_OUT/'INITIAL_VERIFICATION.json')
    if record(initial['state']['path']) != initial['state']: raise ValueError('PR174_STATE_DRIFT')
    target=STATIC/'INITIAL_STATE.pkl.gz'
    shutil.copyfile(initial['state']['path'],target)
    with gzip.open(target,'rb') as f: state=pickle.load(f)
    base,_,_,_,_,_,_,grows,_,_=state
    master=elastic_master(base,grows)
    if base.fingerprint()!=initial['original_snapshot_sha256'] or master.snapshot.fingerprint()!=initial['phase1_snapshot_sha256']:
        raise ValueError('INITIAL_MODEL_DRIFT')
    weights=initial['frozen_weights']
    if record(weights['path'])!=weights or not np.array_equal(np.load(weights['path'])['weights'],np.asarray(list(map(float,master.weights)))):
        raise ValueError('FROZEN_WEIGHTS_DRIFT')
    initial.update(state=record(target),read_only_PR174_initial_receipt=record(PR174_OUT/'INITIAL_VERIFICATION.json'),cold_initial_model=True,prior_native_point_reused=False)
    atomic(OUT/'INITIAL_VERIFICATION.json',initial)
    atomic(OUT/'EARLY_ACTIVATION_POLICY.json',POLICY)
    atomic(OUT/'BASE_IDENTITY.json',dict(PASS=True,exact_base=BASE,base_PR=174,base_URL='https://github.com/BeaverVillage/MobileESS/pull/174',historical_namespace_immutable=True))
    (OUT/'PREREGISTRATION.md').write_text('''# Corrected PR174 May19 single rerun

Exact base: 5d88890fe7ade1afff6f9faf69cc914aa69567e0, Draft PR174.
One cold May19 run from the byte-identical initial scientific active model. Historical native solutions are not warm starts. Initial target Phi=0.006626776621085752.

Use the corrected PR174 Phase-I -> partial exact pricing -> valid concrete activation -> re-solve loop unchanged. Keep exact migration fallback, same-dual continuation after empty bounded batches, old-point inclusion witness, native raw persistence before checks, and all lookahead/failed worker accounting. Preserve all physical candidates, frozen weights, four scientific objectives, original coefficients and 1e-6 science / 1e-8 zero tolerances. No permanent deletions or parameter sweep.

Fixed trigger: 16 independently validated negative concrete class columns or 24 fully priced classes, whichever first. Activate min(16,count), exact rational rc then stable identity. STAY and migration are both eligible. Maximum four process workers with Threads=1; sequential masters; max12 masters. Qualification compares one and four workers on tiny fixtures before May19.

Three consecutive re-solves with relative Phi reduction below1% and valid negatives stop as PHASE1_ACTIVATION_STAGNATION. Preserve each previous raw solution/descriptor as an inclusion witness. A raw Phi increase with a feasible same-Phi prior point is numerical degeneracy and continues; the raw new Phi is never replaced.

One 900s cumulative budget: max(elapsed wall since RUN_STARTED, sum of every real native Runtime), including build, source checks, pricing, recovery and activation. No resets, extension or second run. Initial static copying and qualification precede the budget; final persistence/cleanup overshoot is measured and permits no extra solve.

At certified zero, replay the artificial-free original active scientific model and STOP. P1, closure, other dates, production/Planning/Actual/Fresh AC are explicitly blocked. Budget/stagnation stops remain scientifically INCONCLUSIVE unless a verified witness itself fails. Historical receipts remain immutable in their original namespaces.

Original size/factor guards remain unchanged. Freeze the actual committed source bytes, model identities, gates and policies before the sole execution. Save X/Pi/RC/slack before every assertion, even on timeout. Publication is read-only postsolve; no automatic follow-up.
''',encoding='utf8',newline='\n')
    print('CORRECTED_INITIAL_IDENTITY_PASS',flush=True)

def freeze():
    if (OUT/'SOURCE_FREEZE.json').exists(): raise PermissionError('SOURCE_FREEZE_EXISTS')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    old=read(PR174_OUT/'SOURCE_FREEZE.json')
    sources=[]
    for r in old['source_files']:
        p=Path(r['path'])
        if p.is_relative_to(PR174_ROOT): p=ROOT/p.relative_to(PR174_ROOT)
        sources.append(p)
    sources+=list((ROOT/'v42_a_stage_early').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_corrected_rerun.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources))
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True)
    blobs={line.split('\t',1)[1]:line.split()[2] for line in tree.splitlines()}
    legacy=[]
    for p in sources:
        if not p.is_relative_to(ROOT): continue
        rel=p.relative_to(ROOT).as_posix(); b=p.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=blobs.get(rel):
            actual=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if actual!=blobs.get(rel): raise PermissionError('UNCOMMITTED_SOURCE:'+rel)
            legacy.append(rel)
    archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources): z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    gates=[OUT/name for name in ('INITIAL_VERIFICATION.json','SYNTHETIC_TESTS.json','PARALLEL_PRICING_EQUIVALENCE.json','CONCRETE_RECOVERY_QUALIFICATION.json')]
    gates += [Path(r['path']) for r in read(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/CANARY_EXECUTION_PERMIT.json')['gate_receipts'].values()]
    if not all(read(p).get('PASS') is True for p in gates): raise PermissionError('PRE_RUN_GATE_FAIL')
    atomic(OUT/'SOURCE_FREEZE.json',dict(PASS=True,schema='MAY19_EARLY_LP_900_V2',git_head=head,exact_base=BASE,day=DAY,
        continuous_components=['PHASE_I','LOCAL_PRICING'],budget900=True,
        execution_sources={str(p):sha(p) for p in sources},source_files=[record(p) for p in sources],source_archive=record(archive),
        gate_receipts=[record(p) for p in gates],legacy_checkout_filter_paths=legacy,
        solver_policy=record(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'),policy=record(OUT/'EARLY_ACTIVATION_POLICY.json'),
        historical_PR174_execution_not_extended=True))
    from .execution import verify
    verify();print('CORRECTED_SOURCE_FROZEN',head,len(sources),flush=True)

if __name__=='__main__':
    import sys
    {'prepare':prepare,'freeze':freeze}[sys.argv[1]]()
