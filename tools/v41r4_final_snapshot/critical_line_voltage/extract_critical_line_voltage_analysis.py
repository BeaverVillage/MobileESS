"""Read-only V41R4 archive post-processing. Never imports or executes scientific code."""
import argparse, csv, datetime as dt, hashlib, io, json, math, re, statistics, sys, tarfile, time
from pathlib import Path
import numpy as np

ROOT = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터')
ARCHIVE = ROOT/'V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz'
EXPORT = ROOT/'MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635'
OUT = Path(__file__).resolve().parent

def readj(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()
def writej(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def intake():
    m=readj(EXPORT/'MANIFEST.json'); units=m['unit_source_map']
    folders={u[k] for u in units for k in ('pre_Q','final_Actual','final_Fresh')}
    expected={a['source_inside_archive']:a for a in m['source_artifacts']}
    roots={u['pre_Q'].split('/replays/')[0] for u in units}
    selected={}; total=0; count=0; start=time.time()
    cache=OUT/'selected_raw';cache.mkdir(exist_ok=True)
    with tarfile.open(ARCHIVE,'r|gz') as tf, (OUT/'archive_member_inventory.jsonl').open('w',encoding='utf-8') as listing:
        for member in tf:
            if not member.isfile(): continue
            name=member.name; rel=name.split('/',1)[1] if '/' in name else name
            count+=1;total+=member.size
            listing.write(json.dumps({'member':name,'relative_path':rel,'bytes':member.size})+'\n')
            base=rel.rsplit('/',1)[-1]; folder=rel.rsplit('/',1)[0]
            take=(folder in folders and base in ('OPENDSS_PHASE_ARRAYS.npz','OPENDSS_SUMMARY.json','OPENDSS_OUTPUT_MANIFEST.json','BRANCH_PHASE_CURRENTS.parquet','GRID_AXIS_CONTRACT.json'))
            take=take or rel in ('FINAL_RESULT_INDEX.json','PACKAGE_INFO.json') or (base in ('METHOD_FREEZE.json','RULE_FREEZE.json','FINAL_AUDIT.json') and ('v41r4' in rel))
            take=take or ('/authority/' in rel and base=='AUTHORITY_MANIFEST.json')
            take=take or (base.lower().endswith('.dss') or any(t in base.lower() for t in ('topology','branch_mapping','branch_metadata','feeder_assets')))
            take=take or (base=='BRANCH_PHASE_CURRENTS.parquet' and '/2025-05-01/B0/' in rel)
            if take:
                if member.size>100_000_000: raise RuntimeError('SELECTED_MEMBER_TOO_LARGE:'+rel)
                data=tf.extractfile(member).read();h=hashlib.sha256(data).hexdigest()
                if rel in expected and h!=expected[rel]['sha256']:raise RuntimeError('SOURCE_HASH_MISMATCH:'+rel)
                dest=cache/(h+Path(base).suffix);dest.write_bytes(data)
                selected[rel]={'member':name,'sha256':h,'bytes':len(data),'local':str(dest.relative_to(OUT)),'export_hash_verified':rel in expected}
            if count%5000==0:print('STREAM',count,'members',round(total/1e9,2),'GB uncompressed',len(selected),'selected',round(time.time()-start),'s',flush=True)
    writej(OUT/'selected_raw_index.json',selected)
    writej(OUT/'intake_summary.json',dict(archive_file_count=count,archive_uncompressed_bytes=total,selected_count=len(selected),selected_bytes=sum(x['bytes'] for x in selected.values()),elapsed_seconds=time.time()-start))
    print('INTAKE_COMPLETE',count,len(selected),flush=True)

def supplement():
    m=readj(EXPORT/'MANIFEST.json'); selected=readj(OUT/'selected_raw_index.json')
    expected={a['source_inside_archive']:a for a in m['source_artifacts']}
    wanted=set()
    for u in m['unit_source_map']:
        wanted.add(f"frozen_artifacts/v41r4_may/loop_wall_v4/{u['day']}/{u['policy']}/dayahead/grid/BRANCH_PHASE_CURRENTS.parquet")
        ac=u['final_Actual'].rsplit('/',1)[0]
        wanted.update(ac+'/'+n for n in ('CANDIDATE_RECEIPT.json','COMPLETE.json'))
    wanted-=set(selected)
    count=0;start=time.time()
    with tarfile.open(ARCHIVE,'r|gz') as tf:
        for member in tf:
            if not member.isfile():continue
            rel=member.name.split('/',1)[1]
            if rel not in wanted:continue
            data=tf.extractfile(member).read();h=hashlib.sha256(data).hexdigest()
            if rel in expected and h!=expected[rel]['sha256']:raise RuntimeError('SOURCE_HASH_MISMATCH:'+rel)
            dest=OUT/'selected_raw'/(h+Path(rel).suffix);dest.write_bytes(data)
            selected[rel]={'member':member.name,'sha256':h,'bytes':len(data),'local':str(dest.relative_to(OUT)),'export_hash_verified':rel in expected}
            count+=1
            if count%50==0:print('SUPPLEMENT',count,round(time.time()-start),'s',flush=True)
    writej(OUT/'selected_raw_index.json',selected)
    missing=wanted-set(selected)
    writej(OUT/'supplement_missing_members.json',sorted(missing))
    # Missing topology is handled by the analysis authority gate, never invented.
    if missing:print('MISSING_OPTIONAL_PER_POLICY_TOPOLOGY',sorted(missing),flush=True)
    print('SUPPLEMENT_COMPLETE',count,flush=True)

def analyze():
    sys.path.insert(0,str(OUT/'_deps'))
    import pandas as pd
    index=readj(OUT/'selected_raw_index.json'); manifest=readj(EXPORT/'MANIFEST.json')
    used={}; source_files={}; checks=[]; errors=[]; raw=[]; refs=[]; maxima=[]
    policies=('B0','B1','B2','B3'); days=[f'2025-05-{d:02d}' for d in range(1,32)]
    tol=1e-12  # floating-point unchanged threshold; not a voltage security limit
    def check(ok,label,detail=None):
        checks.append(dict(check=label,status='PASS' if bool(ok) else 'FAIL',detail=detail))
        if not ok:raise ValueError(label+': '+str(detail))
    def use(rel):
        if rel not in index:raise ValueError('MISSING_ARCHIVED_MEMBER:'+rel)
        item=index[rel];p=OUT/item['local']
        if rel not in used:
            check(sha(p)==item['sha256'],'SELECTED_MEMBER_SHA256',rel);used[rel]=item
        return p
    def j(rel):return readj(use(rel))
    def source(p):
        p=Path(p);source_files[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size};return p
    def csvread(name):
        with source(EXPORT/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    source(EXPORT/'MANIFEST.json')
    actual={(r['day'],r['policy']):r for r in csvread('02_actual_summary.csv')}
    qsummary={(r['day'],r['policy']):r for r in csvread('03_q_correction_summary.csv')}
    paper_aggregate={r['policy']:r for r in csvread('08_policy_aggregate_statistics.csv')}
    grid={(r['day'],r['policy'],r['trajectory'],int(r['slot'])):r for r in csvread('05_grid_timeseries.csv')}
    csvread('09_paired_policy_comparisons.csv')
    expected_hash=manifest['source_archive_SHA256']
    print('VERIFY_FULL_ARCHIVE_SHA256',flush=True)
    archive_hash=sha(ARCHIVE)
    check(archive_hash==expected_hash,'RAW_ARCHIVE_SHA256_MATCH',archive_hash)
    source_files[str(ARCHIVE)]={'sha256':archive_hash,'bytes':ARCHIVE.stat().st_size,'hash_method':'Full compressed archive SHA256 read during this task; source_archive_hash.json'}
    final_index=j('FINAL_RESULT_INDEX.json');entries={(x['day'],x['policy']):x for x in final_index}
    units={(u['day'],u['policy']):u for u in manifest['unit_source_map']}
    check(set(entries)==set(units)=={(d,p) for d in days for p in policies},'EXACT_124_FINAL_INDEX_KEYS')
    topology_sources=[];authority_sources=[];method_hashes=set()
    def arrays(folder,d,p,state):
        rel=folder+'/OPENDSS_PHASE_ARRAYS.npz';summary=j(folder+'/OPENDSS_SUMMARY.json')
        native=j(folder+'/OPENDSS_OUTPUT_MANIFEST.json')
        for filename in ('OPENDSS_PHASE_ARRAYS.npz','OPENDSS_SUMMARY.json'):
            use(folder+'/'+filename)
            check(index[folder+'/'+filename]['sha256']==native['files'][filename]['sha256'],'NATIVE_OUTPUT_HASH',[d,p,state,filename])
        with np.load(use(rel),allow_pickle=False) as z: a={k:z[k] for k in z.files}
        check(summary['day']==d and summary['case']==p and summary['namespace']=='ACTUAL','ACTUAL_STATE_IDENTITY',[d,p,state])
        check(a['voltage_pu'].shape==(96,len(a['node_names'])) and a['phase_current_loading_pu'].shape==(96,len(a['branch_names'])),'ARRAY_SHAPE',[d,p,state])
        check(all(np.isfinite(a[k]).all() for k in ('voltage_pu','phase_current_a','phase_current_loading_pu')),'FINITE_SCIENTIFIC_ARRAYS',[d,p,state])
        check(a['convergence'].shape==(96,) and a['convergence'].all() and summary['convergence_count']==96,'96_CONVERGED_SLOTS',[d,p,state])
        node_keys=list(zip(map(str,a['node_names']),map(str,a['node_phases'])))
        branch_keys=list(zip(map(str,a['branch_names']),map(str,a['branch_phases'])))
        check(len(set(node_keys))==len(node_keys) and len(set(branch_keys))==len(branch_keys),'UNIQUE_PHASE_AXES',[d,p,state])
        check(all(n.rsplit('.',1)[1]==str('ABC'.index(ph)+1) for n,ph in node_keys),'NODE_PHASE_SUFFIX_AGREEMENT',[d,p,state])
        li=np.flatnonzero(a['branch_kinds']=='line');rho=a['phase_current_loading_pu'][:,li]
        check(len(li)>0 and all(str(a['branch_names'][b]).startswith('line.') for b in li),'NON_TRANSFORMER_LINE_DEFINITION',[d,p,state])
        mx=float(rho.max());col='preQ_rho_max' if state=='preQ' else 'postQ_rho_max'
        check(mx==float(summary['rho_max_AC'])==float(qsummary[d,p][col]),'EXACT_RAW_SUMMARY_PAPER_DAILY_MAX',[d,p,state,mx])
        if state=='postQ':check(mx==float(actual[d,p]['Actual_rho_max']),'EXACT_FINAL_ACTUAL_SUMMARY_MAX',[d,p])
        tr='ETA95_ACTUAL' if state=='preQ' else 'ETA95_QSAFE_ACTUAL'
        for t in range(96):
            g=grid[d,p,tr,t];bi=int(li[np.argmax(rho[t])])
            check(float(g['rho_line_max'])==float(rho[t].max()) and g['critical_line']==str(a['branch_names'][bi]) and g['critical_line_phase']==str(a['branch_phases'][bi]),'EXACT_96_SLOT_PAPER_GRID',[d,p,state,t])
        if not any(x['date']==d and x['policy']==p and x['source_state']==state for x in maxima):
            maxima.append({'date':d,'policy':p,'source_state':state,'own_daily_max_rho':mx})
        return a,li,rel
    for d in days:
        daily=[]
        try:
            base_array,base_li,base_rel=arrays(units[d,'B0']['pre_Q'],d,'B0','preQ')
            r=base_array['phase_current_loading_pu'][:,base_li]
            t,k=np.unravel_index(np.argmax(r),r.shape);t=int(t);bi=int(base_li[k])
            line=str(base_array['branch_names'][bi]);phase=str(base_array['branch_phases'][bi]);ties=int(np.count_nonzero(r==r.max()))
            timestamp=grid[d,'B0','ETA95_ACTUAL',t]['timestamp']
            expected_ts=(dt.datetime.fromisoformat(d+'T00:00:00+10:00')+dt.timedelta(minutes=15*t)).isoformat()
            check(timestamp==expected_ts,'ARCHIVED_AEST_TIMESTAMP',[d,t,timestamp])
            b0map=None
            for p in policies:
                u=units[d,p];entry=entries[d,p];control=p in ('B0','B1');root=entry['final_actual']
                expected_post=root+('/CONTROL_COMMON_BINDING' if control else '/ETA95_QSAFE_ACTUAL')
                expected_pre=expected_post if control else root+'/ETA95_ACTUAL'
                check(u['pre_Q']==expected_pre and u['final_Actual']==expected_post,'RAW_FINAL_INDEX_STATE_BINDING',[d,p])
                receipt=j(root+'/CANDIDATE_RECEIPT.json');complete=j(root+'/COMPLETE.json')
                check(receipt['status']=='COMPLETE' and complete['status']=='PASS','FINAL_RECEIPT_COMPLETE',[d,p])
                method_hashes.add(receipt['method_SHA'])
                methodrel=root.split('/replays/')[0]+'/METHOD_FREEZE.json';use(methodrel)
                check(index[methodrel]['sha256']==receipt['method_SHA'],'FROZEN_ACTUAL_METHOD_HASH',[d,p])
                toporel=f'frozen_artifacts/v41r4_may/loop_wall_v4/{d}/{p}/dayahead/grid/BRANCH_PHASE_CURRENTS.parquet'
                authrel=f'frozen_artifacts/v41r4_may/loop_wall_v4/{d}/{p}/dayahead/authority/AUTHORITY_MANIFEST.json'
                auth=j(authrel);authority_sources.append(authrel)
                topology_resolution='DIRECT_PER_POLICY_ARCHIVED_TOPOLOGY'
                if toporel not in index:
                    baseauth=j(f'frozen_artifacts/v41r4_may/loop_wall_v4/{d}/B0/dayahead/authority/AUTHORITY_MANIFEST.json')
                    check(auth['electrical_configuration_identity']['sha256']==baseauth['electrical_configuration_identity']['sha256'] and auth['common_input_identity']['electrical_base_data_hash']==baseauth['common_input_identity']['electrical_base_data_hash'],'SHARED_B0_TOPOLOGY_EXACT_ELECTRICAL_AUTHORITY_IDENTITY',[d,p,auth['electrical_configuration_identity']['sha256'],auth['common_input_identity']['electrical_base_data_hash']])
                    toporel=f'frozen_artifacts/v41r4_may/loop_wall_v4/{d}/B0/dayahead/grid/BRANCH_PHASE_CURRENTS.parquet'
                    topology_resolution='SAME_DAY_B0_TOPOLOGY_WITH_IDENTICAL_ARCHIVED_ELECTRICAL_CERTIFICATE_AND_BASE_DATA_SHA256'
                topo=pd.read_parquet(use(toporel));topology_sources.append(toporel)
                # This is recorded topology only; never use these DA currents/voltages as actual observations.
                fields=['line_id','phase','from_bus','to_bus','kind','current_limit_A']
                mapping=topo[fields].drop_duplicates()
                check(not mapping.duplicated(['line_id','phase']).any(),'UNAMBIGUOUS_ARCHIVED_TOPOLOGY',[d,p])
                check(len(topo)==96*len(mapping) and not topo.duplicated(['slot','line_id','phase']).any() and set(topo['slot'])==set(range(96)),'TOPOLOGY_96_SLOT_COVERAGE',[d,p])
                maps={(str(row.line_id),str(row.phase)):(str(row.from_bus).lower(),str(row.to_bus).lower(),str(row.kind),float(row.current_limit_A)) for row in mapping.itertuples(index=False)}
                if p=='B0':b0map=maps
                else:check(maps==b0map,'SAME_DAY_POLICY_TOPOLOGY_AND_RATINGS',[d,p])
                check((line,phase) in maps,'REFERENCE_PHASE_IN_TOPOLOGY',[d,p,line,phase])
                send,recv,kind,rating=maps[line,phase]
                check(kind=='line' and send and recv and math.isfinite(rating) and rating>0,'REFERENCE_ENDPOINTS_AND_RATING',[d,p])
                for state,folder in (('preQ',expected_pre),('postQ',expected_post)):
                    a,li,rel=arrays(folder,d,p,state)
                    rr=rel[len(root)+1:]
                    receipt_files={n.replace('\\','/'):h for n,h in receipt['files'].items()}
                    check(rr in receipt_files and receipt_files[rr]==index[rel]['sha256'],'FINAL_CANDIDATE_ARRAY_HASH',[d,p,state])
                    branchkeys=list(zip(map(str,a['branch_names']),map(str,a['branch_phases'])))
                    check(set(branchkeys)==set(maps),'FULL_TOPOLOGY_BRANCH_PHASE_AXIS',[d,p,state])
                    rates=np.array([maps[branchkeys[b]][3] for b in li])
                    mismatch=float(np.max(np.abs(a['phase_current_a'][:,li]/rates-a['phase_current_loading_pu'][:,li])))
                    check(mismatch<1e-12,'FULL_LINE_CURRENT_RATING_AUTHORITY',[d,p,state,mismatch])
                    i=branchkeys.index((line,phase));nodekeys=list(zip(map(str,a['node_names']),map(str,a['node_phases'])))
                    nodekey_send=(send+'.'+str('ABC'.index(phase)+1),phase);nodekey_recv=(recv+'.'+str('ABC'.index(phase)+1),phase)
                    check(nodekey_send in nodekeys and nodekey_recv in nodekeys,'BOTH_ENDPOINT_PHASES_EXIST',[d,p,state,nodekey_send,nodekey_recv])
                    si=nodekeys.index(nodekey_send);ri=nodekeys.index(nodekey_recv)
                    vs=float(a['voltage_pu'][t,si]);vr=float(a['voltage_pu'][t,ri]);rho=float(a['phase_current_loading_pu'][t,i])
                    daily.append(dict(date=d,policy=p,reference_policy='B0',slot=t,timestamp=timestamp,line=line,phase=phase,sending_bus=send,receiving_bus=recv,
                        rho=rho,phase_current_A=float(a['phase_current_a'][t,i]),line_rating_A=rating,sending_voltage_pu=vs,receiving_voltage_pu=vr,
                        signed_voltage_change_pu=vs-vr,abs_line_voltage_difference_pu=abs(vs-vr),sending_voltage_deviation_abs_pu=abs(vs-1),receiving_voltage_deviation_abs_pu=abs(vr-1),
                        source_state=state,source_trajectory=folder.rsplit('/',1)[1],Q_control_interpretation='NO_Q_CONTROL_COMMON_BINDING' if control else ('REALIZED_BEFORE_Q_CORRECTIVE_CONTROL' if state=='preQ' else 'FINAL_ACCEPTED_AFTER_Q_CORRECTIVE_CONTROL'),
                        source_npz_member=index[rel]['member'],source_npz_sha256=index[rel]['sha256'],source_voltage_array='voltage_pu',source_voltage_slot=t,source_sending_node_index=si,source_receiving_node_index=ri,
                        source_current_array='phase_current_loading_pu',source_branch_index=i,topology_source_member=index[toporel]['member'],topology_resolution=topology_resolution,endpoint_orientation='ARCHIVED_FROM_BUS_TO_BUS',reference_selection_state='B0_PRE_Q',reference_exact_tie_count=ties))
            for state in ('preQ','postQ'):
                rows=[x for x in daily if x['source_state']==state];b=next(x for x in rows if x['policy']=='B0')
                for x in rows:
                    x['rho_change_vs_B0']=x['rho']-b['rho']
                    x['rho_reduction_pct_vs_B0']=(b['rho']-x['rho'])/b['rho']*100
                    for key in ('abs_line_voltage_difference','receiving_voltage_deviation'):
                        metric=key+'_pu' if key=='abs_line_voltage_difference' else key+'_abs_pu'
                        delta=x[metric]-b[metric];x[key+'_change_vs_B0']=delta
                        x[key+'_status_vs_B0']='improved' if delta < -tol else 'worsened' if delta > tol else 'unchanged'
                    check((x['line'],x['phase'],x['slot'])==(line,phase,t),'SAME_B0_REFERENCE_POINT',[d,x['policy'],state])
            b=next(x for x in daily if x['policy']=='B0' and x['source_state']=='preQ')
            refs.append(dict(date=d,slot=t,timestamp=timestamp,line=line,phase=phase,sending_bus=b['sending_bus'],receiving_bus=b['receiving_bus'],B0_rho=b['rho'],B0_Vsend_pu=b['sending_voltage_pu'],B0_Vrecv_pu=b['receiving_voltage_pu'],B0_signed_voltage_change_pu=b['signed_voltage_change_pu'],B0_abs_line_voltage_difference_pu=b['abs_line_voltage_difference_pu'],B0_receiving_voltage_deviation_abs_pu=b['receiving_voltage_deviation_abs_pu'],reference_selection_state='B0_PRE_Q',exact_tie_count=ties,source_npz_member=index[base_rel]['member']))
            raw.extend(daily)
            print('ANALYZED',d,line,phase,t,flush=True)
        except Exception as exc:errors.append({'date':d,'error':str(exc)});print('FAIL_CLOSED',d,str(exc),flush=True)
    def aggregate(rows):
        result=[]
        for p in policies:
            rr=[x for x in rows if x['policy']==p]
            if len(rr)!=31:continue
            r={'policy':p,'N_days':31,'mean_rho':statistics.mean(x['rho'] for x in rr),'SD_rho':statistics.stdev(x['rho'] for x in rr),'mean_rho_reduction_pct_vs_B0':statistics.mean(x['rho_reduction_pct_vs_B0'] for x in rr),'median_rho_reduction_pct_vs_B0':statistics.median(x['rho_reduction_pct_vs_B0'] for x in rr)}
            for key,metric in (('abs_line_voltage_difference','abs_line_voltage_difference_pu'),('receiving_voltage_deviation','receiving_voltage_deviation_abs_pu')):
                r['mean_'+metric]=statistics.mean(x[metric] for x in rr);r['SD_'+metric]=statistics.stdev(x[metric] for x in rr)
                r['mean_'+key+'_change_vs_B0']=statistics.mean(x[key+'_change_vs_B0'] for x in rr)
                r['median_'+key+'_change_vs_B0']=statistics.median(x[key+'_change_vs_B0'] for x in rr)
                for status in ('improved','unchanged','worsened'):r[key+'_'+status+'_days']=sum(x[key+'_status_vs_B0']==status for x in rr)
            result.append(r)
        return result
    pre=[x for x in raw if x['source_state']=='preQ'];post=[x for x in raw if x['source_state']=='postQ']
    try:
        check(len(refs)==31 and len(pre)==len(post)==124,'COMPLETE_OUTPUT_ROWS',[len(refs),len(pre),len(post)])
        check(len(method_hashes)==1,'ONE_FROZEN_ACTUAL_METHOD',sorted(method_hashes))
        b0mean=statistics.mean(r['B0_rho'] for r in refs)
        check(abs(b0mean-0.70120)<0.000005,'B0_PAPER_ROUNDED_MEAN',b0mean)
        for p in policies:
            own=[x['own_daily_max_rho'] for x in maxima if x['policy']==p and x['source_state']=='postQ']
            check(len(own)==31 and abs(statistics.mean(own)-float(paper_aggregate[p]['Actual_rho_mean']))<1e-14,'OWN_POST_Q_HEADLINE_MEAN_DISTINCT_FROM_SAME_POINT',[p,statistics.mean(own)])
    except Exception as exc:errors.append({'date':'ALL','error':str(exc)})
    status='PASS' if not errors else 'FAIL'
    agg=aggregate(pre) if status=='PASS' else [];postagg=aggregate(post) if status=='PASS' else []
    wide=[]
    if status=='PASS':
        for d in days:
            w={'date':d}
            for p in policies[1:]:
                x=next(x for x in pre if x['date']==d and x['policy']==p)
                for k in ('rho_change_vs_B0','rho_reduction_pct_vs_B0','abs_line_voltage_difference_change_vs_B0','receiving_voltage_deviation_change_vs_B0'):w[p+'_'+k]=x[k]
            wide.append(w)
    outputs={}
    def writecsv(name,rows,headers):
        path=OUT/name
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
        with path.open(encoding='utf-8-sig',newline='') as f:readback=list(csv.DictReader(f))
        check(len(readback)==len(rows),'CSV_READBACK_ROW_COUNT',[name,len(rows)])
        outputs[name]={'rows':len(rows),'sha256':sha(path),'bytes':path.stat().st_size,'columns':headers}
    # Failure outputs never contain fabricated voltage values or partial-cohort aggregate statistics.
    specs=[('01_B0_reference_critical_points.csv',refs),('02_policy_comparison_at_B0_critical_points_preQ.csv',pre),('03_policy_aggregate_at_B0_critical_points_preQ.csv',agg),('04_daily_paired_changes_preQ.csv',wide),('05_policy_comparison_at_B0_critical_points_postQ.csv',post)]
    for name,rows in specs:
        headers=list(rows[0]) if rows else ['status','reason']
        writecsv(name,rows if status=='PASS' else [],headers)
    result={'status':status,'raw_endpoint_voltage_authority_exists':bool(raw),'preQ_aggregate':agg,'postQ_aggregate_secondary':postagg,'own_daily_maxima_separate_metric':maxima,'errors':errors,'checks':checks,'scientific_results_rerun_count':0}
    writej(OUT/'VALIDATION_DETAILS.json',result)
    report=['# V41R4 critical-line voltage validation',f'\nOverall status: **{status}**. Scientific result reruns: **0**.','\nPrimary: realized pre-Q. Secondary: final accepted post-Q. Reference points for both are the B0 pre-Q argmax.','\n## Authority and validation','- Voltage is read directly from archived `voltage_pu[slot,node_index]`; no inference, interpolation, or power-flow replay.','- Line current is archived `phase_current_a` and `phase_current_loading_pu`. Ratings and oriented endpoints are archived per-day, per-policy `BRANCH_PHASE_CURRENTS.parquet` topology fields. DA current observations are not used as realized currents.','- Sending/receiving means the archived from_bus/to_bus orientation (upstream/downstream topology), not the instantaneous direction of power flow. The literal DSS Bus1/Bus2 order was not inferred.','- All 96 slots and non-transformer line phases are searched. Switch elements recorded as lines are retained to match the paper authority. Exact ties select the first slot then first branch-phase in archived array ordering.','- Full node/branch axes, unique endpoint phase mapping, 96-slot convergence, finite voltages/currents, recorded current/rating ratios, final candidate and native output hashes, and paper maxima are checked.','- SD is sample SD (ddof=1). Improved/worsened requires a change outside +/-1e-12 pu; unchanged includes this floating-point tolerance. Raw differences are not rounded or zeroed.','- B0/B1 primary and secondary read CONTROL_COMMON_BINDING, with no Q correction. B2/B3 primary reads ETA95_ACTUAL; secondary reads ETA95_QSAFE_ACTUAL.','- No source rows are silently dropped. An authority failure suppresses scientific CSV data rows and aggregates, with errors below. Transformer-only NaNs in the unused total-kVA array are structural and are not endpoint-voltage missingness.']
    report+=['\n## Missing per-policy topology file, resolved by shared authority','The 2025-05-31 B2 DA BRANCH_PHASE_CURRENTS.parquet is absent. Its topology is read from same-day B0 only after verifying identical archived electrical certificate SHA256 (95c21f1edaa3e0409bec07e9b4e256e35e4865a181b766bc80763065428bbe9a) and electrical base-data SHA256 (c0204b833d301f72b35468866d581d4475e4e6e4525f486a210fe301be8279ce). The full final B2 branch-phase axis and all 96-slot line-current/rating ratios are independently checked against that map. B2 voltages and currents are still read exclusively from its own final raw NPZ. This is shared immutable topology, not voltage or current reconstruction.','\n## Errors',json.dumps(errors,ensure_ascii=False,indent=2),'\n## CSV row counts']+[f'- {n}: {v["rows"]}' for n,v in outputs.items()]
    report+=['\n## Primary pre-Q aggregate',json.dumps(agg,ensure_ascii=False,indent=2),'\n## Secondary post-Q aggregate',json.dumps(postagg,ensure_ascii=False,indent=2)]
    if status=='PASS':
        b3=agg[3];diff=b3['mean_abs_line_voltage_difference_change_vs_B0'];dev=b3['mean_receiving_voltage_deviation_change_vs_B0']
        report+=['\n## Interpretation',f'B0 daily maximum mean: {b0mean:.16f}. B3 mean same-point rho reduction: {b3["mean_rho_reduction_pct_vs_B0"]:.10f}%. Mean change in absolute line-voltage difference: {diff:.16g} pu. Mean change in receiving-end absolute deviation from 1 pu: {dev:.16g} pu.', 'The proposed sentence is supported as a descriptive mean association across these 31 fixed B0 reference points.' if diff < -tol and b3['mean_rho_reduction_pct_vs_B0']>0 else 'The proposed sentence is NOT supported by the mean pre-Q result and should not be used.', 'This comparison does not establish causality, universal daily improvement, or a feeder-wide voltage improvement. Separate receiving-end deviation results must be reported. These reference points mix line.l10 and line.sw2; absolute voltage differences are not normalized by segment length.']
    report+=['\nFull check records and distinct policy-own daily maxima: VALIDATION_DETAILS.json.']
    (OUT/'VALIDATION_REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    readme='''# V41R4 critical-line voltage analysis

Read-only post-processing of the final May 2025 archive, 31 dates and four policies.
See VALIDATION_REPORT.md for PASS/FAIL, results and limitations. No repository or frozen source is modified; no solver, OpenDSS, optimization, routing, SUMO, or ML calls are made.

01 contains B0 pre-Q daily critical references. 02 contains the 124 primary realized pre-Q same-point comparisons. 03 contains four primary aggregates (sample SD). 04 contains 31 primary daily paired records. 05 contains 124 secondary final accepted post-Q comparisons, using the same B0 pre-Q reference coordinates. A failed authority gate produces header-only scientific CSVs.

signed_voltage_change_pu = Vsend - Vrecv. abs_line_voltage_difference_pu = abs(Vsend - Vrecv). Endpoint deviations are abs(V - 1). All change_vs_B0 values are policy minus B0 in the same source state. rho_reduction_pct_vs_B0 = (rho_B0 - rho_policy)/rho_B0*100. Post-Q denominators use post-Q B0 values at the original pre-Q point. Changes in voltage metrics have units pu. Lower values improve these metrics. Status tolerance is 1e-12 pu; raw numbers preserve full archived float precision. Timestamps preserve fixed AEST (+10:00) and slots are zero-based 0..95.

Topology orientation is the raw recorded from_bus/to_bus, not inferred from line names or instantaneous flow. Ratings are read directly from the recorded current_limit_A column and checked across every line phase and time against final archived currents/loadings. Per-policy daily maxima in VALIDATION_DETAILS.json are a separate metric, not the same-point comparison.

Reproduce with bundled Python and numpy, pandas, pyarrow. pyarrow is installed locally under _deps (no repository dependency changes). Run:

    python extract_critical_line_voltage_analysis.py --stage intake
    python extract_critical_line_voltage_analysis.py --stage supplement
    python extract_critical_line_voltage_analysis.py --stage analyze

Analysis recomputes the full compressed archive SHA256 on each run. Intake streams the gzip tar and lists every file, copying only selected evidence to content-addressed files under selected_raw. Supplement makes one additional streaming pass for the per-day/per-policy topology and final candidate receipts. It never extracts the full archive. selected_raw_index.json maps exact archive member names to these copies and hashes. Analysis rechecks copied member hashes, archived output manifests, final candidate receipts, and source CSV controls. The missing 2025-05-31 B2 topology table is resolved by same-day B0 topology only after identical archived electrical authority hashes and full final array/rating checks. This resolution is explicitly recorded in CSV and validation files. All scripts and outputs stay in this new folder.
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    repository=Path(r'C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v41r4_final_results_pr')
    import subprocess
    git_head=subprocess.run(['git','-C',str(repository),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    for rel in ('tools/v41r4_final_snapshot/paper_export/export_v41r4_final_archive_to_csv.py','dayahead/v41/grid_archive.py','dayahead/v28r2/opendss_backend.py','dayahead/v28r2/opendss_mapping.py','dayahead/v41/electrical.py'):
        source(repository/rel)
    provenance={'status':status,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_files':source_files,'source_archive_sha256':archive_hash,'raw_archive_members_used':used,'extraction_method':'Two read-only gzip/tar sequential streaming passes; member listing plus selective content-addressed copies; no full extraction','intake':readj(OUT/'intake_summary.json'),'topology_source':topology_sources,'voltage_source':'Per-unit final pre_Q/final_Actual OPENDSS_PHASE_ARRAYS.npz voltage_pu with explicit node phase indices in CSV','line_current_source':'Same NPZ phase_current_loading_pu and phase_current_a; archived DA topology current_limit_A denominator cross-checked over all final line cells','preQ_interpretation':'Realized, DA decisions fixed; B0/B1 CONTROL_COMMON_BINDING, B2/B3 ETA95_ACTUAL','postQ_interpretation':'Secondary final accepted AC; B0/B1 CONTROL_COMMON_BINDING, B2/B3 ETA95_QSAFE_ACTUAL','reference_rule':'B0 preQ daily argmax, branch_kinds=line, 96 slots; first exact maximum in slot-major archived branch-phase order','orientation':'Archived topology from_bus/to_bus; no instantaneous flow claim','unchanged_tolerance_pu':tol,'SD_ddof':1,'CSV_files':outputs,'scripts_used':{'extract_critical_line_voltage_analysis.py':sha(Path(__file__))},'Git_HEAD_read_only':{'repository':str(repository),'HEAD':git_head},'scientific_results_rerun_count':0,'execution_counts':{k:0 for k in ('Gurobi','DA_optimization','AIDC_rescheduling','MESS_routing_search','SUMO','ML_training','ML_inference','OpenDSS')},'errors':errors,'dependency_versions':{'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'pyarrow':__import__('pyarrow').__version__}}
    writej(OUT/'MANIFEST.json',provenance)
    print(json.dumps({'status':status,'row_counts':{k:v['rows'] for k,v in outputs.items()},'preQ_aggregate':agg,'postQ_aggregate':postagg,'errors':errors},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['intake','supplement','analyze'],default='analyze');args=parser.parse_args()
    if args.stage=='intake':intake()
    elif args.stage=='supplement':supplement()
    else:analyze()
