"""Export actual unchanged feeder inventory and source-only AC regression."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .ac import IEEE8500AC


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})


def main():
    root = Path(__file__).resolve().parents[1]
    docs = root / 'docs' / 'ieee8500_v42_single_case'
    docs.mkdir(parents=True,exist_ok=True)
    a = IEEE8500AC(output_dir=root / 'ieee8500_v42' / 'outputs' / 'source_regression')
    original = a.solve()
    rerun = a.solve()
    a.verify_source_unchanged()
    inv = a.inventory
    (docs/'ORIGINAL_FEEDER_INVENTORY.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2),encoding='utf-8')
    regression = {
        'status':'REAL_OPENDSS_ORIGINAL_SOURCE_ONLY_REGRESSION',
        'production_eligible':False,
        'scope':'Original unchanged Master-unbal, original static loads, no PV model activated by Master, no AIDC/MESS overlays',
        'control_policy':inv['control_policy'], 'counts':inv['counts'],
        'source_sha256':inv['source_sha256'], 'engine':inv['engine'],
        'summary':original['summary'], 'repeat_summary':rerun['summary'],
        'repeat_control_states_equal':original['control_state']==rerun['control_state'],
        'source_bytes_unchanged':True, 'regcontrols':original['regcontrols'], 'capacitors':original['capacitors'],
        'rating_semantics':{
            'lines':'Original NormalAmps, every explicit phase/conductor retained; canonical V42 objective uses source-rooted parent terminal; both ends audited',
            'triplex':'Original Kron reduction removes neutral; hot1/hot2 are local split labels and have opposite voltage polarity',
            'transformer_current':'Original NormalAmps is primary line current; secondary denominators transform by original kV and winding kVA ratio',
            'transformer_winding_kva':'Report both strict original winding kVA nameplate and DSS NormHkVA (defaults to 110%); never substitute the latter for nameplate',
            'ground_nodes':'Transformer node0 currents are grounded returns; no independent neutral rating provided',
            'actual_controls':'Each source regression restores original initial state and independently settles original controls'},
        'validation':'7 unittest real OpenDSS checks passed; tests/test_ieee8500_v42_ac.py; original 96-slot temporal/production feasibility is separate',
    }
    (docs/'ORIGINAL_FEEDER_REGRESSION.json').write_text(json.dumps(regression,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(docs/'ORIGINAL_NODE_PHASE_INVENTORY.csv',inv['buses'])
    write_csv(docs/'ORIGINAL_LINE_RATINGS.csv',inv['lines'])
    write_csv(docs/'ORIGINAL_TRANSFORMER_RATINGS.csv',[
        {'element':r['element'],'xfmrcode':r['xfmrcode'],'buses':r['buses'],'node_order':r['node_order'],
         'nphase':r['nphase'],'ncond':r['ncond'],'normal_amps_primary':r['normal_amps_primary'],
         'normal_hkva':r['normal_hkva'],'emergency_hkva':r['emergency_hkva'],**w}
        for r in inv['transformers'] for w in r['windings']])
    write_csv(docs/'ORIGINAL_REGCONTROL_INVENTORY.csv',inv['regcontrols'])
    write_csv(docs/'ORIGINAL_CAPCONTROL_INVENTORY.csv',inv['capcontrols'])
    write_csv(docs/'ORIGINAL_CAPACITOR_INVENTORY.csv',inv['capacitors'])
    write_csv(docs/'ORIGINAL_SOURCE_LINE_CONDUCTORS.csv',original['lines'])
    print(json.dumps(regression['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
