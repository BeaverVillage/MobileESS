"""Reconstruct the prior unclosed child exactly and price its dual with valid boxes."""
import gzip,pickle,time,traceback
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic,sha
from v42_a_stage_lexcases.policy import ROOT,OUT,STATIC
from v42_a_stage_domain_v2.lexstage import LexLock,rebuild_locked_snapshot
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_lexfull.runner import bound
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_compact_rowgen.resources import sample
from .full_bounds import upper_boxes

def run():
    target=OUT/'CERTIFICATE_RECOVERY';target.mkdir(exist_ok=True)
    if (target/'STARTED.json').exists():raise PermissionError('READ_ONLY_RECOVERY_ALREADY_STARTED')
    budget=Budget();start=time.time();limit=min(budget.remaining(),300)
    atomic(target/'STARTED.json',dict(PASS=True,deadline=budget.record,allocation_seconds=limit,native_solve_calls=0,
        source_files=[record(__file__),record(ROOT/'v42_a_stage_certificates/full_bounds.py')]))
    result=dict(PASS=False,native_solve_calls=0,native_model_or_raw_dual_changed=False,old_open_queue_not_pruned=True)
    try:
        b=read(OUT/'LEX_REFINE_BUILD_VERIFICATION.json');source=b['snapshot']
        if record(source['path'])!=source:raise ValueError('QUALIFIED_SOURCE_SNAPSHOT_BYTE_DRIFT')
        with gzip.open(source['path'],'rb') as f:strong=pickle.load(f)
        m=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')['rows']
        original=replace(strong,matrix=strong.matrix[:m].copy(),senses=strong.senses[:m],rhs=strong.rhs[:m]).require()
        if original.fingerprint()!=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')['snapshot_sha256']:raise ValueError('ORIGINAL_FULL_RELEVANT_SNAPSHOT_DRIFT')
        migration=read(OUT/'P2_MIGRATION_PROBE_RESULT.json');inc=read(OUT/'VALIDATED_INTEGER_INCUMBENT.json')
        locks=[LexLock('rho',Fraction(inc['exact_UB']),True,sha(OUT/'P1_FULL_DOMAIN_INTEGER_GAP_CERTIFICATE.json'),Fraction(1e-7)),
            LexLock('migration_count',Fraction(0),True,migration['certificate']['sha256'])]
        stage,_=rebuild_locked_snapshot(original,locks);o=stage.objective('shift_magnitude')
        stage=replace(stage,objectives=(o,)+tuple(v for v in stage.objectives if v.name!=o.name),vtypes=np.full(stage.matrix.shape[1],'C'))
        folder=OUT/'M19/P2/SHIFT_MAGNITUDE/TREE/N2';identity=read(folder/'MODEL_IDENTITY.json');rec=read(folder/'NATIVE_RESULT.json')
        for r in (identity['matrix'],identity['attributes'],rec['raw_attributes']):
            if record(r['path'])!=r:raise ValueError('NATIVE_NODE_BYTE_DRIFT')
        attrs=dict(np.load(identity['attributes']['path']));raw=dict(np.load(rec['raw_attributes']['path']))
        s=replace(stage,lower=attrs['lower'],upper=attrs['upper']).require()
        if s.fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('EXACT_PRIOR_CHILD_RECONSTRUCTION_DRIFT')
        nativeA=sp.load_npz(identity['matrix']['path']);delta=nativeA-s.matrix;delta.eliminate_zeros()
        if delta.nnz:raise ValueError('PERSISTED_NATIVE_MATRIX_DRIFT')
        del nativeA,delta,strong,original
        authority=read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json')['global_descriptor']
        if record(authority['path'])!=authority:raise ValueError('SCIENTIFIC_DESCRIPTOR_BYTE_DRIFT')
        with gzip.open(authority['path'],'rb') as f:descriptor=pickle.load(f)
        indices=[]
        for u in descriptor['units']:
            for items in u['v'].values():
                for e in items.values():
                    if e[0]=='v':indices.append(int(e[1]))
                    elif e[0]=='e':indices.extend(map(int,e[2]))
        n=min(indices)
        def check():
            budget.remaining()
            if time.time()-start>limit:raise TimeoutError('STATIC_CERTIFICATE_PROPAGATION_ALLOCATION')
            if sample()['unsafe']:raise RuntimeError('UNSAFE_RAM_OR_COMMIT')
        def progress(p):atomic(target/'PROPAGATION_CHECKPOINT.json',dict(PASS=True,**p,deadline=budget.record,certificate_only=True))
        u,proof=upper_boxes(s,n,check,progress);atomic(target/'FULL_ORIGINAL_ROW_BOX_PROOF.json',proof)
        path=STATIC/'READ_ONLY_N2_CERTIFICATE_UPPER.npz';np.savez_compressed(path,upper=u)
        replay=primal_replay(s,raw['X']);sign=verify_sign_convention(s,raw['Pi'],raw['RC']);L=bound(s,raw,u) if replay['PASS'] and sign['PASS'] else None
        result.update(PASS=L is not None,valid_LB=L,upper=record(path),proof=record(target/'FULL_ORIGINAL_ROW_BOX_PROOF.json'),
            primal=replay,sign=sign,reconstructed_snapshot_sha256=s.fingerprint(),native_original_result=record(folder/'NATIVE_RESULT.json'),
            full_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),all_original_rows_and_full_relevant_columns_present=True,
            global_variables=n,remaining_global_infinite=proof['remaining_global_infinite'])
    except Exception as e:result.update(stop_reason=repr(e),traceback=traceback.format_exc())
    result['wall_seconds']=time.time()-start;atomic(target/'RESULT.json',result);print('READ_ONLY_RECOVERY',result['PASS'],result.get('valid_LB'),result.get('stop_reason'),flush=True)
    return result
if __name__=='__main__':run()
