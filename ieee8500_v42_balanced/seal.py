"""Light regression, inherited-byte preservation and auditable artifact/source SHAs."""
import io
import unittest
import numpy as np
from .common import *

REQUIRED=('SOURCE_AUTHORITY.md','BALANCED_UNBALANCED_SOURCE_AUDIT.csv','CUSTOMER_POWER_CONSERVATION.csv',
    'FIXED_VARIABLE_LOAD_AUDIT.csv','BALANCED_B0_PLANNING_AC_96.csv','BALANCED_B0_ACTUAL_AC_96.csv',
    'BALANCED_B0_FRESH_RECEIPT.json','VOLTAGE_SECURITY_COMPARISON.csv','PRIMARY_TRIPLEX_LOADING_COMPARISON.csv',
    'BINDING_LINE_96SLOT.csv','TOP20_CRITICAL_LINES.csv','PCC_CONTROLLABILITY_PRECHECK.csv',
    'CONTROL_STATE_COMPARISON.csv','SINGLE_CASE_DECISION_REPORT_KO.md','FINAL_REVIEW_KO.md')


def extra_audits():
    b=read(REPORT/'BALANCED_CUSTOMER_RECORDS.json');u=read(REPORT/'UNBALANCED_CUSTOMER_RECORDS.json')
    index={r['name']:i for i,r in enumerate(u)}; ratio=float(read(DATA/'historical/SCREENING_RULE_PR62.json')['PV_ratio'])
    pv=[]
    for r in b:
        i=index[r['name']+'a'];j=index[r['name']+'b'];a=u[i];c=u[j]
        capacity_a=a['kw']*ratio;capacity_b=c['kw']*ratio
        pv.append(dict(customer_id=r['name'],balanced_load_bus=r['buses'][0],PV_a='aemo_pv_'+f'{i:04d}',PV_b='aemo_pv_'+f'{j:04d}',
            same_old_hot_bus_a=a['buses'][0],same_old_hot_bus_b=c['buses'][0],capacity_a_kw=capacity_a,capacity_b_kw=capacity_b,
            capacity_sum_kw=capacity_a+capacity_b,old_customer_capacity_kw=ratio*(a['kw']+c['kw']),
            capacity_difference_kw=(capacity_a+capacity_b)-ratio*(a['kw']+c['kw']),
            same_Planning_Actual_installation=True,PV_redistributed=False,measured_installation=False))
    table(REPORT/'PV_CUSTOMER_LOSSLESS_MAPPING.csv',pv)
    inv=read(PR193/'ORIGINAL_FEEDER_INVENTORY.json');mapping=rows(MAPPING)
    parent_lines={r['element']:r for r in inv['lines']}
    pre=read(REPORT/'precheck/PREREGISTRATION.json');all_paths=rows(REPORT/'PCC_SOURCE_PATHS.csv')
    path_audit=[]
    for line in pre['targets']:
        meta=parent_lines[line]
        affected=sorted({r['PCC'] for r in all_paths if r['element'].lower()==line.lower()})
        path_audit.append(dict(line=line,group=meta['group'],bus1=meta['buses'][0],bus2=meta['buses'][1],
            nphase=meta['nphase'],ncond=meta['ncond'],NormalAmps=meta['normal_amps'],length=meta['length'],linecode=meta['linecode'],
            original_parent_terminal=meta['parent_terminal'],downstream_AIDC=';'.join(s for s in affected if s.startswith('AIDC')),
            downstream_STA=';'.join(s for s in affected if s.startswith('STA')),
            path_phase_note='Topology downstream does not imply equal effect on every primary phase; see measured P/Q sensitivities'))
    table(REPORT/'CRITICAL_LINE_PATH_AUDIT.csv',path_audit)
    for r in read(ROOT/'ieee8500_v42/data/FEEDER_SOURCE_MANIFEST.json')['files']:
        assert sha(SOURCE/r['name'])==r['sha256']


def tests():
    suites=unittest.TestSuite()
    for path in ('tests/ieee8500_v42_balanced','tests/ieee8500_v42_aemo'):
        suites.addTests(unittest.TestLoader().discover(str(ROOT/path)))
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suites)
    (REPORT/'TEST_LOG.txt').write_text(stream.getvalue(),encoding='utf-8')
    doc=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),PASS=result.wasSuccessful(),
        own_campaign_writes=0,Native_calls=0)
    write(REPORT/'TEST_RECEIPT.json',doc);assert result.wasSuccessful(),stream.getvalue()
    print('regression tests',doc,flush=True)


