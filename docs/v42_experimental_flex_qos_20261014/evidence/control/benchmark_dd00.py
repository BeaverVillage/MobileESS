"""Read-only public first-event benchmark, never a May Actual or AC result."""
from pathlib import Path
import argparse,json,hashlib,time
from v42_integration.experimental_replay import load_conditional_source
from v42_integration.experimental_actual import benchmark_conditional_event
from v42_integration.policy import digest
from v42_integration.sensitivity_policy import OriginalGridPacket

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--original-grid',action='store_true')
    parser.add_argument('--participant',action='store_true')
    args=parser.parse_args();freeze=json.loads(Path(args.freeze).read_text(encoding='utf-8'))
    source=load_conditional_source()
    if args.original_grid:
        source['packet']._at_slot=OriginalGridPacket._at_slot.__get__(source['packet'])
    source['packet'].cache.clear();source['packet'].scenario_cache.clear()
    sha=freeze['source_sha'];case=digest(dict(scope='BENCHMARK_EPOCH_DD00_FIRST_FCFS',
        source_epoch=sha,scenario='E1',participation='FLEX30'))
    started=time.perf_counter()
    result=benchmark_conditional_event(source,case_sha=case,source_epoch_sha=sha,output=args.output,
        participant_only=args.participant)
    result['driver_total_wall_seconds']=time.perf_counter()-started
    result['driver_sha']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['grid_evaluation_method']='ORIGINAL_AT_SLOT' if args.original_grid else type(source['packet']).__name__
    destination=Path(args.output)/'CONTROL_POLICY_RUNTIME_MEMORY.json'
    destination.write_text(json.dumps(result,sort_keys=True),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('uid','initial_Running','initial_Pending',
        'cold_wall_seconds','median_wall_seconds','P95_wall_seconds','process_RSS_after_bytes',
        'rows','driver_total_wall_seconds','grid_evaluation_method')}))

if __name__=='__main__':main()
