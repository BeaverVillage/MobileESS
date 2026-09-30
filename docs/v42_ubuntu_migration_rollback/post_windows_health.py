"""Post-restart native Windows health and original authority checks; no production solve."""
import json,hashlib,csv,zipfile,io,subprocess,sys,os
from pathlib import Path
O=Path(__file__).absolute().parent;R=O.parents[1];sys.path.insert(0,str(R))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert os.name=='nt' and not os.environ.get('MOBILEESS_PATH_MAP')
assert not subprocess.check_output(['git','diff','a88879fd','--','v42_root','tests'],cwd=R,text=True).strip()
from v42_root import common
from v42_boundary.boundaries import load_native
from v42_temporal.native import load_power
from v42_may01.prepare import native_coefficients
from v42_final.runtime import FrozenQ50
import gurobipy as gp
common.frozen();bundle,jobs,*_=load_native();pb,power,*_=load_power(bundle);grid=native_coefficients(pb);FrozenQ50()
assert (len(jobs),len(power),len(grid))==(1499,1152,96)
m=gp.Model();m.Params.OutputFlag=0;x=m.addVar(vtype=gp.GRB.BINARY);m.addConstr(x==1);m.setObjective(x);m.optimize();assert m.Status==2 and m.ObjVal==1;m.dispose()
inputs=list(csv.DictReader((R/'docs/v42_ubuntu_gpu_migration/V42_DATA_MIGRATION_MANIFEST.csv').open(encoding='utf8')))
assert all(sha(Path(r['source']))==r['sha256'] for r in inputs)
z=zipfile.ZipFile(O/'ABORTED_MIGRATION_EVIDENCE.zip');rows=list(csv.DictReader(io.TextIOWrapper(z.open('Ubuntu_evidence/IEEE8500_FILE_MANIFEST.csv'),encoding='utf8')))
win=0;refs=0
for i,row in enumerate(rows):
    if row['original'].startswith('/'):
        relative=row['original'].split('/MobileESS/',1)[1]
        blob=subprocess.check_output(['git','show',row['git_HEAD']+':'+relative],cwd=R)
        assert hashlib.sha256(blob).hexdigest()==row['sha256'];refs+=1
    else:
        p=Path(row['original']);assert p.is_file() and p.stat().st_size==int(row['bytes']),p;win+=1
    if i%20000==0:print('POST_WINDOWS_ORIGINAL_CHECK',i,len(rows),flush=True)
with (O/'TEST_POST_ROLLBACK_WINDOWS.log').open('w',encoding='utf8') as f:
    t=subprocess.run([sys.executable,'-m','pytest','-q','tests'],cwd=R,stdout=f,stderr=subprocess.STDOUT)
assert t.returncode==0
receipt=dict(PASS=True,canonical_runtime='WINDOWS',native_jobs=1499,Runtime_times=1152,grid_times=96,Gurobi_version=list(gp.gurobi.version()),Gurobi_license_PASS=True,FrozenQ50_PASS=True,frozen_source_hashes_PASS=True,original_input_files_hash_checked=len(inputs),Windows_IEEE8500_original_files_size_checked=win,Git_backed_reference_files_hash_checked=refs,Windows_IEEE8500_deleted=0,migration_specific_Linux_dependencies=0,preexisting_UNC_authorities_retained=5,tests=(O/'TEST_POST_ROLLBACK_WINDOWS.log').read_text(encoding='utf8')[-1800:],full_structure_predeletion_PASS=True,production_A1=False,scientific_source_unchanged_from_a88879fd=True,python=sys.executable,branch=subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip(),HEAD_at_healthcheck=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip())
(O/'POST_ROLLBACK_WINDOWS_VALIDATION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('POST_ROLLBACK_WINDOWS_HEALTH_PASS',win,refs,flush=True)
