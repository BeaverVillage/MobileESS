import numpy as np
import scipy.sparse as sp
from v42_may10_prestart_rescue.inspect_saved import read_row


def test_streamed_saved_row_matches_independent_original_csr(tmp_path):
    A=sp.csr_matrix([[0,1,0], [2,0,3], [0,0,0], [0,4,5]],dtype=float)
    p=tmp_path/'matrix.npz';sp.save_npz(p,A)
    for row in range(A.shape[0]):
        indices,data=read_row(p,row)
        original=A.getrow(row)
        assert np.array_equal(indices,original.indices)
        assert np.array_equal(data,original.data)
