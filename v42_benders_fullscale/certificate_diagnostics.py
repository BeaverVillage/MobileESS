"""Read-only exact residual census after the frozen experiment has terminated."""
from fractions import Fraction as F
import gzip,json,math
import numpy as np
from scipy import sparse
from .common import *

def q(v):return F.from_float(float(v))

def run():
    assert (OUT/'FINAL_FLAGS.json').exists(),'NO_HEAVY_DIAGNOSTIC_DURING_PRIMARY_SOLVE'
    summaries=[];unsupported_rows=[]
    for receipt_path in sorted(OUT.rglob('RECOURSE_*_RAW_RECEIPT.json')):
        receipt=json.loads(receipt_path.read_text());persist=receipt['persistence']
        with gzip.open(persist['journal'],'rt') as f:raw=json.loads(list(f)[persist['record']-1])
        if raw['multipliers'] is None:
            summaries.append(dict(path=receipt_path.relative_to(ROOT).as_posix(),status=raw['status'],multiplier_available=False));continue
        with np.load(raw['axis_npz']) as z:
            lower=z['lower'];upper=z['upper'];yi=z['yi'];names=z['original_names'][yi];senses=z['row_senses'];weights=z['weights']
            width=len(lower)+len(z['auxiliary_source_rows'])
            A=sparse.csr_matrix((z['matrix_data'],z['matrix_indices'],z['matrix_indptr']),shape=(len(senses),width))
        w=np.asarray(raw['multipliers']);coo=A.tocoo();products={}
        # Independent COO rational products; do not import generation/product helpers.
        for i,j,value in zip(coo.row,coo.col,coo.data):
            if w[i]:products[int(j)]=products.get(int(j),F(0))+q(w[i])*q(value)
        if raw['status']==3:residual={j:v for j,v in products.items() if j<len(lower) and v}
        else:
            residual={j:-v for j,v in products.items() if j<len(lower) and v}
            if not raw['phase1'] and receipt_path.parent.name in ['FULL_M1_CANARY','PRODUCTION_M1']:
                rho=list(names).index('rho_max');residual[rho]=residual.get(rho,F(0))+F(1)
                if not residual[rho]:del residual[rho]
        unsupported=[];free=[];finite_support=F(0)
        for j,v in residual.items():
            if math.isinf(lower[j]) and math.isinf(upper[j]):free.append(abs(float(v)))
            bound=lower[j] if v>0 else upper[j]
            if not math.isfinite(bound):
                unsupported.append(j);unsupported_rows.append(dict(receipt=receipt_path.name,source=receipt_path.parent.relative_to(OUT).as_posix(),
                    recourse_column=j,original_column=int(yi[j]),name=str(names[j]),exact_residual=str(v),
                    residual_float=float(v),lower=str(float(lower[j])),upper=str(float(upper[j])),required_bound='LB' if v>0 else 'UB'))
            else:finite_support+=v*q(bound)
        sign=1 if raw['status']==3 else -1
        sign_bad=int(np.sum(w[senses=='<']*sign<0)+np.sum(w[senses=='>']*sign>0))
        row=q(0)
        for wi,bi in zip(w,raw['solver_rhs']):
            if wi:row+=q(wi)*q(bi)
        auxiliary_negative=[];aux_index=len(lower)
        if raw['phase1']:
            for i,sense in enumerate(senses):
                if sense in ['<','=']:
                    v=q(weights[i])-products.get(aux_index,F(0));aux_index+=1
                    if v<0:auxiliary_negative.append(float(v))
                if sense in ['>','=']:
                    v=q(weights[i])-products.get(aux_index,F(0));aux_index+=1
                    if v<0:auxiliary_negative.append(float(v))
        reduced_cost_residual=None
        if raw['reduced_costs'] is not None:
            reduced_cost_residual=max([abs(float(residual.get(j,F(0)))-v) for j,v in enumerate(raw['reduced_costs'][:len(lower)])]+[0.])
        summaries.append(dict(path=receipt_path.relative_to(ROOT).as_posix(),status=raw['status'],multiplier_available=True,
            raw_vector_sha256=raw['vector_sha256'],multiplier_min=raw['multiplier_min'],multiplier_max=raw['multiplier_max'],
            sign_distribution=raw['sign_distribution'],native_sense_sign_violations=sign_bad,
            weighted_column_max=max([abs(float(v)) for v in residual.values()]+[0.]),
            truly_free_residual_max=max(free,default=0.),dual_reduced_cost_residual=reduced_cost_residual,
            unsupported_bound_support_columns=len(unsupported),
            required_support_finite=not unsupported,exact_supported_partial_sum=str(finite_support),
            full_bound_support=None if unsupported else str(finite_support),native_FarkasProof=raw['farkas_proof'],
            reconstructed_native_proof=None if unsupported or raw['status']!=3 else float(finite_support-row),
            PhaseI_optimum=raw['objective'] if raw['phase1'] else None,
            PhaseI_artificial_negative_reduced_costs=len(auxiliary_negative),
            PhaseI_artificial_min_reduced_cost=min(auxiliary_negative,default=0.),Kappa=raw['Kappa'],
            no_cut_generated_by_diagnostic=True,clamp=False,flip=False,tiny_coefficient_deletion=False))
        print(receipt_path.name,'INDEPENDENT RESIDUAL AUDIT',len(unsupported),'unsupported columns',flush=True)
        del A,coo,products
    dump('EXACT_RESIDUAL_DIAGNOSTICS.json',dict(optimization_calls=0,independent_COO_rational_arithmetic=True,
        summaries=summaries,scientific_acceptance=False,post_result_engine_changes=0))
    table('REJECTED_SUPPORT_TERMS.csv',unsupported_rows,['receipt','source','recourse_column','original_column','name','exact_residual','residual_float','lower','upper','required_bound'])

if __name__=='__main__':run()
