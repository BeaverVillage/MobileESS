"""Frozen-authority-gated pre-April support and section-10 archive descriptions. No fit."""
from common7 import *
import pandas as pd, numpy as np, datetime

def save(name,rows):
    pd.DataFrame(rows).to_csv(ROOT/name,index=False,lineterminator='\n')

def stats(x):
    x=pd.to_numeric(x,errors='coerce').replace([np.inf,-np.inf],np.nan)
    v=x.dropna()
    return dict(n=len(x),nonmissing=len(v),missing=int(x.isna().sum()),mean=float(v.mean()) if len(v) else None,
                **{f'p{q}':float(v.quantile(q/100)) if len(v) else None for q in [10,50,90,99]})

def main():
    freeze=read(ROOT/'FEATURE_AUTHORITY_FREEZE.json')
    for r in freeze['files']:assert sha(ROOT/Path(r['path']).name)==r['sha256']
    assert read(ROOT/'STRICT_CAUSAL_FEATURE_CONTRACT.json')['features']==[]
    g=pd.read_parquet(LOCAL/'GPU_PREAPRIL.parquet')
    assert g.submit_time.max()<pd.Timestamp('2025-04-01T00Z')
    assert g.end_time.dropna().max()<pd.Timestamp('2025-04-01T00Z')
    g['long']=g.runtime_seconds.gt(14400);g['high_gpu']=g.gpus_requested.ge(16)
    g['gpu_hours']=g.gpus_requested*g.runtime_seconds/3600
    t=lambda x:pd.Timestamp(x)
    valid=g.label_valid
    roles={'TRAIN':valid&g.end_time.ge(t('2024-09-15T08Z'))&g.end_time.lt(t('2025-03-14T08Z')),
      'DEV':valid&g.submit_time.ge(t('2025-03-15T00Z'))&g.submit_time.lt(t('2025-03-23T00Z'))&g.end_time.lt(t('2025-03-23T00Z')),
      'CAL_FIT':valid&g.submit_time.ge(t('2025-03-23T00Z'))&g.submit_time.lt(t('2025-03-27T00Z'))&g.end_time.lt(t('2025-03-27T00Z')),
      'CAL_VALID':valid&g.submit_time.ge(t('2025-03-27T00Z'))&g.submit_time.lt(t('2025-03-31T00Z'))&g.end_time.lt(t('2025-03-31T08Z'))}
    roles['CAL']=roles['CAL_FIT']|roles['CAL_VALID'];roles['ALL_MATURE']=valid
    # Keep per-node and per-CPU memory scopes separate. Neither is a strict feature.
    mem=g.memory_req.astype('string').str.extract(r'^([0-9.]+)([KMGTPE]?)([cn]?)$',expand=True)
    scale=mem[1].map({'':1.,'K':1/1024,'M':1.,'G':1024.,'T':1024.**2,'P':1024.**3,'E':1024.**4})
    mv=pd.to_numeric(mem[0],errors='coerce')*scale
    g['memory_per_node_mib']=mv.where(mem[2].eq('n'));g['memory_per_cpu_mib']=mv.where(mem[2].eq('c'))
    g['memory_unspecified_scope_mib']=mv.where(mem[2].eq(''))
    g['array_membership_descriptor']=np.where(g.array_pos.notna(),'array_pos_present','array_pos_absent')
    hashes=['name_hash','submit_line_hash','submit_script_hash','work_dir_hash','user_hash','account_hash','job_type_hash']
    cats=['qos','partition']+hashes+['python_job','reframe_job','array_membership_descriptor','array_range','array_pos']
    support=[];workflow=[];role_rows=[];diag=[];categorical=[];request_classes=[]
    train=g[roles['TRAIN']]
    for role,mask in roles.items():
        f=g[mask];nh=int(f.high_gpu.sum());nl=int(f.long.sum())
        role_rows.append(dict(role=role,n=len(f),long_n=nl,long_fraction=nl/len(f),high_gpu_n=nh,high_gpu_long_n=int((f.high_gpu&f.long).sum()),
          long_gpu_hour_fraction=float(f.loc[f.long,'gpu_hours'].sum()/f.gpu_hours.sum()),runtime_p50=float(f.runtime_seconds.median()),runtime_p90=float(f.runtime_seconds.quantile(.9)),
          admission='archive positive-GPU descriptors; original submit chronology itself unresolved',label_deadline='pre-April; role-specific earlier cutoffs',strict_feature_count=0))
        for col in cats:
            key=f[col].astype('string').fillna('__MISSING__');tk=train[col].astype('string').fillna('__MISSING__')
            grp=f.assign(category=key).groupby('category',observed=True).agg(n=('id','size'),long_n=('long','sum'),high_gpu_n=('high_gpu','sum'))
            known=set(tk);seen=key.isin(known)
            support.append(dict(role=role,feature=col,category='__ALL__',n=len(f),long_n=nl,high_gpu_n=nh,unique_count=key.nunique(),
              unseen_train_rate=float((~seen).mean()),rare_under100_category_fraction=float(grp.n.lt(100).mean()),rare_under100_row_fraction=float(grp.loc[grp.n.lt(100),'n'].sum()/len(f)),
              strict_allowed=False,scope='archive support only; no predictive ranking'))
            # Complete category-level table can be large; keep compressed CSV losslessly.
            grp=grp.reset_index();grp.insert(0,'feature',col);grp.insert(0,'role',role);grp['seen_in_train']=grp.category.isin(known);grp['strict_allowed']=False
            categorical.append(grp)
        for col in hashes:
            counts=f[col].astype('string').value_counts(dropna=False)
            row=dict(role=role,identity=col,n=len(f),unique_count=len(counts),median_within_group_n=float(counts.median()),recurrence_p90=float(counts.quantile(.9)),recurrence_max=int(counts.max()),
              runtime_within_group_cv=None,cv_status='SKIPPED_AUTHORITY_GATE_SECTION9',available_at_submission='CONCEPT_ONLY; NLR generation/hash time unresolved',
              changes_after_execution='UNKNOWN; no same-task version stream',anonymization_consistency='Repeated existing tokens observed; no collision/stability algorithm attestation',
              unseen_train_rate=float((~f[col].astype('string').isin(set(train[col].astype('string')))).mean()),strict_allowed=False)
            for k in [2,5,10]:row[f'fraction_tokens_ge{k}']=float(counts.ge(k).mean());row[f'fraction_rows_ge{k}']=float(counts[counts.ge(k)].sum()/len(f))
            workflow.append(row)
        for long_value,bucket in [(False,'runtime_le4h'),(True,'runtime_gt4h')]:
            d=f[f.long.eq(long_value)]
            for col in ['requested_seconds','gpus_requested','nodes_req','processors_req','memory_per_node_mib','memory_per_cpu_mib','memory_unspecified_scope_mib']:
                diag.append(dict(role=role,runtime_bucket=bucket,feature=col,kind='numeric',category='',**stats(d[col]),strict_allowed=False,interpretation='SECTION10_ARCHIVE_DESCRIPTOR_ONLY'))
            for col in ['qos','partition','account_hash','user_hash']:
                for key,n in d[col].astype('string').fillna('__MISSING__').value_counts().items():
                    diag.append(dict(role=role,runtime_bucket=bucket,feature=col,kind='categorical',category=key,n=int(n),fraction=float(n/len(d)),strict_allowed=False,interpretation='SECTION10_ARCHIVE_DESCRIPTOR_ONLY'))
        # Identical *archive* request tuple, not certified original request equivalence.
        fields=['requested_seconds','gpus_requested','nodes_req','processors_req','memory_req','qos','partition','account_hash','user_hash']
        c=f.groupby(fields,dropna=False,observed=True).agg(n=('id','size'),long_n=('long','sum'),minimum=('runtime_seconds','min'),maximum=('runtime_seconds','max'),mean=('runtime_seconds','mean'),std=('runtime_seconds','std'))
        mixed=c.long_n.gt(0)&c.long_n.lt(c.n);supported=c.n.ge(10)&c['mean'].gt(0)
        request_classes.append(dict(role=role,n=len(f),archive_request_classes=len(c),classes_ge10=int(supported.sum()),mixed_short_long_classes=int(mixed.sum()),
          rows_in_mixed_classes=int(c.loc[mixed,'n'].sum()),rows_in_mixed_classes_fraction=float(c.loc[mixed,'n'].sum()/len(f)),long_rows_in_mixed_classes_fraction=float(c.loc[mixed,'long_n'].sum()/max(1,nl)),
          median_cv_classes_ge10=float((c.loc[supported,'std']/c.loc[supported,'mean']).median()),
          median_max_min_ratio_classes_ge10_positive_min=float((c.loc[supported&c.minimum.gt(0),'maximum']/c.loc[supported&c.minimum.gt(0),'minimum']).median()),
          scope='section10 within identical archive request descriptor class; not submission-time feature predictiveness'))
    save('COHORT_ROLE_SUMMARY.csv',role_rows);save('COHORT_SUPPORT_AUDIT.csv',support)
    pd.concat(categorical,ignore_index=True).to_csv(ROOT/'COHORT_CATEGORY_SUPPORT.csv.gz',index=False,compression={'method':'gzip','mtime':0},lineterminator='\n')
    save('WORKFLOW_IDENTITY_AUDIT.csv',workflow);save('LONG_JOB_FEATURE_DIAGNOSTIC.csv',diag);save('ARCHIVE_REQUEST_CLASS_TAIL_AUDIT.csv',request_classes)
    save('FEATURE_PREDICTIVENESS_DIAGNOSTIC.csv',[dict(status='SKIPPED_NO_SUBMISSION_TIME_VALID_FEATURES',strict_feature_count=0,spearman=None,mutual_information=None,between_group_variance=None,walltime_runtime_ratios=None,reason='Task section9 authority prerequisite not met. No model and no feature ranking.')])
    write('DESCRIPTIVE_RECEIPT.json',dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),authority_freeze=record(ROOT/'FEATURE_AUTHORITY_FREEZE.json'),
      source=record(LOCAL/'GPU_PREAPRIL.parquet'),roles=role_rows,models_trained=0,feature_selection_performed=False,April_May_payload_read=False,
      memory_scope_counts=mem[2].fillna('__UNPARSED_OR_NULL__').value_counts().to_dict(),
      runtime_cv_policy='Workflow CV and section9 ratios withheld because none is submission-time valid. Section10 request-class dispersion is explicitly retrospective.',
      high_gpu_support_criterion='Report counts; even 100 independent validation jobs (descriptive reference, not a tuned gate) unavailable in DEV or CAL.',
      chronology='TRAIN uses mature end-time interval [2024-09-15T08Z,2025-03-14T08Z); DEV submit[Mar15,Mar23),end<Mar23; CAL_FIT submit[Mar23,Mar27),end<Mar27; CAL_VALID submit[Mar27,Mar31),end<Mar31T08Z. Archive timestamps, not proven original chronology.',
      no_cross_role_label_lookahead=True,all_mature='All valid positive-GPU labels ended before2025-04-01T00Z; no model fit.'))
    print(pd.DataFrame(role_rows).to_string(index=False),flush=True)

if __name__=='__main__':main()
