"""Windows canonical source/input/tests, bounded equivalence and unchanged full F2 census."""
import os,sys,json,subprocess,hashlib,csv,gc,time
from collections import defaultdict,Counter
from pathlib import Path
O=Path(__file__).absolute().parent;R=O.parents[1];sys.path.insert(0,str(R))
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def git(*a):return subprocess.check_output(['git','-C',str(R),*a],text=True,encoding='utf8').strip()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert os.name=='nt' and not os.environ.get('MOBILEESS_PATH_MAP')
assert not git('diff','a88879fdb4e6c51dae35656feee90f68ed19ad8f','--','v42_root','tests')
dump('WINDOWS_CANONICAL_RUNTIME_AUDIT.json',dict(canonical_runtime='WINDOWS',worktree=str(R),branch=git('branch','--show-current'),HEAD=git('rev-parse','HEAD'),status=git('status','--porcelain'),remotes=git('remote','-v'),python=sys.executable,Linux_venv_copied=False))
from v42_root import common,gates,start_audit
from v42_root.data import scientific_signature,prepare
from v42_root.profile import Census
from v42_boundary.boundaries import load_native
from v42_temporal.native import load_power
from v42_may01.prepare import native_coefficients
from v42_final.runtime import FrozenQ50
from v42_exact.support import ExactFactory
from v42_exact.native import build
import gurobipy as gp
common.frozen();bundle,jobs,bounds,seconds,r,raw=load_native();power_bundle,power,*_=load_power(bundle);grid=native_coefficients(power_bundle);FrozenQ50()
assert len(jobs)==1499 and len(power)==1152 and len(grid)==96
m=gp.Model();x=m.addVar(vtype=gp.GRB.BINARY);m.addConstr(x==1);m.setObjective(x);m.optimize();assert m.Status==2 and m.ObjVal==1;m.dispose()
tests={}
for label,args in [('PR102',['--ignore=tests/test_v42_root.py']),('WIP',[])]:
    with (O/('TEST_WINDOWS_'+label+'.log')).open('w',encoding='utf8') as f:q=subprocess.run([sys.executable,'-m','pytest','-q','tests',*args],cwd=R,stdout=f,stderr=subprocess.STDOUT)
    assert q.returncode==0,label;tests[label]=(O/('TEST_WINDOWS_'+label+'.log')).read_text(encoding='utf8')[-1700:];print('WINDOWS_TEST_PASS',label,flush=True)
old=common.OUT;common.OUT=O;gates.main();common.OUT=old
bounded=json.loads((O/'SCIENTIFIC_AGGREGATION_EQUIVALENCE.json').read_text());assert bounded['PASS'] and len(bounded['cases'])==35
factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));classes=defaultdict(list)
for u,j in sorted(jobs.items()):classes[common.digest(scientific_signature(j,bounds[u],factory.original.cache.identity,raw[u],bundle))].append(u)
sizes=Counter(map(len,classes.values()));cs=dict(jobs=len(jobs),class_count=len(classes),singleton_classes=sizes[1],non_singleton_classes=sum(n for s,n in sizes.items() if s>1),jobs_covered_by_non_singletons=sum(s*n for s,n in sizes.items() if s>1),max_class_size=max(sizes))
assert cs==dict(jobs=1499,class_count=117,singleton_classes=20,non_singleton_classes=97,jobs_covered_by_non_singletons=1479,max_class_size=75)
data=prepare();assert len(data[1])==1499
class Context:
    folder=O/'WINDOWS_F2_BUILD_RECEIPTS'
    def check(self):pass
    def progress(self,d):common.atomic(self.folder/'build_progress.json',d)
ctx=Context();ctx.folder.mkdir(exist_ok=True)
old=common.OUT;common.OUT=O;oldlocal=start_audit.LOCAL;start_audit.LOCAL=ctx.folder;start_audit.main();start_audit.LOCAL=oldlocal;common.OUT=old
print('WINDOWS_FULL_F2_CENSUS_BUILD',flush=True);started=time.perf_counter()
with Census() as census:m,v,levels,controls,bindings=build(ctx,data,'F2')
actual=dict(binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,rows=m.NumConstrs,nonzeros=m.NumNZs)
expected=dict(binaries=2796366,continuous=5124335,rows=9358534,nonzeros=100455768);assert actual==expected
families,maxdensity=census.rows(m);by={x['family']:x for x in families}
assert (by['Runtime_completion_risk']['rows'],by['Runtime_completion_risk']['nonzeros'])==(1152,34923402)
assert (by['tie']['rows'],by['tie']['nonzeros'])==(273614,14503274)
with (O/'WINDOWS_ROOT_CENSUS.csv').open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(families[0]));w.writeheader();w.writerows(families)
dump('WINDOWS_PR102_STRUCTURE_COMPARISON.json',dict(PASS=True,actual=actual,expected=expected,full_original_F2=True,optimizer_called=False,seconds=time.perf_counter()-started,Runtime=by['Runtime_completion_risk'],tie=by['tie'],source_hashes_match=True))
m.dispose();del m,v,levels,controls,bindings,data;gc.collect();common.frozen()
inputs=list(csv.DictReader((R/'docs/v42_ubuntu_gpu_migration/V42_DATA_MIGRATION_MANIFEST.csv').open(encoding='utf8')))
for row in inputs:assert sha(Path(row['source']))==row['sha256'],row['source']
preexisting_UNC=[row['source'] for row in inputs if row['source'].replace('\\','/').startswith('//wsl.localhost/')]
dump('MIGRATION_PATH_REVERT_AUDIT.json',dict(PASS=True,scientific_source_unchanged_from_a88879fd=True,production_MOBILEESS_PATH_MAP_unset=True,migration_sitecustomize_inactive=True,migration_specific_Linux_dependencies=0,immutable_original_input_hashes_PASS=True,original_input_files=len(inputs),preexisting_UNC_authorities=preexisting_UNC,note='Original Windows behavior uses five pre-existing Linux/UNC array authorities; these are retained. No migrated mobileess_data/research/worktree path is used.',frozen_input_contents_changed=False))
dump('ROOT_LP_WIP_WINDOWS_RESTORE.json',dict(PASS=True,root_LP_WIP_restored_on_Windows=True,classes=cs,bounded_cases=35,bounded_equivalence_PASS=True,Runtime=by['Runtime_completion_risk'],tie=by['tie'],MIP_start_physical_precheck=json.loads((O/'MIP_START_AUTHORITY_AUDIT.json').read_text())['physical_precheck_PASS'],global_MIP_start_complete=False,production_A1=False,scientific_source_unchanged=True))
dump('WINDOWS_V42_VALIDATION.json',dict(PASS=True,imports=True,Runtime_provider=True,native_grid=True,Gurobi_license=True,Gurobi_version=list(gp.gurobi.version()),tests=tests,bounded_equivalence=True,full_build=True,classes=cs,python=sys.executable,canonical_runtime='WINDOWS',production_A1=False))
print('WINDOWS_CANONICAL_VALIDATION_PASS',actual,cs,flush=True)
