"""Existing two-case OpenDSS path with frozen migration execution accounting."""
from pathlib import Path
import inspect
from dayahead.paper_analysis.storage import read,write_json,reference
from .authority import REL,current_context


def run(repo):
    from dayahead.v40e import smoke as previous
    repo=Path(repo).resolve();root=repo/REL;out=root/'smoke/2025-05-01'
    if any((out/c/'CORRECTED_ACTUAL_RESULT.json').exists() for c in ('B0','B1')):raise RuntimeError('PRESERVE_COMPLETED_PHYSICS')
    src=inspect.getsource(previous.b0_b1).replace('V40E_','V40G_')
    src=src.replace('from dayahead.v40d_actual.job_replay import replay_jobs,validate_jobs',
                    'from dayahead.v40d_actual.job_replay import validate_jobs\n    from dayahead.v40g.actual import replay_jobs')
    src=src.replace('from dayahead.v40d_actual.power_replay import power_from_execution','from dayahead.v40g.actual import power_from_execution')
    src=src.replace('from dayahead.v40d_actual.capacity_audit import write_runtime_audits','from dayahead.v40g.actual import write_runtime_audits')
    src=src.replace("'accepted_A0_assignment_and_WAN','checks')", "'accepted_A0_assignment_and_WAN','checks','common_terminal_obligation','compute_segments','actual_compute_segments','frozen_WAN_transfer')")
    ns=dict(previous.__dict__);ns['REL']=REL;ns['planning_context']=lambda r,d:current_context(r)
    exec(compile(src,'<V40G_frozen_policy_two_case_physics>','exec'),ns)
    write_json(root/'PHYSICAL_RUNNER_LINEAGE.json',{'original_source':reference(Path(inspect.getsourcefile(previous.b0_b1))),
        'adapted_source':src,'electrical_physics_changed':False,'Actual_migration_segment_accounting':True,
        'Actual_optimization_forbidden':True,'B2_B3_reachable':False})
    ns['b0_b1'](repo)


if __name__=='__main__':run(Path.cwd())
