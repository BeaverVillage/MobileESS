"""Past-only CC4 semantic summaries; horizon and target are unchanged."""
import numpy as np
from .semantic_adapter import instant

WINDOWS=(1,6,24,72)

def numeric_state(times,sem,recurrence,issue_seconds,clusters=None):
    """Arrays contain already generated submission representations, never job outcomes."""
    times=np.asarray(times);sem=np.asarray(sem);recurrence=np.asarray(recurrence)
    if sem.shape!=(len(times),32) or len(recurrence)!=len(times):raise ValueError('STATE_SHAPE')
    if clusters is not None and len(clusters)!=len(times):raise ValueError('CLUSTER_SHAPE')
    values=[];names=[];centroids={};fractions={}
    for hours in WINDOWS:
        mask=(times<issue_seconds)&(times>=issue_seconds-hours*3600)
        x=sem[mask].astype(np.float64);n=len(x)
        center=x.mean(axis=0) if n else np.zeros(32)
        centroids[hours]=center
        values.extend(center);names.extend(f'sem_state_{hours}h_{i:02}' for i in range(32))
        dispersion=float(np.mean(np.sum((x-center)**2,axis=1))) if n else 0.
        seen=float(np.mean(recurrence[mask,2::3].any(axis=1))) if n else 0.
        values.extend([n,dispersion,seen]);names.extend([f'arrivals_{hours}h',f'dispersion_{hours}h',f'recurrence_{hours}h'])
    for a,b in [(1,24),(6,72)]:
        values.append(float(np.linalg.norm(centroids[a]-centroids[b])));names.append(f'centroid_change_{a}h_{b}h')
    base_count=len(values)
    if clusters is not None:
        clusters=np.asarray(clusters)
        for hours in [1,6,24]:
            mask=(times<issue_seconds)&(times>=issue_seconds-hours*3600)
            count=np.bincount(clusters[mask].astype(int),minlength=8)
            if len(count)!=8:raise ValueError('INVALID_CLUSTER')
            frac=count/count.sum() if count.sum() else np.zeros(8);fractions[hours]=frac
            values.extend(count);names.extend(f'cluster_count_{hours}h_{i}' for i in range(8))
            values.extend(frac);names.extend(f'cluster_fraction_{hours}h_{i}' for i in range(8))
            nz=frac[frac>0];values.append(float(-np.sum(nz*np.log(nz))));names.append(f'cluster_entropy_{hours}h')
        values.extend(fractions[1]-fractions[24]);names.extend(f'cluster_change_1h_24h_{i}' for i in range(8))
    result=np.asarray(values,np.float32)
    if not np.isfinite(result).all():raise ValueError('NONFINITE_STATE')
    return result,names,base_count

def submission_state(adapter,records,issue_time,cluster_model=None):
    """Filter timestamps before accessing semantic payloads, including issue-time equality."""
    issue=instant(issue_time)
    past=[r for r in records if instant(r.submit_time)<issue and
          instant(r.submit_time).timestamp()>=issue.timestamp()-72*3600]
    past=sorted(past,key=lambda r:(instant(r.submit_time),r.job_uid))
    for r in past:r.validate(issue_time)
    sem,rec=adapter.transform([r.payload for r in past])
    clusters=cluster_model.predict(sem) if cluster_model is not None and len(sem) else np.empty(0,dtype=int) if cluster_model is not None else None
    return numeric_state([instant(r.submit_time).timestamp() for r in past],sem,rec,issue.timestamp(),clusters)
