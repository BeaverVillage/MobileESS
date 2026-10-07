"""Rebuild PR176's final active support and certify residual row identities."""
from pathlib import Path
from fractions import Fraction
import gzip,pickle,subprocess,zipfile,hashlib,csv
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record,sha
from v42_a_stage_domain_v2.active import option_from_json
from v42_a_stage_phase1.backend import assemble_original,update_graph
from v42_a_stage_phase1.core import elastic_master
from v42_a_stage_early.candidate import expanded_graph
from v42_a_stage_early.progress import capture,inclusion_witness
from .policy import ROOT,OUT,STATIC,DAY,POLICY
from .attribution import analyze
from . import BASE

PR176_ROOT=ROOT.parent/'a-stage-phase1-corrected'
PR176_OUT=PR176_ROOT/'docs/v42_a_stage_phase1_corrected_rerun_20261008'

def prepare():
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    if (OUT/'RUN_STARTED.json').exists():raise PermissionError('NO_SECOND_EXPERIMENT')
    previous=read(PR176_OUT/'INITIAL_VERIFICATION.json')
    if record(previous['state']['path'])!=previous['state']:raise ValueError('PR176_INITIAL_STATE_DRIFT')
    with gzip.open(previous['state']['path'],'rb') as f:state=pickle.load(f)
    base,global_descriptor,data,domains,ledger,base_axes,n,base_grows,lrows,owned=state
    weights=np.load(previous['frozen_weights']['path'])['weights'];row_weights={}
    cursor=0
    for row in base_grows:
        row_weights[row]=Fraction(float(weights[cursor]));cursor+=2 if base.senses[row]=='=' else 1
    activation=list(csv.DictReader((PR176_OUT/'ACTIVATED_COLUMNS.csv').open(encoding='utf8')))
    by_id={r['candidate']['candidate_id']:r for p in (PR176_OUT/'M19').rglob('EXACT_PRICING.json') if (r:=read(p))['candidate'] is not None}
    rawrec=read(PR176_OUT/'M19/R2/NATIVE_RESULT.json')['raw_attributes']
    if record(rawrec['path'])!=rawrec:raise ValueError('PR176_OPTIMAL_RAW_DRIFT')
    raw={k:v for k,v in np.load(rawrec['path']).items()};prior=None
    for iteration in range(3):
        for a in activation:
            if a['iteration']!=str(iteration):continue
            c=by_id[a['candidate_id']]['candidate'];uid=data[7]['classes'][c['class_id']][0]
            option=option_from_json(c['option'])
            graph=expanded_graph(data[5][uid],option,data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
            data,ledger=update_graph(data,domains,c['class_id'],graph)
        original,desc,grows,lrows,owned,axes=assemble_original(base,base_grows,n,base_axes,data)
        if iteration==1:
            historical_master=elastic_master(original,grows,weights_by_row=row_weights)
            identity=read(PR176_OUT/'M19/R2/MODEL_IDENTITY.json')
            if historical_master.snapshot.fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('PR176_R2_RECONSTRUCTION_DRIFT')
            historical=(original,desc,data,domains,ledger,axes,n,grows,lrows,owned)
            prior=capture(original,desc,historical_master,raw)
    master=elastic_master(original,grows,weights_by_row=row_weights)
    identity=read(PR176_OUT/'M19/R3/MODEL_IDENTITY.json')
    if master.snapshot.fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('PR176_FINAL_MODEL_DRIFT')
    witness,mapped=inclusion_witness(prior,original,desc,master,n)
    if not witness['PASS']:raise ValueError('PR176_FINAL_INCLUSION_FAIL')
    np.savez_compressed(STATIC/'HISTORICAL_INCLUDED_POINT.npz',X=mapped)
    initial=(original,desc,data,domains,ledger,axes,n,grows,lrows,owned)
    with gzip.open(STATIC/'INITIAL_STATE.pkl.gz','wb',compresslevel=1) as f:pickle.dump(initial,f,protocol=5)
    with gzip.open(STATIC/'GLOBAL_DESCRIPTOR.pkl.gz','wb',compresslevel=1) as f:pickle.dump(global_descriptor,f,protocol=5)
    # The unchanged global prefix is independently matched against the original
    # full scientific model. Only resource RHS constants can differ due to the
    # retained fixed local schedules; no grid row or coefficient may differ.
    authority=Path('C:/v42_pr134_sc_execution_20261007/stages/2025-05-19/A1/1/output')
    coded=authority/'A0_ATTRIBUTES_CODED.npz';source_matrix=authority/'A0_MATRIX.npz'
    with np.load(coded) as z:attrs={k:z[k].copy() for k in z.files}
    source=sp.load_npz(source_matrix);prefix=source[:len(grows),:n].tocsr()
    delta=prefix-original.matrix[:len(grows),:n];delta.eliminate_zeros()
    rhs_differences=set(map(int,np.flatnonzero(attrs['rhs'][:len(grows)]!=original.rhs[:len(grows)])))
    if delta.nnz or not rhs_differences<=set(axes.values()) or not np.array_equal(attrs['sense'][:len(grows)],original.senses[:len(grows)]):
        raise ValueError('ORIGINAL_GLOBAL_ROW_ATLAS_IDENTITY_FAIL')
    del source,prefix,delta
    certificate=read(data[0]['electrical_certificate']['path']);voltage=certificate['outputs']['voltage'];planning=certificate['outputs']['planning_coefficients']
    if record(voltage['path'])['sha256']!=voltage['sha256'] or record(planning['path'])['sha256']!=planning['sha256']:raise ValueError('ELECTRICAL_ARCHIVE_DRIFT')
    with np.load(voltage['path']) as z:node_names=z['node_names'].copy()
    families=attrs['rf_names'][attrs['rf'][:len(grows)]]
    resource_variables=[]
    for kind,site,t in axes:
        e=global_descriptor['known'].get((site,t)) if kind=='GPU' else global_descriptor['risk'].get((site,t)) if kind=='RUNTIME' else None
        if e is not None and e[0]!='v':raise ValueError('EXACT_RESOURCE_VARIABLE_AXIS_REQUIRED')
        resource_variables.append(int(e[1]) if e is not None else -1)
    atlas=dict(rf=attrs['rf'][:len(grows)],rf_names=attrs['rf_names'],node_names=node_names,
        voltage_lower_rows=np.flatnonzero(families=='voltage_lower'),voltage_upper_rows=np.flatnonzero(families=='voltage_upper'),
        resource_variables=np.asarray(resource_variables))
    if len(atlas['voltage_upper_rows'])!=96*len(node_names):raise ValueError('GRID_TIME_NODE_AXIS')
    np.savez_compressed(STATIC/'ROW_ATLAS.npz',**atlas)
    atlas['domains']=domains
    # Required first diagnostic is the saved current certified optimal point.
    analyze(historical_master,raw,historical[2],historical[5],historical[9],atlas,OUT/'HISTORICAL_OPTIMAL_R2')
    atomic(OUT/'INITIAL_VERIFICATION.json',dict(PASS=True,state=record(STATIC/'INITIAL_STATE.pkl.gz'),
        original_snapshot_sha256=original.fingerprint(),phase1_snapshot_sha256=master.snapshot.fingerprint(),
        frozen_weights=previous['frozen_weights'],PR176_final_model=record(PR176_OUT/'M19/R3/MODEL_IDENTITY.json'),
        PR176_optimal_raw=rawrec,historical_included_point=record(STATIC/'HISTORICAL_INCLUDED_POINT.npz'),
        historical_point_witness=witness,retained_PR176_activations=48,weights_changed=False,native_calls=0))
    atomic(OUT/'ROW_ATTRIBUTION_AUTHORITY.json',dict(PASS=True,atlas=record(STATIC/'ROW_ATLAS.npz'),
        global_descriptor=record(STATIC/'GLOBAL_DESCRIPTOR.pkl.gz'),original_global_coefficients_equal=True,
        senses_equal=True,grid_CC4_nonresource_rhs_equal=True,resource_fixed_constant_rhs_differences=sorted(rhs_differences),
        coded_original_attributes=record(coded),coded_original_matrix=record(source_matrix),voltage_archive=voltage,planning_archive=planning,
        workload_class_exclusive_causality_asserted=False,optimization_calls=0,Fresh_AC=False))
    atomic(OUT/'RESIDUAL_POLICY.json',POLICY)
    atomic(OUT/'BASE_IDENTITY.json',dict(PASS=True,exact_base=BASE,base_PR=176,base_URL='https://github.com/BeaverVillage/MobileESS/pull/176'))
    (OUT/'PREREGISTRATION.md').write_text('''# May19 residual-directed migration-inclusive Phase-I

Base Draft PR176 exact1b34350663b972aeeaeb3a1c20596cbc0dd34b65. May19 only. A separate source-bound1200s permit retains every scientific equation, weight, objective, physical candidate, original solver parameter and tolerance. Threads1 per solve, max4 independent pricing processes. No P1, full A1, other dates, Planning/Actual/Fresh AC, production campaign, sweep, reset or automatic extension.

Start from the exact final PR176 model including all48 prior activations. The saved optimal R2 point is attributed first; its inclusion in the final expanded model is separately replayed. It is not called the optimum of the unsolved final expanded model. Obtain a new optimal initial Phase-I solve before freezing the new dual and selecting candidates. Raw points are never overwritten or clipped.

For each current optimal point, account every signed raw artificial contribution with the original frozen dyadic weights. Exact row families/time/nodes are verified against the original global scientific matrix and archived electrical node axis. Shared grid rows have no unique workload-class or AIDC causal allocation; report this explicitly. Resource/column influence rankings are heuristic derivatives from the original matrix, holding other global controls fixed. Neither feasibility nor exact negative rc uses the ranking heuristic.

Target the union of the top16 overall and top16 migration-capable classes by residual influence, deterministic class ID ties. For EVERY targeted class, run the complete exact compact MIGRATION-only native LP before the STAY-only native LP. Temporary q-sum=N /q-sum=0 query rows select the entire migration/STAY native subsets; the scientific pool is untouched. Independently certify both query dual bounds and physical candidates against the ORIGINAL full local model/couplings. Nonmigratable classes receive explicit no-physical-migration receipts. Charge every launched call, including worker failures.

Recover up to4 distinct valid negative STAY and2 migration class columns per target. Migration recovery uses the migration-only oracle point AND exact compact-block physical recovery until the quota or exhaustion. Prefix/tail/block-minimum calculations are exact rational representations of original binary64 coefficients. GPU horizons come from the original axis; no path/time cap or permanent deletion is introduced. Candidate rc must independently be below-1e-8; original membership/local feasibility/couplings must PASS. Record examined blocks/paths and incomplete/unmaterialized negatives; recovery quotas are not closure certificates.

Only after ALL targeted migration pricing/recovery completes, select up to64 concrete negatives. Prefer residual score, then exact rc, then stable identity. Deduplicate identical class+exact coupling effects. Include up to32 migration columns, with at most32 STAY while any verified migration remains. If fewer materialized migration candidates are available after completed targeted search, fill remaining capacity with STAY. Unmaterialized directions are not admissible columns and no exhaustive physical/mixed-fractional negative census is claimed.

Activate once and re-solve. At certified zero, replay artificial-free original rows/bounds and STOP. If relative raw certified-point Phi reduction is below1%, STOP as PHASE1_RESIDUAL_DIRECTED_NONMATERIAL. A raw increase with a feasible same-Phi inclusion witness is not real worsening; it still fails the1% materiality gate. Only reduction>=1% permits one additional batch if budget remains. Maximum two batches/three masters. A failed witness or uncertified numerical solve is NUMERICAL_INCONCLUSIVE. Budget/build/size stops are TRACTABILITY_FAIL, never scientific full-domain infeasibility.

Budget is max(elapsed wall since RUN_STARTED, sum of every native Runtime),1200s total for master build/solve, attribution/ranking, pricing, recovery and activation. Static reconstruction/qualification precedes execution; final persistence/cleanup overshoot is recorded. Keep original active cols200000, factor250M/2GB and half-complete auxiliary size guards. Preregister max100000 new native cols for this larger batch (engineering-only guard; old16-column growth cap is not reused). Stop on any guard, with no scientific candidate deletion.
''',encoding='utf8',newline='\n')
    print('RESIDUAL_STATIC_PREPARED',original.matrix.shape,ledger['receipt']['active_STAY'],flush=True)

def freeze():
    if (OUT/'SOURCE_FREEZE.json').exists():raise PermissionError('SOURCE_FREEZE_EXISTS')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();old=read(PR176_OUT/'SOURCE_FREEZE.json')
    sources=[]
    for r in old['source_files']:
        p=Path(r['path']);sources.append(ROOT/p.relative_to(PR176_ROOT) if p.is_relative_to(PR176_ROOT) else p)
    sources+=list((ROOT/'v42_a_stage_residual').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_residual.py']
    sources=list(dict.fromkeys(p.resolve() for p in sources))
    tree=subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True);blobs={l.split('\t',1)[1]:l.split()[2] for l in tree.splitlines()}
    legacy=[]
    for p in sources:
        if not p.is_relative_to(ROOT):continue
        rel=p.relative_to(ROOT).as_posix();b=p.read_bytes();actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=blobs.get(rel):
            actual=subprocess.check_output(['git','hash-object',str(p)],cwd=ROOT,text=True).strip()
            if actual!=blobs.get(rel):raise PermissionError('UNCOMMITTED_SOURCE:'+rel)
            legacy.append(rel)
    archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,'repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    gates=[OUT/name for name in ('INITIAL_VERIFICATION.json','ROW_ATTRIBUTION_AUTHORITY.json','SYNTHETIC_TESTS.json','PARALLEL_PRICING_EQUIVALENCE.json')]
    gates += [Path(r['path']) for r in read(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/CANARY_EXECUTION_PERMIT.json')['gate_receipts'].values()]
    if not all(read(p).get('PASS') is True for p in gates):raise PermissionError('PRE_RUN_GATE_FAIL')
    atomic(OUT/'SOURCE_FREEZE.json',dict(PASS=True,schema='MAY19_RESIDUAL_LP_1200_V1',git_head=head,exact_base=BASE,day=DAY,
        continuous_components=['PHASE_I','LOCAL_PRICING'],budget1200=True,execution_sources={str(p):sha(p) for p in sources},
        source_files=[record(p) for p in sources],source_archive=record(archive),gate_receipts=[record(p) for p in gates],
        legacy_checkout_filter_paths=legacy,solver_policy=record(ROOT/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'),
        policy=record(OUT/'RESIDUAL_POLICY.json'),historical_PR176_namespace_immutable=True))
    from .execution import verify
    verify();print('RESIDUAL_SOURCE_FROZEN',head,len(sources),flush=True)

if __name__=='__main__':
    import sys
    {'prepare':prepare,'freeze':freeze}[sys.argv[1]]()
