from pathlib import Path
import gzip,pickle
import numpy as np
from v42_pr134_b1.common import read
from v42_pr134_b1.native import bind
from v42_pr134_sc.snapshot import certify
from v42_a_stage_domain_v2.stress_backend import row_replay
from v42_integrated.contract import physical_authority
from .policy import ROOT,STATIC

class Physical:
    def __init__(self,state,snapshot):
        self.state=state;self.snapshot=snapshot;day=state['data'][0]['day']
        if 'scientific_descriptor' in state:d=state['scientific_descriptor']
        else:
            r=read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json')
            with gzip.open(r['global_descriptor']['path'],'rb') as f:d=pickle.load(f)
        self.descriptor=dict(d,units=state['reference_descriptor']['units'])
        self.descriptor['levels']=[(o.name,('e',float(o.constant),np.asarray(list(o.coefficients()),dtype=int),
            np.asarray([float(v) for v in o.coefficients().values()]))) for o in snapshot.objectives]
        _,_,self.coeff,*_=bind(state['data'][0],Path('C:/v42_pr134_sc_execution_20261007/inputs')/day,STATIC/day/'PHYSICAL_REPLAY')
    def verify(self,x):
        r=row_replay(self.snapshot,x)
        with physical_authority():c,selected,controls,globals=certify(self.descriptor,self.state['data'],x,r,self.coeff)
        return dict(PASS=bool(r['PASS'] and c['PASS']),original_rows=r,physical=c,selected_jobs=selected,
            controls=controls,globals=globals,artificial_variables=0,original_individual_migration_integrality=True)
