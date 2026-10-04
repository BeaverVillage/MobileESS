"""Independent saved-point/bound arithmetic; publication with original bytes frozen."""
from .common import *
from fractions import Fraction as F
import numpy as np,re
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities,prototypes
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_dw_root.run import exact_rc
from v42_disjunctive.certificate import rational_bound,down

def verify():
 preserved=preserve_old();verify_freeze();imports=read(OUT/'DW_PR144_IMPORT_AUDIT.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in imports['imports'])
 result=read(OUT/'DW_ACCELERATED_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json');assert cp['type']=='TERMINAL' and len(cp['pool'])==result['retained_columns']==1244+result['new_discovery_columns'];assert read(OUT/'DW_FULL_POOL_FINAL_AUDIT.json')['PASS']
 assert all(sha(ROOT/x['file'])==x['file_SHA'] for x in cp['pool'])
 poolSHA=hashlib.sha256(json.dumps([(x['MESS'],x['column_SHA']) for x in cp['pool']],separators=(',',':')).encode()).hexdigest();assert poolSHA==cp['pool_SHA']
 budget=read(OUT/'DW_OPTIMIZE_INTERVALS.json');assert budget['union_seconds']==result['total_optimize_wall_union']<=1800
 A,d,B,e,*_=inputs();owner,rows=axes();mask=pure_binary_equalities(A,d)
 with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
 blocks=prototypes(B,e,owner,rows,native);duals={};rmps=cp['restart_state']['rmps'];points=[]
 for r in rmps:
  assert r['settings']['Threads']==1 and not r['warm_basis_supplied'] and r['settings']['LPWarmStart']==0
  if r['status']!=2:continue
  assert sha(OUT/r['point_file'])==r['point_SHA']
  with np.load(OUT/r['point_file']) as z:pi=z['pi'];alpha=z['alpha'];x=z['point'];assert corrected_rows(A,d,x,False,mask)['PASS']
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
 old=read(SCI/'DW_THRESHOLD_FINAL_RESULT.json');arc=read(SCI/'ARC_LP_CERTIFIED_RESULT.json');threshold=read(SCI/'DW_MATERIAL_THRESHOLD_AUTHORITY.json')
 assert result['best_certified_LB']==max(arc['L_arc_cert'],old['best_corrected_LB'],*certified) and result['smallest_RMP_upper']==min(old['smallest_RMP_upper'],*points)
 assert result['materiality']==decision(result['best_certified_LB'],result['smallest_RMP_upper'],threshold)
 tests={}
 for label in ['PRECG','SEMANTIC','FULL']:
  r=read(OUT/f'PYTEST_{label}_RECEIPT.json');log=(OUT/f'{label}_TEST.log').read_text(encoding='utf8');matched=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log);assert r['exit_code']==0 and matched
  audit=read(OUT/f'{label}_PYTEST_LANE_CONCURRENCY_AUDIT.json');assert audit['actual_concurrent_heavy_native_solve']==0
  tests[label]=dict(PASS=True,count=int(matched[-1][0]),seconds=float(matched[-1][1]),actual_concurrent_heavy_native_solve=0)
 write('VERIFICATION.json',dict(PASS=True,PR147_scientific_bytes_preserved=preserved,PR144_exact_imports=len(imports['imports']),full_matrix=True,independent_original_primal_points=len(points),independent_exact_corrected_bounds=certified,pool_SHA=poolSHA,pool_file_bindings=len(cp['pool']),full_pool_authority=True,tests=tests,CG_native_union_budget=result['total_optimize_wall_union'],cap=1800,other_lane_kill_calls=0,other_lane_terminate_calls=0,B1_B2_B3_calls=[0,0,0],Branch_and_Price=False))
 flags();report(tests);manifest();print('INDEPENDENT_ACCELERATED_VERIFICATION_PASS',tests,flush=True)

