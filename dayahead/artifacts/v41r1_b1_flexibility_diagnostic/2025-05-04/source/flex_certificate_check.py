"""Check the apparent local bound against a stronger feasible subset witness."""
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT,WORK
from .flex_model import Data,ProbeModel
from .feasible_seed import row_audit


def run():
    d=Data();p=ProbeModel(d)
    try:
        earlier=read(OUT/'COUPLED_ESCAPE_TEST.json')
        subset=read(OUT/'ABLATION_MIGRATION_ONLY_ORIGINAL_MODEL_WITNESS.json')
        with np.load(subset['assignment']['path']) as z:x=z['values']
        p.reset(earlier['opened_groups'])
        check=row_audit(p.m,x)
        assert check['status']=='PASS'
        assert subset['vector'][0]<earlier['bound']-1e-10
        path=WORK/'cb.npz'
        np.savez_compressed(path,LB=p.m.getAttr('LB'),UB=p.m.getAttr('UB'))
        result=dict(status='LOCAL_CERTIFICATE_CONTRADICTED_BY_FEASIBLE_WITNESS',
            prior_report=record(OUT/'COUPLED_ESCAPE_TEST.json'),
            lower_P1_witness=record(OUT/'ABLATION_MIGRATION_ONLY_ORIGINAL_MODEL_WITNESS.json'),
            exact_coupled_bounds_row_audit=check,old_reported_lower_bound=earlier['bound'],
            feasible_counterexample_P1=subset['vector'][0],exact_coupled_bounds=record(path),
            model_authority=record(WORK/'original.mps'),
            original_model_changed=False,production_changed=False,
            interpretation='Do not treat the earlier solver OPTIMAL status as a valid local/global certificate.')
        write_json(OUT/'LOCAL_CERTIFICATE_CONSISTENCY.json',result)
        print('LOCAL_BOUND_COUNTEREXAMPLE_VERIFIED',subset['vector'][0],earlier['bound'],flush=True)
        p.solve('FRESH_COUPLED_CERTIFICATE_CHECK',earlier['opened_groups'],seconds=120,start=x)
    finally:p.close();d.close()


if __name__=='__main__':run()
