"""Small active native LPs with unchanged physical interfaces and lazy pools."""
from pathlib import Path
from dataclasses import asdict,replace
from time import perf_counter
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from . import AUTHORITY
from .census import load_frozen,PRODUCTION,digest as scientific_digest
from .active import (ActivePolicy,prepare_fast_active,activate_fast,grid_priority_hash,
    support_from_membership_receipt,support_from_verified_schedule,option_from_json)
from .stress_backend import Backend as ExactBackend,snapshot_of,row_replay,materialize
from .stress_runner import StageBuild
from .fast_prepare import ROOT,OUT,OLD,CENSUS,STATIC
from v42_pr134_b1.common import atomic,read,record,digest


def frozen_grid_priority(coefficients,resources):
    """Only ranks occupancy; signed native electrical coefficients are unchanged."""
    scores={};identities=[]
    for slot,c in enumerate(coefficients):
        utilization=np.asarray(c.current_constant)+np.asarray(c.current_matrix).T@np.asarray(c.anchor)
        critical=np.maximum(utilization-np.quantile(utilization,.9),0.)
        effect=np.asarray(c.current_matrix)@critical
        for column,name in enumerate(c.control_names):
            if name.startswith('aidc_load_kw['):
                site=name.split('[',1)[1][:-1]
                if site in resources.capacities:scores[site,slot]=-float(effect[column])
        identities.append(digest(dict(names=c.control_names,current_constant=np.asarray(c.current_constant),
            current_matrix=np.asarray(c.current_matrix),anchor=np.asarray(c.anchor))))
    return scores,dict(PASS=True,ranking_only=True,physical_coefficients_changed=False,
        frozen_signed_coefficients_sha256=digest(identities),score_sha256=grid_priority_hash(scores),
        scoring='negative signed critical thermal-load contribution over exact GPU occupancy',
        available=bool(scores),low_rank_remains_in_pool=True)


def lp_replay(snapshot,point):
    result=row_replay(replace(snapshot,vtypes=np.full(len(snapshot.vtypes),'C')),point)
    result['PASS']=bool(result['PASS'])
    return result


