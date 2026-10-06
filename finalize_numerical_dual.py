"""Independent certificate closeout; no optimize calls and no model changes."""
from pathlib import Path
from fractions import Fraction as F
import json,csv,hashlib,time
import numpy as np
from scipy import sparse
from audit_numerical_dual import ROOT,OUT,RAW,read,write,sha,EPS
from v42_m_stage_root.numerical_certificate import independent_csc,down
from revalidate_rmp43 import canonical_rebuild
from polish_numerical_dual import SETTINGS

def run():
    POLISH=OUT/'polish';original=read(OUT/'RAW_NUMERICAL_AUDIT.json');after=read(POLISH/'RAW_NUMERICAL_AUDIT.json')
    first=read(OUT/'OFFLINE_CERTIFICATE_RESULT.json');last=read(POLISH/'FINAL_RESULT.json')
    snapshot=POLISH/'POLISHED_TERMINAL_BEFORE_GATE.npz';m0=read(RAW.with_suffix('.json'));m1=read(snapshot.with_suffix('.json'))
    fields=('indptr','indices','data','shape','rhs','sense','lower','upper','objective','constant','row_names','names','row_multiplier')
    same=all(m0['identity'][k]==m1['identity'][k] for k in fields);assert same
    assert last['native_solve_calls']==1 and last['additional_native_calls']==0
    # Read-only demonstration: model fingerprint also includes warm basis state.
    model,_,_=canonical_rebuild(snapshot);states=[dict(stage='cold_model',fingerprint=hex(model.Fingerprint&0xffffffff))]
    for k,value in SETTINGS.items():model.setParam(k,value)
    states.append(dict(stage='same_model_polish_parameters',fingerprint=hex(model.Fingerprint&0xffffffff)))
    with np.load(RAW) as z:vb=z['raw_VBasis'];cb=z['raw_CBasis']
    model.setAttr('VBasis',model.getVars(),vb.tolist());model.setAttr('CBasis',model.getConstrs(),cb.tolist());model.update()
    states.append(dict(stage='same_model_saved_basis_attached',fingerprint=hex(model.Fingerprint&0xffffffff)))
    model.reset(1);states.append(dict(stage='basis_reset_same_model',fingerprint=hex(model.Fingerprint&0xffffffff)));model.dispose()
    write('FINGERPRINT_BASIS_EFFECT.json',dict(PASS=states[0]['fingerprint']==states[-1]['fingerprint']=='0xf6cbcc5d',states=states,
        snapshot_scientific_array_SHA_identical=same,additional_optimize_calls=0,
        explanation='Observed fingerprint changes only when saved VBasis/CBasis is attached, and returns on reset; CSR/axes/RHS/objective/bounds remain identical'))
    with np.load(snapshot) as z:v={k:z[k] for k in z.files}
    A=sparse.csr_matrix((v['data'],v['indices'],v['indptr']),shape=tuple(v['shape']))
    with np.load(POLISH/'CANONICAL_RATIONAL_DUAL.npz') as z:
        pi={int(i):F(int(n),int(d)) for i,n,d in zip(z['rows'],z['numerators'],z['denominators'])}
    q,terms,dual,free=independent_csc(A,v,pi)
    cert=read(POLISH/'RMP_RATIONAL_SUPPORT_CERTIFICATE.json');assert dual==F(int(cert['dual_objective']['numerator']),int(cert['dual_objective']['denominator']))
    assert all(q[j]>=0 for j in range(A.shape[1]-1841,A.shape[1])) and free==81216
    primal=F(float(v['constant']))+sum((F(float(c))*F(float(x)) for c,x in zip(v['objective'],v['point']) if c),F(0))
    gap=primal-dual;safe=down(dual-F(EPS));assert safe==cert['safe_rational_LB'] and F(safe)<=dual
    numerical=abs(gap)<=F(EPS)
    assert not numerical and last['EXACT_DUAL_AUTHORITY_PASS'] is False
    comparison=[]
    for rec in original['infinite_support_variables']:
        j=rec['index'];comparison.append(dict(variable=rec['name'],index=j,raw_RC=rec['RC'],polished_native_RC=float(v['rc'][j]),
            canonical_RC=float(q[j]),canonical_RC_numerator=str(q[j].numerator),canonical_RC_denominator=str(q[j].denominator),
            exact_original_bound_support_valid=True))
    write('SEVEN_ORIGINAL_RC_COMPARISON.json',dict(variables=comparison,maximum_original_absolute_RC=max(abs(r['raw_RC']) for r in comparison),
        original_OptimalityTol=1e-8,polish_OptimalityTol=1e-9,seven_are_lower_bounded_lambda_not_free_coordinates=True))
    previous=read(ROOT/'docs/v42_m1_rmp43_reproduction_20261006/SHA256_MANIFEST.json')
    assert all(sha(ROOT/'docs/v42_m1_rmp43_reproduction_20261006'/p)==h for p,h in previous['files'].items())
    old=read(ROOT/'docs/v42_m1_dual_authority_early_bap/PR155_BYTE_PRESERVATION.json')
    assert all(sha(ROOT/p)==h for p,h in old['files'].items())
    full=read(POLISH/'FULL_DOMAIN_CORRECTED_LB_CERTIFICATE.json')
    final=dict(EXACT_DUAL_AUTHORITY_PASS=False,stage='FAIL_CLOSED_NUMERICAL_CERTIFICATE_GAP',
        offline_fullscale_native_calls=0,certificate_only_dual_simplex_native_calls=1,remaining_authorized_native_calls=0,
        raw_snapshot_preserved=True,prior_reproduction_files_preserved=True,original_PR155_files_preserved=len(old['files']),
        scientific_array_identity_PASS=same,native_quality=m1['native_quality_before_gate'],
        weak_duality_rational_lower_bound_PASS=True,retained_1841_exact_dual_feasibility_PASS=True,
        free_stationarity_exact_zero=free,canonical_primal_objective=float(primal),canonical_dual_objective=float(dual),
        canonical_primal_dual_difference=float(gap),unchanged_numerical_authority=EPS,numerical_agreement_PASS=numerical,
        restricted_RMP_safe_LB=safe,full_domain_corrected_LB_PASS=full['PASS'],full_domain_corrected_safe_LB=full['safe_corrected_LB'],
        inherited_valid_global_LB=full['aggregate_with_inherited_valid_floor'],restricted_LB_not_global_M1_LB=True,
        additional_pricing_calls=0,root_CG_continuation=False,early_BAP=False,BAP7200=False,P2=False,
        blocker='Exact canonical primal-dual gap 1.7415433958910485e-8 exceeds unchanged 1e-8; local residuals below OptimalityTol alone cannot authorize acceptance')
    write('FINAL_CERTIFICATE_DECISION.json',final)
    native=m1['native_quality_before_gate'];raw_values=original['values'];new_values=after['values']
    table='\n'.join(f"| `{r['variable']}` | {r['raw_RC']:.17g} | {r['polished_native_RC']:.17g} | {r['canonical_RC']:.17g} |" for r in comparison)
    family='\n'.join(f"| {k} | {w['maximum_sign_violation']:.17g} |" for k,w in original['max_sign_violation_by_family'].items())
    report=f'''# Numerical dual-certificate audit

EXACT_DUAL_AUTHORITY_PASS=false. Native solve 없는 최초 audit가 FAIL이어서, 명시적으로 허용된 certificate-only dual-simplex polish 1회만 실행했다. Native runtime 0.6309998035430908초, status OPTIMAL, iteration 0이다. 추가 native solve/CG/pricing/B&P/7200초/P2는 0회다.

## Raw numerical metrics

| Metric | Original independent reconstruction | Polished independent reconstruction | Polished native attribute |
|---|---:|---:|---:|
| Max sign violation | {raw_values['maximum_sign_violation']:.17g} | {new_values['maximum_sign_violation']:.17g} | row family census |
| DualVio | {raw_values['DualVio_reconstructed']:.17g} | {new_values['DualVio_reconstructed']:.17g} | {native['DualVio']:.17g} |
| DualResidual | {raw_values['DualResidual_reconstructed']:.17g} | {new_values['DualResidual_reconstructed']:.17g} | {native['DualResidual']:.17g} |
| ComplVio | {raw_values['ComplVio_reconstructed']:.17g} | {new_values['ComplVio_reconstructed']:.17g} | {native['ComplVio']:.17g} |
| Primal equality residual | {raw_values['primal_equality_residual']:.17g} | {new_values['primal_equality_residual']:.17g} | {native['ConstrResidual']:.17g} |

Original snapshot에 native DualVio/DualResidual/ComplVio가 저장되어 있지 않았으므로 값은 독립 재계산으로 명시했다. Polish snapshot에는 실제 native attribute를 sign gate 전에 저장했다. Native ComplVio와 재구성 값 차이는 내부 slack과 저장된 CSR의 외부 residual 계산을 구분해서 기록했다. 정의: [Gurobi quality attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html).

원래 OptimalityTol=1e-8, polish OptimalityTol=1e-9(강화)이다. Acceptance numerical authority는 1e-8로 유지했다. 원래 max sign violation/tolerance=0.004760779460063163, 원래 max unsupported RC/tolerance=0.06679351498978248. 이 값들만으로 PASS를 선언하지 않았다. Raw original-bound dual objective는 잘못된 sign 및 infinity support 때문에 유한하게 정의되지 않으며 raw primal-dual difference도 unavailable로 명시했다.

## Row-family maximum sign violation

| Family | Maximum original violation |
|---|---:|
{family}

최초 실패: c454461 / transformer_kVA / <=. Raw Pi +4.760779460063163e-11, RHS 245.1963201008076이다. 부호 boundary로 옮길 때 이 row의 RHS 항 변화만 약 1.167e-8이므로 작은 Pi 자체가 작은 목적값 오차를 보장하지 않는다.

## Seven originally invalid infinity supports

이 7개는 LB=0 / UB=infinity인 lambda이며 genuinely free 변수는 아니다. 원래 free global 좌표 81,216개는 별도로 확인했다.

| Variable | Original native RC | Polished native RC | Canonical rational RC (float display) |
|---|---:|---:|---:|
{table}

## Mathematical canonicalization and independent proof

원시 X/Pi/RC는 보존했다. 기존 authority 안에 있는 residual임을 확인한 뒤 positive <= Pi를 정확한 0 boundary로 옮겼다. 원래 triangular equality 81,216개에서 unrestricted equality dual을 유리수로 조정하여 free-coordinate stationarity를 정확히 0으로 만들었다. 각 MESS convexity equality dual을 해당 retained-column의 exact minimum RC만큼 낮춰, 1,841개 RC를 모두 정확히 nonnegative로 만들었다. RC를 직접 clipping하거나 infinity를 pseudo-finite 값으로 바꾸지 않았다. Objective/rows/bounds를 바꾸지 않았다.

전체 83,058 RC와 lower/upper dual 및 bound support 항을 처음부터 재계산했다. 독립 CSC-column Fraction 계산이 CSR-row 계산과 정확히 일치했다. Original bounds만으로 finite support를 구성해 weak-duality rational lower bound를 증명했다. 원래 full local domain의 coordinate interval support로 같은 canonical dual의 full-domain beta lower bounds도 계산했고 corrected formula를 독립 확인했다. 과거 다른 dual의 pricing bounds를 섞지 않았다.

Weak-duality proof와 1,841-column feasibility: PASS. 그러나 complete numerical authority: FAIL.

- Polish primal objective: {float(primal):.17g}
- Canonical rational dual objective: {float(dual):.17g}
- Primal-dual difference: {float(gap):.17g}, 기존 1e-8의 {float(gap)/EPS:.9f}배
- Restricted RMP safe LB (fixed1e-8 safety 후): {safe:.17g}; original M1 global LB로 쓰지 않는다.
- Full-domain analytic corrected LB: {full['safe_corrected_LB']:.17g}, 유효하지만 느슨하다.
- Inherited valid global LB: {full['aggregate_with_inherited_valid_floor']:.17g}, 유지했다. Root CG closure나 integer incumbent UB를 주장하지 않았다.

Polish setting changes: Method1, LPWarmStart1, Presolve0, NumericFocus3, Quad1, MarkowitzTol0.5, OptimalityTol1e-9. Same scientific CSR/axes/RHS/senses/objective/bounds의 SHA가 모두 일치한다. Saved native basis를 붙이면 fingerprint가 0xf6cbcc5d에서 0xb49886f2로 바뀌며 reset하면 돌아오는 것을 optimize 없이 관찰했다; scientific payload 변화가 아니다. `FINGERPRINT_BASIS_EFFECT.json`에 증거를 저장했다.

Same-coordinate transformer face row들도 검사했다. 실패 face 외 동일 두 좌표를 가진 15개 face의 Pi는 모두 0이고 slack이 있다. 이 local census에서는 stationarity/RHS를 보존하면서 부호만 교체할 co-active multiplier identity를 확보하지 못했다. 추가 solver 호출이나 acceptance 완화로 대체하지 않았다.

Original PR155 974개 파일과 이전 reproduction의 모든 manifest 대상 파일을 byte-for-byte 보존했다. Native snapshot 전에 native quality와 원시 벡터를 저장했고, rational dual/RC/bound 항/canonicalization trace와 전체 SHA manifest를 별도로 보관했다. 현재 blocker는 canonical objective agreement다. 허용된 polish 호출은 소진했으며 이후 계산은 시작하지 않았다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    print(json.dumps(final),flush=True)
if __name__=='__main__':run()
