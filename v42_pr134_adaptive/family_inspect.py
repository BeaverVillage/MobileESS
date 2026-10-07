import sys
import numpy as np
from .common import *
z=dict(np.load(SOURCE/sys.argv[1]/'A0_ATTRIBUTES_CODED.npz'))
for i,f in enumerate(z['rf_names']):
    ids=np.flatnonzero(z['rf']==i)
    print(f,int(ids[0]),int(ids[-1]),len(ids),flush=True)
