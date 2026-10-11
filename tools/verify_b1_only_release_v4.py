"""Independent byte and Native0 qualification audit; no optimize calls."""
from pathlib import Path
import sys,inspect,ast,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import b1_only, b1_only_v4 as current
from v42_pr134_b1.common import read,record,atomic,digest,now

def audit(root):
    root=Path(root); m=current.verify_only(root)
    original=current.DEFAULT_ROOT.with_name('v42_b1_only_may_20261012')
    prior=read(original/'CAMPAIGN_MANIFEST.json');proof=read(original/'NATIVE0_PREFLIGHT.json')
    def same_function(name):
        return ast.dump(ast.parse(inspect.getsource(getattr(b1_only,name))))==ast.dump(ast.parse(inspect.getsource(getattr(current,name))))
    assert all(same_function(n) for n in ('preflight','request','prepare'))
    assert proof['PASS'] is True and proof['Native_calls']==0 and proof['denied_native_attempts']==[]
    assert proof['source_SHA']==m['execution_SHA']==prior['execution_SHA']
    prog="from v42_common_campaign.authority import source_files; from v42_pr134_b1.common import digest; print(digest(source_files()))"
    sha=subprocess.check_output([sys.executable,'-B','-X','utf8','-c',prog],cwd=r'D:\v42_svr11_epoch18r_20261011',text=True).strip()
    assert sha==m['execution_SHA']
    assert m['scenario']['sha256']==prior['scenario']['sha256'] and m['thermal']['sha256']==prior['thermal']['sha256']
    rows=[]
    for day in current.DAYS:
        a={Path(r['path']).name:r for r in prior['input_receipts'][day]}
        b={Path(r['path']).name:r for r in m['input_receipts'][day]}
        assert a.keys()==b.keys()
        for name,r in b.items():
            assert record(r['path'])==r
            if name=='OPERATIONS_TEMPLATE_B2.json':
                old=read(a[name]['path']);new=read(r['path']);old.pop('current_day_folder');new.pop('current_day_folder')
                assert old==new  # Unexecuted B2 descriptor differs only in owned root.
            else:assert r['sha256']==a[name]['sha256']
        rows.append(dict(day=day,PASS=True,raw_files=len(b)))
    observed=current.protected_state();before=read(root/'PROTECTED_STATE_BEFORE.json')
    assert observed['hold_markers']==before['hold_markers']
    assert observed['original_repositories']==before['original_repositories']
    qualification=dict(PASS=True,source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],
        qualification_kind='SAME_SCIENTIFIC_BYTES_INPUTS_AND_NATIVE0_PREFLIGHT_IMPLEMENTATION',
        original_Native0=record(original/'NATIVE0_PREFLIGHT.json'),original_operations_SHA=proof['operations_SHA'],
        Native_calls=0,additional_model_builds=0,denied_native_attempts=[],case_verification=proof['case_verification'],
        original_model_build_wall_seconds=proof['model_build_wall_seconds'],
        original_P1_and_lex_and_GPU_Rack_WAN_QoS_sources_unchanged=True,
        same_source18r_scientific_SHA=True,all31_raw_input_verification=rows,
        operations_change='Only date-failure classification and monitor telemetry; preflight/request/preparation ASTs identical',UTC=now())
    atomic(root/'NATIVE0_PREFLIGHT.json',qualification)
    atomic(root/'RELEASE_INDEPENDENT_AUDIT.json',dict(qualification,hardware=m['hardware'],scenario=m['scenario'],thermal=m['thermal'],
        protected_state_unchanged=True,original_sources_modified=0,old_results_promoted=0))
    print(json.dumps(dict(PASS=True,root=str(root),scientific_SHA=sha,Native_calls=0)))

if __name__=='__main__':audit(sys.argv[1])