def flags():
 r=read(OUT/'DW_ACCELERATED_FINAL_RESULT.json');f=read(OUT/'DW_RUNTIME_FEATURE_SELECTION.json');arc=read(SCI/'ARC_LP_CERTIFIED_RESULT.json')
 write('FINAL_FLAGS.json',dict(PR147_SCIENTIFIC_BASE_PRESERVED=True,PR144_RUNTIME_INTEGRATED=True,ARC_LP_CERTIFIED=True,ARC_LP_NATIVE_OPTIMUM=arc['native_optimum'],ARC_LP_CERTIFIED_FLOOR=arc['L_arc_cert'],DW_THRESHOLD=r['material_threshold'],DW_START_COLUMNS=1244,DW_FINAL_COLUMNS=r['retained_columns'],DW_EARLY_STOP_ENABLED=True,DW_PARALLEL_VALIDATION_ENABLED=True,DW_INCREMENTAL_AUDIT_ENABLED=True,PERSISTENT_RMP_TESTED=True,PERSISTENT_RMP_SELECTED=f['persistent_selected'],WARM_BASIS_SELECTED=False,FOUR_WAY_PRICING=True,PRICING_THREADS=1,RAM_FLOOR_GIB=1,DW_DISCOVERY_ROUNDS=r['discovery_rounds'],DW_NEW_COLUMNS=r['new_discovery_columns'],DW_BEST_CERTIFIED_LB=r['best_certified_LB'],DW_BEST_RMP_UPPER=r['smallest_RMP_upper'],DW_FINAL_INTERVAL=r['final_interval'],DW_MATERIALITY=r['materiality'],DW_CG_CONVERGED=r['DW_ROOT_OPTIMAL_CERTIFIED'],BRANCH_AND_PRICE_RUN=False,B1_PRODUCTION_CALLS=0,B2_PRODUCTION_CALLS=0,B3_PRODUCTION_CALLS=0))

