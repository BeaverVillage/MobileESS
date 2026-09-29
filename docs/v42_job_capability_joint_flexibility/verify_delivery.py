"""Verify reports, focused test receipt, protected inputs and delivered byte hashes."""
from pathlib import Path
import argparse, hashlib, json, re, sys, xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def dump(name,data):
    (HERE/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def verify(freeze=False):
    required='''README.md PREREGISTRATION.json EXISTING_FLEXIBILITY_IMPLEMENTATION_AUDIT.md
P1_P5_CURRENT_OBJECTIVE_AUDIT.md V42_SERVICE_BOUNDARY_AUDIT.json JOB_CAPABILITY_SPEC.md
FLEXIBILITY_SOURCE_AUTHORITY.json TRAIN_COHORT_LATENCY_STATISTICS.csv TIMESHIFT_RULE_COMPARISON.csv
TIMESHIFT_ELIGIBILITY_FUNNEL.csv TIMESHIFT_DELAY_BUDGET_DISTRIBUTION.csv PRESTART_PLACEMENT_AUDIT.csv
MIGRATION_CAPABILITY_AUDIT.csv CAPABILITY_MEMBERSHIP.csv CAPABILITY_OVERLAP_SUMMARY.csv
JOINT_OPTION_DOMAIN_AUDIT.csv OPTION_PRESCREEN_AUDIT.csv OBJECTIVE_REDESIGN_SPEC.md
PRIMARY_ONLY_DEGENERACY_AUDIT.json FLEXIBILITY_CAUSALITY_AUDIT.json SERVICE_PRESERVATION_AUDIT.json
BOUNDED_JOINT_MILP_CANARY.json FINAL_SELECTION_FREEZE.json FINAL_VERDICT.json FINAL_REVIEW_KO.md
SOURCE_MANIFEST.json'''.split()
    assert all((HERE/name).is_file() for name in required)
    report=(HERE/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(x) for x in re.findall(r'^(\d+)\. ',report,re.M)]==list(range(1,51))
    tests=ET.parse(HERE/'TEST_RESULTS.xml').getroot().findall('testsuite')
    assert sum(int(s.attrib['tests']) for s in tests)==39
    assert all(int(s.attrib['failures'])==int(s.attrib['errors'])==int(s.attrib['skipped'])==0 for s in tests)
    flags=read('FINAL_VERDICT.json')
    assert not flags['AIDC_MILP_JOINT_ACTION_READY'] and flags['TIMESHIFT_RULE_SELECTED']=='NONE'
    assert flags['V42_SERVICE_BOUNDARY_AUTHORITY']=='NOT_FINALIZED'
    assert all(flags[x] is False for x in ('FULL_IEEE123_CAMPAIGN_RUN','IEEE8500_CAMPAIGN_RUN',
        'RUNTIME_ML_CHANGED','CC4_CHANGED','RADDIT_EMBEDDING_USED','NEW_MAY_EVALUATION_RUN'))
    for name in ('SERVICE_PRESERVATION_AUDIT.json','R0_REPRODUCTION.json','CHECKPOINT_PHASE_AUDIT.json',
                 'BOUNDED_JOINT_MILP_CANARY.json','FLEXIBILITY_CAUSALITY_AUDIT.json','INPUT_PRESERVATION.json'):
        assert read(name)['PASS'] is True
    sources=read('SOURCE_MANIFEST.json')
    assert sha(HERE/'PREREGISTRATION.json')==sources['registered_input']['sha256']
    for item in sources['files']:
        assert sha(item['path'])==item['sha256'],item['path']
    population=read('POPULATION_SCOPE.json')
    entry=population['full_membership'];assert sha(entry['path'])==entry['sha256']
    membership=pd.read_csv(entry['path'],usecols=['operating_day','issue_seconds','split','can_timeshift',
        'can_prestart_place','can_checkpoint_migrate','FLEX','FIX'])
    assert len(membership)==242842 and membership.operating_day.max()<'2025-05-01'
    assert membership[['can_timeshift','can_prestart_place','can_checkpoint_migrate','FLEX','FIX']].isna().all().all()
    v=membership.split.eq('PREMAY_VALIDATION')
    assert v.sum()==90706 and membership.loc[v,'operating_day'].min()=='2025-01-02'
    assert membership.loc[v,'issue_seconds'].min()>=pd.Timestamp('2025-01-01T00:00:00Z').timestamp()
    options=pd.read_csv(HERE/'JOINT_OPTION_DOMAIN_AUDIT.csv')
    assert options.before.sum()==127 and options.after.sum()==76
    if freeze:
        dump('VERIFICATION.json',dict(PASS=True,verified_at_utc=datetime.now(timezone.utc).isoformat(),
            tests_passed=39,tests_failed=0,tests_skipped=0,protected_input_files=len(sources['files']),
            protected_hash_changes=0,required_review_questions_answered=50,historical_null_capability_rows=len(membership),
            final_rule_freeze_blocked=True,unknown_not_mislabeled_FIXED=True,
            canary_complete_options_before=127,canary_complete_options_after=76,
            command_scope=['read-only source/Git audits','pytest focused tests','reproduce.py historical tables and tiny synthetic MILPs','verify_delivery.py'],
            ML_native_IEEE_campaign_entrypoints_invoked=False,May_new_evaluation_invoked=False,
            note='First intermediate validation inventory used operating-day split; corrected to issue-time cutoff before delivery. No rule threshold or service constraint changed.'))
        files=[ROOT/'.gitattributes',ROOT/'v42_job_capability.py',ROOT/'tests/test_v42_job_capability.py']
        files+=sorted(p for p in HERE.iterdir() if p.is_file() and p.name!='DELIVERY_MANIFEST.json')
        dump('DELIVERY_MANIFEST.json',dict(schema='V42_CAPABILITY_DELIVERY_V1',self_excluded=True,
            large_membership=entry,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in files]))
    delivery=read('DELIVERY_MANIFEST.json')
    for item in delivery['files']:
        assert sha(ROOT/item['path'])==item['sha256'],item['path']
    print(json.dumps(dict(PASS=True,delivered_files=len(delivery['files']),protected_sources=len(sources['files']),tests=39)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');verify(p.parse_args().freeze)
