"""Build ALL retained grid rows before any optimizer is reachable.

No callback, candidate separation, refinement or grid-row generation exists
here. Screening and original static-presolve maps are immutable input files.
Raw coefficient mantissas are retained; selected auxiliary equalities remain
sparse instead of expanding every affine response into every 16-face row.
"""
import time,threading
import numpy as np
import scipy.sparse as sp
import psutil
from .static_common import *
from .static_pack import PACK,N_AUX
from .static_screen import CACHE,load
from .prestart_native import native_zero

def stats(m):
    m.update();return dict(binary=int(m.NumBinVars),continuous=int(m.NumVars-m.NumIntVars),
        variables=int(m.NumVars),rows=int(m.NumConstrs),nonzeros=int(m.DNumNZs))

def native_rows_exact(model,handle,C,rhs,sense,start):
    """Every actual Native coefficient, without a full constraint-list copy."""
    for i in range(C.shape[0]):
        constraint=handle[i].item();row=model.getRow(constraint);a,b=C.indptr[i:i+2]
        found={row.getVar(j).index:row.getCoeff(j) for j in range(row.size())}
        assert found==dict(zip(map(int,C.indices[a:b]),map(float,C.data[a:b])))
        assert constraint.RHS==rhs[i] and constraint.Sense==sense[i]
        if i%10000==0:guard(start)

