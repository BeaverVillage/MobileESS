from .common import *
from .domain import tests as domain_tests,child_data,check_child
from v42_physics_redesign.exact_cut import construct
from v42_b2_root_validation.certificate import verify_certificate,tests as exact_tests
import py_compile
import gurobipy as gp

def main():
    prior.forbid_optimize();compiled=[]
    for p in (ROOT/'v42_group_branching').glob('*.py'):py_compile.compile(str(p),doraise=True);compiled.append(p.name)
    for n in ('BARRIER_ITRCNT','BARRIER_PRIMOBJ','BARRIER_DUALOBJ','BARRIER_PRIMINF','BARRIER_DUALINF'):assert hasattr(gp.GRB.Callback,n)
    assert read(REPORTS/'BINARY_MAPPING_AUDIT.json')['PASS'] and read(REPORTS/'BRANCH_DOMAIN_AUDIT.json')['PASS']
    assert read(REPORTS/'DUAL_CERTIFICATION_REPAIR_AUDIT.json')['independent']['PASS']
    A,d,T,AA,full=model_inputs();selected=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected'];rejects=0
    for candidate in selected:
        for value in (0,1):child_data(full,candidate['column'],value)
    j=selected[0]['column'];child=child_data(full,j,0)
    for field in ('objective','rhs','lower','upper'):
        changed=dict(child);changed[field]=child[field].copy();k=0 if field in ('objective','rhs') else (j+1)%len(d['types']);changed[field][k]+=1
        try:check_child(full,changed,j,0)
        except AssertionError:rejects+=1
    assert rejects==4
    # Analytic infeasible scalar domain: y+w=1.5, y=1, 0<=w<=.25.
    fixture=sparse.csr_matrix([[1.,1.]])
    mathdata=dict(objective=np.zeros(2),constant=np.array(0.),rhs=np.array([1.5]),sense=np.array(['=']),lower=np.array([1.,0.]),upper=np.array([1.,.25]))
    proof=construct(fixture,mathdata,np.array([],dtype=int),np.array([1.]),WORK/'artifacts/FARKAS_ANALYTIC_FIXTURE','feasibility')
    check=verify_certificate(fixture,mathdata,proof);assert check['certified_LB']==.25>0
    result=dict(PASS=True,compiled_modules=compiled,callback_API_constants_PASS=True,
        full_binary_mapping_PASS=True,child_static_types_and_domain_PASS=True,objective_RHS_other_bound_mutations_rejected=rejects,
        synthetic_exhaustive=domain_tests(),independent_exact_kernel=exact_tests(),Farkas_analytic_fixture=check,
        license_concurrency_validation='ACTUAL_TWO_ENV_HOLD_BEFORE_FIRST_NATIVE',native_API_child_identity='WORKER_GATE_BEFORE_OPTIMIZE',
        maximum_calls=6,maximum_Runtime=2880,per_child_TimeLimit=480,loss_quality_gate_is_not_execution_gate=True,native_calls=0)
    write(REPORTS/'PREFLIGHT_TESTS.json',result);print('GROUP_PREFLIGHT_TESTS_PASS native=0',flush=True)

if __name__=='__main__':main()
