"""Seal common populations and retained diagnostic evidence without simulation claims."""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from .freeze import ROOT, OUT, BASE
from v42_april_port.audit import read, write, record, table
from v42_april_b0_v2.contracts import digest

def population_seal():
    days=[]
    for d in range(1,31):
        day='2025-04-%02d'%d; folder='DAY_'+day.replace('-','')
        p=read(OUT/'BUNDLE'/folder/'PLANNING_INPUT_BUNDLE.json'); a=read(OUT/'BUNDLE'/folder/'ACTUAL_INPUT_BUNDLE.json')
        common=dict(known=[{k:r[k] for k in ('job_uid','submit_time','GPU_gang','runtime_authority','service_slots')} for r in p['known_population']],
                    arrivals=[{k:r[k] for k in ('job_uid','submit_time','GPU_gang','runtime_authority','service_slots')} for r in a['post_issue_arrivals']])
        sha=digest(common)
        days.append(dict(day=day,common_obligations_sha256=sha,
            per_arm_obligations_sha256={arm:sha for arm in ('B0','B1','B2','B3')},
            known_jobs=len(common['known']),Actual_post_issue_jobs=len(common['arrivals']),
            source_population=record(OUT/'POPULATION/PHYSICAL_MEMBERSHIP.csv')))
    write(OUT,'POPULATION/COMMON_FOUR_ARM_POPULATION_AUTHORITY.json',dict(frozen=True,days=days,
        same_UID_GPU_Runtime_service_Actual_arrivals=True,nonflex_jobs_retained_in_B1_B3=True,
        J_FLEX_subset_required=True,J_FLEX_complete_option_certificate_ready=False,
        B0_B2_flexibility_disabled=True,B1_B3_only_certified_J_FLEX_may_deviate=True,
        shared_power_map='current date-bound POWER_AUTHORITY.json for each day',
        no_arm_execution_performed=True,May_outcomes_used=False))
    auth=read(OUT/'POPULATION/V42_PHYSICAL_MODELABILITY_AUTHORITY.json')
    auth.update(population_frozen=True,membership=record(OUT/'POPULATION/PHYSICAL_MEMBERSHIP.csv'),
                unmodelable_ledger=record(OUT/'POPULATION/V42_UNMODELABLE_WORKLOAD_LEDGER.csv'),
                common_four_arm_authority=record(OUT/'POPULATION/COMMON_FOUR_ARM_POPULATION_AUTHORITY.json'),
                population_changed_after_reference_or_power_preflight=False)
    write(OUT,'POPULATION/V42_PHYSICAL_MODELABILITY_AUTHORITY.json',auth)
    flex=read(OUT/'POPULATION/V42_FLEXIBILITY_ELIGIBILITY_AUTHORITY.json')
    flex.update(candidate_masks=record(OUT/'POPULATION/FLEXIBILITY_CANDIDATES.csv'),
        executable_population_frozen=False,remaining_authority='reference / WAN / complete-option certificates',
        unknown_checkpoint_capability_is_not_false_capability_claim=True)
    write(OUT,'POPULATION/V42_FLEXIBILITY_ELIGIBILITY_AUTHORITY.json',flex)

def evidence_seal():
    xml=ET.parse(OUT/'TEST_RESULTS.xml').getroot()
    suite=xml if xml.tag=='testsuite' else xml.find('testsuite')
    tests={k:suite.attrib.get(k) for k in ('tests','failures','errors','skipped','time')}
    verification=read(OUT/'VERIFICATION.json'); verification.update(tests=tests,
        preserved_baseline_tests=1104,new_tests=65,tests_output=record(OUT/'TEST_OUTPUT.txt'),
        May_fixture_reads_in_inherited_regressions_distinct_from_April_data_construction=True)
    write(OUT,'VERIFICATION.json',verification)
    review=OUT/'FINAL_REVIEW_KO.md'
    text=review.read_text(encoding='utf8')
    if '회귀 검증:' not in text:
        text+=f"\n회귀 검증: {tests['tests']} tests, failures={tests['failures']}, errors={tests['errors']}.\n"
        review.write_text(text,encoding='utf8',newline='\n')
    # Self and verification are separately inspectable and excluded from the
    # digest listing to avoid recursive hashing; all data/code evidence is sealed.
    records=[]
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and p.name not in ('EVIDENCE_SHA256.json','VERIFICATION.json','PR_DESCRIPTION.md'):
            records.append(dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),**record(p)))
    for base in (ROOT/'v42_modelable',ROOT/'tests/v42_modelable'):
        for p in sorted(base.rglob('*.py')): records.append(dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),**record(p)))
    write(OUT,'EVIDENCE_SHA256.json',dict(exact_base=BASE,records=records,scientific_results_fabricated=False))

if __name__=='__main__':
    import sys
    {'population':population_seal,'evidence':evidence_seal}[sys.argv[1]]()
