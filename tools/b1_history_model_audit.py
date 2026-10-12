"""Read-only comparison of actual PR189 and PR212 May01/02/03 receipts."""
from pathlib import Path
from collections import Counter
import gc, gzip, hashlib, json, pickle, subprocess, sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_pr134_b1.common import read,record,digest,atomic,now
from tools.b1_snapshot_prefix import compact_snapshot

OLD='625bbcb8b9a54a00c1660c26d96f7737c2f75457'
NEW='4a969c59823c67dc5f52474491b24a9d55107e3d'
CURRENT=Path(r'D:\v42_b1_only_may_20261012_04')
HISTORICAL=Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01')
DOC=ROOT/'docs/v42_b1_rootcause_20261012'

def source_sha(revision):
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',revision],cwd=ROOT,text=True).splitlines()
    paths=[p for p in paths if p.startswith('v42_') and p.endswith('.py')]
    output=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=('\n'.join(revision+':'+p for p in paths)+'\n').encode())
    offset=0;files={}
    for path in paths:
        end=output.index(b'\n',offset);size=int(output[offset:end].split()[-1]);offset=end+1
        files[path]=hashlib.sha256(output[offset:offset+size]).hexdigest();offset+=size+1
    return dict(SHA=digest(files),files=len(files))

def rows(snapshot):
    a=snapshot.matrix;result=Counter()
    for r in range(a.shape[0]):
        lo,hi=a.indptr[r:r+2]
        h=hashlib.sha256(a.indices[lo:hi].tobytes()+a.data[lo:hi].tobytes()+
            snapshot.senses[r].tobytes()+snapshot.rhs[r].tobytes()).digest()
        result[h]+=1
    return result

def stats(snapshot):
    a=abs(snapshot.matrix.data);positive=a[a>0]
    return dict(rows=snapshot.matrix.shape[0],columns=snapshot.matrix.shape[1],nnz=snapshot.matrix.nnz,
        fingerprint=snapshot.fingerprint(),matrix_abs_range=[float(positive.min()),float(positive.max())],
        RHS_abs_max=float(abs(snapshot.rhs).max()),finite_bound_abs_max=float(np.maximum(abs(snapshot.lower[np.isfinite(snapshot.lower)]).max(initial=0),abs(snapshot.upper[np.isfinite(snapshot.upper)]).max(initial=0))),
        infinite_upper_bounds=int(np.count_nonzero(~np.isfinite(snapshot.upper))),
        types={str(t):int(np.count_nonzero(snapshot.vtypes==t)) for t in set(snapshot.vtypes)})

