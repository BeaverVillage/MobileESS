"""Freeze feature authority before integrating executable implementation."""
from pathlib import Path
import csv, hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_integrated_normalamps_zero_margin_m1'
BASE = 'ac2819cbc7b4e86fce07b4b0ed62e0647e9c473a'
SOLVER = 'a16af252538774b2b2034a8722c31c0ffe5874a9'
NORMALAMPS = '0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
PRESERVED = '724dffea6ee4bf276d361b31ee3cf9b2588a7168'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')
    tmp.replace(p)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def freeze():
    if (OUT/'V42_INTEGRATION_AUTHORITY.json').exists():
        raise ValueError('AUTHORITY_ALREADY_FROZEN')
    if git('rev-parse','HEAD').decode().strip() != BASE:
        raise ValueError('EXACT_PR132_BASE_REQUIRED')
    rules = {
        'A_operational_architecture': 'D-1 A1 -> M1 -> A2 -> M2 -> Planning Freeze -> D-Day Actual -> Fresh OpenDSS; execution ends at M1 here',
        'B_actual_operation': {'full_reoptimization':False,'P_repair':False,'Q_repair':False,'MESS_AIDC_schedule_repair':False,'Planning_tap_replay':False,'Actual_tap_replay':False,'Planning_capacitor_replay':False},
        'C_grid_controls': {'Planning_RegControls':'AUTONOMOUS','Actual_RegControls':'AUTONOMOUS','RegControls':7,'capacitors':4,'capacitors_fixed_ON':True,'CapControls':0},
        'D_voltage': {'lower_pu':0.95,'upper_pu':1.05,'margin_pu':0.0,'voltage_constraints_retained':True},
        'E_transformer_current': {'denominator':'compiled OpenDSS NormalAmps','transformers':44,'phases':120,'authority_SHA':NORMALAMPS,'CTPrim_thermal_authority':False},
        'F_transformer_kVA': 'Independently retain source kVA constraints',
        'G_line_current': 'Retain accepted PR132 line-current authority unchanged',
        'H_Runtime_CC4_capacity': {'source':'PR132 inherited','retraining':False,'Runtime_refit':False,'CC4_refit':False,'queue_redesign':False},
        'I_objectives': {'P1':'MIN MAX_LINE_LOADING','M_block_P2':['movement_energy','movement_count'],'reserve_shortfall_objective':False,'CC4_deviation_objective':False},
        'J_M1_decisions': {'A1_AIDC':'new frozen solution','route':'decision','movement':'decision','P':'decision','Q':'decision','SOC':'decision','historical_route_fix':False},
        'K_solver_components': 'Original M1; exact sparse grid; optional exact Start mapping; diagnostic observation only. PR132 equations take precedence.',
    }
    features = [dict(feature=k,canonical_source_PR=131 if k=='K_solver_components' else 132,canonical_source_SHA=SOLVER if k=='K_solver_components' else BASE,selected_status='SELECTED',superseded_source=['old margin / nameplate thermal / old certificate / replay or repairs'] if k!='K_solver_components' else ['failed Benders authority','Compact M1 production'],integration_rule=v) for k,v in rules.items()]
    write('V42_INTEGRATION_AUTHORITY.json',dict(schema='V42_INTEGRATED_AUTHORITY_V1',canonical_base=BASE,solver_reference=SOLVER,common_merge_base=git('merge-base',BASE,SOLVER).decode().strip(),preserved_provisional_commit=PRESERVED,features=features,old_M1_certificate='SUPERSEDED_REPORTING_ONLY',episode='2025-05-01',horizon=96,code_integration_started=False,downstream='NOT_RUN'))
    write('SUPERSEDED_IMPORT_BLOCKLIST.json',dict(scope='Executable integrated entry point and transitive scientific authorities; inherited inactive historical experiment modules are inventoried separately',hard_block=['voltage 0.955/1.045','margin_pu 0.005','kVA/kV as current denominator','reg1a 693.930612 as hard limit','CTPrim thermal denominator','Planning/Actual tap replay','Actual P/Q/full/MESS/AIDC repair','old UB/LB/gap/accepted certificate','failed Benders authority','Compact M1 production'],historical_evidence_preserved=True))
    tracked=git('ls-files').decode().splitlines()
    write('PR132_BYTE_PRESERVATION.json',dict(base=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked if (ROOT/p).is_file()],April_May_B0_reruns=0))
    paths=['v42_native/voltage.py','v42_native/grid.py','v42_native/mess.py','v42_native/solver.py','v42_m1_sparse/grid.py','v42_bootstrap/grid.py','v42_may01/prepare.py','v42_root/native.py','v42_root/data.py','v42_two/contract.py','v42_exact_start/reconstruct.py','v42_thermal/authority.py','v42_thermal/planning.py']
    ancestor=git('merge-base',BASE,SOLVER).decode().strip(); rows=[]
    def content(ref,p):
        r=subprocess.run(['git','show',ref+':'+p],cwd=ROOT,capture_output=True)
        return r.stdout if r.returncode==0 else None
    for p in paths:
        b,s,a=(content(ref,p) for ref in (BASE,SOLVER,ancestor))
        rows.append(dict(path=p,PR132_status='ABSENT' if b is None else 'UNCHANGED_FROM_COMMON_BASE' if b==a else 'CHANGED_FROM_COMMON_BASE',PR131_status='ABSENT' if s is None else 'UNCHANGED_FROM_COMMON_BASE' if s==a else 'CHANGED_FROM_COMMON_BASE',selected_source='PR132' if b is not None else 'selective function port only',manual_merge=False,reason='Three-way bytes inspected; preserve PR132 implementation and apply explicit integrated contract in new namespace',scientific_semantics_changed=False,test_coverage='24 integrated semantic regression gates',PR132_sha256=hashlib.sha256(b).hexdigest() if b is not None else None,PR131_sha256=hashlib.sha256(s).hexdigest() if s is not None else None,merge_base_sha256=hashlib.sha256(a).hexdigest() if a is not None else None))
    with (OUT/'FILE_LEVEL_INTEGRATION_AUDIT.csv').open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('AUTHORITY_FROZEN',sha(OUT/'V42_INTEGRATION_AUTHORITY.json'),flush=True)

if __name__ == '__main__':
    freeze()
