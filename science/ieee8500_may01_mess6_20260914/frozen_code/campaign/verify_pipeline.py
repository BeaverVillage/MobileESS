"""Read-only pipeline release checks; never calls any optimizer."""
from pathlib import Path
import sys,ast,json,hashlib
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
names=['bootstrap.py','mess_worker.py','mess_runtime.py','actual_worker.py','actual_binding.py','availability_gating.py','a1_worker.py','a1_supervisor.py','mf_worker.py','finalize_campaign.py','fleet_binding.py','v41r4_loop_budget.py','v41r4_ieee8500_adapter.py','aidc_runtime.py']
names+=['numerical_repair.py','campaign_supervisor.py','physical_closure.py']
for n in names:ast.parse((H/n).read_text(encoding='utf-8'),filename=n)
authorization=read(H/'PRODUCTION_AUTHORIZATION.json');assert authorization['fleet']==6 and authorization['A1_continuous_wall_seconds']==14400
for r in read(H/'INHERITED_SOURCE_FREEZE.json')['files']:assert sha(Path(r['path']))==r['sha256']
for r in read(H/'CODE_DIFF.json'):
 assert sha(Path(r['source']))==r['source_sha256'] and sha(Path(r['override']))==r['override_sha256']
cl=(H/'v41r4_loop_budget.py').read_text(encoding='utf-8');assert "clock_pause_allowed=False" in cl
assert "ctx.production_electrical_rows=P/'B3_A1_electrical_rows'" in (H/'aidc_runtime.py').read_text(encoding='utf-8')
assert 'child.kill()' in (H/'a1_supervisor.py').read_text(encoding='utf-8')
assert "ns['independent_audit']=binding.independent_audit" in (H/'actual_worker.py').read_text(encoding='utf-8')
(H/'PIPELINE_READY.json').write_text(json.dumps(dict(status='PASS',production_authorized=True,fleet=6,A1_wall_seconds=14400,code=[dict(path=str(H/n),sha256=sha(H/n)) for n in names],source_preservation='PASS',subsequent_steps=['B2 Actual','B3 M1','B3 A1 continuous 14400s','B3 MF','B3 Actual','final SHA']),indent=2),encoding='utf-8')
print('PIPELINE_READY')
