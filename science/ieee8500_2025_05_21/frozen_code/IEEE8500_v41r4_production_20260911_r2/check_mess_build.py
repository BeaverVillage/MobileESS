from common8500 import *
import mess_runtime,gurobipy as gp
from dayahead.v35.execution import MESS_INITIAL
from dayahead.v41r1.feasible_seed import row_audit
class Built(Exception):pass
def main():
    install_output_paths();cc=mess_runtime.coefficients();tr=mess_runtime.traffic();fn=mess_runtime.integrated_adapter()
    mapping={r['service']:r['PCC'] for r in read(PREF/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
    with np.load(P/'B0/POWER.npz') as z:pcc=z['pcc'].copy()
    original=gp.Model.optimize;seen=[]
    def build_only(model,*a,**kw):
        model.update();values=np.array(model.getAttr('Start',model.getVars()))
        for v in model.getVars():
            if v.VarName=='v34_rho_planning':values[v.index]=read(P/'B0/FINAL.json')['metrics']['max_phase_line_loading_pu']
        audit=row_audit(model,values)
        seen.append(audit)
        save(P/'MESS_EXECUTION_BUILD_GATE.json',dict(status=audit['status'],model=model.ModelName,variables=model.NumVars,linear_rows=model.NumConstrs,general_rows=model.NumGenConstrs,zero_stay_seed=audit,optimization_calls=0,original_MESS_initial_locations=dict(MESS_INITIAL),power_kW=300,PCS_kVA=400,energy_kWh=1200,grid_nodes=8639,control_columns=60))
        model.dispose();raise Built()
    gp.Model.optimize=build_only
    try:
        mid=sorted(MESS_INITIAL)[0]
        fn(case='B2',aidc_pcc_kw_96x12=pcc,electrical_context=None,voltage_authority=mess_runtime.Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes'])),current_authority=mess_runtime.Authority(),route_table=tr[2],service_to_pcc=mapping,initial_service_by_mess={mid:MESS_INITIAL[mid]},grid_coefficients=cc)
    except Built:pass
    finally:gp.Model.optimize=original
    assert len(seen)==1 and seen[0]['status']=='PASS';print('MESS_FULL_BUILD_SEED_PASS',flush=True)
if __name__=='__main__':main()