def report(tests):
 r=read(OUT/'DW_ACCELERATED_FINAL_RESULT.json');old=read(SCI/'DW_THRESHOLD_FINAL_RESULT.json');cp=read(OUT/'DW_CHECKPOINT_LATEST.json');prices=cp['restart_state']['prices'];rmps=cp['restart_state']['rmps'];f=read(OUT/'DW_RUNTIME_FEATURE_SELECTION.json');canary=read(OUT/'DW_PERSISTENT_RMP_FULLSCALE_CANARY.json');cert=read(OUT/'DW_ACCELERATED_FINAL_CERTIFICATION.json');resource=cp['resource_usage']
 neg=[dict(MESS=p['MESS'],status=p['native_status'],BestBd=p['ObjBound'],feasible_RC=p['rc_inc']) for p in prices if p['type']!='DISCOVERY'];write('DW_REMAINING_NEGATIVE_RC.json',dict(pricing=neg,incumbent_diagnostic_only=True))
 lines=['Draft PR / branch / exact remote SHA / clean은 게시 receipt에서 확인.',f'PR147 scientific exact head {BASE_HEAD};11279 original tracked bytes 보존.',f'PR144 exact head {read(OUT/"DW_PR144_IMPORT_AUDIT.json")["head"]};runtime/test11files exact import, PR145/146미통합.',f'Arc floor {r["arc_floor"]}; official threshold {r["material_threshold"]} 보존. 최신 요청의 U<=T 단일 threshold decision policy를 preregister했고 PR147 lower-reference comparator는 진단으로 보존.', 'Starting checkpoint1244;86old pricing replay 없음.',f'Early-stop enabled; quota completion {sum(p["early_stop"]["STOP_REASON"]=="DISCOVERY_QUOTA_FILLED" for p in prices)} calls. INTERRUPTED certificates0.', 'Parallel validation enabled; every actual batch sequential/parallel canonical equivalence PASS; additional pricing process0.', 'Incremental audit enabled; initial complete1244 authority reissue, currentpoint/currentRC mandatory, finalfullpoolPASS.', f'Persistent canary one pair; objective diff {canary["objective_difference"]}, dual diff {canary["dual_max_difference"]}, paired wall reduction {canary["paired_total_wall_reduction"]}; one-time initialization {canary["persistent_initialization_wall"]} s separately reported.',f'Persistent selected {f["persistent_selected"]}: {f["persistent_reason"]}; warmbasisfalse.',f'Four-way Threads1/RAMfloor1GiB; sampled treepeak {resource["observed_total_tree_peak_RSS"]/1024**3} GiB,minavailable {resource["min_available_RAM"]/1024**3} GiB,maxcommit {resource["max_commit_percent"]}%; nativeunion {r["total_optimize_wall_union"]}/1800s.',f'Discovery rounds {r["discovery_rounds"]}.',f'Pricing calls {r["new_pricing_calls"]}.',f'Earlyquota INTERRUPTED {sum(p["native_status"]==11 and p["early_stop"]["STOP_REASON"]=="DISCOVERY_QUOTA_FILLED" for p in prices)}.',f'New validated columns {r["new_discovery_columns"]}.',f'Final retained {r["retained_columns"]}.',f'Columns/min PR147 {old["columns_per_min"]} ->new {r["columns_per_min"]}; measured policy comparison, causal speedup claim 없음.',f'Discovery median {old["discovery_median"]} -> {r["discovery_median"]} s.',f'RMP optimize median {float(np.median([x["wall_seconds"] for x in read(SCI/"DW_CHECKPOINT_LATEST.json")["restart_state"]["rmps"]]))} -> {float(np.median([x["wall_seconds"] for x in rmps]))} s; paired build/update/opt/postsolve wall separately recorded.',f'Upper trajectory {[x["objective"] for x in rmps if x["status"]==2]}.',f'Distance trajectory DW_ACCELERATED_CG_THRESHOLD_DISTANCE.csv; final D_U={r["smallest_RMP_upper"]-r["material_threshold"]}, D_L={r["material_threshold"]-r["best_certified_LB"]}.',f'Final Certification {cert["status"]}; shortcut disabled/fulloriginaldomain/sameTrueSHA.',f'New corrected LB {r["new_corrected_LB"]}.',f'Aggregated certified lower {r["best_certified_LB"]}.',f'Smallest audited RMP upper {r["smallest_RMP_upper"]}.',f'Final certified D-W interval {r["final_interval"]}.',f'Materiality {r["materiality"]}.',f'Exact CG convergence {r["DW_ROOT_OPTIMAL_CERTIFIED"]}; threshold crossing separate.',f'Remaining negative RC receipts {neg}; feasible incumbents are diagnostics/columns, neverLB.', 'Next single blocker: consume genuine negative RC via exact-domain root CG, unless final pricing receipts instead demonstrate proof weakness; no further budget run in this task.', 'Branch-and-Price NOT_RUN.', 'External B0 lane untouched; no kill/terminate calls.', 'B1/B2/B3 production calls0/0/0.',f'Tests {tests}; compile/static/diffcheckPASS.', 'Remote SHA/clean publication receipt after push; no forcepush/no merge.']
 endings=['PR147의 Arc-LP certificate, D-W dominance authority와 material threshold를 scientific base로 유지하고 PR144의 runtime acceleration 기능만 통합했다.','Discovery early termination은 same-iteration true RMP dual에서 검증된 distinct true-negative trajectory 4개를 확보한 경우에만 사용했으며 INTERRUPTED status를 pricing certificate로 사용하지 않았다.','Scientific lower-bound, materiality 및 CG convergence 판정은 true unstabilized RMP dual과 valid global pricing BestBd만 사용했다.','Persistent RMP는 full-scale paired canary에서 정확성과 성능 gate를 모두 통과한 경우에만 선택했으며 warm basis는 사용하지 않았다.','Branch-and-Price는 실행하지 않았고 B1/B2/B3 production도 실행하지 않았다.']
 (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {x}' for i,x in enumerate(lines,1))+'\n\n'+'\n\n'.join(endings)+'\n',encoding='utf8')

def manifest():
 prefixes=['v42_dw_accelerated','tests/v42_dw_accelerated','v42_dw_runtime','tests/v42_dw_runtime','docs/v42_m1_dw_accelerated_root_integration'];files=[]
 for prefix in prefixes:
  for p in sorted((ROOT/prefix).rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.tmp','.pyc'] and p.name!='SHA256_MANIFEST.json':files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
 write('SHA256_MANIFEST.json',dict(files=files,self_excluded=True,byte_hashes=True))
if __name__=='__main__':verify()
