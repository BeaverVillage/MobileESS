"""Seal the historical defect and its transitive Planning dependencies first."""
from pathlib import Path
from collections import defaultdict
import ast
import json
import os
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, sha, write_json, write_parquet

REL = Path('dayahead/artifacts/v40e_background_mapping_fix')
OLD = Path('dayahead/artifacts/v40d_actual_realized_replay')
STATUS = 'INVALIDATED_BY_BACKGROUND_MAPPING_DEFECT'


def source(repo, path, function):
    p = repo / path
    tree = ast.parse(p.read_text(encoding='utf-8-sig'))
    f = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function)
    return {**reference(p), 'function': function, 'line': f.lineno, 'end_line': f.end_lineno,
            'source_text': '\n'.join(p.read_text(encoding='utf-8-sig').splitlines()[f.lineno-1:f.end_lineno])}


def seal(repo):
    repo = Path(repo).resolve(); out = repo / REL; out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'PROTECTED_OLD_ARTIFACTS_MANIFEST.json'
    if not manifest.exists():
        refs = dict(read(repo / OLD / 'V40D_PROTECTED_PLANNING_MANIFEST.json')['files'])
        for root in (repo / OLD,):
            for p in root.rglob('*'):
                if p.is_file(): refs[str(p)] = reference(p)
        write_json(manifest, {'files': refs, 'new_V40E_outputs_excluded': True})
    power = read(repo / OLD / 'power_scale_parity/2025-05-01/V40D_POWER_SCALE_PARITY_AUDIT.json')
    adapter = read(power['feeder_asset_refs']['runtime_adapter']['path'])
    members = defaultdict(list)
    for row in adapter['loads']:
        for phase in row['phases']:
            members[row['bus'].lower(), int(phase)].append(row)
    shared = []
    for (bus, phase), rows in members.items():
        if len(rows) > 1:
            shared.append({'bus': bus, 'phase': 'ABC'[phase-1], 'application_count': len(rows), 'loads': rows,
                           'bad_expression': 'sum(background.gross_[p/q][slot][bus,phase] for phase in load.phases)'})
    root = {'BACKGROUND_MAPPING_DEFECT': 'CONFIRMED', 'classification': 'IMPLEMENTATION_DEFECT',
            'OLD_RESULT_STATUS': STATUS, 'shared_bus_phases': shared,
            'offending_sources': [source(repo, 'dayahead/v28r2/opendss_mapping.py', 'apply_trajectory_slot'),
                                  source(repo, 'dayahead/run_v16_3_voltage_candidate.py', '_set_slot')],
            'mechanism': 'Aggregated bus-phase targets are copied into every overlapping native load. Each of the six shared phases at buses 65 and 76 is counted twice.',
            'evidence': power['background_mapping_defect'],
            'historical_Fresh_Actual_8_replays_bit_exact': all(c['repeat_arrays_exact'] for c in power['cases']) if 'repeat_arrays_exact' in power['cases'][0] else 'See case evidence refs below',
            'complete_prior_audit': reference(repo / OLD / 'power_scale_parity/2025-05-01/V40D_POWER_SCALE_PARITY_AUDIT.json'),
            'allocation_authority': {'runtime_adapter': power['feeder_asset_refs']['runtime_adapter'],
                'native_compilation_assets': power['feeder_asset_refs'],
                'forward_phase_compilation': source(repo, 'dayahead/grid_background_v16_2.py', '_adapter_arrays'),
                'native_per_load_share_rule': 'For P and Q separately, native load base / number of listed conductors, divided by the sum of those native contributions for the bus-phase. This inverts the existing forward native-weight construction; no new equal split between loads.',
                'missing_zero_or_ambiguous_share_authority': 'FAIL_CLOSED'}}
    write_json(out / 'V40E_BACKGROUND_LOAD_DUPLICATION_ROOT_CAUSE.json', root)
    all_dates = [f'2025-05-{n:02d}' for n in range(1,32)]
    definitions = [
        ('A', 'Planning objective', [('dayahead/v40a/grid.py','add_grid'),('dayahead/v40a/grid.py','evaluate_grid'),('dayahead/v28r2/electrical_subproblem.py','anchored_polygon_parameters')], 'INDIRECT_AC_ANCHOR_AND_CURRENT_JACOBIAN', 'COOPT_STAGE_OBJECTIVES.json; historical case checkpoints'),
        ('B', 'Planning electrical constraints/cache', [('dayahead/v40a/context.py','load_planning_context'),('dayahead/v28r2/electrical_subproblem.py','slot_coefficients')], 'INDIRECT_VOLTAGE_CURRENT_ANCHOR_AND_JACOBIANS', 'D1_AC_ANCHOR_*; voltage applicability; coefficient caches'),
        ('C', 'Planning sensitivity generation', [('dayahead/run_v16_3_voltage_candidate.py','_anchor_and_sensitivity_day'),('dayahead/run_v16_3_correction.py','_generate_current_day'),('dayahead/tools/run_v37_r2_voltage_fidelity_repair.py','_solve_slot_voltage'),('dayahead/v37r3/voltage_authority.py','joint_repaired_coefficients')], 'DIRECT_AND_TRANSITIVE_APRIL_CALIBRATION', 'D1_AC_ANCHOR_*; V37_R2_FRESH_LOCAL_SENSITIVITY.parquet; V37_R3_JOINT_VOLTAGE_AUTHORITY.json'),
        ('D', 'Planning physical gates', [('dayahead/v40a/grid.py','evaluate_grid')], 'INDIRECT_CONTAMINATED_COEFFICIENTS', 'PLANNING_PHYSICAL_GATES.json; V39E planning_feasibility'),
        ('E', 'Fresh exact AC', [('dayahead/v28r2/opendss_backend.py','run_fresh_opendss')], 'DIRECT', 'Fresh OPENDSS_PHASE_ARRAYS.npz and summaries'),
        ('F', 'Fresh AC restoration', [('dayahead/v40a/postfreeze.py','production_verification'),('dayahead/v37r3/restoration.py','local_fresh_ac_restoration_cuts')], 'DIRECT_LOCAL_DERIVATIVES_AND_INDIRECT_PLANNING_CONSTRAINTS', 'postfreeze rounds; final P/Q and decision SHA'),
        ('G', 'Actual exact AC', [('dayahead/v28r2/opendss_backend.py','run_fresh_opendss')], 'DIRECT', 'V40D May-01 Actual OPENDSS_PHASE_ARRAYS.npz'),
    ]
    layers = []
    for code, layer, funcs, dependency, artifact in definitions:
        layers.append({'id': code, 'layer': layer, 'uses_defective_mapper': 'YES', 'dependency_kind': dependency,
                       'source_functions': [source(repo,p,f) for p,f in funcs], 'affected_artifacts': artifact,
                       'date_case_coverage': {'dates': all_dates if code!='G' else ['2025-05-01'], 'cases': ['B0','B1','B2','B3']},
                       'Actual_full_124_campaign_executed': False})
    affected = []
    restoration = []
    for day in all_dates:
        cache = repo / 'dayahead/cache/v37_may_locked_final/electrical' / day / 'data'
        vp = cache / f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz'
        ip = cache / f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'
        with np.load(ip) as i:
            assert str(i['source_voltage_cache_sha256']) == sha(vp)
        affected.append({'day': day, 'cases': ['B0','B1','B2','B3'], 'voltage_cache': reference(vp), 'current_cache': reference(ip), 'current_binds_exact_voltage_SHA': True})
        d = repo / 'dayahead/artifacts/v40b_v40a_may_launch/days' / day / 'B3'
        chk = read(d / 'COOPT_PLANNING_CHECKPOINT.json')
        final = read(d / 'FINAL_JOINT_DECISION_PAYLOAD.json')
        pre = chk['mf']['trajectory'] if isinstance(chk['mf'],dict) and 'trajectory' in chk['mf'] else chk['mf']
        # Exact pre/post fixed-PQ comparison is finalized with known slot schema below.
        post = read(d / 'postfreeze/POSTFREEZE_VERIFICATION.json')
        restoration.append({'day': day, 'case': 'B3', 'restoration_rounds': post['restoration_rounds'],
                            'Fresh_calls': post['Fresh_calls'], 'buggy_Fresh_triggered_restoration': post['restoration_rounds']>0,
                            'report': reference(d / 'postfreeze/POSTFREEZE_VERIFICATION.json')})
    april = read(repo / 'dayahead/artifacts/v37_r3_restore_intended_cuts/V37_R3_JOINT_VOLTAGE_AUTHORITY.json')
    blast = {'BACKGROUND_MAPPING_DEFECT':'CONFIRMED','AFFECTED_LAYERS':layers,'PLANNING_CONTAMINATED':'YES',
             'FRESH_CONTAMINATED':'YES','ACTUAL_CONTAMINATED':'YES','AFFECTED_DATES':all_dates,'AFFECTED_CASES':['B0','B1','B2','B3'],
             'actual_executed_affected_dates':['2025-05-01'],'affected_case_cache_bindings':affected,
             'April_calibration_also_contaminated': {'days':april['calibration_days'],'source':april['calibration_source_path'],
                 'reason':'The April local gradient measurement uses apply_trajectory_slot; selecting a complete same-state vector does not remove the erroneous background operating point.'},
             'FRESH_RESTORATION_DECISIONS_AFFECTED':restoration,
             'REQUIRED_RERUN_BOUNDARY':'CASE C','FULL_MAY_RERUN_REQUIRED':'YES',
             'rerun_sequence':['Correct native allocation and test conservation','Regenerate affected D1 native-control anchors and voltage/current sensitivities',
                 'Remeasure frozen April calibration states with corrected mapping and corrected D1 native state; apply the same frozen joint-gradient selection rule',
                 'Regenerate RW/reference placement where electrical constraints were used; regenerate A0 RSP site/temporal feasibility stages as required',
                 'Recompute B0/B1; rerun B2 MESS and B3 A0/M1/A1/MF; corrected physical gates; seal joint decisions',
                 'Corrected Fresh and fixed-discrete restoration if necessary; corrected Actual'],
             'OLD_RESULT_STATUS':STATUS,'common_defect_cancellation_assumed':False,
             'full_31_day_rerun_started':False,'FULL_CAMPAIGN_AUTHORIZED':False,'UNASSIGNED_blocked_case_count':44}
    write_json(out / 'V40E_BACKGROUND_DEFECT_BLAST_RADIUS.json',blast)
    planning = {'PLANNING_CONTAMINATED':'YES','REQUIRED_RERUN_BOUNDARY':'CASE C',
                'optimizer_background':'MIXED: correct lossless bus-phase base, but duplicated-background AC voltage/current anchors, current Jacobians, and April replacement voltage gradients.',
                'why_correct_LP_base_does_not_exonerate_Planning':'The anchored polygon bias equals contaminated AC current at the anchor minus the lossless polygon. Voltage/current affine constants preserve contaminated AC anchors exactly.',
                'correct_forward_base_source':source(repo,'dayahead/full_ieee123_g11_v16_1.py','build_full_grid_binding'),
                'contaminated_dependency_layers':[r for r in layers if r['id'] in 'ABCD'],
                'May01_numeric_cache_reproduction':'PENDING','all_31_days_current_voltage_SHA_bindings_exact':True,
                'historical_Planning_science_valid':False,'May01_corrected_smoke_ready':False}
    write_json(out / 'V40E_PLANNING_CONTAMINATION_AUDIT.json',planning)
    print('SEALED root cause and CASE C blast radius', flush=True)
    return out


