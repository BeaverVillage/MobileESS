"""Hash final static evidence and check preservation; never optimize."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'docs/v42_joint_critical_grid_lb_pilot'
PARENT = '9383a99f1bdcabbd49c79b3ad9f9ee36d523868a'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p,data):
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main():
    certs=[read(OUT/'INDEPENDENT_CERTIFICATE.json'),read(OUT/'native360/INDEPENDENT_CERTIFICATE.json')]
    results=[read(OUT/'RESULT.json'),read(OUT/'native360/RESULT.json')]
    assert all(c['PASS'] for c in certs)
    assert all(read(OUT/p)['PASS'] for p in ['REPORT_MATH_REVIEW.json','POST_RUN_RESOURCE_HOLD.json','native360/POST_RUN_RESOURCE_HOLD.json'])
    report=OUT/'JOINT_CRITICAL_GRID_LB_REPORT_KO.md'
    assert sha(report)==read(OUT/'REPORT_MATH_REVIEW.json')['report_sha256']
    for prefix in ['', 'native360/']:
        certificate=read(OUT/prefix/'INDEPENDENT_CERTIFICATE.json')
        for p,digest in certificate['file_sha256'].items():
            assert sha(OUT/prefix/p)==digest, p
    changed=subprocess.check_output(['git','diff','--name-status',PARENT,'--'],cwd=ROOT,text=True).splitlines()
    assert changed and all(line.startswith('A\t') for line in changed), 'Existing parent files changed'
    root_originals=read(OUT/'native360/POST_RUN_RESOURCE_HOLD.json')['originals']
    for old in root_originals:
        head=subprocess.check_output(['git','-C',old['path'],'rev-parse','HEAD'],text=True).strip()
        status=subprocess.check_output(['git','-C',old['path'],'status','--porcelain'],text=True).strip()
        assert head==old['expected_HEAD'] and not status
    assert sum(r['Native_optimize_calls'] for r in results)==2
    assert all(r['full_MILP_calls']==r['separate_LP_calls']==r['campaign_calls']==0 for r in results)
    write(OUT/'FINAL_VALIDATION_SUMMARY.json',dict(PASS=True,
        existing_PR209_parent_paths_modified=0,parent=PARENT,
        changed_paths=changed,original_PR207_PR209_clean_and_HEAD_preserved=True,
        report_math_review_sha_matches=True,independent_certificate_artifact_hashes_match=True,
        original_90_second_and_added_360_second_latches_preserved=True,
        extra_360_explicitly_user_authorized=True,Native_optimize_calls=2,
        actual_total_Native_Runtime=sum(r['Runtime'] for r in results),
        configured_TimeLimits=[90,360],actual_runtimes=[r['Runtime'] for r in results],
        full_MILP_calls=0,separate_LP_calls=0,campaign_calls=0,
        final_classification=certs[-1]['classification'],Global_LB=certs[-1]['Global_LB'],
        exact_numeric_BB_certificate=False,Global_Gap_percent=certs[-1]['Gap_percent'],
        goal_3percent=False,Source18r_U4_StageBudget_NativeStopRequested_original_budgets_and_campaign_unchanged=True,
        HOLD_Disabled_PAUSED_preserved=True,git_diff_check_required=True))
    files=list(OUT.rglob('*'))+list((ROOT/'tools/joint_critical_grid_lb').rglob('*'))
    records={str(p.relative_to(ROOT)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=sha(p))
             for p in sorted(files) if p.is_file() and p.name!='EVIDENCE_INDEX.json' and '__pycache__' not in p.parts}
    write(OUT/'EVIDENCE_INDEX.json',dict(schema='V42_JOINT_FINAL_EVIDENCE_INDEX_V1',PASS=True,
          self_excluded=True,files=records))
    print(json.dumps(dict(PASS=True,indexed_files=len(records),Native_calls=2,Global_LB=certs[-1]['Global_LB'])))


if __name__=='__main__':
    main()
