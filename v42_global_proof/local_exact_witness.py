"""Exact full-physical local witnesses, without native optimization.

These are separate vehicle support witnesses with grid coupling removed. They
are never full-model feasible counterexamples or capacity upper bounds.
"""
from .common import *
from fractions import Fraction as F
from collections import Counter
import gzip


def q(x):return F.from_float(float(x))
def down(x):
    v=float(x);return float(np.nextafter(v,-np.inf)) if q(v)>x else v
def unpack(n):return str(n).split('[',1)[1][:-1].split(',')


def main():
    forbid_optimize();began=time.perf_counter();A,d,T,AA,dd=load()
    demand=read(OUT/'GRID_DEMAND_CERTIFICATE.json')['selected']
    gp=Path(demand['exact_artifact']['path']);assert sha(gp)==demand['exact_artifact']['sha256']
    grid=json.loads(gzip.decompress(gp.read_bytes()))
    weights={int(r['column']):F(r['coefficient']) for r in grid['weights']}
    identity_path=ROOT/'docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json'
    identity=read(identity_path);assert identity['PASS'] and identity['terminal_stay_only']
    sites=identity['graph_receipt']['sites'];initial=identity['graph_receipt']['initial_MESS_sites']
    assert len(sites)==24 and len(initial)==4
    results=[];total=F(0)
    for unit,site in initial.items():
        folder=OUT/'vehicles'/unit
        with np.load(folder/'LOCAL_PROJECTION.npz') as z:
            cols=z['columns'].copy();rows=z['rows'].copy()
            projection={k:z[k].copy() for k in ('lower','upper','types','rhs','sense')}
        for k in ('lower','upper','types'):assert np.array_equal(projection[k],d[k][cols])
        for k in ('rhs','sense'):assert np.array_equal(projection[k],dd[k][rows])
        local_rows=AA[rows].tocsr();byname={str(d['names'][j]):int(j) for j in cols}
        energy_rows=[i for i in rows if str(dd['row_names'][i])=='energy_balance'];assert len(energy_rows)==96
        chco=[];disco=[]
        for i in energy_rows:
            row=AA.getrow(i)
            chco.extend(q(a) for j,a in zip(row.indices,row.data) if str(d['names'][j]).startswith('Pch['))
            disco.extend(q(a) for j,a in zip(row.indices,row.data) if str(d['names'][j]).startswith('Pdis['))
        assert len(set(chco))==len(set(disco))==1
        ach,adis=chco[0],disco[0];assert ach<0<adis
        discharge=F(32);charge=F(30)*adis*discharge/(F(66)*-ach)
        peak=F(760)+66*(-ach)*charge
        assert peak<=1080 and peak-30*adis*discharge==760
        x={};siteid=sites.index(site)
        for j in cols:
            j=int(j);name=str(d['names'][j]);fam=name.split('[',1)[0];args=unpack(name);v=F(0)
            assert args[0]==unit
            if fam=='route_flow':
                ai=int(args[1]);v=F(int(ai<2304 and ai//96==siteid))
            elif fam=='node_activity':v=F(int(args[1]==site))
            elif fam=='charge_mode':v=F(int(int(args[-1])<66))
            elif fam=='SOC':
                t=int(args[-1]);v=F(760)+min(t,66)*(-ach)*charge-max(0,t-66)*adis*discharge
            elif fam in ('Pch','Pdis','Q'):
                if args[1]==site:
                    t=int(args[-1])
                    if fam=='Pch' and t<66:v=charge
                    elif fam=='Pdis' and t>=66:v=discharge
                    elif fam=='Q':
                        w=weights.get(j,F(0));v=F(392) if w>0 else F(-392) if w<0 else F(0)
            else:raise AssertionError(('UNEXPECTED_VEHICLE_COLUMN',name))
            assert q(d['lower'][j])<=v<=q(d['upper'][j]),('BOUND',name,str(v))
            if d['types'][j]=='B':assert v in (F(0),F(1))
            if v:x[j]=v
        maximum_inequality_slack=None;violations=[];families=Counter()
        for i in rows:
            i=int(i);lhs=F(0)
            for k in range(AA.indptr[i],AA.indptr[i+1]):
                j=int(AA.indices[k])
                if j in x:lhs+=q(AA.data[k])*x[j]
            rhs=q(dd['rhs'][i]);sense=str(dd['sense'][i]);families[str(dd['row_names'][i]).split('[',1)[0]]+=1
            if sense=='=':ok=lhs==rhs
            elif sense=='<':ok=lhs<=rhs
            elif sense=='>':ok=lhs>=rhs
            else:raise AssertionError(sense)
            if not ok:violations.append(dict(row=i,name=str(dd['row_names'][i]),sense=sense,residual=str(lhs-rhs)))
        assert not violations,violations[:5]
        support=sum(weights.get(j,F(0))*v for j,v in x.items());total+=support
        witness=dict(schema='ORIGINAL_VEHICLE_EXACT_RATIONAL_WITNESS_V1',MESS=unit,
            grid_exact_sha256=sha(gp),source_matrix_sha256=sha(PARENT/'C3A_A.npz'),source_data_sha256=sha(PARENT/'C3A_DATA.npz'),
            original_integer_route_projection_sha256=sha(identity_path),projection_sha256=sha(folder/'LOCAL_PROJECTION.npz'),
            construction=dict(initial_site=site,movement_arcs=0,all96_STAY_at_initial_site=True,
                charge_slots='0..65',discharge_slots='66..95',charge_power_exact=str(charge),discharge_power_exact='32',
                Q_kvar_exact='sign(selected_Q_coefficient)*392',mode_charge_before66=True,
                initial_SOC_exact='760',peak_SOC_exact=str(peak),terminal_SOC_exact='760',
                original_charge_energy_coefficient=str(ach),original_discharge_energy_coefficient=str(adis)),
            nonzero_values=[dict(column=j,name=str(d['names'][j]),value=str(v)) for j,v in sorted(x.items())],
            all_other_projected_values_exactly_zero=True,projection_columns=[int(j) for j in cols],
            projection_rows=[int(i) for i in rows],support_exact=str(support),
            producer_all_original_local_rows_exact_PASS=True,checked_rows=len(rows),checked_columns=len(cols),
            row_families=dict(families),scope='Original physical vehicle projection including every local B2 row; original coupled grid constraints excluded',
            no_global_integer_counterexample_claim=True,no_optimize_call=True)
        target=OUT/(unit+'_LOCAL_EXACT_WITNESS.json.gz')
        target.write_bytes(gzip.compress((json.dumps(witness,separators=(',',':'))+'\n').encode(),mtime=0))
        results.append(dict(MESS=unit,support_exact=str(support),support_lower=down(support),
            exact_artifact=dict(path=str(target),sha256=sha(target),bytes=target.stat().st_size),
            checked_rows=len(rows),checked_columns=len(cols),peak_SOC_kwh=float(peak),
            charge_power_kw=float(charge),discharge_power_kw=32.,producer_exact_replay_PASS=True))
    D=F(grid['D_exact']);margin=total-D
    report=dict(schema='EXACT_LOCAL_CAPACITY_LOWER_WITNESSES_V1',PASS=True,
        status='EXACT_LOCAL_SUPPORT_EXCEEDS_GRID_SCALAR_DEMAND' if margin>0 else 'NOT_PROVEN',
        exact_support_is_lower_bound_on_maximum_capacity=True,vehicles=results,
        sum_support_exact=str(total),sum_support_lower=down(total),D_exact=str(D),
        sum_support_minus_D_exact=str(margin),sum_support_minus_D_lower=down(margin),
        selected_scalar_direction_cannot_prove_infeasibility_even_with_exact_vehicle_physics=margin>0,
        original_full_grid_constraints_satisfied='NOT_CLAIMED',global_feasible_counterexample=False,
        independent_checker_status='PENDING',native_optimize_calls=0,
        elapsed_wall_seconds=time.perf_counter()-began)
    write(OUT/'EXACT_LOCAL_CAPACITY_LOWER_WITNESSES.json',report)
    print(json.dumps(dict(status=report['status'],sum_support=down(total),D=float(D),margin=down(margin),
        elapsed_wall_seconds=time.perf_counter()-began)),flush=True)


if __name__=='__main__':main()
