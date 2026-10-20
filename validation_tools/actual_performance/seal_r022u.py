"""Unconditional r022 deployment, without touching its live sealed source."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r022u
from v44.common import read,record,verify,atomic,now,digest
from v44_recovery_r022 import operations as old
from v44_recovery_r022u import operations as new
old.validate()
tests=Path('D:/MobileESS_V44/development/r022u/regressions.xml');tree=ET.parse(tests).getroot()
assert len(tree.findall('.//testcase'))==234 and not tree.findall('.//failure') and not tree.findall('.//error')
changes={'phase_rebuild.py','operations.py','handover.py','reporting.py'}
for p in Path('v44_recovery_r022').glob('*.py'):
    if p.name not in changes:
        assert (Path('v44_recovery_r022u')/p.name).read_text(encoding='utf-8-sig')==p.read_text(encoding='utf-8-sig').replace('r022','r022u').replace('R022','R022U'),p.name
before=Path('v44_recovery_r022/phase_rebuild.py').read_text(encoding='utf-8-sig').replace('r022','r022u').replace('R022','R022U')
after=Path('v44_recovery_r022u/phase_rebuild.py').read_text(encoding='utf-8-sig')
start=before.index('    pilot=request.');end=before.index('    output=Path(',start)
assert before[:start]+'    row_generation=stable\n'+before[end:]==after
assert 'pilot_result' not in after
verify(read(old.OPS/'R022_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
protected=read(old.OPS/'R022U_HANDOVER_GUARD.json')
from v44.locks import alive
assert alive(protected['protected_worker']) and alive(protected['protected_coordinator'])
report=dict(UTC=now(),PASS=True,algorithm_revision='v44_recovery_r022',operational_revision='v44_recovery_r022u',
    regressions=234,regression_receipt=record(tests),authorization=record(old.OPS/'R022U_USER_AUTHORIZATION.json'),
    pilot_PASS_required=False,prior_A2_result_read=False,unconditional_stages=['B1/A1','B3/A2'],common_B1_A2_supported=True,
    test_prior_A2_states=['MISSING','RUNNING','FAILED','PASS'],
    boundary='CURRENT_WORKER_AND_COORDINATOR_NATURAL_EXIT_AFTER_ANY_TERMINAL_STATUS_NO_PASS_GATE',
    algorithm_sources_equal_after_revision_label_normalization=True,phase_scope_only_change='REMOVE_FOUR_LINE_PILOT_STATUS_LOOKUP_AND_SELECT_ROW_GENERATION_FOR_EVERY_SUPPORTED_STAGE',
    Native_optimizer_calls=0,current_worker_interrupted=False,Native_clock_reset=False,
    original_PhaseI_primal_dual_FullPhi_inclusion_pricing_and_Native_budgets_unchanged=True,
    old_source_sealed=record(old.OPS/'R022_SEALED.json'),old_permit=record(old.PERMIT),sources=new.sources())
p=old.OPS/'R022U_CHANGE_AND_VALIDATION.json';assert not p.exists();atomic(p,report)
new.make_permit();out=old.OPS/'source_snapshots/r022u';out.mkdir(exist_ok=False)
for source in Path('v44_recovery_r022u').glob('*.py'):(out/source.name).write_bytes(source.read_bytes())
atomic(out/'MANIFEST.json',dict(UTC=now(),sources=new.sources(),permit=record(new.PERMIT),validation=record(p)))
atomic(old.OPS/'R022U_SEALED.json',dict(UTC=now(),PASS=True,sources=new.sources(),source_sha=digest(new.sources()),permit=record(new.PERMIT),validation=record(p)))
old.validate();new.validate();print(dict(PASS=True,regressions=234,unconditional_future_B1_B3=True,current_r022_worker_unchanged=True))
