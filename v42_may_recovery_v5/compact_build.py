"""Reusable exact LP hybrid rebuild, retaining the full original reference."""
from dataclasses import replace
from collections import defaultdict
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_phase1.backend import assemble_original
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.active import option_from_json
from v42_a_stage_early.candidate import point_for_option,exact_coupling
from v42_a_stage_compact_rowgen.prepare import shift
from v42_a_stage_compact_rowgen.equivalence import verify,role,mapping
from v42_a_stage_compact_rowgen.kernel import perspective
from v42_a_stage_compact_rowgen.projection import exact_replay

def partition(s,metas,grows):
    owners=np.full(s.matrix.shape[1],-1,dtype=int);keys=sorted(metas)
    for k,key in enumerate(keys):m=metas[key];owners[m['offset']:m['offset']+m['width']]=k
    owned={int(j):keys[int(k)] for j,k in enumerate(owners) if k>=0}
    local={key:[] for key in keys}
    for i in range(len(grows),s.matrix.shape[0]):
        a,b=s.matrix.indptr[i:i+2]
        if a!=b:
            k=int(owners[s.matrix.indices[a]])
            if k<0 or np.any(owners[s.matrix.indices[a:b]]!=k):raise ValueError('NONSEPARABLE_LOCAL_CLASS_ROW')
            local[keys[k]].append(i)
    return {k:tuple(v) for k,v in local.items()},owned

def build(base,grows,n,axes,data,domains,ledger,candidates):
    reference,rdesc,_,rlrows,rowned,_=assemble_original(base,grows,n,axes,data)
    byclass=defaultdict(list)
    for c in candidates:byclass[c['class_id']].append(c)
    ids={k:[] for k in data[7]['classes']}
    for j,owner in rowned.items():
        ids[owner].append(j)
    ids={k:sorted(v) for k,v in ids.items()}
    parts=[];global_parts=[base.matrix[list(grows),:n].tocsr()];lower=[];upper=[];senses=[];rhs=[];metas={};proofs=[];offset=n;descriptors=[]
    for key,members in sorted(data[7]['classes'].items()):
        N=len(members);uid=members[0];snap,B,const,units=native_block(data,key,data[5][uid],tuple(axes),averaged=True)
        cols=ids[key];first=cols[0] if cols else n
        original=replace(reference,matrix=reference.matrix[list(rlrows[key])][:,cols].tocsr(),lower=reference.lower[cols],upper=reference.upper[cols],
            senses=reference.senses[list(rlrows[key])],rhs=reference.rhs[list(rlrows[key])],vtypes=np.full(len(cols),'C'),objectives=(Objective('local_price',(),0),))
        runits=[shift(u,-first) for u in rdesc['units'] if u['uid'] in members]
        proofs.append(dict(class_id=key,**verify(original,reference.matrix[list(axes.values())][:,cols],runits,snap,B,units,N)))
        points=[];cs=byclass[key]
        for c in cs:
            o=option_from_json(c['option']) if isinstance(c['option'],dict) else c['option']
            p=point_for_option(dict(snapshot=snap,B=B,units=units,graph=data[5][uid]),data[1][uid],data[3],o,N)
            if not exact_replay(snap,p)['PASS'] or exact_coupling(B,p)!={int(i):Fraction(v) for i,v in c['coupling']}:raise ValueError('ADMITTED_COLUMN_EXACT_RECONSTRUCTION_FAIL')
            points.append(p)
        meta=dict(class_id=key,N=N,offset=offset,kernel_columns=snap.matrix.shape[1],points=points,units=units,
            reference_columns=cols,reference_units=runits,candidates=cs,folded_constants=const)
        if points:snap,B,extra=perspective(snap,B,points,N);meta.update(extra)
        meta['width']=snap.matrix.shape[1];metas[key]=meta;coo=B.tocoo()
        global_parts.append(sp.csr_matrix((coo.data,([list(axes.values())[i] for i in coo.row],coo.col)),shape=(len(grows),snap.matrix.shape[1])))
        parts.append(snap.matrix);lower.extend(snap.lower);upper.extend(snap.upper);senses.extend(snap.senses);rhs.extend(snap.rhs)
        descriptors.extend(shift(u,offset) for u in units);offset+=meta['width']
    local=sp.block_diag(parts,format='csr')
    A=sp.vstack((sp.hstack(global_parts,format='csr'),sp.hstack((sp.csr_matrix((local.shape[0],n)),local),format='csr')),format='csr')
    objectives=[base.objective('rho')]
    for name in ('migration_count','shift_magnitude','prestart_relocation'):
        terms=[];constant=Fraction(0)
        for u in descriptors:
            job=data[1][u['uid']]
            for k,e in u['v']['q' if name=='migration_count' else 'y'].items():
                c=1 if name=='migration_count' else abs(k[1]-job.reference_start) if name=='shift_magnitude' else int(k[0]!=job.reference_site)
                if not c:continue
                if e[0]=='v':terms.append((int(e[1]),Fraction(c)))
                elif e[0]=='e':constant+=Fraction(float(e[1]))*c;terms.extend((int(j),Fraction(float(a))*c) for j,a in zip(e[2],e[3]))
                else:constant+=Fraction(float(e[1]))*c
        for key,m in metas.items():
            job=data[1][data[7]['classes'][key][0]]
            for j,candidate in zip(m.get('compact_path_columns',()),m['candidates']):
                o=option_from_json(candidate['option']) if isinstance(candidate['option'],dict) else candidate['option']
                c=int(o.migrated) if name=='migration_count' else abs(o.start-job.reference_start) if name=='shift_magnitude' else int(o.initial_site!=job.reference_site)
                if c:terms.append((m['offset']+j,Fraction(c)))
        objectives.append(Objective(name,tuple(terms),constant))
    compact=LinearSnapshot(A,np.r_[base.lower[:n],lower],np.r_[base.upper[:n],upper],np.r_[base.senses[list(grows)],senses],np.r_[base.rhs[list(grows)],rhs],
        np.full(A.shape[1],'C'),tuple(objectives)).require()
    return dict(compact=compact,reference=reference,reference_descriptor=rdesc,data=data,domains=domains,ledger=ledger,
        metas=metas,n=n,grows=grows,axes=axes,projection_proofs=proofs)

def compact_inverse(state,expanded):
    x=np.zeros(state['compact'].matrix.shape[1]);x[:state['n']]=expanded[:state['n']]
    for m in state['metas'].values():
        fold,owners=mapping(m['reference_units'],m['units'],len(m['reference_columns']))
        sums=defaultdict(Fraction);values={}
        for j,t in fold.items():
            v=Fraction(float(expanded[m['reference_columns'][j]]))
            if owners[j][0]=='OPT' and m['N']>1:sums[t]+=v
            elif t in values and values[t]!=v:raise ValueError('INCONSISTENT_UNCHANGED_HISTOGRAM_INVERSE')
            else:values[t]=v
        for t,v in {**values,**sums}.items():x[m['offset']+t]=float(v)
        if m['points']:x[m['offset']+m['residual_mass_column']]=m['N']
    return x
