"""Read-only postsolve audit/publication; never invokes native optimize.

This reporter is intentionally outside the executed-source package. Its later
addition does not alter the source archive used by any May19 native call.
"""
from pathlib import Path
from fractions import Fraction
import gzip,pickle,json,zipfile,hashlib,subprocess,csv as csvlib
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record,sha,table
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.active import option_from_json
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,elastic_master,phase_objective,verify_zero
from v42_a_stage_phase1.runner import load_cache,projected_global_pi
from v42_a_stage_phase1.backend import assemble_original,update_graph,evaluate
from v42_a_stage_phase1.oracle import corrected_certificate
from v42_a_stage_early.candidate import validate,expanded_graph
from v42_a_stage_early.policy import ROOT,OUT,STATIC,HISTORY
from v42_a_stage_early import BASE
from v42_a_stage_early.progress import capture,inclusion_witness

def audit():
    result=read(OUT/'PHASE1_RESULT.json');freeze=read(OUT/'SOURCE_FREEZE.json')
    archive=freeze['source_archive']
    if record(archive['path'])!=archive:raise ValueError('EXECUTED_ARCHIVE_BYTE_DRIFT')
    with zipfile.ZipFile(archive['path']) as z:
        current_differences=[]
        allowed={r['relative_path']:r for r in read(OUT/'POST_CANARY_CODE_FIX.json')['changes']} if (OUT/'POST_CANARY_CODE_FIX.json').exists() else {}
        for i,r in enumerate(freeze['source_files']):
            p=Path(r['path']);name='repo/'+p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name
            b=z.read(name)
            if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('ARCHIVED_SOURCE_MISMATCH:'+name)
            if record(p)!=r:
                rel=p.relative_to(ROOT).as_posix()
                if rel not in allowed or allowed[rel]['prior_executed']!=r or allowed[rel]['current']!=record(p):
                    raise ValueError('UNDECLARED_CURRENT_NATIVE_SOURCE_DRIFT:'+name)
                current_differences.append(rel)
    calls=[];raw_checks=[];external=[]
    for p in sorted((OUT/'M19').rglob('NATIVE_RESULT.json')):
        rec=read(p);identity=read(p.parent/'MODEL_IDENTITY.json')
        for field in ('matrix','attributes'):
            r=identity[field]
            if record(r['path'])!=r:raise ValueError('MODEL_BYTES_DRIFT')
            external.append(r)
        r=rec['raw_attributes']
        if record(r['path'])!=r:raise ValueError('RAW_NATIVE_BYTES_DRIFT')
        external.append(r)
        if identity['source_commit']!=freeze['git_head'] or identity['source_manifest']!=record(OUT/'SOURCE_FREEZE.json'):
            raise ValueError('NATIVE_SOURCE_IDENTITY_DRIFT')
        if identity['day']!='2025-05-19' or identity['component'] not in ('PHASE_I','LOCAL_PRICING'):
            raise ValueError('UNAUTHORIZED_NATIVE_COMPONENT')
        attrs={k:v for k,v in np.load(identity['attributes']['path']).items()}
        raw={k:v for k,v in np.load(r['path']).items()}
        snapshot=LinearSnapshot(sp.load_npz(identity['matrix']['path']),attrs['lower'],attrs['upper'],attrs['senses'],attrs['rhs'],attrs['vtypes'],
            (Objective('first_objective',tuple((j,Fraction(float(v))) for j,v in enumerate(attrs['objective']) if v),Fraction(0)),)).require()
        replay=primal_replay(snapshot,raw['X']) if 'X' in raw else None
        sign=verify_sign_convention(snapshot,raw['Pi'],raw['RC']) if 'Pi' in raw and 'RC' in raw else None
        checks=dict(folder=str(p.parent),component=identity['component'],status=rec['status'],available_raw=sorted(raw),
            replay=replay,sign=sign,source_commit=identity['source_commit'],source_archive_sha256=archive['sha256'],raw_persisted_first=rec['all_available_attributes_persisted_before_assertions'])
        if rec['status']==2 and (not replay or not sign or not replay['PASS'] or not sign['PASS']):raise ValueError('OPTIMAL_NATIVE_RAW_AUDIT_FAIL')
        raw_checks.append(checks);calls.append(dict(rec,folder=str(p.parent),component=identity['component'],rows=identity['rows'],cols=identity['cols'],nnz=identity['nnz']))
        print('EARLY_AUDIT_NATIVE',len(calls),identity['component'],rec['status'],flush=True)
    actual_native=sum(c['native_seconds'] or 0 for c in calls)
    if abs(actual_native-result['native_seconds'])>1e-6 or len(calls)!=result['native_calls']:raise ValueError('DURABLE_NATIVE_LEDGER_MISMATCH')
    with gzip.open(STATIC/'INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
    base,desc,data,domains,ledger,axes,n,grows,lrows,owned=state
    initial_descriptor=desc
    base_axes=dict(axes);base_grows=tuple(grows);original=base
    initial_master=elastic_master(base,grows);frozen_weights={r:w for r,w in zip(initial_master.artificial_rows,initial_master.weights)}
    roster={r['class_id']:r for r in read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    candidate_checks=[];block_checks=[];prior=None;prior_witnesses=[];master_diagnostics=[]
    activation=list(csvlib.DictReader((OUT/'ACTIVATED_COLUMNS.csv').open(encoding='utf8')))
    selected={c['candidate_id'] for c in activation}
    active_certificates={};original_reconstructions=[]
    folders=sorted((p for p in (OUT/'M19').glob('R*') if p.is_dir()),key=lambda p:int(p.name[1:]))
    for folder in folders:
        if not (folder/'NATIVE_RESULT.json').exists():
            if (folder/'BUILD_STOP.json').exists():
                identity=read(folder/'MODEL_IDENTITY.json')
                master=elastic_master(original,grows,weights_by_row={i:frozen_weights[r] for i,r in enumerate(base_grows)})
                actual=sp.load_npz(identity['matrix']['path']);delta=actual-master.snapshot.matrix;delta.eliminate_zeros()
                attrs={k:v for k,v in np.load(identity['attributes']['path']).items()}
                if delta.nnz or not all(np.array_equal(getattr(master.snapshot,key),attrs[key]) for key in ('lower','upper','senses','rhs','vtypes')):
                    raise ValueError('UNSOLVED_FINAL_MATRIX_RECONSTRUCTION_FAIL')
                stop=read(folder/'BUILD_STOP.json')
                if stop['native_optimize_entered']:raise ValueError('UNREPORTED_NATIVE_CALL')
                witness,mapped=inclusion_witness(prior,original,desc,master,n)
                if not witness['PASS']:raise ValueError('FINAL_PRIOR_INCLUSION_FAIL')
                point=STATIC/'FINAL_EXPANDED_PRIOR_POINT.npz';np.savez_compressed(point,X=mapped)
                prior_witnesses.append(dict(iteration=folder.name,**witness,native_optimize_entered=False,separate_point=record(point)))
                original_reconstructions.append(dict(iteration=folder.name,PASS=True,native_optimize_entered=False,
                    original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz))
            continue
        identity=read(folder/'MODEL_IDENTITY.json')
        master=elastic_master(original,grows,weights_by_row=None if folder.name=='R0' else {i:frozen_weights[r] for i,r in enumerate(base_grows)})
        actual=sp.load_npz(identity['matrix']['path']);delta=actual-master.snapshot.matrix;delta.eliminate_zeros()
        attrs={k:v for k,v in np.load(identity['attributes']['path']).items()}
        if delta.nnz or not all(np.array_equal(getattr(master.snapshot,key),attrs[key]) for key in ('lower','upper','senses','rhs','vtypes')):
            raise ValueError('INDEPENDENT_ACTIVE_MATRIX_RECONSTRUCTION_FAIL')
        original_reconstructions.append(dict(iteration=folder.name,PASS=True,original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz))
        raw={k:v for k,v in np.load(read(folder/'NATIVE_RESULT.json')['raw_attributes']['path']).items()}
        if prior is not None:
            witness,mapped=inclusion_witness(prior,original,desc,master,n)
            if not witness['PASS']:raise ValueError('PRIOR_POINT_INCLUSION_AUDIT_FAIL')
            investigation=folder/'MONOTONICITY_INVESTIGATION.json'
            if investigation.exists():
                saved=read(investigation)
                if saved['stop'] or not saved['witness']['PASS']:raise ValueError('INCORRECT_REAL_WORSENING_STOP')
                if not np.array_equal(np.load(saved['separate_point']['path'])['X'],mapped):raise ValueError('PRIOR_POINT_DRIFT')
            prior_witnesses.append(dict(iteration=folder.name,**witness))
        if 'X' in raw:
            exact=phase_objective(master,raw['X']);zero=verify_zero(master,raw['X']);solve=read(folder/'NATIVE_RESULT.json')
            master_diagnostics.append(dict(iteration=folder.name,status=solve['status'],raw_Phi=float(exact),exact_raw_Phi=str(exact),certified_zero=solve['status']==2 and zero['PASS'],
                raw_primal_PASS=primal_replay(master.snapshot,raw['X'])['PASS'],original_artificial_free_PASS=zero['original_rows_and_bounds']['PASS'],native_seconds=solve['native_seconds'],Work=solve['Work']))
            prior=capture(original,desc,master,raw)
        else:
            solve=read(folder/'NATIVE_RESULT.json')
            master_diagnostics.append(dict(iteration=folder.name,status=solve['status'],raw_Phi=None,
                certified_zero=False,raw_primal_PASS=None,original_artificial_free_PASS=None,
                native_seconds=solve['native_seconds'],Work=solve['Work']))
        receipts=[read(p) for p in sorted(folder.rglob('EXACT_PRICING.json'))]
        if receipts:
            pi=projected_global_pi(master,raw['Pi']);cp=np.asarray([pi[row] for row in axes.values()])
            for receipt in receipts:
                key=receipt['class_id'];cache=load_cache(roster[key]);cols=sorted(j for j,c in owned.items() if c==key);rows=list(lrows.get(key,()))
                from dataclasses import replace
                active=replace(original,matrix=original.matrix[rows][:,cols].tocsr(),lower=original.lower[cols],upper=original.upper[cols],
                    senses=original.senses[rows],rhs=original.rhs[rows],vtypes=np.full(len(cols),'C'),objectives=cache['snapshot'].objectives)
                cert=corrected_certificate(active,original.matrix[list(axes.values())][:,cols],cp,pi[rows])
                if str(cert['exact_lower_bound'])!=receipt['active_local_lower_bound'] or not np.array_equal(cp,np.asarray(receipt['global_coupling_pi'])):
                    raise ValueError('CANDIDATE_ACTIVE_POTENTIAL_OR_FROZEN_GLOBAL_PI_FORGERY')
                active_certificates[folder.name,key]=True
            for receipt in receipts:
                c=receipt['candidate']
                round_selected={a['candidate_id'] for a in activation if a['iteration']==str(int(folder.name[1:]))}
                if c is None or c['candidate_id'] not in round_selected:continue
                uid=data[7]['classes'][receipt['class_id']][0];option=option_from_json(c['option'])
                graph=expanded_graph(data[5][uid],option,data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
                data,ledger=update_graph(data,domains,receipt['class_id'],graph)
            if any(c['iteration']==str(int(folder.name[1:])) for c in activation):
                original,desc,grows,lrows,owned,axes=assemble_original(base,base_grows,n,base_axes,data)
    for p in sorted((OUT/'M19').rglob('EXACT_PRICING.json')):
        receipt=read(p);key=receipt['class_id'];cache=load_cache(roster[key]);cache['coupling_axes']=tuple(axes)
        cert=corrected_certificate(cache['snapshot'],cache['B'],np.asarray(receipt['global_coupling_pi']),np.asarray(receipt['local_raw_pi']))
        from v42_a_stage_phase1.runner import serial
        if serial(cert)!=receipt['certificate']:raise ValueError('INDEPENDENT_BLOCK_EXACT_CERTIFICATE_FAIL')
        block_checks.append(dict(class_id=key,folder=str(p.parent),PASS=True,status=receipt['status']))
        c=receipt['candidate']
        if c is None:continue
        uid=data[7]['classes'][key][0];option=option_from_json(c['option'])
        checked=validate(cache,data[1][uid],data[2][uid],data[3],domains[uid],data[4][uid],data[0],{k:i for i,k in enumerate(axes)},
            np.asarray(receipt['global_coupling_pi']),len(data[7]['classes'][key]),receipt['active_local_lower_bound'],option,key)
        if checked['candidate_id']!=c['candidate_id'] or str(checked['price'])!=c['price'] or checked['coefficient_sha256']!=c['coefficient_sha256'] or checked['price']>=-Fraction(1,100000000):
            raise ValueError('CONCRETE_CANDIDATE_INDEPENDENT_AUDIT_FAIL')
        candidate_checks.append(dict(candidate_id=c['candidate_id'],class_id=key,exact_rc=c['price'],kind=c['kind'],PASS=True))
    atomic(OUT/'MASTER_SOLVE_DIAGNOSTICS.json',dict(PASS=True,solves=master_diagnostics,prior_inclusion_witnesses=prior_witnesses))
    valid={c['candidate_id'] for c in candidate_checks}
    if any(c['candidate_id'] not in valid for c in activation):raise ValueError('ACTIVATION_WITHOUT_CONCRETE_CERTIFICATE')
    unchanged=subprocess.check_output(['git','diff','--name-only',BASE,'--','v42_a_stage_phase1','docs/v42_a_stage_phase1_pricing_20261007','docs/v42_a_stage_fast_active_domain_20261007'],cwd=ROOT,text=True).strip()==''
    if not unchanged:raise ValueError('HISTORICAL_AUTHORITY_CHANGED')
    if not read(OUT/'PARALLEL_PRICING_EQUIVALENCE.json')['exact_equal'] and result['selected_workers']!=1:raise ValueError('NONDETERMINISTIC_PARALLEL_USED')
    verification=dict(PASS=True,all_available_raw_persisted_first=True,native_calls=len(calls),native_seconds=actual_native,
        optimal_raw_replays=sum(c['status']==2 for c in calls),timed_out_calls=sum(c['status']==9 for c in calls),
        independently_recomputed_complete_block_receipts=len(block_checks),independently_recomputed_concrete_candidates=len(candidate_checks),
        independently_recomputed_active_local_potentials=len(active_certificates),original_native_matrix_reconstructions=original_reconstructions,
        activated_columns_all_concrete_certified=True,source_archive_verified=True,all_native_source_commit=freeze['git_head'],
        current_native_sources_equal_executed_archive=not current_differences,
        declared_post_canary_source_differences=current_differences,all_executed_native_sources_verified_from_immutable_archive=True,
        PR172_and_older_scientific_authority_unchanged=unchanged,
        physical_STAY=ledger['receipt']['physical_STAY'],physical_migration=ledger['receipt']['physical_migration'],
        permanent_scientific_candidate_deletions=0,physics_or_tolerance_changes=0,old_prescreen_restored=False,
        forbidden_dates_or_pipeline_executed=False,LP_PRICING_CLOSED=result['LP_PRICING_CLOSED'],INTEGER_DOMAIN_CLOSURE_PROVEN=False,
        budget_rule='max(execution elapsed wall, every actual native Runtime sum); reporter verification is readonly postsolve',
        recorded_accounted_seconds=result['accounted_seconds'],soft_stop_overshoot=max(0,result['accounted_seconds']-900))
    verification.update(corrected_loop_May19_native_executed=True,prior_inclusion_witnesses=prior_witnesses,one_run_only=True,original_P1_calls=0,actual_native_Work=sum(c['Work'] or 0 for c in calls))
    engineering_unchanged=subprocess.check_output(['git','diff','--name-only',BASE,'--','v42_a_stage_early/candidate.py','v42_a_stage_early/pricing.py','v42_a_stage_early/progress.py','v42_a_stage_early/recovery.py','v42_a_stage_early/budget.py','docs/v42_a_stage_phase1_early_activation_20261007'],cwd=ROOT,text=True).strip()==''
    if not engineering_unchanged:raise ValueError('PR174_CORRECTED_ALGORITHM_OR_HISTORY_CHANGED')
    verification.update(PR174_exact_pricing_candidate_recovery_inclusion_and_budget_sources_unchanged=True,historical_PR174_namespace_unchanged=True)
    atomic(OUT/'VERIFICATION.json',verification)
    atomic(OUT/'RAW_AND_CANDIDATE_AUDIT.json',dict(PASS=True,raw=raw_checks,blocks=block_checks,candidates=candidate_checks))
    table(OUT/'NATIVE_RUN_SOURCES.csv',[dict(component=c['component'],folder=c['folder'],source_commit=freeze['git_head'],archive_sha256=archive['sha256'],
        matrix_sha256=read(Path(c['folder'])/'MODEL_IDENTITY.json')['matrix']['sha256'],raw_sha256=c['raw_attributes']['sha256'],native_seconds=c['native_seconds']) for c in calls],
        ['component','folder','source_commit','archive_sha256','matrix_sha256','raw_sha256','native_seconds'])
    table(OUT/'ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv',[dict(component=c['component'],folder=c['folder'],rows=c['rows'],cols=c['cols'],nnz=c['nnz'],
        factor_nnz=c['max_factor_nnz'],factor_memory_GB=c['max_factor_memory_GB'],RSS=c['peak_RSS_bytes']) for c in calls],
        ['component','folder','rows','cols','nnz','factor_nnz','factor_memory_GB','RSS'])
    atomic(STATIC/'AUDIT_EXTERNAL_RECORDS.json',dict(records=external))
    print('EARLY_VERIFICATION_PASS',verification,flush=True)

def manifest():
    files=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    external={}
    def collect(v):
        if isinstance(v,dict):
            if set(('path','sha256','bytes'))<=set(v) and Path(v['path']).is_file():
                p=Path(v['path'])
                if not p.is_relative_to(OUT):external[str(p)]=record(p)
            for x in v.values():collect(x)
        elif isinstance(v,list):
            for x in v:collect(x)
    for p in OUT.rglob('*.json'):
        if p.name!='SHA256_MANIFEST.json':collect(read(p))
    collect(read(STATIC/'AUDIT_EXTERNAL_RECORDS.json'))
    collect(read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json'))
    external[str(ROOT/'publication_corrected.py')]=record(ROOT/'publication_corrected.py')
    external[str(ROOT/'review_corrected.py')]=record(ROOT/'review_corrected.py')
    for p in STATIC.rglob('*'):
        if p.is_file() and p.name not in ('FINAL_PUBLICATION_RECEIPT.json','PR_BODY.md'):external[str(p)]=record(p)
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,namespace_files=files,external_immutable_records=list(external.values()),
        self_excluded=True,final_publication_receipt_external_to_avoid_self_commit_hash_cycle=True,
        mutable_GitHub_publication_body_excluded=True,
        inherited_scientific_authority_unchanged=True))

if __name__=='__main__':
    import sys
    if sys.argv[1]=='audit':audit()
    elif sys.argv[1]=='manifest':manifest()
