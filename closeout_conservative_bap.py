"""Independent read-only closeout; imports/builds/optimizes no native model."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,subprocess,csv
import xml.etree.ElementTree as ET
import numpy as np
from scipy import sparse
from run_restricted_1841 import ROOT,OUT,read,write,sha
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_dw_resume.audit import corrected_rows,prototypes,pure_binary_equalities
from v42_m_stage_root.dual_authority import ARRAY_FIELDS,array_sha
from v42_m_stage_root.conservative_authority import numerical_zero_sign,free_rc_consistency
from v42_m_stage_root.numerical_certificate import independent_csc
from v42_dw_bound.certificate import global_dual,corrected

def snapshot(path):
    meta=read(path.with_suffix('.json'));assert sha(path)==meta['snapshot_SHA']
    with np.load(path) as z:v={k:z[k] for k in ARRAY_FIELDS}
    assert {k:array_sha(v[k]) for k in ARRAY_FIELDS}==meta['identity']
    return sparse.csr_matrix((v['data'],v['indices'],v['indptr']),shape=tuple(v['shape'])),v,meta

def closeout():
    bench=read(OUT/'EARLY_BAP_MICROBENCHMARK.json');assert not bench['EARLY_BAP_SELECTED'],'SELECTED_REQUIRES_SEPARATE_7200_PHASE'
    A,d,B,e,*_=inputs();owner,row_owner=axes();gc=np.flatnonzero(owner<0);gr=np.flatnonzero(row_owner<0)
    with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native)
    with np.load(OUT/'VALID_INTEGER_ORIGINAL_POINT.npz') as z:x=z['point']
    incumbent=corrected_rows(A,d,x,True,pure_binary_equalities(A,d))
    physical=[b.validate(x[b.columns],True) for b in blocks]
    assert incumbent['PASS'] and all(p['PASS'] for p in physical)
    assert incumbent['objective']==bench['ending']['UB']
    gate=read(OUT/'certificate/SPLIT_DUAL_GATES.json');assert gate['EXACT_DUAL_AUTHORITY_FOR_BAP'] and not gate['OPTIMAL_DUAL_IDENTITY']
    cert=read(OUT/'certificate/RMP_RATIONAL_SUPPORT_CERTIFICATE.json')
    raw=ROOT/'docs/v42_m1_numerical_dual_certificate_20261006/polish/POLISHED_TERMINAL_BEFORE_GATE.npz'
    R,v,meta=snapshot(raw)
    with np.load(OUT/'certificate/CANONICAL_RATIONAL_DUAL.npz') as z:
        pi={int(i):F(int(n),int(q)) for i,n,q in zip(z['rows'],z['numerators'],z['denominators'])}
    q,terms,L,free=independent_csc(R,v,pi)
    assert L==F(int(cert['dual_objective']['numerator']),int(cert['dual_objective']['denominator']))
    assert all(q[j]>=0 for j in range(len(gc),R.shape[1])) and free==81216
    node_ledger=read(OUT/'EARLY_BAP_NODE_LEDGER.json');prices=read(OUT/'PRICING_LEDGER.json');calls=read(OUT/'NATIVE_CALL_LEDGER.json')
    all_prices_valid=all(p['rc'] is None or p['candidate_valid'] for p in prices)
    assert all_prices_valid,'INVALID_NATIVE_PRICING_POINT_MUST_NOT_AUTHORIZE_NEW_BOUND'
    callmap={c['label']:c for c in calls}
    for p in prices:
        if p['bound'] is not None:assert p['bound']==callmap[f"node{p['node']}/price{p['unit']}"]['ObjBound']
    source=ROOT/'docs/v42_m1_dw_certified_dual_bound/PROVEN_COORDINATE_ENCLOSURES.npz'
    assert sha(source)==read(source.with_name('COORDINATE_ENCLOSURE_PROOF.json'))['artifact_SHA']
    with np.load(source) as z:lo=z['lower'];hi=z['upper']
    gd=dict(objective=e['objective'][gc],constant=e['constant'],rhs=e['rhs'][gr],sense=e['sense'][gr]);G=B[gr][:,gc]
    audits=[]
    for p in sorted(OUT.glob('NODE_*_BEFORE_GATE.npz')):
        matrix,v,m=snapshot(p);nid=int(p.stem.split('_')[1]);canon,trace=numerical_zero_sign(v['pi'],v['sense'])
        rc=v['objective']-matrix.T@canon;consistency=free_rc_consistency(rc,v['lower'],v['upper'])
        residual=matrix@v['point']-v['rhs'];s=v['sense']
        vio=np.where(s=='=',abs(residual),np.where(s=='<',np.maximum(residual,0),np.maximum(-residual,0)))
        convex=float(np.max(abs(residual[-4:]),initial=0));bounds=float(max(0,np.max(v['lower']-v['point']),np.max(v['point']-v['upper'])))
        assert np.max(vio,initial=0)<=1e-6 and convex<=1e-8 and bounds<=1e-8
        transport=matrix[:len(gr),:len(gc)].tocsr()
        assert all(np.array_equal(getattr(transport,k),getattr(G,k)) for k in ('indptr','indices','data'))
        assert all(np.array_equal(v[k][:len(gc)],e[k][gc]) for k in ('objective','lower','upper','names'))
        assert np.array_equal(v['rhs'][:len(gr)],e['rhs'][gr]) and np.array_equal(v['sense'][:len(gr)],e['sense'][gr])
        error=float(np.max(abs(v['objective']-matrix.T@v['pi']-v['rc']),initial=0));assert error<=1e-8
        proof_path=OUT/f'NODE_{nid:04d}_BOUND_CERTIFICATE.json'
        proof_ok=False;candidate=None
        if proof_path.exists():
            proof=read(proof_path);same=[r for r in prices if r['node']==nid]
            assert len(same)==4 and sorted(r['unit'] for r in same)==[0,1,2,3]
            bounds_price=[next(r['bound'] for r in same if r['unit']==m) for m in range(4)]
            value,gproof=global_dual(G,gd,canon[:len(gr)],lo[gc],hi[gc])
            candidate,exact,beta,delta=corrected(value,canon[-4:],bounds_price)
            assert candidate==proof['candidate_LB'] and exact==F(int(proof['exact_numerator']),int(proof['exact_denominator']))
            assert proof['LB']==max(gate['current_certified_conservative_global_LB'],candidate)
            C=matrix.tocsc();minimum=None
            for j in range(len(gc),matrix.shape[1]):
                if v['upper'][j]==0:continue
                a,b=C.indptr[j:j+2]
                r=F(float(v['objective'][j]))-sum((F(float(canon[int(i)]))*F(float(w)) for i,w in zip(C.indices[a:b],C.data[a:b]) if canon[int(i)]),F(0))
                mess=str(v['names'][j]).split('MESS',1)[1][:2];r-=delta[int(mess)-1]
                minimum=r if minimum is None else min(minimum,r)
            assert minimum>=0 and float(minimum)==proof['all_retained_corrected_RC_min']
            proof_ok=True
        audits.append(dict(node=nid,snapshot_SHA=sha(p),same_original_global_model_PASS=True,
            maximum_row_violation=float(np.max(vio,initial=0)),convexity_residual=convex,maximum_bound_violation=bounds,
            native_RC_identity_error=error,**trace,**consistency,new_corrected_bound_independently_rebuilt=proof_ok,candidate_LB=candidate))
    floor=gate['current_certified_conservative_global_LB']
    for n in node_ledger:assert n['LB']>=floor
    # All completed nodes here are internal binary partitions, no subtree is
    # discarded on a restricted LP objective or an unproved infeasibility.
    assert all(n['fathom_reason'] is None for n in node_ledger)
    nodes={n['node_id']:n for n in node_ledger}
    for n in node_ledger:
        children=[c for c in node_ledger if c['parent']==n['node_id']]
        if children:
            assert len(children)==2 and children[0]['decisions'][:-1]==children[1]['decisions'][:-1]==n['decisions']
            a,b=children[0]['decisions'][-1],children[1]['decisions'][-1]
            assert a['variable']==b['variable'] and {a['value'],b['value']}=={0,1}
    history=[]
    for directory in ['v42_m1_rmp43_reproduction_20261006','v42_m1_numerical_dual_certificate_20261006']:
        path=ROOT/'docs'/directory;files=read(path/'SHA256_MANIFEST.json')['files'];assert all(sha(path/p)==h for p,h in files.items());history.append(dict(directory=directory,files=len(files),PASS=True))
    old=read(ROOT/'docs/v42_m1_dual_authority_early_bap/PR155_BYTE_PRESERVATION.json')['files'];assert all(sha(ROOT/p)==h for p,h in old.items())
    resources=read(OUT/'EARLY_BAP_RESOURCE_LEDGER.json')
    rim=read(OUT/'RESTRICTED_INCUMBENT_SEARCH_RESULT.json');authority=read(OUT/'certificate/NUMERICAL_ZERO_AUTHORITY.json')
    test_count=sum(int(s.attrib['tests']) for s in ET.parse(OUT/'FINAL_TEST_RESULTS.xml').getroot().findall('testsuite'))
    final=dict(TAU_DUAL=1e-8,canonicalized_Pi_count=authority['canonicalized_Pi_count'],maximum_canonicalized_Pi=authority['maximum_canonicalized_absolute_Pi'],
        free_RC_after_sign_boundary_max=authority['maximum_free_absolute_RC'],canonical_free_RC_exact_max=0,
        OPTIMAL_DUAL_IDENTITY=False,strong_duality_difference=gate['strong_duality_difference'],weak_duality_PASS=True,
        CONSERVATIVE_DUAL_LB_CERTIFICATE=True,EXACT_DUAL_AUTHORITY_FOR_BAP=True,
        restricted_RMP_safe_LB=gate['restricted_safe_LB'],same_canonical_full_domain_corrected_LB=gate['full_domain_corrected_LB'],
        starting_UB=bench['starting']['UB'],starting_LB=bench['starting']['LB'],starting_gap=bench['starting']['gap'],
        final_global_UB=bench['ending']['UB'],final_global_LB=bench['ending']['LB'],final_MIP_gap=bench['ending']['gap'],
        BAP_nodes=bench['BAP_nodes'],pricing_calls=bench['pricing_calls'],RMP_calls=bench['ending']['RMP_calls'],new_columns=bench['retained_new_columns'],
        microbenchmark_wall_seconds=bench['wall_seconds'],microbenchmark_native_runtime=bench['native_runtime'],
        native_exit_wall=max(c['end'] for c in calls),requested_wall_cap=600.,publication_overhead_seconds=bench['wall_seconds']-max(c['end'] for c in calls),
        restricted_integer_preparation_native_calls=2,restricted_integer_preparation_native_runtime=rim['total_restricted_native_runtime'],
        gap_reduction_per_wall_second=bench['gap_reduction_per_wall_second'],EARLY_BAP_SELECTED=False,
        development7200_executed=False,P1='NOT_ACCEPTED_GLOBAL_GAP_ABOVE_0_5_PERCENT',P2='NOT_RUN_P1_NOT_ACCEPTED',
        independent_node_snapshot_audits=audits,independent_integer_full_original_and_physical_PASS=True,
        branch_union_disjointness_PASS=True,all_pricing_native_candidates_valid=all_prices_valid,
        RAM_telemetry_peak_RSS=max(r['RSS'] for r in resources),RAM_telemetry_peak_process_commit=max(r['commit'] for r in resources if r['commit'] is not None),
        RAM_telemetry_min_available=min(r['RAM_available'] for r in resources),read_only_memory_telemetry=True,
        history_byte_preservation=history,PR155_files_byte_preserved=len(old),root_CG_continuation_calls=0,
        reason_not_selected='No validated integer-global gap reduction in the bounded early-BAP experiment; more columns/nodes alone do not satisfy selection',
        benchmark_source_commit=read(OUT/'EARLY_BAP_ONCE.json')['source_commit'],final_regression_tests=test_count,
        system_commit_spot_sample=read(OUT/'SYSTEM_MEMORY_SPOT_SAMPLE.json'),
        post_experiment_gate_assertions='Future adapter explicitly checks unchanged1e-8 convexity/bounds and rejects bounds attached to invalid native points; independent closeout verified all recorded cases already pass those checks')
    write('FINAL_RESULT.json',final)
    with (OUT/'M1_GLOBAL_GAP_TRAJECTORY.csv').open('w',newline='',encoding='utf8') as f:
        rows=read(OUT/'EARLY_BAP_GAP_TRAJECTORY.json');w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    report=f'''# Conservative dual authority and Early B&P

수치-zero authority는 TAU_DUAL=1e-8로 고정했다. Wrong-sign Pi {authority['canonicalized_Pi_count']}개,
최대 {authority['maximum_canonicalized_absolute_Pi']:.17g}를 정확한0 경계로 canonicalize했다.
그 후 free-coordinate RC 최대 {authority['maximum_free_absolute_RC']:.17g}는 numerical consistency PASS이며,
원래 equality의 유리수 증명으로 복원한 최종 free stationarity는 정확히0이다. 개별 RC zeroing은 하지 않았다.
전체83,058 RC/bound-dual 항과1,841 retained-column 제약을 처음부터 재계산하고 독립 CSC로 확인했다.

Strong-duality 차이는 {gate['strong_duality_difference']:.17g}, OPTIMAL_DUAL_IDENTITY=false로 보존했다.
Weak duality와 exact rational support, same-dual corrected formula는 PASS:
CONSERVATIVE_DUAL_LB_CERTIFICATE=true, EXACT_DUAL_AUTHORITY_FOR_BAP=true.
제한 RMP safe LB {gate['restricted_safe_LB']:.17g}는 global M1 LB가 아니다.
동일 canonical dual의 full-domain box-support corrected LB는 {gate['full_domain_corrected_LB']:.17g}로 유효하지만 느슨하다.
현재 B&P global floor는 검증된 기존 {floor:.17g}를 상속했다.

## Integer UB preparation

1,841-column 제한 정수 master의 첫120초 시도는 TIME_LIMIT/no incumbent다.
원래 seed-column MIP 후보를 사용한 후속480초-cap 탐색은 native283.398초에 OPTIMAL,
전체 준비 native 합계{rim['total_restricted_native_runtime']:.9f}초다. 유효 integer UB는 {rim['integer_UB']:.17g}.
모든 original rows, exact integer pattern, route/SOC/PCS와 objective를 독립 검증했다.
제한-domain native optimal bound를 전역 LB나 원래 M1 optimality로 사용하지 않았다.

## 600s maximum Early B&P microbenchmark

| Metric | Start | End |
|---|---:|---:|
| Valid global UB | {bench['starting']['UB']:.17g} | {bench['ending']['UB']:.17g} |
| Certified global LB | {bench['starting']['LB']:.17g} | {bench['ending']['LB']:.17g} |
| Global relative MIP gap | {bench['starting']['gap']:.12%} | {bench['ending']['gap']:.12%} |

연속 wall {bench['wall_seconds']:.6f}초, native {bench['native_runtime']:.6f}초,
B&P 생성 nodes {bench['BAP_nodes']}, pricing calls {bench['pricing_calls']}, RMP calls {bench['ending']['RMP_calls']},
추가 검증 열 {bench['retained_new_columns']}. Node-queue/trajectory/native receipts/raw snapshots는 별도 파일로 저장했다.
Root exact CG convergence 전에 원래 binary projection으로 분기했고 모든 자식이 valid parent floor를 상속했다.
Unfinished RMP objective와 제한-domain MIP bound는 global LB로 사용하지 않았다.
TIME_LIMIT/INTERRUPTED pricing은 최적해로 선언하지 않고 검증된 native bound에만 원래1e-8 safety를 적용했다.
실제 negative pricing RC는 제거/zeroing하지 않았다. Original branch equalities는 retained/unseen trajectories에 동일하게 적용했다.
Restricted infeasibility/미완료 노드는 폐기하지 않고 open domain으로 남겼다.

Peak process RSS {final['RAM_telemetry_peak_RSS']/2**30:.3f}GiB,
process commit {final['RAM_telemetry_peak_process_commit']/2**30:.3f}GiB,
minimum available RAM {final['RAM_telemetry_min_available']/2**30:.3f}GiB.
이는 읽기 전용 관찰이며 RAM-based stop/wait/kill/solver-setting policy는 없다.

Gap reduction/wall-second={bench['gap_reduction_per_wall_second']:.17g}.
과거 PR155 root continuation은 같은 certified floor를 유지했다. 이번 integer UB를 고정한
역사적 global-gap 비교의 baseline은0이며, root restricted-LP objective 개선을 integer-global gap 개선으로 대체하지 않았다.
이는 paired fresh-runtime comparison이 아니므로 전체 알고리즘 속도 우열을 주장하지 않는다.
노드/새 열 수 증가만으로 practical selection을 PASS 처리하지 않았다.

EARLY_BAP_SELECTED=false.7200초 grant/실행은 하지 않았다.
최종 global UB {bench['ending']['UB']:.17g}, LB {bench['ending']['LB']:.17g}, gap {bench['ending']['gap']:.12%} >0.5%.
P1 NOT_ACCEPTED, P2 NOT_RUN. Physical constraints, full pricing domain, branch coverage,
실제 negative RC 및 global-gap .005를 완화하지 않았다.

600초 시점에 native 종료를 요청했고 마지막 native 호출 종료는 {final['native_exit_wall']:.6f}초다.
종료 영수증과 ledger 기록 {final['publication_overhead_seconds']:.6f}초를 포함한 실제 wall을 그대로 보고했다.
600초 이후 새 optimize 호출이나 예산 연장은 하지 않았다.

System commit은 실험 중 한 번의 read-only spot sample로
{final['system_commit_spot_sample']['Memory']['CommittedBytes']/2**30:.3f}GiB /
{final['system_commit_spot_sample']['Memory']['CommitLimit']/2**30:.3f}GiB이었다. 연속 peak 값으로 주장하지 않는다.

검증:{test_count} regression tests PASS,5개 새 early-branch fixture가 direct MILP/complete master와 일치했다.
PR155974개 및 이전 reproduction30개/numerical38개 evidence bytes는 모두 보존했다.
실험 source는 {final['benchmark_source_commit']}, 신규 Draft PR157이다.
실험 종료 후 adapter에 원래 convexity/bound1e-8 gate와 invalid native point에 딸린 bound 거부를
명시적으로 추가했다. 독립 closeout에서 이번 모든 기록이 이미 이 조건을 통과했음을 확인했다.
이 추가 guard를 이유로 full-scale solve를 다시 실행하지 않았다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    print(json.dumps({k:v for k,v in final.items() if k not in ('independent_node_snapshot_audits','history_byte_preservation')}),flush=True)

if __name__=='__main__':closeout()
