"""Read saved campaign evidence only. No solver/model imports or construction."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import sys, importlib.abc
class SolverImportBlock(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'gurobipy' or fullname.startswith('v42_'):
            raise PermissionError('DIAGNOSTIC_SOLVER_AND_PRODUCTION_IMPORT_FORBIDDEN')
sys.meta_path.insert(0, SolverImportBlock())
import argparse, ast, csv, datetime as dt, gzip, hashlib, json, math, pickle, re
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
RUN = Path('C:/v42_pr134_sc_execution_20261007')
SELECTED = ['2025-05-11', '2025-05-12', '2025-05-13', '2025-05-20', '2025-05-01']
EXCLUDED = {'2025-05-10', '2025-05-17', '2025-05-19'}
SOURCES = {}
def record(p):
    p=Path(p)
    with p.open('rb') as f: h=hashlib.file_digest(f, 'sha256').hexdigest()
    r=dict(path=str(p), sha256=h, bytes=p.stat().st_size)
    SOURCES[str(p)]=r
    return r
def read(p):
    record(p)
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(n,x):
    (OUT/n).write_bytes((json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
def clean_range(x):
    x=np.abs(x[np.isfinite(x)&(np.abs(x)<1e90)&(x!=0)])
    return [float(x.min()),float(x.max())] if len(x) else [None,None]
def row_group(n):
    if n.startswith(('voltage_', 'transformer_', 'line_thermal', 'NormalAmps')):return 'grid'
    if n.startswith('CC4_'):return 'CC4'
    if n.startswith(('RT_', 'Runtime_', 'exact_Runtime_')):return 'Runtime'
    if n in ('known_GPU_binding','nominal_and_compute_headroom'):return 'rack_GPU_gang'
    if n.startswith('physical_'):return 'WAN_flow_state'
    if n.startswith('row_v42_root_'):
        line=int(n.rsplit('_',1)[1])
        if line in (81,82,86,92,93,94,95,96,146,149):return 'WAN_flow_state'
        if line in (65,66,67,69,70,75,76,77,102,104,111,113):return 'migration'
        if line in (40,78,125,128,129):return 'job_time_resource'
    if n=='class_exact_cardinality':return 'job_time_resource'
    return 'other_explicit'
def col_group(n):
    if n in ('wan_start','wan_active','wan_final','remaining','sent','link_selected','link_bytes'):return 'WAN_flow_state'
    if n in ('migration_selected','source_selected','destination_selected','pair','depart','arrive'):return 'migration'
    if n in ('y','q','f0','f1','r0','h','r1'):return 'job_time_resource'
    if n.startswith('CC4'):return 'CC4'
    if n.startswith(('RT_','Runtime','risk')):return 'Runtime'
    if n=='known':return 'rack_GPU_gang'
    if n=='rho_max':return 'grid'
    return 'global_other' if n=='global_other' else 'other_explicit'

def parse_log(day,p):
    record(p); text=p.read_text(encoding='utf-8')
    headers=list(re.finditer(r'^Optimize a model with ',text,re.M))
    assert headers
    first=text[:headers[1].start()] if len(headers)>1 else text
    def match(pattern,cast=float):
        m=re.search(pattern,first,re.M)
        return cast(m[1]) if m else None
    raw=re.search(r'Optimize a model with (\d+) rows, (\d+) columns and (\d+) nonzeros',first)
    pre=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',first)
    types=list(re.finditer(r'Variable types: (\d+) continuous, (\d+) integer \((\d+) binary\)',first))
    root=re.search(r'Root relaxation: (.*?), (\d+) iterations, ([\d.]+) seconds \(([\d.]+) work units\)',first)
    assert raw and pre and len(types)>=2 and root
    def counts(m,types):return dict(rows=int(m[1]),columns=int(m[2]),nnz=int(m[3]),continuous=int(types[1]),integer_total=int(types[2]),binaries=int(types[3]),other_integers=int(types[2])-int(types[3]))
    progress=[]
    for m in re.finditer(r'^\s*(\d+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+(\d+)s\s*$',first,re.M):
        progress.append(dict(iteration=int(m[1]),objective=float(m[2]),primal_infeasibility=float(m[3]),dual_infeasibility=float(m[4]),native_runtime_rounded_seconds=int(m[5])))
    warnings=[s.strip() for s in first.splitlines() if re.search(r'Warning:|numerical trouble|Markowitz|refactor|Kappa|quad precision|switch to|scaling',s,re.I)]
    root_done=root[1].startswith('objective ')
    clock=re.search(r'logging started (.+)',first)[1].strip()
    clock=dt.datetime.strptime(clock,'%a %b %d %H:%M:%S %Y').replace(tzinfo=dt.timezone(dt.timedelta(hours=9)))
    r=dict(native_logging_start_UTC=clock.astimezone(dt.timezone.utc).isoformat(),raw=counts(raw,types[0]),presolved=counts(pre,types[1]),presolve_seconds=match(r'Presolve time: ([\d.]+)s'),
        root_method=match(r'Set parameter Method to value (\d+)',int),root_phase='DUAL_SIMPLEX',root_completed=root_done,
        root_status=root[1],root_iterations=int(root[2]),root_seconds=float(root[3]),root_Work=float(root[4]),
        root_progress=progress,root_objective=float(root[1].split()[-1]) if root_done else None,
        last_printed_root_objective=progress[-1]['objective'] if progress else None,
        warnings=warnings,barrier_seen=bool(re.search(r'Barrier statistics|Barrier performed|Root barrier log',first)),
        crossover_seen=bool(re.search(r'Crossover log|pushes remaining|crossover time',first,re.I)),
        refactorization_messages=[s for s in warnings if 'refactor' in s.lower()],Kappa=None,KappaExact=None,
        Kappa_availability='Not recorded in existing receipts/logs; no solve requested',
        input_MIP_start_messages=[s.strip() for s in first.splitlines() if re.search(r'User MIP start|Loaded.*start|MIP start did not|Start solution',s,re.I)],
        native_log_rounding={'times_seconds':0.01,'Work':0.01,'progress_seconds':1},P1_log_file=record(p))
    for label,pattern in [('matrix_range',r'Matrix range\s+\[([^,]+), ([^\]]+)\]'),('objective_range',r'Objective range\s+\[([^,]+), ([^\]]+)\]'),('bounds_range',r'Bounds range\s+\[([^,]+), ([^\]]+)\]'),('RHS_range',r'RHS range\s+\[([^,]+), ([^\]]+)\]')]:
        m=re.search(pattern,first);r[label+'_native_printed']=[float(m[1]),float(m[2])] if m else None
    r['rows_removed']=r['raw']['rows']-r['presolved']['rows'];r['columns_removed']=r['raw']['columns']-r['presolved']['columns']
    r['presolve_reduction']={k:1-r['presolved'][k]/r['raw'][k] for k in ['rows','columns','nnz']}
    if len(progress)>1:
        steps=np.diff([x['objective'] for x in progress]);times=np.diff([x['native_runtime_rounded_seconds'] for x in progress]);iters=np.diff([x['iteration'] for x in progress])
        r['stalling']=dict(progress_rows=len(progress),printed_objective_identical_intervals=int((steps==0).sum()),
            objective_step_abs_below_1e_7_intervals=int((np.abs(steps)<=1e-7).sum()),
            maximum_identical_objective_interval_seconds=float(times[steps==0].max(initial=0)),
            all_printed_dual_infeasibility_zero=all(x['dual_infeasibility']==0 for x in progress),
            first=progress[0],last=progress[-1],iterations_per_root_second=int(root[2])/float(root[3]))
    return r

def telemetry(day,native_runtime,start_UTC):
    p=RUN/'MAY_B1_RESOURCE_LEDGER.csv';record(p)
    rows=[]
    with p.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['day']==day and row['stage']=='A1' and row['worker_PID']:
                rows.append(row)
    assert rows
    def time(s):return dt.datetime.fromisoformat(s).timestamp()
    start=time(start_UTC);end=start+native_runtime
    native=[x for x in rows if start<=time(x['UTC'])<=end+1]
    def summary(v):
        return dict(samples=len(v),first_UTC=v[0]['UTC'],last_UTC=v[-1]['UTC'],
            max_RSS_GiB=max(float(x['RSS']) for x in v)/2**30,min_available_RAM_GiB=min(float(x['available_RAM']) for x in v)/2**30,
            CPU_seconds_delta=float(v[-1]['CPU_seconds'])-float(v[0]['CPU_seconds']),
            wall_seconds=time(v[-1]['UTC'])-time(v[0]['UTC']),
            paging_and_system_commit_counters_recorded=False)
    result=dict(full_A1=summary(rows),P1_native_interval=summary(native),
        P1_interval_method='First native log logging-start clock (KST, integer second), plus P1 receipt Runtime; approximately +/-1 second',
        pre_native_build_proof_and_materialization_wall_seconds=start-time(rows[0]['UTC']),
        resource_guard_or_slowdown_actions=any(x['admission_or_cancellation_action']=='True' for x in rows),
        limitation='RSS/CPU/free RAM recorded; page-in, hard faults, process commit, system commit, disk queue not recorded',source=record(p))
    return result

def family_roles(descriptor,z,proof,stats):
    # Do not trust uint16 vf codes when the original dictionary has >65536 entries.
    # Independently reconstruct first-seen scientific variable ownership from saved
    # interfaces, in the same documented order as the existing native family census.
    n=len(z['lb']);roles=np.full(n,-1,dtype=np.int16);labels=[]
    def assign(label,ids):
        if label not in labels:labels.append(label)
        code=labels.index(label);ids=np.asarray(ids,dtype=np.int64)
        if ids.size:roles[ids[roles[ids]<0]]=code
    for u in descriptor['units']:
        for fam,items in u['v'].items():
            ids=[]
            for e in items.values():
                if e[0]=='v':ids.append(e[1])
                elif e[0]=='e':ids.extend(e[2])
            assign(fam,ids)
    # A nonzero coefficient's column with a family recorded independently in the
    # snapshot is an explicit semantic authority, not a guessed name dictionary.
    for label,items in [('known',descriptor['known']),('risk',descriptor['risk'])]:
        assign(label,[e[1] for e in items.values() if e[0]=='v'])
    for name,j in descriptor['globals'].items():assign(name.split('[')[0],[j])
    # finish_count variables were created after all units. Their names survive in
    # vf_names and each exact defining row has the newly created column last.
    return roles,labels

def sample_parallel(a,z):
    samples=[]
    for code in np.unique(z['rf']):
        ids=np.flatnonzero(z['rf']==code)
        chosen=np.unique(np.concatenate([ids[:32],ids[-32:]]))
        for j in chosen:
            b,e=a.indptr[j:j+2]
            samples.append((int(j),a.indices[b:e],a.data[b:e]))
    lhs={};exact={};support=defaultdict(list);same=0;duplicates=0;max_cos=-1.;pair=None;near=0;examined=0
    for j,idx,coef in samples:
        key=(idx.tobytes(),coef.tobytes());rhs=(key,str(z['sense'][j]),float(z['rhs'][j]))
        if key in lhs:same+=1
        if rhs in exact:duplicates+=1
        lhs.setdefault(key,j);exact.setdefault(rhs,j)
        if len(idx) and np.linalg.norm(coef)>0:support[idx.tobytes()].append((j,coef))
    for members in support.values():
        for i,(j,c) in enumerate(members):
            for k,d in members[:i]:
                cos=abs(float(np.dot(c,d)/(np.linalg.norm(c)*np.linalg.norm(d))));examined+=1
                if cos>max_cos:max_cos=cos;pair=[k,j]
                if cos>=1-1e-10:near+=1
    return dict(scope='Deterministic first/last 32 rows of every original retained row family; no model reduction or proof adoption',
        sample_rows=len(samples),exact_duplicate_rows_in_sample=duplicates,identical_LHS_rows_in_sample=same,
        same_support_pairs_examined=examined,absolute_cosine_at_least_1_minus_1e_10_pairs=near,
        maximum_absolute_cosine=max_cos if max_cos>=0 else None,max_cosine_row_pair=pair,
        limitations='Sample only; cosine depends on units; neither near-parallelism nor zero findings establish exact redundancy or root degeneracy')

def analyze(day):
    assert day in SELECTED and day not in EXCLUDED
    p=RUN/'stages'/day/'A1'/'1'/'output'
    log=parse_log(day,p/'A1_SOLVE.log');receipt=read(p/'PASS_1_RECEIPT.json');build=read(p/'BUILD_RECEIPT.json');census=read(p/'A2SC_MODEL_CENSUS.json')
    bundle=read(RUN/'inputs'/day/'NATIVE_INPUT.json');window=read(RUN/'inputs'/day/'WINDOWS.json')
    stats=read(p/'F2-CRA_MODEL_STATS.json') if (p/'F2-CRA_MODEL_STATS.json').exists() else None
    record(p/'SCIENTIFIC_INTERFACES.pkl.gz')
    with gzip.open(p/'SCIENTIFIC_INTERFACES.pkl.gz','rb') as f:desc=pickle.load(f)
    data=dict(day=day,campaign_status='TIMEOUT' if day=='2025-05-12' else 'PASS',log=log,P1_receipt=receipt,build_receipt=build,
        jobs_raw=len(bundle['known_population']),jobs_modeled=sum(j['planning_eligible'] and j['service_slots']>0 for j in bundle['known_population']),
        complete_logical_units=len(desc['units']),optional_migration_units=sum(u['optional'] for u in desc['units']),
        scientific_classes=len(set(u['class_key'] for u in desc['units'])),native_build_stats=stats,
        native_model_build_seconds=stats['model_build_seconds'] if stats else None,census=census,
        source_input_SHA256=record(RUN/'inputs'/day/'NATIVE_INPUT.json')['sha256'],telemetry=telemetry(day,receipt['native_runtime'],log['native_logging_start_UTC']))
    raw_roles=None;labels=None;family=[];numerical=[];global_raw_n=None
    record(p/'A2SC_PROOF.npz')
    with np.load(p/'A2SC_PROOF.npz') as q:proof={k:q[k] for k in ['roots_delta','retained_rows_delta']}
    roots=np.cumsum(proof['roots_delta']);kept=np.cumsum(proof['retained_rows_delta'])
    for name in ['A0','A2SC']:
        record(p/(name+'_MATRIX.npz'));record(p/(name+'_ATTRIBUTES_CODED.npz'))
        a=sparse.load_npz(p/(name+'_MATRIX.npz'))
        with np.load(p/(name+'_ATTRIBUTES_CODED.npz'),allow_pickle=False) as f:z={k:f[k] for k in f.files}
        assert a.shape==(len(z['rhs']),len(z['lb']))
        if name=='A0':
            raw_roles,labels=family_roles(desc,z,proof,stats)
            finish=np.flatnonzero(np.isin(z['rf'],[i for i,n in enumerate(z['rf_names']) if n=='exact_Runtime_finish_count']))
            finish_ids=a.indices[a.indptr[finish+1]-1] if len(finish) else np.array([],dtype=np.int64)
            if 'Runtime_finish_count' not in labels:labels.append('Runtime_finish_count')
            unknown=finish_ids[raw_roles[finish_ids]<0];raw_roles[unknown]=labels.index('Runtime_finish_count')
            if 'global_other' not in labels:labels.append('global_other')
            raw_roles[raw_roles<0]=labels.index('global_other');roles=raw_roles
            if stats:
                actual=Counter(labels[int(k)] for k in roles)
                for k,n in stats['family_counts'].items():assert actual[k]==n,(day,k,actual[k],n)
            global_raw_n=sum(int(np.count_nonzero(roles==i)) for i,n in enumerate(labels) if col_group(n) in ['grid','CC4','Runtime','rack_GPU_gang','global_other'])
        else:roles=raw_roles[roots]
        row_counts=np.bincount(z['rf'],minlength=len(z['rf_names']));rd=np.diff(a.indptr);cd=np.bincount(a.indices,minlength=a.shape[1])
        for i,n in enumerate(z['rf_names']):
            ids=np.flatnonzero(z['rf']==i);family.append(dict(day=day,model=name,kind='ROW',family=str(n),group=row_group(str(n)),count=int(row_counts[i]),nnz=int(rd[ids].sum()),ownership='disjoint exact saved row-family axis'))
        for i,n in enumerate(labels):
            ids=np.flatnonzero(roles==i);family.append(dict(day=day,model=name,kind='COLUMN',family=n,group=col_group(n),count=len(ids),nnz=int(cd[ids].sum()),ownership='disjoint first-seen original interface ownership transported through saved exact roots mapping'))
        fixed=np.equal(z['lb'],z['ub']);cont=z['vtype']=='C';zero_obj=z['obj']==0
        unbounded_hi=z['ub']>=1e90;unbounded_lo=z['lb']<=-1e90;finite_bounds=(~unbounded_hi)&(~unbounded_lo)
        info=dict(model=name,rows=a.shape[0],columns=a.shape[1],nnz=int(a.nnz),binaries=int((z['vtype']=='B').sum()),continuous=int(cont.sum()),other_integers=int((z['vtype']=='I').sum()),
            coefficient_range_exact=clean_range(a.data),RHS_range_exact=clean_range(z['rhs']),bound_range_exact=clean_range(np.concatenate([z['lb'],z['ub']])),
            matrix_nonzeros_abs_below_1e_8=int((np.abs(a.data)<1e-8).sum()),objective_nonzero_columns=int((~zero_obj).sum()),
            objective_zero_fraction=float(zero_obj.mean()),zero_objective_continuous_columns=int((zero_obj&cont).sum()),
            fixed_columns=int(fixed.sum()),upper_unbounded_columns=int(unbounded_hi.sum()),lower_unbounded_columns=int(unbounded_lo.sum()),
            fully_free_columns=int((unbounded_hi&unbounded_lo).sum()),upper_unbounded_continuous_columns=int((unbounded_hi&cont).sum()),
            finite_bound_width_quantiles={str(q):float(np.quantile((z['ub']-z['lb'])[finite_bounds],q)) for q in [0,.5,.9,.99,1]},
            row_density_quantiles={str(q):float(np.quantile(rd,q)) for q in [0,.5,.9,.99,1]},
            column_degree_quantiles={str(q):float(np.quantile(cd,q)) for q in [0,.5,.9,.99,1]},
            isolated_columns=int((cd==0).sum()),
            variable_at_bound_fraction_at_root=None,zero_reduced_cost_variables_at_root=None,
            root_point_or_basis_or_reduced_cost_availability='No saved root primal vector, basis, or RC in existing date evidence',
            variable_family_dictionary_size=len(z['vf_names']),variable_family_code_dtype=str(z['vf'].dtype),
            variable_family_code_overflow=len(z['vf_names'])>np.iinfo(z['vf'].dtype).max+1,
            variable_family_ownership_authority='Reconstructed saved scientific interfaces; uint16 name codes not used')
        info['high_degree_columns']=[]
        for j in np.argsort(cd)[-12:][::-1]:
            original=int(j) if name=='A0' else int(roots[j]);entry=dict(column=int(j),original_column=original,degree=int(cd[j]),family=labels[int(roles[j])],objective=float(z['obj'][j]),lb=float(z['lb'][j]) if abs(z['lb'][j])<1e90 else '-Infinity',ub=float(z['ub'][j]) if abs(z['ub'][j])<1e90 else 'Infinity')
            info['high_degree_columns'].append(entry)
        if name=='A2SC':
            info['sampled_row_parallelism']=sample_parallel(a,z)
            point=p/'PASS_1_RAW_POINT.npz'
            if point.exists():
                record(point)
                with np.load(point) as f:x=f['values']
                assert len(x)==a.shape[1]
                at=np.isclose(x,z['lb'],rtol=0,atol=1e-6)|np.isclose(x,z['ub'],rtol=0,atol=1e-6)
                info['P1_incumbent_at_bounds_fraction_NOT_ROOT']=float(at.mean())
                info['P1_incumbent_at_bounds_point_role']='Final P1 integer incumbent; not the root LP iterate/basis'
            else:info['P1_incumbent_at_bounds_fraction_NOT_ROOT']=None
        numerical.append(info)
        del a,z,rd,cd
    data['families']=family;data['numerical']=numerical
    modeled={j['job_uid'] for j in bundle['known_population'] if j['planning_eligible'] and j['service_slots']>0}
    data['shift_prestart_domain']=dict(window_jobs=len(window),allowed_start_choices=sum(len(x['allowed_starts']) for x in window),
        jobs_with_multiple_allowed_starts=sum(len(x['allowed_starts'])>1 for x in window),
        modeled_allowed_start_choices=sum(len(x['allowed_starts']) for x in window if x['job_id'] in modeled),
        modeled_jobs_with_multiple_allowed_starts=sum(len(x['allowed_starts'])>1 for x in window if x['job_id'] in modeled),
        modeled_can_prestart_place=sum(j['can_prestart_place'] for j in bundle['known_population'] if j['job_uid'] in modeled),
        modeled_can_checkpoint_migrate=sum(j['can_checkpoint_migrate'] for j in bundle['known_population'] if j['job_uid'] in modeled),
        ownership='Shared job-start y/state domains; no separate disjoint shift/prestart row family in P1',
        prestart_relocation='Later objective over original y placement; not a separate P1 constraint block')
    data['start']=dict(old_start_loaded=build['old_start_loaded'],previous_native_runtime_loaded=build['previous_native_runtime_loaded'],
        solver_MIP_start_messages=log['input_MIP_start_messages'],supplied=False,accepted=False,
        B0_reference_present=True,B0_reference_SHA256=bundle['reference']['sha256'],
        independently_validated_same_input_B0_or_B1_MIP_start_in_existing_output=False,
        reason='Authoritative B0 common reference is an input, not a full native feasible vector. Frozen production path supplies no Start or read-start operation before P1. May12 contains no incumbent point/freeze.')
    data['sources']=list(SOURCES.values());write(day+'.json',data)
    print('STATIC_DIAGNOSTIC_COMPLETE',day,data['jobs_modeled'],log['root_seconds'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--day',choices=SELECTED,required=True);args=parser.parse_args();analyze(args.day)
