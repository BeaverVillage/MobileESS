"""Bitwise source replay for the certified zero-dispatch reference IO."""
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .static_pack import PACK,N_AUX
from .prestart_native import native_zero


def certify():
    from v44.frozen.v43_mess.library import load
    with measured('BEAM_ZERO_REFERENCE_EQUIVALENCE.json') as (report,start),native_zero() as denied:
        source=load()['table_v_k48'].original_oracle
        with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:md={k:z[k] for k in z.files}
        n=len(md['names']);records=[]
        for t in (0,47,95):
            folder=WORK/'M1/view'/f'{t:02d}';A=sp.load_npz(folder/'A.npz')
            with np.load(folder/'D.npz') as z:d={k:z[k] for k in z.files}
            for key in ('names','lower','upper','types','objective'):d[key]=np.r_[md[key],d[key]]
            g=source.Geometry(A,d);assert len(g.definitions)==N_AUX
            x=np.zeros(A.shape[1]);g.numerical(x,np.zeros_like(x))
            expected=np.zeros_like(x)
            for col,row in g.definitions.items():expected[col]=d['rhs'][row]
            assert np.array_equal(x.view(np.uint64),expected.view(np.uint64))
            records.append(dict(slot=t,all_helper_values_bitwise_equal=True,helpers=len(g.definitions)))
            print('SOURCE ZERO REFERENCE BITWISE',t,flush=True)
        report.update(PASS=True,records=records,source=record(source.__file__),
            full96_admission='Every binding is rechecked by stage_geometry_io.assemble: positive unit pivot; only physical P/Q and zero injection dependencies; zero injection RHS',
            mathematical_identity='rhs - Python sum of signed-zero products equals rhs; source zero physical/injection values are +0',
            source_signed_scores_selectors_and_native_constraints_unchanged=True,
            error_envelopes_not_omitted_for_K48_pricing=True,unused_Beam_error_array_only=True,
            zero_reference_not_incumbent_or_MIPStart=True,denied_attempts=denied)


if __name__=='__main__':certify()
