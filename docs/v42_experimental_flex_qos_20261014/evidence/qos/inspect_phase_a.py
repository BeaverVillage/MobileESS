from pathlib import Path
import sys, json
sys.path.insert(0, str(Path(__file__).parents[2]))
from v42_integration.experimental_replay import load_conditional_source
from dataclasses import asdict
s=load_conditional_source()
p,planning=s['fresh_actual_inputs']()
args=p['arguments'];data=s['data'];uid=next(iter(data[1]));request=args['requests'][0]
print(json.dumps(dict(data_types=[type(x).__name__ for x in data],native_jobs=len(data[1]),
    native_example=asdict(data[1][uid]),boundary_example=asdict(data[2][uid]),
    request_example=asdict(request),running_example=asdict(args['running'][0][0]),
    known_issue_example=planning['known_receipts'][uid],known_issue=len(planning['known_receipts']),
    active_origin_unknown=sum(r.metadata['origin_unknown'] for r in args['requests'])+sum(r[0].metadata['origin_unknown'] for r in args['running']),
    begin=args['begin'],issue=p['issue_epoch_seconds']),ensure_ascii=False,default=str))
