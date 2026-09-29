"""Research trace descriptor transforms. This module never sees target or outcomes."""
import numpy as np,pandas as pd
BASE_RESOURCE=['num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib']
RESOURCE_SHAPE=['log_gpu','log_nodes','log_cores','log_memory','gpu_per_node','cores_per_node','cores_per_gpu','memory_per_gpu','memory_per_node']
DURATION=['requested_seconds','log_walltime','requested_gpu_time','log_requested_gpu_time']
IDENTITIES=['account','user','job_name_token','submitline_token','script_token','workdir_token']
FORBIDDEN={'start_time','end_time','runtime_seconds','actual_runtime','actual_start','actual_end','queue_wait','queue_wait_seconds','completion_status','state','state_simple','wallclock_used','cpu_used','utilization','checkpoint','future_scheduler_state','D_day_completion'}
RAW_MAP={'gpus_requested':'num_gpus_req','nodes_req':'num_nodes_req','processors_req':'num_cores_req','user_hash':'user','account_hash':'account','name_hash':'job_name_token','submit_line_hash':'submitline_token','submit_script_hash':'script_token','work_dir_hash':'workdir_token','array_pos':'array_index'}

def engineer(records,maps):
    # Select individual whitelisted keys; no id/time/state can enter X.
    f=pd.DataFrame(records);out=pd.DataFrame(index=f.index)
    for col in BASE_RESOURCE+['requested_seconds','array_index']:
        x=pd.to_numeric(f[col],errors='coerce') if col in f else pd.Series(np.nan,index=f.index)
        valid=np.isfinite(x)&(x>=0 if col=='array_index' else x>0)
        if col in ['num_gpus_req','num_nodes_req','num_cores_req','array_index']:valid&=x.eq(np.floor(x))
        out[col]=x.where(valid).astype(float);out[col+'_missing_or_invalid']=(~valid).astype(float)
    for src,dst in [('requested_seconds','log_walltime'),('num_gpus_req','log_gpu'),('num_nodes_req','log_nodes'),('num_cores_req','log_cores'),('requested_memory_mib','log_memory'),('array_index','log_array_index')]:out[dst]=np.log1p(out[src])
    for a,b,c in [('num_gpus_req','num_nodes_req','gpu_per_node'),('num_cores_req','num_nodes_req','cores_per_node'),('num_cores_req','num_gpus_req','cores_per_gpu'),('requested_memory_mib','num_gpus_req','memory_per_gpu'),('requested_memory_mib','num_nodes_req','memory_per_node')]:out[c]=out[a]/out[b]
    out['requested_gpu_time']=out.num_gpus_req*out.requested_seconds;out['log_requested_gpu_time']=np.log1p(out.requested_gpu_time)
    out['is_array_descriptor']=out.array_index.notna().astype(float)
    out['gpu_nodes_inconsistent']=((out.num_gpus_req>4*out.num_nodes_req)&out.num_nodes_req.notna()).astype(float)
    for col,mapping in maps.items():
        x=f[col].astype('string').fillna('__MISSING__') if col in f else pd.Series('__MISSING__',index=f.index)
        out[col]=x.map(mapping).fillna(0).astype('int32')
    return out.replace([np.inf,-np.inf],np.nan)

def families(accepted):
    f0=BASE_RESOURCE+RESOURCE_SHAPE+[c+'_missing_or_invalid' for c in BASE_RESOURCE]+['gpu_nodes_inconsistent']
    f1=f0+DURATION+['requested_seconds_missing_or_invalid','qos','partition']
    f2=f1+accepted+['is_array_descriptor','log_array_index','array_index_missing_or_invalid']
    return {'F0':f0,'F1':f1,'F2':f2}

def groups(columns):
    labels={c:'resource_shape' for c in RESOURCE_SHAPE+['gpu_nodes_inconsistent']}
    labels.update({c:'walltime' for c in DURATION+['requested_seconds_missing_or_invalid']})
    labels.update({c:'scheduler' for c in ['qos','partition']});labels.update({c:'identity' for c in IDENTITIES})
    labels.update({c:'array' for c in ['is_array_descriptor','log_array_index','array_index_missing_or_invalid']})
    result={}
    for c in columns:result.setdefault(labels.get(c,'resource_base'),[]).append(c)
    return result
