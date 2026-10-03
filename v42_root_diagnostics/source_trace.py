"""Source replay supplement; preserves the original frozen census trace."""
from .analytics import csvread
from .common import *
import re

def run():
    from v42_forensic.common import inputs
    from v42_bootstrap.grid import coefficients
    bundle,*_=inputs();cert,coeff=coefficients(bundle)
    traces=csvread('EXTREME_COEFFICIENT_SOURCE_TRACE.csv');rows=row_families('original')
    counts={f:np.flatnonzero(rows==f) for f in set(rows)}
    selected=[k for k,n in enumerate(coeff[0].branch_names) if n.lower().startswith('transformer.') and re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]',n.lower()) is None]
    for r in traces:
        f=r['row_family'];name=r['variable_name'];value=float(r['coefficient'])
        if f=='transformer_current':
            ordinal=int(np.searchsorted(counts[f],int(r['row'])));t,local=divmod(ordinal,len(selected));branch=selected[local];c=coeff[t]
            site=name.split('[',1)[1].rsplit(',',1)[0];control=('mess_p_kw' if r['variable_family']=='injection_P' else 'mess_q_kvar')+'['+site+']'
            q=list(c.control_names).index(control);expected=float(c.current_matrix[q,branch])
            r.update(source_function='add_compressed -> expr (transformer_current)',source_formula='current_matrix[control,branch]',source_recomputed_coefficient=expected,
                source_replay_absolute_difference=abs(value-expected),physical_meaning='Frozen Planning normalized transformer-current sensitivity to active/reactive MESS injection',
                physical_units='dimensionless transformer current loading per kW/kvar',why_small_or_large='Direct small entry of the frozen Planning current Jacobian. The source replay proves its origin; network coupling versus numerical derivative error is not distinguished by this task.')
        elif f.startswith('response_'):
            r['physical_units']='dimensionless line loading per kW/kvar' if 'correction' in f else 'kW or kvar per kW/kvar'
            r['source_function']='add_compressed -> response -> expr'
            r['why_small_or_large']='Explicit source subtraction current_matrix.T - active-face affine gradient produces this signed residual. No unsupported claim that it is harmless floating-point noise.' if 'correction' in f else 'Frozen affine response matrix entry.'
        elif f.startswith('voltage_'):
            r['source_function']='add_compressed -> expr (voltage band)'
            r['why_small_or_large']='Small frozen Planning voltage-Jacobian entry; its generation error versus electrical coupling is unresolved. Magnitude alone does not authorize removal.'
        r['coefficient_source_file']='v42_may01/prepare.py'
        r['coefficient_source_function']='native_coefficients (read frozen certified Planning NPZ; no electrical regeneration)'
        r['planning_coefficients_sha256']=cert['outputs']['planning_coefficients']['sha256']
        r['source_file_sha256']=sha(ROOT/r['source_file'])
        r['magnitude_class']='tiny' if abs(value)<=1e-12 else 'large'
        if r['source_replay_absolute_difference']!='':assert float(r['source_replay_absolute_difference'])==0
    table('EXTREME_COEFFICIENT_SOURCE_TRACE_COMPLETE.csv',traces)
    dump('EXTREME_SOURCE_REPLAY_RECEIPT.json',dict(PASS=all(r['source_recomputed_coefficient']!='' and float(r['source_replay_absolute_difference'])==0 for r in traces),
        original_trace_preserved_sha256=sha(OUT/'EXTREME_COEFFICIENT_SOURCE_TRACE.csv'),complete_trace_sha256=sha(OUT/'EXTREME_COEFFICIENT_SOURCE_TRACE_COMPLETE.csv'),
        representative_entries=len(traces),all_replayed_entries_bit_equal=True,coefficients_deleted=0,
        scope='Representative extreme entries for every identified source family, both formulations. Exact source arithmetic replay is distinguished from unproved claims about underlying electrical/numerical smallness.',
        frozen_planning_coefficient_sha256=cert['outputs']['planning_coefficients']['sha256']))

if __name__=='__main__':run()
