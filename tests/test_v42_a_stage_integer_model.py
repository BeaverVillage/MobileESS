import numpy as np
import pytest
from test_v42_a_stage_compact_rowgen import fixture
from v42_a_stage_practical.integer_model import typed_block
from v42_a_stage_early.candidate import point_for_option
from v42_a_stage_compact_rowgen.projection import exact_replay

@pytest.mark.parametrize('N',(1,2,3))
def test_integer_types_are_original_expanded_native_not_SUM(N):
    data,axes,stay,migration,cache,_=fixture(N)
    s,B,c,u=typed_block(data,'c',cache['graph'],axes)
    assert (s.matrix-cache['snapshot'].matrix).nnz==0
    assert np.any(s.vtypes!='C')
    for option in (stay,migration):
        p=point_for_option(dict(snapshot=s,B=B,units=u,graph=cache['graph']),data[1]['j0'],data[3],option,N)
        assert exact_replay(s,p)['PASS']
        assert np.all(p[s.vtypes!='C']==np.rint(p[s.vtypes!='C']))
    if N>1:assert len([v for v in u if v['optional']])==N
