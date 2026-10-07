"""Separate restored closed-LP queue; preserve both old children and the old file."""
from fractions import Fraction
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT
from v42_a_stage_bnp.queue import Queue,Node

def run():
    folder=OUT/'M19/P2/SHIFT_MAGNITUDE';old=read(folder/'BEST_BOUND_CHECKPOINT.json')
    repaired=read(OUT/'CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json');one=read(folder/'TREE/N1/INDEPENDENT_NODE_CLOSURE.json')
    if not repaired['PASS'] or not one['PASS']:raise ValueError('BOTH_CHILD_LP_CLOSURES_REQUIRED')
    q=Queue();q.next_id=old['queue']['next_id']
    for n in old['queue']['nodes']:
        n=dict(n,restrictions=tuple(tuple(r) for r in n['restrictions']));q.nodes[n['id']]=Node(**n)
    if set(q.nodes)!={0,1,2} or q.nodes[0].status!='BRANCHED' or q.nodes[1].restrictions!=((106932,'UPPER',1),) or q.nodes[2].restrictions!=((106932,'LOWER',2),):raise ValueError('EXACT_ORIGINAL_BOTH_CHILDREN_REQUIRED')
    parent=Fraction(q.nodes[0].lower_bound)
    q.close_lp(1,max(parent,Fraction(one['valid_LB'])),row_closed=True,column_closed=True)
    q.close_lp(2,max(parent,Fraction(repaired['valid_LB'])),row_closed=True,column_closed=True)
    L=q.global_bound()
    atomic(OUT/'CERTIFICATE_RECOVERY/RESTORED_BEST_BOUND_CHECKPOINT.json',dict(PASS=L is not None,queue=q.document(),
        valid_global_LP_LB=float(L),incumbent=old['incumbent'],original_file_unchanged=record(folder/'BEST_BOUND_CHECKPOINT.json'),
        child1=record(folder/'TREE/N1/INDEPENDENT_NODE_CLOSURE.json'),child2=record(OUT/'CERTIFICATE_RECOVERY/REPAIRED_NODE_BOUND.json'),
        parent_bound_inherited_validly=True,both_children_OPEN_not_pruned=True,no_new_native_solve=True,
        no_integer_optimality_claim=True,current_stronger_full_native_integer_bound_not_overwritten=True,source=record(__file__)))
    print('RESTORED_BEST_BOUND_QUEUE',float(L),flush=True)
if __name__=='__main__':run()
