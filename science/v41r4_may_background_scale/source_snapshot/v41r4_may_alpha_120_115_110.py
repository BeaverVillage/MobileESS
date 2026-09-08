"""Three explicitly authorized B0 candidates using the unchanged V41R4 replay.

Prior screen inputs are copied byte-for-byte into a new evidence namespace.
Only alpha and output paths are rebound, independently in every spawn worker.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import importlib.abc
import shutil, sys, time, json
import numpy as np
import pandas as pd
import v41r4_may_alpha_screen as base

ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT/'dayahead/artifacts/v41r4_may_alpha_screen'
OUT=ROOT/'dayahead/artifacts/v41r4_may_alpha_120_115_110'
ALPHAS=(1.20,1.15,1.10)
DELIVERY=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/artifacts/v41r4_may_alpha_120_115_110')
RULE='Select the first all-31-day Day-Ahead B0 eligible candidate in priority 1.20, 1.15, 1.10; otherwise FAIL_CLOSE.'
read,rec,save,atomic,arrays=base.read,base.rec,base.save,base.atomic,base.arrays

class NoGurobi(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='gurobipy' or fullname.startswith('gurobipy.'):
            raise RuntimeError('GUROBI_FORBIDDEN_IN_REQUESTED_ALPHA_PHYSICAL_SCREEN')
        return None

def configure():
    base.OUT=OUT;base.ALPHAS=ALPHAS

def copy_checked(p,q):
    q.parent.mkdir(parents=True,exist_ok=True);assert not q.exists()
    shutil.copyfile(p,q)
    a,b=rec(p),rec(q);assert a['sha256']==b['sha256']
    return dict(source=a,local=b)

def prepare():
    assert not OUT.exists(),'PRESERVE_EXISTING_EXTENSION_EVIDENCE'
    protocol=read(PREVIOUS/'PREDECLARED_PROTOCOL.json')
    assert rec(ROOT/'v41r4_may_alpha_screen.py')==protocol['runner']
    assert read(PREVIOUS/'V41R4_VERIFICATION.json')['status']=='PASS'
    protection=read(PREVIOUS/'PROTECTED_INPUTS_AND_SOURCES.json')
    for r in protection['records']:assert rec(r['path'])==r,('PRIOR_PROTECTED_SOURCE_DRIFT',r['path'])
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    assert FeederAssets.from_repo(SOURCE_DATA_REPOSITORY).sha256==read(PREVIOUS/'TOPOLOGY_AND_CONTROLS.json')['source_assets']
    # Hash prior evidence without using any historical results for selection.
    prior_roots=(PREVIOUS,ROOT/'dayahead/artifacts/v41r4_may_alpha_130_125')
    prior=[rec(p) for old in prior_roots for p in sorted(old.rglob('*')) if p.is_file()]
    OUT.mkdir(parents=True)
    save(OUT/'PREDECLARED_PROTOCOL.json',dict(schema='V41R4_THREE_ADDITIONAL_ALPHAS_PROTOCOL_V1',
        candidate_alphas=list(ALPHAS),days=list(base.DAYS),selection_rule=RULE,
        hard_limits=protocol['hard_limits'],worker_count=4,engine='One new isolated OpenDSS context per trajectory in spawn processes',
        B1_B2_B3_RESULTS_USED=False,Actual_results_used_for_selection=False,
        MESS_OFF=True,Gurobi_forbidden=True,coefficient_regeneration_calls=0,policy_optimization_calls=0,
        prior_alphas_replayed=False,runner=rec(__file__),unchanged_replay_source=protocol['runner'],
        created_UTC=pd.Timestamp.now(tz='UTC').isoformat(),Full_May_policy_optimization='HOLD'))
    copies=[]
    for name in ('NODE_AXIS.npz','TOPOLOGY_AND_CONTROLS.json','PROTECTED_INPUTS_AND_SOURCES.json'):
        copies.append(copy_checked(PREVIOUS/name,OUT/name))
    for item in protection['daily']:
        day=item['day'];folder=PREVIOUS/'inputs'/day
        for key,name in [('background','DAYAHEAD_BACKGROUND.npz'),('power','DAYAHEAD_POWER.npz')]:
            assert rec(folder/name)==item[key]
            copies.append(copy_checked(folder/name,OUT/'inputs'/day/name))
        assert read(folder/'DAYAHEAD_INPUT_RECEIPT.json')==item
        copies.append(copy_checked(folder/'DAYAHEAD_INPUT_RECEIPT.json',OUT/'inputs'/day/'DAYAHEAD_INPUT_RECEIPT.json'))
    save(OUT/'REUSE_AND_PRESERVATION_MANIFEST.json',dict(status='PASS',prior_screen_files=prior,input_copies=copies,
        prior_source_files_verified=len(protection['records']),B0_780GPU_bit_exact=True,background_P_Q_original_bit_exact=True,
        PV_bit_exact=True,new_reference_construction_calls=0,new_ML_calls=0,prior_validation=rec(PREVIOUS/'V41R4_VERIFICATION.json')))
    print('PREPARED',len(base.DAYS),'days; unchanged validated replay; candidates',ALPHAS,flush=True)

def worker(task):
    configure();day,alpha,stage=task
    assert alpha in ALPHAS and stage=='DAYAHEAD'
    guard=NoGurobi();sys.meta_path.insert(0,guard)
    try:
        assert 'gurobipy' not in sys.modules
        result=base.replay(task)
        assert 'gurobipy' not in sys.modules
        return result
    finally:sys.meta_path.remove(guard)

def run():
    configure();started=time.perf_counter();rows=[]
    tasks=[(d,a,'DAYAHEAD') for d in base.DAYS for a in ALPHAS]
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:
        futures={pool.submit(worker,t):t for t in tasks}
        for future in as_completed(futures):
            try:r=future.result()
            except BaseException as e:
                atomic(OUT/'SCREEN_ERROR.json',dict(task=futures[future],error=repr(e)));raise
            rows.append(r)
            atomic(OUT/'DAYAHEAD_PROGRESS.json',dict(completed=len(rows),total=93,elapsed_seconds=time.perf_counter()-started,
                last=dict(day=r['day'],alpha_BG=r['alpha_BG'],PASS=r['PASS'])))
            print('DAYAHEAD',len(rows),'/ 93',r['day'],r['alpha_BG'],'PASS' if r['PASS'] else 'FAIL',
                'rho',round(r['rho_max'],6),'Vmax',round(r['Vmax'],9),'txI',round(r['transformer_current'],6),flush=True)
    rows=sorted(rows,key=lambda r:(-r['alpha_BG'],r['day']))
    save(OUT/'DAYAHEAD_ROWS.json',rows)
    return rows

def verify(rows):
    configure();assert len(rows)==93 and {(r['day'],r['alpha_BG']) for r in rows}=={(d,a) for d in base.DAYS for a in ALPHAS}
    checked=[];count=0
    for r in rows:
        assert rec(r['arrays']['path'])==r['arrays'];z=arrays(r['arrays']['path'])
        line=z['branch_kinds']=='line';tx=~line;v=z['voltage_pu'];c=z['phase_current_loading_pu'];k=z['transformer_total_kva_loading_pu']
        assert z['convergence'].shape==(96,) and z['convergence'].all();count+=int(z['convergence'].sum())
        unique=list(dict.fromkeys(z['branch_names'][tx]));ix=[z['branch_names'].tolist().index(n) for n in unique]
        for name in unique:
            cols=np.flatnonzero(z['branch_names']==name);assert all(np.array_equal(k[:,cols[0]],k[:,j]) for j in cols)
        values=dict(Vmin=float(v.min()),Vmax=float(v.max()),rho_max=float(c[:,line].max()),transformer_current=float(c[:,tx].max()),
            transformer_kVA=float(k[:,tx].max()),p95_line_loading=float(np.percentile(c[:,line],95)),p99_line_loading=float(np.percentile(c[:,line],99)))
        assert all(r[key]==value for key,value in values.items())
        counts=dict(voltage=int(((v<.95)|(v>1.05)).sum()),line_current=int((c[:,line]>=1).sum()),
            transformer_current=int((c[:,tx]>=1).sum()),transformer_kVA=int((k[:,ix]>=1).sum()))
        assert counts==r['violation_counts'] and r['PASS']==(not any(counts.values()))
        assert z['regulator_taps'].shape==(96,7) and z['capacitor_states'].shape==(96,4) and np.all(z['capacitor_states']==1)
        assert len(r['root_P_kW'])==len(r['root_Q_kvar'])==96
        checked.append(dict(day=r['day'],alpha_BG=r['alpha_BG'],arrays=r['arrays'],strict_summary=rec(Path(r['arrays']['path']).parents[1]/'STRICT_SUMMARY.json')))
    assert count==8928
    protocol=read(OUT/'PREDECLARED_PROTOCOL.json')
    assert rec(__file__)==protocol['runner'] and rec(ROOT/'v41r4_may_alpha_screen.py')==protocol['unchanged_replay_source']
    reuse=read(OUT/'REUSE_AND_PRESERVATION_MANIFEST.json')
    for r in reuse['prior_screen_files']:assert rec(r['path'])==r,('PRIOR_SCREEN_EVIDENCE_CHANGED',r['path'])
    protection=read(OUT/'PROTECTED_INPUTS_AND_SOURCES.json')
    for r in protection['records']:assert rec(r['path'])==r
    for item in reuse['input_copies']:assert rec(item['source']['path'])==item['source'] and rec(item['local']['path'])==item['local']
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    assert FeederAssets.from_repo(SOURCE_DATA_REPOSITORY).sha256==read(OUT/'TOPOLOGY_AND_CONTROLS.json')['source_assets']
    result=dict(status='PASS',trajectories=93,converged_slots=count,all_trajectories_96_of_96=True,
        prior_screen_files_unchanged=len(reuse['prior_screen_files']),protected_sources_unchanged=len(protection['records']),
        byte_exact_input_copies=len(reuse['input_copies']),arrays=checked,strict_no_tolerance_readback=True,
        native_settings_checked_each_slot=True,fixed_capacitors_unchanged=True,Gurobi_module_never_loaded=True,
        prior_validated_numerical_code_unchanged=True,additional_verification_solves=0)
    save(OUT/'V41R4_VERIFICATION.json',result)
    return result

def finalize(rows,verified):
    configure();groups=base.aggregate(rows)
    for group in groups:
        rr=[r for r in rows if r['alpha_BG']==group['alpha_BG']]
        group['stress_distribution']['mean']=float(np.mean([r['rho_max'] for r in rr]))
        group['worst_metric_locations']={name:dict(day=(min(rr,key=lambda r:r[name]) if name=='Vmin' else max(rr,key=lambda r:r[name]))['day'],
            **(min(rr,key=lambda r:r[name]) if name=='Vmin' else max(rr,key=lambda r:r[name]))['worsts'][key])
            for name,key in [('rho_max','line'),('Vmin','voltage_low'),('Vmax','voltage_high'),('transformer_current','transformer_current'),('transformer_kVA','transformer_kVA')]}
    selected=next((a for a in ALPHAS if next(g for g in groups if g['alpha_BG']==a)['eligible']),None)
    status='FROZEN_DAYAHEAD_MAY_WIDE_ELIGIBLE' if selected is not None else 'FAIL_CLOSE_NO_MAY_WIDE_ELIGIBLE_ALPHA'
    authority=dict(schema='V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY_V3_THREE_ADDITIONAL_CANDIDATES',status=status,
        candidate_alphas=list(ALPHAS),selected_alpha_BG=selected,selection_rule=RULE,eligibility_results=groups,
        all_day_alpha_results=rows,source_SHAs=rec(OUT/'PROTECTED_INPUTS_AND_SOURCES.json'),
        reuse_and_preservation_manifest=rec(OUT/'REUSE_AND_PRESERVATION_MANIFEST.json'),predeclared_protocol=rec(OUT/'PREDECLARED_PROTOCOL.json'),
        verification=rec(OUT/'V41R4_VERIFICATION.json'),AIDC_authority=read(OUT/'PROTECTED_INPUTS_AND_SOURCES.json')['AIDC_authority'],
        AIDC_vector=list(base.VECTOR),AIDC_total_GPU=780,AIDC_power_unchanged=True,ML_unchanged=True,MESS_OFF=True,
        B1_B2_B3_RESULTS_USED=False,Actual_results_used_for_selection=False,Actual_replays=0,
        Gurobi_calls=0,coefficient_regeneration_calls=0,ROBUST_B1_executed=False,Full_May_policy_optimization='HOLD',
        previous_evidence_preserved=True,prior_screen_authority=rec(PREVIOUS/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json'),
        downstream_execution_allowed=False,frozen_UTC=pd.Timestamp.now(tz='UTC').isoformat())
    save(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json',authority)
    daily=[dict(day=d,**{f'alpha_{a:.2f}':next(r['rho_max'] for r in rows if r['day']==d and r['alpha_BG']==a) for a in ALPHAS}) for d in base.DAYS]
    report=dict(schema='V41R4_MAY_ALPHA_SCREEN_THREE_ADDITIONAL_CANDIDATES_V1',status=status,candidate_alphas=list(ALPHAS),
        selected_alpha_BG=selected,groups=groups,all_day_alpha_results=rows,daily_rho_max=daily,
        mean_definition='Arithmetic mean of the 31 daily maximum line-phase loadings',verification=verified,
        selection_authority=rec(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json'),selection_rule=RULE,
        Actual_used=False,B1_B2_B3_RESULTS_USED=False,previous_evidence_preserved=True)
    save(OUT/'V41R4_MAY_ALPHA_SCREEN.json',report)
    lines=['# V41R4 May-wide B0 screen: alpha 1.20, 1.15 and 1.10','',f'**{status}; selected alpha_BG = {selected if selected is not None else "NONE"}.**',
        'All 31 dates from 2025-05-01 through 2025-05-31 evaluated at exactly the three new candidates. The previous validated replay function and prepared 780-GPU B0 inputs are unchanged.',
        f'93 isolated clean-engine trajectories, all 96/96 converged: 8,928 slots. Physical replay wall time: {read(OUT/"DAYAHEAD_PROGRESS.json")["elapsed_seconds"]:.1f} seconds.','',
        '| alpha | May-wide | PASS / FAIL days | worst rho | worst Vmin | worst Vmax | worst transformer current | worst transformer kVA |',
        '|---:|:---:|:---:|---:|---:|---:|---:|---:|']
    for g in groups:lines.append(f'| {g["alpha_BG"]:.2f} | {"PASS" if g["eligible"] else "FAIL"} | {g["PASS_days"]} / {g["FAIL_days"]} | {g["rho_max"]:.9f} | {g["Vmin"]:.9f} | {g["Vmax"]:.9f} | {g["transformer_current"]:.9f} | {g["transformer_kVA"]:.9f} |')
    lines+=['','Voltage is pu; loadings are fractions of unchanged nameplate ratings. No tolerance: voltage inclusive [0.95,1.05]; all thermal loadings strictly below 1.0.','',
        '| alpha | first failing day | constraint | asset / phase | slot (0-based) | value |','|---:|:---:|---|---|---:|---:|']
    for g in groups:
        for w in g['first_failing_constraints']:lines.append(f'| {g["alpha_BG"]:.2f} | {g["first_failing_day"]} | {w["kind"]} | {w["asset"]} / {w["phase"]} | {w["slot"]} | {w["value"]:.12f} |')
        if not g['first_failing_constraints']:lines.append(f'| {g["alpha_BG"]:.2f} | NONE | NONE | — | — | — |')
    lines+=['','## Distribution of 31 daily rho maxima','',
        '| alpha | min | mean | median | P75 | P90 | max |','|---:|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        d=g['stress_distribution'];lines.append('| '+f'{g["alpha_BG"]:.2f}'+' | '+' | '.join(f'{d[k]:.9f}' for k in ('min','mean','median','P75','P90','max'))+' |')
    lines+=['','The mean is the arithmetic mean of 31 daily maxima, not the mean of all line/phase/slot samples. These statistics do not override the predeclared selection rule.','',
        '| Date | alpha 1.20 | alpha 1.15 | alpha 1.10 |','|:---|---:|---:|---:|']
    for d in daily:lines.append("| "+d["day"]+" | "+" | ".join(f'{d[f"alpha_{a:.2f}"]:.9f}' for a in ALPHAS)+" |")
    lines+=['','## Authority and verification','',RULE,'',
        '- Native/background P and Q scaled only; original spatial/phase/time shape and PF retained.',
        '- PV, AIDC, MESS, ratings, impedances, topology, source voltage and native Day-Ahead regulator settings unchanged. MESS OFF.',
        '- No B1/B2/B3, Actual replay, Gurobi or electrical coefficient regeneration.',
        '- All per-day source/input records, strict counts, worst asset/phase/slot and full voltage/current/kVA/tap/capacitor trajectories are persisted.',
        f'- Re-read all 93 trajectory arrays; verified exact strict gates. {verified["prior_screen_files_unchanged"]} previous screen files and {verified["protected_sources_unchanged"]} protected input/source files retain their SHA-256 hashes.',
        '- Existing screen reports and authorities are preserved in their original directories.',
        '- Full May policy optimization remains HOLD. No unrequested alpha is evaluated.','']
    (OUT/'V41R4_MAY_ALPHA_SCREEN.md').write_text('\n'.join(lines),encoding='utf-8')
    assert not DELIVERY.exists(),'PRESERVE_EXISTING_DELIVERY'
    DELIVERY.mkdir(parents=True);delivered=[]
    for name in ('V41R4_MAY_ALPHA_SCREEN.json','V41R4_MAY_ALPHA_SCREEN.md','V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json','V41R4_VERIFICATION.json'):
        delivered.append(copy_checked(OUT/name,DELIVERY/name))
    save(OUT/'DELIVERY_MANIFEST.json',dict(status='PASS',files=delivered))
    print('COMPLETE',status,'selected',selected,flush=True)
    print(json.dumps([{k:v for k,v in g.items() if k!='May02'} for g in groups],indent=2),flush=True)

if __name__=='__main__':
    prepare();values=run();proof=verify(values);finalize(values,proof)
