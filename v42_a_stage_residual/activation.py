from fractions import Fraction
from v42_a_stage_phase1.backend import update_graph,assemble_original
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_early.candidate import expanded_graph,point_for_option,exact_coupling
from v42_pr134_b1.common import atomic
from .policy import POLICY
from .native import BudgetStop

def activate(state,negative,iteration,folder,activations,budget):
    base,descriptor,data,domains,ledger,base_axes,n,grows,local_rows,owned=state
    proposed=data;newledger=ledger;selected=list(negative)
    if len(selected)>64:raise ValueError('BATCH_64_LIMIT')
    for c in selected:
        budget.remaining()
        uid=data[7]['classes'][c['class_id']][0]
        graph=expanded_graph(proposed[5][uid],c['option'],data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
        block,B,constant,units=native_block(proposed,c['class_id'],graph,tuple(base_axes),averaged=False)
        target=dict(snapshot=block,B=B,graph=graph,units=units)
        concrete=point_for_option(target,data[1][uid],data[3],c['option'],c['cardinality'])
        replay=primal_replay(block,concrete)
        if not replay['PASS'] or exact_coupling(B,concrete)!={r:Fraction(v) for r,v in c['coupling']}:
            raise ValueError('TARGET_ORIGINAL_NATIVE_CANDIDATE_REPLAY_FAIL')
        proposed,newledger=update_graph(proposed,domains,c['class_id'],graph)
    budget.remaining()
    counts=newledger['receipt']
    if counts['active_STAY'] > .5*counts['physical_STAY'] or counts['active_migration']>2000000:
        atomic(folder/'EXPANSION_STOP.json',dict(counts=counts,committed=False))
        raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
    budget.remaining()
    new,desc,global_rows,lrows,owners,axes=assemble_original(base,grows,n,base_axes,proposed)
    if new.matrix.shape[1]>200000 or new.matrix.shape[1]-activate.previous_cols>POLICY['max_new_native_columns_per_round']:
        atomic(folder/'EXPANSION_STOP.json',dict(rows=new.matrix.shape[0],cols=new.matrix.shape[1],nnz=new.matrix.nnz,committed=False))
        raise BudgetStop('PHASE1_DOMAIN_EXPANSION_TOO_LARGE')
    budget.remaining()
    for c in selected:
        activations.append(dict(iteration=iteration,class_id=c['class_id'],candidate_id=c['candidate_id'],kind=c['kind'],
            option=repr(c['option']),exact_reduced_cost=str(c['price']),coefficient_sha256=c['coefficient_sha256'],cardinality=c['cardinality'],residual_score=c['residual_score'],
            native_local_PASS=True,physical_membership_PASS=True,exact_coupling_PASS=True,independent_rc_PASS=True))
    return proposed,newledger,new,desc,global_rows,lrows,owners,axes
