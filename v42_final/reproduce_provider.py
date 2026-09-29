"""Audit original fold5 daily maps and the approved final March31 snapshot."""
from .common import *
from .runtime import FrozenQ50


def main():
    provider=FrozenQ50();path=V9/'.local/fold5/VALID.parquet';f=pd.read_parquet(path)
    columns=['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','array_index','account','qos','partition']
    parameters=provider.parameters(f[columns].to_dict('records'))
    with np.load(V10/'.local/fold5/G1.npz',allow_pickle=False) as z:expected_parameters=z['val_parameters']
    parameter_error=float(np.max(abs(parameters-expected_parameters)))
    require(np.allclose(parameters,expected_parameters,rtol=1e-10,atol=1e-12),'FROZEN_HAZARD_PARAMETER_REPRODUCTION')
    states=read(V10/'CALIBRATION_STATES/fold5_ISOTONIC_ROLLING14.json')['states'];days=f.submit_time.dt.floor('D');q=np.zeros(len(f));dayrows=[]
    with np.load(V10/'.local/fold5/T3_ISOTONIC_ROLLING14_calibrated.npz',allow_pickle=False) as z:expected=z['quantiles'][:,0]
    for day in sorted(days.unique()):
        mask=days.eq(day).to_numpy();state=states[str(day)]
        q[mask]=provider.q50_parameters(parameters[mask],state)
        dayrows.append(dict(day=str(day),N=int(mask.sum()),max_abs_Q50_error_seconds=float(np.max(abs(q[mask]-expected[mask])))))
    err=float(np.max(abs(q-expected)));require(err<1e-7,'FOLD5_Q50_REPRODUCTION')
    latest=days.eq(pd.Timestamp(provider.state['day'])).to_numpy();require(latest.any(),'LATEST_STATE_REPRODUCTION_SUPPORT')
    latestq=provider.q50_parameters(parameters[latest]);latesterr=float(np.max(abs(latestq-expected[latest])))
    require(latesterr<1e-7,'LATEST_SNAPSHOT_Q50_REPRODUCTION')
    # Replaying earlier fold days with the LAST state is not the stored rolling
    # experiment. Do not relabel its whole-fold metrics as fixed-map metrics.
    receipt=dict(PASS=True,fold=5,total_rows=len(f),latest_state_rows=int(latest.sum()),
        parameter_max_abs_error=parameter_error,fold_daily_state_Q50_max_abs_error_seconds=err,
        latest_state_Q50_max_abs_error_seconds=latesterr,
        full_fold_reproduction='Matched fold5 model/preprocessing plus each original stored daily map',
        deployment_reproduction='Exact March31 map on original March31 submissions; same map held fixed for May',
        historical_metric_scope='Five-fold rolling evaluation; not a fresh metric for one fixed deployment map',
        all_sources=[rec(path),rec(V10/'.local/fold5/G1.npz'),rec(V10/'.local/fold5/T3_ISOTONIC_ROLLING14_calibrated.npz')],
        no_fit_or_calibration_update=True)
    dump('FROZEN_FOLD5_PROVIDER_REPRODUCTION.json',receipt);csv('FROZEN_FOLD5_DAILY_REPRODUCTION.csv',dayrows)
    freeze=read(OUT/'V42_RUNTIME_PROVIDER_FREEZE.json');freeze.update(deployment_pair_status='FROZEN_MATCHED_FOLD5_STUDY_PROVIDER_REPRODUCTION_PASS',
        approved_state=provider.state['day'],max_completion_used=provider.state['max_completion_used'],
        bundle_integrity=rec(provider.root/'INTEGRITY.json'),existing_final_callable_provider_modified=False)
    dump('V42_RUNTIME_PROVIDER_FREEZE.json',freeze)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