def build():
    import gurobipy as gp
    res=init();start=time.perf_counter();peak=[0];done=threading.Event();m=None
    def sample():
        while not done.wait(.05):peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();blocks=[];report={}
    try:
        scr=read(OUT/'IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json');assert scr['PASS']
        pre=read(OUT/'ORIGINAL_STATIC_PRESOLVE_MESS8.json');assert pre['PASS']
        B=sp.load_npz(RUN/'mobility/SELECTED.npz')
        with np.load(RUN/'mobility/DOMAIN.npz') as z:d={k:z[k] for k in z.files}
        with np.load(RUN/'mobility/ORIGINAL_MAP.npz') as z:mp=z['column'];off=z['constant']
        nbase=len(mp);maps=[];nativefolder=RUN/'native';nativefolder.mkdir(exist_ok=True)
        m=gp.Model('V2_ADD_COMPLETE_STATIC_FULL_M1');m.Params.OutputFlag=0
        with native_zero() as denied:
            base=m.addMVar(B.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],name=d['names'])
            base_rows=m.addMConstr(B,base,d['sense'],d['rhs'],name='original_static_mobility')
            m.setObjective(d['objective']@base+float(d['constant']));m.update();vv=list(base.tolist())
            base_count=stats(m);native_rows_exact(m,base_rows,B,d['rhs'],d['sense'],start);del B,base_rows
            for t in range(96):
                guard(start)
                A,vd,r=load(t);lo=nbase+t*N_AUX
                with np.load(CACHE/f'{t:02d}'/'STATIC_SELECTION.npz') as z:rows=z['rows'];needed=z['variables']
                allocation_upper=len(needed)*512+A[rows].nnz*40+len(rows)*160
                if psutil.Process().memory_info().rss+allocation_upper>4*1024**3-128*1024**2:
                    raise MemoryError('PREEMPTIVE_4GIB_NATIVE_BUILD_LIMIT')
                if psutil.virtual_memory().available-allocation_upper<5*1024**3:
                    raise MemoryError('PREEMPTIVE_PROTECTED_WORKER_5GIB_RESERVE')
                # Reference components have local suffix00. Native global
                # names include the real slot; coordinate maps retain both.
                native_names=np.char.replace(vd['names'][needed].astype(str),'_00[',f'_{t:02d}[')
                v=m.addMVar(len(needed),lb=vd['lower'][needed],ub=vd['upper'][needed],vtype=vd['types'][needed],name=native_names);m.update()
                assert np.array_equal(m.getAttr('VarName',v.tolist()),native_names)
                startcol=len(vv);vv.extend(v.tolist())
                mapfile=np.full(N_AUX,-1,dtype=np.int64);mapfile[needed]=np.arange(startcol,len(vv))
                S=A[rows].tocoo();columns=np.empty(S.nnz,dtype=np.int64)
                isbase=S.col<nbase;local=S.col[~isbase]-lo
                assert np.all((local>=0)&(local<N_AUX))
                columns[isbase]=mp[S.col[isbase]];columns[~isbase]=mapfile[local]
                fixed=columns<0
                # Referenced eliminated power coordinates can only be exact0.
                assert not np.any(fixed&~isbase)
                assert np.all(off[S.col[fixed]]==0.)
                C=sp.csr_matrix((S.data[~fixed],(S.row[~fixed],columns[~fixed])),shape=(len(rows),len(vv)))
                C.sum_duplicates();C.eliminate_zeros();C.sort_indices()
                first=m.NumConstrs;used=np.unique(C.indices)
                native_rows=m.addMConstr(C[:,used],[vv[j] for j in used],r['sense'][rows],r['rhs'][rows],name=f'complete_original_grid_{t:02d}')
                m.update();guard(start)
                native_rows_exact(m,native_rows,C,r['rhs'][rows],r['sense'][rows],start)
                sp.save_npz(nativefolder/f'{t:02d}_EXPECTED.npz',C)
                np.savez_compressed(nativefolder/f'{t:02d}_MAP.npz',original_rows=rows,original_aux_to_native=mapfile,
                    first_native_row=first,rhs=r['rhs'][rows],sense=r['sense'][rows])
                b=dict(slot=t,rows=len(rows),nonzeros=C.nnz,auxiliary_variables=len(needed),first_native_row=first,
                    map=record(nativefolder/f'{t:02d}_MAP.npz'),expected=record(nativefolder/f'{t:02d}_EXPECTED.npz'))
                blocks.append(b);maps.append(mapfile)
                del native_rows
                put('COMPLETE_STATIC_NATIVE0_PROGRESS.json',dict(completed_slots=t+1,model=stats(m),
                    RSS_bytes=psutil.Process().memory_info().rss,wall_seconds=time.perf_counter()-start))
                if t%8==0:print('STATIC NATIVE0',t,stats(m),flush=True)
                del A,S,C
            guard(start);measured=stats(m);built=time.perf_counter()-start
            # Complete CSR readback; each block is compared without assembling
            # a second global expected matrix. No sample-based PASS.
            predicted=psutil.Process().memory_info().rss+int(m.DNumNZs)*32+int(m.NumConstrs)*24
            actual=m.getA().tocsr() if predicted<3.7*1024**3 else None
            if actual is not None:actual.sort_indices()
            readback_mode='EVERY_ROW_AT_INSERTION_PLUS_WHOLE_CSR' if actual is not None else 'EVERY_ROW_AT_INSERTION_PLUS_FINAL_COUNTS_RHS_SENSE_DOMAIN'
            guard(start)
            def compare(C,first):
                if actual is not None:
                    D=actual[first:first+C.shape[0],:C.shape[1]]-C;D.eliminate_zeros();assert D.nnz==0
                    assert actual[first:first+C.shape[0],C.shape[1]:].nnz==0
                else:
                    # Every row was exhaustively read back from its MConstr
                    # handle at insertion. Later code only appends columns
                    # and rows; no setAttr/chgCoeff, optimize or presolve.
                    assert measured['rows']==base_count['rows']+sum(b['rows'] for b in blocks)
                    assert measured['nonzeros']==base_count['nonzeros']+sum(b['nonzeros'] for b in blocks)
            B=sp.load_npz(RUN/'mobility/SELECTED.npz')
            compare(B,0)
            rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'))
            assert np.array_equal(rhs[:len(d['rhs'])],d['rhs']) and np.array_equal(sense[:len(d['sense'])],d['sense'])
            for b in blocks:
                C=sp.load_npz(b['expected']['path']);first=b['first_native_row'];n=b['rows']
                compare(C,first)
                with np.load(b['map']['path']) as z:
                    assert np.array_equal(rhs[first:first+n],z['rhs']) and np.array_equal(sense[first:first+n],z['sense'])
            lower=list(d['lower']);upper=list(d['upper']);types=list(d['types'])
            for t in range(96):
                with np.load(PACK/f'{t:02d}'/'DOMAIN.npz') as z:
                    keep=maps[t]>=0;lower.extend(z['lower'][keep]);upper.extend(z['upper'][keep]);types.extend(z['types'][keep])
            assert np.array_equal(m.getAttr('LB'),lower) and np.array_equal(m.getAttr('UB'),upper)
            assert np.array_equal(m.getAttr('VType'),types)
            assert np.array_equal(m.getAttr('Obj'),np.r_[d['objective'],np.zeros(m.NumVars-len(d['objective']))])
            assert m.ObjCon==float(d['constant'])
            # Matrix is complete. Save before handoff so source algorithms can
            # consume a static CSR case, not a restricted master or row oracle.
            if actual is not None:sp.save_npz(nativefolder/'COMPLETE_A.npz',actual)
            # All actual metadata above is read back while Native is live.
            # Persist large name axes only AFTER freeing the Native model.
            export=dict(lower=np.asarray(lower),upper=np.asarray(upper),types=np.asarray(types),rhs=rhs,sense=sense,
                objective=np.asarray(m.getAttr('Obj')),constant=np.asarray(m.ObjCon))
            report=dict(PASS=True,complete_static_M1_Native0_PASS=True,model=measured,
                build_seconds=built,all_retained_rows_materialized_before_solver=True,
                full_native_matrix_RHS_sense_bounds_types_objective_readback_PASS=True,
                original_static_presolve=record(OUT/'ORIGINAL_STATIC_PRESOLVE_MESS8.json'),
                static_screen=record(OUT/'IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json'),
                blocks=blocks,base_model=base_count,Native_optimize_calls=0,denied_attempts=denied,
                grid_row_generation=False,global_LB=None,global_UB=None,global_gap=None,
                fixed_B0_M1_only=True,A1_A2_M2_Native0_PASS=False,
                independent_original_FULL_equivalence_pending=True)
            report['native_readback_mode']=readback_mode
            report['native_domain_names_encoding']='ASCII bytes; decode before source case binding'
    except BaseException as exc:
        import traceback
        report=dict(PASS=False,complete_static_M1_Native0_PASS=False,error=repr(exc),traceback=traceback.format_exc(),
            completed_grid_slots=len(blocks),model=stats(m) if m is not None else None,blocks=blocks,
            measured_partial_never_called_FULL=True,Native_optimize_calls=0,grid_row_generation=False)
    finally:
        done.set();th.join(1)
        if m is not None:m.dispose()
    if report.get('PASS') and actual is None:
        # Every coefficient above has already been compared to its actual
        # Native row. Assemble the identical static CSR only after releasing
        # the Native model, avoiding two full in-memory representations.
        C0=sp.load_npz(RUN/'mobility/SELECTED.npz');n=report['model']['variables']
        parts=[sp.hstack([C0,sp.csr_matrix((C0.shape[0],n-C0.shape[1]))],format='csr')]
        for b in blocks:
            C=sp.load_npz(b['expected']['path'])
            parts.append(sp.hstack([C,sp.csr_matrix((C.shape[0],n-C.shape[1]))],format='csr'))
            guard(start)
        actual=sp.vstack(parts,format='csr');guard(start)
        sp.save_npz(RUN/'native/COMPLETE_A.npz',actual)
    if report.get('PASS'):
        # Variable names were checked at every Native addMVar. Row identity
        # maps contain every original index; these are the declared Native
        # names, with no additional semantic row or variable introduced.
        n=report['model']['variables'];nr=report['model']['rows']
        width=max(len(str(x)) for x in d['names'])
        for t in range(96):
            with np.load(PACK/f'{t:02d}'/'DOMAIN.npz') as z:width=max(width,z['names'].dtype.itemsize//4)
        names=np.empty(n,dtype=f'S{width}');names[:len(d['names'])]=d['names'].astype('S')
        rownames=np.empty(nr,dtype='S64');count=report['base_model']['rows']
        rownames[:count]=np.array([f'original_static_mobility[{i}]' for i in range(count)],dtype='S64')
        for t,b in enumerate(blocks):
            with np.load(PACK/f'{t:02d}'/'DOMAIN.npz') as z:
                mask=maps[t]>=0;target=maps[t][mask]
                names[target]=np.char.replace(z['names'][mask].astype(str),'_00[',f'_{t:02d}[').astype('S')
            first=b['first_native_row'];count=b['rows']
            rownames[first:first+count]=np.array([f'complete_original_grid_{t:02d}[{i}]' for i in range(count)],dtype='S64')
            guard(start)
        np.savez_compressed(RUN/'native/COMPLETE_DOMAIN.npz',names=names,row_names=rownames,**export)
    measured_peak=getattr(psutil.Process().memory_info(),'peak_wset',peak[0])
    report.update(wall_seconds=time.perf_counter()-start,peak_RSS_bytes=max(peak[0],measured_peak),resources=res,
        protection_limit_bytes=4*1024**3,official_campaign_executed=False)
    put('IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json',report)
    print('COMPLETE STATIC NATIVE0',report['PASS'],report.get('model'),report.get('error'),flush=True)

if __name__=='__main__':build()
