"""Read-only receipt of actual corrected-Source reruns of the four old labels."""
from pathlib import Path
import sys,json
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
root=Path(sys.argv[1]);m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
rows=[]
for day in ('2025-05-19','2025-05-20','2025-05-21','2025-05-22'):
    row=ledger['dates']['B0/'+day];proof=read(root/'handoff37'/('B0_'+day+'.json'))
    assert row['status']=='PASS' and proof['PASS'] and proof['source_SHA']==m['execution_SHA']
    assert all(record(r['path'])==r for r in proof['evidence'])
    result=read(row['result']);environments={}
    for receipt in result['metrics']['evidence']:
        audit=read(receipt['path']);assert record(receipt['path'])==receipt
        slots=read(audit['slots_receipt']['path']);assert record(audit['slots_receipt']['path'])==audit['slots_receipt']
        peak=max(c['current_A'] for s in slots for c in s['physical']['currents']
            if c['element']=='transformer.reg1a' and c['terminal']==1 and c['phase']==1)
        environments[audit['namespace']]=dict(peak_reg1a_primary_A_A=peak,
            NormalAmps_A=763.323673207438,logical_slots=len(slots),
            original_transformer_current_authority=audit['original_transformer_current_authority'],
            original_nominal_diagnostic_exceedance_cells=audit['original_nominal_phase_current_diagnostic_exceedance_cells'],
            Full_AC_Physical_PASS=audit['Full_AC_Physical_PASS'],slots_receipt=audit['slots_receipt'])
    assert set(environments)=={'DAYAHEAD','ACTUAL'}
    rows.append(dict(day=day,PASS=True,result=record(row['result']),independent_96_slot_verification=record(root/'handoff37'/('B0_'+day+'.json')),
        environments=environments))
value=dict(schema='SVR11_CORRECTED_FOUR_OFFICIAL_RERUNS_V1',PASS=True,source_SHA=m['execution_SHA'],
    campaign_root=str(root),all_four_actual_reruns_PASS=True,old_results_promoted=False,
    Native_calls_by_this_verifier=0,AC_calls_by_this_verifier=0,dates=rows,UTC=now())
atomic(root/'CORRECTED_FOUR_OFFICIAL_RERUNS.json',value)
print(json.dumps({d['day']:d['environments']['ACTUAL']['peak_reg1a_primary_A_A'] for d in rows}))
