import sys
import numpy as np,scipy.sparse as sp
from .common import *
folder=Path(sys.argv[1]);a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'));names=dict(np.load(folder/'NATIVE_NAMES.npz'))
for s in sys.argv[2:]:
    i=int(s);p,q=a.indptr[i:i+2]
    print(i,str(names['rows'][i]),z['sense'][i],z['rhs'][i],[(str(names['vars'][j]),c) for j,c in zip(a.indices[p:q],a.data[p:q])][:20],flush=True)