def native_summary(output, component, iteration='S0'):
    p=output/component/iteration
    if not (p/'NATIVE_RESULT.json').exists():return dict(available=False)
    n=read(p/'NATIVE_RESULT.json');i=read(p/'MODEL_IDENTITY.json');z=np.load(n['raw_attributes']['path'])
    return dict(available=True,result=record(p/'NATIVE_RESULT.json'),log=record(p/'NATIVE_SOLVER.log'),
        matrix=i['matrix'],attributes=i['attributes'],raw=n['raw_attributes'],
        raw_X_abs_max=float(abs(z['X']).max(initial=0)),status=n['status'],Runtime=n['native_seconds'],
        objective=n['objective'],parameters=read(p/'SOLVER_PARAMETERS.json'),
        compiled=read(p/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'))

def semantic_classes(output):
    with gzip.open(output/'STATIC/SCIENTIFIC_INTERFACES.pkl.gz','rb') as stream: desc=pickle.load(stream)
    members={}
    for unit in desc['units']:
        members.setdefault(unit['class_key'],set()).update(unit['members'])
    return {tuple(sorted(v)):k for k,v in members.items()},desc

def run():
    manifest=read(CURRENT/'CAMPAIGN_MANIFEST.json');audit=[]
    for day in ('2025-05-01','2025-05-02','2025-05-03'):
        historical=HISTORICAL/'dates/B1'/day/'output'
        root=Path(r'D:\v42_b1_only_may_20261012_03') if day.endswith('01') else CURRENT
        current=root/'dates/B1'/day/'attempts/attempt_01/output'
        old=compact_snapshot(historical/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz')
        new=compact_snapshot(current/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz')
        oldrows=rows(old);newrows=rows(new)
        oldq=read(historical/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records'];newq=read(current/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
        om={x['class_id']:x for x in oldq};nm={x['class_id']:x for x in newq}
        oldclasses,olddesc=semantic_classes(historical);newclasses,newdesc=semantic_classes(current)
        assert set(oldclasses)==set(newclasses)
        aligned=[]
        for members in sorted(oldclasses):
            oq=om[oldclasses[members]];nq=nm[newclasses[members]]
            aligned.append(dict(members=list(members),old_class=oq['class_id'],new_class=nq['class_id'],
                same_graph=oq['complete_graph_sha256']==nq['complete_graph_sha256'],
                same_local_snapshot=oq['complete_local_snapshot_sha256']==nq['complete_local_snapshot_sha256'],
                same_STAY=oq['full_physical_STAY']==nq['full_physical_STAY'],
                same_migration=oq['full_physical_migration']==nq['full_physical_migration'],
                cardinality_equal=oq['cardinality']==nq['cardinality']))
        oldprep=read(historical/'A_PREPARE_RECEIPT.json');newprep=read(current/'A_PREPARE_RECEIPT.json')
        for prep in (oldprep,newprep):
            for ref in prep['scientific_input'].values():assert record(ref['path'])==ref
        ob=read(oldprep['scientific_input']['NATIVE_INPUT.json']['path']);nb=read(newprep['scientific_input']['NATIVE_INPUT.json']['path'])
        different_keys=[k for k in sorted(set(ob)|set(nb)) if digest(ob.get(k))!=digest(nb.get(k))]
        identical_keys=[k for k in sorted(set(ob)&set(nb)) if digest(ob[k])==digest(nb[k])]
        coeff={}
        for k in ('voltage','current','planning_coefficients','transformer_coefficients'):
            ro=ob.get('grid_outputs',{}).get(k);rn=nb.get('grid_outputs',{}).get(k)
            if ro and rn:
                for ref in (ro,rn):
                    actual=record(ref['path'])
                    assert actual['sha256']==ref['sha256'] and actual['bytes']==ref['bytes']
                    assert Path(actual['path']).resolve()==Path(ref['path']).resolve()
                zo=np.load(ro['path']);zn=np.load(rn['path']);fields={}
                for f in sorted(set(zo.files)&set(zn.files)):
                    x,y=zo[f],zn[f];same=x.shape==y.shape and np.array_equal(x,y,equal_nan=True) if x.dtype.kind in 'fci' and y.dtype.kind in 'fci' else x.shape==y.shape and np.array_equal(x,y)
                    fields[f]=dict(old_shape=list(x.shape),new_shape=list(y.shape),bit_equal=bool(same))
                    if x.shape==y.shape and x.dtype.kind=='f' and y.dtype.kind=='f':fields[f]['max_abs_difference']=float(np.nanmax(abs(x-y),initial=0))
                coeff[k]=dict(old=ro,new=rn,fields=fields)
        oldstats=read(historical/'STATIC/BASE/F2-CRA_MODEL_STATS.json');newstats=read(current/'STATIC/BASE/F2-CRA_MODEL_STATS.json')
        oldfreeze=read(historical/'A_NATIVE_SOURCE_FREEZE.json');newfreeze=read(current/'A_NATIVE_SOURCE_FREEZE.json')
        rec=dict(day=day,old_result=manifest['origins'][day]['historical_B1_result'],
            current_result=record(current.parent/'RESULT.json'),old_actual_execution_commit=oldfreeze['git_head'],new_actual_execution_commit=newfreeze['git_head'],
            old_source_freeze=record(historical/'A_NATIVE_SOURCE_FREEZE.json'),new_source_freeze=record(current/'A_NATIVE_SOURCE_FREEZE.json'),
            old_initial_checkpoint=record(historical/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'),new_initial_checkpoint=record(current/'STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz'),
            old_model=stats(old),new_model=stats(new),old_builder_stats=oldstats,new_builder_stats=newstats,
            row_multiset_bit_identical=sum((oldrows&newrows).values()),old_unique_rows=sum((oldrows-newrows).values()),new_unique_rows=sum((newrows-oldrows).values()),
            columns_same_count=old.matrix.shape[1]==new.matrix.shape[1],
            column_arrays_equal={k:bool(np.array_equal(getattr(old,k),getattr(new,k))) for k in ('lower','upper','vtypes')} if old.matrix.shape[1]==new.matrix.shape[1] else None,
            classes_same_ids=set(om)==set(nm),job_counts=[sum(x['cardinality'] for x in oldq),sum(x['cardinality'] for x in newq)],
            class_counts=[len(oldq),len(newq)],
            domain_graphs_same=sum(om[k]['complete_graph_sha256']==nm[k]['complete_graph_sha256'] for k in set(om)&set(nm)),
            complete_local_snapshots_same=sum(om[k]['complete_local_snapshot_sha256']==nm[k]['complete_local_snapshot_sha256'] for k in set(om)&set(nm)),
            classes_aligned_by_original_job_members=aligned,
            aligned_same_graphs=sum(c['same_graph'] for c in aligned),aligned_same_local_snapshots=sum(c['same_local_snapshot'] for c in aligned),
            global_named_axes_identical=olddesc['globals']==newdesc['globals'],
            native_bundle_different_keys=different_keys,native_bundle_identical_keys=identical_keys,
            old_input=oldprep['scientific_input'],new_input=newprep['scientific_input'],electrical_coefficients=coeff,
            old_phaseI=native_summary(historical,'PHASE_I'),new_phaseI=native_summary(current,'PHASE_I'),
            old_P1=native_summary(historical,'P1'),new_P1=native_summary(current,'P1'),
            old_P1_trace=read(historical/'P1_TRACE.json'),new_P1_trace=read(current/'P1_TRACE.json') if (current/'P1_TRACE.json').exists() else None,
            old_initial_verification=record(historical/'INITIAL_VERIFICATION.json'),new_initial_verification=record(current/'INITIAL_VERIFICATION.json'))
        assert record(rec['old_result']['path'])==rec['old_result']
        audit.append(rec)
        print(json.dumps(dict(day=day,jobs=rec['job_counts'],classes=rec['class_counts'],unchanged_domains=rec['domain_graphs_same'],same_local_models=rec['complete_local_snapshots_same'],old_shape=old.matrix.shape,new_shape=new.matrix.shape,shared_rows=rec['row_multiset_bit_identical'])),flush=True)
        del old,new,oldrows,newrows;gc.collect()
    sources={p:dict(old=hashlib.sha256(subprocess.check_output(['git','show',OLD+':'+p],cwd=ROOT)).hexdigest(),new=hashlib.sha256(subprocess.check_output(['git','show',NEW+':'+p],cwd=ROOT)).hexdigest()) for p in ('v42_a_stage_canary/phase.py','v42_a_stage_canary/pricing.py','v42_pr134_b1/native.py','v42_may_campaign_native90/a_stage.py')}
    result=dict(schema='B1_HISTORICAL_CURRENT_MODELS_AUDIT_V1',Git_bases=[OLD,NEW],source_SHA_at_Git_bases={OLD:source_sha(OLD),NEW:source_sha(NEW)},source_files=sources,days=audit,Native_calls=0,historical_PASS_promoted=False,UTC=now())
    atomic(DOC/'HISTORICAL_MODEL_COMPARISON.json',result)

if __name__=='__main__':run()
