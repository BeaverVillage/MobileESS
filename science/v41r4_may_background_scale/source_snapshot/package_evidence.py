"""Package existing screen evidence only; never run a model or simulator."""
from pathlib import Path
import gzip, hashlib, json, shutil
import numpy as np

SOURCE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
TARGET=Path('D:/ChatGPT/Mobile ESS 2/v41r4_alpha_screen_pr/science/v41r4_may_background_scale')
ROUNDS=[('round1', 'v41r4_may_alpha_screen', [1.35,1.4,1.45,1.5]),
        ('round2', 'v41r4_may_alpha_130_125', [1.3,1.25]),
        ('round3', 'v41r4_may_alpha_120_115_110', [1.2,1.15,1.1])]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def main():
    assert not (TARGET/'BUNDLE_MANIFEST.json').exists()
    projections=[];ledger=[];round_refs=[];copies=[]
    names=['V41R4_MAY_ALPHA_SCREEN.json','V41R4_MAY_ALPHA_SCREEN.md','V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json',
           'V41R4_VERIFICATION.json','PREDECLARED_PROTOCOL.json','PROTECTED_INPUTS_AND_SOURCES.json','TOPOLOGY_AND_CONTROLS.json']
    for label,folder,alphas in ROUNDS:
        src=SOURCE/'dayahead/artifacts'/folder
        report=read(src/'V41R4_MAY_ALPHA_SCREEN.json');assert report['candidate_alphas']==alphas
        authority=read(src/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json')
        assert read(src/'V41R4_VERIFICATION.json')['status']=='PASS'
        protocol=read(src/'PREDECLARED_PROTOCOL.json');assert sha(protocol['runner']['path'])==protocol['runner']['sha256']
        for name in names:
            p=src/name;q=TARGET/'rounds'/label/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
            assert sha(q)==sha(p);copies.append(dict(archive=q.relative_to(TARGET).as_posix(),original=str(p),sha256=sha(p)))
        round_refs.append(dict(round=label,candidate_alphas=alphas,selected_alpha_BG=authority['selected_alpha_BG'],report=f'rounds/{label}/V41R4_MAY_ALPHA_SCREEN.json'))
        for row in report['all_day_alpha_results']:
            p=Path(row['arrays']['path']);assert sha(p)==row['arrays']['sha256']
            with np.load(p) as z:
                line=z['branch_kinds']=='line';tx=~line
                columns=[z['convergence'].astype(int),z['voltage_pu'].min(axis=1),z['voltage_pu'].max(axis=1),
                    z['phase_current_loading_pu'][:,line].max(axis=1),z['phase_current_loading_pu'][:,tx].max(axis=1),
                    z['transformer_total_kva_loading_pu'][:,tx].max(axis=1)]
                slots=np.column_stack(columns);assert slots.shape==(96,6) and np.isfinite(slots).all()
                expected=dict(Vmin=float(slots[:,1].min()),Vmax=float(slots[:,2].max()),rho_max=float(slots[:,3].max()),
                    transformer_current=float(slots[:,4].max()),transformer_kVA=float(slots[:,5].max()))
                assert all(row[k]==v for k,v in expected.items())
                projections.append(dict(round=label,day=row['day'],alpha_BG=row['alpha_BG'],source_array_sha256=sha(p),
                    slots=slots.tolist(),regulator_taps=z['regulator_taps'].tolist(),capacitor_states=z['capacitor_states'].tolist()))
            keys=['day','alpha_BG','PASS','convergence_count','Vmin','Vmax','rho_max','transformer_current','transformer_kVA','p95_line_loading','p99_line_loading','worsts','limiting_constraints','violation_counts']
            ledger.append(dict(round=label,**{k:row[k] for k in keys},source_array_sha256=row['arrays']['sha256']))
    assert len(ledger)==279
    write(TARGET/'DAILY_RESULTS.json',ledger)
    projection=dict(schema='V41R4_EXACT_SLOT_EXTREMA_V1',columns=['convergence','Vmin','Vmax','rho_max','transformer_current','transformer_kVA'],
        extraction='Exact reductions of persisted clean-engine arrays; no rounding, no new OpenDSS solves. Full original array SHA retained per trajectory.',
        trajectories=projections)
    (TARGET/'SLOT_EXTREMA.json.gz').write_bytes(gzip.compress(json.dumps(projection,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    source_names=['v41r4_may_alpha_screen.py','v41r4_may_alpha_130_125.py','v41r4_may_alpha_120_115_110.py','v41r4_verify_and_report.py','v41r4_daily_rho_report.py',
        'native_forensic.py','screen.py','dayahead/v28r2/opendss_backend.py','dayahead/v28r2/opendss_mapping.py','dayahead/v28r2/opendss_results.py','dayahead/v28r2/trajectory.py',
        'dayahead/v40e/mapping.py','dayahead/grid_background_v16_2.py','dayahead/full_ieee123_g11_v16_1.py','dayahead/run_v16_3_voltage_candidate.py']
    for name in source_names:
        p=SOURCE/name;q=TARGET/'source_snapshot'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
        copies.append(dict(archive=q.relative_to(TARGET).as_posix(),original=str(p),sha256=sha(p)))
    write(TARGET/'BUNDLE_MANIFEST.json',dict(schema='V41R4_REVIEW_BUNDLE_V1',selected_alpha_BG=1.15,rounds=round_refs,
        tested_alphas=sorted({r['alpha_BG'] for r in ledger},reverse=True),days=31,trajectories=279,slots=26784,
        files={p.relative_to(TARGET).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(TARGET.rglob('*')) if p.is_file()},
        original_copies=copies,full_raw_arrays='Remain in the original local evidence namespace; hashes are included. Committed exact slot extrema suffice to reproduce every eligibility gate.',
        source_snapshot='Historical source evidence from the original runtime, not a self-contained simulator installation.',
        packaging_source_sha256=sha(__file__),additional_simulator_calls=0,policy_results_used=False,Actual_used=False))
    print('PACKAGED',len(ledger),'trajectories',sum(p.stat().st_size for p in TARGET.rglob('*') if p.is_file()),'bytes')

if __name__=='__main__':main()
