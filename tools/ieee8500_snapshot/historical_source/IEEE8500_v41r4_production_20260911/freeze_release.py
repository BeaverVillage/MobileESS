from common8500 import *
import aidc_runtime,mess_runtime,mess_grid8500,grid8500
from dayahead.tools import run_v35r3e_r1_beam
from dayahead.v35r3e import algorithm
from dayahead.v35r3 import algorithm as r3
from dayahead.v40a import recourse
from dayahead.v39e import runtime
from dayahead.v37 import runner
def main():
    assert read(P/'EXECUTION_ADAPTER_GATE.json')['status']=='PASS'
    assert read(P/'MESS_EXECUTION_BUILD_GATE.json')['status']=='PASS'
    for f in P.glob('*.py'):compile(f.read_text(encoding='utf-8'),str(f),'exec')
    for f in read(BIND/'ORIGINAL_V41R4_SOURCE_SHA256.json')['files']:assert sha(f['path'])==f['sha256']
    code=[record(f) for f in sorted(P.glob('*.py'))]
    src={str(Path(m.__file__).absolute()) for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).absolute().is_relative_to(ROOT)}
    code += [record(f) for f in sorted(src)]
    rules=dict(date='2025-05-21',source_pu=1.04,Vreg_V=123.5,alpha8500=.5,CAPBank3='OFF',AIDC=12,MESS_service_locations=24,PCC_transformers=36,AIDC_GPUs=780,MESS_units=4,MESS_P_kW=300,MESS_PCS_kVA=400,MESS_energy_kWh=1200,B1_search_seconds=14400,B3_A1_search_seconds=14400,checkpoints_seconds=[1800,3600,7200,14400],stage_order=['B0_reference','B1','B2','B3_M1_with_final_B1_as_A0','B3_A1_with_M1_fixed','B3_MF_fixed_route_PQ'],AIDC_stage_order=['P1','P2','P3','P4','P5'],hard_voltage=[.95,1.05],hard_line_current=1.,hard_transformer_current=1.,hard_transformer_kVA=1.,stagnation_early_stop=False,objective_floor_early_stop=False,stopped_production_reuse=False,per_policy_exact_96_slot_validation=True,automatic_restart=False,electrical_solver_equivalence='All full logical rows remain authoritative; only interval-proven redundant materialized rows are omitted; AIDC domains and objectives byte-identical',MESS_search='Original K 200/400/800/FULL, beam 2/4, seed 2; original route/power/energy model. IEEE8500 numerical matrices and service PCC mapping only.')
    save(P/'PRODUCTION_RULES.json',rules)
    save(P/'PRODUCTION_RELEASE.json',dict(status='FROZEN_AUTHORIZED',authorized_by='User: IEEE8500 실행하고 모니터링 화면 띄워줘',created_unix=time.time(),code=code,rules=record(P/'PRODUCTION_RULES.json'),gate=record(P/'EXECUTION_ADAPTER_GATE.json'),MESS_gate=record(P/'MESS_EXECUTION_BUILD_GATE.json'),preflight=record(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),preflight_manifest=record(PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json'),inputs=read(P/'LAUNCH_INPUTS.json')['inputs'],traffic=record(P/'MESS_TRAFFIC_AUTHORITY.json')))
    save(P/'PRODUCTION_RELEASE_SHA256.json',record(P/'PRODUCTION_RELEASE.json'))
    print('PRODUCTION_RELEASE_FROZEN',sha(P/'PRODUCTION_RELEASE.json'),flush=True)
if __name__=='__main__':main()
