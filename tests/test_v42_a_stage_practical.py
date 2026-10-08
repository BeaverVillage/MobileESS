from dataclasses import replace,asdict
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from test_v42_a_stage_compact_rowgen import fixture
from v42_a_stage_compact_rowgen.assembly import build,compact_inverse,partition
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.backend import update_graph
from v42_a_stage_early.candidate import point_for_option,exact_coupling
from v42_a_stage_compact_rowgen.projection import exact_replay

@pytest.mark.parametrize('N',(1,2,3))
def test_reusable_builder_matches_all_original_rows_and_couplings(N):
    data,axes,stay,migration,cache,_=fixture(N)
    from v42_a_stage_domain_v2.domain import physical_domain
    domains={uid:physical_domain(j,data[2][uid],data[3]) for uid,j in data[1].items()}
    data,ledger=update_graph(data,domains,'c',cache['graph'])
    base=LinearSnapshot(sp.csr_matrix((len(axes),0)),np.zeros(0),np.zeros(0),np.full(len(axes),'='),np.zeros(len(axes)),np.zeros(0,dtype='U1'),(Objective('rho',(),Fraction(7)),)).require()
    candidates=[]
    for o in (stay,migration):
        p=point_for_option(cache,data[1]['j0'],data[3],o,N)
        candidates.append(dict(class_id='c',option=asdict(o),coupling=tuple((i,str(v)) for i,v in exact_coupling(cache['B'],p).items())))
    state=build(base,tuple(range(len(axes))),0,{k:i for i,k in enumerate(axes)},data,domains,ledger,candidates)
    local,owned=partition(state['compact'],state['metas'],state['grows'])
    m=state['metas']['c'];x=np.zeros(state['compact'].matrix.shape[1]);x[m['offset']+m['compact_path_columns'][1]]=N
    original=expanded_point(state,x);inverse=compact_inverse(state,original)
    assert exact_replay(replace(state['compact'],matrix=state['compact'].matrix[len(axes):],senses=state['compact'].senses[len(axes):],rhs=state['compact'].rhs[len(axes):]),inverse)['PASS']
    assert exact_coupling(state['compact'].matrix[:len(axes)],x)==exact_coupling(state['reference'].matrix[:len(axes)],original)
    assert exact_coupling(state['compact'].matrix[:len(axes)],inverse)==exact_coupling(state['reference'].matrix[:len(axes)],original)
    assert len(owned)==state['compact'].matrix.shape[1] and local['c']
    for name in ('rho','migration_count','shift_magnitude','prestart_relocation'):
        def cost(s,z):o=s.objective(name);return o.constant+sum((c*Fraction(float(z[j])) for j,c in o.coefficients().items()),Fraction(0))
        assert cost(state['compact'],x)==cost(state['reference'],original)==cost(state['compact'],inverse)
