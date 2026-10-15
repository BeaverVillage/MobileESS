"""Independent saved-point comparisons and immutable Native accounting audit."""
import argparse,csv,gzip,hashlib,json,pickle,sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import numpy as np
import scipy.sparse as sp
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.table_v_phase_diagnostics import residual_report
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
read=lambda p:json.loads(p.read_text(encoding='utf8'))
write=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8')


def audit(output):
    import gurobipy as gp
    def forbidden(*a,**k):raise AssertionError('SAVED_POINT_AUDIT_NATIVE_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS'):setattr(gp.Model,name,forbidden)
    old=Path('D:/v42_b1_only_may_20261012_03/dates/B1/2025-05-01/attempts/attempt_01')
    static=old/'output/STATIC/NATIVE/PHASE_I/S0';identity=read(old/'output/PHASE_I/S0/MODEL_IDENTITY.json')
    native=read(old/'output/PHASE_I/S0/NATIVE_RESULT.json')
    for record in (identity['matrix'],identity['attributes'],native['raw_attributes']):
        if file_record(record['path'])!=record:raise ValueError('HISTORICAL_SOURCE18R_BYTES_DRIFT')
    with np.load(static/'ATTRIBUTES.npz') as a:
        objective=Objective('Phi',tuple((int(j),Fraction(float(v))) for j,v in enumerate(a['objective']) if v))
        snapshot=LinearSnapshot(sp.load_npz(static/'MATRIX.npz'),*[a[k].copy() for k in ('lower','upper','senses','rhs','vtypes')],(objective,)).require()
    if snapshot.fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('HISTORICAL_SNAPSHOT_DRIFT')
    with np.load(static/'NATIVE_RAW.npz') as a:raw={k:a[k].copy() for k in a.files}
    folder=output/'HISTORICAL_SOURCE18R';folder.mkdir(exist_ok=True)
    historical=residual_report(snapshot,raw,folder);historical['snapshot_sha']=snapshot.fingerprint()
    write(folder/'REPLAY_COMPARISON.json',historical)
    matrix=Path('D:/v42_mess_prep_fix_20261015/PHASE_POLICY_MATRIX03')
    rec=read(matrix/'RECEIPT.json')['snapshots'][0]['record']
    if file_record(rec['path'])!=rec:raise ValueError('SAVED_CURRENT_S0_DRIFT')
    with gzip.open(rec['path'],'rb') as stream:master=pickle.load(stream)
    check=read(ROOT/'docs/v42_phase_gap_recovery_20261015/FAST_B_INDEPENDENT_VALIDATION.json')
    if file_record(check['raw']['path'])!=check['raw']:raise ValueError('FAST_B_RAW_DRIFT')
    with np.load(check['raw']['path']) as a:raw={k:a[k].copy() for k in a.files}
    folder=output/'HISTORICAL_FAST_B';folder.mkdir(exist_ok=True)
    fast_b=residual_report(master.snapshot,raw,folder,master=master)
    write(folder/'REPLAY_COMPARISON.json',fast_b)
    b=read(Path('D:/v42_mess_prep_fix_20261015/PHASE_POLICY_NATIVE04/FAST_B_EXTENDED/RESULT.json'))
    result=read(output/'NATIVE03/RESULTS.json');current=result['results'][0]
    if current['snapshot_sha']!=b['snapshot_sha'] or current['snapshot_sha']!=master.snapshot.fingerprint():
        raise ValueError('SAME_S0_COMPARISON_REQUIRED')
    oldsettings=read(old/'output/PHASE_I/S0/NATIVE_TELEMETRY.json')['solver_settings']
    rows=[]
    def row(label,kind,snap,native,status,barrier,simplex,settings,replay,presolved,peak,meaning):
        return dict(profile=label,measurement_kind=kind,snapshot_sha=snap,Native_seconds=native,status=status,
            Barrier_iterations=barrier,Simplex_iterations=simplex,Presolve=settings['Presolve'],Method=settings['Method'],
            NumericFocus=settings['NumericFocus'],FeasibilityTol=settings['FeasibilityTol'],OptimalityTol=settings['OptimalityTol'],
            ScaleFlag=settings['ScaleFlag'],Threads=settings['Threads'],Phi=replay.get('Phi',{}).get('exact'),
            primal_max_abs=replay.get('max_absolute_row_violation'),primal_max_relative=replay.get('max_relative_row_violation'),
            dual_stationarity_abs=replay.get('numerical_1e5',{}).get('native_dual_reconstruction',{}).get('maximum_absolute_error'),
            KKT_complementarity_abs=replay.get('numerical_1e5',{}).get('dual_KKT',{}).get('max_complementarity'),
            numerical_1e5_PASS=replay['numerical_1e5']['PASS'],legacy_1e6_PASS=replay['legacy_1e6']['PASS'],
            presolved_statistics=str(presolved),peak_RSS_bytes=peak,peak_RSS_scope=meaning,certified_Global_LB=None)
    rows.append(row('SOURCE18R_ORIGINAL','historical different smaller matrix',historical['snapshot_sha'],native['native_seconds'],2,
        native['BarIterCount'],native['IterCount'],oldsettings,historical,native['presolved_matrix'],native['peak_RSS_bytes'],'process lifetime; includes preceding model build'))
    rows.append(row('FAST_B','historical identical saved S0; different run conditions',b['snapshot_sha'],b['Native_Runtime'],b['status'],
        b['barrier_iterations'],None,b['settings'],fast_b,b['presolved_statistics'],None,'NOT_RECORDED'))
    rows.append(row('SOURCE18R_FAST','new identical saved S0; capped by existing Phase-I remainder',current['snapshot_sha'],current['Native_Runtime'],current['status'],
        current['BarIterCount'],current['IterCount'],current['parameters'],current['residuals'],current['presolve_lines'],current['peak_sampled_RSS_bytes'],'0.2s samples; separate diagnostic process'))
    with (output/'COMPARISON.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    stop=read(ROOT/'docs/v42_pr230_bottleneck_20261015/EXECUTION08_STOP_AUDIT.json')
    if not all(file_record(r['path'])==r for r in stop['raw_and_freeze_records']):raise ValueError('E08_RAW_FREEZE_CHANGED')
    head=read(output/'DIAGNOSTIC_HEAD.json');ledger=read(Path(head['ledger']['path']))
    if file_record(head['ledger']['path'])!=head['ledger'] or ledger.get('inflight') or ledger.get('active_stage_context'):
        raise ValueError('DIAGNOSTIC_LEDGER_NOT_RECONCILED')
    archive=read(output/'EXECUTED_SOURCE_ARCHIVE.json')
    if not all(hashlib.sha256(Path(r['archived_path']).read_bytes()).hexdigest()==r['sha256'] for r in archive['records']):
        raise ValueError('EXECUTED_SOURCE_ARCHIVE_DRIFT')
    regression=read(output/'REGRESSION_FINAL/RESULTS.json')
    summary=dict(status='SOURCE18R_RESTORED_RELAXED_ADMISSION_IMPLEMENTED_SPEED_TARGET_NOT_PROVEN',
        historical_Source18r_FAIL_preserved=True,historical_relaxed_numerical_PASS=historical['numerical_1e5']['PASS'],
        new_Native_calls=1,new_Native_seconds=current['Native_Runtime'],new_status=current['status'],
        valid_new_X_Pi_RC=False,new_current_S0_speed_success=False,
        priority_policy='SOURCE18R_FAST',priority_is_provisional_not_a_new_speed_validated_winner=True,
        retained_validated_reference='FAST_B 111.157s on identical saved S0; old run conditions',
        comparison=rows,last_barrier_diagnostic=current['barrier_progress'][-1],
        Phase_I_used_seconds=result['phase_used'],Phase_I_remaining_seconds=result['phase_remaining'],
        A1_remaining_seconds=result['A1_remaining'],planning_cycle_used_seconds=ledger['Gurobi_Native_seconds'],
        canonical_predecessor=head['ledger'],E08_Raw_and_Freeze_preserved=True,executed_sources_archived=archive['files'],
        regression=regression,physical_and_service_constraints_modified=False,
        original_P1_FULL_tolerance=1e-6,elastic_numerical_replay_tolerance=1e-5,
        Phase_I_exact_zero_requirement_preserved=True,relaxed_numerical_PASS_is_not_Global_LB=True,
        same_229_classes_preserved=True,common_path='CurrentNative / execute_current_dw for B1 A1, B3 A1/A2 and May',
        actual_native_basis_transfer_tested=False,basis_mapping_Native0_tested=True,
        DualSimplex_test='NOT_RUN_PHASE_ALLOWANCE_EXHAUSTED',solver_tolerance_1e5_test='NOT_RUN_PHASE_ALLOWANCE_EXHAUSTED',
        campaign_HOLD=True,campaign_resumed=False,Native_reset=False,P2_calls=0,R2='HOLD',IEEE8500_executed=False)
    write(output/'SUMMARY.json',summary)
    paths=[p for p in output.rglob('*') if p.is_file() and p.suffix in ('.npz','.csv') and p.name!='COMPARISON.csv']
    paths += [output/'EXECUTED_SOURCE_ARCHIVE.json']
    write(output/'LOCAL_ARTIFACT_MANIFEST.json',dict(local_only_records=[file_record(p) for p in paths]))
    print(json.dumps({k:summary[k] for k in ('status','new_Native_seconds','Phase_I_used_seconds','A1_remaining_seconds','planning_cycle_used_seconds')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    audit(p.parse_args().output)
