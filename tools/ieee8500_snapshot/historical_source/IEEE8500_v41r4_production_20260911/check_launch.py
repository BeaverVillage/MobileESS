from common8500 import *
import scipy.sparse as sp
import mess_runtime
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
def main():
    install_output_paths();a=MessElectricalAuthority.from_repository();traffic=mess_runtime.traffic();fn=mess_runtime.integrated_adapter()
    assert fn and len(traffic[2].service_ids)==24
    folder=P/'B1_electrical_rows';certificate=read(folder/'CERTIFICATE.json');rho=certificate['rho_implied_lower_bound']
    with np.load(folder/'PCC_IMPLIED_BOUNDS.npz') as z:lo=z['lower'];hi=z['upper']
    with np.load(PREF/'B0_REPLAY/ANCHORS.npz') as z:reference=z['x'][:,:12]
    tol=1e-9;rows=0;retained=0;proved_floor=0.
    for t in range(96):
        full=sp.load_npz(folder/f'full_{t:02}.npz');rhs=np.load(folder/f'rhs_{t:02}.npy');w=full[:,:12]
        upper=w.maximum(0)@hi[t]+w.minimum(0)@lo[t]-rhs;lower=w.maximum(0)@lo[t]+w.minimum(0)@hi[t]-rhs
        line=np.asarray(full[:,12].toarray()).ravel()==-1
        with np.load(folder/f'active_data_{t:02}.npz') as z:idx=z['original_row_indices'];b=z['rhs']
        omitted=np.ones(len(rhs),bool);omitted[idx]=False
        assert np.all(upper[omitted&~line]<=-1e-8) and np.all(upper[omitted&line]<=rho-1e-8)
        proved_floor=max(proved_floor,float(lower[line].max())-1e-8)
        active=sp.load_npz(folder/f'active_{t:02}.npz');assert (active-full[idx]).nnz==0 and np.array_equal(rhs[idx],b)
        seed=np.r_[reference[t],read(P/'B0/FINAL.json')['metrics']['max_phase_line_loading_pu']]
        assert max((full@seed-rhs).max(initial=0),0)<=tol and seed[-1]>=rho-tol
        rows+=full.shape[0];retained+=len(idx)
    assert rho<=proved_floor and abs(rho-proved_floor)<1e-12
    save(P/'EXECUTION_ADAPTER_GATE.json',dict(status='PASS',full_rows=rows,materialized_rows=retained+1,exact_redundancy_proof=True,independent_rho_floor_proof=proved_floor,no_AIDC_domain_or_objective_change=True,original_60_control_axis=NAMES,original_MESS_electrical_authority=repr(a),MESS_traffic=record(P/'MESS_TRAFFIC_AUTHORITY.json'),B0_exact=record(P/'B0/exact/AC_VALIDATION.json'),numerical_preflight=record(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),B1_search_budget_seconds=14400,B3_A1_search_budget_seconds=14400))
    print('EXECUTION_ADAPTER_GATE_PASS',rows,retained+1,flush=True)
if __name__=='__main__':main()
