"""Original native class histogram transport, without optimizing a model."""
from dataclasses import asdict,replace
from pathlib import Path
import subprocess
import numpy as np
import pytest
from v42_job_capability import Job,ServiceBoundary,Resources,Option
from v42_a_stage_domain_v2.domain import physical_domain
from v42_a_stage_phase1.producer import complete_graph
from v42_root.factor import stay,mapping
from v42_integration.a_seed import reference_assignments,full_replay


@pytest.fixture(scope='module')
def prior_assignments():
    code=subprocess.check_output(['git','show','f32b22adf8e3e53ab68256458cb991f9d30d2ecb:v42_integration/a_seed.py'],
        cwd=Path(__file__).resolve().parents[1],text=True)
    space=dict(__name__='v42_integration.prior_seed',__package__='v42_integration')
    exec(compile(code,'PR230_A_SEED.py','exec'),space)
    return space['reference_assignments']


def model_case(checkpoint):
    import gurobipy as gp
    j=Job('a','PENDING',0,0,2,'A',6,1,initial_sites=('A','B'),checkpoint_authorized=checkpoint,
        duration_authority='FIXTURE',qos_policy_id='RESEARCH',qos_receipt_sha='a'*64,
        qos_allowed_starts=(2,3),qos_budget_seconds=3600.)
    b=ServiceBoundary('FIXTURE',True,True,(2,3),12)
    r=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},{('AB',t):4 for t in range(12)},
        {('A','B'):('AB',),('B','A'):('AB',)},12,3,{}, {}, {},restart_slots=1,max_active_transfers=2)
    g=complete_graph(j,physical_domain(j,b,r));m=gp.Model();m.Params.OutputFlag=0
    v=stay(m,j,g,2,eliminate_f0=True,eliminate_state=True)
    m.addConstr(gp.quicksum(v['y'].values())==2)
    selector=m.addVar(lb=0,ub=1);v['migration_selected']={'selected':selector};m.addConstr(selector==0)
    m.update()
    jobs={'a':j,'b':replace(j,uid='b',qos_receipt_sha='b'*64)}
    data=({},jobs,{u:b for u in jobs},r,{}, {u:g for u in jobs},{u:g for u in jobs},{'classes':{'c':list(jobs)}})
    units=[dict(uid='a',members=['a','b'],optional=False,stay_count=True,v=v)]
    return m,units,data


@pytest.mark.parametrize('checkpoint',(False,True))
def test_default_transport_equals_original_literal_mapping(prior_assignments,checkpoint):
    m,units,data=model_case(checkpoint)
    try:
        assert reference_assignments(m,units,data)==prior_assignments(m,units,data)
        j=data[1]['a'];o=Option(2,'A',(('A',2,8),))
        from v42_compact.graph import old_to_compact
        literal=mapping(j,data[5]['a'],data[3],o);compact=old_to_compact(o)
        for family,items in literal.items():
            for key,value in items.items():assert compact.get(family,{}).get(key,0)==value
    finally:m.dispose()


def test_different_member_stays_use_histogram_and_full_native_replay():
    m,units,data=model_case(True)
    try:
        choice=asdict(Option(3,'B',(('B',3,9),)))
        fixed,plans=reference_assignments(m,units,data,{'b':choice})
        v=units[0]['v']['y']
        assert fixed[v['A',2].index]==fixed[v['B',3].index]==1
        assert sum(fixed[x.index] for x in v.values())==2
        point=np.zeros(m.NumVars)
        for index,value in fixed.items():point[index]=value
        assert full_replay(m,point)['PASS']
        assert plans['a']['start']==2 and plans['b']['start']==3
        with pytest.raises(ValueError,match='UID_NOT_IN_CURRENT_DOMAIN'):
            reference_assignments(m,units,data,{'missing':choice})
        with pytest.raises(ValueError,match='START_WINDOW'):
            reference_assignments(m,units,data,{'b':asdict(Option(7,'A',(('A',7,13),)))})
        with pytest.raises(ValueError,match='CANNOT_ASSIGN_MIGRATION'):
            reference_assignments(m,units,data,{'b':dict(choice,checkpoint=4,destination='A')})
    finally:m.dispose()
