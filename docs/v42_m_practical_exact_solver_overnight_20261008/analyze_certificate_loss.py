"""Attribute saved exact-certificate loss; floating diagnostics, no solver."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
import json, csv, hashlib
from pathlib import Path
from fractions import Fraction
from collections import defaultdict
import numpy as np
from scipy import sparse
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run():
    matrix=ROOT/'docs/v42_m1_ultracompact_exact_20261006/C3A_A.npz'
    data=matrix.with_name('C3A_DATA.npz')
    assert sha(matrix)=='45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8'
    assert sha(data)=='20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467'
    A=sparse.load_npz(matrix).tocsr()
    with np.load(data) as z:d={k:z[k] for k in z.files}
    summaries=[];families=[];top=[]
    for p in sorted((OUT/'external_production/external_nodes').glob('*/RESULT.json')):
        result=read(p)
        proof=p.with_name('LP_POINT_PROOF.npz')
        if result['LP_status']!='OPTIMAL' or not proof.exists():continue
        with np.load(proof) as z:
            x=z['x'];pi=z['clipped_Pi'];r=z['exact_residual_display'];terms=z['exact_bound_terms_display']
        lower=d['lower'].copy();upper=d['upper'].copy()
        for j,v in result['fixings']:lower[j]=upper[j]=v
        at=np.where(r>=0,lower,upper)
        col=r*(x-at)
        rows=pi*(A@x-d['rhs'])
        groups=defaultdict(lambda:dict(count=0,loss=0.,max_abs_residual=0.,fixed=0))
        for j,name in enumerate(d['names']):
            group=groups[str(name).split('[')[0]]
            group['count']+=1;group['loss']+=float(col[j])
            group['max_abs_residual']=max(group['max_abs_residual'],abs(float(r[j])))
            group['fixed']+=int(lower[j]==upper[j])
        for family,stats in groups.items():families.append(dict(node_id=result['node_id'],family=family,**stats))
        for j in np.argsort(-col)[:25]:top.append(dict(node_id=result['node_id'],column=int(j),name=str(d['names'][j]),loss=float(col[j]),exact_residual_display=float(r[j]),raw_x=float(x[j]),lower=float(lower[j]),upper=float(upper[j]),is_original_binary=d['types'][j]=='B'))
        exact=float(Fraction(result['certified_LB']))
        loss=result['LP_objective']-exact
        attributed=float(col.sum()+rows.sum())
        summaries.append(dict(node_id=result['node_id'],BarConvTol=result.get('parameters',{}).get('BarConvTol'),Runtime=result['Runtime'],LP_objective=result['LP_objective'],exact_certificate_display=exact,total_certificate_loss=loss,column_minimization_loss=float(col.sum()),row_complementarity_loss=float(rows.sum()),float_decomposition_residual=loss-attributed,max_exact_stationarity_residual_display=float(abs(r).max()),nonzero_exact_stationarity_residual_display=int(np.count_nonzero(r)),raw_LP_replay=result['LP_primal_replay'],proof_SHA256=sha(proof)))
    for name,records in [('CERTIFICATE_LOSS_NODES.csv',summaries),('CERTIFICATE_LOSS_FAMILIES.csv',families),('CERTIFICATE_LOSS_TOP_COLUMNS.csv',top)]:
        with (OUT/name).open('w',encoding='utf-8',newline='') as f:
            if records:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    report=dict(optimize_calls=0,diagnostic_only=True,arithmetic='Stored exact dyadic residuals rounded for float attribution; does not create or replace any LB certificate',identity=dict(A_SHA256=sha(matrix),DATA_SHA256=sha(data)),nodes=summaries,top_aggregate_families=sorted(({**r} for r in families),key=lambda r:-r['loss'])[:20],no_bound_or_model_modified=True)
    (OUT/'CERTIFICATE_LOSS_ATTRIBUTION.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(nodes=len(summaries),top=report['top_aggregate_families'][:5],max_float_decomposition_residual=max((abs(r['float_decomposition_residual']) for r in summaries),default=0))))
if __name__=='__main__':run()
