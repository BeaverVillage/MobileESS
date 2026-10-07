"""Static-only reconstruction and proof of weighted integer cuts."""
import gzip,pickle
from dataclasses import replace
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT,STATIC
from .cuts import strengthen

def prepare():
    if (OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json').exists():raise PermissionError('WEIGHTED_CG_ALREADY_PREPARED')
    b=read(OUT/'LEX_REFINE_BUILD_VERIFICATION.json');source=b['snapshot']
    if record(source['path'])!=source:raise ValueError('QUALIFIED_INTEGER_SNAPSHOT_BYTE_DRIFT')
    with gzip.open(source['path'],'rb') as f:strong=pickle.load(f)
    full=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json');m=full['rows']
    original=replace(strong,matrix=strong.matrix[:m].copy(),senses=strong.senses[:m].copy(),rhs=strong.rhs[:m].copy()).require()
    if original.fingerprint()!=full['snapshot_sha256']:raise ValueError('QUALIFIED_FULL_INTEGER_ORIGINAL_RECONSTRUCTION_DRIFT')
    hist=read(OUT/'P2_INHERITED_INTEGER_STRENGTHENING.json')
    result,proof=strengthen(original,strong,hist)
    path=STATIC/'P2_WEIGHTED_CG_SNAPSHOT.pkl.gz'
    with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(result,f,protocol=5)
    atomic(OUT/'WEIGHTED_CG_BUILD_VERIFICATION.json',dict(PASS=True,snapshot=record(path),proof=proof,
        source_full_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),source_verified_histogram_proof=record(OUT/'P2_INHERITED_INTEGER_STRENGTHENING.json'),
        rows=result.matrix.shape[0],cols=result.matrix.shape[1],nnz=result.matrix.nnz,native_solve_calls=0,
        May19_native_application=False,original_physics_tolerances_objectives_unchanged=True))
    print('WEIGHTED_CG_PREPARED',proof['cuts_added'],proof['cut_nnz'],flush=True)
if __name__=='__main__':prepare()
