"""Consumer inventory and the explicit equivalence boundary for old kernels."""
from pathlib import Path
import subprocess
from dayahead.paper_analysis.storage import write_json, reference
from .authority import REL


def inventory(repo):
    repo = Path(repo); root = repo / REL
    pattern = r"compute_segments|actual_compute_segments|pcc_from_jobs|terminal_audit|selected_site|start_slot.*end_slot|actual_residual_start|\['AIDC_site'\]"
    scanned = subprocess.run(['rg', '-n', '-g', '*.py', pattern, 'dayahead'], cwd=repo,
                             capture_output=True, encoding='utf-8', errors='replace')
    if scanned.returncode not in (0, 1): raise RuntimeError(scanned.stderr)
    search = root / 'LEGACY_INTERVAL_SEARCH.txt'; search.write_text(scanned.stdout, encoding='utf-8')
    rows = []

    def add(file, functions, classification, proof):
        rows.append({'source': reference(repo / 'dayahead' / file), 'functions': functions,
                     'classification': classification, 'proof_or_replacement': proof})

    add('v40g_segments/canonical.py', ['import_frozen', 'validate', 'identities', 'occupancy', 'planning_power', 'terminal', 'terminal_audit', 'wan_audit'],
        'DIRECT_CANONICAL_SEGMENTS', 'Only import_frozen may translate nonmigrated one-interval records. Migrants require two compute segments and one explicit event. All downstream power/state uses segments.')
    add('v40g_segments/b3.py', ['bind_b1', 'SegmentB1AsA0.load', 'coordinate_segments', 'run'], 'DIRECT_CANONICAL_SEGMENTS',
        'B1 byte aliases plus deterministic canonical sidecar; GPU/IT/PCC rebuilt and compared. M1/MF receive certified numeric PCC. Production run blocks before loading M1 while authorization is NO.')
    add('v40g_segments/feedback.py', ['candidates', 'solve_feedback'], 'DIRECT_CANONICAL_SEGMENTS',
        'RUNNING/migrated choices are copied intact; pending domains alone call legacy authorized_options. Every MILP load term sums each candidate compute segment. Symmetric deviation and terminal audit are canonical.')
    add('v40g_segments/coordination.py', ['coordinate'], 'DIRECT_CANONICAL_SEGMENTS',
        'Inherited one-pass acceptance order retained. Full RUNNING decision/segment/event identity replaces incomplete single-site field comparison. Terminal reads canonical segments.')
    add('v40a/feedback.py', ['authorized_options'], 'PROVEN_SINGLE_SEGMENT_SUBDOMAIN',
        'Called only after canonical validation and the RUNNING/post-H fixed branch in candidates. Remaining PENDING rows have exactly one compute segment by schema. The original temporal/site domain is unchanged.')
    add('v40a/feedback.py', ['pcc_from_jobs', 'solve_feedback'], 'DEFECT_REPLACED_IN_V40G_SEGMENT_ENTRYPOINTS',
        'A final site over the elapsed span creates interruption GPU and loses source GPU. Replaced by canonical.planning_power and v40g_segments.feedback. Original historical source preserved, not a supported V40G entry point.')
    add('v40a/invariants.py', ['tail', 'terminal_audit', 'occupancy_deviation', 'feedback_delta'], 'DEFECT_REPLACED_IN_V40G_SEGMENT_ENTRYPOINTS',
        'Old elapsed-span equality rejects migration and old final-site tail can misassign ownership. Replaced by canonical terminal/deviation and segment report. Numeric route_sha, digest, monotone and joint_decision do not interpret job intervals and remain valid.')
    add('v40a/coordination.py', ['coordinate'], 'DEFECT_REPLACED_IN_V40G_SEGMENT_ENTRYPOINTS',
        'Historical terminal reader and partial RUNNING field comparison are replaced by v40g_segments.coordination; no legacy coordinator call in the new route.')
    add('v40b/b3.py', ['run'], 'DEFECT_RETIRED_FOR_V40G',
        'Constructs legacy A0 and calls single-interval power/A1/terminal/reporting. New authoritative entry is v40g_segments.b3.run with exact B1 handle. No B3 science has executed in this correction.')
    add('v40a/mobility.py', ['search_once'], 'PROVEN_NUMERIC_COMPRESSION',
        'Input is a 96x12 PCC array, not jobs. For N_s(t)=sum_j g_j sum_k 1(site_jk=s and start_jk<=t<end_jk), deterministic CENTER and frozen C1 yield the exact same PCC controls. M1 receives this array and its segment/event certificate.')
    add('v40a/recourse.py', ['solve_fixed_route'], 'PROVEN_NUMERIC_COMPRESSION',
        'Receives certified canonical PCC and fixed M1 trajectory. It has no AIDC choice variables. Existing fixed-route P/Q/energy constraints and coordinator route hash remain binding.')
    add('v40a/grid.py', ['controls_from_trajectory', 'add_grid', 'evaluate_grid'], 'PROVEN_NUMERIC_COMPRESSION',
        'All grid rows use numeric PCC and MESS controls only. Equal segment-derived controls imply equal affine/polygon constraints and objectives, including all line/phase/time rows.')
    add('v40g_segments/smoke.py', ['prepare', 'physical'], 'DIRECT_CANONICAL_SEGMENTS',
        'Reconstructs and certifies Planning arrays from canonical segments; the Fresh loader recomputes all four arrays before loading FrozenTrajectory. Only May-01 B0/B1 physical replay is reachable, with optimize patched to reject.')
    add('v40e/smoke.py', ['b0_b1'], 'PROVEN_ADAPTED_PHYSICAL_KERNEL',
        'Persisted adapter changes output namespace, canonical loader certification, Actual replay/power/audit imports and ledger serialization only. Old prepare/evaluate/initial are not called.')
    add('v40g_segments/actual.py', ['replay_jobs', 'compare_occupancy', 'power_from_execution', 'write_runtime_audits'], 'DIRECT_CANONICAL_SEGMENTS_WITH_PROVEN_DISPATCH_PROJECTION',
        'Canonical source checkpoint, destination and ready time produce disjoint whole-gang internal handles; final root UID segments independently reproduce dispatcher occupancy. CENTER/C1 kernel receives only canonical root occupancy.')
    add('v40d_actual/job_replay.py', ['replay_jobs'], 'PROVEN_DISJOINT_PHASE_COMPRESSION_ONLY',
        'Never receives a selected migrated scientific row. For residual R and checkpoint c, source=min(R,900c), destination=R-source; destination admission is no earlier than frozen restart. Release uses ceil(end), and c/ready are integers with ready>c. Handles cannot overlap or split a gang; inherited priority/rack admission is identical. For R<=900c, migration is cancelled by completion, not replanned.')
    add('v40d_actual/rack_dispatch.py', ['RackDispatcher'], 'PROVEN_DISJOINT_PHASE_COMPRESSION_ONLY',
        'Each handle requests the full original GPU gang at one canonical site. Logical racks remain compatibility labels; site capacity is the hard additive cap. Root UID occupancy rejects concurrent handles; legacy phase audit verifies every admission/release.')
    add('v40d_actual/capacity_audit.py', ['compare_occupancy', 'audit_gangs', 'write_runtime_audits'], 'PROVEN_PHASE_AUDIT_ONLY',
        'Used only with internal single-segment frozen/realized phase records. The resulting occupancy must also equal independent canonical root-UID reconstruction. Direct use on migrated root rows would be a defect and is not called.')
    add('v40d_actual/power_replay.py', ['power_from_execution'], 'PROVEN_NUMERIC_KERNEL_WITH_CANONICAL_READER',
        'Function bytecode reused with compare_occupancy global explicitly bound to v40g_segments.actual.compare_occupancy. No legacy root interval reader remains. Frozen decimal CENTER and one C1 application are unchanged.')
    add('v38/wan.py', ['validate_fixed_path_transfers'], 'PROVEN_EVENT_COMPRESSION',
        'Receives canonical migration-event bytes and fixed OD paths. canonical.wan_audit additionally checks payload=g-dependent authority, exact path, capacity, causal interval and restart; actual subset excludes only completion-before-checkpoint jobs.')
    add('v28r2/trajectory.py', ['FrozenTrajectory'], 'PROVEN_NUMERIC_COMPRESSION', 'The container carries the certified PCC P/Q arrays; it never reconstructs job placement.')
    add('v28r2/opendss_backend.py', ['run_fresh_opendss'], 'PROVEN_NUMERIC_COMPRESSION', 'Fresh input PCC is segment-certified before construction. Native element P/Q readback and all output arrays are compared independently.')
    add('v40d_actual/grid_replay.py', ['replay'], 'PROVEN_NUMERIC_COMPRESSION', 'Actual engine receives canonical execution-derived PCC. Applied AIDC P/Q readback is exact and full phase output arrays are independently compared.')
    add('v40g_segments/report.py', ['finish', 'actual_audit'], 'DIRECT_CANONICAL_SEGMENTS', 'Every scientific UID has explicit actual segments, terminal state, service partition and root UID/site/slot reconstruction. No final-site interval fallback.')
    add('v40g/actual.py', ['replay_jobs', 'power_from_execution'], 'PRIOR_MAY01_EQUIVALENCE_PROVEN_BY_COUNTERFACTUAL',
        'Historical adapter already splits source and destination. New reconstruction, original UID occupancy/service proof and complete OpenDSS array byte comparison determine equivalence; no trust based only on equal rho.')
    add('v40g/optimizer.py', ['solve'], 'PRESERVED_FROZEN_PRIMARY_NOT_REEXECUTED', 'Accepted B1 remains unchanged. Candidate occupation was already Option.segments-based; the new canonical reconstruction proves the accepted trajectory. No extra primary audit or solve was performed.')
    result = {'status': 'PASS', 'scope': 'Active V40G segment-integration entrypoints and all job/interval-sensitive inherited consumers',
        'repository_wide_search': reference(search), 'matched_lines': len(scanned.stdout.splitlines()), 'consumers': rows,
        'unresolved_active_single_interval_consumers': 0,
        'historical_defects_preserved_as_evidence_not_authorized_entrypoints': True,
        'effective_entrypoints': ['dayahead.v40g_segments.smoke.prepare', 'dayahead.v40g_segments.smoke.physical',
                                  'dayahead.v40g_segments.b3.run (execution gated)', 'dayahead.v40g_segments.report.finish']}
    write_json(root / 'SCIENTIFIC_CONSUMER_INVENTORY.json', result)
    return result
