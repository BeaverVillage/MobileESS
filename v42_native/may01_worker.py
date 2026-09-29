"""Source-hashed external-supervision entry point; no policy/ML imports."""
from pathlib import Path
from v42_native.contracts import require,file_sha
from v42_may01.prepare import read,native_coefficients
from v42_may01.projection import known_planning_gate,solve


def worker(context,payload):
    bundle_path=Path(payload['bundle']);require(file_sha(bundle_path)==payload['bundle_sha'],'BUNDLE_DRIFT')
    for row in payload['source_files']:require(file_sha(row['path'])==row['sha256'],'FROZEN_SOURCE_DRIFT:'+row['path'])
    bundle=read(bundle_path);known_planning_gate(bundle)
    # Verify real native coefficient axes before the resource check; never
    # inject synthetic coefficients or reuse an Actual response kernel.
    c=native_coefficients(read(bundle['electrical_certificate']['path']))
    require(len(c)==96 and len(c[0].control_names)==60,'NATIVE_GRID_AXIS')
    jobs=[r for r in bundle['known_population'] if r['planning_eligible']]
    result=solve(jobs,bundle['C0_Q50'],sum(bundle['capacities'].values()),context.folder,context.remaining)
    # An infeasibility certificate is not an incumbent. Do not context.publish.
    require(result['full_A1_infeasible_proven'],'RESOURCE_PROJECTION_NOT_A_FULL_PLANNING_SOLUTION')


def validator(candidate,payload):
    return {'PASS':False,'reason':'PROJECTION_NEVER_AN_ACCEPTED_OPERATING_SCHEDULE'}
