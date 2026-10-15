"""Recover a Native0 sparse FULL capture without constructing another model."""
from collections import defaultdict
from fractions import Fraction
import gzip
import json
from pathlib import Path
import pickle

import numpy as np

from .a_engine import authorized_data,digest
from .m_engine import _write,file_record,matrix_sha


def _terms(expressions):
    terms=defaultdict(Fraction);constant=Fraction(0)
    for e in expressions:
        if e[0]=='v':terms[int(e[1])]+=1
        elif e[0]=='c':constant+=Fraction(float(e[1]))
        else:
            constant+=Fraction(float(e[1]))
            for j,a in zip(e[2],e[3]):terms[int(j)]+=Fraction(float(a))
    return {j:a for j,a in terms.items() if a},constant


def recover_runtime_bindings(snapshot,descriptor,data):
    """Verify the original sorted finish-group creation order against each row."""
    groups=defaultdict(list);representatives={};owned=set()
    for unit in descriptor['units']:
        for items in unit['v'].values():
            for e in items.values():
                if e[0]=='v':owned.add(int(e[1]))
                elif e[0]=='e':owned.update(map(int,e[2]))
        for family in ('f0','f1'):
            if unit['optional'] and family=='f0':continue
            for (site,end),e in unit['v'][family].items():
                key=unit['class_key'],site,end
                groups[key].append(e);representatives[key]=unit['uid']
    prefix=min(owned)
    auxiliaries=[j for j in range(prefix,snapshot.matrix.shape[1]) if j not in owned]
    if len(auxiliaries)!=len(groups):raise ValueError('TABLE_V_DW_RECOVER_RUNTIME_COMPLETE_AUX_AXIS_REQUIRED')
    bindings={};rows=[];first_equality=snapshot.matrix.shape[0]-len(auxiliaries)
    for offset,(j,key) in enumerate(zip(auxiliaries,sorted(groups))):
        terms,constant=_terms(groups[key]);wanted={k:-a for k,a in terms.items()};wanted[j]=Fraction(1)
        row=first_equality+offset;a,b=snapshot.matrix.indptr[row:row+2]
        actual={int(k):Fraction(float(v)) for k,v in zip(snapshot.matrix.indices[a:b],snapshot.matrix.data[a:b])}
        if actual!=wanted or snapshot.senses[row]!='=' or Fraction(float(snapshot.rhs[row]))!=constant:
            raise ValueError('TABLE_V_DW_RECOVER_RUNTIME_SORTED_EQUALITY_DRIFT')
        if snapshot.lower[j]!=0 or snapshot.upper[j]!=len(data[7]['classes'][key[0]]):
            raise ValueError('TABLE_V_DW_RECOVER_RUNTIME_ORIGINAL_BOX_DRIFT')
        bindings[key]=j;rows.append(row)
    return dict(Runtime_finish_counts=bindings,_runtime_equality_rows=rows),representatives


def recover_coupling_rows(snapshot,descriptor,data,runtime,representatives):
    """Read back the original root.native resource rows and all coefficients.

    Their source creation order precedes grid/local construction. Reconstruct
    the unchanged native binder's expressions; reject any row/RHS/coefficient
    mismatch. No inferred name or positional assertion substitutes for replay.
    """
    from v42_sparse.runtime import coefficient_vector
    from v42_final.reserve import risk_exposure
    bundle,jobs,_,resources,raw,graphs,_,_=data
    axes={};expected={};constants=defaultdict(float);right={};senses={};index=0
    for site in resources.capacities:
        for key in (key for key in descriptor['known'] if key[0]==site):
            axis=('GPU',key);axes[axis]=index;index+=1
            expected[axis]={int(descriptor['known'][key][1]):1.};right[axis]=resources.fixed_gpu.get(key,0);senses[axis]='='
        for key in (key for key in descriptor['risk'] if key[0]==site):
            axis=('Runtime',key);axes[axis]=index;index+=1
            expected[axis]={int(descriptor['risk'][key][1]):1.};right[axis]=0.;senses[axis]='='
    for key,value in resources.wan_capacities.items():
        axis=('WAN',key);axes[axis]=index;index+=1
        expected[axis]={};right[axis]=(value-resources.fixed_wan.get(key,0))/2.**20;senses[axis]='<'
    for t in range(resources.control_end):
        axis=('ACTIVE',t);axes[axis]=index;index+=1
        expected[axis]={};right[axis]=resources.max_active_transfers-resources.fixed_transfers.get(t,0);senses[axis]='<'
    def attach(axis,e,coefficient):
        coefficient=float(coefficient)
        if e[0]=='v':expected[axis][int(e[1])]=coefficient
        elif e[0]=='e':
            for j,a in zip(e[2],e[3]):expected[axis][int(j)]=coefficient*float(a)
            constants[axis]+=coefficient*float(e[1])
        else:constants[axis]+=coefficient*float(e[1])
    for uid,row in raw.items():
        if uid not in jobs:
            for key,x in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),
                    row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():
                right['Runtime',key]+=bundle['runtime_reserve_gamma']*x
    for unit in descriptor['units']:
        uid=unit['uid'];job=jobs[uid];v=unit['v'];graph=graphs[uid]
        for family in ('r0','r1'):
            for key,e in v[family].items():attach(('GPU',key),e,-job.gpu)
        if 'pair' in v:
            for key,e in v['link_bytes'].items():attach(('WAN',key),e,1./2.**20)
            for t,e in v['wan_active'].items():attach(('ACTIVE',t),e,1.)
        else:
            for key,e in v['w'].items():
                tr=graph.transfers[key]
                for link,t,value in tr.wan:attach(('WAN',(link,t)),e,value/2.**20)
                for t in range(key[2],tr.end):attach(('ACTIVE',t),e,1.)
    for key,j in runtime['Runtime_finish_counts'].items():
        uid=representatives[key];_,site,end=key
        for target,value in coefficient_vector(jobs[uid],raw[uid],site,end,bundle):
            expected['Runtime',target][j]=-float(value)
    for axis,row in axes.items():
        a,b=snapshot.matrix.indptr[row:row+2]
        actual=dict(zip(map(int,snapshot.matrix.indices[a:b]),snapshot.matrix.data[a:b]))
        want={j:value for j,value in expected[axis].items() if value}
        if actual!=want or snapshot.senses[row]!=senses[axis] or snapshot.rhs[row]!=right[axis]-constants[axis]:
            raise ValueError('TABLE_V_DW_RECOVER_ORIGINAL_RESOURCE_ROW_DRIFT:'+str(axis))
    return axes


