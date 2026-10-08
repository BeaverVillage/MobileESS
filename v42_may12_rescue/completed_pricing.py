"""Restore a complete, source-bound pricing round; no new optimize calls."""
from fractions import Fraction as F
import numpy as np
from .policy import OLDOUT,DAY
from v42_pr134_b1.common import read,record
from v42_a_stage_phase1.runner import load_cache,block_folder
from v42_a_stage_phase1.producer import price_snapshot,support_graph,native_block
from v42_a_stage_phase1.backend import project_local_point
from v42_a_stage_phase1.oracle import corrected_certificate,true_objective
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
from v42_a_stage_practical.policy import POLICY

def restore(state,folder,raw_master):
    result=read(folder/'FULL_PRICING_RESULT.json')
    required={r['class_id']:r for r in read(OLDOUT/DAY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    records={r['class_id']:r for r in result['block_certificates']}
    if set(records)!=set(required) or result['classes']!=130 or not result['complete_STAY_and_migration_coverage']:
        raise ValueError('COMPLETE_PRICING_CHECKPOINT_COVERAGE_FAIL')
    global_proof=read(folder/'ORIGINAL_ROW_GLOBAL_BOX_CERTIFICATE.json')
    if not global_proof['PASS'] or global_proof['original_snapshot_sha256']!=state['compact'].fingerprint():
        raise ValueError('COMPLETE_PRICING_CHECKPOINT_GLOBAL_MATRIX_FAIL')
    aggregate=F(global_proof['global_bound']);negative=[]
    master=state['compact'];mp=np.asarray(raw_master['Pi']).copy()
    mp[(master.senses=='<')&(mp>0)]=0;mp[(master.senses=='>')&(mp<0)]=0
    expected_pi=mp[list(state['axes'].values())]
    for key,want in sorted(required.items()):
        cache=load_cache(want);full,B=cache['snapshot'],cache['B'];f=block_folder(folder,key)
        receipt=read(f/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json');pi=np.asarray(receipt['global_coupling_pi'])
        if not np.array_equal(pi,expected_pi):raise ValueError('COMPLETE_PRICING_CHECKPOINT_MASTER_DUAL_DRIFT')
        if full.fingerprint()!=receipt['full_snapshot_sha256']:raise ValueError('COMPLETE_PRICING_CHECKPOINT_FULL_MATRIX_FAIL')
        if full.matrix.shape[1]:
            native=read(f/'NATIVE_RESULT.json');identity=read(native['model_identity']['path'])
            if native['status']!=2 or record(native['raw_attributes']['path'])!=native['raw_attributes'] or identity['original_snapshot_sha256']!=price_snapshot(full,B,pi).fingerprint():
                raise ValueError('COMPLETE_PRICING_CHECKPOINT_NATIVE_RAW_OR_MATRIX_FAIL')
            raw=dict(np.load(native['raw_attributes']['path']))
            if not primal_replay(full,raw['X'])['PASS'] or not verify_sign_convention(price_snapshot(full,B,pi),raw['Pi'],raw['RC'],absolute=1e-7,relative=1e-10)['PASS']:
                raise ValueError('COMPLETE_PRICING_CHECKPOINT_RAW_REPLAY_FAIL')
            cert=corrected_certificate(full,B,pi,raw['Pi'])
        else:
            raw={'X':np.zeros(0),'Pi':np.zeros(full.matrix.shape[0])};cert=corrected_certificate(full,B,pi,raw['Pi'])
        if not cert['PASS'] or cert['exact_lower_bound']!=receipt['certificate']['exact_lower_bound']:
            raise ValueError('COMPLETE_PRICING_CHECKPOINT_EXACT_BOUND_FAIL')
        aggregate+=F(cert['exact_lower_bound'])
        delta=true_objective(B,pi,raw['X'])-F(receipt['active_local_lower_bound'])
        if full.matrix.shape[1] and delta < -F(POLICY['price_epsilon']):
            if delta!=F(receipt['oracle_point_price']):raise ValueError('COMPLETE_PRICING_CHECKPOINT_NEGATIVE_PRICE_FAIL')
            uid=state['data'][7]['classes'][key][0]
            graph=support_graph(state['data'][5][uid],cache['graph'],cache['units'],raw['X'],job=state['data'][1][uid])
            reduced,_,_,units=native_block(state['data'],key,graph,tuple(state['axes']))
            point=project_local_point(cache['units'],raw['X'],units,reduced.matrix.shape[1])
            if not primal_replay(reduced,point)['PASS']:raise ValueError('COMPLETE_PRICING_CHECKPOINT_DIRECTION_REPLAY_FAIL')
            negative.append(dict(class_id=key,price=delta,graph=graph,support_sha256=graph.sha))
    if aggregate!=F(result['full_domain_phase1_lower_bound']) or len(negative)!=result['negative_blocks']:
        raise ValueError('COMPLETE_PRICING_CHECKPOINT_AGGREGATE_OR_NEGATIVE_COUNT_FAIL')
    return result,negative
