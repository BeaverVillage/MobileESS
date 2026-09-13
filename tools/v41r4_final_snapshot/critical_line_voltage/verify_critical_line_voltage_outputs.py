"""Independent saved-CSV verification. Reads raw copies; no scientific execution."""
import csv, hashlib, json, math, statistics
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def load(name):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
manifest=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
index=json.loads((ROOT/'selected_raw_index.json').read_text(encoding='utf-8'))
members={v['member']:v for v in index.values()}
references={r['date']:r for r in load('01_B0_reference_critical_points.csv')}
assert len(references)==31
counts={};observations={};checked_values=0;reduction_days={}
for name,metadata in manifest['CSV_files'].items():
    assert sha(ROOT/name)==metadata['sha256']
    rows=load(name);assert len(rows)==metadata['rows'];counts[name]=len(rows)
for state,file in [('preQ','02_policy_comparison_at_B0_critical_points_preQ.csv'),('postQ','05_policy_comparison_at_B0_critical_points_postQ.csv')]:
    rows=load(file);assert len(rows)==124
    keys={(r['date'],r['policy']) for r in rows};assert len(keys)==124
    by_key={(r['date'],r['policy']):r for r in rows}
    for row in rows:
        ref=references[row['date']]
        assert all(row[k]==ref[k] for k in ['date','slot','timestamp','line','phase','sending_bus','receiving_bus'])
        assert row['source_state']==state and row['reference_selection_state']=='B0_PRE_Q'
        source=members[row['source_npz_member']];p=ROOT/source['local']
        assert sha(p)==row['source_npz_sha256']==source['sha256']
        with np.load(p,allow_pickle=False) as z:
            t=int(row['slot']);i=int(row['source_branch_index']);si=int(row['source_sending_node_index']);ri=int(row['source_receiving_node_index'])
            assert str(z['branch_names'][i])==row['line'] and str(z['branch_phases'][i])==row['phase']
            assert str(z['node_names'][si])==row['sending_bus']+'.'+str('ABC'.index(row['phase'])+1)
            assert str(z['node_names'][ri])==row['receiving_bus']+'.'+str('ABC'.index(row['phase'])+1)
            for field,array,idx in [('sending_voltage_pu','voltage_pu',si),('receiving_voltage_pu','voltage_pu',ri),('rho','phase_current_loading_pu',i),('phase_current_A','phase_current_a',i)]:
                assert float(row[field])==float(z[array][t,idx]);checked_values+=1
            if row['policy']=='B0' and state=='preQ':
                indices=np.flatnonzero(z['branch_kinds']=='line');a=z['phase_current_loading_pu'][:,indices]
                tt,ii=np.unravel_index(a.argmax(),a.shape)
                assert t==tt and i==indices[ii] and float(ref['B0_rho'])==a.max()
        vs=float(row['sending_voltage_pu']);vr=float(row['receiving_voltage_pu']);rho=float(row['rho']);b=by_key[row['date'],'B0']
        formulas={'signed_voltage_change_pu':vs-vr,'abs_line_voltage_difference_pu':abs(vs-vr),'sending_voltage_deviation_abs_pu':abs(vs-1),'receiving_voltage_deviation_abs_pu':abs(vr-1),'rho_change_vs_B0':rho-float(b['rho']),'rho_reduction_pct_vs_B0':(float(b['rho'])-rho)/float(b['rho'])*100,'abs_line_voltage_difference_change_vs_B0':abs(vs-vr)-float(b['abs_line_voltage_difference_pu']),'receiving_voltage_deviation_change_vs_B0':abs(vr-1)-float(b['receiving_voltage_deviation_abs_pu'])}
        assert all(float(row[k])==v and math.isfinite(v) for k,v in formulas.items());checked_values+=len(formulas)
        assert abs(float(row['phase_current_A'])/float(row['line_rating_A'])-rho)<1e-12
    observations[state]=rows
    reduction_days[state]={p:sum(float(x['rho_reduction_pct_vs_B0'])>0 for x in rows if x['policy']==p) for p in ['B0','B1','B2','B3']}
