"""Gated exact-five-fold bridge; original V13 files are read-only."""
from common16 import *
sys.path.insert(0,str(V13))
sys.path.insert(0,str(REPO))
import common13,model13,train13
from v42.semantic_adapter import SubmissionSemanticRecord
from semantic_payload_v2_candidate import SubmissionSemanticPayloadV2,FIELD_MISSING
from neighbors16 import CompletedNeighborIndex
import lightgbm as lgb,pickle,time,gc

APPROVED=['user','submit_line']

class RichCategoryAdapter:
    def fit(self,f):
        assert list(f.columns)==APPROVED
        self.maps={c:{v:i+1 for i,v in enumerate(pd.unique(f[c].dropna().astype(str))) if v.strip() and v!=FIELD_MISSING} for c in APPROVED}
        return self
    def save(self,path):
        Path(path).write_text(json.dumps(dict(version='RICH_CAT_V2',whitelist=APPROVED,namespace='kestrel-job-anon-v1',maps=self.maps),ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
    @classmethod
    def load(cls,path):
        state=read(path)
        if state['version']!='RICH_CAT_V2' or state['whitelist']!=APPROVED or state['namespace']!='kestrel-job-anon-v1':raise ValueError('Bundle contract mismatch')
        result=cls();result.maps=state['maps'];return result
    def transform(self,f):
        if set(f.columns)-set(APPROVED):raise ValueError('Approved submission whitelist required')
        f=f.reindex(columns=APPROVED)
        return pd.DataFrame({f'rich_{c}':f[c].fillna(FIELD_MISSING).astype(str).map(self.maps[c]).fillna(-1).to_numpy(np.float32) for c in APPROVED})
    def record(self,record,query_time):
        if set(record)!={'submit_time','observed_time','namespace','metadata'}:raise ValueError('Unknown receipt keys')
        if record['namespace']!='kestrel-job-anon-v1':raise ValueError('Uncertified identity namespace')
        payload=SubmissionSemanticPayloadV2.from_mapping(dict(record['metadata'],identity_namespace=record['namespace']))
        SubmissionSemanticRecord('research-query',str(record['submit_time']),str(record['observed_time']),payload).validate(query_time)
        return self.transform(pd.DataFrame([payload.category_projection()]))

def metadata(source,jobs):
    out=source.loc[jobs.job_id,['user_hash','submit_line_hash']].rename(columns={'user_hash':'user','submit_line_hash':'submit_line'}).reset_index(drop=True)
    return out.astype(object).where(out.notna(),None)

def hazard_fit(train,x,pre,arm):
    # Same frozen V13 discrete-hazard likelihood, age expansion, bins and learner.
    # Only added rich fields are explicitly categorical, never suffix/ordinal magnitudes.
    begin=time.perf_counter();edges=np.array(read(V13/'HAZARD_BIN_CONTRACT.json')['edges_seconds'],float)
    k=len(edges)-1;lower=train.duration_lower.to_numpy(float);exact=train.event.to_numpy(bool);within=exact&(lower<=edges[-1])
    counts=np.minimum(np.where(within,np.searchsorted(edges[1:],lower,side='left')+1,np.searchsorted(edges[1:],lower,side='right')),k)
    rows=np.repeat(np.arange(len(train)),counts);bins=np.arange(len(rows))-np.repeat(np.cumsum(counts)-counts,counts)
    xx=np.column_stack([x.to_numpy()[rows],model13.age_matrix(edges)[bins]])
    y=(within[rows]&(bins==counts[rows]-1)).astype('int8')
    cats=[list(x.columns).index(c) for c in ['qos','partition','account','rich_user','rich_submit_line']]
    learner=read(V13/'EXPERIMENT_PROTOCOL.json')['learner'];model=lgb.LGBMClassifier(**learner)
    model.fit(xx,y,categorical_feature=cats);del xx;gc.collect()
    return model13.Hazard(dict(kind='D1',arm=arm,columns=list(x.columns),edges=edges.tolist(),tail_exponential_rate=None,
        training_seconds=time.perf_counter()-begin,TRAIN_N=len(train),person_period_N=len(rows),fit_cutoff=pre['fit_cutoff'],
        provenance_mode='Kestrel_trace_proxy',preprocessing=pre,learner=learner,TAIL_GRID_CHANGED_FROM_V9=False,
        categorical_features=[list(x.columns)[i] for i in cats],rich_approved=APPROVED,research_only=True),model.booster_)

def neighbor_features(tr,va,ct,cv,folder):
    fields=['num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','num_gpus_req']
    raw=np.log1p(np.maximum(tr[fields].to_numpy(float),0));center=np.nanmedian(raw,axis=0)
    scale=np.maximum(np.nanquantile(raw,.75,axis=0)-np.nanquantile(raw,.25,axis=0),1)
    def resource(f):return np.nan_to_num((np.log1p(np.maximum(f[fields].to_numpy(float),0))-center)/scale).astype(np.float32)
    def codes(c):
        out=np.full((len(c),10),-1,np.int32);out[:,0]=c.rich_user;out[:,7]=c.rich_submit_line;return out
    pc=codes(ct);vc=codes(cv);pr=resource(tr);vr=resource(va)
    completed=np.flatnonzero(tr.event.to_numpy(bool));end=tr.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
    index=CompletedNeighborIndex(completed,end[completed],pc[completed],pr[completed],tr.runtime_seconds.to_numpy()[completed],[np.zeros((1,1)),np.zeros((1,1))])
    result=[];audits=[]
    for role,f,c,r in [('TRAIN',tr,pc,pr),('VALID',va,vc,vr)]:
        features=np.empty((len(f),18),np.float32);neighbors=np.empty((len(f),64),np.int32)
        submit=f.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
        for start in range(0,len(f),8192):
            stop=min(start+8192,len(f));nf,ni=index.query(submit[start:stop],c[start:stop],r[start:stop]);features[start:stop]=nf;neighbors[start:stop]=ni
            valid=ni>=0;assert tr.event.to_numpy()[np.maximum(ni,0)][valid].all()
            assert ((submit[start:stop,None]-end[np.maximum(ni,0)])[valid]>0).all()
        np.save(folder/f'{role}_neighbor_features.npy',features);np.save(folder/f'{role}_neighbor_ids.npy',neighbors)
        audits.append(dict(role=role,N=len(f),violations=0,TRAIN_completed_only=True,query_empty=int(np.sum(neighbors[:,0]<0))))
        result.append(pd.DataFrame(features,columns=[f'rich_neighbor_{i}' for i in range(18)]))
    write(str((folder/'NEIGHBOR_AUDIT.json').relative_to(ROOT)),dict(checks=audits,pool_completed_N=len(completed),source_metadata=APPROVED,
        request_scope='Exact existing R0 trace-proxy contract; not newly source-certified',normalization_center=center,normalization_scale=scale))
    return result

def register():
    v=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json');assert v['deployable_bridge_authorized'] and not v['program_stop_triggered']
    if (ROOT/'RUNTIME_BRIDGE_EXECUTION_FREEZE.json').exists():return
    assert not list(LOCAL.glob('runtime_fold*/*.json'))
    fields=pd.read_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv');rows=[]
    for r in fields[fields.source.eq('Kestrel original archive')].itertuples():
        rows.append(dict(field=r.field,information_class=r.information_class,retained_new_rich_feature=r.field in APPROVED,
            capture_rule='Immutable accepted-submission user/original-command pseudonym in certified matching identity namespace' if r.field in APPROVED else 'NOT_APPROVED_AS_NEW_RICH_FIELD',
            original_source_column=getattr(r,'source_column',None),receipt_required=True,archive_initial_version_proven=False,
            operational_namespace_service_proven=False))
    pd.DataFrame(rows).to_csv(ROOT/'V42_DEPLOYABLE_FIELD_BRIDGE.csv',index=False)
    write('RUNTIME_BRIDGE_EXECUTION_FREEZE.json',dict(time=now(),before_any_bridge_fit=True,approved_rich_fields=APPROVED,
        H0='Exact V13 R0 reused',H1='R16-A',H2='NOT_RUN_MODULES_CONDA_NOT_DEPLOYABLE',
        R16_A='Same V13 hazard plus two label-free categorical fields',
        R16_B='Identical input columns as A, fixed preregistered LightGBM direct Q50/Q90; fit only matured event labels within exact TRAIN role',
        R16_B_censoring_limitation='Right-censored TRAIN labels cannot be treated as exact runtimes; therefore architecture comparison also differs in likelihood/censoring handling. No pure architecture-superiority claim.',
        R16_B_proper_score='Quantile pinball is proper; existing required interval-NLL distribution gate remains NOT_DEFINED and cannot be declared passed',
        R16_C='R16-A plus k16/64 completed TRAIN neighbors. A is the only new model defining the required full hazard distribution; B cannot qualify as best distribution-approved model.',
        broad_search=False,exact_existing_five_folds=True,model_code=rec(ROOT/'bridge16.py'),payload_code=rec(ROOT/'semantic_payload_v2_candidate.py'),
        native_success=v['native_information_success'],native_routing=rec(ROOT/'EXECUTION_ROUTING_CORRECTION.json')))

def one(fold,source,state):
    folder=LOCAL/f'runtime_fold{fold}';folder.mkdir(exist_ok=True)
    tr=common13.data(fold,'TRAIN');va=common13.data(fold,'VALID');pre=common13.prep(fold)
    old=read(V15/'RUNTIME_INPUT_RECEIPT.json')['memberships']
    for role,d in [('TRAIN',tr),('VALID',va)]:assert common13.ids(d)==old[f'{fold}_{role}']['membership']
    assert tr.loc[tr.event,'end_time'].lt(pd.Timestamp(pre['fit_cutoff'])).all()
    mt=metadata(source,tr);mv=metadata(source,va);adapter=RichCategoryAdapter().fit(mt)
    ct=adapter.transform(mt);cv=adapter.transform(mv)
    adapter.save(folder/'rich_adapter.json')
    cols=model13.columns('EXPANDING_S4',pre['columns'],state.columns)
    xt=model13.matrix(tr,pre,state,cols);xv=model13.matrix(va,pre,state,cols)
    a=pd.concat([xt,ct],axis=1);b=pd.concat([xv,cv],axis=1)
    for arm in ['R16-A','R16-B','R16-C']:
        rpath=folder/(arm+'.json')
        if rpath.exists():continue
        if arm=='R16-C':
            nt,nv=neighbor_features(tr,va,ct,cv,folder);aa=pd.concat([a,nt],axis=1);bb=pd.concat([b,nv],axis=1)
        else:aa=a;bb=b
        print('BRIDGE_FIT',fold,arm,len(tr),len(aa.columns),flush=True)
        start=time.perf_counter()
        if arm!='R16-B':
            model=hazard_fit(tr,aa,pre,arm);model.meta['rich_adapter_sha256']=sha(folder/'rich_adapter.json');model.save(folder/arm)
            inference=time.perf_counter();par=model.parameters(bb,threads=4);elapsed=time.perf_counter()-inference
            s,p,q=train13.evaluate(model,par,va);training=model.meta['training_seconds'];del model,par
        else:
            pred=[];observed=tr.event.to_numpy(bool)
            cats=[list(aa.columns).index(c) for c in ['qos','partition','account','rich_user','rich_submit_line']]
            for alpha in [.5,.9]:
                model=lgb.LGBMRegressor(objective='quantile',alpha=alpha,**read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters'])
                model.fit(aa.loc[observed].to_numpy(),tr.loc[observed,'runtime_seconds'].to_numpy(),categorical_feature=cats)
                pred.append(np.maximum(model.predict(bb.to_numpy()),0));model.booster_.save_model(str(folder/f'{arm}_q{int(alpha*100)}.txt'));del model
            q=np.column_stack([pred[0],np.maximum(pred[0],pred[1])]);event=va.event.to_numpy(bool)
            p=va.loc[event,['job_id','runtime_seconds','num_gpus_req','requested_seconds']].reset_index(drop=True);p['q50']=q[event,0];p['q90']=q[event,1]
            s=train13.stats(p.runtime_seconds,p.num_gpus_req,p.q50,p.q90);s.update(train13.sharpness(p))
            for h in [4,8,12,24]:
                ix=p.runtime_seconds>h*3600;s[f'gt{h}h_N']=int(ix.sum());s[f'gt{h}h_coverage']=float((p.loc[ix,'runtime_seconds']<=p.loc[ix,'q90']).mean())
            s.update(proper_interval_NLL=None,proper_NLL_N=int((va.event|va.censored).sum()),proper_score_finite=False,
                zero_support_count=None,monotonicity_pass=True,quantile_invalid_support_N=int(np.sum(~np.isfinite(q)|(q<0))),
                proper_quantile_pinball_finite=bool(np.isfinite(s['Q90_pinball'])),interval_distribution_gate='NOT_DEFINED_QUANTILE_ONLY',
                actual_TRAIN_exact_label_N=int(observed.sum()),censored_TRAIN_not_mislabeled=int((~observed).sum()))
            training=time.perf_counter()-start;elapsed=None
        s.update(arm=arm,fold=fold,calibration='C0',TRAIN_N=len(tr),VALID_N=len(va),training_seconds=training,inference_seconds=elapsed,
            features=len(aa.columns),TRAIN_membership=common13.ids(tr),VALID_membership=common13.ids(va),new_rich_fields=APPROVED,
            source_scope='Research trace-proxy; accepted-submit receipt and namespace parity required for future input',status='COMPLETED')
        p.to_parquet(folder/(arm+'.parquet'),index=False);np.savez_compressed(folder/(arm+'_quantiles.npz'),q=q)
        artifacts=[folder/(arm+'.parquet'),folder/(arm+'_quantiles.npz'),folder/'rich_adapter.json']
        artifacts+=sorted((folder/arm).glob('*')) if arm!='R16-B' else [folder/f'{arm}_q50.txt',folder/f'{arm}_q90.txt']
        s['artifacts']=[rec(path) for path in artifacts if path.is_file()]
        write(str(rpath.relative_to(ROOT)),s)
        print('BRIDGE_RESULT',fold,arm,s['Q90_coverage'],s['gt4h_coverage'],s['Q90_pinball'],flush=True)
        if arm=='R16-C':del nt,nv,aa,bb
        gc.collect()

def main():
    register();freeze=read(ROOT/'RUNTIME_BRIDGE_EXECUTION_FREEZE.json');assert sha(ROOT/'bridge16.py')==freeze['model_code']['sha256']
    assert sha(ROOT/'semantic_payload_v2_candidate.py')==freeze['payload_code']['sha256']
    source=pd.read_parquet(V15/'.local/GPU_SUBMISSION_METADATA.parquet').set_index('id')
    state=pd.read_parquet(V13/'.local/CURRENT_STATE_FEATURES.parquet').set_index('job_id')
    for i in range(1,6):one(i,source,state)
    print('BRIDGE_FIVE_FOLDS_COMPLETE',flush=True)

if __name__=='__main__':main()
