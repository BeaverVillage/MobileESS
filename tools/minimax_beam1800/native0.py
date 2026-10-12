"""Independent source extraction and helper elimination; never optimizes."""
from fractions import Fraction as F
from scipy import sparse
import gc,numpy as np
from tools.minimax_beam1800.adapter import *
from tools.critical_grid_cg.verify import Geometry,canonical_data,original_row_sha

def template(case):
    folder=DOCS/'lp_template'
    with np.load(folder/'DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    physics={'connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin','no_simultaneous_charge',
        'no_simultaneous_discharge','PCS16','energy_balance','initial_SOC','terminal_SOC'}
    od=case.original_d;A=case.original_A.tocsr()
    rows=np.flatnonzero([str(n).split('[',1)[0] in physics for n in od['row_names']])
    cols=np.flatnonzero([str(n).split('[',1)[0] in {'Pch','Pdis','Q','SOC','charge_mode','rho_max'} for n in od['names']])
    arcs=np.flatnonzero(np.char.startswith(od['names'],'arc['))
    assert np.array_equal(rows,d['original_rows']) and np.array_equal(cols,d['columns']) and np.array_equal(arcs,d['arc_columns'])
    P=sparse.load_npz(folder/'PHYS_POWER_A.npz').tocsr();R=sparse.load_npz(folder/'PHYS_ARC_A.npz').tocsr()
    assert v.matrix_sha(P)==v.matrix_sha(A[rows][:,cols].tocsr())
    assert v.matrix_sha(R)==v.matrix_sha(A[rows][:,arcs].tocsr())
    for local,source,axis in [('names','names',cols),('lb','lower',cols),('ub','upper',cols),('c','objective',cols),
        ('senses','sense',rows),('rhs','rhs',rows),('row_names','row_names',rows),('arc_names','names',arcs)]:
        assert np.array_equal(d[local],od[source][axis])
    assert d['constant']==od['constant'] and not np.any(od['objective'][np.setdiff1d(np.arange(len(od['names'])),cols)])
    assert set(A[rows].indices)<=set(np.r_[cols,arcs])
    result=dict(PASS=True,independent_original_FULL_CSR_extraction=True,all_original_physical_rows_and_domains_exact=True,
        mode_relaxation_only=True,other_omitted_rows_are_relaxation=True,source_matrix=v.matrix_sha(A),
        source_domain=v.domain_sha(od),rows=len(rows),columns=len(cols),Native_optimize_calls=0,
        file_sha256={p.name:v.file_sha(p) for p in folder.glob('*.npz')})
    assert result['source_matrix']==v.FULL_MATRIX_SHA and result['source_domain']==v.FULL_DOMAIN_SHA
    write(folder/'INDEPENDENT_SOURCE_REEXTRACTION.json',result);return result

def grid(case,context):
    A=case.original_A.tocsr();d=canonical_data(case.original_d);geo=Geometry(A,d);receipts=[]
    for packet in context['rows']:
        row=packet['original_row'];rhs,constant,terms=geo.security(row)
        exact={str(d['names'][j]):str(value) for j,value in terms.items()}
        assert F(packet['rhs'])==rhs and {n:F(v) for n,v in packet['coeff'].items()}=={n:F(v) for n,v in exact.items()}
        assert packet['source_row_sha256']==original_row_sha(A,d,row)
        assert all(n=='rho_max' or n.split('[',1)[0] in ('Pch','Pdis','Q') for n in exact)
        receipts.append(dict(row=row,rhs_exact=str(rhs),eliminated_constant=str(constant),term_count=len(terms)))
    result=dict(PASS=True,independent_recursive_source_helper_elimination=True,rows=receipts,
        fixed_AIDC_forecast_RHS_preserved=True,source_FULL_matrix_SHA=v.matrix_sha(A),Native_optimize_calls=0)
    assert result['source_FULL_matrix_SHA']==v.FULL_MATRIX_SHA
    return result

def certificate(folder):
    """Offline reproduce exact weak-duality bound from native raw multipliers."""
    from tools.b2_root_lp_tightening.verify import exact_box_dual,downward
    cert=read(folder/'CONDITIONAL_BOUND_CERTIFICATE.json')
    if not cert['PASS']:return dict(PASS=True,certified=False,not_prunable=True)
    with np.load(folder/'LP_DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    with np.load(folder/'LP_DUAL_RAW.npz',allow_pickle=False) as z:pi=z['pi'].copy()
    A=sparse.load_npz(folder/'LP_A.npz').tocsr();bound,detail=exact_box_dual(A,d,pi)
    assert str(bound)==cert['exact_conditional_bound'] and downward(bound)==cert['Certified_LP_LB']
    assert read(folder/'NATIVE_READBACK.json')['PASS'] and read(folder/'INDEPENDENT_RELAXATION_NATIVE0.json')['PASS']
    result=dict(PASS=True,certified=True,exact_weak_duality_recomputed=True,Certified_LP_LB=downward(bound),
        LP_bound_is_Global_LB=False,verifier_Optimize_calls=0,native_raw_dual=record(folder/'LP_DUAL_RAW.npz'))
    write(folder/'OFFLINE_DUAL_CERTIFICATE.json',result);return result
