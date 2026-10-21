"""Read immutable authorities; write exclusively to V2_add paths.

No Production module, worker, optimizer, route generator or scheduler is imported.
The official DSS compile includes CalcVoltageBases; it is a source inventory,
not a V44-input B0 measurement or a time-series AC validation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import psutil

R043 = 'affc7226a519adbe072d7debbc3ae25ea71c3487'
PR197 = '35079f458fc9d87a469ebd79e0e5d2cb7bd5fe1e'
PR199 = '23c3643681e38c8b3cf16f2d02686a78c4570cc7'
PR200 = '3b12690a627473ae111f845fbb832c7294da87f1'
PR235 = 'c4b4a72ae15467737464603d4bd8e3c2bdf092d8'
ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/v2_add'
BETA = [1., 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def save(name, value):
    p = DOC / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def table(name, fields, rows):
    with (DOC / name).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def blob(repo, ref, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{ref}:{path}'])


def restore(repo, ref, path, target, receipts):
    b = blob(repo, ref, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b)
    receipts.append(dict(source_commit=ref, source_path=path,
                         target=str(target.relative_to(ROOT)), sha256=sha(b), bytes=len(b)))
    return b


def check_receipt(day, role, r):
    p = Path(r['path'])
    out = dict(day=day, role=role, path=str(p), expected_sha256=r.get('sha256', ''),
               observed_sha256='', bytes='', status='NOT_VERIFIED', reason='')
    try:
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        out.update(observed_sha256=h.hexdigest(), bytes=p.stat().st_size)
        out['status'] = 'PASS' if out['observed_sha256'] == out['expected_sha256'] else 'SHA_MISMATCH'
    except OSError as e:
        out['reason'] = str(e)
    return out


def receipt_leaves(value, prefix=''):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield prefix, value
        else:
            for k, v in value.items():
                yield from receipt_leaves(v, prefix + '/' + k)
    elif isinstance(value, list):
        for k, v in enumerate(value):
            yield from receipt_leaves(v, prefix + '/' + str(k))


def preregister():
    registration = dict(
        experiment_id='V2_add', registered_UTC=datetime.now(timezone.utc).isoformat(),
        baseline=1., beta_BG=BETA, first_tier=BETA[:7], conditional_stress_tier=BETA[7:],
        conditional_stress_trigger='Only if 1.00..1.30 has no physically qualified target/headroom/controllability candidate; never inspect B1/B2/B3 to trigger extension',
        formula='P_BG=beta_BG*P_BG_V44_frozen; Q_BG=beta_BG*Q_BG_V44_frozen',
        alpha_BG_already_in_frozen_arrays=True, alpha_BG_reapplication=False,
        unchanged=['PV P/Q', 'AIDC Jobs/GPU/C1', 'ratings', 'route/ETA/energy', 'per-vehicle battery/P/Q/PCS'],
        common_beta_for_planning_actual=True, planning_actual_timeseries_separate=True,
        physics_required=['Planning Fresh96', 'Actual prefix24+evaluation96', 'independent Actual Fresh120',
                          'all original line-phase/both-terminal currents', 'all transformers',
                          'all nodes 0.95..1.05 pu', 'native taps/caps', 'power balance', 'PCC ports'],
        selection_order=['all input/physical gates PASS', 'B0 Actual rho 0.75..0.85 preferred, else 0.70..0.85',
                         'MV binding; daily MV-LV >=0.05 preferred plus slotwise top-congestion checks',
                         'accessible PCC and feasible 96-slot joint pilot >=0.01 preferred; >=0.02 recorded',
                         'smaller beta among otherwise equal-priority candidates'],
        tie_break='Compare target tier, MV/LV headroom preference, feasible pilot >=1pp preference, then smaller beta; no B1/B2/B3 scores',
        pilot_below_1pp='retain failure and causes; do not fabricate dispatch or relax constraints',
        beta_above_1_description='V44-derived background load stress scenario',
        no_qualified_status='NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO only after complete screening',
        PCC_policy='PR199 C2 mapping candidate fixed before scale; no outcome-based reselection',
        fallback_PCC_candidates=[], fallback_policy='physical failure requires new recorded preregistration before any alternative screening',
        selected_beta=None, B1_B2_B3_results_read=False)
    target=DOC/'BACKGROUND_SCALE_PREREGISTRATION.json'
    if target.exists():
        previous=read(target)
        registration['registered_UTC']=previous['registered_UTC']
        if previous!=registration:
            raise RuntimeError('Preregistered rules changed; preserve prior registration and record an explicit amendment before proceeding')
    else:
        save('BACKGROUND_SCALE_PREREGISTRATION.json',registration)


def snapshot(runtime, label):
    processes = []
    for p in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'memory_info', 'cpu_times']):
        try:
            d = p.info
            cmd = ' '.join(d.get('cmdline') or [])
            if p.pid != os.getpid() and ('v44_' in cmd or 'MobileESS_V44' in cmd):
                processes.append(dict(pid=p.pid, parent_pid=d['ppid'], name=d['name'], command=cmd,
                                      rss_bytes=d['memory_info'].rss,
                                      cpu_seconds=d['cpu_times'].user+d['cpu_times'].system))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    lockpaths = [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),
                 Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock'),
                 Path('D:/MobileESS_V43/runtime/V43_HEAVY_WORKER.lock')]
    locks = []
    for p in lockpaths:
        row = dict(path=str(p), exists=p.exists(), sha256=None, read_status='ABSENT')
        if p.is_file():
            try:
                row.update(sha256=sha(p.read_bytes()), read_status='READ_ONLY_SHA_RECORDED')
            except OSError as e:
                row.update(read_status='HELD_OR_NOT_READABLE', reason=str(e))
        locks.append(row)
    state = dict(UTC=datetime.now(timezone.utc).isoformat(), processes=processes, locks=locks,
                 available_RAM_bytes=psutil.virtual_memory().available,
                 process_policy='read-only observation; no terminate/priority/affinity/budget/monitor changes',
                 new_native_calls=0, new_worker_calls=0)
    save(f'CAMPAIGN_RESOURCE_{label}.json', state)
    (runtime / f'CAMPAIGN_RESOURCE_{label}.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    return state


def inventory(runtime):
    import opendssdirect as odd
    d = odd.NewContext()
    for method in ('AllowChangeDir', 'AllowForms', 'AllowEditor', 'AllowDOScmd'):
        getattr(d.Basic, method)(False)
    d.Text.Command(f'set datapath="{runtime}"')
    d.Text.Command(f'compile "{DOC / "source/feeder/Master.dss"}"')
    # Master CalcVoltageBases internally solves at nominal input. No B0 output is used.
    d.Text.Command(f'set datapath="{runtime}"')
    d.Text.Command('set mode=snapshot controlmode=off')
    d.Solution.Solve()  # Initialize NodeOrder for source inventory, no V44 inputs.
    counts = dict(electrical_nodes=d.Circuit.NumNodes(), lines=d.Lines.Count(),
                  transformers=d.Transformers.Count(), loads=d.Loads.Count(),
                  regcontrols=d.RegControls.Count(), capcontrols=d.CapControls.Count(),
                  capacitors=d.Capacitors.Count())
    lines, loads, transformers, controls, buses = [], [], [], [], {}
    for b in d.Circuit.AllBusNames():
        d.Circuit.SetActiveBus(b)
        buses[b.lower()] = dict(kv_ln=d.Bus.kVBase(), nodes=d.Bus.Nodes(), x=d.Bus.X(), y=d.Bus.Y())
    for name in d.Lines.AllNames():
        d.Lines.Name(name)
        bs = d.CktElement.BusNames()
        triplex = str(d.Lines.LineCode()).lower().startswith('tpx') or name.lower().startswith('tpx')
        enabled=bool(d.CktElement.Enabled())
        try:
            node_order=d.CktElement.NodeOrder()
            node_order_status='MEASURED'
        except Exception as e:
            if enabled:
                raise RuntimeError(f'Enabled line {name} has no initialized NodeOrder') from e
            node_order=None
            node_order_status='ORIGINAL_DISABLED_ELEMENT_NO_SOLVED_NODE_ORDER'
        lines.append(dict(name=name, buses=bs, phases=d.CktElement.NumPhases(),
                          enabled=enabled,node_order=node_order,node_order_status=node_order_status,normal_amps=d.Lines.NormAmps(),
                          emergency_amps=d.Lines.EmergAmps(), linecode=d.Lines.LineCode(),
                          length=d.Lines.Length(), units=d.Lines.Units(),
                          kv_ln=buses[bs[0].split('.')[0].lower()]['kv_ln'],
                          triplex=triplex))
    for name in d.Loads.AllNames():
        d.Loads.Name(name)
        loads.append(dict(name=name, buses=d.CktElement.BusNames(), phases=d.Loads.Phases(),
                          kw=d.Loads.kW(), kvar=d.Loads.kvar(), kv=d.Loads.kV(),
                          model=d.Loads.Model(), delta=d.Loads.IsDelta(),
                          status=d.Properties.Value('status')))
    for name in d.Transformers.AllNames():
        d.Transformers.Name(name)
        windings=[]
        for w in range(1,d.Transformers.NumWindings()+1):
            d.Transformers.Wdg(w)
            windings.append(dict(winding=w,kv=d.Transformers.kV(),kva=d.Transformers.kVA(),
                                 delta=d.Transformers.IsDelta(),tap=d.Transformers.Tap()))
        transformers.append(dict(name=name,buses=d.CktElement.BusNames(),windings=windings))
    for cls in ('RegControl','CapControl'):
        d.Basic.SetActiveClass(cls)
        for name in d.ActiveClass.AllNames():
            d.Circuit.SetActiveElement(cls+'.'+name)
            # Properties are data, never executable instructions.
            controls.append(dict(kind=cls,name=name,properties={k:d.Properties.Value(k) for k in d.CktElement.AllPropertyNames()}))
    counts['triplex_lines']=sum(r['triplex'] for r in lines)
    counts['all_loads_official_balanced_2phase_wye_208V']=all(r['phases']==2 and not r['delta'] and abs(r['kv']-.208)<1e-10 for r in loads)
    expected=dict(electrical_nodes=8531,lines=3703,triplex_lines=1177,transformers=1190)
    result=dict(engine=' '.join(odd.Basic.Version().split()), counts=counts, expected=expected,
                count_PASS=all(counts[k]==v for k,v in expected.items()),
                nominal_P_kw=math.fsum(r['kw'] for r in loads), nominal_Q_kvar=math.fsum(r['kvar'] for r in loads),
                B0_run=False, P5_applied=False,source_inventory_snapshot_solve_calls=1,
                source_inventory_snapshot_converged=bool(d.Solution.Converged()),
                compile_note='Official CalcVoltageBases plus one control-off nominal snapshot for NodeOrder; no time-series V44 AC or control pilot executed')
    save('OFFICIAL_BALANCED_INVENTORY.json',result)
    save('OFFICIAL_BALANCED_AXES.json',dict(lines=lines,loads=loads,transformers=transformers,buses=buses))
    save('OFFICIAL_ORIGINAL_CONTROLS_AND_LINECODES.json',dict(controls=controls,
         linecode_authority='Unmodified original LineCodes2.DSS and Triplex_Linecodes.dss in source/feeder; byte SHA in SOURCE_COPY_RECEIPTS.json'))
    return result,loads,buses


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--balanced-repo',type=Path,default=ROOT.parent/'ieee8500_v42_balanced_case_pr')
    ap.add_argument('--joint-repo',type=Path,default=ROOT.parent/'ieee8500_v42_high_impact_pr')
    ap.add_argument('--v1-repo',type=Path,default=Path('D:/smartds_gso_substation2_v44_r043'))
    ap.add_argument('--runtime',type=Path,default=ROOT.parent/'V2_add_runtime')
    args=ap.parse_args()
    runtime=args.runtime.resolve()
    assert runtime!=ROOT and 'V2_add' in runtime.name
    runtime.mkdir(parents=True,exist_ok=True)
    DOC.mkdir(parents=True,exist_ok=True)
    try:
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except (AttributeError,psutil.AccessDenied):
        pass
    before=snapshot(runtime,'BEFORE')
    preregister()  # Must precede any scenario measurement or candidate result.
    packages={}
    for package in ('numpy','scipy','psutil','OpenDSSDirect.py','dss-python','dss-python-backend','matplotlib'):
        try:packages[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:packages[package]='NOT_INSTALLED'
    save('RUNTIME_ENVIRONMENT.json',dict(python=sys.version,executable=sys.executable,
         runtime=str(runtime),packages=packages,
         environment='Separate V2_add venv with read-only inherited system site packages; not a fully vendored dependency closure',
         production_modules_imported=False,worker_or_solver_launched=False))
    receipts=[]
    prefix='ieee8500_v42/data/feeder/'
    paths=subprocess.check_output(['git','-C',str(args.balanced_repo),'ls-tree','-r','--name-only',PR197,prefix],text=True).splitlines()
    for path in paths:
        restore(args.balanced_repo,PR197,path,DOC/'source/feeder'/Path(path).name,receipts)
    for path in ('docs/ieee8500_v42_balanced_case/SOURCE_AUTHORITY.md',
                 'ieee8500_v42/data/IEEE8500_SOURCE_AUDIT.md'):
        restore(args.balanced_repo,PR197,path,DOC/'source/history'/Path(path).name,receipts)
    map_path='docs/ieee8500_v42_joint_pcc_reselection/C2_SCORED/JOINT_LOCATION_SELECTION.csv'
    mb=restore(args.joint_repo,PR199,map_path,DOC/'source/PR199_C2_LOCATION_SELECTION.csv',receipts)
    mapping=list(csv.DictReader(io.StringIO(mb.decode('utf-8-sig'))))
    for r in mapping:
        r['route_service_id']=r['location_id'].replace('AIDC','IDC')
        r['V2_add_acceptance']='NOT_VERIFIED_P300_Q250_PCS400_AND_SIMULTANEOUS8'
        r['V2_add_mapping_role']='PRE_FIXED_C2_CANDIDATE_NO_SCALE_SCREENING_YET'
    table('AIDC12_STA12_PCC_MAPPING.csv',list(mapping[0]),mapping)
    source_audit,loads,buses=inventory(runtime)
    manifest=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')
    assert sha((ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json').read_bytes())==sha(blob(args.v1_repo,R043,'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json'))
    checked=[]
    for day in manifest['days']:
        for role,r in receipt_leaves(day['files']):
            checked.append(check_receipt(day['day'],role,r))
    # PR235 May01 direct supplementary authority includes raw weather/jobs/archive receipts.
    v1prefix='docs/smartds_gso_substation2_v44_r043/'
    primary=blob(args.v1_repo,PR235,v1prefix+'PRIMARY_MAY01_SOURCE_AUTHORITY.csv')
    for r in csv.DictReader(io.StringIO(primary.decode('utf-8-sig'))):
        checked.append(check_receipt('2025-05-01','PR235/'+r['role'],dict(path=r['resolved_path'],sha256=r['expected_sha256'])))
    table('MAY01_07_AUTHORITY_SHA_RECHECK.csv',list(checked[0]),checked)
    eb=restore(args.v1_repo,PR235,v1prefix+'IEEE123_FROZEN_ELECTRICAL_INPUTS.npz',DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz',receipts)
    metadata=json.loads(restore(args.v1_repo,PR235,v1prefix+'ELECTRICAL_ARRAY_SHA256.json',DOC/'input/PR235_ELECTRICAL_ARRAY_SHA256.json',receipts))
    arraychecks=[]
    arrays=np.load(io.BytesIO(eb),allow_pickle=False)
    for name,r in metadata['arrays'].items():
        buffer=io.BytesIO();np.save(buffer,arrays[name],allow_pickle=False)
        observed=sha(buffer.getvalue())
        arraychecks.append(dict(name=name,shape=list(arrays[name].shape),expected_sha256=r['sha256_npy'],
                                observed_sha256=observed,PASS=observed==r['sha256_npy']))
    table('FROZEN_ARRAY_SHA_RECHECK.csv',['name','shape','expected_sha256','observed_sha256','PASS'],arraychecks)
    # Candidate spatial arithmetic only: preserve original customer Balanced connectivity;
    # nominal powers act as weights, and are never added as operating demand.
    wp=np.array([r['kw'] for r in loads]);wp=wp/math.fsum(wp)
    wq=np.array([r['kvar'] for r in loads]);wq=wq/math.fsum(wq)
    allocation={};totals=[]
    for role in ('PLANNING','ACTUAL'):
        for quantity,weight in [('P',wp),('Q',wq)]:
            key=f'{role}_BG_{quantity}_'+('kw' if quantity=='P' else 'kvar')
            total=np.array([math.fsum(row) for row in arrays[key]])
            alloc=total[:,None]*weight[None,:]
            # Correct float summation residual on the largest receiver, without changing total.
            j=int(np.argmax(weight))
            for i in range(len(total)):
                alloc[i,j]+=total[i]-math.fsum(alloc[i])
            allocation[f'{role}_{quantity}']=alloc
            for t in range(len(total)):
                totals.append(dict(role=role,slot=t,evaluation_slot=t-(24 if role=='ACTUAL' else 0),
                                   quantity=quantity,beta_BG=1.,source_total=total[t],allocated_total=math.fsum(alloc[t]),
                                   absolute_error=abs(total[t]-math.fsum(alloc[t])),status='ARITHMETIC_ONLY_NOT_AC_INPUT'))
    np.savez_compressed(DOC/'input/IEEE8500_BG_ALLOCATION_CANDIDATE.npz',**allocation)
    table('BG_CUSTOMER_ALLOCATION_TOTALS.csv',list(totals[0]),totals)
    native=read(manifest['days'][0]['files']['native']['path'])
    jobs=native['known_population']
    windows=read(manifest['days'][0]['files']['windows']['path'])
    window_by_uid={r['job_id']:r for r in windows}
    eligible_jobs=[r for r in jobs if r.get('planning_eligible')]
    assert all(r['job_uid'] in window_by_uid for r in eligible_jobs)
    effective_windows=dict(
        source='WINDOWS.json, applied by original v42_may_campaign_native90/bindings.py:check_a_cells',
        source_sha256=sha(Path(manifest['days'][0]['files']['windows']['path']).read_bytes()),
        rows=len(windows),eligible_known_jobs=len(eligible_jobs),
        effective_can_timeshift_count=sum(bool(window_by_uid[r['job_uid']]['can_timeshift']) for r in eligible_jobs),
        positive_service_can_timeshift_count=sum(bool(window_by_uid[r['job_uid']]['can_timeshift']) and r['service_slots']>0 for r in eligible_jobs),
        warning='Effective source window capability, not independently certified feasible flexible power')
    capability={}
    for flag in ('can_timeshift','can_prestart_place','can_checkpoint_migrate'):
        eligible=[r for r in jobs if r.get(flag) is True]
        capability[flag]=dict(job_count=len(eligible),
            GPU_gang_sum=sum(r['GPU_gang'] for r in eligible),
            warning='Sum across jobs, not simultaneous GPU or feasible flexible kW; masks alone are not a QoS/WAN/96-slot witness')
    save('AIDC_JOB_CAPABILITY_AUDIT.json',dict(known_jobs=len(jobs),capacities=native['capacities'],
         installed_GPU=sum(native['capacities'].values()),capability=capability,
         effective_windows=effective_windows,
         native_raw_masks_are_not_final_window_authority=True,
         peak_flexible_kw=None,feasible_GPUh_shift=None,status='CAPABILITY_MASKS_ONLY_NOT_VERIFIED_FEASIBLE_POWER'))
    route_path=Path(manifest['days'][0]['files']['route_table']['path'])
    routes=json.loads(gzip.decompress(route_path.read_bytes()))
    service_ids=routes['service_ids']
    assert set(r['route_service_id'] for r in mapping)==set(service_ids)
    initial=dict(native['initial_MESS_sites'])
    available=sorted(s for s in service_ids if s.startswith('STA') and s not in initial.values())
    for number,sta in zip(range(5,9),available):
        initial[f'MESS{number:02}']=sta
    assert len(initial)==8 and len(set(initial.values()))==8
    battery=dict(native['battery'])
    save('MESS8_INITIAL_STATES_AND_PORTS.json',dict(experiment_id='V2_add',status='PROPOSED_NOT_PHYSICALLY_CERTIFIED',
         original_first4_preserved=True,additional_rule='lexical first four unused original STA IDs, fixed before scale',
         initial_sites=initial,source_battery=battery,Q_limit_kvar=250.,PCS_kVA=400.,P_limit_kW=300.,
         P_Q_simultaneous='original V44 PCS constraint to be ported byte-equivalently; no independent box relaxation',
         apparent_power_at_box_corner_kVA=math.hypot(300,250),
         instantaneous_fleet_P_limit_kw=2400.,instantaneous_fleet_Q_limit_kvar=2000.,
         fleet_initial_discharge_energy_before_travel_kwh=8*(battery['initial']-battery['minimum'])*battery['eta_discharge'],
         terminal_SOC_requires_recharge=True,feasible_96slot_energy=None,
         route_table_sha256=sha(route_path.read_bytes()),route_rows=len(routes['routes']),
         service_ids=service_ids,all_initial_sites_exist=all(s in service_ids for s in initial.values()),
         physical_port_occupancy_and_PQ_acceptance='NOT_VERIFIED',
         dispatch_STAY_MOVE_fixed=False,route_ETA_energy_regeneration=False))
    save('V44_R043_INPUT_BINDING_AUDIT.json',dict(experiment_id='V2_add',source_commit=R043,
         authority_receipt_count=len(checked),authority_PASS=sum(r['status']=='PASS' for r in checked),
         unique_path_sha_receipts=len({(r['path'],r['expected_sha256']) for r in checked}),
         authority_nonPASS=[r for r in checked if r['status']!='PASS'],
         frozen_array_checks=arraychecks,planning_slots=96,actual_prefix_slots=24,actual_evaluation_slots=96,
         May01_frozen_source='PR235, rechecked exact Git bytes and NPY arrays',
         May02_07='dated authority receipts rehashed; final per-day frozen electrical arrays not exported',
         alpha_BG=1.15,alpha_BG_reapplied=False,background_allocation='nominal P/Q weights only; no original static demand added',
         allocation_max_abs_error=max(r['absolute_error'] for r in totals),
         PV='source P/Q arrays preserved; original 2.4kV Model1 to official hot-leg voltage/inverter mapping NOT_VERIFIED',
         D1='Planning and Actual remain separate; inherited as-of/source lineage limitations not silently certified',
         status='INPUT_MAPPING_NOT_VERIFIED'))
    save('SOURCE_COPY_RECEIPTS.json',receipts)
    save('V2_ADD_EXPERIMENT_IDENTITY.json',dict(experiment_id='V2_add',experiment_version='V2_add',
         baseline_commit=R043,branch='codex/v2-add-ieee8500-balanced-preflight',worktree=str(ROOT),runtime=str(runtime),
         report_directory=str(DOC),feeder='official IEEE8500 Balanced Master.dss / Loads.dss',
         AIDC=12,STA=12,MESS=8,installed_GPU=780,source_PRs=dict(PR197=PR197,PR199=PR199,PR200=PR200,PR235=PR235),
         campaign_results_merge=False,source_and_worker_mutations=0,
         stage_chain=dict(B0=['REFERENCE','ACTUAL','FRESH'],B1=['A1','ACTUAL','FRESH'],
         B2=['REFERENCE','K48_M1','M1','ACTUAL','FRESH'],
         B3=['A1_REUSE','K48_M1','M1','A2','K48_M2','M2','ACTUAL','FRESH']),
         objective='min max over ALL original line/phase/time abs(I)/original NormalAmps',
         production_solver_policy='unchanged; no optimizer execution'))
    blockers=[
        'PV voltage/phase/inverter and bus-wise power balance adapter not certified',
        'PR199 C2 dedicated hardware not yet AC-certified for V44 P300/Q250/PCS400 and 8 simultaneous vehicles',
        'IEEE8500 original controls/P5 versus V44 Planning7/Actual43 physical contract unresolved',
        'No verified 96-slot Job/route/SOC/rebound pilot; no scale B0 measured',
        '8-vehicle FULL/Compact/K48/A1/M1/A2/M2 integration and independent validator not certified']
    if before['processes'] or any(r['exists'] for r in before['locks']):
        blockers.append('Existing V44 processes/heavy-worker leases active: no conflicting long Native run')
    if any(r['status']!='PASS' for r in checked):
        blockers.append('Some dated source authority receipts failed the fresh SHA check')
    save('FINAL_GO_NO_GO.json',dict(experiment_id='V2_add',decision='NO_GO_PENDING_PREFLIGHT',
         status='INPUT_MAPPING_NOT_VERIFIED',preflight_complete=False,blockers=blockers,
         operating_AC_allowed=False,native_allowed=False,selected_beta=None,
         qualified_scenario_search_complete=False,
         no_qualified_scenario_declared=False,new_B0_timeseries_solves=0,new_native_optimize_calls=0,
         note='Not a finding that no suitable beta exists; no candidate has been physically screened'))
    save('SELECTED_SCENARIO_FREEZE.json',dict(experiment_id='V2_add',status='NOT_FROZEN',beta_BG=None,
         PCC_candidate_source_commit=PR199,PCC_candidate_sha256=sha(mb),
         PCC_acceptance='NOT_VERIFIED',initial_states='PROPOSED_NOT_CERTIFIED',reason=blockers))
    make_pending_tables(blockers)
    make_reports(source_audit,checked,dict(raw_native_masks=capability,effective_windows=effective_windows),initial,blockers)
    after=snapshot(runtime,'AFTER')
    save('READINESS_COUNTS.json',dict(source_files=len(paths),input_receipts=len(checked),
         input_PASS=sum(r['status']=='PASS' for r in checked),arrays=len(arraychecks),
         unique_path_sha_receipts=len({(r['path'],r['expected_sha256']) for r in checked}),
         array_PASS=sum(r['PASS'] for r in arraychecks),official_counts=source_audit['counts'],
         V44_processes_before=len(before['processes']),V44_processes_after=len(after['processes'])))
    print(json.dumps(read(DOC/'READINESS_COUNTS.json'),indent=2))


def make_pending_tables(blockers):
    reason='; '.join(blockers[:3])
    table('BACKGROUND_SCALE_SCREENING.csv',
          ['beta_BG','tier','status','planning_rho','actual_rho','Vmin','Vmax','transformer_rho','reason'],
          [dict(beta_BG=b,tier='PRIMARY' if b<=1.3 else 'CONDITIONAL_STRESS',status='NOT_VERIFIED',reason=reason) for b in BETA])
    table('MV_LV_LOADING_COMPARISON.csv',['beta_BG','role','slot','rho_MV','rho_LV','rho_global','H_MV_LV','H_daily','status','reason'],
          [dict(beta_BG=b,role=r,status='NOT_VERIFIED',reason='No accepted B0 time-series AC') for b in BETA for r in ['PLANNING','ACTUAL']])
    table('TOP20_GLOBAL_CRITICAL_LINES.csv',['rank','line','phase','voltage_class','slot','rho','status','reason'],
          [dict(rank=k,status='NOT_VERIFIED',reason='Global all-line/time B0 not measured') for k in range(1,21)])
    table('AIDC_MESS_SENSITIVITY.csv',['control','role','baseline_rho','controlled_rho','delta_global_pp','noise_pp','status','reason'],
          [dict(control=c,role=r,status='NOT_VERIFIED',reason='No accepted PCC/PV/B0 adapter') for c in ['AIDC_ONLY','MESS_ONLY','JOINT'] for r in ['PLANNING','ACTUAL']])
    table('FEASIBLE_96SLOT_CONTROL_PILOT.csv',['slot','AIDC_kw','MESS_P_kw','MESS_Q_kvar','SOC_kwh','route','rho_global','status','reason'],
          [dict(slot=t,status='NOT_VERIFIED',reason='No feasible certified pilot; no dispatch value invented') for t in range(96)])
    table('B0_B1_B2_B3_COMPARISON.csv',['day','arm','planning_rho','actual_rho','rho_MV','rho_LV','Vmin','Vmax','transformer_rho','UB','LB','gap','runtime_s','status','reason'],
          [dict(day=f'2025-05-{d:02}',arm=a,status='NOT_VERIFIED',reason='Primary scenario not frozen; optimizer not run') for d in range(1,8) for a in ['B0','B1','B2','B3']])


def make_reports(inv,checked,capability,initial,blockers):
    c=inv['counts'];passed=sum(r['status']=='PASS' for r in checked)
    (DOC/'IEEE8500_BALANCED_SOURCE_AUDIT.md').write_text(
        f'''# V2_add — 공식 Balanced 원본 감사

PR #197 `{PR197}` Git blob에서 공식 feeder 파일을 바이트 그대로 복원했다. `SOURCE_COPY_RECEIPTS.json`은 파일별 SHA를 기록한다. 운영 전력 크기·PV·PCC는 PR197의 BG=.552 조건에서 가져오지 않았다.

독립 DSS context의 실제 compile 결과: 전기 노드 {c['electrical_nodes']:,}, 선로 {c['lines']:,}, Triplex {c['triplex_lines']:,}, 변압기 {c['transformers']:,}, 고객 Load {c['loads']:,}, RegControl {c['regcontrols']}, CapControl {c['capcontrols']}. 사전 기준 개수 일치: {inv['count_PASS']}.

Master의 CalcVoltageBases 및 NodeOrder 초기화용 control-off 명목 snapshot 1회를 실행했다. 이것은 원본 inventory 확인이며 V44 입력 B0, 전압 적합성, 96슬롯 Fresh AC 또는 제어 민감도 결과가 아니다. P5 overlay는 적용하지 않았다. 원본 정상/비상 정격과 winding kVA는 OFFICIAL_BALANCED_AXES.json에 보존했다. 어떤 Triplex도 제거하지 않았다.

모든 공식 고객은 2상 wye .208kV 정의다. 두 반대 hot에 고객 총 P/Q를 나누는 공식 연결을 유지하며 전체 ABC 완전 평형이나 MESS의 동적 상 변환으로 해석하지 않는다. 고객별 명목 P/Q는 공간 가중치로만 사용한다. 원본 명목 부하를 V44 운영 P/Q에 더하지 않는다.

원본 명목 총 P={inv['nominal_P_kw']:.12f} kW, Q={inv['nominal_Q_kvar']:.12f} kvar. 원본 ZIP 출처/해시는 PR197 출처 감사가 권위이며 최신 배포본 재수집은 하지 않았다. 실행 엔진: {inv['engine']}.

V44 Planning 7개/Actual 43개 RegControl 계약과 공식 모델의 차이는 미해결이다. PR197 P5(Source1.04, Vreg123.5, capbank3 off)를 검토 후보로만 기록한다. Scale마다 전압제어를 조정하지 않는다.
''',encoding='utf-8')
    (DOC/'V44_TO_IEEE8500_8MESS_PORT_AUDIT.md').write_text(f'''# V2_add — r043 → IEEE8500 MESS8 이식 Gate

기준 `{R043}` 소스는 수정하지 않았다. PR200은 V42 6대 shape-only 준비이며 V44 통합 인증이 아니다. 이번에 원본 4대→8대 모델 생성·최적화는 실행하지 않았다.

검토해야 할 원본 결합: v44/inputs.py 초기 4대 roster, v44/initial_states.py, v42_may_campaign_native90/traffic.py, operations.py, m_model.py, v43_actual/planning_reference.py, v44/svr11_ac.py의 96×4 배열, v43_arms/current_ac.py, v44/svr11_frozen/v42_voltage_control/authority.py. 탐색 MOVE depth=4와 시간 quarter=4는 차량 축으로 일괄 치환하지 않는다.

A1–M1–A2–M2, K48, Adaptive Beam, Direct Joint MILP, Gap/시간/독립 FULL 및 LB/UB 인증 정책은 그대로 유지해야 한다. IEEE123 전용 노드/선로/제어기 축을 가져오지 않는다. 전체 원본 3,703개 선로와 1,177개 Triplex가 목적함수/검증 대상이다. 선로 양단 도체 전류와 실제 상을 독립 검증하고 NormalAmps를 바꾸지 않는다.

변수/제약/nonzero, 모델 생성시간, peak RAM, K48/Joint MILP 시간, UB/LB/Gap, AC/Actual/Fresh 시간은 모두 NOT_VERIFIED다. 계통과 차량 수가 동시에 증가하므로 IEEE123 4대 대비 차이를 차량 증가만의 효과로 해석하지 않는다.

P±300 kW/Q±250 kvar의 box corner는 390.512 kVA지만 기존 PCS 부등식/다각형과 충방전 mode/SOC/효율/이동 에너지 제약을 그대로 이식해야 한다. 순간 정격 2.4MW는 96슬롯 보장 운전량이 아니다. 사전 초기 STA 후보: {json.dumps(initial,ensure_ascii=False)}. 원본 첫 4개를 유지하고 나머지는 미사용 STA의 사전 lexical 순서다. 물리 수용성 PASS 이전에는 동결된 운전 초기상태로 사용하지 않는다.
''',encoding='utf-8')
    text=f'''# V2_add — 현재 Preflight 검토

판정: **NO_GO_PENDING_PREFLIGHT / INPUT_MAPPING_NOT_VERIFIED**. 버전명은 **V2_add**다. 실험·브랜치·runtime·원장은 V44 및 V1_add와 분리했다. 이번 보고서는 준비/감사 결과이며 확장성 실험 완료 보고서가 아니다.

공식 Balanced를 실제 OpenDSS에서 다시 compile해 8,531 노드, 3,703 선로, 1,177 Triplex, 1,190 변압기를 확인했다. 날짜별 원본 권위 검사 {len(checked)}행 중 {passed}행이 현재 SHA와 일치했다(고유 path/SHA 쌍 {len({(r['path'],r['expected_sha256']) for r in checked})}개; May01 보강 검사와 중복 포함). 정확한 범위는 MAY01_07_AUTHORITY_SHA_RECHECK.csv에 있다. 전체 재귀 Source Lineage나 D-1 입수 시점의 인증은 아니다. PR235의 May01 최종 전력 배열을 Git 바이트 및 .npy SHA로 다시 확인했다. Planning96과 Actual24+96을 구분하고 alpha_BG=1.15를 재적용하지 않았다.

PR199 C2 공동 PCC24 후보를 결과 탐색 전에 고정해 복원했다. 24개 기존 route service ID 대응을 확인했지만 P300/Q250/PCS400·동시8대 물리 적합성 인증은 아니다. 후보 beta=[1.00,1.05,1.10,1.15,1.20,1.25,1.30,1.40,1.50]와 판정/동률 규칙을 먼저 등록했다. B1/B2/B3 결과를 읽거나 Scale 선택에 사용하지 않았다.

## 요청한 12개 질문의 현재 답

1. V44 입력 연결: May01 원본 최종 BG/PV/AIDC P/Q 배열은 그대로 확보했다. 공식 고객 P/Q 가중치로 BG를 배분한 후보의 총량만 검증했다. PV의 2.4kV Model1→공식 hot-leg 전압/상/인버터 및 PCC24 물리 계약은 미검증이다. 후보 산술을 실제 AC 적용 완료로 표시하지 않는다.
2. beta=1.00 B0 최대 부하율: **NOT_VERIFIED**. PR197의 57.0975%는 다른 입력/조건의 과거 결과이며 이번 값으로 사용하지 않는다.
3. 최종 beta: **선정하지 않았다**. SELECTED_SCENARIO_FREEZE.json은 NOT_FROZEN이다.
4. 75~85% 달성 여부: **NOT_VERIFIED**. 후보 실패와 미실행을 구분한다.
5. MV/LV 차이: **NOT_VERIFIED**. 일별/슬롯별 전역 AC가 필요하다.
6. 병목 하류 제어 PCC: **NOT_VERIFIED**. 원본 topology와 C2 후보는 복원했지만 병목이 측정되지 않았다.
7. AIDC 실제 유연량: 설치 GPU780을 보존했다. 원본 로더가 최종 적용하는 WINDOWS.json 기준 시간 이동 허용 Job은 {capability['effective_windows']['effective_can_timeshift_count']}개다. 구형 Native raw can_timeshift 플래그 0개를 최종 유연 Job 0개로 해석하지 않는다. 아래 원본 capability 및 Window 집계는 실현 가능한 피크 kW/GPUh 이동량으로 합산하지 않는다.

```json
{json.dumps(capability,ensure_ascii=False,indent=2)}
```

8. MESS8 제어량: 대당 P±300kW/Q±250kvar/PCS400kVA, 초기/종단760kWh, SOC440~1080kWh, 충방전효율0.95를 원본에서 유지한다. 순간 합계2.4MW와 실제 96슬롯 이동/SOC/Rebound 제약을 만족한 공급량은 다르다. 후자는 NOT_VERIFIED다.
9. 96슬롯 pilot의 전역 감소량: **NOT_VERIFIED**. 진단 결과를 B1/B2/B3 성과로 표시하지 않는다.
10. B0/B1/B2/B3 차이: **NOT_VERIFIED**, 단일 시나리오 동결 및 알고리즘 통합 전 미실행.
11. B3 공동제어 추가효과: **NOT_VERIFIED**. 우열을 가정하거나 보정하지 않는다.
12. IEEE123 대비 계산량/시간/Gap: **NOT_VERIFIED**. 실제 모델/Native 실행이 없다.

## 차단 원인과 재개 조건

'''+''.join(f'- {b}\n' for b in blockers)+'''
PV/PCC/제어 하드웨어 Adapter를 독립 검증한 뒤 beta1.00부터 Fresh AC 전수 screening을 실행해야 한다. 해당 결과와 실제 feasible pilot만으로 Primary Scenario를 동결한다. 전체 후보 screening을 수행하지 않았으므로 NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO로 단정하지 않는다. 장시간 Native는 기존 캠페인 lease/실행 보호 Gate를 통과한 뒤에만 진행한다.

요청한 숫자 산출물은 빈 수치와 NOT_VERIFIED/사유를 저장했다. topology 그림은 실제 원본 정적 구조와 C2 후보만 보여준다. MV/LV 히트맵·Scale 곡선·민감도·B0~B3 그림은 실제 측정자료가 없어 생성하지 않았다. 요청한 그림들의 완료 상태는 FIGURE_READINESS.json에 기록한다.
'''
    (DOC/'FINAL_V2_ADD_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (DOC/'README_KO.md').write_text('''# V2_add

독립 IEEE8500 Balanced / AIDC12 / STA12 / MESS8 확장실험 준비.

- [현재 한국어 검토](FINAL_V2_ADD_REVIEW_KO.md)
- [실험 식별](V2_ADD_EXPERIMENT_IDENTITY.json)
- [공식 계통 감사](IEEE8500_BALANCED_SOURCE_AUDIT.md)
- [Scale 사전등록](BACKGROUND_SCALE_PREREGISTRATION.json)
- [실행 Gate](FINAL_GO_NO_GO.json)

재현: 별도 Python 환경에서 `python -B -m v2_add_preflight.audit`.
필요 라이브러리: numpy, psutil, opendssdirect.py, matplotlib(figures).
외부 권위 저장소 경로와 runtime은 CLI 인수로 지정할 수 있다.
입력 authority 파일이 없거나 SHA가 다르면 PASS를 선언하지 않는다.
이 진입점은 inventory와 입력 산술까지만 실행하며 B0/Native를 호출하지 않는다.
''',encoding='utf-8')


if __name__=='__main__':
    main()
