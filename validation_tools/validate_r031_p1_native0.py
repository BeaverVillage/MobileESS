"""Real May02 full graphs and compiler routing; no optimization or state edits."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r031
import gzip, pickle
from unittest.mock import patch
from v44.common import read, atomic, record, now
from v44_recovery_r031 import p1_expansion as policy
from v44_recovery_r031 import operations as op
from v42_a_stage_phase1.runner import load_cache
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_domain_v2.domain import graph_content_hash
import gurobipy as gp

root=op.CAMPAIGN/'2025-05-02/B3/attempt014/A2/OUTPUT'
destination=Path('D:/MobileESS_V44/development/r031_p1_native0_20261018_final')
if destination.exists(): raise FileExistsError(destination)
destination.mkdir(parents=True)
calls=[]
def denied(*args,**kwargs):
    calls.append('attempted');raise PermissionError('R031_NATIVE0_OPTIMIZATION_DENIED')

with patch.object(gp.Model,'optimize',denied),patch.object(gp.Model,'presolve',denied):
    with gzip.open(root/'STATIC/P1_CLOSED_STATE.pkl.gz','rb') as stream: state=pickle.load(stream)
    qualified=read(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    required={r['class_id']:r for r in qualified['records']}
    keys=['0abb4b6f5a85216e50286cf5eef61422018265c1c80185abf5a7219bb7c1113b',
          '6954ca818f007e8cb40770274b1bd241c9689cda57a72bce608405a35571168f',
          '864932a351b39a4d9552bce47bda2f02210d9bbe50a93fb7eafa6f0282ca158e']
    expansion=policy.Expansion();negative=[];details=[]
    for key in keys:
        cache=load_cache(required[key]);full=cache['graph']
        snapshot, coupling, _, _ = native_block(state['data'],key,full,tuple(state['axes']))
        assert snapshot.fingerprint() == cache['snapshot'].fingerprint()
        assert (coupling != cache['B']).nnz == 0
        for member in state['data'][7]['classes'][key]: policy.contains(full,state['data'][5][member])
        active=state['data'][5][state['data'][7]['classes'][key][0]]
        negative.append(dict(class_id=key,price=-1,graph=active,support_sha256=active.sha))
        details.append(dict(class_id=key,native_columns=cache['snapshot'].matrix.shape[1],
            graph_identity=graph_content_hash(full)==required[key]['complete_graph_sha256'],
            original_native_builder_snapshot_and_coupling_identical=True,
            all_current_physical_primitives_in_complete_graph=True))
    expansion.apply(negative,state['data'],qualified,destination/'FIRST',load_cache)
    promoted=expansion.apply(negative,state['data'],qualified,destination/'SECOND',load_cache)
    assert len(expansion.promoted)==3
    assert all(c['graph'].sha==required[c['class_id']]['complete_graph_sha256'] for c in promoted)
    # Exercise the real source-compilation chain in the same delayed order as
    # production, while calling no model builder or solver.
    from v44 import worker
    from v44_recovery_r029 import voltage_policy, phase_rebuild
    from v42_may_campaign_native90 import a_stage
    from v42_a_stage_canary import phase
    original_stage=worker.a_stage
    seen=[]
    def stage(request):
        namespace=a_stage.group(phase,('activate','run'),OUT=None,
            full_pricing=lambda *a,**k:None,targeted=lambda *a,**k:None)
        seen.append(namespace['full_pricing'].__module__)
    request=dict(day='2025-05-03',arm='B3',stage='A2',root=str(destination),output=str(destination))
    with voltage_policy.install(),phase_rebuild.install():
        with patch.object(worker,'a_stage',stage),policy.install(),phase_rebuild.stage_scope(request):
            worker.a_stage(request)
    assert seen==[policy.__name__]
    assert worker.a_stage is original_stage
    assert not calls

proof=dict(UTC=now(),PASS=True,Native_optimization_calls=len(calls),sources=op.sources(),
    three_real_repeated_classes=details,complete_native_columns=expansion.columns,
    immutable_prior_state=record(root/'STATIC/P1_CLOSED_STATE.pkl.gz'),
    full_oracle=record(root/'BLOCK_PRICING_ORACLE_VERIFICATION.json'),
    original_source_compiler_chain_passed=True,no_active_worker_edited=True,
    measured_speedup_claimed=False)
atomic(destination/'VALIDATION.json',proof)
print(proof)
