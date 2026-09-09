"""Reproduce frozen B3 Fresh physics without optimizing or changing decisions."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np,pandas as pd
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_electrical import configure
from dayahead.v40a.grid import controls_from_trajectory
from dayahead.v41.execution import command_arrays
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v40e.mapping import corrected_mapping
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY

def main():
    run=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4'
    da=run/'2025-05-11/B3/dayahead';out=run/'audit/mission/MAY11_B3_FRESH_FORENSIC'
    out.mkdir(parents=True,exist_ok=True)
    frozen=read(da/'FROZEN_JOINT_DECISION.json');d=frozen['decision']
    before=record(da/'FROZEN_JOINT_DECISION.json')
    with np.load(da/'FROZEN_AIDC_POWER.npz') as z:power={k:z[k].copy() for k in z.files}
    ctx=configure(d['day']).load(d['day'])
    try:
        controls=controls_from_trajectory(ctx.coefficients,power['pcc'],[SimpleNamespace(**r) for r in d['MESS_trajectory']])
        nodes=list(map(str,ctx.electrical.voltage['node_names']))
        observed=pd.read_parquet(da/'grid/BUS_PHASE_VOLTAGES.parquet')
        rows=[]
        for row in observed[observed.voltage_pu>1.05].itertuples():
            t=int(row.slot);k=nodes.index(row.node);c=ctx.coefficients[t]
            predicted=float(np.sqrt(c.voltage_constant[k]+c.voltage_matrix[:,k]@controls[t]))
            rows.append(dict(slot=t,node=row.node,planning_pu=predicted,fresh_pu=row.voltage_pu,model_residual_pu=row.voltage_pu-predicted))
        mp,mq,mids,locations=command_arrays(d['MESS_trajectory'])
        trajectory=FrozenTrajectory(d['day'],'DAYAHEAD','B3',power['pcc'],power['qcc'],mp,mq,tuple(mids),locations,frozen['decision_SHA'])
        with corrected_mapping():
            result=run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=ctx.electrical,voltage=ctx.electrical.voltage,trajectory=trajectory,output=out/'fixed_replay')
        original=read(da/'FRESH_RESULT.json')['summary']
        assert abs(result.summary['Vmax_pu']-original['Vmax_pu'])<1e-10
        assert result.summary['voltage_violation_count']==original['voltage_violation_count']==6
        assert before==record(da/'FROZEN_JOINT_DECISION.json')
        write_json(out/'DIAGNOSIS.json',dict(status='CONFIRMED_PHYSICAL_VIOLATION',
            cause='Frozen nominal linear voltage prediction undershoots nonlinear OpenDSS near the upper voltage bound',
            violations=rows,original_summary=original,reproduction_summary=result.summary,decision=before,
            mapper=read(da/'audit/mapper/MAPPER_AUDIT.json'),max_setpoint_error=read(da/'FRESH_RESULT.json')['readback']['max_setpoint_error'],
            numerical_optimization_calls=0,decision_changes=0,coefficients_regenerated=0,Actual_data_read=False,
            next_step_requires_method_decision=True))
        print('PHYSICAL_VIOLATION_REPRODUCED',rows,flush=True)
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

if __name__=='__main__':main()
