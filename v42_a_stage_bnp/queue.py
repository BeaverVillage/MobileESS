"""Deterministic best-bound queue with strict closed-bound provenance."""
from dataclasses import dataclass,asdict
from fractions import Fraction
import heapq

@dataclass
class Node:
    id:int
    parent:int|None
    restrictions:tuple
    lower_bound:str|None=None
    row_closed:bool=False
    column_closed:bool=False
    status:str='OPEN'

class Queue:
    def __init__(self):self.nodes={};self.next_id=0
    def add(self,parent,restrictions=()):
        n=Node(self.next_id,parent,tuple(restrictions));self.nodes[n.id]=n;self.next_id+=1;return n
    def close_lp(self,id,bound,*,row_closed,column_closed):
        if not row_closed or not column_closed:raise ValueError('NODE_BOUND_REQUIRES_BOTH_CLOSURES')
        n=self.nodes[id];n.lower_bound=str(Fraction(bound));n.row_closed=True;n.column_closed=True
    def split(self,id,column,value):
        n=self.nodes[id];v=Fraction(value);floor=v.numerator//v.denominator
        if v.denominator==1:raise ValueError('BRANCH_OBJECT_MUST_BE_FRACTIONAL')
        left=self.add(id,n.restrictions+((int(column),'UPPER',floor),))
        right=self.add(id,n.restrictions+((int(column),'LOWER',floor+1),))
        n.status='BRANCHED';return left,right
    def best(self):
        ready=[n for n in self.nodes.values() if n.status=='OPEN' and n.lower_bound is not None]
        if not ready:return None
        return min(ready,key=lambda n:(Fraction(n.lower_bound),n.id))
    def global_bound(self):
        opened=[n for n in self.nodes.values() if n.status=='OPEN']
        if not opened or any(not n.row_closed or not n.column_closed or n.lower_bound is None for n in opened):return None
        for n in self.nodes.values():
            if n.status not in ('OPEN','BRANCHED','PRUNED_INFEASIBLE','PRUNED_BOUND','INTEGER_FEASIBLE'):raise ValueError('UNPROVEN_NODE_FATHOMING')
        return min(Fraction(n.lower_bound) for n in opened)
    def document(self):return dict(nodes=[asdict(n) for n in sorted(self.nodes.values(),key=lambda n:n.id)],next_id=self.next_id)

def gap(L,U):
    L,U=Fraction(L),Fraction(U)
    if L>U:raise ValueError('CERTIFIED_LOWER_BOUND_EXCEEDS_INCUMBENT')
    return (U-L)/abs(U) if U else Fraction(0) if L==0 else None
