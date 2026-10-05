"""Read-only exact149 matrix/pool/dual/authority audit, zero optimize."""
from .common import *
import numpy as np
from v42_degen.identity import inputs,signature,digest
from v42_dw_root.partition import axes
from v42_dw_root.models import hash_column
def audit():
 preserved=preserve_old();head=subprocess.check_output(['git','merge-base',BASE_HEAD,'HEAD'],text=True).strip();assert head==BASE_HEAD
 remote=json.loads(subprocess.check_output(['gh','pr','view','149','--repo','BeaverVillage/MobileESS','--json','headRefOid,isDraft'],text=True));assert remote['headRefOid']==BASE_HEAD and remote['isDraft']
 manifest=read(SCI/'SHA256_MANIFEST.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in manifest['files'])
 cp=read(SCI/'DW_CHECKPOINT_LATEST.json');assert cp['type']=='TERMINAL' and cp['RMP']['status']==2 and cp['total_retained_columns']==len(cp['pool'])==1433
 for x in cp['pool']:
  assert sha(ROOT/x['file'])==x['file_SHA']
  with np.load(ROOT/x['file']) as z:
   modern='x' in z;v=z['x'] if modern else z['local_values'];a=z['a'] if modern else z['master_coefficients'];c=float(z['c'] if modern else z['objective']);assert hash_column(v,a,c)==x['column_SHA']
 pool=hashlib.sha256(json.dumps([(x['MESS'],x['column_SHA']) for x in cp['pool']],separators=(',',':')).encode()).hexdigest();assert pool==cp['pool_SHA']
 A,d,B,e,*_=inputs();assert signature(A,d)==read(SCI/'DW_INTEGRATION_BASE_AUDIT.json')['full_matrix_signature'];owner,rows=axes();assert cp['dual_axis_SHA']==digest(np.flatnonzero(rows<0)) and cp['row_axis_SHA']==digest(e['row_names'][rows<0])
 with np.load(SCI/cp['RMP']['point_file']) as z:assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['RMP']['dual_SHA']
 assert sha(SCI/cp['RMP']['point_file'])==cp['RMP']['point_SHA']
 with np.load(SCI/cp['smooth_file']) as z:assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['smooth_key']
 arc=read(ARC/'ARC_LP_CERTIFIED_RESULT.json');threshold=read(ARC/'DW_MATERIAL_THRESHOLD_AUTHORITY.json');assert threshold['T_cert']==arc['native_optimum']+.005 and cp['arc_floor']==arc['L_arc_cert'];assert cp['threshold_authority']==threshold
 feature=read(SCI/'DW_RUNTIME_FEATURE_SELECTION.json');assert not feature['persistent_selected'] and sha(SCI/'DW_RUNTIME_FEATURE_SELECTION.json')==cp['feature_selection_SHA'];assert read(SCI/'DW_FULL_POOL_FINAL_AUDIT.json')['PASS']
 from v42_arc_floor.finalize import independent_arc
 independent=independent_arc(A,d);assert independent['L_dual_support']==arc['L_arc_cert']
 write('DW_CONTINUATION_BASE_AUDIT.json',dict(PASS=True,exact_head=BASE_HEAD,original_files=preserved,pool_columns=1433,pool_SHA=pool,true_dual_SHA=cp['RMP']['dual_SHA'],smooth_file=cp['smooth_file'],smooth_key=cp['smooth_key'],alpha=cp['alpha_next'],current_upper=cp['best_interval'][1],current_lower=cp['best_interval'][0],historical_optimize=cp['elapsed_budget'],full_matrix_signature=signature(A,d),floor=arc['L_arc_cert'],threshold=threshold['T_cert'],feature_selection_SHA=cp['feature_selection_SHA'],cache_authority=cp['authority_key'],native_optimize_calls=0,independent_arc=independent))
 print('CONTINUATION_BASE_PASS',1433,cp['elapsed_budget'],flush=True)
if __name__=='__main__':audit()
