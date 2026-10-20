from pathlib import Path
import sys,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024b
from v44.common import read,record,verify,atomic,now
from v44_recovery_r024b.operations import validate,OPS,CAMPAIGN
validate();verify(read(OPS/'R024B_PASS_AND_M1_PRESERVATION_BASELINE.json')['files'])
case=CAMPAIGN/'2025-05-02/B3/attempt010';output=case/'A2/OUTPUT'
ledger=read(case/'A2/NATIVE_RUNTIME_LEDGER.json');trace=read(output/'PHASE_I_TRACE.json')
assert ledger['Native_ceiling_seconds']==5400. and ledger['Phase_I_separate_time_limit'] is None
assert ledger['Native_clock_reset'] is False and ledger['inherited_Native_seconds']==458.1179983615875
assert trace['trajectory'][0]['row_closed'] and trace['trajectory'][0]['Phi']<.001543
price=output/'PHASE_I/S0/PRICE/EXPLORED';progress=read(price/'PRICING_PROGRESS.json')
assert progress['fully_priced_classes']>=1
certificates=[]
for path in price.glob('B/*/*/EXACT_QUERY.json'):
    value=read(path);assert value['certificate']['PASS'];certificates.append(record(path))
assert certificates
receipt=dict(UTC=now(),PASS=True,active_algorithm='r024a',operational_adapter='r024b',
    case=str(case),Native_total_limit=5400,Phase_I_separate_limit=None,Native_clock_reset=False,
    inherited_Native_seconds=458.1179983615875,current_measured_Native_seconds=ledger['measured_Native_Runtime'],
    first_row_closed_Phi=trace['trajectory'][0]['Phi'],first_LP=record(output/'PHASE_I/S0/NATIVE_RESULT.json'),
    numerical_primal_dual_acceptance=record(output/'PHASE_I/S0/R024B_NUMERICAL_ACCEPTANCE.json'),
    restored_roster=record(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json'),
    fully_priced_classes=progress['fully_priced_classes'],exact_native_query_certificates=certificates,
    missing_roster_error_repaired_and_production_pricing_entered=True,previous_PASS_bytes_preserved=True,
    A2_completed=False,A2_gap_certified=False,commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
atomic(OPS/'R024B_FIRST_NATIVE_AND_PRICING_VERIFIED.json',receipt)
atomic(Path(__file__).resolve().parents[2]/'docs/v44/R024B_FIRST_NATIVE_AND_PRICING_VERIFIED.json',receipt)
h=read(OPS/'CURRENT_HANDOFF.json');h.update(adapter_source_commit=receipt['commit'],
    first_production_verification=record(OPS/'R024B_FIRST_NATIVE_AND_PRICING_VERIFIED.json'))
atomic(OPS/'CURRENT_HANDOFF.json',h)
print(dict(PASS=True,Native=receipt['current_measured_Native_seconds'],Phi=receipt['first_row_closed_Phi'],
    classes=progress['fully_priced_classes'],exact_query_certificates=len(certificates)))
