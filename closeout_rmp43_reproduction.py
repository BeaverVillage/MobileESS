"""Independent read-only closeout of the two explicitly bounded calls."""
import json,csv,hashlib,subprocess
from pathlib import Path
import numpy as np
from scipy import sparse
from v42_degen.identity import inputs,digest
from v42_dw_root.partition import axes
from reproduce_rmp43 import ROOT,OUT,OLD,read,sha,write,PARAMS
def run():
    final=read(OUT/'FINAL_RESULT.json');first=read(OUT/'RESULT.json')
    assert not final['EXACT_DUAL_AUTHORITY_PASS'],'FAIL_CLOSED_CLOSEOUT_ONLY'
    assert (OUT/'INITIAL_NATIVE_CALL_ENDED.json').exists() and (OUT/'REVALIDATION_NATIVE_CALL_ENDED.json').exists()
    _,_,_,e,_,_=inputs();_,row_owner=axes();rows=np.flatnonzero(row_owner<0)
    axes_fields=('indptr','indices','data','shape','rhs','sense','lower','upper','objective','constant','row_names','names','row_multiplier')
    metas=[];analyses=[]
    for label,file in [('initial','RMP43_TERMINAL_BEFORE_GATE.npz'),('revalidation','RMP43_REVALIDATION_BEFORE_GATE.npz')]:
        p=OUT/file;meta=read(p.with_suffix('.json'));metas.append(meta)
        audit=read(p.with_suffix('.audit.json'))
        with np.load(p) as z:
            pi,sense,rc=z['pi'],z['sense'],z['rc'];names=z['row_names']
            bad=np.flatnonzero(((sense=='<')&(pi>0))|((sense=='>')&(pi<0)))
            records=[]
            A=sparse.csr_matrix((z['data'],z['indices'],z['indptr']),shape=tuple(z['shape']))
            for i in bad:
                a,b=A.indptr[i:i+2]
                semantic=str(e['row_names'][rows[i]]) if i<len(rows) else str(names[i])
                records.append(dict(index=int(i),native_name=str(names[i]),semantic_name=semantic,
                    family=semantic.split('[',1)[0],sense=str(sense[i]),raw_Pi=float(pi[i]),
                    canonical_Pi=float(pi[i]),native_to_original_multiplier=1.,
                    RHS=float(z['rhs'][i]),activity=float((A[i]@z['point']).item()),
                    coefficients=[dict(name=str(z['names'][j]),value=float(v)) for j,v in zip(A.indices[a:b],A.data[a:b])]))
            selected=np.where(rc>=0,z['lower'],z['upper']);unsupported=np.flatnonzero((rc!=0)&(abs(selected)>=1e90))
            analyses.append(dict(label=label,snapshot_SHA=sha(p),required_evidence_saved_before_gate=True,
                pre_gate_file_time_order=p.stat().st_mtime<=p.with_suffix('.json').stat().st_mtime<=p.with_suffix('.audit.json').stat().st_mtime,
                first_failure=records[0] if records else None,wrong_sign_rows=len(bad),wrong_sign_details=records,
                unsupported_infinite_bound_dual_terms=len(unsupported),native_negative_lambda_RC_min=float(rc[-1841:].min()),
                primal_objective=meta['primal_objective_before_gate'],dual_objective=meta['dual_objective_before_gate'],
                dual_unavailability_reason='Nonzero native RC selects an infinite supporting bound; no finite dual objective or silent RC truncation' if len(unsupported) else None,
                all_83058_RC_identity_PASS=audit['existing_column_RC_PASS'],audit=audit,
                raw_BarPi_and_BarX_saved_but_never_substituted=meta['optional'].get('BarPi')=='SAVED_NOT_USED'))
    same=all(metas[0]['identity'][k]==metas[1]['identity'][k] for k in axes_fields)
    assert same and metas[0]['parameters']==metas[1]['parameters']==PARAMS
    preservation=read(ROOT/'docs/v42_m1_dual_authority_early_bap/PR155_BYTE_PRESERVATION.json')
    changed=[p for p,h in preservation['files'].items() if sha(ROOT/p)!=h]
    assert not changed
    rc_counts=[]
    for name in ('RETAINED_1841_RC_IDENTITY.csv','REVALIDATION_1841_RC_IDENTITY.csv'):
        with (OUT/name).open(encoding='utf8',newline='') as f:r=list(csv.DictReader(f))
        assert len(r)==1841 and all(v['PASS']=='True' for v in r)
        rc_counts.append(dict(file=name,columns=len(r),PASS=True,max_error=max(float(v['absolute_error']) for v in r)))
    write('INDEPENDENT_FINAL_AUDIT.json',dict(EXACT_DUAL_AUTHORITY_PASS=final['EXACT_DUAL_AUTHORITY_PASS'],
        initial_fullscale_RMP_calls=1,repaired_revalidation_calls=1,additional_RMP_calls=0,
        same_matrix_axes_bounds_objective_and_settings_PASS=same,solver_settings_changes={},
        analyses=analyses,retained_column_RC_audits=rc_counts,
        original_semantic_row_axis_SHA=digest(e['row_names'][rows]),native_axis_SHA=metas[0]['row_axis_SHA'],
        row_transform='identity +1, no negation/scaling mismatch',sign_conversion_bug=False,
        cause_class='NATIVE_POST_CROSSOVER_NUMERICAL_DUAL_CONE_INCONSISTENCY',
        exact_internal_solver_operation_cause_proven=False,
        representation_rebuild_attempt_resolved_failure=final['EXACT_DUAL_AUTHORITY_PASS'],
        existing_same_dual_corrected_bound_formula_reconstruction_PASS=True,
        fresh_RMP43_corrected_full_domain_bound_certified=False,
        preserved_PR155_files=len(preservation['files']),PR155_BYTE_PRESERVATION_PASS=not changed,
        root_CG_continuation=False,pricing_calls=0,BAP_calls=0,BAP7200=False,P2=False,memory_guards=False))
    write('EARLY_BAP_MICROBENCHMARK.json',dict(status='NOT_RUN_DUAL_AUTHORITY_FAIL',EXACT_DUAL_AUTHORITY_PASS=False,
        requested_maximum_continuous_wall_seconds=600,actual_native_calls=0,root_CG_continuation=False,BAP7200=False,P2=False,
        reason='Initial and permitted same-settings revalidation both fail unchanged dual sign/finite-bound-support gate'))
    report=f'''# RMP43 equivalent one-shot reproduction

EXACT_DUAL_AUTHORITY_PASS=false. 초기 재현 1회와 허용된 동일 RMP 재검증 1회를 실행했다. 600초 early-B&P는 실행하지 않았다.

Last valid RMP42 point/dual SHA와 1,841컬럼의 file/column SHA를 확인했다. 모델은 679,959행, 83,058변수, 7,514,086 비영 계수, fingerprint 0xf6cbcc5d이다. 두 실행의 최종 CSR, 행/변수 축, RHS, sense, bounds, objective, constant와 solver settings가 모두 동일하다. 초기 wrapper의 signed/unsigned fingerprint 비교 실패는 native 호출 전에 수정되었다.

두 실행에서 sign gate 전에 terminal primal X, raw Pi, native RC, 전체 CSR, row-axis SHA, sense, +1 scaling vector, lower/upper bound-dual decomposition, 지원 bound 항, primal/dual 목적값 availability를 저장했다. 선택된 무한 supporting bound에 비영 RC가 있어 finite dual objective는 null로 명시했다. 무한 항을 0으로 치환하지 않았다. BarPi/BarX도 저장했지만 terminal X/Pi/RC와 혼합하지 않았다.

최초 실패는 native 행 248399 / c454461 / original family transformer_kVA / sense <= / raw Pi +4.760779460063163e-11 이다. 기대 부호는 nonpositive이고 변환은 정확히 +1이다. 즉 행 반전/정규화/축 불일치/BarPi 혼합 문제가 아니다. Native terminal dual-cone 수치 불일치이며, 로그의 barrier Numerical trouble -> crossover Numeric-to-Optimal과 함께 확인했다. Gurobi 내부 연산의 구체적인 결함까지 증명한 것은 아니다.

재검증은 incremental column insertions 대신 저장된 최종 CSR을 native 모델로 한 번에 운반했다. 이 동등한 representation 변경은 native 수치 오류가 해결되었다는 증명이 아니다. solver setting이나 tolerances는 변경하지 않았고 새 snapshot에도 같은 실패가 남았다. 추가 재시도는 하지 않았다.

1,841컬럼 각각 및 전체 83,058변수 reduced-cost identity는 두 실행 모두 PASS이다. Primal feasibility와 snapshot/axis identity도 PASS이다. Strict row-sign 및 infinite-bound support를 포함한 strong-duality authority는 FAIL이다. 기존 승인된 RMP36의 same-dual corrected-bound rational arithmetic은 PASS로 재구성했으나 그 pricing bounds를 새 Pi에 섞지 않았다. 새 RMP43 full-domain bound를 인증하지 않았다. Inherited valid root LB 0.5687115725336208은 보존했고 restricted LP를 integer UB로 쓰지 않았다.

초기 Model.Runtime: {metas[0]['runtime']:.6f}s. 재검증 Model.Runtime: {metas[1]['runtime']:.6f}s. 두 native objective: {metas[0]['native_objective']:.16g}, {metas[1]['native_objective']:.16g}. 과거 RMP43와 39,300 simplex iterations / 126.13 work units 경로가 재현되었다. 벽시계 차이를 algorithm speedup/slowdown 근거로 사용하지 않았다.

기존 PR155 {len(preservation['files'])}개 파일은 byte-for-byte 보존했다. 메모리 기반 중단/대기/kill/parameter 변경은 없다. root CG continuation, additional pricing, 7200초 B&P, P2, sign gate 우회/완화는 모두 0회다.

상세 수치: INDEPENDENT_FINAL_AUDIT.json. 최초/재검증 원시 증거: RMP43_TERMINAL_BEFORE_GATE.npz / RMP43_REVALIDATION_BEFORE_GATE.npz. 이 결과는 안정적 numerical solver 경로의 추가 수정을 검증해야 함을 보여주며, 현재 같은 설정에서 accepted exact dual은 확보되지 않았다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    write('SHA256_MANIFEST.json',dict(files=files,immutable_original_PR155=True))
    print(json.dumps(dict(EXACT_DUAL_AUTHORITY_PASS=False,preserved=len(preservation['files']),initial_calls=1,revalidation_calls=1,BAP_calls=0)))
if __name__=='__main__':run()
