import csv,difflib,hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;OLD=BASE/'selection_v2'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def save(name,rows):
    (ROOT/(name+'.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
    if isinstance(rows,list) and rows:
        with (ROOT/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

features=read(BASE/'audit/candidate_pool_static_features.json')
dist=np.array([r['primary_upstream_impedance_ohm'] for r in features]);cut=float(np.quantile(dist,.05,method='linear'))
assert len(features)==638
rows=[{**r,'root_distance_q05_ohm':cut,'source_proximity_excluded':r['primary_upstream_impedance_ohm']<cut} for r in features]
save('CANDIDATE_ROOT_DISTANCE_DISTRIBUTION',sorted(rows,key=lambda r:(r['primary_upstream_impedance_ohm'],r['bus'])))
save('ROOT_DISTANCE_EXCLUDED_CANDIDATES',[r for r in rows if r['source_proximity_excluded']])
save('GUARDED_CANDIDATE_POOL',[r for r in rows if not r['source_proximity_excluded']])
summary={'original_count':638,'excluded_count':sum(r['source_proximity_excluded'] for r in rows),'remaining_count':sum(not r['source_proximity_excluded'] for r in rows),'quantile_method':'linear','quantile_fraction':.05,'zero_based_interpolation_position':31.85,'sorted_value_index31':float(np.sort(dist)[31]),'sorted_value_index32':float(np.sort(dist)[32]),'root_distance_q05_ohm':cut,'rule':'exclude strictly below original 638-candidate q05; keep equality','mean_ohm':float(dist.mean()),'population_std_ohm':float(dist.std()),'percentiles_ohm':{str(p):float(np.quantile(dist,p/100,method='linear')) for p in [0,1,5,10,25,50,75,90,95,99,100]},'original_pair_thresholds_unchanged':True}
save('ROOT_DISTANCE_GUARD_AUDIT',summary)
original=(OLD/'select_sites.py').read_text(encoding='utf-8')
marker='    dmx=float(D.max());gmx=float(G.max())\n'
extra='''    # Additional outcome-blind hard guard; retain original objective normalizers.
    rootdist=np.array([f['primary_upstream_impedance_ohm'] for f in features])
    cutoff=float(np.quantile(rootdist,.05,method='linear'))
    guard=read(ROOT/'ROOT_DISTANCE_GUARD_AUDIT.json')
    assert cutoff==guard['root_distance_q05_ohm']
    keep=np.flatnonzero(rootdist>=cutoff)
    ids=ids[keep];xy=xy[keep];groups=groups[keep]
    D=D[np.ix_(keep,keep)];R=R[np.ix_(keep,keep)];G=G[np.ix_(keep,keep)]
    assert len(ids)==guard['remaining_count'] and len(ids)==606
'''
assert original.count(marker)==1
modified=original.replace(marker,marker+extra).replace('np.arange(638)','np.arange(len(ids))')
(ROOT/'select_sites.py').write_text(modified,encoding='utf-8')
(ROOT/'SELECTOR_V2_TO_GUARDED.diff').write_text(''.join(difflib.unified_diff(original.splitlines(keepends=True),modified.splitlines(keepends=True),fromfile='immutable_selection_v2/select_sites.py',tofile='selection_v3_source_proximity/select_sites.py')),encoding='utf-8')
inputs=['audit/candidate_pool_static_features.json','audit/candidate_pair_metrics.npz','audit/melbourne_12_anchors.json','audit/melbourne_66_pair_geometry.json','audit/primary_corridors.json','audit/methodology_inputs.json','audit/buses.json']
oldfreeze={r['path']:r['sha256'] for r in read(BASE/'FREEZE_MANIFEST.json')['files']}
assert all(sha(BASE/p)==oldfreeze[p] for p in inputs)
freeze={'freeze_id':'IEEE8500_SOURCE_PROXIMITY_GUARD_PRE_EXECUTION','original_freeze_sha256':sha(BASE/'FREEZE_MANIFEST.json'),'selection_v2_freeze_sha256':sha(OLD/'SELECTION_FREEZE_MANIFEST.json'),'original_v2_selector_sha256':sha(OLD/'select_sites.py'),'files':[{'path':p,'sha256':sha(ROOT/p)} for p in ['AGENTS.md','ROOT_DISTANCE_GUARD_ADDENDUM.md','prepare_guard.py','select_sites.py','SELECTOR_V2_TO_GUARDED.diff','ROOT_DISTANCE_GUARD_AUDIT.json','GUARDED_CANDIDATE_POOL.json']],'inputs':[{'path':p,'sha256':sha(BASE/p)} for p in inputs]}
assert not (ROOT/'PROCEDURE_FREEZE_MANIFEST.json').exists()
save('PROCEDURE_FREEZE_MANIFEST',freeze)
print(json.dumps(summary,indent=2));print('Procedure frozen',sha(ROOT/'PROCEDURE_FREEZE_MANIFEST.json'))
