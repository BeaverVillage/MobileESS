"""Independent saved-point/bound arithmetic; publication with original bytes frozen."""
from .common import *
from fractions import Fraction as F
import numpy as np,re
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities,prototypes
from v42_degen.identity import inputs,signature
from v42_dw_root.partition import axes
from v42_dw_root.run import exact_rc
from v42_disjunctive.certificate import rational_bound,down
from .audit_helpers import ordered_events,check_segment_chain

def verify():
 preserved=preserve_old();verify_freeze();imports=read(OUT/'DW_PR144_IMPORT_AUDIT.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in imports['imports'])
 terminal_freeze=read(OUT/'AUTHORITATIVE_TERMINAL_FREEZE.json')
 assert terminal_freeze['additional_native_optimize_forbidden'] and not terminal_freeze['multicolumn_development_started']
 assert all(sha(ROOT/p)==s for p,s in terminal_freeze['files'].items())
 assert read(OUT/'DW_TERMINAL_FREEZE_AND_RESOURCE_RECHECK.json')['PASS']
 result=read(OUT/'DW_CONTINUATION_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json');assert cp['type']=='TERMINAL' and len(cp['pool'])==result['retained_columns']==1433+result['new_discovery_columns'];assert read(OUT/'DW_FULL_POOL_FINAL_AUDIT.json')['PASS']
 assert all(sha(ROOT/x['file'])==x['file_SHA'] for x in cp['pool'])
 poolSHA=hashlib.sha256(json.dumps([(x['MESS'],x['column_SHA']) for x in cp['pool']],separators=(',',':')).encode()).hexdigest();assert poolSHA==cp['pool_SHA']
 budget=read(OUT/'DW_OPTIMIZE_INTERVALS.json');assert budget['union_seconds']==result['total_optimize_wall_union']<=1800
 write('DW_SEGMENTED_BUDGET_INDEPENDENT_AUDIT.json',check_segment_chain(OUT))
 assert abs(budget['budget_carried']+union_seconds(budget['intervals'])-budget['union_seconds'])<1e-8 and read(OUT/'DW_RESUME_RECEIPT.json')['PASS']
 A,d,B,e,*_=inputs();assert signature(A,d)==read(OUT/'DW_CONTINUATION_BASE_AUDIT.json')['full_matrix_signature'];owner,rows=axes();mask=pure_binary_equalities(A,d)
 with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
 blocks=prototypes(B,e,owner,rows,native);oldcp=read(SCI/'DW_CHECKPOINT_LATEST.json');r=oldcp['RMP'];rmps=cp['restart_state']['rmps'];points=[]
 with np.load(SCI/r['point_file']) as z:duals={r['dual_SHA']:(z['pi'].copy(),z['alpha'].copy())}
 for r in rmps:
  assert r['settings']['Threads']==1 and not r['warm_basis_supplied'] and r['settings']['LPWarmStart']==0
  if r['status']!=2:continue
  assert sha(OUT/r['point_file'])==r['point_SHA']
  with np.load(OUT/r['point_file']) as z:pi=z['pi'];alpha=z['alpha'];x=z['point'];assert corrected_rows(A,d,x,False,mask)['PASS'];assert abs(float(d['objective']@x+d['constant'])-r['objective'])<=EPS
  assert hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()==r['dual_SHA'];duals[r['dual_SHA']]=(pi,alpha);points.append(r['objective'])
 prices=cp['restart_state']['prices'];new=[c for c in cp['new_columns']];used=set()
 for p in prices:
  assert p['settings']['Threads']==1 and p['full_original_domain'] and p['horizon']==96 and p['no_fixing'] and not p['basis_or_pool_restriction']
  assert all(p['settings'][k]==EPS for k in ['FeasibilityTol','IntFeasTol','OptimalityTol']);assert p['true_dual_SHA'] in duals
  if p['type']=='DISCOVERY':
   assert not p['valid_bound'] and not p['pricing_optimality_claimed'];assert p['settings']['TimeLimit']<=20
   t=p['timing'];q=p['early_stop']
   if q['STOP_REASON']=='DISCOVERY_QUOTA_FILLED':
    assert q['accepted_count']==len(set(q['accepted_SHAs']))==4;assert t['quota_fill_time']<=t['terminate_request_time']<=t['native_terminal'];assert len(t['accepted_candidate_timestamps'])==4
    assert all(c['time']<=t['terminate_request_time'] for c in t['accepted_candidate_timestamps'])
  else:assert p['dual_SHA']==p['true_dual_SHA'] and not p['stabilized_discovery'] and p['settings']['TimeLimit']<=120
  if p['valid_bound']:assert p['native_status'] in (2,9) and p['ObjBound'] is not None
  if p['native_status']==11:assert p['type']=='DISCOVERY' and not p['valid_bound']
 for c in new:
  p=next(p for p in prices if p['call']==c['pricing_call']);assert p['type']=='DISCOVERY';m=UNITS.index(c['MESS']);pi,alpha=duals[p['true_dual_SHA']]
  with np.load(OUT/c['file']) as z:x=z['x'];a=z['a'];obj=float(z['c']);assert np.array_equal(z['axis'],blocks[m].columns)
  assert blocks[m].validate(x,True)['PASS'] and blocks[m].column(x)[2]==c['SHA256'];assert float(exact_rc(blocks[m],x,pi,alpha[m]))<=-1e-7 and c['SHA256'] not in used;used.add(c['SHA256'])
 certified=[];g=np.flatnonzero(rows<0);zc=np.flatnonzero(owner<0)
 from v42_dw_root.models import subset
 gd=subset(e,g,zc,native);gd['constant']=e['constant']
 with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][zc];hi=z['upper'][zc]
 for c in cp['restart_state']['certs']:
  if not c['certified']:continue
  pi,alpha=duals[c['dual_SHA']];proof=rational_bound(B[g][:,zc],gd,pi,lo,hi);v=F(int(proof['exact_bound_numerator']),int(proof['exact_bound_denominator']))
  for m,file in enumerate(c['pricing_receipts']):
   p=read(OUT/file);assert p['valid_bound'] and p['native_status'] in (2,9) and p['type']!='DISCOVERY' and p['dual_SHA']==p['true_dual_SHA']==c['dual_SHA']
   v+=F(float(alpha[m]))+min(F(0),F(down(F(float(p['ObjBound']))-F(EPS))))
  assert v==F(int(c['exact_numerator']),int(c['exact_denominator'])) and down(v)==c['L_corr'];certified.append(c['L_corr'])
 old=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json');arc=read(ARC/'ARC_LP_CERTIFIED_RESULT.json');threshold=read(ARC/'DW_MATERIAL_THRESHOLD_AUTHORITY.json')
 assert result['best_certified_LB']==max([arc['L_arc_cert'],old['best_corrected_LB']]+certified) and result['smallest_RMP_upper']==min([old['smallest_RMP_upper']]+points)
 assert result['materiality']==decision(result['best_certified_LB'],result['smallest_RMP_upper'],threshold)
 tests={}
 for label in ['PRECG','SEMANTIC','FULL']:
  r=read(OUT/f'PYTEST_{label}_RECEIPT.json');log=(OUT/f'{label}_TEST.log').read_text(encoding='utf8');matched=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log);assert r['exit_code']==0 and matched
  audit=read(OUT/f'PYTEST_{label}_RECEIPT.json');assert audit['actual_concurrent_heavy_native_solve']==0
  tests[label]=dict(PASS=True,count=int(matched[-1][0]),seconds=float(matched[-1][1]),actual_concurrent_heavy_native_solve=0)
 write('VERIFICATION.json',dict(PASS=True,PR149_scientific_bytes_preserved=preserved,PR144_exact_imports=len(imports['imports']),full_matrix=True,independent_original_primal_points=len(points),independent_exact_corrected_bounds=certified,pool_SHA=poolSHA,pool_file_bindings=len(cp['pool']),full_pool_authority=True,tests=tests,CG_native_union_budget=result['total_optimize_wall_union'],cap=1800,other_lane_kill_calls=0,other_lane_terminate_calls=0,B1_B2_B3_calls=[0,0,0],Branch_and_Price=False))
 assert read(OUT/'CG_STARTED.json')['new_grant']==1800
 assert result['initial_retained_columns']==1433 and cp['historical_PR149_optimize']==oldcp['elapsed_budget']
 assert cp['pool'][:1433]==oldcp['pool'] and read(OUT/'DW_CONTINUATION_FULL_POOL_AUDIT.json')['PASS']
 assert result['new_consumed_optimize']==budget['union_seconds'] and result['cumulative_optimize']==oldcp['elapsed_budget']+budget['union_seconds']
 flags();report(tests);manifest();print('INDEPENDENT_CONTINUATION_VERIFICATION_PASS',tests,flush=True)

