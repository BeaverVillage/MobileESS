"""Original active native matrices and deterministic feasible local witnesses."""
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_job_capability import Option
from v42_root.factor import mapping
from v42_a_stage_domain_v2.lexstage import Objective,LinearSnapshot
from v42_a_stage_domain_v2.active import _ledger
from .producer import native_block
from .core import primal_replay


def evaluate(e,point):
    return float(point[e[1]]) if e[0]=='v' else float(e[1]+sum(c*point[j] for j,c in zip(e[2],e[3]))) if e[0]=='e' else float(e[1])


def constructed_point(snapshot,descriptor,data,global_variables,hard_rows):
    x=np.zeros(snapshot.matrix.shape[1])
    x[:global_variables]=np.maximum(np.minimum(0.,snapshot.upper[:global_variables]),snapshot.lower[:global_variables])
    if not np.all(np.isfinite(x)):raise ValueError('CONSTRUCTED_GLOBAL_BOX_POINT_INVALID')
    for unit in descriptor['units']:
        uid=unit['uid'];job=data[1][uid];graph=data[5][uid]
        if unit['optional']:continue
        starts=[(s,k) for k,s in graph.events['y'] if (k,s+job.service_slots) in graph.events['f0']]
        if not starts and graph.fixed:starts=[(graph.fixed.start,graph.fixed.initial_site)]
        if not starts:raise ValueError('PHASE1_IMPLEMENTATION_INVALID_NO_LOCAL_STAY')
        start,site=min(starts)
        option=Option(start,site,((site,start,start+job.service_slots),))
        values=mapping(job,graph,data[3],option)
        count=len(unit['members']) if unit['stay_count'] else 1
        for family,items in unit['v'].items():
            for key,e in items.items():
                want=count*values.get(family,{}).get(key,0.)
                if e[0]=='v':x[e[1]]=want
    local=replace(snapshot,matrix=snapshot.matrix[list(hard_rows)].tocsr(),
        senses=snapshot.senses[list(hard_rows)],rhs=snapshot.rhs[list(hard_rows)])
    replay=primal_replay(local,x)
    if not replay['PASS']:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_CONSTRUCTED_LOCAL_REPLAY:'+str(replay))
    return x,replay


def artificial_point(master,original_point):
    n=master.original.matrix.shape[1]
    x=np.r_[original_point,np.zeros(len(master.artificial_rows))]
    residual=master.original.matrix@original_point-master.original.rhs
    for j,(row,sign) in enumerate(zip(master.artificial_rows,master.artificial_signs)):
        x[n+j]=max(0.,-residual[row]/sign)
    replay=primal_replay(master.snapshot,x)
    if not replay['PASS']:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_CONSTRUCTED_ELASTIC_POINT')
    return x,replay


def assemble_original(base,base_global_rows,global_variables,axes,data):
    """Global equations are copied; only exact native local support is rebuilt."""
    grows=list(base_global_rows);global_position={row:i for i,row in enumerate(grows)}
    matrices=[];couplings=[];lower=[];upper=[];senses=[];rhs=[];units=[];offset=global_variables
    global_parts=[base.matrix[grows,:global_variables].tocsr()]
    local_ranges={};owned={}
    for key,members in sorted(data[7]['classes'].items()):
        block,B,constant,encoded=native_block(data,key,data[5][members[0]],tuple(axes),averaged=False)
        coo=B.tocoo()
        expanded=sp.csr_matrix((coo.data,([global_position[list(axes.values())[i]] for i in coo.row],coo.col)),
            shape=(len(grows),block.matrix.shape[1]))
        global_parts.append(expanded)
        matrices.append(block.matrix);lower.extend(block.lower);upper.extend(block.upper)
        senses.extend(block.senses);rhs.extend(block.rhs)
        local_ranges[key]=(sum(m.shape[0] for m in matrices[:-1]),block.matrix.shape[0])
        for unit in encoded:
            v={}
            for family,items in unit['v'].items():
                v[family]={}
                for k,e in items.items():
                    v[family][k]=('v',int(e[1])+offset) if e[0]=='v' else ('e',e[1],np.asarray(e[2])+offset,e[3]) if e[0]=='e' else e
            units.append(dict(unit,v=v,members=members))
        for j in range(block.matrix.shape[1]):owned[offset+j]=key
        offset+=block.matrix.shape[1]
    localA=sp.block_diag(matrices,format='csr')
    A=sp.vstack((sp.hstack(global_parts,format='csr'),
        sp.hstack((sp.csr_matrix((localA.shape[0],global_variables)),localA),format='csr')),format='csr')
    objectives=[Objective('rho',base.objective('rho').terms,base.objective('rho').constant)]
    for name in ('migration_count','shift_magnitude','prestart_relocation'):
        terms=[];constant=Fraction(0)
        for unit in units:
            job=data[1][unit['uid']]
            family='q' if name=='migration_count' else 'y'
            for key,e in unit['v'][family].items():
                co=1 if name=='migration_count' else abs(key[1]-job.reference_start) if name=='shift_magnitude' else int(key[0]!=job.reference_site)
                if not co:continue
                if e[0]=='v':terms.append((e[1],Fraction(co)))
                elif e[0]=='e':
                    constant+=Fraction(float(e[1]))*co
                    terms.extend((int(j),Fraction(float(c))*co) for j,c in zip(e[2],e[3]))
                else:constant+=Fraction(float(e[1]))*co
        objectives.append(Objective(name,tuple(terms),constant))
    snapshot=LinearSnapshot(A,np.r_[base.lower[:global_variables],lower],np.r_[base.upper[:global_variables],upper],
        np.r_[base.senses[grows],senses],np.r_[base.rhs[grows],rhs],np.full(A.shape[1],'C'),tuple(objectives)).require()
    local_rows={key:tuple(range(len(grows)+first,len(grows)+first+count)) for key,(first,count) in local_ranges.items()}
    new_axes={key:global_position[value] for key,value in axes.items()}
    return snapshot,dict(units=units),tuple(range(len(grows))),local_rows,owned,new_axes


def update_graph(data,domains,key,graph):
    graphs=dict(data[5])
    for member in data[7]['classes'][key]:graphs[member]=graph
    new=(*data[:5],graphs,data[6],data[7])
    ledger=_ledger(new,domains,{key:{} for key in data[7]['classes']})
    return new,ledger


def project_local_point(source_units,source_point,target_units,target_columns):
    """Projection/reindexing is separate from the persisted raw solver point."""
    lookup={}
    for unit in source_units:
        role='STAY' if unit['stay_count'] else 'SUM' if unit['optional'] else 'SINGLE'
        for family,items in unit['v'].items():
            for key,e in items.items():lookup[role,family,key]=evaluate(e,source_point)
    point=np.zeros(target_columns)
    assigned=set()
    for unit in target_units:
        role='STAY' if unit['stay_count'] else 'SUM' if unit['optional'] else 'SINGLE'
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='v':
                    point[e[1]]=lookup.get((role,family,key),0.);assigned.add(e[1])
    # Byte-scaled link columns are encoded as one-term expressions. They
    # have no separate Var entry in the scientific descriptor.
    for unit in target_units:
        role='STAY' if unit['stay_count'] else 'SUM' if unit['optional'] else 'SINGLE'
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='e' and len(e[2])==1 and int(e[2][0]) not in assigned:
                    j=int(e[2][0]);point[j]=(lookup.get((role,family,key),0.)-e[1])/e[3][0];assigned.add(j)
    return point
