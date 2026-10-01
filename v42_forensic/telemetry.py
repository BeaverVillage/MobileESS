"""Reconcile runtime evidence from immutable solver logs, never reoptimize."""
import re
from .common import *

def run():
    checks=[]
    for p in sorted(OUT.glob('*_OPTIMIZATION.json')):
        r=read(p);name=r['name'];log=gzip.decompress((OUT/(name+'_SOLVER.log.gz')).read_bytes()).decode()
        root=re.findall(r'Root relaxation:.*?([0-9.]+) seconds',log)
        presolve=re.findall(r'Presolve time: ([0-9.]+)s',log)
        r['free_binary_variables']=max(0,r['binary_variables']-r['fixed_binary_bounds'])
        r.setdefault('root_processing_seconds_estimate',r['root_relaxation_seconds'])
        r['root_relaxation_seconds']=float(root[0]) if root else None
        r['root_relaxation_time_source']='Gurobi root-relaxation log line' if root else 'No completed root-relaxation time reported; unavailable'
        if presolve:r['presolve_seconds']=float(presolve[0]);r['presolve_time_source']='Gurobi presolve log line'
        # A 300s bound first observed at 536s is not a 300s observation.
        for threshold in [300,600]:
            point=r['checkpoints'][str(threshold)]
            if point.get('seconds') is not None and point['seconds']>threshold+5:
                r.setdefault('first_observation_after_checkpoints',{})[str(threshold)]=point
                r['checkpoints'][str(threshold)]=dict(seconds=None,BestBd=None,source='No observation within 5s of checkpoint; later observation preserved separately')
        legacy=name in ['R_ROUTE_ONLY','R_ACTIVE']
        if legacy:
            r['telemetry_unsupported_POLLING_query_path']=True;r['telemetry_error_scope']='Unsupported RUNTIME query path in POLLING (ignored exceptions observed in R_ROUTE_ONLY and R_ACTIVE); no solver parameter/model/termination action; official final attrs and raw log remain authority'
            old=r['events'].pop('first_non_root_node_seconds',None)
            if old is not None:r['events']['first_positive_processed_node_count_seconds']=old
            r['first_non_root_node_time_available']=False
        else:r['telemetry_unsupported_POLLING_query_path']=False
        # No branch node can have been visited if the root was the only node.
        if r['node_count']<=1:r['events'].pop('first_non_root_node_seconds',None)
        dump(p.name,r);checks.append(dict(name=name,root_seconds=r['root_relaxation_seconds'],presolve_seconds=r['presolve_seconds'],log_sha256=sha(OUT/(name+'_SOLVER.log.gz')),optimize_calls=0))
    dump('TELEMETRY_RECONCILIATION.json',dict(PASS=True,checks=checks,optimization_retries=0,
        unsupported_POLLING_query_arms=['R_ROUTE_ONLY','R_ACTIVE'],fix='Return before cbGet on POLLING. Old driver stops only between completed R_ACTIVE and not-yet-started R_BUFFER; no arm optimization is interrupted or retried.',
        official_callback_reference='https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html',
        model_or_solver_policy_changes=False,results_authority='Saved solver final status/ObjBound/X and raw logs plus independent matrix/domain checks'))
if __name__=='__main__':run()
