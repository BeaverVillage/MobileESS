"""Read back all screen arrays and finalize the fail-closed evidence package."""
from v41r4_may_alpha_screen import *
import shutil

def main():
    x=read(OUT/'DAYAHEAD_SCREEN_COMPLETE.json');authority=read(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json')
    assert x['selected_alpha_BG'] is None and authority['selected_alpha_BG'] is None
    assert not any(g['eligible'] for g in x['groups'])
    assert rec(ROOT/'v41r4_may_alpha_screen.py')==read(OUT/'PREDECLARED_PROTOCOL.json')['runner']
    checked=[];convergence=0;counts={k:0 for k in ('voltage','line_current','transformer_current','transformer_kVA')}
    for r in x['rows']:
        assert rec(r['arrays']['path'])==r['arrays'];z=arrays(r['arrays']['path'])
        assert z['convergence'].shape==(96,) and z['convergence'].all();convergence+=int(z['convergence'].sum())
        line=z['branch_kinds']=='line';tx=~line;v=z['voltage_pu'];c=z['phase_current_loading_pu'];k=z['transformer_total_kva_loading_pu']
        unique=list(dict.fromkeys(z['branch_names'][tx]));ix=[z['branch_names'].tolist().index(n) for n in unique]
        for name in unique:
            cols=np.flatnonzero(z['branch_names']==name)
            assert all(np.array_equal(k[:,cols[0]],k[:,j]) for j in cols)
        expected=dict(Vmin=float(v.min()),Vmax=float(v.max()),rho_max=float(c[:,line].max()),transformer_current=float(c[:,tx].max()),transformer_kVA=float(k[:,tx].max()),p95_line_loading=float(np.percentile(c[:,line],95)),p99_line_loading=float(np.percentile(c[:,line],99)))
        assert all(r[key]==value for key,value in expected.items())
        violations=dict(voltage=int(((v<.95)|(v>1.05)).sum()),line_current=int((c[:,line]>=1).sum()),transformer_current=int((c[:,tx]>=1).sum()),transformer_kVA=int((k[:,ix]>=1).sum()))
        assert violations==r['violation_counts'] and r['PASS']==(not any(violations.values()))
        for key,val in violations.items():counts[key]+=val
        assert z['regulator_taps'].shape==(96,7) and z['capacitor_states'].shape==(96,4)
        assert np.all(z['capacitor_states']==1),'FIXED_SHUNT_CHANGED'
        assert len(r['root_P_kW'])==len(r['root_Q_kvar'])==len(r['Bus83_B_voltage'])==96
        checked.append(dict(day=r['day'],alpha_BG=r['alpha_BG'],arrays=r['arrays'],strict_summary=rec(Path(r['arrays']['path']).parents[1]/'STRICT_SUMMARY.json')))
    assert len(checked)==124 and convergence==11904
    # Match two independently persisted old physical trajectories at exact same
    # candidate alphas, without any new solve or reading policy outcomes.
    equivalence=[]
    for alpha in (1.4,1.5):
        old=ROOT/'dayahead/artifacts/v41r3_scale_rebalance/screen'/f'alpha_{alpha:.3f}'/'DAYAHEAD/physics/OPENDSS_PHASE_ARRAYS.npz'
        new=OUT/'replays/DAYAHEAD'/f'alpha_{alpha:.2f}'/'2025-05-04/physics/OPENDSS_PHASE_ARRAYS.npz'
        a,b=arrays(old),arrays(new)
        same={key:(np.array_equal(a[key],b[key],equal_nan=True) if a[key].dtype.kind=='f' else np.array_equal(a[key],b[key])) for key in a}
        assert all(same.values()),same
        equivalence.append(dict(day='2025-05-04',alpha_BG=alpha,result='BIT_EXACT_ALL_ARRAYS',old=rec(old),new=rec(new),arrays=same))
    protected=read(OUT/'PROTECTED_INPUTS_AND_SOURCES.json')
    for r in protected['records']:assert rec(r['path'])==r,('PROTECTED_DRIFT',r['path'])
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
    assert assets.sha256==read(OUT/'TOPOLOGY_AND_CONTROLS.json')['source_assets']
    # A boundary regression uses stored arrays as an object, never the engine.
    r=x['rows'][0];z=arrays(r['arrays']['path']);obj=SimpleNamespace(**z,day=r['day'],elapsed_seconds=0.,opendss_version='BOUNDARY_REGRESSION')
    obj.voltage_pu[:]=1.;obj.phase_current_loading_pu[:]=0.
    obj.transformer_total_kva_loading_pu[:,obj.branch_kinds=='transformer']=0.
    li=int(np.flatnonzero(obj.branch_kinds=='line')[0]);ti=int(np.flatnonzero(obj.branch_kinds=='transformer')[0])
    obj.voltage_pu[0,0]=.95;obj.voltage_pu[1,0]=1.05
    assert strict_summary(obj,[[0.,0.]]*96,1.35,'DAYAHEAD')['PASS']
    for name,setter,restore in (
        ('voltage',lambda:obj.voltage_pu.__setitem__((1,0),np.nextafter(1.05,np.inf)),lambda:obj.voltage_pu.__setitem__((1,0),1.05)),
        ('line_current',lambda:obj.phase_current_loading_pu.__setitem__((0,li),1.),lambda:obj.phase_current_loading_pu.__setitem__((0,li),0.)),
        ('transformer_current',lambda:obj.phase_current_loading_pu.__setitem__((0,ti),1.),lambda:obj.phase_current_loading_pu.__setitem__((0,ti),0.)),
        ('transformer_kVA',lambda:obj.transformer_total_kva_loading_pu.__setitem__((0,ti),1.),lambda:obj.transformer_total_kva_loading_pu.__setitem__((0,ti),0.))):
        setter();s=strict_summary(obj,[[0.,0.]]*96,1.35,'DAYAHEAD');assert not s['PASS'] and s['violation_counts'][name]==1;restore()
    verified=dict(status='PASS',physical_replays_verified=124,converged_slots=convergence,strict_counts=counts,
        protected_files_unchanged=len(protected['records']),assets_unchanged=True,all_fixed_shunts_ON=True,
        May04_independent_historical_equivalence=equivalence,strict_boundary_regression='PASS; voltage inclusive, thermal strict, no tolerance',
        verification_source=rec(__file__),array_manifest=checked,additional_OpenDSS_solves=0,
        screen_elapsed_seconds=read(OUT/'DAYAHEAD_PROGRESS.json')['elapsed_seconds'])
    save(OUT/'V41R4_VERIFICATION.json',verified)
    raw_request=Path('C:/Users/kjw39/.codex/attachments/55c44c1f-53b7-4af1-9f2f-8eb2b900099f/pasted-text.txt')
    shutil.copyfile(raw_request,OUT/'USER_REQUEST.txt')
    report=dict(schema='V41R4_MAY_ALPHA_SCREEN_V1',status=x['status'],candidate_alphas=list(ALPHAS),available_dates=list(DAYS),missing_dates=[],
        selected_alpha_BG=None,selection_rule=authority['deterministic_selection_rule'],groups=x['groups'],all_day_alpha_results=x['rows'],
        verification=rec(OUT/'V41R4_VERIFICATION.json'),scale_authority=rec(OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json'),
        source_SHAs=protected,request=rec(OUT/'USER_REQUEST.txt'),
        Actual_B0_diagnostic=dict(status='NOT_EXECUTED_NO_SELECTED_ALPHA',PASS_days=None,FAIL_days=None,worst_Vmin=None,worst_Vmax=None,worst_rho=None,worst_transformer_current=None,worst_transformer_kVA=None,used_for_selection=False),
        selected_alpha_May02=None,selected_alpha_stress_distribution=None,
        AIDC_780_unchanged=True,AIDC_power_unchanged=True,ML_unchanged=True,
        B1_B2_B3_RESULTS_USED=False,ROBUST_B1_executed=False,FULL_MAY_policy_optimization='HOLD',
        electrical_coefficients_regenerated=0,additional_alphas_tested=[],alpha_1_60_replayed=False,
        previous_alpha_1_60_status='DEVELOPMENT_HISTORICAL_ONLY',preMay_residual_templates='RETAINED_UNCHANGED; no May S0/S1/S2 rebuild or alpha=1.60 coefficient reuse',
        worst_day_definition='Day with largest max(line loading, transformer current loading, transformer total-kVA loading, Vmax/1.05, .95/Vmin); metric-specific worst days also recorded',
        slot_axis='0..95, 15 minutes, fixed AEST; slot 0 = 00:00, slot 95 = 23:45',
        kVA_definition='Direct OpenDSS terminal total sqrt(P^2+Q^2)/unchanged winding rating; counted once per transformer per slot. Historical planning kVA metrics are not substituted.',
        stopped_reason='No candidate passes every May Day-Ahead B0 day. Fail-close before Actual, coefficients, or policies.')
    save(OUT/'V41R4_MAY_ALPHA_SCREEN.json',report)
    lines=['# V41R4 May-wide B0 background scale screen','',
        '**FAIL-CLOSE — no selected alpha_BG.** All 31 May dates were evaluated at exactly 1.35 / 1.40 / 1.45 / 1.50.',
        f'All 124 trajectories converged 96/96 ({convergence:,} slots). Four isolated processes completed physical replay in {verified["screen_elapsed_seconds"]:.1f} seconds. No coefficient generation, optimization, or additional alpha tests.','',
        '| alpha | May-wide | PASS / FAIL days | Worst day* | max rho | min V | max V | max transformer current | max transformer kVA |',
        '|---:|:---:|:---:|:---:|---:|---:|---:|---:|---:|']
    for g in x['groups']:
        lines.append(f'| {g["alpha_BG"]:.2f} | FAIL | {g["PASS_days"]} / {g["FAIL_days"]} | {g["worst_day"]} | {g["rho_max"]:.9f} | {g["Vmin"]:.9f} | {g["Vmax"]:.9f} | {g["transformer_current"]:.9f} | {g["transformer_kVA"]:.9f} |')
    lines+=['','*Worst day uses maximum normalized constraint utilization. Each metric above is its own campaign extremum; exact metric-specific dates and assets are in JSON. Voltages are pu; current and kVA are fractions of unchanged ratings.','',
        '## First failing day and limiting constraint','',
        '| alpha | First failing day | Constraint | Asset / phase | Slot (0-based) | Value |',
        '|---:|:---:|---|---|---:|---:|']
    for g in x['groups']:
        for w in g['first_failing_constraints']:
            lines.append(f'| {g["alpha_BG"]:.2f} | {g["first_failing_day"]} | {w["kind"]} | {w["asset"]} / {w["phase"]} | {w["slot"]} | {w["value"]:.12f} |')
    lines+=['','Voltage limits are inclusive [0.95, 1.05]. Line current, transformer phase current, and transformer total kVA must each be strictly below 1.0. No tolerance is applied.','',
        '## May-02 explicit direct OpenDSS recheck','',
        '| alpha | PASS | reg1a-A max current | reg1a-A max kVA | Bus83-B min V | Bus83-B max V | max line rho | system Vmin | system Vmax |',
        '|---:|:---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in x['groups']:
        r=g['May02'];lines.append(f'| {g["alpha_BG"]:.2f} | {"YES" if r["PASS"] else "NO"} | {r["reg1a_A_current"]:.9f} | {r["reg1a_A_kVA"]:.9f} | {r["Bus83_B_Vmin"]:.9f} | {r["Bus83_B_Vmax"]:.9f} | {r["rho_max"]:.9f} | {r["Vmin"]:.9f} | {r["Vmax"]:.9f} |')
    lines+=['','kVA is direct terminal total kVA divided by the frozen winding rating. These measurements do not use historical planning polygon kVA or linear scaling assumptions. The full 96-slot Bus83-B traces are in JSON and NPZ.','',
        '## Descriptive May stress distribution','',
        '| alpha | rho min | median | P75 | P90 | max | days ≥.70 | ≥.75 | ≥.80 | ≥.85 | ≥.90 | ≥.95 |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in x['groups']:
        d=g['stress_distribution'];values=[f'{g["alpha_BG"]:.2f}']+[f'{d[k]:.9f}' for k in ('min','median','P75','P90','max')]+[str(v) for v in d['days_ge'].values()]
        lines.append('| '+' | '.join(values)+' |')
    lines+=['','These distributions did not override the predeclared largest-feasible-alpha rule.','',
        '## Selected-alpha diagnostics and downstream state','',
        '- SELECTED alpha_BG = NONE.',
        '- Selected-alpha May-02 and May distribution = N/A.',
        '- Selected-alpha Actual B0 = NOT EXECUTED; PASS/FAIL day counts and extrema = N/A.',
        '- No alpha qualified. No Actual input or Actual result was used for selection.',
        '- AIDC 780 unchanged = YES; AIDC power unchanged = YES; ML unchanged = YES.',
        '- B1/B2/B3 used for alpha selection = NO; robust B1 executed = NO.',
        '- Electrical coefficient regeneration = 0; May-04 scenario rebuild = HOLD.',
        '- FULL MAY policy optimization = HOLD.',
        '- Previous alpha=1.60 = DEVELOPMENT_HISTORICAL_ONLY; its original evidence is preserved.','',
        '## Verification and artifacts','',
        f'- Recomputed 31 B0 GPU/IT/PCC arrays: bit exact with authoritative stored inputs. H4 physical cap remains 3120 GPUh.',
        f'- {len(protected["records"])} protected source/input files retained their SHA-256 hashes; feeder asset hashes and every-slot regulator/capacitor settings were unchanged.',
        '- Re-read all 124 NPZs; independently recalculated eligibility, counts, extrema, and quantiles. Verified strict threshold boundary behavior.',
        '- May-04 alpha=1.40 and 1.50: bit exact with independently stored historical native-DA trajectories for every saved array.',
        '- Every run saves regulator taps, capacitor states, full voltage/current/kVA arrays, losses, root P/Q and strict summaries under `replays/DAYAHEAD/`.',
        '- All day × alpha results, source SHAs, metric-specific worst dates and descriptive distributions are in `V41R4_MAY_ALPHA_SCREEN.json`.',
        '- The frozen negative selection is in `V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json`.','']
    (OUT/'V41R4_MAY_ALPHA_SCREEN.md').write_text('\n'.join(lines),encoding='utf-8')
    # Put the requested deliverables in the user's current shared workspace too.
    delivery=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/artifacts/v41r4_may_alpha_screen')
    delivery.mkdir(parents=True,exist_ok=True)
    delivered=[]
    for name in ('V41R4_MAY_ALPHA_SCREEN.json','V41R4_MAY_ALPHA_SCREEN.md','V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json','V41R4_VERIFICATION.json'):
        dest=delivery/name;assert not dest.exists();shutil.copyfile(OUT/name,dest);assert rec(dest)['sha256']==rec(OUT/name)['sha256'];delivered.append(rec(dest))
    save(OUT/'DELIVERY_MANIFEST.json',dict(status='PASS',files=delivered,full_replay_evidence=str(OUT)))
    print('VERIFIED_FAIL_CLOSE',len(checked),convergence,'source files unchanged',len(protected['records']),flush=True)
    print('DELIVERED',delivery,flush=True)

if __name__=='__main__':main()
