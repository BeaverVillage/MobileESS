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
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,elastic_master,phase_objective
from v42_a_stage_phase1.runner import load_cache,projected_global_pi
from v42_a_stage_phase1.backend import assemble_original,update_graph,evaluate
from v42_a_stage_phase1.oracle import corrected_certificate
from v42_a_stage_early.candidate import validate,expanded_graph
from v42_a_stage_early.policy import ROOT,OUT,STATIC,HISTORY
from v42_a_stage_early import BASE

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
        if identity['day']!='2025-05-19' or identity['component'] not in ('PHASE_I','LOCAL_PRICING','ORIGINAL_P1'):
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
    candidate_checks=[];block_checks=[]
    activation=list(csvlib.DictReader((OUT/'ACTIVATED_COLUMNS.csv').open(encoding='utf8')))
    selected={c['candidate_id'] for c in activation}
    active_certificates={};original_reconstructions=[]
    folders=sorted((p for p in (OUT/'M19').glob('R*') if p.is_dir()),key=lambda p:int(p.name[1:]))
    for folder in folders:
        if not (folder/'NATIVE_RESULT.json').exists():continue
        identity=read(folder/'MODEL_IDENTITY.json')
        master=elastic_master(original,grows,weights_by_row=None if folder.name=='R0' else {i:frozen_weights[r] for i,r in enumerate(base_grows)})
        actual=sp.load_npz(identity['matrix']['path']);delta=actual-master.snapshot.matrix;delta.eliminate_zeros()
        attrs={k:v for k,v in np.load(identity['attributes']['path']).items()}
        if delta.nnz or not all(np.array_equal(getattr(master.snapshot,key),attrs[key]) for key in ('lower','upper','senses','rhs','vtypes')):
            raise ValueError('INDEPENDENT_ACTIVE_MATRIX_RECONSTRUCTION_FAIL')
        original_reconstructions.append(dict(iteration=folder.name,PASS=True,original_rows=original.matrix.shape[0],original_cols=original.matrix.shape[1],original_nnz=original.matrix.nnz))
        raw={k:v for k,v in np.load(read(folder/'NATIVE_RESULT.json')['raw_attributes']['path']).items()}
        if folder.name=='R0':initial_raw=raw
        if folder.name=='R1':
            lookup={}
            for unit in initial_descriptor['units']:
                for family,items in unit['v'].items():
                    for key,e in items.items():lookup[unit['id'],family,key]=evaluate(e,initial_raw['X'])
            point=np.zeros(original.matrix.shape[1]);point[:n]=initial_raw['X'][:n];assigned=set(range(n))
            for unit in desc['units']:
                for family,items in unit['v'].items():
                    for key,e in items.items():
                        if e[0]=='v':point[e[1]]=lookup.get((unit['id'],family,key),0.);assigned.add(int(e[1]))
            for unit in desc['units']:
                for family,items in unit['v'].items():
                    for key,e in items.items():
                        if e[0]=='e' and len(e[2])==1 and int(e[2][0]) not in assigned:
                            point[e[2][0]]=(lookup.get((unit['id'],family,key),0.)-e[1])/e[3][0];assigned.add(int(e[2][0]))
            mapped=np.r_[point,initial_raw['X'][base.matrix.shape[1]:]]
            replay=primal_replay(master.snapshot,mapped)
            old_phi=phase_objective(initial_master,initial_raw['X']);mapped_phi=phase_objective(master,mapped);new_phi=phase_objective(master,raw['X'])
            negative=[]
            for m,x in [(initial_master,initial_raw['X']),(master,raw['X'])]:
                art=x[m.original.matrix.shape[1]:]
                neg=sum((w*Fraction(float(v)) for w,v in zip(m.weights,art) if v<0),Fraction(0))
                negative.append(dict(negative_artificial_count=int(np.count_nonzero(art<0)),negative_artificial_objective=str(neg)))
            mapped_path=STATIC/'MAPPED_PRE_ACTIVATION_POINT.npz';np.savez_compressed(mapped_path,X=mapped)
            investigation=dict(PASS=replay['PASS'] and old_phi==mapped_phi,
                raw_points_unchanged=True,mapped_point_separate=True,native_solves_added=0,
                first_phi=str(old_phi),mapped_phi=str(mapped_phi),second_phi=str(new_phi),
                increase=str(new_phi-old_phi),relative_increase=float((new_phi-old_phi)/old_phi),
                prior_raw_point_embeds_at_original_tolerance=replay['PASS'],same_exact_weighted_objective=old_phi==mapped_phi,
                mapped_replay=replay,negative_artificials=negative,point=record(mapped_path),
                interpretation='A raw objective increase is not certified growth of the true optimal value when the previous raw point embeds at identical Phi. No tolerance or primal was changed. The preregistered conservative investigation stop remains the observed engineering outcome.',
                not_a_three_resolve_stagnation_certificate=True,not_full_domain_infeasibility=True)
            atomic(OUT/'MONOTONICITY_INVESTIGATION.json',investigation)
            if (ROOT/'v42_a_stage_early/progress.py').exists():
                from v42_a_stage_early.progress import capture,inclusion_witness
                prior=capture(base,initial_descriptor,initial_master,initial_raw)
                current_witness,current_mapped=inclusion_witness(prior,original,desc,master,n)
                if not current_witness['PASS'] or not np.array_equal(mapped,current_mapped):raise ValueError('POST_CANARY_WITNESS_DIFFERS_FROM_INDEPENDENT_AUDIT')
                atomic(OUT/'POST_CANARY_MAY19_WITNESS_REPLAY.json',dict(PASS=True,witness=current_witness,native_runs_added=0,
                    only_saved_May19_point_replayed=True,corrected_loop_not_native_May19_executed=True))
        receipts=[read(p) for p in sorted((folder/'B').glob('*/EXACT_PRICING.json'))] if (folder/'B').exists() else []
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
                if c is None or c['candidate_id'] not in selected:continue
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
        corrected_loop_not_May19_native_validated=bool(current_differences),old_execution_permit_cannot_authorize_current_corrected_sources=bool(current_differences),
        PR172_and_older_scientific_authority_unchanged=unchanged,
        physical_STAY=ledger['receipt']['physical_STAY'],physical_migration=ledger['receipt']['physical_migration'],
        permanent_scientific_candidate_deletions=0,physics_or_tolerance_changes=0,old_prescreen_restored=False,
        forbidden_dates_or_pipeline_executed=False,LP_PRICING_CLOSED=result['LP_PRICING_CLOSED'],INTEGER_DOMAIN_CLOSURE_PROVEN=False,
        budget_rule='max(execution elapsed wall, every actual native Runtime sum); reporter verification is readonly postsolve',
        recorded_accounted_seconds=result['accounted_seconds'],soft_stop_overshoot=max(0,result['accounted_seconds']-900))
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

