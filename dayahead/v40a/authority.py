"""Bind the accepted production overlay and every V40A executable entrypoint."""
from pathlib import Path
import json
from .context import file_sha
from .invariants import digest


def mobility_input_authority(day):
    from dayahead.v35.execution import daily_traffic_authority, _route_cache_paths
    from dayahead.v35.contracts import PHASE_CALIBRATION
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE
    cache=FROZEN_MESS_WORKTREE/'dayahead/cache/v35'
    paths=_route_cache_paths(cache,PHASE_CALIBRATION,day)
    if not all(p.is_file() for p in paths):
        raise ValueError('V40A_REQUIRES_EXISTING_AUTHORIZED_D1_TRAFFIC_BYTES')
    bundle,graph,route_table,files=daily_traffic_authority(FROZEN_MESS_WORKTREE,cache,PHASE_CALIBRATION,day,None)
    if not bundle.causality_pass or bundle.future_actual_read_count or bundle.max_input_timestamp>bundle.issue_time:
        raise ValueError('V40A_TRAFFIC_CAUSALITY_FAILURE')
    return {'day':day,'files':list(files),'forecast_SHA':bundle.canonical_sha256,
            'route_table_SHA':route_table.canonical_sha256,'road_graph_SHA':graph.route_graph_sha,
            'issue_time':bundle.issue_time.isoformat(),'max_input_timestamp':bundle.max_input_timestamp.isoformat(),
            'future_actual_read_count':bundle.future_actual_read_count,'causality_pass':bundle.causality_pass}


def source_authority(repo, root):
    repo, root = Path(repo), Path(root)
    snapshot = json.loads((root / 'V40A_PRESTOP_CAMPAIGN_SNAPSHOT.json').read_text(encoding='utf-8'))
    inherited = snapshot['source_file_fingerprints']
    drift = [name for name, sha in inherited.items()
             if not (repo / name).is_file() or file_sha(repo / name) != sha]
    if drift:
        raise ValueError('ACCEPTED_PRODUCTION_SOURCE_DRIFT:' + str(drift))
    paths = list((repo / 'dayahead/v40a').glob('*.py'))
    paths += list((repo / 'dayahead/tools').glob('*v40a*.py'))
    return {
        'accepted_production_common_source_SHA': snapshot['current_common_source_fingerprint'],
        'accepted_production_source_manifest_SHA': digest(inherited),
        'accepted_production_source_files_verified': len(inherited),
        'accepted_production_authority_manifest_SHA': digest(snapshot['production_authority_fingerprints']),
        'V39K_history_authority_SHA': snapshot['V39K_authority_SHA'],
        'V40A_source_SHAs': {p.relative_to(repo).as_posix(): file_sha(p) for p in sorted(paths)},
    }
