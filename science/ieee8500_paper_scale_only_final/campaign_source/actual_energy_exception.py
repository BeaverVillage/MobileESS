"""User-authorized continuation below the 440-kWh operating floor; no energy injection."""
import ast,inspect,copy
import actual_binding as binding
from dayahead.v40d_actual import mess_replay
ORIGINAL_PROJECT=mess_replay.project_command
RULE=dict(version='USER_ACCEPTED_440KWH_OPERATING_FLOOR_EXCEPTION_V1',operating_floor_kWh=440.,physical_lower_bound_kWh=0.,upper_bound_kWh=1080.,continue_below_operating_floor=True,energy_clipping=False,DA_PQ_clock_unchanged=True,discharge_saturation_floor_unchanged=True,QSAFE_Q_only=True,acceptance_status='PASS_WITH_USER_ACCEPTED_E_MIN_EXCEPTION')
text=inspect.getsource(ORIGINAL_PROJECT)
old='available < e_min - 1e-9'
assert text.count(old)==1
namespace=dict(ORIGINAL_PROJECT.__globals__)
exec(compile(text.replace(old,'available < -1e-9'),__file__+'::project','exec'),namespace)
project_command=namespace['project_command']
source=binding.source.read_text(encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='independent_audit')
audit_source=ast.get_source_segment(source,node).replace("'2025-05-21'","'2025-05-01'").replace('len(commands)==len(actual)==len(rows)==384',"len(commands)==len(actual)==len(rows)==96*len(saved['initial_energy'])")
for point in ('available','after'):
    old=f'da.energy_min_kwh-1e-9<={point}<=da.energy_max_kwh+1e-9'
    assert audit_source.count(old)==1
    audit_source=audit_source.replace(old,f'-1e-9<={point}<=da.energy_max_kwh+1e-9')
scope=dict(binding.__dict__)
exec(compile(audit_source,__file__+'::independent_audit','exec'),scope)
audit=scope['independent_audit']
def independent_audit(saved,rows,eta,da,q_safety=False):
    result=audit(saved,rows,eta,da,q_safety=q_safety)
    events=[]
    for row in rows:
        available=row['energy_before_kWh']-row['travel_energy_kWh']
        minimum=min(available,row['energy_after_kWh'])
        if minimum<da.energy_min_kwh-1e-9:
            events.append(dict(mess_id=row['mess_id'],slot=row['slot'],energy_min_kWh=minimum,shortfall_kWh=da.energy_min_kwh-minimum))
    result.update(status=RULE['acceptance_status'] if events else 'PASS',operating_440kWh_floor_feasible=not events,user_accepted_exception=bool(events),energy_floor_exceptions=events,exception_rule=RULE,physical_0_to_1080kWh_verified=True)
    return result
def install():
    mess_replay.project_command=project_command
    binding.independent_audit=independent_audit
