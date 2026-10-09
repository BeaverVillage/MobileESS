"""Saved scientific data only; no case factory, Native model or solve."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
from fractions import Fraction
from unittest.mock import patch
import json,sys,time,gc,psutil
import numpy as np
from scipy import sparse

CODE=Path(r'D:\v42run32')
OUT=Path(__file__).resolve().parent
EVIDENCE=Path(r'D:\v42_f1_price_seed35_candidate_20261010_01\SOURCE32_CURRENT_F1_PRICE_SEED_EVIDENCE_94dd89f0a9d5d36e.json')
EXPECTED='94dd89f0a9d5d36ebb8fde0d321e3a4e6533f49b9fdbdf4159c77a41040bc1a6'
EXECUTION='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'

def record(path):
 path=Path(path).resolve();h=sha256();size=0
 with path.open('rb') as stream:
  while chunk:=stream.read(1048576):h.update(chunk);size+=len(chunk)
 return dict(path=str(path),bytes=size,sha256=h.hexdigest())

def load_json(path):
 path=Path(path);raw=path.read_bytes()
 return json.loads(raw.decode('utf-8-sig')),dict(path=str(path.resolve()),bytes=len(raw),sha256=sha256(raw).hexdigest())

def array_sha(array):
 a=np.ascontiguousarray(array);h=sha256()
 h.update(json.dumps(dict(dtype=a.dtype.str,shape=a.shape),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
 h.update(memoryview(a).cast('B'));return h.hexdigest()

def case_fingerprint(matrix,data):
 return dict(matrix_shape=list(matrix.shape),
  matrix={k:array_sha(getattr(matrix,k)) for k in ('indptr','indices','data')},
  domain={k:array_sha(v) for k,v in sorted(data.items())})

evidence,evidence_record=load_json(EVIDENCE)
assert evidence_record['sha256']==EXPECTED and evidence['PASS'] is True and evidence['execution_SHA']==EXECUTION
sys.path.insert(0,str(CODE))
import gurobipy as gp
actual_model=gp.Model;constructors=[];optimizers=[]
def denied_model(*a,**k):constructors.append(dict(args=repr(a),kwargs=repr(k)));raise AssertionError('INDEPENDENT_EVIDENCE_MODEL_DENIED')
def denied_optimize(*a,**k):optimizers.append(dict(args=repr(a),kwargs=repr(k)));raise AssertionError('INDEPENDENT_EVIDENCE_NATIVE_DENIED')
source_before={k:record(v['path']) for k,v in evidence['source_files'].items()}
assert source_before==evidence['source_files']
started=datetime.now(timezone.utc).isoformat();wall=time.perf_counter();cpu=time.process_time()
host_before=dict(available_bytes=psutil.virtual_memory().available,RSS=psutil.Process().memory_info().rss)
rows=[];all_producers={};snapshot_paths={}
with patch.object(gp,'Model',denied_model),patch.object(actual_model,'__init__',denied_model),patch.object(actual_model,'optimize',denied_optimize):
 from v42_m1_research import lb,check_lb
 from v42_b2_seed_recovery_v18 import certificate_box
 from v42_m1_hybrid import blocks
 modules={'v42_m1_research/lb.py':lb,'v42_m1_research/check_lb.py':check_lb,
  'v42_b2_seed_recovery_v18/certificate_box.py':certificate_box,'v42_m1_hybrid/blocks.py':blocks}
 for row in evidence['rows']:
  # Live ledger bytes can advance. Keep each freshly read snapshot separate.
  request,rr=load_json(row['request']['path']);manifest,mr=load_json(request['manifest'])
  assert rr==row['request'] and mr==row['manifest'] and request['manifest_SHA']==mr['sha256']
  assert request['implementation_SHA']==manifest['execution_SHA']==EXECUTION
  original_map=manifest['builder_original_sources'];full_map=dict(original_map,**manifest['execution_sources'])
  if not all_producers:
   all_producers={name:record(CODE/name) for name in sorted(full_map)}
   assert len(all_producers)==1105 and all(r['sha256']==full_map[n] for n,r in all_producers.items())
   assert sha256(json.dumps(manifest['execution_sources'],sort_keys=True,separators=(',',':')).encode()).hexdigest()==EXECUTION
  for name,module in modules.items():
   assert Path(module.__file__).resolve()==(CODE/name).resolve() and record(module.__file__)['sha256']==full_map[name]
  identity={k:request[k] for k in ('run_id','arm','day','worker_slot','attempt_id')}
  output=Path(request['output']);attempt=output.parent
  assert identity==row['identity'] and attempt==Path(row['request']['path']).parent
  assert output==Path(request['root'])/'dates/B2'/request['day']/'attempts'/request['attempt_id']/'output'
  admission,ar=load_json(row['admission']['path']);selection,sr=load_json(row['selection']['path'])
  assert ar==row['admission'] and sr==row['selection']
  assert admission['status']=='ADMITTED_CURRENT_ATTEMPT_ONLY'
  binding=admission['binding'];assert binding['identity']==identity and binding['implementation_SHA']==EXECUTION
  assert binding['code_root']==str(CODE) and binding['manifest']==mr
  for key in ('state_packet','current_matrix','current_full_row_metadata','actual_L1_coupling','actual_L4_coupling'):
   assert record(row[key]['path'])==row[key] and Path(row[key]['path']).is_relative_to(output)
  assert admission['state_packet']==row['state_packet']
  with np.load(row['state_packet']['path'],allow_pickle=False) as packet:
   assert {k:array_sha(packet[k]) for k in packet.files}==binding['arrays']
   pi=packet['pi'].copy()
  with np.load(row['current_full_row_metadata']['path'],allow_pickle=False) as packet:
   data={k:packet[k].copy() for k in packet.files}
  matrix=sparse.load_npz(row['current_matrix']['path']).tocsr()
  before_case=case_fingerprint(matrix,data)
  assert before_case=={k:binding['case'][k] for k in ('matrix_shape','matrix','domain')}
  assert pi.shape==(matrix.shape[0],) and np.isfinite(pi).all()
  assert binding['case']['case_sha']==selection['case_sha']
  l1,l1r=load_json(row['actual_L1_coupling']['path']);l4,l4r=load_json(row['actual_L4_coupling']['path'])
  axis=np.asarray(l1['original_rows'],dtype=np.int64)
  assert l1['case_sha']==l4['case_sha']==selection['case_sha'] and not l1['multipliers'] and not l4['multipliers']
  assert np.array_equal(l1['original_senses'],data['sense'][axis]) and np.array_equal(l4['original_rows'],axis)
  # Independent original column-owner support partition, without a model or graph.
  owners=[blocks.unit_owner(n) for n in data['names']];units=sorted({u for u in owners if u is not None})
  assert len(units)==4;codes={u:j+1 for j,u in enumerate(units)}
  columns=np.asarray([codes.get(u,0) for u in owners],dtype=np.int64)
  nonempty=np.flatnonzero(np.diff(matrix.indptr));low=np.zeros(matrix.shape[0],dtype=np.int64);high=low.copy()
  support=columns[matrix.indices]
  low[nonempty]=np.minimum.reduceat(support,matrix.indptr[nonempty])
  high[nonempty]=np.maximum.reduceat(support,matrix.indptr[nonempty])
  assert np.array_equal(np.flatnonzero(low!=high),axis)
  repaired,repair_receipt=lb.repair_affine_equality_duals(matrix,data,pi)
  dual_sha=sha256('\n'.join(f'{i}:{repaired[str(i)]}' for i in sorted(map(int,repaired))).encode('ascii')).hexdigest()
  candidate=next(v for v in selection['candidates'] if v['kind']=='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI')
  certificate=candidate['certificate']
  assert certificate==row['f1_original_full_domain_certificate'] and certificate['PASS'] is True
  assert dual_sha==certificate['dual_SHA256']==row['actual_repaired_dual_SHA256']
  coupling={str(int(i)):repaired[str(int(i))] for i in axis if str(int(i)) in repaired}
  raw_count=int(np.count_nonzero(pi[axis]))
  assert coupling==row['actual_repaired_coupling'] and len(coupling)==row['actual_repaired_coupling_nonzero']==48
  assert raw_count==row['raw_pi_coupling_nonzero']
  proof_record=certificate['finite_box_original_row_implication']['proof_file']
  proof,pr=load_json(proof_record['path']);assert pr==proof_record
  lo=np.array(data['lower'],dtype=float,copy=True);hi=np.array(data['upper'],dtype=float,copy=True)
  for step in proof['steps']:lo[int(step['column'])]=step['lower'];hi[int(step['column'])]=step['upper']
  proof_checked=certificate_box.verify(matrix,data,lo,hi,proof)
  assert proof_checked['PASS'] is True and proof_checked==certificate['finite_box_original_row_implication']['independent_replay']
  # Fresh original rational evaluator, complete original rows/domain and proven envelope.
  checked=check_lb.check_rational_dual_certificate(matrix,data,repaired,lower=lo,upper=hi,case_sha=selection['case_sha'])
  for key in ('PASS','status','case_sha','certified_domain','exact_bound','weighted_rhs_exact','box_correction_exact',
   'nonzero_dual_rows','residual_nonzero_columns','max_exact_residual','dual_SHA256','source_rows_SHA256',
   'native_objective_used','native_BestBd_used','optimality_claimed'):
   assert checked[key]==certificate[key],key
  assert Fraction(checked['exact_bound'])<0
  assert selection['selected']==row['selected_dual']=='ORIGINAL_ZERO_SIGNED_DUAL'
  assert selection['maximum_exact_bound']==row['selected_exact_bound']=='0'
  assert max(Fraction(v['certificate']['exact_bound']) for v in selection['candidates'])==0
  initial,initial_record=load_json(output/'INITIAL_EXACT_ORIGINAL_DUAL.json');assert initial=={}
  ledger_raw=(attempt/'NATIVE_RUNTIME_LEDGER.json').read_bytes();ledger=json.loads(ledger_raw)
  ledger_record=dict(path=str((attempt/'NATIVE_RUNTIME_LEDGER.json').resolve()),bytes=len(ledger_raw),sha256=sha256(ledger_raw).hexdigest())
  native=admission['F1_completed_Native_receipt'];assert native==row['f1_completed_native_receipt'] and native in ledger['calls']
  assert native['status']=='FINISHED' and native['entered_native'] is True and native['runtime_unavailable'] is False
  assert native['label']=='CURRENT_DAY_STATIONARY_FULL_INTEGER_REPRESENTATIVE_BOUNDS' and native['requested_seconds']==120.
  assert 0<native['Native_Runtime']<=native['effective_TimeLimit']<=120.
  assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0 and ledger['wall_ceiling_seconds'] is None
  target=OUT/(request['day']+'_LIVE_LEDGER_SNAPSHOT.json')
  with target.open('xb') as stream:stream.write(ledger_raw)
  snapshot_paths[request['day']]=record(target)
  rmp_records=[]
  for old in row['rmp_no_pi']:
   result,recorded=load_json(old['artifact']['path']);assert recorded==old['artifact']
   assert result['native']==old['native'] and result['native'] in ledger['calls']
   assert result['dual_status']==old['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
   assert result['full_original_dual'] is None and result['convexity_duals'] is None
   assert result['native']['Native_status']==11 and result['native']['Native_SolCount']==0
   rmp_records.append(recorded)
  assert before_case==case_fingerprint(matrix,data)
  producers=[rr,mr,ar,sr,l1r,l4r,initial_record,row['state_packet'],row['current_matrix'],row['current_full_row_metadata'],pr,*rmp_records]
  rows.append(dict(day=request['day'],identity=identity,producer_records=producers,
   case_sha=selection['case_sha'],current_original_matrix_domain_all_arrays_match=True,
   independently_derived_original_coupling_axis_match=True,raw_F1_Pi_coupling_nonzero=raw_count,
   repaired_coupling_nonzero=48,complete_repaired_dual_SHA256=dual_sha,
   full_original_signed_certificate_freshly_reevaluated=checked,
   independently_replayed_equality_envelope=proof_checked,
   selected_exact_bound='0',selected_dual='ORIGINAL_ZERO_SIGNED_DUAL',actual_L1_L4_price_coupling_nonzero=0,
   actual_RMP_native_finite_Pi_absent=True,
   completed_F1_call_matches_current_same_attempt_ledger=True,completed_F1_call=native,
   producer_live_ledger_snapshot=row['current_ledger'],current_live_ledger_snapshot=ledger_record,
   live_ledger_bytes_equal_producer_snapshot=ledger_record==row['current_ledger'],
   current_original_case_arrays_unchanged_after_math_replay=True,RSS_after_case=psutil.Process().memory_info().rss))
  del matrix,data,pi,lo,hi,proof,support,columns,owners,low,high,nonempty,repaired,coupling
  gc.collect()

all_after={name:record(CODE/name) for name in all_producers}
assert all_producers==all_after and source_before=={k:record(v['path']) for k,v in evidence['source_files'].items()}
assert record(EVIDENCE)==evidence_record and not constructors and not optimizers
static_paths=['v42_may_campaign_native90/m_stage.py','v42_m1_anytime/algorithms.py',
 'v42_m1_anytime/core.py','v42_autonomous_b2/f1_state.py','v42_m1_hybrid/pricing.py']
doc=dict(schema='SOURCE35_SAVED_SOURCE32_DIAGNOSIS_INDEPENDENT_NATIVE_ZERO_REVIEW_V1',
 PASS=True,UTC=datetime.now(timezone.utc).isoformat(),started_UTC=started,evidence=evidence_record,
 Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=constructors,nativeattempts=optimizers,
 production_immutable_process_queue_candidate_code_changes=0,
 Source32_execution_SHA=EXECUTION,source_file_count=len(all_producers),source_start_end_identical=True,
 source_records={k:all_producers[k] for k in sorted(set(static_paths)|set(modules))},
 complete_source_manifest=record(rows[0]['producer_records'][1]['path']),rows=rows,live_ledger_raw_snapshots=snapshot_paths,
 wall_seconds=time.perf_counter()-wall,CPU_seconds=time.process_time()-cpu,
 host_memory_before=host_before,host_memory_after=dict(available_bytes=psutil.virtual_memory().available,RSS=psutil.Process().memory_info().rss),
 conclusion=dict(diagnosis_supported=True,
  same_attempt_finite_complete_F1_Pi_has_48_exact_repaired_nonzero_coupling_rows_each=True,
  negative_F1_certificates_do_not_improve_original_selected_zero_Global_LB=True,
  original_selected_zero_dual_causes_actual_L1_L4_zero_coupling=True,
  actual_Source32_RMP_has_no_finite_Pi_not_measured_zero_Pi=True,
  separate_current_attempt_computational_price_seed_can_leave_original_Frontier_final_bracket_unchanged=True),
 required_candidate_separation=['Do not replace certified best original dual or existing exact Frontier with a negative F1 candidate.',
  'Only pass the same-attempt/source/case/axis-bound repaired F1 vector to computational pricing; do not use Native objective as LB.',
  'Each pricing round must retain original complete independent certificate, producer/full-sum agreement, packet SHA and Frontier.publish gate.',
  'Update authoritative dual only after an actual independently certified improving bound is adopted; final original dual/checker/frontier equality remains unchanged.',
  'No hypothetical pricing result or seed may change UB, exact gap, Native budgets, original physical/domain bounds or public PASS.'],
 limitations=['Diagnosis evidence review only; candidate module/test implementation was not validated.',
  'No new Native pricing/model or actual performance/day PASS was measured.',
  'Live ledger snapshot may differ from the producer snapshot through natural progress; original completed call and RMP records must remain present.'],
 runner=record(__file__))
raw=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf8')
target=OUT/'SOURCE35_DIAGNOSIS_INDEPENDENT_NATIVE_ZERO_REVIEW.json'
with target.open('xb') as stream:stream.write(raw)
print(json.dumps(dict(PASS=True,receipt=record(target),days=len(rows),wall_seconds=doc['wall_seconds'],CPU_seconds=doc['CPU_seconds']),indent=2))
