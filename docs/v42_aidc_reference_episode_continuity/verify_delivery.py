"""Final artifact verification; --refresh seals only this new delivery manifest."""
from build_evidence import *

def main(refresh=False):
    required='REFERENCE_EPISODE_CONTRACT.md EPISODE_IDENTITY_AUTHORITY.md CANONICAL_REFERENCE_LEDGER.parquet CANONICAL_REFERENCE_LEDGER_SCHEMA.json REFERENCE_LEDGER_FREEZE.json CROSS_DAY_CONTINUITY_AUDIT.csv CROSS_DAY_CONTINUITY_SUMMARY.json APR1_APR2_PENDING_RUNNING_CONTINUITY.csv APR1_APR2_CONTINUITY_SUMMARY.json REFERENCE_CAPACITY_RACK_AUDIT.csv REFERENCE_CAPACITY_RACK_SUMMARY.json POLICY_INDEPENDENCE_AUDIT.json REFERENCE_GENERATOR_INPUT_AUDIT.json SPATIAL_TEMPORAL_ELIGIBILITY_AUDIT.csv RUNNING_IMMUTABILITY_AUDIT.json WORKER_ORDER_REPRODUCIBILITY.json OLD_VS_NEW_REFERENCE_COMPARISON.csv SOURCE_MANIFEST.json DELIVERY_MANIFEST.json FINAL_REVIEW_KO.md FINAL_VERDICT.json'.split()
    assert all((HERE/n).is_file() for n in required)
    freeze=read(HERE/'REFERENCE_LEDGER_FREEZE.json');flags=read(HERE/'FINAL_VERDICT.json')
    assert sha(REPO/'v42_reference_episode.py')==freeze['code']['sha256']
    assert sha(HERE/'CANONICAL_REFERENCE_LEDGER.parquet')==freeze['ledger']['sha256']
    f=pd.read_parquet(HERE/'CANONICAL_REFERENCE_LEDGER.parquet')
    assert len(f)==242842 and not f.duplicated(['operating_day','episode_id']).any()
    assert f.operating_day.max()=='2025-04-30'
    assert f.groupby('episode_id').reference_AIDC_site.nunique().max()==1
    assert not f.grid_information_used.any() and not f.policy_output_used.any() and not f.future_outcome_used.any()
    assert f.temporal_eligible_if_authorized.isna().all() and not f.migration_selected_in_reference.any()
    for day,h in freeze['day_hashes'].items():
        assert day_hash((HERE,day))[1]==h
        assert sha(HERE/'days'/f'{day}.json.gz')==freeze['daily_bytes'][day]
    assert flags['V42_PROBLEM4_REFERENCE_PLACEMENT_READY']==freeze['ready']==False
    try:frozen_day(HERE,'2025-04-01')
    except ValueError as e:assert str(e)=='REFERENCE_NOT_READY'
    else:raise AssertionError('UNREADY_FREEZE_WAS_EXECUTABLE')
    coverage=read(HERE/'OLD_87_APRIL_CHANGE_COVERAGE.json')
    assert coverage['old_changed_UID_with_preserved_new_site']==coverage['old_changed_UID_both_new_rows_capacity_feasible']==87
    for r in read(HERE/'PROTECTED_INPUTS_BEFORE.json'):assert sha(r['path'])==r['sha256']
    sample=pd.read_csv(HERE/'UNKNOWN_POLICY_DIFFERENCE_CLASSIFICATION.csv')
    assert set(sample.reference_rule_sha256)=={freeze['code']['sha256']}
    assert sample.classification.eq('PHYSICAL_STATE_DEPENDENCE').all()
    if refresh:
        manifest=dict(status=flags['status'],files=[rec(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='DELIVERY_MANIFEST.json' and '__pycache__' not in p.parts],
            implementation=[rec(REPO/'v42_reference_episode.py'),rec(REPO/'tests/test_v42_reference_episode.py')],manifest_self_excluded=True,
            source_branch='codex/v42-r0-aidc-reference-episode-continuity',unmodified_dependencies=['Runtime ML','CC4','MESS','electrical response kernel','trust','epsilon'])
        (HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    manifest=read(HERE/'DELIVERY_MANIFEST.json')
    for r in manifest['files']+manifest['implementation']:assert sha(r['path'])==r['sha256'],'DELIVERY_HASH_DRIFT:'+r['path']
    print(json.dumps(dict(PASS=True,required_artifacts=len(required),rows=len(f),days=len(freeze['day_hashes']),
        delivery_files=len(manifest['files']),ready=freeze['ready'],old_87_capacity_and_site_regression_pass=True)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');main(p.parse_args().refresh)
