"""Same submit-day cohort: lifetime mass versus actual D-day execution."""
from core import *
from prepare import H,DAY,ns,overlap
def main():
    source=next(r for r in read(BASE/'SOURCE_MANIFEST.json')['sources'] if r['purpose']=='frozen CC4 eligible job population')
    assert sha(source['path'])==source['sha256'];w=pd.read_parquet(source['path'])
    s=ns(w.submit_time);a=ns(w.start_time);b=ns(w.end_time);g=w.gpus_requested.to_numpy();mass=g*(b-a)/H;z=np.load(ROOT/'TARGETS.npz');boundary=pd.read_csv(ROOT/'TARGET_BOUNDARY_AUDIT.csv');rows=[];curves=[]
    for i,day in enumerate(DAYS):
        start=pd.Timestamp(str(day),tz=TZ).value;sel=(s>=start)&(s<start+DAY)
        curve=overlap(a[sel],b[sel],g[sel],start+np.arange(25)*H)
        assert np.isclose(curve.sum()+boundary.Dday_overlap_GPUh.iloc[i],z['T2'][i].sum(),rtol=1e-13,atol=1e-7)
        assert np.isclose(mass[sel].sum(),Y0[i].sum(),rtol=1e-13,atol=1e-7)
        rows.append(dict(day=day,role=L.split.iloc[i],same_cohort_jobs=int(sel.sum()),T0_full_lifetime_GPUh=mass[sel].sum(),same_cohort_execution_in_D_GPUh=curve.sum(),execution_after_D_GPUh=mass[sel].sum()-curve.sum(),lifetime_mass_outside_D_fraction=1-curve.sum()/mass[sel].sum() if mass[sel].sum() else None))
        curves.append(curve)
    csv('LIFETIME_PLACEMENT_AUDIT.csv',rows);np.savez_compressed(ROOT/'SAME_COHORT_EXECUTION.npz',y=np.array(curves),days=DAYS)
    f=pd.DataFrame(rows);write('LIFETIME_PLACEMENT_AUDIT.json',dict(source=source,all_days_outside_D_mass_fraction=f.execution_after_D_GPUh.sum()/f.T0_full_lifetime_GPUh.sum(),TRAIN_outside_D_mass_fraction=f.iloc[TRAIN].execution_after_D_GPUh.sum()/f.iloc[TRAIN].T0_full_lifetime_GPUh.sum(),identity='T2 daily mass = same D-submit cohort D-overlap + post-issue/pre-D00 D-overlap',PASS=True,diagnostic_only=True,selection_or_features_changed=False))
    hist=Path(source['path']).parent/'history/A/dayahead/v41/scientific_archive.py'
    write('POWER_MAPPING_AUTHORITY_AUDIT.json',dict(inspected=[dict(path=str(hist),sha256=sha(hist))],finding='Inherited scientific archive constructs site-specific GPU/IT/PCC trajectories from capacity and scheduled job assignment; it explicitly lists site allocation of global future reserve as unmodeled. This study has global future submissions, no frozen site allocation or policy decision. No new per-site power mapping or PUE is invented.',unknown_PCC_trajectory='NOT_AVAILABLE for this global target interface',optimizer_run=False))
    print('PLACEMENT_AUDIT_PASS')
if __name__=='__main__':main()
