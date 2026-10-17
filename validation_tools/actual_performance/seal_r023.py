"""Seal the verified next-day assembly revision; never modify current workers."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r023
from v44.common import read,record,verify,atomic,now,digest
from v44.locks import alive
from v44_recovery_r022 import operations as current
from v44_recovery_r022u import operations as pending
from v44_recovery_r023 import operations as new
current.validate();pending.validate()
OPS=current.OPS
assert read(OPS/'CURRENT_HANDOFF.json')['active_revision']=='v44_recovery_r022'
assert read(OPS/'CURRENT_HANDOFF.json')['pending_revision']=='v44_recovery_r022u'
tests=Path('D:/MobileESS_V44/development/r023/regressions.xml')
tree=ET.parse(tests).getroot();count=len(tree.findall('.//testcase'))
assert count>=248 and not tree.findall('.//failure') and not tree.findall('.//error')
bench=Path('D:/MobileESS_V44/development/r023/full_138_classes/RESULT.json')
result=read(bench)
assert result['PASS'] and result['class_count']==138 and result['Native_calls']==0
assert result['whole_original_and_compact_matrix_objective_descriptor_proofs_metas_identical']
verify(read(OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
guard=read(OPS/'R022U_HANDOVER_GUARD.json')
assert alive(guard['protected_worker']) and alive(guard['protected_coordinator'])
for p in Path('v44_recovery_r022u').glob('*.py'):
    if p.name not in {'phase_rebuild.py','operations.py','handover.py'}:
        assert (Path('v44_recovery_r023')/p.name).read_text(encoding='utf-8')==p.read_text(encoding='utf-8-sig').replace('r022u','r023').replace('R022U','R023'),p.name
authorization=OPS/'R023_USER_AUTHORIZATION.json'
assert not authorization.exists()
atomic(authorization,dict(UTC=now(),user_instruction='응 병목 개선하고다음 날짜부터 적용하게 해.',
    previous_instruction='이후 미실행 B1 B3에도 현재 A2 PASS 조건 없이 적용',
    effective_from_day='2025-05-03',arms=['B0','B1','B3'],
    current_May02_r022_worker_unchanged=True,pilot_PASS_required=False,
    latest_monitor_instruction='매시간 Codex 점검·진단·적절한 오류 수정 및 실패 날짜 재개; 케이스 오류는 격리하고 즉시 다음 날짜 캠페인 진행'))
guard.update(UTC=now(),authorization=record(authorization),superseded_pending_permit=record(pending.PERMIT),
    effective_from_day='2025-05-03')
atomic(OPS/'R023_HANDOVER_GUARD.json',guard)
report=dict(UTC=now(),PASS=True,regressions=count,regression_receipt=record(tests),benchmark=record(bench),
    full_production_class_count=138,Native_optimizer_calls=0,
    source_changes=['one axis position vector per reference/compact rebuild','one combined sparse global coupling CSR per rebuild','next-day-only dispatch scope'],
    matrix_objective_descriptor_proofs_metas_identical=True,original_tolerances_and_all_proofs_preserved=True,
    existing_PASS_and_M1_baseline_verified=True,current_worker_interrupted=False,Native_clock_reset=False,
    current_source_seal=record(OPS/'R022_SEALED.json'),superseded_source_seal=record(OPS/'R022U_SEALED.json'),
    unconditional_future_B1_B3=True,pilot_PASS_required=False,effective_from_day='2025-05-03',
    authorization=record(authorization),sources=new.sources())
atomic(OPS/'R023_CHANGE_AND_VALIDATION.json',report)
new.make_permit()
out=OPS/'source_snapshots/r023';out.mkdir(exist_ok=False)
for source in Path('v44_recovery_r023').glob('*.py'):(out/source.name).write_bytes(source.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=new.sources(),permit=record(new.PERMIT),validation=record(OPS/'R023_CHANGE_AND_VALIDATION.json')))
atomic(OPS/'R023_SEALED.json',dict(UTC=now(),PASS=True,sources=new.sources(),source_sha=digest(new.sources()),permit=record(new.PERMIT),validation=record(OPS/'R023_CHANGE_AND_VALIDATION.json')))
current.validate();pending.validate();new.validate()
print(dict(PASS=True,regressions=count,current_r022_worker_unchanged=True,pilot_PASS_required=False))
