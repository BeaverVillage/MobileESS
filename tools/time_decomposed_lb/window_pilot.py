"""One 8-slot Window, only after explicit execution and binary-cap authority."""
from pathlib import Path
from fractions import Fraction as F
import argparse,gc,json,math,os,re,shutil,sys,time,traceback
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.time_decomposed_lb.grid import read,write,sha,require
from tools.time_decomposed_lb.pilot import data,attr,PARENT,SOURCE,CASE,UB
from tools.time_decomposed_lb.resources import memory,admission,inventory,heavy_candidates,admit,callbackcheck
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
DOCS=ROOT/'docs/v42_b2_time_decomposed_global_lb'
PHYS=DOCS/'window_native0'
GRID=DOCS/'window_native0'
OUT=DOCS/'window360'
PARAMS=dict(Threads=1,TimeLimit=360.,Method=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=1e-6)

def build():
    require(not (OUT/'NATIVE0.json').exists(),'SEALED_WINDOW_NO_REBUILD')
    begin=time.perf_counter();pre=memory();proof=read(PHYS/'WINDOW_NATIVE0_DESIGN.json')
    require(proof['PASS'] and proof['window']==[88,96] and proof['original_FULL_to_window_physical_projection_proved'],'WINDOW_PHYSICAL_PROJECTION')
    for n,h in proof['file_sha256'].items():require(sha(PHYS/n)==h,'SEALED_WINDOW_PHYSICS_BYTES:'+n)
    gridproof=read(GRID/'WINDOW_GRID_AUTHORITY.json');raw=read(GRID/'WINDOW_GRID_RAW_CLOSURE.json.gz')
    require(gridproof['PASS'] and raw['source']==SOURCE and raw['case_sha']==CASE,'ALL_WINDOW_SOURCE_GRID_AUTHORITY')
    Aphys=sparse.load_npz(PHYS/'WINDOW_PHYSICS_A.npz').tocsr();d=data(PHYS/'WINDOW_PHYSICS_DATA.npz');u4=data(PHYS/'WINDOW_PHYSICS_U4.npz')['x']
    names=list(map(str,d['names']));lb=list(d['lb']);ub=list(d['ub']);types=list(d['vtypes']);start=list(u4);lookup={n:j for j,n in enumerate(names)}
    require('rho_max' not in lookup and np.count_nonzero(d['c'])==0 and float(d['constant'])==0.,'PHYSICAL_WINDOW_OBJECTIVE')
    def add(n,lo,hi,value):
        lookup[n]=len(names);names.append(n);lb.append(lo);ub.append(hi);types.append('C');start.append(value)
    add('rho_max',0.,1.,UB);raw_names={int(j):b['name'] for j,b in raw['columns'].items()};helpers=[]
    for j,b in raw['columns'].items():
        n=b['name'];lo=float.fromhex(b['lower_hex']);hi=float.fromhex(b['upper_hex'])
        if n in lookup:require(lb[lookup[n]]==lo and ub[lookup[n]]==hi,'WINDOW_GRID_PHYSICAL_BOX:'+n)
        else:
            require(b['type']=='C' and n.startswith(('response_','injection_')) and float.fromhex(b['objective_hex'])==0.,'WINDOW_UNKNOWN_HELPER')
            add(n,lo,hi,0.);helpers.append(n)
    definitions={};rr=[];cc=[];vv=[];rhs=[];senses=[];rownames=[]
    for i,r in enumerate(raw['rows']):
        coeff={raw_names[int(j)]:float.fromhex(v) for j,v in r['terms']}
        for n,v in coeff.items():rr.append(i);cc.append(lookup[n]);vv.append(v)
        rhs.append(float.fromhex(r['rhs_hex']));senses.append(r['sense']);rownames.append(r['name'])
        fam=r['name'].split('[',1)[0]
        if fam.endswith('_binding'):
            pivot=[n for n,v in coeff.items() if v==1. and n.split('[',1)[0]+'_binding'==fam]
            require(len(pivot)==1 and r['sense']=='=' and pivot[0] not in definitions,'WINDOW_U4_HELPER_PIVOT')
            definitions[pivot[0]]=(coeff,F(rhs[-1]))
    values={n:F(float(start[j])) for n,j in lookup.items() if n not in helpers};visiting=set()
    def lift(n):
        if n in values:return values[n]
        require(n in definitions and n not in visiting,'WINDOW_HELPER_START_CYCLE')
        visiting.add(n);co,b=definitions[n];ans=b-sum((F(v)*lift(k) for k,v in co.items() if k!=n),F(0));visiting.remove(n);values[n]=ans;return ans
    for n in helpers:start[lookup[n]]=float(lift(n))
    G=sparse.csr_matrix((vv,(rr,cc)),shape=(len(raw['rows']),len(names)));G.sort_indices()
    P=sparse.hstack((Aphys,sparse.csr_matrix((Aphys.shape[0],len(names)-Aphys.shape[1]))),format='csr')
    A=sparse.vstack((P,G),format='csr');A.sort_indices()
    d=dict(names=np.asarray(names),lb=np.asarray(lb),ub=np.asarray(ub),vtypes=np.asarray(types),c=np.asarray([float(n=='rho_max') for n in names]),
        rhs=np.r_[d['rhs'],rhs],senses=np.r_[d['senses'],senses],row_names=np.r_[d['row_names'],rownames],constant=np.asarray(0.))
    x=np.asarray(start);res=A@x-d['rhs'];err=np.where(d['senses']=='=',abs(res),np.where(d['senses']=='<',res,-res))
    require(float(err.max())<=1e-7 and np.max(abs(x[d['vtypes']=='B']-np.rint(x[d['vtypes']=='B'])))==0.,'WINDOW_ORIGINAL_U4_LIFT_FAILED')
    require(np.all(x>=d['lb']-1e-8) and np.all(x<=d['ub']+1e-8),'WINDOW_U4_BOUND_FAILED')
    dims=dict(rows=A.shape[0],columns=A.shape[1],binary=int(np.count_nonzero(d['vtypes']=='B')),nnz=int(A.nnz))
    require(dims['rows']<=100000 and dims['nnz']<=1500000,'WINDOW_ROW_NNZ_CAP')
    OUT.mkdir(parents=True,exist_ok=True);sparse.save_npz(OUT/'WINDOW_A.npz',A);np.savez_compressed(OUT/'WINDOW_DATA.npz',**d);np.savez_compressed(OUT/'WINDOW_START.npz',x=x)
    files={n:sha(OUT/n) for n in ('WINDOW_A.npz','WINDOW_DATA.npz','WINDOW_START.npz')}
    source_records={str(PHYS/n):sha(PHYS/n) for n in ('WINDOW_PHYSICS_A.npz','WINDOW_PHYSICS_DATA.npz','WINDOW_PHYSICS_U4.npz','WINDOW_NATIVE0_DESIGN.json')}
    source_records.update({str(GRID/n):sha(GRID/n) for n in ('WINDOW_GRID_AUTHORITY.json','WINDOW_GRID_RAW_CLOSURE.json.gz')})
    write(OUT/'NATIVE0.json',dict(PASS=True,phase='Mathematical model only; execution requires separate binary-cap/user/resource authority',window=[88,96],source18r=SOURCE,parent_PR214=PARENT,case_sha=CASE,
        dimensions=dims,physical_rows=Aphys.shape[0],grid_plus_helpers_rows=G.shape[0],grid_plus_helpers_nnz=G.nnz,physical_directory=str(PHYS),grid_directory=str(GRID),
        physical_representation='compact_node_activity' if PHYS.name=='window_compact_native0' else 'literal_binary_arcs',
        original_binary_cap=1500,original_binary_cap_PASS=dims['binary']<=1500,Rows_NNZ_caps_PASS=True,
        current_binary_cap_authority_required=dims['binary']>1500,Native_execution_authorized_by_this_receipt=False,
        original_FULL_projection_subset_Window=True,all_8_slot_Source_security_retained=True,original_unbounded_helpers_retained=True,new_coefficient_rounding=False,
        matrix_sha=matrix_sha(A),domain_sha=_domain_sha(d),file_sha256=files,source_records=source_records,U4_max_violation=float(max(0,err.max())),
        model_extraction_seconds=time.perf_counter()-begin,Native_optimize_calls=0,full_MILP_calls=0,memory_before=pre,memory_after=memory()))
    print(json.dumps(dict(PASS=True,dimensions=dims,original_binary_cap_PASS=dims['binary']<=1500)))

