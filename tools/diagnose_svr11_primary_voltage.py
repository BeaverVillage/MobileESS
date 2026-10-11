"""Saved evidence only: distinguish protected Bus82 from unregulated primary."""
from pathlib import Path
import sys,json
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
root=Path(r'D:\v42_svr11_may_20261011_08');m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
comparisons=[];receipts=[]
for arm,day in [('B2','2025-05-04'),('B0','2025-05-04'),('B2','2025-05-03')]:
    result=Path(ledger['dates'][arm+'/'+day]['result']);r=read(result)
    ar=next(p for p in r['metrics']['evidence'] if 'ACTUAL' in p['path']);a=read(ar['path'])
    assert record(ar['path'])==ar and record(a['slots_receipt']['path'])==a['slots_receipt']
    slots=read(a['slots_receipt']['path']);values=[]
    for s in slots:
        v={n['node_phase']:n['voltage_pu'] for n in s['physical']['nodes']}
        bank=next(d for d in s['svr']['devices'] if d['id']=='BUS82');p=bank['phases'][0]
        values.append(dict(slot=s['slot'],Bus81A=v['81.1'],SVR82_primaryA=v['svr_bus82_series_input.1'],
            controlled_Bus82A=v['82.1'],line_voltage_rise=v['svr_bus82_series_input.1']-v['81.1'],
            SVR82_tap=p['tap'],W1_P_kw=p['terminals'][0]['P_into_kw'],W1_Q_kvar=p['terminals'][0]['Q_into_kvar'],
            Reg4A_tap=next(p['initial_tap'] for p in s['settled_original_controls']['original_regulators'] if p['name']=='creg4a')))
    comparisons.append(dict(arm=arm,day=day,execution_SHA=r['source_SHA'],status=r['status'],
        peak_primary=max(values,key=lambda v:v['SVR82_primaryA']),slot37=values[37],
        positive_line_rise_slots=sum(v['line_voltage_rise']>0 for v in values),values=values))
    receipts.extend([record(result),ar,a['slots_receipt']])
history=SOURCE/'docs/v42_capcontrol_svr_20261011/supporting_audits/SVR7_CE30_MAY03_UPSTREAM_FAILURE_AUDIT_03/MAY03_UPSTREAM_FAILURE_SAVED_CAUSE_AUDIT.json'
old=read(history)
out=dict(schema='SVR11_LINE82_PRIMARY_VOLTAGE_SAVED_CAUSE_V1',source_SHA=m['execution_SHA'],
    confirmed_physical_FAIL='B2/2025-05-04',failed_slot=37,failed_node='svr_bus82_series_input.1',
    voltage=1.0500718582125512,upper_limit=1.05,violation_cells=1,
    measurements_and_source_integrity_verified=True,comparisons=comparisons,source_receipts=receipts,
    historical_SVR7_saved_audit=record(history),historical_failed_cells=old['failed_cell_pairs'],
    interpretation='The downstream-terminal bank controls Bus82 but leaves the line82 receiving-side primary upstream of its regulated winding. Positive line voltage rise occurs in all96 slots on both saved B2 dates and B0. Capacitive Q flow and upstream automatic taps are observed; individual causal contributions have not been isolated. The current physical violation is genuine, not a path, current rating, tap range, convergence or metering error.',
    conservative_candidate='Relocate existing BUS82 bank to line82 terminal1 while retaining remote Bus82 A/B/C sensing, all11 banks, finite400A/kVA,120V/Band2/Delay30/TapDelay2/range/MaxTapChange1 and original seven controls. Candidate only; not installed, released, or certified.',
    decision='Keep current campaign FAIL-CONTINUE and observe other independent dates. Do not add an SVR solely for one violation. Any justified physical relocation requires a new common equipment/source epoch, fresh affected official physics/models/results and no mixing of old results.',
    scientific_workers_terminated=0,Native_calls=0,OpenDSS_solves=0,settings_or_tolerance_changed=False,UTC=now())
atomic(root/'LINE82_PRIMARY_VOLTAGE_CAUSE_AUDIT.json',out)
print(json.dumps({k:v for k,v in out.items() if k not in ('comparisons','source_receipts','historical_failed_cells')},ensure_ascii=False))
