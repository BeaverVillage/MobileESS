"""Audit saved results/exports, without OpenDSS or optimization."""
import json,csv,hashlib
from pathlib import Path
from decimal import Decimal
import numpy as np
H=Path(__file__).absolute().parent;REF=H.parent/'IEEE8500_B0_POLICY_SCALE058_20260915'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=read(H/'SCREEN_TABLE.json');result=read(H/'SEARCH_RESULT.json');freeze=read(H/'SEARCH_FREEZE.json')
assert len(rows)==9 and result['new_exact_snapshots']==768
assert Decimal(str(result['boundary_upper']))-Decimal(str(result['boundary_lower']))<=Decimal('.0005')
reference=list(csv.DictReader((REF/'B0_96_SLOT_EXTREMA.csv').open(encoding='utf-8')))
audit_rows=[]
for r in rows:
    p=Path(r['folder']);assert sha(p/'B0_ALL_PHASE_ARRAYS.npz')==r['raw_sha256']
    slots=list(csv.DictReader((p/'B0_96_SLOT_EXTREMA.csv').open(encoding='utf-8')));assert len(slots)==96
    for t,(x,old) in enumerate(zip(slots,reference)):
        assert int(x['slot'])==t and x['converged']=='True' and x['control_actions_complete']=='True'
        for key in ['PV_scheduled_kw','AIDC_P_scheduled_kw','AIDC_Q_scheduled_kvar','MESS_P_scheduled_kw','MESS_Q_scheduled_kvar']:assert float(x[key])==float(old[key]),(r['scale'],t,key)
        for key in ['native_P_scheduled_kw','native_Q_scheduled_kvar']:assert abs(float(x[key])/r['scale']-float(old[key])/.58)<1e-10
    with np.load(p/'B0_ALL_PHASE_ARRAYS.npz') as z:
        v=z['voltage_pu'];a=z['line_current_loading_pu'];tx=z['transformer_current_loading_pu'];kv=z['transformer_winding_kva_loading_pu']
        assert [v.min(),v.max(),a.max(),tx.max(),kv.max()]==[r[k] for k in ['Vmin','Vmax','max_line_loading','transformer_current','transformer_kVA']]
        status='PASS' if v.min()>=.95 and v.max()<=1.05 and max(a.max(),tx.max(),kv.max())<=1 else 'FAIL'
        assert status==r['status']
        assert v.max()<=1.05 and max(a.max(),tx.max(),kv.max())<=1
    audit_rows.append(dict(scale=r['scale'],slots=96,convergence='PASS',PV_AIDC_MESS_unchanged='PASS',uniform_native_PQ_scaling='PASS',metrics_match_raw='PASS',hard_status=status))
selected=result['selected'];assert selected['Vmin']>=.9505
eligible=[r for r in rows if r['status']=='PASS' and r['Vmin']>=.9505]
assert max(eligible,key=lambda r:(r['max_line_loading'],r['scale']))==selected
tables=read(H/'csv/extracted_tables.json')
for t in tables:
    exported=list(csv.reader((H/'csv'/t['filename']).open(encoding='utf-8')))
    assert exported[0]==t['columns'] and len(exported)==len(t['rows'])+1
    for row,expected in zip(exported[1:],t['rows']):
        assert len(row)==len(expected)
        for actual,x in zip(row,expected):
            if isinstance(x,bool):assert actual==str(x).lower()
            elif isinstance(x,(float,int)):assert float(actual)==x
            else:assert actual==('' if x is None else x)
daily=list(csv.DictReader((H/f'csv/B0_{selected["scale"]}_DAILY_MAX_HEATMAP.csv').open(encoding='utf-8')))
critical=list(csv.DictReader((H/f'csv/B0_{selected["scale"]}_CRITICAL_TIME_HEATMAP.csv').open(encoding='utf-8')))
with np.load(Path(selected['folder'])/'B0_ALL_PHASE_ARRAYS.npz') as z:
    a=z['line_current_loading_pu'];axis={};byline={}
    for j,label in enumerate(z['line_phase_axes']):
        n,term,bus,node=str(label).lower().split('|');axis[n,term[1:],node[4:]]=j;byline.setdefault(n,[]).append(j)
    for r in daily:
        if r['data_status']=='DISABLED':assert not r['B0_element_max_loading'];continue
        assert float(r['B0_element_max_loading'])==a[:,byline[r['element_id']]].max()
        assert a[int(r['max_slot']),axis[r['element_id'],r['max_terminal'],r['max_phase']]]==float(r['B0_element_max_loading'])
    for r in critical:
        if r['data_status']=='DISABLED':assert not r['B0_loading_at_critical_time'];continue
        assert int(r['critical_slot'])==selected['critical_slot']
        assert float(r['B0_loading_at_critical_time'])==a[selected['critical_slot'],axis[r['element_id'],r['terminal'],r['phase']]]
assert all(sha(r['path'])==r['sha256'] for r in freeze['files'])
audit=dict(status='PASS',rows=audit_rows,all_original_sources_unchanged=True,all_candidate_convergence_and_controls_96=True,all_export_values_match=True,selected_daily_and_critical_CSV_checked_against_raw=True,hard_limits_not_relaxed=True,production_selection_checked=True,B1_B2_B3_runs=0)
(H/'FINAL_VERIFICATION.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
paths=[p for p in H.glob('*') if p.is_file() and p.name!='FINAL_MANIFEST.json']+list((H/'csv').glob('*.csv'))+list(H.glob('scale_*/*.png'))
(H/'FINAL_MANIFEST.json').write_text(json.dumps(dict(status='COMPLETE',files=[dict(path=str(p.absolute()),sha256=sha(p)) for p in paths]),ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL_VERIFICATION_PASS: 9 candidates, 768 new snapshots, unchanged source/PV/AIDC/MESS, exact CSV validation')
