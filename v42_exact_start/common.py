from pathlib import Path
import csv,json,os
import numpy as np
from v42_monolithic.common import ROOT,UB,LB,original,sha,stamp,git
from v42_monolithic.prepare import SETTINGS
from v42_monolithic.experiment import load_compact,attr,clean_number

BASE='c7d808a315e04aefc1bcfc537b84cc38d895a9ab'
OUT=ROOT/'docs/v42_m1_compact_exact_start'
LOCAL=ROOT.parent/'EXACT_START_LOCAL'
PR124=ROOT/'docs/v42_m1_compact_monolithic'
OLD_CACHE=ROOT.parent/'COMPACT_MONOLITHIC_LOCAL'
PRIMARY={'arc','SOC','charge_mode','Pch','Pdis','Q','rho_max','movement_flow','node_activity'}
AUX={'injection_P','injection_Q','response_line_P','response_line_Q','response_line_correction','response_transformer_P','response_transformer_Q'}

def read(name,directory=OUT):return json.loads((Path(directory)/name).read_text(encoding='utf8'))
def dump(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def table(name,rows,fields):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def family(name):return str(name).split('[')[0]
def primary_mask(names):
    families={family(n) for n in names};assert families<=PRIMARY|AUX,('UNKNOWN_VARIABLE_FAMILY',families-(PRIMARY|AUX))
    return np.array([family(n) in PRIMARY for n in names])
def preserve():
    receipt=read('PR124_BASE_RECEIPT.json')
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in receipt['files'])
    return len(receipt['files'])
def old_start(kind):
    with np.load(OLD_CACHE/'AXIS_START.npz') as z:return z[kind+'_names'],z[kind+'_values']
def start(kind):
    with np.load(LOCAL/(kind.upper()+'_RECONSTRUCTED_START.npz')) as z:return z['names'],z['values']
def model(kind,env):return original(env) if kind=='original' else load_compact(env)
def solver_freeze_check():
    assert read('PREREGISTRATION.json')['solver']==SETTINGS
    f=read('SOURCE_FREEZE.json');assert all(sha(ROOT/n)==s for n,s in f['sources'].items())
    assert sha(OUT/'PREREGISTRATION.json')==f['preregistration_sha256']
    assert all(sha(Path(n))==s for n,s in f['immutable_cache_inputs'].items())
    preserve()
def freeze():
    from v42_monolithic.experiment import check_freeze
    check_freeze();preserve()
    sources={p.relative_to(ROOT).as_posix():sha(p) for folder in ['v42_exact_start','v42_monolithic','v42_m1_sparse','v42_native','v42_bootstrap'] for p in sorted((ROOT/folder).glob('*.py'))}
    cache=[ROOT.parent/'THRESHOLD_LOCAL/F3.mps']+[OLD_CACHE/n for n in ['COMPACT_A.npz','COMPACT_DATA.npz','AXIS_START.npz','INVERSE_T.npz','FORWARD_F.npz']]
    dump('SOURCE_FREEZE.json',dict(utc=stamp(),code_commit=git('rev-parse','HEAD'),sources=sources,
        immutable_cache_inputs={str(p):sha(p) for p in cache},preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        solver=SETTINGS,no_optimizer_run_before_freeze=True))