def native():
    authority=read(DOCS/'USER_WINDOW_360_OVERRIDE.json')
    require(authority['binary_cap_override_authorized'] is True and authority['Window_TimeLimit_seconds']==360 and
        authority['explicit_Window_execution_requested_despite_nonmaterial_snapshots'],'WINDOW_BINARY_CAP_AUTHORITY_PENDING')
    review=read(DOCS/'PRE_NATIVE_WINDOW_FORMULATION_REVIEW.json')
    require(review['PASS'] and review['Source18r_continuous_route_binary_node_reuse_reviewed'] and
        review['chosen_representation']==read(OUT/'NATIVE0.json')['physical_representation'],'WINDOW_COMPACT_PRIORITY_REVIEW_REQUIRED')
    require(not (OUT/'PILOT_STARTED.json').exists(),'WINDOW_ALREADY_CONSUMED_NO_REPEAT')
    zero=read(OUT/'NATIVE0.json');ind=read(OUT/'INDEPENDENT_NATIVE0.json');require(zero['PASS'] and ind['PASS'],'INDEPENDENT_WINDOW_NATIVE0_GATE')
    require(zero['dimensions']['binary']<=authority['approved_binary_cap'] and zero['dimensions']['rows']<=100000 and
        zero['dimensions']['nnz']<=1500000,'WINDOW_ACTUAL_SIZE_CAPS')
    for n,h in zero['file_sha256'].items():require(sha(OUT/n)==h,'SEALED_WINDOW_DRIFT:'+n)
    for n,h in zero['source_records'].items():require(sha(n)==h,'WINDOW_SOURCE_DRIFT:'+n)
    pre=memory();require(admission(pre),'WINDOW_PRE_BUILD_MEMORY')
    peers,errors=inventory();heavy=heavy_candidates(peers);write(OUT/'PRE_NATIVE_PEERS.json',dict(PASS=not heavy and not errors,peers=peers,errors=errors,heavy_peers=heavy));require(not heavy and not errors,'OTHER_HEAVY_NATIVE')
    A=sparse.load_npz(OUT/'WINDOW_A.npz').tocsr();d=data(OUT/'WINDOW_DATA.npz')
    import gurobipy as gp
    from gurobipy import GRB
    env=gp.Env(empty=True);env.setParam('LogFile',str(OUT/'NATIVE.log'));env.start();m=gp.Model('B2_JOINT_WINDOW_88_96',env=env)
    for n,v in PARAMS.items():m.setParam(n,v)
    begin=time.perf_counter();x=m.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],obj=d['c'],vtype=d['vtypes']);m.addMConstr(A,x,d['senses'],d['rhs']);m.ObjCon=0.;m.ModelSense=1;m.update();buildseconds=time.perf_counter()-begin
    checks=dict(matrix=matrix_sha(m.getA().tocsr())==matrix_sha(A),RHS=np.array_equal(m.getAttr('RHS'),d['rhs']),senses=np.array_equal(m.getAttr('Sense'),d['senses']),
        lb=np.array_equal(x.LB,d['lb']),ub=np.array_equal(x.UB,d['ub']),types=np.array_equal(x.VType,d['vtypes']),objective=np.array_equal(x.Obj,d['c']),
        ObjCon=m.ObjCon==0.,ModelSense=m.ModelSense==1,Rows=m.NumConstrs==A.shape[0],Columns=m.NumVars==A.shape[1],Binary=m.NumBinVars==zero['dimensions']['binary'],NNZ=m.NumNZs==A.nnz,IsMIP=m.IsMIP==1)
    write(OUT/'NATIVE_READBACK.json',dict(PASS=all(checks.values()),checks=checks,parameters={n:getattr(m.Params,n) for n in PARAMS},model_build_seconds=buildseconds,
        gurobi_version=list(gp.gurobi.version()),matrix_sha=matrix_sha(A),domain_sha=_domain_sha(d)));require(all(checks.values()),'WINDOW_NATIVE_READBACK_FAILED')
    post=memory();gate=admit(pre,post,phase='WINDOW_POST_BUILD_PRE_OPTIMIZE');write(OUT/'MEMORY_RESOURCE_ADMISSION.json',gate);require(gate['PASS'],'WINDOW_ACTUAL_MEMORY_RESOURCE_ADMISSION')
    x.Start=data(OUT/'WINDOW_START.npz')['x'];m.update();ledgerpath=DOCS/'NATIVE_LEDGER.json';ledger=read(ledgerpath)
    frozen=read(DOCS/'SNAPSHOT_NATIVE_LEDGER.json');require(ledger['calls']==frozen['calls'] and len(ledger['calls'])==3 and [c['slot'] for c in ledger['calls']]==[75,82,94],'SNAPSHOT_LEDGER_PREFIX_MUST_MATCH')
    require(sum(c['TimeLimit'] for c in ledger['calls'])==90,'SNAPSHOT_BUDGET_MUST_BE_PRESERVED')
    ledger['original_maximum_requested_seconds']=ledger['maximum_requested_seconds'];ledger['maximum_requested_seconds']=450;ledger['user_window_override_sha256']=sha(DOCS/'USER_WINDOW_360_OVERRIDE.json')
    ledger['calls'].append(dict(kind='WINDOW',window=[88,96],TimeLimit=360.,pid=os.getpid(),time=time.time(),out=str(OUT)));write(ledgerpath,ledger)
    execution={p.name:sha(p) for p in (ROOT/'tools/time_decomposed_lb').glob('*.py')};write(OUT/'EXECUTION_SOURCES.json',execution)
    for p in (ROOT/'tools/time_decomposed_lb').glob('*.py'):shutil.copyfile(p,OUT/('EXECUTED_'+p.name+'.txt'))
    with (OUT/'PILOT_STARTED.json').open('x',encoding='utf-8') as f:json.dump(dict(kind='WINDOW',window=[88,96],Native_optimize_calls=1,parameters=PARAMS,files=zero['file_sha256'],
        source_records=zero['source_records'],independent_native0_sha256=sha(OUT/'INDEPENDENT_NATIVE0.json'),user_override_sha256=sha(DOCS/'USER_WINDOW_360_OVERRIDE.json'),
        formulation_review_sha256=sha(DOCS/'PRE_NATIVE_WINDOW_FORMULATION_REVIEW.json'),latest_user_requirements_sha256=sha(DOCS/'USER_WINDOW_PRE_NATIVE_REQUIREMENTS_KO.txt'),
        ledger_sha256=sha(ledgerpath),execution_source_sha256=execution),f,indent=2)
    samples=[post];issues=[];stops=[];unsafe=[];lastmem=0.;lastsafe=0.;roots=[];rootmsg=[];callbackseconds=0.
    def callback(model,where):
        nonlocal lastmem,lastsafe,callbackseconds
        begin=time.perf_counter();now=time.monotonic()
        try:
            if now-lastmem>=.5:
                sample=memory();samples.append(sample);lastmem=now
                if not admission(sample,0):unsafe.append(sample);model.terminate()
            if now-lastsafe>=5:
                check=callbackcheck();lastsafe=now
                if not check['PASS']:stops.append(check);model.terminate()
            if where==GRB.Callback.MIPNODE and model.cbGet(GRB.Callback.MIPNODE_NODCNT)==0:
                roots.append(dict(status=int(model.cbGet(GRB.Callback.MIPNODE_STATUS)),bound=model.cbGet(GRB.Callback.MIPNODE_OBJBND)))
            if where==GRB.Callback.MESSAGE:
                msg=model.cbGet(GRB.Callback.MSG_STRING)
                if 'Root relaxation:' in msg:rootmsg.append(msg.strip())
                if any(s in msg.lower() for s in ('numerical trouble','out of memory','numeric error')):issues.append(msg.strip());model.terminate()
        except Exception as exc:issues.append(repr(exc));model.terminate()
        finally:callbackseconds+=time.perf_counter()-begin
    begin=time.perf_counter();error=None
    try:m.optimize(callback)
    except Exception as exc:error=repr(exc)
    elapsed=time.perf_counter()-begin;samples.append(memory());solcount=attr(m,'SolCount') or 0
    if solcount:np.savez_compressed(OUT/'INCUMBENT.npz',x=x.X)
    rootlp=[]
    for msg in rootmsg:
        hit=re.search(r'Root relaxation: objective\s+([-+\d.eE]+)',msg)
        if hit:rootlp.append(float(hit.group(1)))
    result=dict(kind='WINDOW',window=[88,96],Status=attr(m,'Status'),SolCount=solcount,ObjVal=attr(m,'ObjVal'),ObjBound=attr(m,'ObjBound'),ObjBoundC=attr(m,'ObjBoundC'),
        MIPGap=attr(m,'MIPGap'),NodeCount=attr(m,'NodeCount'),IterCount=attr(m,'IterCount'),Runtime=attr(m,'Runtime'),Work=attr(m,'Work'),MaxMemUsed_GB=attr(m,'MaxMemUsed'),TimeLimit=360.,Threads=1,Native_optimize_calls=1,
        Rows=m.NumConstrs,Columns=m.NumVars,Binary=m.NumBinVars,NNZ=m.NumNZs,model_build_seconds=buildseconds,optimize_wall_seconds=elapsed,callback_seconds=callbackseconds,
        LP_relaxation_log_objective=rootlp[0] if rootlp else None,LP_relaxation_value_is_log_rounded=True,root_complete=bool(rootlp or any(r['status']==2 for r in roots)),root_node_observations=roots,root_log_messages=rootmsg,integer_optimal=attr(m,'Status')==2,
        peak_process_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),minimum_commit_available=min(s['system']['Commit_available'] for s in samples),
        optimize_error=error,numeric_errors=issues,resource_stops=stops,memory_stops=unsafe,full_MILP_calls=0,B1_launches=0,campaign_calls=0,incumbent_is_original_FULL_UB=False,Actual_AC_PASS=False)
    write(OUT/'MEMORY_TRACE.json',dict(samples=samples,unsafe_samples=unsafe));write(OUT/'RESOURCE_TRACE.json',dict(stops=stops,callback_errors=issues));m.dispose();env.dispose();write(OUT/'RESULT.json',result);print(json.dumps(result))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=('build','native'),required=True);ap.add_argument('--physical',type=Path,default=PHYS);args=ap.parse_args();PHYS=args.physical.resolve()
    try:build() if args.mode=='build' else native()
    except Exception as exc:
        write(OUT/(args.mode.upper()+'_FAILURE.json'),dict(error=repr(exc),traceback=traceback.format_exc(),Native_optimize_started=(OUT/'PILOT_STARTED.json').exists(),memory=memory()));raise
