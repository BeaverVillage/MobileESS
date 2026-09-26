"""Six-fleet facade over the final arrival-gated Actual implementation."""
import ast,copy,math,json,hashlib
from dataclasses import replace
import numpy as np,pandas as pd
from pathlib import Path
import fleet_binding as fb
import availability_gating as gating
H=fb.H;W=H.parent.parent;ROOT=fb.ROOT
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=fb.sha
def rec(p):return dict(path=str(p),sha256=sha(p))
source=W/'IEEE8500_B2_actual_availability_gating_20260912_r3/run_actual.py'
text=source.read_text(encoding='utf-8');tree=ast.parse(text)
for name in ('Traffic','independent_audit'):
 node=next(n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
 code=ast.get_source_segment(text,node).replace("'2025-05-21'","'2025-05-01'").replace('len(commands)==len(actual)==len(rows)==384','len(commands)==len(actual)==len(rows)==96*len(saved[\'initial_energy\'])')
 if name=='independent_audit':
  substitutions={
   'SoC_before=energy/1200.,SoC_after=after/1200.':'SoC_before=energy/da.capacity_kwh,SoC_after=after/da.capacity_kwh',
   'final_SoC=energy/1200.':'final_SoC=energy/da.capacity_kwh',
   'terminal_energy_deviation_from_760_kWh=energy-760.':'terminal_energy_deviation_from_1520_kWh=energy-da.terminal_energy_kwh',
  }
  for before,after in substitutions.items():
   assert code.count(before)==1,before
   code=code.replace(before,after)
 exec(compile(code,str(source)+'::fleet6','exec'),globals())
def replay_fleet(repo,binding):
 from dayahead.v40d_actual.mess_audit import resolve_initial_states
 from dayahead.v40d_actual.mess_replay import project_command
 from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
 from dayahead.paper_analysis.storage import digest
 assert binding['day']=='2025-05-01' and binding['case'] in ('B2','B3','PREFLIGHT')
 full=read(binding['final_PQ_source'])['MESS_trajectory']
 assert len(full)==576 and {(r['mess_id'],r['slot']) for r in full}=={(m,t) for m in fb.IDS for t in range(96)}
 allowed=('mess_id','slot','service_id','p_kw','q_kvar','departure_slot','origin_service_id','destination_service_id','route_link_ids','connection_ready_slot','mode','battery_energy_kwh','soc_fraction')
 commands=[{k:c[k] for k in allowed} for c in full]
 energies={c['mess_id']:c['battery_energy_kwh'] for c in commands if c['slot']==0}
 assert set(energies)==set(fb.IDS) and set(energies.values())=={1520.}
 initial,states=resolve_initial_states(commands,fb.INITIAL,energies,{'D00_trajectory':rec(binding['final_PQ_source']),'energy_contract':rec(H/'FLEET_AUTHORITY.json')},binding['day'])
 traffic=Traffic(repo,binding['day'])
 moves=gating.realize_sequence(commands,initial,lambda c,d:traffic.realize(c,d,rec(binding['final_PQ_source'])))
 result=gating.replay(commands,moves,energies,initial,project_command,capacity_kwh=2400.,e_min=880.,e_max=2160.,pcs_kva=800.,eta_charge=.95,eta_discharge=.95,dt_hours=.25)
 saved=dict(frozen_commands=commands,moves=moves,initial_energy=energies,initial_states=states)
 base_authority=MessElectricalAuthority.from_repository()
 audit_authority=replace(base_authority,capacity_kwh=2400.,energy_min_kwh=880.,energy_max_kwh=2160.,
                         initial_energy_kwh=1520.,terminal_energy_kwh=1520.,
                         active_power_limit_kw=600.,pcs_kva=800.)
 audit_authority.validate()
 audit=independent_audit(saved,result['trajectory'],dict(eta_charge=.95,eta_discharge=.95),audit_authority)
 frame=pd.DataFrame(result['trajectory']);frame['physical_location']=frame.actual_service_id.where(frame.connected,'TRANSIT_OR_CONNECTION_DELAY')
 def vals(field):return frame.pivot(index='slot',columns='mess_id',values=field).reindex(index=range(96),columns=fb.IDS).to_numpy()
 loc=vals('actual_service_id').astype(object);loc[pd.isna(loc)]='TRANSIT_UNAVAILABLE'
 return dict(p=vals('P_EXEC'),q=vals('Q_EXEC'),locations=loc.astype(str),ids=list(fb.IDS),frame=frame,moves=moves,counters=result['counters'],frozen_commands_SHA=digest(commands),initial_states=states,audit=audit,frozen_commands=commands,initial_energy=energies,availability=result['availability'])
def install_actual():
 import dayahead.v40d_actual.mobility_inputs as mi
 mi.actual_mobility=replay_fleet
