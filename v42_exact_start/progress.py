"""Evidence-only raw-log enrichment; never interprets infeasible LP objectives as bounds."""
import re,shutil
from .common import *

def parse_lines(lines):
    pattern=re.compile(r'^\s*(\d+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+(\d+)s\s*$')
    found=[]
    for line in lines:
        match=pattern.match(line)
        if match:
            it,obj,primal,dual,t=match.groups()
            found.append(dict(t=float(t),simplex_iterations=int(it),simplex_phase_objective=float(obj),
                              primal_infeasibility=float(primal),dual_infeasibility=float(dual)))
    return found

def enrich(kind):
    key=kind.upper();result=read('CANARY_'+key+'_600S.json');path=OUT/('CANARY_PROGRESS_'+key+'.csv')
    backup=OUT/('CANARY_PROGRESS_'+key+'_CALLBACKS.csv')
    if not backup.exists():shutil.copyfile(path,backup)
    with backup.open(encoding='utf8',newline='') as f:
        callbacks=[]
        for row in csv.DictReader(f):
            converted={k:(None if v=='' else v) for k,v in row.items()}
            for k in ['t','Incumbent_UB','BestBd','Gap','Nodes','simplex_iterations','bound_observed_at','incumbent_observed_at']:
                converted[k]=None if converted.get(k) is None else float(converted[k])
            callbacks.append(converted)
    fields=list(callbacks[0])+['requested_timestamp','observation_note','bound_observation_age','simplex_phase_objective','primal_infeasibility','dual_infeasibility','presolved_rows','presolved_columns','presolved_binaries','presolved_continuous','UB_valid','LB_valid','valid_global_gap']
    records=[]
    for sample in parse_lines((OUT/('CANARY_'+key+'_600S.log')).read_text(encoding='utf8').splitlines()):
        prior=[r for r in callbacks if r['t']<=sample['t'] and r['source']!='terminal']
        if not prior:continue
        row=dict(prior[-1]);row.update(sample);row['source']='raw_root_simplex_log_with_last_observed_MIP_bounds'
        completed=result.get('root_relaxation_completion_time')
        row['Root_relaxation_status']='COMPLETED' if completed is not None and sample['t']>=completed else 'IN_PROGRESS'
        row['bound_observation_age']=None if row.get('bound_observed_at') is None else row['t']-float(row['bound_observed_at'])
        row['observation_note']='LP phase objective is diagnostic only. UB/BestBd are last observed MIP callback values, not newly observed bounds at log timestamp. Displayed log time resolution is one second.'
        records.append(row)
    records+=callbacks;records.sort(key=lambda r:r['t'])
    checkpoints={}
    for t in [30,60,120,300,600]:
        candidates=[r for r in records if r['t']>=t]
        point=dict(candidates[0] if candidates else records[-1]);point['requested_timestamp']=t
        point['observation_note']=point.get('observation_note','')+' Requested timestamp and actual observation timestamp are separate; no interpolated bound.'
        checkpoints[str(t)]=point;records.append(point)
    from v42_monolithic.certificates import interval
    for row in records:
        dims=result.get('presolved_dimensions') or {};types=result.get('presolved_types') or {}
        row.update(presolved_rows=dims.get('rows'),presolved_columns=dims.get('columns'),presolved_binaries=types.get('binary'),presolved_continuous=types.get('continuous'))
        bound=interval(row.get('BestBd'),None)
        row.update(UB_valid=bound['validated_retained_UB'],LB_valid=bound['valid_retained_LB'],valid_global_gap=bound['valid_global_gap'])
        row['observation_note']=row.get('observation_note','')+' Presolved dimensions are the final reported fixed presolved model, not a separate timed observation.'
    records.sort(key=lambda r:r['t'])
    table(path.name,[{k:r.get(k) for k in fields} for r in records],fields)
    dump('CANARY_PROGRESS_'+key+'_RECEIPT.json',dict(PASS=True,checkpoints=checkpoints,
        raw_log_sha256=sha(OUT/('CANARY_'+key+'_600S.log')),callback_csv_sha256=sha(backup),progress_csv_sha256=sha(path),
        infeasible_simplex_objective_never_used_as_UB_or_LB=True,displayed_log_time_resolution_seconds=1,
        absent_root_and_branch_events_are_not_invented=True))
    return checkpoints

if __name__=='__main__':
    for kind in ['original','compact']:enrich(kind)