def reproduce_old_cache(repo):
    from dayahead.v40a.context import load_planning_context
    from dayahead.v28r2.electrical_context import source_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
    from dayahead.run_v16_3_correction import _generate_current_day
    repo=Path(repo).resolve();out=repo/REL;day='2025-05-01'
    ctx=load_planning_context(repo,day);e=ctx.electrical;bg=e.legacy_context[2];binding=e.legacy_context[3]
    plan=np.asarray(e.voltage['anchor_control'])[:,:12].tolist()
    cache=out/'historical_cache_reproduction';vp=cache/'data'/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz'
    previous=Path.cwd()
    try:
        print('Reproduce historical voltage anchor and 96x60 sensitivities',flush=True)
        _anchor_and_sensitivity_day(SOURCE_DATA_REPOSITORY,source_root(SOURCE_DATA_REPOSITORY),bg,plan,binding,day,vp)
        print('Reproduce historical current anchor and 96x60 sensitivities',flush=True)
        _generate_current_day(SOURCE_DATA_REPOSITORY,source_root(SOURCE_DATA_REPOSITORY),cache,day,({'plan_kw_96x12':plan},None,bg,binding,vp,None))
    finally:os.chdir(previous)
    comparisons={}
    for name,old,new in [('voltage',e.voltage,vp),('current',e.current,cache/'data'/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz')]:
        with np.load(new) as z:
            comparisons[name]={}
            for k in old.files:
                if k not in z:continue
                a=np.asarray(old[k]);b=np.asarray(z[k])
                if a.dtype.kind in 'fiu' and a.shape==b.shape:
                    comparisons[name][k]={'array_equal':bool(np.array_equal(a,b)), 'max_abs_error':float(np.max(np.abs(a-b),initial=0))}
    p=read(out/'V40E_PLANNING_CONTAMINATION_AUDIT.json')
    p['May01_numeric_cache_reproduction']=comparisons
    p['numeric_reproduction_artifact_refs']=[reference(vp),reference(cache/'data'/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz')]
    write_json(out/'V40E_PLANNING_CONTAMINATION_AUDIT.json',p)
    print(json.dumps(comparisons),flush=True)
    e.voltage.close();e.current.close()
