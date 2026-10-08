"""A genuine integer gap forces both LP children of the best-bound engine."""
from dataclasses import replace
from types import SimpleNamespace
import json
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_lexfull import tree

def test_both_children_close_full_pool_and_certify_integer_gap(tmp_path,monkeypatch):
    for name in ('LEX_FULL_SOURCE_FREEZE.json','LEX_FULL_BUILD_VERIFICATION.json'):
        (tmp_path/name).write_text(json.dumps(dict(PASS=True)))
    monkeypatch.setattr(tree,'OUT',tmp_path);monkeypatch.setattr(tree,'STATIC',tmp_path)
    A=sp.csr_matrix([[1,1,0,0,0,0],[1,0,1,0,0,0],[0,1,1,0,0,0],
        [0,0,0,1,1,0],[0,0,0,1,0,1],[0,0,0,0,1,1]],dtype=float)
    integer=LinearSnapshot(A,np.zeros(6),np.ones(6),np.full(6,'>'),np.ones(6),np.full(6,'B'),
        (Objective('shift_magnitude',tuple((j,1) for j in range(6))),)).require()
    lp=replace(integer,vtypes=np.full(6,'C'))
    class Native:
        budget=SimpleNamespace(record=dict(deadline_unix=123));calls=[]
        def remaining(self):return 100
        def solve(self,s,folder,component):
            r=linprog(np.ones(6),A_ub=-s.matrix,b_ub=-s.rhs,bounds=list(zip(s.lower,s.upper)),method='highs')
            assert r.success
            pi=-r.ineqlin.marginals;raw=dict(X=r.x,Pi=pi,RC=np.ones(6)-s.matrix.T@pi)
            self.calls.append((s.lower.copy(),s.upper.copy()));return dict(status=2),raw
    n=Native();_,raw=n.solve(lp,tmp_path,'NODE_LP');n.calls=[]
    incumbent=np.array([1,1,0,1,1,0.]);physical=SimpleNamespace(verify=lambda x:dict(PASS=True))
    result=tree.continue_tree(n,lp,raw,3.,dict(value=4.),incumbent,physical,np.ones(6),tmp_path,integer,'shift_magnitude')
    assert result['processed_nodes']==1 and len(n.calls)==2
    assert len(result['queue']['nodes'])==3
    assert n.calls[0][1][0]==0 and n.calls[1][0][0]==1
    assert np.ceil(result['valid_LB']-1e-6)>=4
