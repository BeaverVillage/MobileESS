"""Invoke original metadata/partition interfaces without solving any model."""
import inspect,textwrap,types
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from .static_common import *
from .static_pack import PACK
from .prestart_native import native_zero

def probe():
    init();checks=[]
    from v44.frozen.v43_mess.library import load
    with native_zero() as denied:
        modules=load();k=modules['table_v_k48']
        with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={f:z[f] for f in z.files}
        with np.load(PACK/'00/DOMAIN.npz') as z:vd={f:z[f] for f in z.files}
        with np.load(PACK/'00/ROWS.npz') as z:r={f:z[f] for f in z.files}
        A=sp.load_npz(PACK/'00/MATRIX.npz')[:,:len(md['names'])+len(vd['names'])]
        d=dict(names=np.r_[md['names'],vd['names']],lower=np.r_[md['lower'],vd['lower']],
            upper=np.r_[md['upper'],vd['upper']],types=np.r_[md['types'],vd['types']],
            rhs=r['rhs'],sense=r['sense'],row_names=r['local_names'],objective=np.r_[md['objective'],np.zeros(len(vd['names']))],constant=0.)
        try:
            geo=k.original_oracle.Geometry(A,d)
            row=next(i for i,n in enumerate(r['local_names']) if str(n).startswith('parent_line_thermal_face'))
            columns=np.r_[np.flatnonzero([str(n).split('[',1)[0] in ('Pch','Pdis','Q','SOC','charge_mode','arc') for n in d['names']]),np.flatnonzero(d['objective'])]
            k.exact_cut(A,d,row,columns,geo)
        except Exception as exc:checks.append(dict(interface='Original K48 Geometry/exact_cut on actual new Source-YY component',
            PASS=False,error=repr(exc),scope='Actual coefficient and original CSR names; single-slot admission probe, not96FULL K48',
            diagnosis='Scaled sparse helpers and IEEE8500 named axes require a certified exact representation adapter; bypassing Geometry would change the LB proof.'))
        else:checks.append(dict(interface='Original K48 Geometry/exact_cut',PASS=True,scope='single-slot only'))
        from .static_helper_view import helper_view
        shadow,sd,proof=helper_view(A,d,len(md['names']),0)
        geo=k.original_oracle.Geometry(shadow,sd)
        row=next(i for i,n in enumerate(r['local_names']) if str(n).startswith('parent_line_thermal_face'))
        columns=np.r_[np.flatnonzero([str(n).split('[',1)[0] in ('Pch','Pdis','Q','SOC','charge_mode','arc') for n in sd['names']]),np.flatnonzero(sd['objective'])]
        cut=k.exact_cut(shadow,sd,row,columns,geo)
        checks.append(dict(interface='Original K48 exact_cut with exact dyadic helper view',PASS=True,
            scope='One real Source-YY slot, not full96 K48 packet or LB certificate',
            helper_view=proof,exact_terms=len(cut['original_terms']),helper_rows=len(cut['helper_rows']),
            new_grid_rows_added=0,original_oracle_algorithm_edited=False))
        if (RUN/'mobility/SELECTED.npz').exists():
            import pickle
            import v42_m1_hybrid.blocks as source
            with np.load(RUN/'mobility/DOMAIN.npz') as z:dd={f:z[f] for f in z.files}
            with (RUN/'mobility/TRANSPORT.pkl').open('rb') as f:transport=pickle.load(f)
            case=SimpleNamespace(A=sp.load_npz(RUN/'mobility/SELECTED.npz'),d=dd,graph=transport['graph'],case_sha=digest(record(RUN/'mobility/SELECTED.npz')))
            try:source.build_blocks(case)
            except Exception as exc:checks.append(dict(interface='Original build_blocks eight-unit guard',PASS=False,error=repr(exc)))
            body=textwrap.dedent(inspect.getsource(source.build_blocks));assert body.count('len(units) != 4')==1
            ns=dict(source.build_blocks.__globals__,_expected_units=len(INITIAL))
            exec(compile(body.replace('len(units) != 4','len(units) != _expected_units'),source.__file__,'exec'),ns)
            block=ns['build_blocks'](case)
            checks.append(dict(interface='Isolated dimension-only eight-unit exact partition',PASS=block.inclusion['PASS'],
                units=list(block.units),proof=block.inclusion,source=record(source.__file__),
                original_algorithm_file_edited=False,scope='MOBILITY_ONLY; not full grid/K48/Joint certification',
                independent_unit_MILPs_executed=0))
    return put('ORIGINAL_CURRENT_CASE_INTERFACE_PROBES.json',dict(checks=checks,Native_calls=0,
        denied_attempts=denied,source_algorithms_reused_verbatim=True,
        actual96_FULL_stage_interface_PASS=False,old_IEEE123_bounds_reused=False))

if __name__=='__main__':probe()
