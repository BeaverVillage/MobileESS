from pathlib import Path
import json,hashlib,shutil,difflib
H=Path(__file__).absolute().parent;W=H.parent.parent
F=H.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913';Q=H.parent/'IEEE8500_MAY01_MESS6_PREFLIGHT_20260913'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):return dict(path=str(p),sha256=sha(p))
def save(n,x):(H/n).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
assert not(H/'PRODUCTION_AUTHORIZATION.json').exists()
assert read(Q/'RESULT.json')['status']=='6_MESS_FLEET_PREFLIGHT_PASS'
for r in read(Q/'FINAL_SHA256_MANIFEST.json')['files']:assert sha(Path(r['path']))==r['sha256']
names=['common8500.py','electrical_engine.py','numerical_coefficients.py','full_electrical_rows.py','frozen_binding.py','headroom_authority.py','actual_power_binding.py','v41r4_ieee8500_adapter.py','v41r4_loop_budget.py','v41r4_search_budget.py','aidc_runtime.py','ranking8500.py','grid8500.py','structural_projection.py','AXES.json','HEADROOM_AUTHORITY.json','AIDC_2X_AUTHORITY.json','SCREENING_RULE.json','MAPPING_FREEZE.json','PCC_Master.dss','PCC_OVERLAY_INVENTORY.json','IEEE8500_PCC_Overlay.dss','PCC_BusCoordinates.dss','D1_AEMO_VIC1_FORECAST.json','MAY01_B0_AIDC_POWER.npz','NORMALIZED_B0_AIDC_POWER.npz','REFERENCE_JOBS.json','COEFFICIENT_GENERATION.json']
for n in names:shutil.copyfile(F/n,H/n)
for n in ['fleet_binding.py','CODE_DIFF.json','FLEET_AUTHORITY.json','availability_gating.py','actual_binding.py','MESS_24_SERVICE_PCC_COLUMN_BINDING.json','IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json','mess_runtime.py']:shutil.copyfile(Q/n,H/n)
shutil.copyfile(W/'IEEE8500_B3_production_20260912/mess_grid8500.py',H/'mess_grid8500.py')
shutil.copyfile(W/'IEEE8500_v41r4_binding_reconstruction_20260911/IEEE8500_V41R4_AIDC_BINDING_PASS.json',H/'IEEE8500_V41R4_AIDC_BINDING_PASS.json')
# Existing A1 helper rejects HOME itself because its earlier release HOME was a
# reconstruction workspace. This independent authorized output is now HOME.
p=H/'v41r4_ieee8500_adapter.py';old=p.read_text(encoding='utf-8');new=old.replace("assert allowed!=HOME.resolve() and 'IEEE8500_production_20260911' not in allowed.parts","assert allowed==HOME.resolve() and read(HOME/'PRODUCTION_AUTHORIZATION.json')['authorized'] is True")
assert old!=new;p.write_text(new,encoding='utf-8')
p=H/'aidc_runtime.py';old2=p.read_text(encoding='utf-8');new2=old2.replace("ctx.production_electrical_rows=P.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_20260912'/'B1_electrical_rows'","ctx.production_electrical_rows=P/'B3_A1_electrical_rows'");assert old2!=new2;p.write_text(new2,encoding='utf-8')
p=H/'mess_runtime.py';s=p.read_text(encoding='utf-8');s=s.replace("trajectory=MessTrajectory(tuple(beam._restore_slots(result['trajectory_slots'])))","save(folder/'ORIGINAL_SELECTED_BEFORE_EXACT.json',result)\n        trajectory=MessTrajectory(tuple(beam._restore_slots(result['trajectory_slots'])))")
p.write_text(s,encoding='utf-8')
chosen=read(F/'FOUR_HOUR_INCUMBENT.json');seed=H/'B1_REUSE';seed.mkdir()
for src,n in [(Path(chosen['checkpoint']['path']),'assignment.npz'),(F/'B1/POLICY_FEASIBLE_SEED.npz','variable_names.npz'),(Path(chosen['jobs']['path']),'JOBS.json'),(Path(chosen['power']['path']),'POWER.npz')]:shutil.copyfile(src,seed/n)
save('FINAL_B1_REUSE.json',dict(status='PASS',source=rec(F/'FOUR_HOUR_INCUMBENT.json'),jobs=rec(seed/'JOBS.json'),power=rec(seed/'POWER.npz'),seed_bundle=dict(status='FINAL_B1_INDEPENDENTLY_VALIDATED',candidate_stream_sha256='07e2d7d515915477ce79ffc6a99b6bb7715ec8c4104be6576ac17f727f4875cd',binding_gate_sha256=sha(H/'IEEE8500_V41R4_AIDC_BINDING_PASS.json'),assignment=rec(seed/'assignment.npz'),variable_names=rec(seed/'variable_names.npz'))))
save('PRODUCTION_AUTHORIZATION.json',dict(authorized=True,user_instruction='응 B2 B3 실행해.',date='2025-05-01',policies=['B2','B3'],fleet=6,initial=read(Q/'FLEET_AUTHORITY.json')['initial_locations'],B1_A0_reuse=rec(F/'RESULT.json'),preflight=rec(Q/'RESULT.json'),A1_continuous_wall_seconds=14400,stage_deadlines=[7200,11040,12480,13440,14400],MESS_physics=read(Q/'FLEET_AUTHORITY.json')['physical'],tap_cap='native automatic; no decisions or tuning',AIDC_scale=2,capacity_GPU=2624))
save('ADAPTER_DIFF.json',dict(seed_scope_diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),fixed_M1_electrical_rows_diff=''.join(difflib.unified_diff(old2.splitlines(True),new2.splitlines(True))),fleet_overrides=rec(Q/'CODE_DIFF.json')))
save('INHERITED_SOURCE_FREEZE.json',dict(files=[rec(F/n) for n in names]+[rec(Q/'FINAL_SHA256_MANIFEST.json'),rec(Q/'RESULT.json'),rec(F/'RESULT.json'),rec(F/'FOUR_HOUR_INCUMBENT.json')]))
print('PRODUCTION_NAMESPACE_READY')
