from v42_arc_floor.common import ROOT,sha,read,OLD,PREVIOUS,DOMINANCE,EPS
import json,subprocess,hashlib,numpy as np
OUT=ROOT/'docs/v42_m1_dw_accelerated_root_integration'
SCI=ROOT/'docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'
BASE='31858f4e35b44caadeee2a72ef2ae2d35b74899b'
RUNTIME='42204661b8a92e0b1153ade0dc11830d54ec8df5'
def write(n,d):
 p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');q.replace(p)
def audit():
 from v42_degen.identity import inputs,signature,digest
 from v42_dw_root.partition import axes
 from v42_dw_root.models import hash_column
 from v42_arc_floor.finalize import independent_arc
 f=read(OUT/'PR147_BYTE_FREEZE.json');assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['files'])
 for pr,h in [(147,BASE),(144,RUNTIME)]:
  remote=json.loads(subprocess.check_output(['gh','pr','view',str(pr),'--json','headRefOid,isDraft'],cwd=ROOT,text=True));assert remote['headRefOid']==h and remote['isDraft']
 subprocess.run(['python',str(SCI/'verify_index_manifest.py'),str(ROOT)],check=True,cwd=ROOT)
 A,d,B,e,*_=inputs();owner,rows=axes();identity=read(SCI/'ARC_LP_BASE_IDENTITY.json');assert signature(A,d)==identity['matrix_signature']
 certificate=independent_arc(A,d);arc=read(SCI/'ARC_LP_CERTIFIED_RESULT.json');assert certificate['L_dual_support']==arc['L_arc_cert']
 dom=read(DOMINANCE/'DW_FULL_SCALE_DOMINANCE_PROOF.json');assert dom['PASS'] and sha(DOMINANCE/'DW_FULL_SCALE_DOMINANCE_PROOF.json')==identity['dominance_proof_SHA']
 t=read(SCI/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');assert t['PASS'] and t['T_cert']==arc['native_optimum']+.005
 cp=read(SCI/'DW_CHECKPOINT_LATEST.json');assert len(cp['pool'])==cp['total_retained_columns']==1244
 for r in cp['pool']:
  assert sha(ROOT/r['file'])==r['file_SHA']
  with np.load(ROOT/r['file']) as z:
   new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c'] if new else z['objective'])
   assert hash_column(x,a,c)==r['column_SHA']
 pool=hashlib.sha256(json.dumps([(r['MESS'],r['column_SHA']) for r in cp['pool']],separators=(',',':')).encode()).hexdigest();assert pool==cp['pool_SHA']
 assert cp['dual_axis_SHA']==digest(np.flatnonzero(rows<0)) and cp['row_axis_SHA']==digest(e['row_names'][rows<0])
 with np.load(SCI/cp['smooth_file']) as z:assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['smooth_key']
 assert read(SCI/'VERIFICATION.json')['PASS']
 write('DW_INTEGRATION_BASE_AUDIT.json',dict(PASS=True,PR147=BASE,PR144=RUNTIME,tracked_bytes_preserved=len(f['files']),full_matrix_signature=identity['matrix_signature'],independent_arc=certificate,dominance_SHA=identity['dominance_proof_SHA'],coupling_SHA=identity['coupling_proof_SHA'],threshold=t,columns=1244,pool_SHA=pool,dual_axis_SHA=cp['dual_axis_SHA'],row_axis_SHA=cp['row_axis_SHA'],variable_axis_SHA=digest(d['names']),smoothing_SHA=cp['smooth_key'],alpha_next=cp['alpha_next'],corrected_theorem_SHA=sha(ROOT/'v42_dw_bound/certificate.py'),physical_validator_SHA=sha(ROOT/'v42_dw_resume/audit.py'),original_physical_sources={p:sha(ROOT/p) for p in ['v42_native/mess.py','v42_bootstrap/attribution.py']},native_optimize_calls=0))
 print('INTEGRATION_BASE_PASS',len(f['files']),pool,flush=True)
if __name__=='__main__':audit()
