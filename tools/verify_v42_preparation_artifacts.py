"""Compare every stored FULL/C3A/Dense matrix and metadata array, Native0."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse


def digest_array(value):
    value=np.asarray(value);h=hashlib.sha256()
    h.update(value.dtype.str.encode());h.update(np.asarray(value.shape,dtype='<i8').tobytes());h.update(value.tobytes())
    return h.hexdigest()


def main(reference,candidate,output):
    checks={};avoided=0
    for prefix in ('FULL','C3A','DENSE_RESPONSE'):
        left=sparse.load_npz(reference/(prefix+'_A.npz'));right=sparse.load_npz(candidate/(prefix+'_A.npz'))
        checks[prefix+'_matrix_bit_exact']=(left.shape==right.shape and all(
            np.array_equal(getattr(left,k),getattr(right,k)) for k in ('indptr','indices','data')))
        with np.load(reference/(prefix+'_DATA.npz'),allow_pickle=True) as a,np.load(candidate/(prefix+'_DATA.npz'),allow_pickle=True) as b:
            checks[prefix+'_metadata_keys']=set(a.files)==set(b.files)
            for key in a.files:checks[prefix+'_'+key+'_bytes']=digest_array(a[key])==digest_array(b[key])
        if prefix=='C3A':avoided=left.data.nbytes+left.indices.nbytes+left.indptr.nbytes
    for name in ('CURRENT_C3A_ROW_CERTIFICATES.json','CURRENT_C3A_BOUND_PROOFS.json','CURRENT_C2_ALIASES.json','CURRENT_C2_ROW_PROOFS.json','DENSE_RESPONSE_PLANS.json'):
        checks[name]=json.loads((reference/name).read_text())==json.loads((candidate/name).read_text())
    report=dict(PASS=all(checks.values()),checks=checks,Native_optimize_calls=0,
                candidate=str(candidate),reference=str(reference),
                CSR_copy_upper_bound_avoided_per_dense_verification_bytes=avoided)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))
    if not report['PASS']:raise AssertionError('ORIGINAL_PREPARATION_ARTIFACT_BYTE_DRIFT')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.reference,a.candidate,a.output)