aggregates=load('03_policy_aggregate_at_B0_critical_points_preQ.csv')
for a in aggregates:
    rows=[r for r in observations['preQ'] if r['policy']==a['policy']]
    for k,f in [('rho','mean_rho'),('abs_line_voltage_difference_pu','mean_abs_line_voltage_difference_pu'),('receiving_voltage_deviation_abs_pu','mean_receiving_voltage_deviation_abs_pu'),('rho_reduction_pct_vs_B0','mean_rho_reduction_pct_vs_B0')]:
        assert float(a[f])==statistics.mean(float(r[k]) for r in rows)
    assert float(a['SD_rho'])==statistics.stdev(float(r['rho']) for r in rows)
    for metric in ['abs_line_voltage_difference','receiving_voltage_deviation']:
        changes=[float(r[metric+'_change_vs_B0']) for r in rows]
        assert float(a['mean_'+metric+'_change_vs_B0'])==statistics.mean(changes)
        assert float(a['median_'+metric+'_change_vs_B0'])==statistics.median(changes)
        for label,n in [('improved',sum(v< -1e-12 for v in changes)),('unchanged',sum(abs(v)<=1e-12 for v in changes)),('worsened',sum(v>1e-12 for v in changes))]:assert int(a[metric+'_'+label+'_days'])==n
paired=load('04_daily_paired_changes_preQ.csv');assert len(paired)==31
for w in paired:
    for p in ['B1','B2','B3']:
        r=next(x for x in observations['preQ'] if x['date']==w['date'] and x['policy']==p)
        for k,v in w.items():
            if k.startswith(p+'_'):assert float(v)==float(r[k[3:]])
for path,metadata in manifest['source_files'].items():
    if path.endswith('.tar.gz'):assert Path(path).stat().st_size==metadata['bytes']
    else:assert sha(path)==metadata['sha256']
details=json.loads((ROOT/'VALIDATION_DETAILS.json').read_text(encoding='utf-8'))
assert details['status']=='PASS' and not details['errors'] and all(c['status']=='PASS' for c in details['checks'])
assert len(details['own_daily_maxima_separate_metric'])==248
b0=aggregates[0];b3=aggregates[3]
receipt={'status':'PASS','checked_saved_row_raw_values_and_formulas':checked_values,'row_counts':counts,'primary_validation_check_count':len(details['checks']),'primary_failed_checks':0,'line_loading_reduced_days':reduction_days,'B3_preQ_abs_voltage_difference_reduction_ratio_of_means_pct':(float(b0['mean_abs_line_voltage_difference_pu'])-float(b3['mean_abs_line_voltage_difference_pu']))/float(b0['mean_abs_line_voltage_difference_pu'])*100,'B3_preQ_receiving_deviation_increase_ratio_of_means_pct':(float(b3['mean_receiving_voltage_deviation_abs_pu'])-float(b0['mean_receiving_voltage_deviation_abs_pu']))/float(b0['mean_receiving_voltage_deviation_abs_pu'])*100,'scientific_rerun_count':0}
(ROOT/'INDEPENDENT_VERIFICATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
manifest['scripts_used'][Path(__file__).name]=sha(Path(__file__))
manifest['selected_evidence_totals']={'selected_member_count':len(index),'selected_member_bytes':sum(x['bytes'] for x in index.values()),'unique_cached_file_count':len(set(x['local'] for x in index.values()))}
manifest['topology_missing_file_resolution']={'date':'2025-05-31','policy':'B2','missing':'Own DA BRANCH_PHASE_CURRENTS.parquet','resolution':'Same-day B0 archived topology after exact electrical certificate and base-data hash identity, full final array-axis agreement and recorded current/rating consistency checks','voltage_reconstructed':False}
manifest['independent_verification']=receipt
manifest['support_file_sha256']={n:sha(ROOT/n) for n in ['README.md','VALIDATION_REPORT.md','VALIDATION_DETAILS.json','INDEPENDENT_VERIFICATION.json','selected_raw_index.json','archive_member_inventory.jsonl']}
(ROOT/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(receipt,indent=2))
