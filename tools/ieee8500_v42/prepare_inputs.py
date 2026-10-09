"""Copy exact, read-only authorities into the isolated namespace; no launchers."""
from __future__ import annotations

import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ieee8500_v42.common import DATA, REPORT, read, write, receipt, sha


def prepare():
    original = ROOT / 'docs/v42_may_b0_zero_margin_holdout'
    target = DATA / 'v42_inputs'
    target.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name in ('PLANNING_INPUT_BUNDLE.json', 'POWER_AUTHORITY.json', 'C1_PLANNING_COEFFICIENTS.csv', 'SOURCE_PROVENANCE.json'):
        source = original / 'INPUT/BUNDLE/DAY_20250501' / name
        shutil.copyfile(source, target / name)
        sources[name] = receipt(source)
    for name in ('PLANNING_PHYSICAL.npz', 'REFERENCE.json', 'PLANNING_FREEZE.json'):
        source = original / 'BUNDLE/DAY_20250501' / name
        shutil.copyfile(source, target / name)
        sources[name] = receipt(source)
    power = read(target / 'POWER_AUTHORITY.json')
    for key, name in [('C1', 'C1_MODEL.json'), ('C1_implementation', 'c1_affine.py')]:
        source = Path(power[key]['path'])
        if sha(source) != power[key]['sha256']:
            raise ValueError('ORIGINAL_POWER_AUTHORITY_DRIFT:' + key)
        shutil.copyfile(source, target / name)
        sources[name] = receipt(source)
    thermal = Path(power['C1_implementation']['path']).parents[1] / 'v28/thermal.py'
    dest = target / 'source/dayahead/v28'
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(thermal, dest / 'thermal.py')
    (dest / '__init__.py').write_text('', encoding='utf8')
    (dest.parent / '__init__.py').write_text('', encoding='utf8')
    write(target / 'INPUT_SOURCE_MANIFEST.json', dict(
        original_v42_SHA=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        day='2025-05-01', role='D1_FROZEN_PLANNING_INPUT_ONLY', sources=sources,
        c1_copy_sha256=sha(target / 'c1_affine.py'), thermal_module=receipt(thermal),
        thermal_copy_sha256=sha(dest / 'thermal.py'),
        no_actual_truth_loaded=True, no_old_feeder_coefficients_loaded=True,
        background_scope='ORIGINAL_IEEE8500_STATIC_SNAPSHOT_NO_MAY01_CUSTOMER_TIME_SERIES',
        PV_scope='ORIGINAL_MASTER_UNBAL_NO_PV_OBJECTS_NO_NEW_PV_CREATED'))
    canonical = ROOT.parent / 'IEEE8500_scalability_20260910/source'
    files = []
    for p in sorted((DATA / 'feeder').iterdir()):
        if p.is_file() and p.suffix.lower() in ('.dss', '.csv', '.py'):
            source = canonical / p.name
            if not source.exists() or sha(p) != sha(source):
                raise ValueError('FEEDER_COPY_BYTE_MISMATCH:' + p.name)
            files.append(dict(name=p.name, sha256=sha(p), bytes=p.stat().st_size, original=receipt(source)))
    write(DATA / 'FEEDER_SOURCE_MANIFEST.json', dict(master='Master-unbal.dss', files=files,
        copied_unchanged=True, inherited_source_audit=receipt(canonical.parent / 'IEEE8500_SOURCE_AUDIT.md'),
        inherited_source_freeze=receipt(canonical.parent / 'FREEZE_MANIFEST.json')))
    for name in ('IEEE8500_SOURCE_AUDIT.md', 'FREEZE_MANIFEST.json'):
        shutil.copyfile(canonical.parent / name, DATA / name)
    numbers = (191, 192, 128, 129, 45, 52, 55, 62)
    def pr(number):
        return read_json_output(subprocess.check_output([
            'gh', 'pr', 'view', str(number), '--repo', 'BeaverVillage/MobileESS',
            '--json', 'number,title,state,baseRefName,headRefName,headRefOid,mergeCommit,body,url'], text=True, encoding='utf8'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        refs = list(pool.map(pr, numbers))
    write(REPORT / 'REVIEWED_GITHUB_PR_SOURCES.json', refs)
    preregistration = dict(
        schema='IEEE8500_V42_PREREGISTRATION_V1', day='2025-05-01', final_scenario_count=1,
        order=['source/model consistency', 'fixed AIDC and strict geometry/LV eligibility', 'full AC constraints',
               'Job/GPU/QoS/facility capacity', 'B0 rho target proximity', 'independent reproducibility'],
        selected_only_if_all_hard_gates_pass=True, target_rho_range=[0.80, 0.85], target_is_hard_constraint=False,
        deterministic_tie_break='minimum abs(rho_max-0.825), then minimum installed expansion, then lexicographic mapping',
        performance_of_B1_B2_B3_used_for_selection=False,
        background_scales=[1.0], background='unchanged original static snapshot; no calibration to target',
        capacity_screening=[1.0, 1.25, 1.5], workload_multiplier=1.0,
        PV='original active master inventory; zero newly invented systems',
        controls='ALL_ORIGINAL_SOURCE_AUTONOMOUS_REGCONTROL_AND_CAPCONTROL',
        source_voltage_pu=1.05, Vmin_pu=0.95, Vmax_pu=1.05,
        line_rating='original compiled NormalAmps; never tuned',
        MESS_count=6, vehicle_rating=dict(Pmax_kW=450, PCS_kVA=600, Emax_kWh=1800),
        MESS_SOC_policy='native original input SOC/efficiency constraints require certified six-vehicle adapter',
        LV_PCC_output='UNSET until interface/protection/vehicle-access proof exists',
        geometry='one common proper similarity or affine orientation preserving transform; no reflection; frozen 1m tolerances',
        sensitivity=dict(signed_positive='injection', method='central AC difference with settled base controls fixed',
                         auto_comparison='restore identical settled base then independent original controls',
                         MV_step_kW=1.0, LV_step_kW=0.1, nonlinear_step_multiple=10,
                         slots='all 96 for all 24 retained service hosts; static LV engineering diagnostics at peak slot',
                         physical_permission='hypothetical test ports only; unverified PCC capabilities never admitted to production'),
        production_Native_calls_authorized=False, fake_solver_allowed=False)
    prereg_path = REPORT / 'PREREGISTRATION.json'
    if prereg_path.exists() and read(prereg_path) != preregistration:
        raise ValueError('PREREGISTRATION_ALREADY_FROZEN')
    write(prereg_path, preregistration)
    print('Exact feeder copies, current V42 inputs, PR sources and preregistration sealed.', flush=True)


def read_json_output(value):
    import json
    return json.loads(value)


if __name__ == '__main__':
    prepare()