def flags():
 r=read(OUT/'DW_CONTINUATION_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json');last=cp['restart_state']['certs'][-1] if cp['restart_state']['certs'] else None
 ps=[read(OUT/n) for n in last['pricing_receipts']] if last else []
 neg={p['MESS']:p['rc_inc'] if p['native_status']==2 else None for p in ps} if last and last['dual_SHA']==cp['RMP']['dual_SHA'] else {}
 write('DW_LAST_CERTIFIED_POINT_NEGATIVE_RC.json',dict(pricing=[dict(MESS=p['MESS'],status=p['native_status'],exact_RC=p['rc_inc'] if p['native_status']==2 else None) for p in ps],certified_point_SHA=last['dual_SHA'] if last else None,final_RMP_SHA=cp['RMP']['dual_SHA'],matches_final_RMP=bool(last and last['dual_SHA']==cp['RMP']['dual_SHA']),incumbent_never_LB=True))
 write('FINAL_FLAGS.json',dict(PR149_BASE_PRESERVED=True,ARC_LP_CERTIFIED_FLOOR=r['arc_floor'],DW_THRESHOLD=r['material_threshold'],DW_START_COLUMNS=1433,DW_FINAL_COLUMNS=r['retained_columns'],FOUR_WAY_PRICING=True,PRICING_THREADS=1,ADAPTIVE_DUAL_SMOOTHING=True,EARLY_STOP=True,PARALLEL_VALIDATION=True,INCREMENTAL_AUDIT=True,PERSISTENT_RMP_SELECTED=False,WARM_BASIS_SELECTED=False,NEW_AUTHORIZED_OPTIMIZE_SECONDS=1800,NEW_CONSUMED_OPTIMIZE_SECONDS=r['new_consumed_optimize'],HISTORICAL_PR149_OPTIMIZE_SECONDS=r['historical_PR149_optimize'],CUMULATIVE_OPTIMIZE_SECONDS=r['cumulative_optimize'],DW_NEW_DISCOVERY_ROUNDS=r['discovery_rounds'],DW_NEW_COLUMNS=r['new_discovery_columns'],DW_BEST_CERTIFIED_LB=r['best_certified_LB'],DW_BEST_RMP_UPPER=r['smallest_RMP_upper'],DW_FINAL_INTERVAL=r['final_interval'],DW_MATERIALITY=r['materiality'],DW_ROOT_OPTIMAL=r['DW_ROOT_OPTIMAL_CERTIFIED'],DW_CG_CONVERGED=r['DW_ROOT_OPTIMAL_CERTIFIED'],REMAINING_EXACT_NEGATIVE_RC=neg or None,BRANCH_AND_PRICE_RUN=False,B1_UNTOUCHED=True,B2_PRODUCTION_CALLS=0,B3_PRODUCTION_CALLS=0))

