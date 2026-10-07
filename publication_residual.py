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
from v42_a_stage_residual.policy import ROOT,OUT,STATIC,HISTORY
from v42_a_stage_residual import BASE
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
        print('RESIDUAL_AUDIT_NATIVE',len(calls),identity['component'],rec['status'],flush=True)
    actual_native=sum(c['native_seconds'] or 0 for c in calls)
    if abs(actual_native-result['native_seconds'])>1e-6 or len(calls)!=result['native_calls']:raise ValueError('DURABLE_NATIVE_LEDGER_MISMATCH')
    from dataclasses import replace
    from v42_a_stage_residual.query import migration_query,select
    from v42_a_stage_residual.attribution import analyze
    from v42_a_stage_phase1.runner import serial
    with gzip.open(STATIC/'INITIAL_STATE.pkl.gz','rb') as f:state=pickle.load(f)
    base,desc,data,domains,ledger,axes,n,grows,lrows,owned=state
    base_axes=dict(axes);base_grows=tuple(grows);original=base
    weights=np.load(read(OUT/'INITIAL_VERIFICATION.json')['frozen_weights']['path'])['weights']
    row_weights={};cursor=0
    for row in base_grows:
        row_weights[row]=Fraction(float(weights[cursor]));cursor+=2 if base.senses[row]=='=' else 1
    master=elastic_master(base,grows,weights_by_row=row_weights)
    point=np.load(STATIC/'HISTORICAL_INCLUDED_POINT.npz')['X'];prior=capture(original,desc,master,dict(X=point))
    atlas={k:v for k,v in np.load(STATIC/'ROW_ATLAS.npz').items()};atlas['domains']=domains
    roster={r['class_id']:r for r in read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    activation=list(csvlib.DictReader((OUT/'ACTIVATED_COLUMNS.csv').open(encoding='utf8')))
    candidate_checks=[];query_checks=[];potentials=[];reconstructions=[];witnesses=[];diagnostics=[];class_records=[]
    valid=set();last_optimal=None;queried_classes=set()
    for folder in sorted((OUT/'M19').glob('R*'),key=lambda p:int(p.name[1:])):
        if not folder.is_dir():continue
        master=elastic_master(original,grows,weights_by_row=row_weights)
        identity_path=folder/'MODEL_IDENTITY.json'
        if identity_path.exists():
            identity=read(identity_path);actual=sp.load_npz(identity['matrix']['path']);attrs=np.load(identity['attributes']['path'])
            delta=actual-master.snapshot.matrix;delta.eliminate_zeros()
            if delta.nnz or not all(np.array_equal(getattr(master.snapshot,k),attrs[k]) for k in ('lower','upper','senses','rhs','vtypes')):
                raise ValueError('INDEPENDENT_ACTIVE_MATRIX_RECONSTRUCTION_FAIL')
            expected_c=np.zeros(master.snapshot.matrix.shape[1])
            for j,v in master.snapshot.objectives[0].coefficients().items():expected_c[j]=float(v)
            if not np.array_equal(expected_c,attrs['objective']):raise ValueError('FROZEN_PHI_WEIGHT_RECONSTRUCTION_FAIL')
            reconstructions.append(dict(iteration=folder.name,PASS=True,original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz))
            del actual,attrs,delta
        witness,mapped=inclusion_witness(prior,original,desc,master,n)
        if not witness['PASS']:raise ValueError('PRIOR_POINT_INCLUSION_AUDIT_FAIL')
        saved=folder/'INCLUSION_WITNESS.json'
        if saved.exists():
            if not np.array_equal(mapped,np.load(read(saved)['separate_point']['path'])['X']):raise ValueError('SAVED_INCLUSION_POINT_DRIFT')
        witnesses.append(dict(iteration=folder.name,**witness))
        recpath=folder/'NATIVE_RESULT.json'
        if not recpath.exists():continue
        rec=read(recpath);raw={k:v for k,v in np.load(rec['raw_attributes']['path']).items()}
        if 'X' in raw:
            phi=phase_objective(master,raw['X']);zero=verify_zero(master,raw['X'])
            diagnostics.append(dict(iteration=folder.name,status=rec['status'],Phi=float(phi),exact_Phi=str(phi),certified_optimal=rec['status']==2,
                certified_zero=rec['status']==2 and zero['PASS'],original_artificial_free_PASS=zero['original_rows_and_bounds']['PASS']))
            if rec['status']==2:
                analyze(master,raw,data,axes,owned,atlas,folder/'POSTSOLVE_ATTRIBUTION')
                last_optimal=phi
                prior=capture(original,desc,master,raw)
        elif rec['status']==2:raise ValueError('OPTIMAL_MASTER_WITHOUT_RAW')
        query_paths=sorted(folder.rglob('EXACT_QUERY.json'))
        recovery_paths=sorted(folder.rglob('CONCRETE_RECOVERY.json'))
        byclass={}
        for p in query_paths:byclass.setdefault(read(p)['class_id'],[]).append(p)
        for p in recovery_paths:byclass.setdefault(read(p)['class_id'],[])
        queried_classes.update(byclass)
        round_candidates=[]
        if byclass:
            pi=projected_global_pi(master,raw['Pi']);cp=np.asarray([pi[r] for r in axes.values()])
            recovery={read(p)['class_id']:read(p) for p in recovery_paths}
            for key,paths in sorted(byclass.items()):
                cache=load_cache(roster[key]);uid=data[7]['classes'][key][0];N=len(data[7]['classes'][key])
                for p in paths:
                    receipt=read(p);query=migration_query(cache,N,receipt['kind'])
                    if not np.array_equal(cp,np.asarray(receipt['global_coupling_pi'])):raise ValueError('FROZEN_QUERY_PI_DRIFT')
                    cert=corrected_certificate(query,cache['B'],cp,np.asarray(receipt['local_raw_pi']))
                    if serial(cert)!=receipt['certificate'] or query.fingerprint()!=receipt['query_snapshot_sha256']:raise ValueError('EXACT_QUERY_AUDIT_FAIL')
                    query_checks.append(dict(class_id=key,kind=receipt['kind'],folder=str(p.parent),PASS=True,
                        physical_paths_covered=roster[key]['full_physical_migration' if receipt['kind']=='MIGRATION' else 'full_physical_STAY']))
                receipt=recovery.get(key)
                if receipt is None:continue
                cols=sorted(j for j,c in owned.items() if c==key);rows=list(lrows[key])
                active=replace(original,matrix=original.matrix[rows][:,cols].tocsr(),lower=original.lower[cols],upper=original.upper[cols],
                    senses=original.senses[rows],rhs=original.rhs[rows],vtypes=np.full(len(cols),'C'),objectives=cache['snapshot'].objectives)
                cert=corrected_certificate(active,original.matrix[list(axes.values())][:,cols],cp,pi[rows])
                if not cert['PASS'] or str(cert['exact_lower_bound'])!=receipt['active_local_lower_bound']:raise ValueError('INDEPENDENT_ACTIVE_NORMALIZATION_POTENTIAL_FAIL')
                if not np.array_equal(cp,np.asarray(receipt['global_coupling_pi'])):raise ValueError('RECOVERY_PI_DRIFT')
                potentials.append(dict(iteration=folder.name,class_id=key,PASS=True))
                class_records.append(dict(iteration=folder.name,**{k:v for k,v in receipt.items() if k not in ('candidates','migration_query_certificate','STAY_query_certificate','global_coupling_pi')}))
                for c in receipt['candidates']:
                    checked=validate(cache,data[1][uid],data[2][uid],data[3],domains[uid],data[4][uid],data[0],{k:i for i,k in enumerate(axes)},cp,N,receipt['active_local_lower_bound'],option_from_json(c['option']),key)
                    if checked['candidate_id']!=c['candidate_id'] or str(checked['price'])!=c['price'] or checked['coefficient_sha256']!=c['coefficient_sha256'] or checked['price']>=-Fraction(1,100000000):raise ValueError('CANDIDATE_AUDIT_FAIL')
                    checked['residual_score']=c['residual_score'];round_candidates.append(checked);valid.add(c['candidate_id'])
                    candidate_checks.append(dict(iteration=folder.name,class_id=key,candidate_id=c['candidate_id'],kind=c['kind'],exact_rc=c['price'],PASS=True))
        pricing=folder/'TARGETED/PRICING_RESULT.json'
        if pricing.exists():
            receipt=read(pricing)
            chosen=select(round_candidates,receipt['targeted_migration_search_completed'])
            if [c['candidate_id'] for c in chosen]!=[c['candidate_id'] for c in receipt['selected_candidates']]:raise ValueError('DETERMINISTIC_DIVERSIFIED_SELECTION_AUDIT_FAIL')
            expansion_stop=folder/'EXPANSION_STOP.json'
            if expansion_stop.exists() and 'cols' in read(expansion_stop):
                proposed=data;planned_ledger=ledger
                for c in chosen:
                    uid=data[7]['classes'][c['class_id']][0]
                    graph=expanded_graph(proposed[5][uid],c['option'],data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
                    proposed,planned_ledger=update_graph(proposed,domains,c['class_id'],graph)
                planned,pdesc,pgrows,_,_,_=assemble_original(base,base_grows,n,base_axes,proposed)
                stop=read(expansion_stop)
                if (planned.matrix.shape[0],planned.matrix.shape[1],planned.matrix.nnz)!=(stop['rows'],stop['cols'],stop['nnz']):raise ValueError('UNCOMMITTED_BATCH_SIZE_RECONSTRUCTION_FAIL')
                pmaster=elastic_master(planned,pgrows,weights_by_row=row_weights)
                pwitness,px=inclusion_witness(prior,planned,pdesc,pmaster,n)
                if not pwitness['PASS']:raise ValueError('UNCOMMITTED_BATCH_PRIOR_INCLUSION_FAIL')
                np.savez_compressed(STATIC/'UNCOMMITTED_BATCH_INCLUDED_POINT.npz',X=px)
                atomic(OUT/'UNCOMMITTED_BATCH_AUDIT.json',dict(PASS=True,selected_batch=len(chosen),STAY=sum(c['kind']=='STAY' for c in chosen),
                    migration=sum(c['kind']=='MIGRATION' for c in chosen),original_rows=stop['rows'],original_cols=stop['cols'],original_nnz=stop['nnz'],
                    new_columns=stop['cols']-original.matrix.shape[1],original_cols_limit=200000,new_columns_limit=100000,
                    original_snapshot_sha256=planned.fingerprint(),active_counts=planned_ledger['receipt'],committed=False,native_optimize_calls=0,
                    independently_reconstructed=True,prior_inclusion_witness=pwitness,separate_point=record(STATIC/'UNCOMMITTED_BATCH_INCLUDED_POINT.npz')))
                del planned,pmaster,pdesc,px,proposed
        selected=[a for a in activation if a['iteration']==folder.name[1:]]
        candidates_by_id={c['candidate_id']:c for c in round_candidates}
        for a in selected:
            if a['candidate_id'] not in candidates_by_id:raise ValueError('UNCERTIFIED_ACTIVATION')
            c=candidates_by_id[a['candidate_id']];uid=data[7]['classes'][c['class_id']][0]
            graph=expanded_graph(data[5][uid],c['option'],data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
            data,ledger=update_graph(data,domains,c['class_id'],graph)
        if selected:original,desc,grows,lrows,owned,axes=assemble_original(base,base_grows,n,base_axes,data)
    final_size=dict(rows=original.matrix.shape[0],cols=original.matrix.shape[1],nnz=original.matrix.nnz)
    if final_size!=result['final_original_model']:raise ValueError('FINAL_ACTIVE_MODEL_AUDIT_FAIL')
    final_master=elastic_master(original,grows,weights_by_row=row_weights);witness,mapped=inclusion_witness(prior,original,desc,final_master,n)
    if not witness['PASS']:raise ValueError('FINAL_PRIOR_POINT_INCLUSION_FAIL')
    np.savez_compressed(STATIC/'FINAL_PRESERVED_POINT.npz',X=mapped)
    witnesses.append(dict(iteration='FINAL_EXPANDED',**witness,separate_point=record(STATIC/'FINAL_PRESERVED_POINT.npz')))
    historical_paths=['v42_a_stage_phase1','v42_a_stage_early','docs/v42_a_stage_phase1_corrected_rerun_20261008','docs/v42_a_stage_phase1_early_activation_20261007','docs/v42_a_stage_phase1_pricing_20261007','docs/v42_a_stage_fast_active_domain_20261007']
    unchanged=not subprocess.check_output(['git','diff','--name-only',BASE,'--',*historical_paths],cwd=ROOT,text=True).strip()
    if not unchanged:raise ValueError('PR176_SCIENTIFIC_OR_HISTORY_CHANGED')
    verification=dict(PASS=True,source_archive_verified=True,executed_source_HEAD=freeze['git_head'],native_sources_unchanged=not current_differences,
        historical_PR176_scientific_authority_unchanged=True,native_calls=len(calls),native_seconds=actual_native,Work=sum(c['Work'] or 0 for c in calls),
        optimal_calls=sum(c['status']==2 for c in calls),nonoptimal_calls=sum(c['status']!=2 for c in calls),query_certificates_recomputed=len(query_checks),
        active_local_potentials_recomputed=len(potentials),valid_concrete_candidates_recomputed=len(candidate_checks),activated_columns=len(activation),
        master_matrix_reconstructions=reconstructions,prior_inclusion_witnesses=witnesses,physical_STAY=ledger['receipt']['physical_STAY'],
        physical_migration=ledger['receipt']['physical_migration'],retained_PR176_activations=48,permanent_candidate_deletions=0,
        physics_tolerance_or_Phi_weight_changes=0,May19_only=True,P1_calls=0,full_150_closure=False,production_or_Fresh_AC=False,
        single_1200_execution=True,accounted_seconds=result['accounted_seconds'],persistence_cleanup_overshoot=max(0.,result['accounted_seconds']-1200))
    atomic(OUT/'VERIFICATION.json',verification)
    atomic(OUT/'RAW_AND_CANDIDATE_AUDIT.json',dict(PASS=True,raw=raw_checks,queries=query_checks,candidates=candidate_checks,potentials=potentials))
    atomic(OUT/'MASTER_SOLVE_DIAGNOSTICS.json',dict(PASS=True,solves=diagnostics,prior_inclusion_witnesses=witnesses))
    atomic(OUT/'TARGETED_CLASS_AUDIT.json',dict(PASS=True,classes=class_records,unique_classes_queried=len(queried_classes),
        note='Complete native subset pricing is distinct from bounded physical recovery. Unmaterialized negative-block counts are unresolved negative-query directions, not an exhaustive physical negative census.'))
    table(OUT/'ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv',[dict(component=c['component'],folder=c['folder'],rows=c['rows'],cols=c['cols'],nnz=c['nnz'],factor_nnz=c['max_factor_nnz'],factor_memory_GB=c['max_factor_memory_GB'],RSS=c['peak_RSS_bytes']) for c in calls],
        ['component','folder','rows','cols','nnz','factor_nnz','factor_memory_GB','RSS'])
    atomic(STATIC/'AUDIT_EXTERNAL_RECORDS.json',dict(records=external))
    print('RESIDUAL_VERIFICATION_PASS',verification,flush=True)

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
    collect(read(HISTORY/'BLOCK_PRICING_ORACLE_VERIFICATION.json'))
    for p in STATIC.rglob('*'):
        if p.is_file() and p.name not in ('FINAL_PUBLICATION_RECEIPT.json','PR_BODY.md'):external[str(p)]=record(p)
    for name in ('publication_residual.py','review_residual.py'):external[str(ROOT/name)]=record(ROOT/name)
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,namespace_files=files,external_immutable_records=list(external.values()),self_excluded=True,
        final_publication_receipt_external_to_avoid_self_commit_hash_cycle=True,mutable_GitHub_publication_body_excluded=True))

if __name__=='__main__':
    import sys
    {'audit':audit,'manifest':manifest}[sys.argv[1]]()
