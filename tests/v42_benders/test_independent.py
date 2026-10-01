import copy
import numpy as np
import pytest
import gurobipy as gp
from v42_benders.common import read
from v42_benders.fixtures import build,CASES
from v42_benders.canonical import from_model
from v42_benders.certificates import Uncertifiable
from v42_benders.independent import verify

@pytest.mark.parametrize('case',list(CASES))
def test_independent_COO_and_affine_domination_verifier(case):
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=build(env,case);can=from_model(m)
    rows=[r for r in read('FIXTURE_CUT_PAYLOADS.json') if r['case']==case]
    known=[(np.asarray(r['source_x']),r['record']['recourse_optimum']) for r in rows if r['record']['type']=='optimality']
    for r in rows:
        cut=dict(record=r['record'],coefficients=np.array(r['coefficients']),multipliers=np.array(r['multipliers']),source_x=np.array(r['source_x']))
        assert verify(can,cut,known)['independent_implementation']
    m.dispose();env.dispose()

def test_independent_physical_source_adversarial_replay():
    audit=read('INDEPENDENT_CUT_REPLAY_AUDIT.json')
    assert audit['PASS'] and audit['certificates']==1536 and audit['optimize_calls']==0
    assert audit['additional_stronger_perturbation_rejections']==48
    assert all(c['physical_infeasible_sources']>0 and c['all_certificates_PASS'] for c in audit['cases'])

@pytest.mark.parametrize('field',['ray_sign','bound_term','B_coefficient','RHS'])
def test_independent_verifier_rejects_payload_mutations(field):
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=build(env,'J');can=from_model(m)
    row=next(r for r in read('FIXTURE_CUT_PAYLOADS.json') if r['case']=='J' and r['record']['type']=='feasibility')
    cut=dict(record=copy.deepcopy(row['record']),coefficients=np.array(row['coefficients']),multipliers=np.array(row['multipliers']),source_x=np.array(row['source_x']))
    if field=='ray_sign':cut['multipliers']*=-1
    elif field=='bound_term':cut['record']['bound_row_contribution']='100'
    elif field=='B_coefficient':cut['coefficients'][0]+=1
    else:cut['record']['intercept']+=1
    with pytest.raises(Uncertifiable):verify(can,cut)
    m.dispose();env.dispose()