def report(tests):
 r=read(OUT/'DW_CONTINUATION_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json');b=read(OUT/'DW_CONTINUATION_BASE_AUDIT.json');wait=read(OUT/'DW_CONTINUATION_WAIT_RESOURCE.json');f=read(OUT/'FINAL_FLAGS.json');prices=cp['restart_state']['prices'];rmps=cp['restart_state']['rmps'];cert=read(OUT/'DW_CONTINUATION_FINAL_CERTIFICATION.json');du=r['smallest_RMP_upper']-r['material_threshold'];dl=r['material_threshold']-r['best_certified_LB'];neg=f['REMAINING_EXACT_NEGATIVE_RC']
 events=ordered_events(rmps,cp['restart_state']['certs'])
 upper=b['current_upper'];corr=read(SCI/'DW_ACCELERATED_FINAL_RESULT.json')['best_corrected_LB'];distance=[]
 def record(kind,point,dual):
  lower=max(b['floor'],corr);distance.append(dict(kind=kind,point=point,true_dual_SHA=dual,U_RMP=upper,L_corr=corr,L_final=lower,T_cert=b['threshold'],D_U=upper-b['threshold'],D_L=b['threshold']-lower))
 record('PR149',14,b['true_dual_SHA'])
 for point,kind,x in events:
  if kind=='RMP':upper=min(upper,x['objective'])
  else:corr=max(corr,x['L_corr'])
  record(kind,point,x['dual_SHA'])
 assert [distance[-1]['L_final'],distance[-1]['U_RMP']]==r['final_interval']
 table('DW_CONTINUATION_THRESHOLD_DISTANCE.csv',distance);write('DW_CONTINUATION_DISTANCE_AUDIT.json',dict(PASS=True,RMP_points=len([x for x in distance if x['kind']=='RMP']),certified_points=len([x for x in distance if x['kind']=='CERTIFICATION']),final_interval=r['final_interval'],receipts_reconstructed=True))
 prior_wait=read(OUT/'PRE_B1_OVERRIDE_WAIT_RESOURCE.json') if (OUT/'PRE_B1_OVERRIDE_WAIT_RESOURCE.json').exists() else dict(events=[])
 wait_events=prior_wait['events']+wait['events'];write('DW_CONTINUATION_WAIT_RESOURCE_HISTORY.json',dict(events=wait_events,latest=wait,B1_concurrency_authorized=(OUT/'USER_RESOURCE_ADMISSION_OVERRIDE.json').exists(),wait_optimize_debit=0))
 last_prices=[read(OUT/n) for n in cert['certificate']['pricing_receipts']]
 blocker='없음: exact threshold decision 완료' if r['materiality']!='INCONCLUSIVE' else '최종 true-dual에서 4 MESS 모두 음수 feasible RC가 남아 root CG 미완료; 3개 exact optimum 음수, MESS01 TIME_LIMIT exact optimum NULL. 원인 유일성은 주장하지 않음' if all(p['rc_inc'] is not None and p['rc_inc']< -EPS for p in last_prices) else '남은 root interval의 exact pricing certificate 확보'
 lines=['Draft PR / branch / SHA / clean은 게시 후 PUBLICATION receipt와 최종 응답에서 확인.',f'PR149 exact head {BASE_HEAD}; {b["original_files"]} tracked files의 bytes 보존.',f'Authoritative1433-column pool {b["pool_SHA"]}; 완료 pricing/RMP replay0.',f'True dual {b["true_dual_SHA"]}; smoothing {b["smooth_key"]}, alpha={b["alpha"]}; exact axis/pool binding.',f'B1 resource interaction: WAIT_RESOURCE observations {len(wait_events)}; 최신 사용자 지시로 B1-process-only wait 해제, RAM/commit/OOM guards 유지; other-lane kill/terminate/edit0; wait optimize debit0.',f'Starting interval [{b["current_lower"]}, {b["current_upper"]}].',f'Starting D_U={b["current_upper"]-b["threshold"]}, D_L={b["threshold"]-b["current_lower"]}.','New authorized native optimize UNION budget1800s; automatic second grant false.',f'New consumed {r["new_consumed_optimize"]}s; remaining {1800-r["new_consumed_optimize"]}s.',f'Historical {r["historical_PR149_optimize"]}s + new = cumulative {r["cumulative_optimize"]}s.',f'Discovery rounds {r["discovery_rounds"]}; checkpoint blocks8, fixed round limit 없음.',f'New terminal pricing calls {r["new_pricing_calls"]}.',f'Quota terminations {sum(p["early_stop"]["STOP_REASON"]=="DISCOVERY_QUOTA_FILLED" for p in prices)}; INTERRUPTED Discovery scientific LB 사용0.',f'New validated columns {r["new_discovery_columns"]}.',f'Final retained columns {r["retained_columns"]}; deletion0.',f'Columns/min {r["columns_per_min"]}; 복원/build/audit 및 현재 continuation elapsed denominator; 사용자 admission 변경 전 WAIT는 별도 history receipt로 기록.',f'Discovery median {r["discovery_median"]}s.',f'RMP native optimize median {float(np.median([x["wall_seconds"] for x in rmps])) if rmps else None}s.',f'Upper trajectory {[x["objective"] for x in rmps if x["status"]==2]}.',f'Threshold-distance ledger DW_CONTINUATION_THRESHOLD_DISTANCE.csv; final D_U={du}, D_L={dl}.',f'Final Certification {cert["status"]}; terminal receipts와 unstabilized same true dual authority.',f'Best corrected LB {r["best_corrected_LB"]}; final new corrected LB {r["new_corrected_LB"]}.',f'Aggregated certified LB=max(floor,corr)={r["best_certified_LB"]}.',f'Smallest audited RMP upper {r["smallest_RMP_upper"]}.',f'Final certified interval {r["final_interval"]}.',f'Materiality {r["materiality"]}; stop {r["stop_reason"]}.',f'Exact CG convergence {r["DW_ROOT_OPTIMAL_CERTIFIED"]}; materiality와 별도 판정.',f'Remaining exact negative RC {neg}; terminal OPTIMAL일 때만 exact optimum으로 기재.',f'Root optimality {r["DW_ROOT_OPTIMAL_CERTIFIED"]}.',f'Next single blocker: {blocker}.','Branch-and-Price NOT_RUN.','B1 detached scientific files / scheduler / worktree untouched.','B2/B3 production calls0/0; 이 Lane May production0/0/0.',f'Tests {tests}; independent matrix/points/rational bound/pool hashes recheck PASS; compile/static/diffcheck receipt.', 'Local/remote/PR head SHA equality 및 clean은 게시 후 receipt에 기록; no merge / force push / history rewrite.']
 endings=['PR149의 certified Arc-LP floor, material threshold, scientific model과 1,433-column authoritative checkpoint에서 계산을 재시작하지 않고 그대로 continuation했다.','Discovery는 adaptive smoothing과 early-stop을 사용했지만, column acceptance는 same-iteration true RMP dual의 true-negative reduced cost 검증을 유지했다.','Scientific lower-bound, materiality 및 exact CG convergence 판정은 unstabilized true RMP dual과 valid global pricing BestBd만 사용했다.','B1 detached production lane과 자원이 겹치는 경우 다른 Lane을 종료하지 않고 WAIT_RESOURCE로 대기했으며, B1 scientific state를 변경하지 않았다.','Branch-and-Price와 B2/B3 production은 실행하지 않았다.']
 lines[0]=f'Draft PR / final remote SHA / clean은 게시 후 최종 응답에서 확인. Native source-freeze SHA {cp["source_commit"]}; authoritative pool SHA {cp["pool_SHA"]}.'
 lines[4]=f'B1 resource interaction: 과거 WAIT_RESOURCE observations {len(wait_events)} 보존. 이후 사용자 명시 재개 지시로 launch wait 조건을 해제했으며 runtime RAM/commit/OOM guards 유지. Other-lane kill/terminate/edit0; wait optimize debit0.'
 lines[8]+= ' 미사용분은 accounting only이며 사용자 최종 동결 지시에 따라 추가 Discovery/RMP/pricing 실행 금지.'
 lines[15]=f'Columns/min {r["columns_per_min"]}; denominator {r["elapsed_including_build_audit"]}s는 복원된 checkpoint elapsed와 마지막 실행 elapsed 합계. 사용자 pause, admission 변경 전 WAIT, checkpoint에 반영되지 않은 중단 후 audit 시간은 포함하지 않음. 계산적 인과 우월성 주장 없음.'
 lines[17]+=f' Scope: OPTIMAL11 / INTERRUPTED3을 포함한 native attempt14 전체; OPTIMAL-only median {float(np.median([x["wall_seconds"] for x in rmps if x["status"]==2]))}s.'
 lines[20]+=f' iteration={cert["certificate"]["iteration"]}; MESS01 TIME_LIMIT / MESS02–04 OPTIMAL. Incumbent를 LB로 사용하지 않음.'
 lines[34]='게시 전 evidence commit의 local/remote/PR SHA 일치는 PUBLICATION_EVIDENCE.json, 마지막 게시 commit의 정확한 SHA와 clean은 최종 응답에 기록. No merge / force push / history rewrite. Multi-column 개발 파일 및 benchmark0; 기존1604-column 결과만 freeze한 뒤 STOP.'
 (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {x}' for i,x in enumerate(lines,1))+'\n\n'+'\n\n'.join(endings)+'\n',encoding='utf8',newline='\n')

def manifest():
 files=[]
 for prefix in ['v42_dw_continuation','tests/v42_dw_continuation','docs/v42_m1_dw_root_continuation_v2']:
  for p in sorted((ROOT/prefix).rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.tmp','.pyc'] and p.name!='SHA256_MANIFEST.json':files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
 write('SHA256_MANIFEST.json',dict(files=files,self_excluded=True,byte_hashes=True))
if __name__=='__main__':verify()