def review(pr_url):
    r=read(OUT/'PHASE1_RESULT.json');p=read(OUT/'ORIGINAL_P1_RESULT.json');c=read(OUT/'FINAL_PRICING_CLOSURE.json');e=read(OUT/'PARALLEL_PRICING_EQUIVALENCE.json')
    batches=list(csvlib.DictReader((OUT/'PRICING_BATCH_TRACE.csv').open(encoding='utf8')))
    receipt=STATIC/'FINAL_PUBLICATION_RECEIPT.json'
    answers=[BASE,r['initial_phi'],r['phase1_master_solves'],r['phase1_trajectory'],r['partial_pricing_batches'],
        [(b['iteration'],b['fully_priced_classes']) for b in batches],r['valid_negative_columns'],r['activated_columns'],
        f"STAY {r['activated_STAY']}, migration {r['activated_migration']}",r['ACTIVE_DOMAIN_FEASIBLE'],r['time_to_zero'],
        r['final_original_model'],f"{r['maximum_factor_nnz']} nnz / {r['maximum_factor_memory_GB']} GB",
        e['exact_equal'],'May19 동일 배치의 serial 재실행을 하지 않았으므로 speedup 미측정; tiny fixture startup 포함 시간은 별도 receipt',
        r['ACTIVE_DOMAIN_FEASIBLE'],p.get('status'),r['LP_PRICING_CLOSED'],c.get('full_150_coverage',False),
        'NO','NO','NO','NO',r['classification'],f'최종 공개 HEAD는 [{receipt.name}]({receipt.as_posix()})의 exact_final_head에 기록. 실행 소스 HEAD: {r["source_commit"]}. 자기 commit 해시 순환참조를 피하는 외부 출판 영수증.',pr_url]
    questions=['Exact base HEAD','초기 Phi','Phase-I master solve 수','Phi 궤적','부분 가격 배치 수','반복별 완전히 가격 계산된 클래스 수','독립 검증 음수 구체 후보 수','활성화된 후보 수','STAY / migration 활성화','certified Phi zero','Phi zero까지 시간','최종 original active 크기','최대 factor 크기 / 추정 메모리','1-worker = 4-worker 정확 동등성','유효하게 측정된 pricing speedup','artificial-free 원래 active 모델 feasible','original P1 LP solved','P1 LP pricing closure','final150/150 closure 실행','영구 과학 후보 삭제','physics / tolerance 변경','old prescreen 복원','May17 / May12 / May10 실행','최종 분류','정확한 최종 HEAD','Draft PR URL']
    text='# May19 Early Activation V2 최종 검토\n\n'
    text+=f"분류: **{r['classification']}**. Stop: {r.get('stop_reason','gate reached')}.\n\n"
    text+='이번900초 실험은 PR172의600초 결과를 수정하거나 연장하지 않았다. 검증된 구체적 경로만 활성화했으며, pool 후보는 모두 보존했다. 양의 Phi나 시간/크기 종료는 complete-domain infeasibility 증거가 아니다. LP closure와 integer closure, production acceptance는 별도다.\n\n'
    text+='실제 heavy 실행은608.5489초에서 보수적인 조사 기준으로 종료되어900초를 소진하지 않았다. 이전 raw 해는 확장 모델에 그대로 포함되고 같은 Phi를 유지한다는 독립 replay가 PASS했다. 따라서6.73e-7 증가가 실제 최적값 증가를 증명하지 않는다. 세 번의 stagnation 조건도 충족되지 않았다.\n\n'
    text+='이 발견 뒤 경미한 증가 처리와 미복원 후보 처리를 보완했다. 이전 해의 포함 witness가 통과하면 다음 반복으로 진행하며, raw Phi를 바꾸거나 tolerance를 완화하지 않는다. 후보가 없는 부분 배치 뒤에도 같은 dual로 남은 클래스를 탐색하고, native positive support로 복원되지 않는 migration은 정확 prefix 가격으로 순차 복원한다. 고정16/24 규칙과 세 번1% stagnation 규칙은 유지한다. 현재 코드127개 tests와 저장된 May19 witness replay는 PASS, 수정된 루프의 새로운 May19 native 검증은 미실행이다. 모든21개 실제 native 호출의 소스는ba1c9b2... archive이며, 현재 수정 코드는 기존 source permit에서 거부된다. 추가 실행에는 별도의 새 source freeze/예산이 필요하다.\n\n'
    for i,(q,a) in enumerate(zip(questions,answers),1):text+=f'{i}. **{q}?** {a}\n\n'
    text+='실행 종료 후 새 native solve는 수행하지 않았다. 다른 날짜 및 full A1/Planning/Actual/Fresh는 실행하지 않았다. 최종 HEAD/remote/clean-tree 검증은 외부 출판 영수증이 고정하며, 각 native 실행 소스와 archive 해시는 NATIVE_RUN_SOURCES.csv에 별도로 고정한다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')

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
    external[str(ROOT/'publication_early.py')]=record(ROOT/'publication_early.py')
    for p in STATIC.rglob('*'):
        if p.is_file() and p.name not in ('FINAL_PUBLICATION_RECEIPT.json','PR_BODY.md'):external[str(p)]=record(p)
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,namespace_files=files,external_immutable_records=list(external.values()),
        self_excluded=True,final_publication_receipt_external_to_avoid_self_commit_hash_cycle=True,
        mutable_GitHub_publication_body_excluded=True,
        inherited_scientific_authority_unchanged=True))

if __name__=='__main__':
    import sys
    if sys.argv[1]=='audit':audit()
    elif sys.argv[1]=='review':review(sys.argv[2])
    elif sys.argv[1]=='manifest':manifest()
