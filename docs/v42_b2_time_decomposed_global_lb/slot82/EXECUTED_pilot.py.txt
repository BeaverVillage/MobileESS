"""Three preregistered joint integer snapshots, one Optimize each, no Full96 build."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import argparse, gc, hashlib, json, math, os, re, shutil, sys, time, traceback
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.time_decomposed_lb.grid import read,write,sha,require
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
from tools.time_decomposed_lb.resources import memory,admission,inventory,heavy_candidates,admit,callbackcheck

DOCS=ROOT/'docs/v42_b2_time_decomposed_global_lb'
OLD=ROOT/'docs/v42_physical_global_lb_pilot'
SAVED=Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
PARENT='40ab888b884255e76fd6c89fd01933570b60c242'
SOURCE='497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE='34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
UB=.6760534504652341
OLDLB=.46498486997548166
SLOTS=(75,82,94)
UNITS=('MESS01','MESS02','MESS03','MESS04')
PHYSICS={'connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','connected_Qmax','connected_Qmin','PCS16'}
PARAMS=dict(Threads=1,TimeLimit=30.,Method=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=1e-6)

def data(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k] for k in z.files}

def axis(name):
    family,parts=str(name).rstrip(']').split('[',1)
    return family,parts.split(',')

def build(slot):
    require(slot in SLOTS,'UNREGISTERED_SLOT')
    out=DOCS/f'slot{slot:02d}'
    require(not (out/'NATIVE0.json').exists(),'SEALED_SNAPSHOT_NO_REBUILD')
    begin=time.perf_counter();before=memory()
    raw=read(out/'GRID_RAW_CLOSURE.json.gz');authority=read(out/'GRID_AUTHORITY.json')
    require(authority['PASS'] and raw['source']==SOURCE and raw['case_sha']==CASE and raw['slot']==slot,'GRID_AUTHORITY')
    inherited=read(OLD/'NATIVE0.json');proof=read(OLD/'INDEPENDENT_NATIVE0.json')
    require(inherited['PASS'] and proof['PASS'] and inherited['case_sha']==CASE,'ORIGINAL_PHYSICAL_SLICE_AUTHORITY')
    index=read(OLD/'EVIDENCE_INDEX.json')['files']
    identity=read(SAVED/'SCIENTIFIC_CASE_IDENTITY.json')
    require(sha(SAVED/'SCIENTIFIC_CASE_IDENTITY.json')==inherited['source_records'][str(SAVED/'SCIENTIFIC_CASE_IDENTITY.json')],'SOURCE_IDENTITY_BYTES')
    physical=identity['physical_prescreen_authority']['proof'];arcs=physical['arcs']
    names=[];lower=[];upper=[];types=[];start=[];columns={};rows=[];sources={}
    def add(name,lo,hi,typ,value):
        require(name not in columns,'DUPLICATE_SNAPSHOT_COLUMN')
        columns[name]=len(names);names.append(name);lower.append(float(lo));upper.append(float(hi));types.append(typ);start.append(float(value))
    for unit in UNITS:
        paths={kind:OLD/f'UNIT_{unit}_{kind}.npz' for kind in ('A','DATA','AXES','START')}
        for kind,p in paths.items():
            expected=inherited['models'][unit].get({'A':'matrix_sha','DATA':'data_sha','AXES':'axes_sha'}.get(kind,'')) if kind!='START' else index[p.name]['sha256']
            require(sha(p)==expected,'UNIT_AUTHORITY_BYTES:'+p.name);sources[str(p)]=expected
        A=sparse.load_npz(paths['A']).tocsr();d=data(paths['DATA']);ax=data(paths['AXES']);u4=data(paths['START'])['point']
        local_names=list(map(str,d['names']));lookup={n:j for j,n in enumerate(local_names)}
        power={n:j for j,n in enumerate(local_names) if n.startswith(('Pch[','Pdis[','Q[')) and int(axis(n)[1][-1])==slot}
        power_ids=set(power.values())
        sites=sorted({axis(n)[1][1] for n in power})
        require(set(sites)==set(physical['sites']),'SNAPSHOT_MUST_INCLUDE_ALL_ORIGINAL_SITES')
        stays={}
        for j,n in enumerate(local_names):
            if not n.startswith('arc['):continue
            k=int(axis(n)[1][1]);site,t,dest,end,route=arcs[k]
            if route is None and t==slot:
                require(site==dest and end==slot+1 and site not in stays,'ORIGINAL_STAY_AXIS')
                stays[site]=j
        require(set(stays)==set(sites),'ORIGINAL_ALL_SLOT_STAYS')
        replacement={j:f'z[{unit},{site},{slot}]' for site,j in stays.items()}
        for site in sites:
            j=stays[site];require(d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1,'STAY_BINARY_CONTRACT')
            add(replacement[j],0,1,'B',u4[j])
        mode=f'charge_mode[{unit},{slot}]';j=lookup[mode]
        require(d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1,'MODE_BINARY_CONTRACT');add(mode,0,1,'B',u4[j])
        for n,j in sorted(power.items()):
            require(d['types'][j]=='C','ORIGINAL_POWER_TYPE');add(n,d['lower'][j],d['upper'][j],'C',u4[j])
        selected=[]
        for i,rname in enumerate(d['row_names']):
            family=str(rname).split('[',1)[0]
            if family not in PHYSICS:continue
            a,b=A.indptr[i:i+2];ids=A.indices[a:b];vals=A.data[a:b]
            pp=[int(j) for j in ids if local_names[j].startswith(('Pch[','Pdis[','Q['))]
            if not pp or not any(j in power_ids for j in pp):continue
            require(all(j in power_ids for j in pp),'IMMEDIATE_PHYSICS_HAS_CROSS_TIME_POWER')
            coeff={};original={}
            for j,v in zip(ids,vals):
                j=int(j);n=local_names[j];mapped=replacement.get(j,n)
                require(mapped in columns,'UNKNOWN_TIME_COUPLING_IN_IMMEDIATE_PHYSICS:'+n)
                coeff[mapped]=str(F(float(v)));original[n]=str(F(float(v)))
            rows.append(dict(name=f'{family}[{unit},{slot},original{int(ax["rows"][i])}]',family=family,unit=unit,
                original_row=int(ax['rows'][i]),original_unit_row=i,original_coeff=original,coeff=coeff,
                sense=str(d['sense'][i]),rhs=str(F(float(d['rhs'][i]))),
                native_coeff={n:float(F(v)) for n,v in coeff.items()},native_rhs=float(d['rhs'][i]),
                stay_replacement={local_names[j]:replacement[j] for j in ids if int(j) in replacement}))
            selected.append(family)
        require(Counter(selected)==Counter({fam:len(sites)*(16 if fam=='PCS16' else 1) for fam in PHYSICS}),'PHYSICS_FULL_FACET_GATE_COVER')
        rows.append(dict(name=f'one_location[{unit},{slot}]',family='one_location',unit=unit,original_row=None,
            coeff={replacement[j]:'1' for j in stays.values()},sense='<',rhs='1',
            native_coeff={replacement[j]:1. for j in stays.values()},native_rhs=1.,
            proof='Binary unit-flow on original strict time DAG is one path; at most one STAY in any slot. All-zero permits transit/disconnection.'))
        del A,d,ax,u4;gc.collect()
    rho=authority['rho_contract'];require(rho==dict(name='rho_max',original_column=240134,lower=0.,upper=1.,objective=1.,objective_constant=0.),'ORIGINAL_RHO_CONTRACT')
    add('rho_max',0,1,'C',UB)
    raw_names={int(j):v['name'] for j,v in raw['columns'].items()}
    helper_names=[]
    for j,b in raw['columns'].items():
        n=b['name'];lo=float.fromhex(b['lower_hex']);hi=float.fromhex(b['upper_hex'])
        if n in columns:
            require(lower[columns[n]]==lo and upper[columns[n]]==hi,'GRID_PHYSICS_LEAF_DOMAIN:'+n)
        else:
            require(n.startswith(('response_','injection_')) and b['type']=='C' and float.fromhex(b['objective_hex'])==0.,'UNKNOWN_HELPER_LEAF:'+n)
            add(n,lo,hi,'C',0.);helper_names.append(n)
    gridrows=[];definitions={}
    for r in raw['rows']:
        coeff={raw_names[int(j)]:float.fromhex(v) for j,v in r['terms']}
        gridrows.append(dict(name=r['name'],native_coeff=coeff,native_rhs=float.fromhex(r['rhs_hex']),sense=r['sense']))
        family=r['name'].split('[',1)[0]
        if family.endswith('_binding'):
            pivots=[n for n,v in coeff.items() if v==1. and n.split('[',1)[0]+'_binding'==family]
            require(r['sense']=='=' and len(pivots)==1 and pivots[0] not in definitions,'HELPER_START_PIVOT')
            definitions[pivots[0]]=gridrows[-1]
    exact_start={n:F(start[c]) for n,c in columns.items() if n not in helper_names};visiting=set()
    def helper_value(n):
        if n in exact_start:return exact_start[n]
        require(n in definitions and n not in visiting,'HELPER_START_CYCLE_OR_UNKNOWN')
        visiting.add(n);r=definitions[n]
        value=F(r['native_rhs'])-sum((F(v)*helper_value(k) for k,v in r['native_coeff'].items() if k!=n),F(0))
        visiting.remove(n);exact_start[n]=value;return value
    for n in helper_names:start[columns[n]]=float(helper_value(n))
    physical_rows=len(rows);allrows=rows+gridrows
    rr=[];cc=[];vv=[]
    for i,row in enumerate(allrows):
        for n,v in row['native_coeff'].items():
            require(n in columns,'GRID_LEAF_UNMAPPED:'+n)
            rr.append(i);cc.append(columns[n]);vv.append(v)
    A=sparse.csr_matrix((vv,(rr,cc)),shape=(len(allrows),len(names)));A.sort_indices()
    d=dict(names=np.asarray(names),lb=np.asarray(lower),ub=np.asarray(upper),vtypes=np.asarray(types),
        c=np.asarray([float(n=='rho_max') for n in names]),rhs=np.asarray([r['native_rhs'] for r in allrows]),
        senses=np.asarray([r['sense'] for r in allrows]),row_names=np.asarray([r['name'] for r in allrows]),constant=np.asarray(0.))
    x=np.asarray(start);res=A@x-d['rhs'];violation=np.where(d['senses']=='=',abs(res),np.where(d['senses']=='<',res,-res))
    require(float(violation.max())<=1e-8 and np.max(abs(x[d['vtypes']=='B']-np.rint(x[d['vtypes']=='B'])))==0,'U4_SNAPSHOT_REPLAY_FAILED')
    require(np.all(x>=d['lb']-1e-8) and np.all(x<=d['ub']+1e-8),'U4_SNAPSHOT_BOX_FAILED')
    dims=dict(rows=A.shape[0],columns=A.shape[1],binary=int(sum(d['vtypes']=='B')),nnz=int(A.nnz))
    sizepass=dims['binary']<=256 and dims['rows']<=30000 and dims['nnz']<=500000
    sparse.save_npz(out/'SNAP_A.npz',A);np.savez_compressed(out/'SNAP_DATA.npz',**d);np.savez_compressed(out/'SNAP_START.npz',x=x)
    write(out/'PHYSICS_EXACT.json',dict(PASS=True,slot=slot,source=SOURCE,case_sha=CASE,rows=rows,source_records=sources,
        original_sites=physical['sites'],original_integer_projection_preserved=True,
        omitted_couplings=['96-slot route flow','inter-slot travel','SOC and endpoints','departure energy','rebound temporal coupling'],
        projection='Original binary STAY arcs become z; original mode and P/Q retained; literal immediate rows unchanged.'))
    files=['SNAP_A.npz','SNAP_DATA.npz','SNAP_START.npz','PHYSICS_EXACT.json','GRID_EXACT.json.gz','GRID_RAW_CLOSURE.json.gz','GRID_AUTHORITY.json']
    write(out/'NATIVE0.json',dict(PASS=sizepass,slot=slot,parent_PR214=PARENT,source18r=SOURCE,case_sha=CASE,
        dimensions=dims,physical_rows=physical_rows,grid_rows=authority['rows'],helper_rows=len(raw['helper_rows']),matrix_sha=matrix_sha(A),domain_sha=_domain_sha(d),
        Native_grid_representation='Literal original equality-helper lift; equivalent to exact Fraction-eliminated security',
        flattened_grid_nnz=authority['nnz'],helper_grid_nnz=sum(len(r['native_coeff']) for r in gridrows),
        new_Native_coefficient_rounding=False,unbounded_helper_bounds_preserved=True,
        file_sha256={n:sha(out/n) for n in files},U4_max_violation=float(max(0.,violation.max())),
        original_integer_projection_preserved=True,size_gate_PASS=sizepass,Native_optimize_calls=0,
        Full96_model_constructed=False,full_MILP_calls=0,model_extraction_seconds=time.perf_counter()-begin,
        memory_before=before,memory_after=memory()))
    print(json.dumps(dict(PASS=sizepass,slot=slot,dimensions=dims)))

def attr(m,name):
    try:
        v=getattr(m,name)
        return None if isinstance(v,float) and (not math.isfinite(v) or abs(v)>=1e99) else v
    except Exception:return None

def native(slot):
    out=DOCS/f'slot{slot:02d}'
    require(slot in SLOTS and not (out/'PILOT_STARTED.json').exists(),'SNAPSHOT_UNREGISTERED_OR_ALREADY_CONSUMED')
    zero=read(out/'NATIVE0.json');ind=read(out/'INDEPENDENT_NATIVE0.json')
    require(zero['PASS'] and ind['PASS'],'INDEPENDENT_NATIVE0_GATE')
    for n,h in zero['file_sha256'].items():require(sha(out/n)==h,'SEALED_SNAPSHOT_DRIFT:'+n)
    pre=memory();require(admission(pre),'INITIAL_MEMORY_ADMISSION')
    peers,errors=inventory();heavy=heavy_candidates(peers)
    write(out/'PRE_NATIVE_PEERS.json',dict(PASS=not heavy and not errors,peers=peers,errors=errors,heavy_peers=heavy))
    require(not heavy and not errors,'OTHER_HEAVY_SOLVER_PRESENT')
    A=sparse.load_npz(out/'SNAP_A.npz').tocsr();d=data(out/'SNAP_DATA.npz')
    import gurobipy as gp
    from gurobipy import GRB
    env=gp.Env(empty=True);env.setParam('LogFile',str(out/'NATIVE.log'));env.start()
    m=gp.Model(f'B2_4MESS_SNAPSHOT_{slot}',env=env)
    for n,v in PARAMS.items():m.setParam(n,v)
    begin=time.perf_counter();x=m.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],obj=d['c'],vtype=d['vtypes'])
    m.addMConstr(A,x,d['senses'],d['rhs']);m.ObjCon=float(d['constant']);m.ModelSense=1;m.update();buildseconds=time.perf_counter()-begin
    checks=dict(matrix=matrix_sha(m.getA().tocsr())==matrix_sha(A),RHS=np.array_equal(m.getAttr('RHS'),d['rhs']),
        senses=np.array_equal(m.getAttr('Sense'),d['senses']),lb=np.array_equal(x.LB,d['lb']),ub=np.array_equal(x.UB,d['ub']),
        types=np.array_equal(x.VType,d['vtypes']),objective=np.array_equal(x.Obj,d['c']),ObjCon=m.ObjCon==0.,ModelSense=m.ModelSense==1,
        binary=m.NumBinVars==zero['dimensions']['binary'],Rows=m.NumConstrs==A.shape[0],Columns=m.NumVars==A.shape[1],NNZ=m.NumNZs==A.nnz,
        IsMIP=m.IsMIP==1)
    write(out/'NATIVE_READBACK.json',dict(PASS=all(checks.values()),checks=checks,parameters={n:getattr(m.Params,n) for n in PARAMS},
        gurobi_version=list(gp.gurobi.version()),model_build_seconds=buildseconds,matrix_sha=matrix_sha(A),domain_sha=_domain_sha(d)))
    require(all(checks.values()),'NATIVE_READBACK_FAILED')
    post=memory();gate=admit(pre,post);write(out/'MEMORY_RESOURCE_ADMISSION.json',gate);require(gate['PASS'],'POST_BUILD_RESOURCE_ADMISSION')
    x.Start=data(out/'SNAP_START.npz')['x'];m.update()
    ledgerpath=DOCS/'NATIVE_LEDGER.json';ledger=read(ledgerpath) if ledgerpath.exists() else dict(calls=[],snapshot_maximum_calls=3,window_maximum_calls=1,maximum_requested_seconds=210)
    prior=[c for c in ledger['calls'] if c['kind']=='SNAPSHOT']
    require(len(prior)<3 and slot not in [c['slot'] for c in prior] and len(ledger['calls'])<4,'GLOBAL_CALL_BUDGET')
    require([c['slot'] for c in prior]==list(SLOTS[:len(prior)]) and slot==SLOTS[len(prior)],'SNAPSHOT_SEQUENCE')
    require(sum(c['TimeLimit'] for c in prior)+30<=90 and sum(c['TimeLimit'] for c in ledger['calls'])+30<=210,'REQUESTED_TIME_BUDGET')
    ledger['calls'].append(dict(kind='SNAPSHOT',slot=slot,TimeLimit=30.,pid=os.getpid(),time=time.time(),out=str(out)));write(ledgerpath,ledger)
    execution={p.name:sha(p) for p in (ROOT/'tools/time_decomposed_lb').glob('*.py')}
    write(out/'EXECUTION_SOURCES.json',execution)
    for p in (ROOT/'tools/time_decomposed_lb').glob('*.py'):shutil.copyfile(p,out/('EXECUTED_'+p.name+'.txt'))
    with (out/'PILOT_STARTED.json').open('x',encoding='utf-8') as f:json.dump(dict(slot=slot,kind='SNAPSHOT',parameters=PARAMS,
        Native_optimize_calls=1,source=SOURCE,case_sha=CASE,files=zero['file_sha256'],independent_native0_sha256=sha(out/'INDEPENDENT_NATIVE0.json'),
        ledger_sha256=sha(ledgerpath),execution_source_sha256=execution),f,indent=2)
    samples=[post];issues=[];stops=[];unsafe=[];lastmem=0.;lastsafe=0.;root_observations=[];simplex_complete=[];message_root=[];callback_time=0.
    def callback(model,where):
        nonlocal lastmem,lastsafe,callback_time
        b=time.perf_counter();now=time.monotonic()
        try:
            if now-lastmem>=.5:
                sample=memory();samples.append(sample);lastmem=now
                if not admission(sample,0):unsafe.append(sample);model.terminate()
            if now-lastsafe>=5:
                check=callbackcheck();lastsafe=now
                if not check['PASS']:stops.append(check);model.terminate()
            if where==GRB.Callback.SIMPLEX:
                if model.cbGet(GRB.Callback.SPX_PRIMINF)<=1e-8 and model.cbGet(GRB.Callback.SPX_DUALINF)<=1e-8:
                    simplex_complete.append(dict(objective=model.cbGet(GRB.Callback.SPX_OBJVAL),iteration=model.cbGet(GRB.Callback.SPX_ITRCNT)))
            if where==GRB.Callback.MIPNODE and model.cbGet(GRB.Callback.MIPNODE_NODCNT)==0:
                root_observations.append(dict(status=int(model.cbGet(GRB.Callback.MIPNODE_STATUS)),bound=model.cbGet(GRB.Callback.MIPNODE_OBJBND)))
            if where==GRB.Callback.MESSAGE:
                msg=model.cbGet(GRB.Callback.MSG_STRING)
                if 'Root relaxation:' in msg:message_root.append(msg.strip())
                if any(token in msg.lower() for token in ('numerical trouble','out of memory','numeric error')):issues.append(msg.strip());model.terminate()
        except Exception as exc:issues.append(repr(exc));model.terminate()
        finally:callback_time+=time.perf_counter()-b
    begin=time.perf_counter();error=None
    try:m.optimize(callback)
    except Exception as exc:error=repr(exc)
    elapsed=time.perf_counter()-begin;samples.append(memory());solcount=attr(m,'SolCount') or 0
    if solcount>0:np.savez_compressed(out/'INCUMBENT.npz',x=x.X)
    root_log=[]
    for msg in message_root:
        hit=re.search(r'Root relaxation: objective\s+([-+\d.eE]+)',msg)
        if hit:root_log.append(float(hit.group(1)))
    result=dict(kind='SNAPSHOT',slot=slot,Status=attr(m,'Status'),SolCount=solcount,ObjVal=attr(m,'ObjVal'),ObjBound=attr(m,'ObjBound'),
        ObjBoundC=attr(m,'ObjBoundC'),MIPGap=attr(m,'MIPGap'),NodeCount=attr(m,'NodeCount'),IterCount=attr(m,'IterCount'),Runtime=attr(m,'Runtime'),
        Work=attr(m,'Work'),MaxMemUsed_GB=attr(m,'MaxMemUsed'),TimeLimit=30.,Threads=1,Native_optimize_calls=1,
        model_build_seconds=buildseconds,optimize_wall_seconds=elapsed,callback_seconds=callback_time,
        Rows=m.NumConstrs,Columns=m.NumVars,Binary=m.NumBinVars,NNZ=m.NumNZs,
        LP_relaxation_log_objective=root_log[0] if root_log else None,LP_relaxation_value_is_log_rounded=True,
        root_complete=bool(root_log or any(r['status']==2 for r in root_observations)),
        root_relaxation_observed=bool(root_log or any(r['status']==2 for r in root_observations)),integer_optimal=attr(m,'Status')==2,
        root_node_observations=root_observations,simplex_completed_observations=simplex_complete,root_log_messages=message_root,
        peak_process_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
        minimum_RAM_available=min(s['system']['RAM_available'] for s in samples),minimum_commit_available=min(s['system']['Commit_available'] for s in samples),
        optimize_error=error,numeric_errors=issues,resource_stops=stops,memory_stops=unsafe,
        full_MILP_calls=0,campaign_calls=0,B1_launches=0,incumbent_is_original_FULL_UB=False,Actual_AC_PASS=False)
    write(out/'MEMORY_TRACE.json',dict(samples=samples,unsafe_samples=unsafe));write(out/'RESOURCE_TRACE.json',dict(stops=stops,callback_errors=issues))
    m.dispose();env.dispose();write(out/'RESULT.json',result);print(json.dumps(result))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['build','native'],required=True);ap.add_argument('--slot',type=int,required=True)
    args=ap.parse_args()
    try:build(args.slot) if args.mode=='build' else native(args.slot)
    except Exception as exc:
        out=DOCS/f'slot{args.slot:02d}';write(out/(args.mode.upper()+'_FAILURE.json'),dict(error=repr(exc),traceback=traceback.format_exc(),
            Native_optimize_started=(out/'PILOT_STARTED.json').exists(),memory=memory()));raise
