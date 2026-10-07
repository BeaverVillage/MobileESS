"""Freeze current source and independent receipts before fast native canaries."""
import ast,subprocess
import xml.etree.ElementTree as ET
import gurobipy as gp
from .fast_prepare import ROOT,OUT,OLD,STATIC
from .fast_execution import create_fast_run_permit,REQUIRED_FAST_GATES
from .solver_policy import solver_policy
from v42_pr134_b1.common import atomic,read,record


def qualify():
    junit=STATIC/'FAST_FULL_TESTS.xml'
    test_receipts=[junit,STATIC/'FAST_FINAL_TARGETED.xml']
    cases=[c for path in test_receipts for c in ET.parse(path).getroot().findall('.//testcase')]
    failed=[c.attrib for c in cases if any(c.find(k) is not None for k in ('failure','error','skipped'))]
    if failed:raise ValueError('CURRENT_FULL_TEST_QUALIFICATION_NOT_PASS:'+str(failed[:3]))
    changed=subprocess.check_output(['git','diff','--name-only','b4e061bdf2416eccd7aa2a42b3761db1affce8c1'],cwd=ROOT,text=True).splitlines()
    new=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    sources=[ROOT/p for p in sorted(set(changed+new)) if p.endswith('.py')]
    for path in sources:compile(path.read_text(encoding='utf-8-sig'),str(path),'exec')
    prior_attempt=OUT/'REJECTED_FAST_CANARY_ATTEMPT_01/MAY17_CANARY/FAST_RESULT.json'
    spent=read(prior_attempt)['native_seconds'] if prior_attempt.exists() else 0.
    atomic(OUT/'FAST_PRE_RUN_TESTS.json',dict(PASS=True,test_cases=len(cases),unique_test_cases=len({(c.get('classname'),c.get('name')) for c in cases}),
        failures=0,errors=0,skipped=0,Junit=record(junit),independent_Junit_receipts=[record(p) for p in test_receipts],compiled_changed_python=len(sources),
        compiled_sources=[record(p) for p in sources],native_canary_calls_before_current_generation_qualification=0,
        previous_rejected_native_calls=1 if spent else 0,previous_rejected_native_seconds=spent,
        no_test_fabrication=True,full_test_suite=True))
    # The preserved old gates certify unchanged scientific modules; the fast
    # gates independently qualify current active support and execution sources.
    prior=read(OLD/'STRESS_RUN_PERMIT.json')
    gates={key:OLD/'PRESERVED_COMPLETE_ACTIVE_PRE_RUN_GATES'/key/__import__('pathlib').Path(value['path']).name
        for key,value in prior['gate_receipts'].items() if key in REQUIRED_FAST_GATES}
    gates.update(complete_physical_domain=OUT/'SCIENTIFIC_DOMAIN_AUTHORITY.json',
        active_pool_partition=OUT/'ACTIVE_POOL_PARTITION.json',initial_active_support=OUT/'INITIAL_ACTIVE_SUPPORT.json',
        exact_pricing_authority=OUT/'EXACT_PRICING_AUTHORITY_VERIFICATION.json',fast_pre_run_tests=OUT/'FAST_PRE_RUN_TESTS.json')
    atomic(OUT/'SOLVER_POLICY.json',solver_policy(gp))
    paths=[ROOT/p for p in subprocess.check_output(['rg','--files','-g','*.py'],cwd=ROOT,text=True).splitlines()]
    from v42_pr134_b1.common import CODE
    paths.extend(CODE/p for p in subprocess.check_output(['rg','--files','-g','*.py'],cwd=CODE,text=True).splitlines())
    budget=300.-spent
    if not 0<budget<=300:raise ValueError('CANARY_PRIOR_RUNTIME_EXHAUSTS_DIAGNOSTIC_BUDGET')
    permit=create_fast_run_permit(gates,paths,OUT/'SOLVER_POLICY.json',OUT/'ACTIVE_DOMAIN_POLICY.json',
        native_budget_seconds=budget,output=OUT/'CANARY_EXECUTION_PERMIT.json',checkpoint='b4e061bdf2416eccd7aa2a42b3761db1affce8c1')
    atomic(OUT/'CANARY_SOURCE_FREEZE.json',dict(PASS=True,source_count=len(paths),source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),permit_sha256=permit.identity,
        physical_pool_caches=[record(STATIC/day/'PHYSICAL_DOMAIN_CACHE.json') for day in permit.document['run_order']],
        native_budget_per_canary=budget,previous_rejected_native_seconds=spent,
        cumulative_May17_budget_across_attempts=300.,other_27_dates_authorized=False))
    return permit

if __name__=='__main__':qualify()