def preservation():
    checked={}
    for prefix in ('docs/ieee8500_v42_single_case','docs/ieee8500_v42_aemo_voltage_rebuild'):
        manifest=read(ROOT/prefix/'ARTIFACT_SHA256_MANIFEST.json')
        for name,r in manifest['files'].items():assert sha(ROOT/name)==r['sha256'],name
        checked[prefix]=len(manifest['files'])
    core=read(PR193/'V42_SOURCE_SHA_MANIFEST.json')
    for name,value in core['files'].items():assert sha(ROOT/name)==value
    changed=git('diff','--name-only',P5_COMMIT).decode().splitlines()
    own=('docs/ieee8500_v42_balanced_case/','ieee8500_v42_balanced/','tests/ieee8500_v42_balanced/')
    assert all(n.startswith(own) for n in changed), ('PARENT_TRACKED_FILES_CHANGED',changed)
    write(REPORT/'PARENT_PRESERVATION.json',dict(PASS=True,parent_commit=P5_COMMIT,sealed_namespace_counts=checked,
        inherited_V42_core_bytes_checked=len(core['files']),source_DSS_changed=0,parent_result_or_code_changes=0,
        own_campaign_writes=0,scheduler_mutations=0,worker_kills=0,scope='content identity, not frozen external worker progress'))


def manifest():
    assert all((REPORT/n).is_file() for n in REQUIRED)
    files={}
    roots=('docs/ieee8500_v42_balanced_case','ieee8500_v42_balanced','tests/ieee8500_v42_balanced')
    excluded={'ARTIFACT_SHA256_MANIFEST.json'}
    for prefix in roots:
        for p in sorted((ROOT/prefix).rglob('*')):
            if not p.is_file() or p.name in excluded or '/dss/' in p.as_posix() or '__pycache__' in p.parts:continue
            n=p.relative_to(ROOT).as_posix();files[n]=dict(sha256=sha(p),bytes=p.stat().st_size)
    write(REPORT/'ARTIFACT_SHA256_MANIFEST.json',dict(schema='BALANCED_OFFICIAL_CASE_RESEARCH_SEAL_V1',parent_P5_commit=P5_COMMIT,
        files=files,content_sha=digest(files),required_outputs=15,Production_eligible=False,final_case_frozen=False,
        self_manifest_excluded=True,Native_calls=0))
    print('sealed',len(files),'files,',sum(r['bytes'] for r in files.values()),'bytes; contentSHA',digest(files),flush=True)


def code_manifest():
    dependencies=('ieee8500_v42/ac.py','ieee8500_v42/screening.py','ieee8500_v42_aemo/common.py',
        'ieee8500_v42_aemo/engine.py','ieee8500_v42_aemo/run_b0.py','ieee8500_v42_aemo/data_binding.py',
        'ieee8500_v42_aemo/archives.py','ieee8500_v42_aemo/diagnostics.py','ieee8500_v42_aemo/sensitivity.py')
    sources={n:sha(ROOT/n) for n in dependencies}
    for p in sorted((ROOT/'ieee8500_v42_balanced').glob('*.py')):sources[p.relative_to(ROOT).as_posix()]=sha(p)
    write(REPORT/'CODE_SOURCE_SHA256.json',dict(parent_unbalanced_P5_commit=P5_COMMIT,Balanced_code_files=sources,
        source_roster_sha256=digest(sources),engine=read(REPORT/'SOURCE_AUTHORITY.json')['engine_version']))


def run():
    extra_audits();tests();preservation();code_manifest()
    (REPORT/'REPRODUCE.md').write_text('''# 재현

부모 P5 commit 및 원본 데이터 SHA를 유지한 현재 branch에서 실행한다. Python3.11, NumPy1.26.4, SciPy1.14.1, pandas2.2.3, OpenDSSDirect0.9.4 / DSS-CAPI0.14.5가 기존 실행 환경이다. 새 원본 수집·normalization·Job/C1 생성 없이 부모 `.npz` 입력을 그대로 사용한다.

```powershell
python -B -m ieee8500_v42_balanced.audit before
python -B -m ieee8500_v42_balanced.audit audit
python -B -m ieee8500_v42_balanced.run_ac
python -B -m ieee8500_v42_balanced.precheck
python -B -m ieee8500_v42_balanced.verify
python -B -m ieee8500_v42_balanced.report
python -B -m ieee8500_v42_balanced.figures
python -B -m ieee8500_v42_balanced.audit after
python -B -m ieee8500_v42_balanced.seal
```

after snapshot은 실행 시의 기존 캠페인 등록·source/manifest를 읽기만 한다. 현재 작업의 쓰기·중단·Scheduler 변경은 허용하지 않는다. 다른 Worker의 외부 진행/추가 등록까지 정지시키거나 동일하다고 주장하지 않는다. 결과를 다시 만들면 다른 별도 출력 작업 트리에서 실행해 이번 sealed 결과와 SHA를 비교해야 한다. Native / B1–B3 Solver 호출은 없다.

96슬롯 전체 hard-axis archive는 `ac/BALANCED_{PLANNING,ACTUAL}[_FRESH]/AC_96.npz`이고 metadata는 AC_AXES.json이다. 전체 고객/두 레그/PV/PCC/전력수지는 CUSTOMER_PV_PQ_96.npz, 원본제어 궤적은 CONTROL_STATES.json/CSV다. 별도의 Fresh가 동일 byte input으로 새 context를 compile한다. 2025-05-01은 이미 노출된 날이며 미노출 holdout은 아니다.
''',encoding='utf-8')
    manifest()


if __name__=='__main__':run()
