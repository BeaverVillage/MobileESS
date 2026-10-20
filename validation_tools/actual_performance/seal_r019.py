from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r019 import operations as ops
from v44_recovery_r019.a2_continue import ADMISSION
from v44_recovery_r018.operations import validate as validate18
proof=read(ADMISSION);verify(proof['sources']+[proof['checkpoint'],proof['implementation']]);validate18()
parent=ops.CAMPAIGN/'2025-05-02/B3'
first=read(parent/'attempt001/A2/NATIVE_RUNTIME_LEDGER.json');second=read(parent/'attempt002/A2/NATIVE_RUNTIME_LEDGER.json')
assert first['calls']==second['calls'] and first['measured_Native_Runtime']==second['measured_Native_Runtime'] and second['inflight'] is None
assert read(parent/'attempt002/A2/RESULT.json')['error']=='NameError("name \'folder\' is not defined")'
tree=ET.parse('D:/MobileESS_V44/development/r019_regressions_final.xml').getroot()
assert not tree.findall('.//failure') and not tree.findall('.//error') and len(tree.findall('.//testcase'))==180
report=dict(UTC=now(),PASS=True,revision='v44_recovery_r019',
    inherited_checkpoint_validation=record(ops.OPS/'R018_CHANGE_AND_VALIDATION.json'),
    checkpoint_admission=record(ADMISSION),checkpoint=proof['checkpoint'],
    correction='Restore original folder=OUT/day initialization in resumed Phase I; no mathematical changes.',
    direct_S15_entry_test_PASS=True,previous_connection_failure=record(parent/'attempt002/A2/RESULT.json'),
    previous_connection_new_Native_seconds=0.,original_545_calls_preserved=True,
    inherited_Native_seconds=proof['Native_account']['measured'],remaining_Native_seconds=proof['Native_account']['remaining'],
    A2_total_Native_ceiling=5400.,Native_clock_reset=False,next_solve=15,
    original_inclusion_witness=proof['original_inclusion_witness'],regressions=180,
    regression_receipt=record('D:/MobileESS_V44/development/r019_regressions_final.xml'),
    sources=ops.sources(),original_scientific_sources_unchanged=True,constraints_or_tolerances_relaxed=False)
path=ops.OPS/'R019_CHANGE_AND_VALIDATION.json';assert not path.exists();atomic(path,report)
ops.make_permit()
snapshot=ops.OPS/'source_snapshots/r019';snapshot.mkdir(exist_ok=False)
for source in Path('v44_recovery_r019').glob('*.py'):(snapshot/source.name).write_bytes(source.read_bytes())
atomic(snapshot/'MANIFEST.json',dict(UTC=now(),sources=ops.sources(),permit=record(ops.PERMIT),validation=record(path)))
atomic(ops.OPS/'R019_SEALED.json',dict(UTC=now(),PASS=True,sources=ops.sources(),source_sha=digest(ops.sources()),
    permit=record(ops.PERMIT),validation=record(path)))
ops.validate();print(dict(PASS=True,regressions=180,start_solve=15,inherited_native_seconds=proof['Native_account']['measured']))