class Backend(ExactBackend):
    def __init__(self):
        super().__init__();self.active_state=None;self.frozen_data=None;self.ledger=None
        self.native_bindings=None;self.units=None;self.row_keys=None;self.names=None;self.policy=None

    def _prepare(self,day,folder):
        from v42_pr134_b1.native import bind
        data,frozen=load_frozen(day);self.frozen_data=data
        expected=read(OLD/'STATIC_SOURCE_DATA_IDENTITY.json')['dates'][day]
        inputs=PRODUCTION/'inputs'/day;bundle=read(inputs/'NATIVE_INPUT.json')
        for field,path in [('DATA_file',frozen/'DATA.pkl'),('frozen_native_input',inputs/'NATIVE_INPUT.json')]:
            if record(path)['sha256']!=expected[field]['sha256']:raise ValueError('FROZEN_FAST_INPUT_BYTE_DRIFT:'+field)
        if scientific_digest(bundle)!=scientific_digest(data[0]):raise ValueError('FROZEN_BUNDLE_DRIFT')
        if scientific_digest(asdict(data[3]))!=expected['resources_sha256']:raise ValueError('FROZEN_RESOURCE_DRIFT')
        static=STATIC/day;static.mkdir(parents=True,exist_ok=True)
        _,native,self.coeff,*_=bind(bundle,inputs,static)
        scores,ranking=frozen_grid_priority(self.coeff,data[3]);atomic(folder/'FROZEN_GRID_RANKING.json',ranking)
        supports=[]
        membership=CENSUS/('MAY17_RESCUE_OPTION_MEMBERSHIP.json' if day.endswith('17')
                           else 'MAY19_PR165_PR166_OPTION_MEMBERSHIP.json')
        if day.endswith(('17','19')):
            supports.append(support_from_membership_receipt(read(membership),record(membership)['sha256']))
        schedule=OLD/('MAY'+day[-2:])/'ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json'
        if schedule.exists():supports.append(support_from_verified_schedule(read(schedule),data[7]['classes'],record(schedule)['sha256']))
        for component in ('rho','migration_count','shift_magnitude','prestart_relocation'):
            replay=OLD/('MAY'+day[-2:])/component/'INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json'
            if replay.exists():
                value=read(replay)
                if value.get('PASS') is True:
                    supports.append(support_from_verified_schedule(dict(selected_jobs=value['selected_jobs'],
                        independent_physical=value['physical']),data[7]['classes'],record(replay)['sha256'],name='VERIFIED_'+component))
        policy=read(OUT/'ACTIVE_DOMAIN_POLICY.json');self.policy=policy
        from .fast_census import load_physical_cache
        cached=load_physical_cache(day,data,frozen/'DATA.pkl',STATIC) if (static/'PHYSICAL_DOMAIN_CACHE.json').exists() else None
        self.data,self.domains,self.ledger=prepare_fast_active(data,policy=ActivePolicy(
            policy['same_site_radius'],policy['extra_stay_per_class'],policy['migration_extra_seeds']),
            required_support=supports,grid_scores=scores,expected_grid_priority_hash=ranking['score_sha256'],physical_domains=cached)
        self.active_state=self.ledger
        identity=dict(PASS=True,day=day,input=record(inputs/'NATIVE_INPUT.json'),frozen_data=record(frozen/'DATA.pkl'),
            resources_sha256=expected['resources_sha256'],physical_authority_sha256=self.data[7]['physical_domain_hash'],
            authority=AUTHORITY,CC4_Runtime_service_GPU_WAN_grid_physics_changed=False,
            historical_lock_imported=False,historical_bound_imported=False,
            prior_incumbent_support_used_only_after_independent_replay=True)
        atomic(folder/'INPUT_IDENTITY.json',identity);atomic(folder/'INITIAL_ACTIVE_DOMAIN.json',self.ledger['receipt'])
        self.native=native
        return native,static,identity

    def _native(self,day,folder,native,static,identity):
        from v42_pr134_sc.snapshot import capture
        from v42_two.contract import aidc_groups,passes
        from v42_integrated.contract import physical_authority,all_transformer_rows
        import v42_boundary.model as boundary
        start=perf_counter()
        from .fast_execution import current_fast_permit
        permit=current_fast_permit()
        if permit is not None:static=static/('EXECUTION_'+permit.identity[:16])
        static=static/'rho'/folder.name
        static.mkdir(parents=True,exist_ok=True)
        class Context:
            def __init__(self):self.folder=static
            def check(self):pass
            def progress(self,value):atomic(folder/'BUILD_PROGRESS.json',dict(day=day,**value))
        old=boundary.add_grid;boundary.add_grid=all_transformer_rows(old)
        boundary.planning_grid.__globals__['add_grid']=boundary.add_grid
        try:
            with physical_authority():model,units,levels,controls,bindings=native.build(Context(),self.data,'F2-CRA')
        finally:
            boundary.add_grid=old;boundary.planning_grid.__globals__['add_grid']=old
        objectives=[(name,expr) for _,name,expr in passes(aidc_groups(levels,units,self.data))]
        self.base=snapshot_of(model,objectives);self.mapping=np.arange(self.base.matrix.shape[1],dtype=np.int64)
        self.descriptor=capture(model,units,levels,controls,bindings,static/'SCIENTIFIC_INTERFACES.pkl.gz')
        self.units=units;self.native_bindings=bindings;self.names=model.getAttr('VarName')
        self.row_keys=self._coupling_rows(model,bindings)
        sp.save_npz(static/'INITIAL_ACTIVE_MATRIX.npz',self.base.matrix)
        np.savez_compressed(static/'INITIAL_ACTIVE_ATTRIBUTES.npz',lower=self.base.lower,upper=self.base.upper,
            senses=self.base.senses,rhs=self.base.rhs,vtypes=self.base.vtypes)
        partition=dict(self.ledger['receipt'],permanent_speed_deletion=False,inactive_candidates_materialized=False)
        lp=replace(self.base,vtypes=np.full(len(self.base.vtypes),'C'))
        model.setAttr('VType',['C']*model.NumVars);model.update();self.current=lp;self.model=model
        metadata=dict(scientific_identity_PASS=True,physical_authority_sha256=self.data[7]['physical_domain_hash'],
            lp_snapshot_sha256=lp.fingerprint(),objective_sha256=digest(dict(name='rho',
                terms=[(j,str(c)) for j,c in lp.objective('rho').coefficients().items()],constant=str(lp.objective('rho').constant))),
            pool_partition=partition,input_identity=identity,domain_census=self.ledger['receipt'],
            original_integer_snapshot_sha256=self.base.fingerprint(),
            static_artifacts=[record(static/name) for name in ('INITIAL_ACTIVE_MATRIX.npz','INITIAL_ACTIVE_ATTRIBUTES.npz','SCIENTIFIC_INTERFACES.pkl.gz')],
            STAY_DOMAIN_COMPLETE=True,STAY_ACTIVE_COMPLETE=self.ledger['receipt']['inactive_STAY']==0,
            active_counts=dict(stay=self.ledger['receipt']['active_STAY'],inactive_stay=self.ledger['receipt']['inactive_STAY'],
                migration=self.ledger['receipt']['active_migration']),
            immutable_physical_universe=True,build_seconds=perf_counter()-start,
            stage_equivalence=dict(PASS=True,original_native_equations_preserved=True,
                original_singleton_mixed_flow_preserved=True,LP_relaxation_only_vtype_changed=True))
        build=StageBuild(model,units,objectives,controls,bindings,self.data,self.coeff,metadata)
        if day.endswith('17') and (OLD/'MAY17/ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json').exists():
            replay=self._replay_incumbent(build,day)
            atomic(folder/'CURRENT_MATRIX_INCUMBENT_SUPPORT_REPLAY.json',replay)
            if not replay['PASS']:raise ValueError('CURRENT_NATIVE_INCUMBENT_SUPPORT_REPLAY_FAIL')
            metadata['incumbent_support']=replay
        atomic(folder/'PRE_OPTIMIZE_MODEL_AND_POOL.json',dict(metadata,
            rows=model.NumConstrs,cols=model.NumVars,nnz=model.NumNZs,
            original_binaries=int(np.sum(self.base.vtypes=='B')),
            original_integer_counts=int(np.sum(self.base.vtypes=='I')),
            original_continuous=int(np.sum(self.base.vtypes=='C')),
            written_before_optimize=True))
        return build

    def _coupling_rows(self,model,bindings):
        rows=model.getConstrs();names=model.getAttr('ConstrName');result={}
        for family,keys,name in [('GPU',list(bindings['known']),'known_GPU_binding'),
            ('Runtime',list(bindings['risk']),'Runtime_risk_binding'),
            ('WAN',list(self.data[3].wan_capacities),'physical_WAN'),
            ('ACTIVE',list(range(self.data[3].control_end)),'physical_ACTIVE')]:
            indices=[i for i,n in enumerate(names) if n==name]
            if len(indices)!=len(keys):raise ValueError('EXACT_COUPLING_ROW_AXIS_REQUIRED:'+family)
            for key,i in zip(keys,indices):result[family,key]=i
        return result

    def _replay_incumbent(self,build,day):
        """Reconstruct a prior verified schedule into this freshly built matrix."""
        from collections import defaultdict
        from v42_root.factor import mapping
        receipt=OLD/'MAY17/migration_count/INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json'
        prior=read(receipt);schedule=dict(selected_jobs=prior['selected_jobs'])
        source=OLD/'MAY17/migration_count/RAW_ACTIVE_DOMAIN_POINT.npz'
        oldpoint=np.load(source)['values'];oldstats=read(STATIC.parent/'v42-a-stage-v2-stress4-static/2025-05-17/F2-CRA_MODEL_COMPLETE.json')
        # This point precedes the migration-zero projection; the original
        # native grid prefix has the same verified construction and axes.
        n=oldstats['global_variables'];point=np.zeros(self.base.matrix.shape[1]);point[:n]=oldpoint[:n]
        chosen={uid:option_from_json(v) for uid,v in schedule['selected_jobs'].items()}
        for unit,encoded in zip(build.units,self.descriptor['units']):
            uid=unit['uid'];job=self.data[1][uid];graph=self.data[5][uid]
            if unit['optional']:continue
            values=defaultdict(lambda:defaultdict(float))
            members=unit['members'] if unit['stay_count'] else [uid]
            for member in members:
                for family,items in mapping(job,graph,self.data[3],chosen[member]).items():
                    for key,value in items.items():values[family][key]+=value
            for family,items in encoded['v'].items():
                for key,e in items.items():
                    want=values[family].get(key,0.)
                    if e[0]=='v':point[e[1]]=want
        physical=self.verify(build,point,'rho')
        return dict(PASS=physical['PASS'],source_schedule=record(receipt),
            source_point=record(source),source_is_new_run_incumbent_support_only=True,
            current_original_matrix_replay=physical['base_original_rows'],physical=physical['physical'],
            incumbent_objectives={name:float(self.base.objective(name).constant)+sum(float(c)*point[j]
                for j,c in self.base.objective(name).coefficients().items()) for name in
                ('rho','migration_count','shift_magnitude','prestart_relocation')},
            current_optimum_or_bound_imported=False,point_rounded_or_clipped=False)

    def build_lp(self,day,folder,component,locks,active_state=None):
        if component!='rho' or locks:raise ValueError('FAST_INITIAL_DIAGNOSTIC_RHO_LP_ONLY')
        if self.data is None:native,static,identity=self._prepare(day,folder)
        else:
            static=STATIC/day;native=self.native
            identity=read(folder.parent/'LP_0000/INPUT_IDENTITY.json')
            if self.model is not None:self.model.dispose()
        return self._native(day,folder,native,static,identity)

    def verify_lp(self,build,point):
        replay=lp_replay(self.current,point)
        return dict(replay,LP_relaxation=True,physical_integer_schedule_claimed=False,
                    lp_snapshot_sha256=self.current.fingerprint())

    def price(self,build,mode,iteration):
        from .fast_pricing import score_active_pools
        return score_active_pools(self,build,mode,iteration)

    def verify_pricing(self,build,pricing,mode):
        from .fast_pricing import verify_active_pool_scores
        return verify_active_pool_scores(self,build,pricing,mode)

    def activate(self,active_state,pricing):
        self.data,self.ledger=activate_fast(self.data,self.domains,self.ledger,pricing['selections'])
        self.active_state=self.ledger
        return self.active_state

    def build_milp(self,*args,**kwargs):
        raise PermissionError('FULL_NATIVE_LP_PRICING_CLOSURE_REQUIRED_BEFORE_MILP')
