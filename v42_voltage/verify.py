"""Read-only final evidence checks, including the stopped infeasible path."""
import csv,subprocess,xml.etree.ElementTree as ET
import numpy as np
from v42_root.common import *
from v42_native.voltage import authority_sha,PLANNING_LOWER_SQUARED,PLANNING_UPPER_SQUARED
from .a1 import check_sources


def verify():
    check_sources()
    required='README.md PREREGISTRATION.json PR104_BASE_RECEIPT.json PROBLEM13_PLANNING_ROBUSTNESS_CONTRACT.md PLANNING_VOLTAGE_AUTHORITY.json PLANNING_VOLTAGE_SOURCE_AUDIT.json ACTUAL_LOCAL_REPAIR_SUPERSESSION.json ACTUAL_REPAIR_CALL_AUDIT.json LOCAL_REPAIR_POLICY_IMPACT_AUDIT.json A1_MODEL_STATS.json A1_OPTIMIZATION.json A1_PHYSICAL_VALIDATION.json A1_VOLTAGE_MARGIN_REPORT.json A1_PROVISIONAL_CONTROL_TABLE.csv A1_UNKNOWN_POLICY_TABLE.json A1_AIDC_SITE_TIME_ANCHOR.csv A1_AIDC_GRID_CONTROL_ANCHOR.json A1_TO_M1_HANDOFF.json M1_PREFLIGHT.json M1_MODEL_STATS.json M1_VOLTAGE_AUTHORITY_RECEIPT.json M1_OPTIMIZATION.json M1_PROGRESS.csv M1_PHYSICAL_VALIDATION.json M1_VOLTAGE_MARGIN_REPORT.json VOLTAGE_MARGIN_OPERABILITY_REPORT.json M1_BOTTLENECK_DIAGNOSIS.json M1_NEXT_MODIFICATIONS.md PIPELINE_STATUS.json FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json'.split()
    assert all((OUT/n).is_file() for n in required)
    a=read(OUT/'A1_OPTIMIZATION.json');d=read(OUT/'A1_INFEASIBILITY_DIAGNOSIS.json');flags=read(OUT/'FINAL_FLAGS.json')
    assert a['passes'][0]['status']==3 and a['passes'][0]['incumbent'] is None and a['P1_lock'] is None
    assert a['total_optimize_seconds']<=3600 and a['settings']['Threads']==1 and a['settings']['MIPGap']==.005
    assert len(d['violations'])==145 and d['voltage_authority_sha256']==authority_sha()
    for row in d['violations']:
        c=np.asarray(row['voltage_coefficients']);lo=np.asarray(row['controls_lower']);hi=np.asarray(row['controls_upper'])
        lower=row['voltage_constant']+np.maximum(c,0)@lo+np.minimum(c,0)@hi
        upper=row['voltage_constant']+np.maximum(c,0)@hi+np.minimum(c,0)@lo
        assert abs(lower-row['minimum_squared'])<1e-12 and abs(upper-row['maximum_squared'])<1e-12
        assert lower>PLANNING_UPPER_SQUARED+1e-8 or upper<PLANNING_LOWER_SQUARED-1e-8
    assert not any(flags[k] for k in ('M1_RUN','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','PROBLEM13_FINAL_VALIDATED'))
    assert not flags['A1_COMPLETE'] and not flags['A1_HANDOFF_MATERIALIZED'] and not flags['UNKNOWN_FUTURE_INDIVIDUAL_JOBS_FABRICATED']
    for n in ('A1_PROVISIONAL_CONTROL_TABLE.csv','A1_AIDC_SITE_TIME_ANCHOR.csv'):
        with (OUT/n).open(encoding='utf8',newline='') as f:assert len(list(csv.DictReader(f)))==0
    assert read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json')['controls'] is None
    for n in ('M1_MODEL_STATS.json','M1_OPTIMIZATION.json','M1_PREFLIGHT.json'):assert read(OUT/n)['RUN'] is False
    assert not (LOCAL/'M1/STARTED.json').exists()
    executed=read(OUT/'A1_EXECUTED_SOURCE_MANIFEST.json');changed=[]
    for row in executed['sources']:
        if sha(ROOT/row['path'])!=row['sha256']:changed.append(row['path'])
    assert changed==['v42_voltage/setup.py'],changed
    suite=ET.parse(OUT/'TEST_RESULTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0 and int(suite.attrib['tests'])>=463
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):
        checks=subprocess.run(args,cwd=ROOT,capture_output=True)
        assert checks.returncode==0,(checks.stdout+checks.stderr).decode('utf8',errors='replace')
    evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='VERIFICATION.json']
    report=dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,inherited_calibration_warning=1,
                required_outputs=len(required),files=evidence,source_seals_PASS=True,executed_A1_physics_and_candidate_sources_unchanged=True,
                post_A1_source_changes=changed,post_A1_changes_reason='setup allowlist extended only for explicit supersession-aware historical preservation tests',
                independent_voltage_contradictions=145,empty_handoff_is_non_result=True,no_M1_execution=True,git_diff_check=True)
    dump('VERIFICATION.json',report);print('FINAL VERIFICATION PASS',report['tests'],'tests;',len(required),'required outputs')


if __name__=='__main__':verify()