def recover_sparse_full_capture(context,original_snapshot,descriptor_path,identity_path,output):
    """Recover an interrupted capture using saved exact arrays and fresh domains."""
    from .table_v_dw import project_runtime_auxiliaries,audit_source_domain
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_DW_RECOVER_FRESH_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    audit=audit_source_domain(context);_write(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json',audit)
    identity=json.loads(Path(identity_path).read_text(encoding='utf8'))
    case=context['make_a_case']('A1',folder=output/'UNBUILT_FULL',arm='B1')
    if identity['source_identity']!=context['manifest']['identity'] or identity['case_sha']!=case.case_sha:
        raise ValueError('TABLE_V_DW_RECOVER_SAME_SOURCE_CASE_REQUIRED')
    with gzip.open(original_snapshot,'rb') as stream:original=pickle.load(stream)
    with gzip.open(descriptor_path,'rb') as stream:descriptor=pickle.load(stream)
    if matrix_sha(original.matrix)!=identity['native_binding']['matrix_sha']:
        raise ValueError('TABLE_V_DW_RECOVER_SAVED_MATRIX_BINDING_DRIFT')
    objective=original.objective('rho');coefficients=np.zeros(original.matrix.shape[1])
    for j,a in objective.coefficients().items():coefficients[j]=float(a)
    objective_sha=digest(dict(coefficients=list(coefficients),constant=float(objective.constant),sense=1))
    if objective_sha!=identity['objective_sha']:raise ValueError('TABLE_V_DW_RECOVER_ORIGINAL_OBJECTIVE_DRIFT')
    data,_=authorized_data(case)
    bindings,representatives=recover_runtime_bindings(original,descriptor,data)
    axes=recover_coupling_rows(original,descriptor,data,bindings,representatives)
    raw_packet=dict(data=data,original=original,original_descriptor=descriptor,coupling_rows=axes,
        original_runtime_bindings=bindings['Runtime_finish_counts'],runtime_equality_rows=bindings['_runtime_equality_rows'],
        case_sha=case.case_sha,objective_sha=objective_sha,native_binding=identity['native_binding'],
        source_identity=context['manifest']['identity'],input_sha=context['input_audit']['a_input_sha'])
    raw_path=output/'ORIGINAL_FULL_CAPTURE.pkl.gz'
    with gzip.open(raw_path,'xb',compresslevel=1) as stream:pickle.dump(raw_packet,stream,protocol=5)
    _write(output/'ORIGINAL_FULL_CAPTURE_RECEIPT.json',dict(PASS=True,capture=file_record(raw_path),Native_calls=0,
        Native_model_builds=0,original_snapshot=file_record(original_snapshot),original_descriptor=file_record(descriptor_path)))
    projected,translated,proof=project_runtime_auxiliaries(None,original,bindings,descriptor,data)
    packet=dict(data=data,original=original,projected=projected,descriptor=translated,runtime_projection=proof,
        coupling_rows=axes,case_sha=case.case_sha,objective_sha=objective_sha,
        native_binding=identity['native_binding'],source_identity=context['manifest']['identity'],
        input_sha=context['input_audit']['a_input_sha'])
    path=output/'FULL_DW_CAPTURE.pkl.gz'
    with gzip.open(path,'xb',compresslevel=1) as stream:pickle.dump(packet,stream,protocol=5)
    _write(output/'RECOVERY_RESULT.json',dict(PASS=True,capture=file_record(path),Native_calls=0,Native_model_builds=0,
        source_domain=audit,eliminated_auxiliaries=proof['eliminated_auxiliaries'],
        preserved_constant_Runtime_auxiliaries=proof['preserved_constant_Runtime_auxiliaries']))
    return file_record(path)
