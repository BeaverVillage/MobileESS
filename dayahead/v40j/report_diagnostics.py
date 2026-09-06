"""Descriptive post-selection summaries; never changes eligibility or winner."""
import json
from .contracts import OUT
from .data import read_frame
from .methods import raw_features,safety_metrics
from .firewall import ReadFirewall,write

def main():
    fw=ReadFirewall('diagnostic_reporting').install()
    try:
        selection=json.loads((OUT/'V40J_SELECTION_FREEZE.json').read_text())
        comparison=json.loads((OUT/'V40J_CONDITIONAL_CALIBRATION_REPORT.json').read_text())['comparisons']
        diagnostics=[]
        for r in comparison:
            row=read_frame(OUT/(r['id']+'_validation.parquet'))
            x=raw_features(row)
            baseline=r['baseline'];current=r['metrics']
            diagnostics.append({'id':r['id'],'point_gate':r['gates']['point'],'coverage_gate':r['gates']['coverage'],
                'GPU_active_miss_reduction_fraction':1-current['CRITICAL_SLOT_MISS_GPU_SLOTS']/baseline['CRITICAL_SLOT_MISS_GPU_SLOTS'],
                'overreserved_GPU_hours_extra_vs_C0':current['overreserved_GPU_hours']-baseline['overreserved_GPU_hours'],
                'capacity_reservation_inflation_vs_C0':current['reserved_GPU_hours']/baseline['reserved_GPU_hours'],
                'safe_duration_inflation_vs_nominal_seconds_sum':float(row.safe.sum()/row.point.sum()) if row.point.sum()>0 else None,
                'reserved_GPU_hours_savings_vs_requested':r['requested_reference']['reserved_GPU_hours']-current['reserved_GPU_hours'],
                'mean_safe_minus_nominal_seconds':float((row.safe-row.point).mean()),
                'hard_occupancy_GPU_hours':float((row.hard*row.num_gpus_req).sum()/3600),
                'tail_reserve_GPU_hours':float(((row.safe-row.hard)*row.num_gpus_req).sum()/3600)})
        row=read_frame(OUT/(comparison[0]['id']+'_validation.parquet'))
        x=raw_features(row);mask=(x.hardware=='H100')&(x.standby==1)
        anchor=row.start_time.dt.as_unit('ns').astype('int64').to_numpy()/1e9%300
        write('V40J_DIAGNOSTIC_SUMMARY.json',{'selection_status':selection['status'],'winner':selection['winner'],
            'diagnostic_only':True,'baseline_overall':comparison[0]['baseline'],
            'baseline_H100_standby':safety_metrics(row.runtime_seconds[mask],row.baseline_safe[mask],row.num_gpus_req[mask],anchor[mask]),
            'variants':diagnostics})
    finally:fw.close()

if __name__=='__main__':main()
