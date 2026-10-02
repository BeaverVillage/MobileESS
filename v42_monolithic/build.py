import time
from collections import Counter
from scipy import sparse
import numpy as np
import gurobipy as gp
from .common import *
from .formulation import Compact
from .resources import snapshot,PeakMemory
LOCAL=ROOT.parent/'COMPACT_MONOLITHIC_LOCAL'
def stats(m):
    return dict(binary=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,total_columns=m.NumVars,rows=m.NumConstrs,nnz=m.NumNZs)
def main():
    preserve();assert read('FIXTURE_PATH_CENSUS.json')['PASS'];snapshot('FULL_BUILD');LOCAL.mkdir(exist_ok=True)
    with PeakMemory() as peak,gp.Env(params={'OutputFlag':0}) as env:
        start=time.perf_counter();o=original(env);original_read=time.perf_counter()-start;g,sites,initial,bundle,battery=graph_inputs()
        start=time.perf_counter();c=Compact(o,g,initial,96);transform=time.perf_counter()-start
        n=c.build(env);print('FULL BUILD',stats(n),flush=True)
        from v42_certificate.common import load_start,original_validation,matrix_validation
        names,values=load_start();assert np.array_equal(names,c.old_names),'START_AXIS_DRIFT'
        mapped=c.forward(values);reconstructed=c.inverse(mapped);error=float(np.max(abs(values-reconstructed)))
        original_check=matrix_validation(o,values);compact_check=matrix_validation(n,mapped)
        physical=original_validation(c.old_names,reconstructed)
        assert original_check['PASS'] and compact_check['PASS'] and physical['valid_new_UB'] and error<=1e-12
        obj=float(c.c@mapped+o.ObjCon);assert abs(obj-UB)<=1e-12
        for p in list(c.z.values())+list(c.movement_columns.values()):assert abs(mapped[p]-round(mapped[p]))<=1e-12
        dump('MIP_START_MAPPING.json',dict(PASS=True,original_UB=UB,compact_objective=obj,reconstruction_error=error,
            original_matrix=original_check,compact_matrix=compact_check,fixing=False,source='docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz'))
        dump('MIP_START_PHYSICAL_VALIDATION.json',dict(PASS=True,validator='Inherited independent original route/SOC/PCS16/grid/rho validator on inverse reconstruction',result=physical))
        original_stats=stats(o);compact_stats=stats(n)
        reduction=1-n.NumBinVars/o.NumBinVars
        arc_binaries=len(c.arc_columns);stay_binaries=len(c.stays);movements=len(c.movement_columns)
        assert arc_binaries==207928 and movements+stay_binaries==arc_binaries
        # Every native reachable scientific route is retained, including unit-specific IDs.
        assert set(c.movement_columns)=={key for key,j in c.arc_columns.items() if g[key[1]][-1] is not None}
        assert sum(c.old_types=='B')==arc_binaries+384 and sum(c.types=='B')==len(c.nodes)+len(c.selectors)+384
        count=dict(original=original_stats,compact=compact_stats,route_binaries=arc_binaries,removed_stay_binaries=stay_binaries,
            node_activity_binaries=len(c.nodes),parallel_selector_binaries=len(c.selectors),charge_mode_binaries=384,
            continuous_movement_flows=movements-len(c.selectors),other_continuous=108431,
            all_graph_arcs=len(g),native_movement_records=len(g)-24*96,initial_sites=initial,
            actual_reachable_nodes_by_unit=dict(Counter(k[0] for k in c.nodes)),
            symbolic_zero_unit_arcs=len(initial)*len(g)-arc_binaries,no_new_pruning=True)
        dump('FULL_DOMAIN_CENSUS.json',dict(PASS=True,**count))
        dump('BINARY_REDUCTION_REPORT.json',dict(PASS=reduction>=.8,binary_reduction_percent=100*reduction,
            total_column_change_percent=100*(n.NumVars/o.NumVars-1),row_change_percent=100*(n.NumConstrs/o.NumConstrs-1),nnz_change_percent=100*(n.NumNZs/o.NumNZs-1),
            interpretation='Integer dimension reduced; total continuous columns and sparse coupling can increase.'))
        dump('COMPACT_MODEL_STATS.json',dict(PASS=True,**compact_stats,original_read_seconds=original_read,
            exact_substitution_seconds=transform,solver_build_seconds=c.build_seconds,
            total_compact_build_seconds=transform+c.build_seconds,exact_rational_row_audits=c.exact_substitution_rows,
            original_row_count_preserved=o.NumConstrs,extra_connected_and_terminal_rows=len(c.extra_b),
            scientific_continuous_columns_unchanged=True,API_matrix_transport_exact=True,peak_worker_RSS_bytes=peak.peak))
        parallel=read('PARALLEL_ROUTE_SELECTOR_COUNT.json');parallel.update(selector_count_pending_full_build=False,actual_selector_binaries=len(c.selectors));dump('PARALLEL_ROUTE_SELECTOR_COUNT.json',parallel)
        # Freeze both maps as sparse matrices: inverse T and forward F.
        rr=[];cc=[];dd=[]
        for p,j in enumerate(c.keep):rr.append(p);cc.append(j);dd.append(1.)
        for key,p in c.z.items():
            u,s,t=key
            if t<96:
                for k in c.node_arcs[key]:rr.append(p);cc.append(c.arc_columns[u,k]);dd.append(1.)
            else:
                prev=(u,s,t-1)
                if prev in c.stays:rr.append(p);cc.append(c.stays[prev]);dd.append(1.)
                for k in c.incoming[key]:rr.append(p);cc.append(c.arc_columns[u,k]);dd.append(1.)
        forward=sparse.csr_matrix((dd,(rr,cc)),shape=(n.NumVars,o.NumVars))
        assert np.max(abs(forward@values-mapped))<=1e-12
        sparse.save_npz(LOCAL/'INVERSE_T.npz',c.T);sparse.save_npz(LOCAL/'FORWARD_F.npz',forward)
        np.savez_compressed(LOCAL/'AXIS_START.npz',original_names=c.old_names,compact_names=c.names,original_values=values,compact_values=mapped)
        sparse.save_npz(LOCAL/'COMPACT_A.npz',sparse.vstack([c.A,c.extra],format='csr'))
        np.savez_compressed(LOCAL/'COMPACT_DATA.npz',names=c.names,types=c.types,lower=c.lower,upper=c.upper,
            rhs=np.r_[c.old_b,c.extra_b],sense=np.r_[c.old_sense,c.extra_sense],objective=c.c,objcon=np.array(o.ObjCon))
        n.write(str(LOCAL/'COMPACT.mps'))
        dump('MODEL_FREEZE.json',dict(original_MPS_sha256=sha(ROOT.parent/'THRESHOLD_LOCAL/F3.mps'),compact_MPS_sha256=sha(LOCAL/'COMPACT.mps'),
            maps={p.name:sha(p) for p in [LOCAL/'INVERSE_T.npz',LOCAL/'FORWARD_F.npz',LOCAL/'AXIS_START.npz',LOCAL/'COMPACT_A.npz',LOCAL/'COMPACT_DATA.npz']},
            source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'v42_monolithic').glob('*.py'))}))
        print('MAPPING PHYSICS PASS; REDUCTION',100*reduction,flush=True)
        n.dispose();o.dispose();preserve()
if __name__=='__main__':main()
