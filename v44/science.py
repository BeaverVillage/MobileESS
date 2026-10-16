"""Offline byte and AST evidence; never claim an unbuilt model was certified."""
import ast
from pathlib import Path
import subprocess
from .common import ROOT,V43_ROOT,V43_COMMIT,DOC,record,read,digest,verify

PACKAGES=('v43','v43_actual','v43_arms','v43_corrective','v43_baseline','v43_followup',
    'v42_may_campaign_native90','v42_pr134_b1','v42_boundary','v42_final','v42_native',
    'v42_m1_research','v42_capacity','v42_regcontrol','v42_integrated','v42_a_stage_domain_v2')


def support():
    """Export only the already pinned small PR189 support inputs into V44."""
    cert=read(DOC/'../v43/GOLDEN003_CERTIFIED_NUMERICAL_CASE.json')
    rows=read(cert['source_freeze']['path'])['support'];verify(rows);result=[]
    for row in rows:
        source=Path(row['path']);relative=source.relative_to(V43_ROOT);target=ROOT/relative
        if target.exists() and target.read_bytes()!=source.read_bytes():
            if target.read_bytes().replace(b'\r\n',b'\n')!=source.read_bytes().replace(b'\r\n',b'\n'):
                raise ValueError('EXISTING_SUPPORT_DIFFERENT_BYTES:'+str(relative))
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or target.read_bytes()!=source.read_bytes():target.write_bytes(source.read_bytes())
        result.append(dict(relative=relative.as_posix(),V43=row,V44=record(target)))
    return result


def tree_sha(path):return digest(ast.dump(ast.parse(Path(path).read_text(encoding='utf-8-sig')),include_attributes=False))


def manifest():
    support_rows=support()
    rows=[];different=[];byte_drift=[]
    candidates={p for package in PACKAGES for p in (ROOT/package).rglob('*.py')}
    cert=read(DOC/'../v43/GOLDEN003_CERTIFIED_NUMERICAL_CASE.json')
    original_freeze=read(cert['source_freeze']['path'])
    start=read('D:/MobileESS_V43/runtime/may01_B2_M1_attempt002_resume001/START.json')
    for row in original_freeze['sources']+start['sources']:
        old=Path(row['path'])
        if old.suffix=='.py' and old.is_relative_to(V43_ROOT):
            rel=old.relative_to(V43_ROOT)
            if rel.parts[0] in ('v43_mess','v43_a2'):continue # separately pinned V44 adapters/overlay
            if (ROOT/rel).exists():candidates.add(ROOT/rel)
    for path in sorted(candidates):
            rel=path.relative_to(ROOT);original=V43_ROOT/rel
            row=dict(relative=rel.as_posix(),V44=record(path),V43=record(original))
            row['byte_identical']=row['V44']['sha256']==row['V43']['sha256']
            row['AST_identical']=tree_sha(path)==tree_sha(original)
            if not row['byte_identical']:byte_drift.append(rel.as_posix())
            if not row['AST_identical']:different.append(rel.as_posix())
            rows.append(row)
    external=read(DOC/'V43_MESS_REUSE_SOURCE_MANIFEST.json')['sources'];verify([r['source'] for r in external])
    adapters=[dict(relative=p.relative_to(ROOT).as_posix(),**record(p)) for p in sorted((ROOT/'v44').rglob('*.py'))]
    overlays=[]
    for folder in ('v43_mess','v43_a2'):
        for p in sorted((ROOT/'v44/frozen'/folder).glob('*.py')):
            old=V43_ROOT/folder/p.name
            if old.exists():overlays.append(dict(V43=record(old),V44=record(p),
                byte_identical=record(old)['sha256']==record(p)['sha256'],
                scope='V43_RUNTIME_PERFORMANCE_PLUS_CHECKED_B3_STAGE_AND_DATED_NAMESPACE_ADAPTER'))
    return dict(schema='V44_SCIENTIFIC_FREEZE_V1',V43_base_commit=V43_COMMIT,
        V43_runtime_overlay='B2_PERFORMANCE_AND_RESUME_REPAIRS_COMMITTED_IN_BASE;RUNTIME_BYTES_SEPARATELY_SHA_PINNED',
        unchanged_source_rows=rows,AST_drift=different,byte_drift=byte_drift,source_PASS=not different and not byte_drift,
        inherited_external_M_algorithms=external,adapters=adapters,
        runtime_overlay_sources=overlays,
        unchanged_support_inputs=support_rows,
        source_sha=digest(dict(unchanged=[(r['relative'],r['V44']['sha256']) for r in rows],
            support=[r['V44'] for r in support_rows],external=[r['source'] for r in external],adapters=[(r['relative'],r['sha256']) for r in adapters])),
        frozen_algorithms=['PR189_FAST_A1_PHASE_I_FULL_PRICING_INTEGER_RESTORATION_P1_ONLY',
            'ORIGINAL_FULL_DOMAIN_OBJECTIVE_AND_PHYSICAL_VALIDATORS','SEEDLESS_K16_K32_K48_INDEPENDENT_GLOBAL_LB',
            'ADAPTIVE_BEAM_FOUR_MESS_DIRECT_COMPACT_JOINT_MILP',
            'R0_Q50_FCFS_BASELINE','B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1','R1_FLEX30_C1_OVERRUN_PENDING',
            'CERTIFIED_CURRENT_AC_AND_INDEPENDENT_FRESH96','IEEE123_12AIDC_4MESS_0.95_1.05'],
        allowed_changes=['dated_input_and_stage_arm_IO_metadata','M_joint_1800_to_900_K48_separate_300',
            'Main1_B2two_scheduler','same_V43_performance_reuse',
            'USER_AUTHORIZED_EPOCH12_SVR11_11BANKS_40REGCONTROL_NATIVE_TIME_PHYSICS_REVISION',
            'EXPLICIT_INDEPENDENT_DAILY_INITIAL_STATE_MODEL_ASSUMPTIONS',
            'COMPLETED_STAGE_AND_RECONCILED_BINARY_M_CHECKPOINT_RESUME_NO_NATIVE_CLOCK_RESET',
            'USER_AUTHORIZED_MAY02_07_SIX_PARALLEL_FORECAST_WORKERS_MAY01_PRESERVED'],
        new_model_matrix_validation='NOT_RUN_NO_MODEL_BUILT',new_Actual_or_Fresh='NOT_EXECUTED',
        Runtime_ML='V10::T3_ISOTONIC_ROLLING14_calibrated',CC4='Q50_Q90_UNCHANGED',
        Known_policy='B1_RESEARCH_RELAXED_KNOWN_WINDOW_V1',Unknown_policy='R1_FLEX30_C1_R1_ASSUMED',
        Source_authority_promoted=False,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED',
        B3_fixes=['M2_stage_authority_and_A2_parent_labels',
            'A2_independent_acceptance_and_proof_labels','fixed_M1_PQ_materializer',
            'failed_or_incomplete_M1_handoff_rejected','same_day_A1_reuse_only'],
        stage_budgets=dict(K48=300,Joint=900,Joint_call_cap=140,A1=5400,A2=5400,A_gap=.005))
