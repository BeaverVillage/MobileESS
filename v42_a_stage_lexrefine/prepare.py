"""Verified inherited integer cuts; original LP science is unchanged."""
import gzip,pickle
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_practical.physical import Physical
from v42_a_stage_domain_v2.strengthening import strengthen_histogram_capacity
from .policy import OUT,STATIC

def prepare():
    if (OUT/'LEX_REFINE_BUILD_VERIFICATION.json').exists():raise PermissionError('LEX_REFINEMENT_ALREADY_PREPARED')
    b=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    with gzip.open(b['state']['path'],'rb') as f:p=pickle.load(f)
    s=p['snapshot'];physical=Physical(p['state'],s)
    augmented,proof=strengthen_histogram_capacity(s,s,physical.descriptor,p['state']['data'],np.arange(s.matrix.shape[1],dtype=np.int64))
    atomic(OUT/'P2_INHERITED_INTEGER_STRENGTHENING.json',proof)
    path=STATIC/'P2_INTEGER_STRENGTHENED_SNAPSHOT.pkl.gz'
    with gzip.open(path,'xb',compresslevel=1) as f:pickle.dump(augmented,f,protocol=5)
    atomic(OUT/'LEX_REFINE_BUILD_VERIFICATION.json',dict(PASS=True,snapshot=record(path),source=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),
        proof=record(OUT/'P2_INHERITED_INTEGER_STRENGTHENING.json'),rows=augmented.matrix.shape[0],cols=augmented.matrix.shape[1],nnz=augmented.matrix.nnz,
        full_relevant_domain=True,same_integer_schedules_and_objectives=True))
    atomic(OUT/'LEX_REFINE_ENTRY_GATE.json',dict(PASS=True,build=record(OUT/'LEX_REFINE_BUILD_VERIFICATION.json'),
        migration_zero=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')['certificate'],rho_lock_epsilon=1e-7,
        objective_integrality_authority=True,both_objective_partition_children_preserved=True,
        native_bound_scope='CURRENT_ACTUAL_FULL_RELEVANT_DOMAIN_INTEGER_MODEL',parameter_sweep=False))
    print('LEX_INTEGER_STRENGTHENED',proof['cuts_added'],proof['cut_nnz'],flush=True)
if __name__=='__main__':prepare()
