from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from test_v42_a_stage_compact_rowgen import fixture
from test_v42_a_stage_phase1 import solve
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_practical.integer_model import typed_block
from v42_a_stage_domain_v2.lexstage import project_migration_zero
from v42_a_stage_lexfull.projection import restrict,objectives

@pytest.mark.parametrize('N',(1,2,3))
def test_full_zero_projection_matches_original_integer_lanes_and_all_objectives(N,tmp_path):
    data,axes,stay,mig,old,_=fixture(N);graph=old['graph']
    s,B,c,u=native_block(data,'c',graph,axes,averaged=True)
    cache=dict(snapshot=s,B=B,constant=c,units=u,graph=graph)
    projected,PB,pc,pu,lift,receipt=restrict(data,'c',cache,axes)
    assert receipt['PASS'] and not receipt['SUM_integerized']
    original,OB,oc,ou=typed_block(data,'c',graph,axes)
    original=replace(original,objectives=objectives(ou,data[1]['j0']))
    terms=original.objective('migration_count').coefficients()
    row=sp.csr_matrix(([float(v) for v in terms.values()],([0]*len(terms),list(terms))),shape=(1,original.matrix.shape[1]))
    original=replace(original,matrix=sp.vstack((original.matrix,row),format='csr'),rhs=np.append(original.rhs,0),senses=np.append(original.senses,'='))
    direct,_,proof=project_migration_zero(original,migration_lock_row=original.matrix.shape[0]-1)
    for name in ('rho','migration_count','shift_magnitude','prestart_relocation'):
        a=replace(projected,objectives=(projected.objective(name),));b=replace(direct,objectives=(direct.objective(name),))
        sa,va,_=solve(a,tmp_path,'compact'+name+str(N));sb,vb,_=solve(b,tmp_path,'original'+name+str(N))
        assert sa==sb==2 and va==vb
    assert np.array_equal(pc,oc)
    assert N==1 or all(t=='I' for t in projected.vtypes)
