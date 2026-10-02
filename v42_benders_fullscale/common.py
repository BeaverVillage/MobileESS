from pathlib import Path
import csv,hashlib,json,os,subprocess,time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_mess_benders_v2_fullscale_loop'
BASE='4cee7ad048d43db6a0049eebecdd44d59f3cc567'
PRIOR=Path('C:/Users/kjw39/Documents/Codex/2026-10-02/mess-benders-v2-native-recourse/worktree')
T=.5732125039436496
UB=.5912812634331275
LB=.5722125039436496

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def dump(name,value,directory=OUT):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);p=directory/name;tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w',encoding='utf8',newline='\n') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def read(name,directory=OUT):return json.loads((Path(directory)/name).read_text(encoding='utf8'))
def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def table(name,rows,fields,directory=OUT):
    with (Path(directory)/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def verify_inherited():
    r=read('PR116_BASE_RECEIPT.json')
    if any(sha(ROOT/x['path'])!=x['sha256'] for x in r['files']):raise ValueError('INHERITED_BYTES_CHANGED')
    return True

def require_scope():
    r=read('SCOPE_CORRECTION_ADDENDUM.json');checkpoint=read('SCOPE_CHECKPOINT.json')
    if not r['user_authorized_new_candidate'] or sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json')!=checkpoint['addendum_sha256']:raise ValueError('SCOPE_NOT_FROZEN')
    raw=subprocess.check_output(['git','show',checkpoint['commit']+':docs/v42_mess_benders_v2_fullscale_loop/SCOPE_CORRECTION_ADDENDUM.json'],cwd=ROOT)
    if hashlib.sha256(raw).hexdigest()!=checkpoint['addendum_sha256']:raise ValueError('SCOPE_NOT_COMMITTED')
    verify_inherited();return checkpoint
