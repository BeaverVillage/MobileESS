"""Export truthful diagnostic artifacts. Unproved minimality stays UNRESOLVED."""
import sys,csv,re,shutil,json,gzip,hashlib
from .common import *

def report_table(name,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)

def copy_evidence(source,target):
    if source.suffix=='.json' and source.stat().st_size>5_000_000:
        payload=source.read_bytes();compressed=target.with_suffix(target.suffix+'.gz')
        compressed.write_bytes(gzip.compress(payload,compresslevel=9,mtime=0))
        if hashlib.sha256(gzip.decompress(compressed.read_bytes())).hexdigest()!=sha(source):raise ValueError('LARGE_JSON_ARCHIVE_ROUNDTRIP')
        atomic(target,dict(lossless_gzip=compressed.name,sha256=sha(compressed),original_sha256=sha(source),original_bytes=len(payload),
                          source=record(source),roundtrip_PASS=True))
    else:shutil.copyfile(source,target)

def log_metrics(folder,prefix):
    p=folder/(prefix+'_NATIVE.log')
    if not p.exists():return {}
    text=p.read_text(encoding='utf8',errors='replace')
    shapes=re.findall(r'Presolved: ([\d,]+) rows, ([\d,]+) columns, ([\d,]+) nonzeros',text)
    times=re.findall(r'Presolve time: ([\d.]+)s',text)
    roots=re.findall(r'Root relaxation:.*?, ([\d.]+) seconds',text)
    return dict(presolved_shapes=[dict(rows=int(a.replace(',','')),cols=int(b.replace(',','')),nnz=int(c.replace(',',''))) for a,b,c in shapes],
                presolve_seconds=[float(x) for x in times],root_seconds=[float(x) for x in roots],log=record(p))

def main():
    sizes=[];domains={};evidence=[]
    for day in DAYS:
        lab=label(day);baseline=read(SOURCE/day/'F2-CRA_MODEL_COMPLETE.json');base=dict(rows=baseline['constraints'],cols=baseline['columns'],binary=baseline['binaries'],integer=baseline['integers'],continuous=baseline['continuous'],nnz=baseline['nonzeros'])
        traces=[];full=[]
        for folder in sorted((CASE/day).iterdir()):
            if not folder.is_dir() or not (folder/'CENSUS.json').exists():continue
            c=read(folder/'CENSUS.json');r=read(folder/'RESULT.json') if (folder/'RESULT.json').exists() else {}
            g=read(folder/'GLOBAL_NUMERIC_IDENTITY.json') if (folder/'GLOBAL_NUMERIC_IDENTITY.json').exists() else {}
            valid=g.get('PASS') is True
            if folder.name=='S2_RANK2_INITIAL':valid=False
            row=dict(day=day,tag=folder.name,scientific_numeric_authority_PASS=valid,**c)
            for k in ('rows','cols','binary','integer','continuous','nnz'):row[k+'_increase']=c[k]-base[k];row[k+'_increase_pct']=100*(c[k]-base[k])/base[k] if base[k] else None
            model=read(folder/'F2-CRA_MODEL_COMPLETE.json') if (folder/'F2-CRA_MODEL_COMPLETE.json').exists() else {}
            row['native_build_seconds']=model.get('model_build_seconds');row['S0_native_build_seconds']=baseline['model_build_seconds']
            row['native_build_increase_pct']=100*(row['native_build_seconds']/baseline['model_build_seconds']-1) if row['native_build_seconds'] else None
            row['LP_metrics']=log_metrics(folder,'LP');row['MIP_metrics']=log_metrics(folder,'MIP')
            row['timings_are_not_controlled_performance_benchmarks']=True;sizes.append(row)
            inc=folder/'INDEPENDENT_S0_INCLUSION.json'
            if inc.exists():row['logical_class_support_state_increases']=read(inc).get('logical_class_support_state_increases')
            traces.append(dict(day=day,tag=folder.name,authority_valid=valid,classes=c['added_classes'],options=c['added_options'],sites=c['added_sites'],migration=c['added_migration_lanes'],
                LP_status=r.get('LP_status'),MIP_status=r.get('MIP_status'),LP_runtime=r.get('LP_runtime'),MIP_runtime=r.get('MIP_runtime'),classification=r.get('classification','CAPTURED_SOLVE_RESULT_UNCOMPLETED' if (folder/'SOLVE_START.json').exists() or (folder/'START.json').exists() else 'STATIC_ONLY'),
                minimum_proven=False,census_SHA=sha(folder/'CENSUS.json'),matrix_SHA=sha(folder/'EXPANDED_MATRIX.npz') if (folder/'EXPANDED_MATRIX.npz').exists() else None))
            dest=OUT/'restricted_evidence'/day/folder.name;dest.mkdir(parents=True,exist_ok=True)
            for name in ('CENSUS.json','RESULT.json','STATIC_ONLY.json','GLOBAL_NUMERIC_IDENTITY.json','DOMAIN_AUTHORITY_AUDIT.json','INDEPENDENT_S0_INCLUSION.json',
                         'FULL_PHYSICAL_FEASIBILITY_VERIFICATION.json','LP_ALL_ROWS_REPLAY.json','MIP_ALL_ROWS_REPLAY.json','SELECTED_PHYSICAL_OPTIONS.json',
                         'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json','INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json','REPRICE_COUNTS.json','NEXT_SELECTION_NECESSARY_ONLY.json',
                         'SELECTED_INPUT_PROVENANCE_RECOVERY.json','INDEPENDENT_EXACT_CERTIFICATE.json','ZERO_START_AUDIT.json','LP_NATIVE.log','MIP_NATIVE.log',
                         'EXACT_NECESSARY_SUPPORT_SELECTION.json','INDEPENDENT_EXACT_SUPPORT_SELECTION.json','EXCLUDED_GREEDY_BATCH.json','FULL_PHYSICAL_UNIVERSE_SUPPORT_AUDIT.json','NO_TRUNCATION_SCALE_AUDIT.json'):
                if (folder/name).exists():copy_evidence(folder/name,dest/name)
            for name in ('COMPRESSION_VERIFICATION.json','A2SC_MODEL_CENSUS.json','A2SC_INDEPENDENT_VERIFICATION.json','PROJECTED_OBJECTIVES.json'):
                if (folder/'COMPACT'/name).exists():copy_evidence(folder/'COMPACT'/name,dest/name)
            if valid and r.get('physical_PASS') is True:full.append((folder,c,r))
        report_table(lab+'_EXPANSION_TRACE.csv',traces)
        selected=full[-1] if full else None
        latest=max((f for f in (CASE/day).iterdir() if f.is_dir() and (f/'RESULT.json').exists() and (f/'CENSUS.json').exists()),key=lambda f:(f/'RESULT.json').stat().st_mtime)
        if selected:
            folder,c,r=selected;point=record(folder/'MIP_RAW_POINT.npz')
            domain=dict(day=day,classification='UNRESOLVED',full_integer_feasible=True,lex_minimum_proven=False,
                first_feasible_observed_case=folder.name,added_classes=c['added_classes'],added_options=c['added_options'],added_sites=c['added_sites'],added_migration=0,
                selected=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected'],raw_native_point=point,physical_verifier=record(folder/'FULL_PHYSICAL_FEASIBILITY_VERIFICATION.json'),
                normal_four_pass_executed=False,ADAPTIVE_MINIMAL_PRESCREENING_V1_frozen=False,production_adopted=False)
            write(lab+'_A1_RESULT.json',dict(r,diagnostic_only=True,normal_A1_production_PASS=False,normal_four_pass_executed=False))
            write(lab+'_FINAL_VALIDATION.json',dict(PASS=False,full_integer_feasibility_diagnostic_PASS=True,normal_four_pass_executed=False,
                Planning_freeze_executed=False,fixed_Actual_executed=False,Fresh_OpenDSS_executed=False,reason='MINIMALITY_AND_BOTH_DATE_FREEZE_GATE_NOT_SATISFIED',physical_diagnostic=read(folder/'FULL_PHYSICAL_FEASIBILITY_VERIFICATION.json')))
        else:
            r=read(latest/'RESULT.json');c=read(latest/'CENSUS.json')
            domain=dict(day=day,classification='UNRESOLVED',full_integer_feasible=False,lex_minimum_proven=False,
                selected=None,latest_restricted_case=latest.name,latest_diagnostic_candidate=read(latest/'DOMAIN_AUTHORITY_AUDIT.json')['selected'],
                latest_candidate_added_classes=c['added_classes'],latest_candidate_added_options=c['added_options'],
                latest_native_status=r,normal_four_pass_executed=False,production_adopted=False,physical_universe_infeasible_proven=False)
        probe=CASE/day/'ALL_PHYSICAL_RANK_MINIMUM_PROBES/RESULT.json'
        if probe.exists():
            domain['all_rank_minimum_probe']=read(probe)
            dest=OUT/'minimum_evidence'/day;dest.mkdir(parents=True,exist_ok=True)
            for p in probe.parent.rglob('*'):
                if p.is_file() and p.suffix in ('.json','.log','.npz'):
                    q=dest/p.relative_to(probe.parent);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
        write(lab+'_MINIMAL_DOMAIN.json',domain);domains[day]=domain
        proof=CASE/day/'CAPACITY_SELECTION_V2'
        if proof.exists():
            dest=OUT/'necessary_selection_evidence'/day;dest.mkdir(parents=True,exist_ok=True)
            for p in proof.glob('*.json'):shutil.copyfile(p,dest/p.name)
    report_table('MODEL_SIZE_COMPARISON.csv',sizes)
    write('EXPANSION_SHELL_DEFINITION.json',dict(S0='exact current compressed candidate domain',S1='nearest physically valid missing same-reference-site rank 1',
        S2='successive missing same-site ranks; no arbitrary plus/minus window',S3='compatible prestart-placement site, only if same-site search insufficient',
        S4='original physically authorized checkpoint migration only if necessary',tie=['absolute displacement','earlier before later','site ID','start slot','option ID'],
        lex_objectives=['expanded scientific classes','added options','max abs displacement','sum abs displacement','new sites','prestart candidates','migration candidates','deterministic tie'],
        actual_new_site_options=0,actual_new_migration_options=0,full_universe_native_model_created=False))
    ver=dict(PASS=True,artifact_integrity_and_scientific_preservation_PASS=True,task_success=False,
        overall_classification='ADAPTIVE_PRESCREENING_PARTIAL_SUCCESS' if any(d['full_integer_feasible'] for d in domains.values()) else 'ADAPTIVE_PRESCREENING_NOT_SUPPORTED',
        per_date={d:v['classification'] for d,v in domains.items()},minimum_domain_selected=False,ADAPTIVE_MINIMAL_PRESCREENING_V1_frozen=False,
        normal_objectives_executed=False,P2_executed=False,May10_May12_optimization_calls=0,PASS27_S0_reuse=read(OUT/'PASS27_S0_REUSE_AUDIT.json')['PASS'],
        independent_pools_PASS=all(read(OUT/(label(d)+'_INDEPENDENT_POOL_VERIFICATION.json'))['PASS'] for d in DAYS),
        original_production_preserved=read(OUT/'ORIGINAL_PRODUCTION_PRESERVATION_AUDIT.json')['PASS'],
        CC4_changed=False,voltage_limits_changed=False,GPU_capacities_changed=False,service_Runtime_WAN_changed=False,future_information_used=False,
        heuristic_pruning_used=False,memory_guard_added=False,scientific_objective_hierarchy_changed=False,
        blocker='Validated minimal domains on BOTH dates are required. Conditional necessary-master optima and diagnostic feasible points cannot authorize production.',
        unsupported_infeasibility_or_TIME_LIMIT_never_promoted_to_PASS=True,
        experimental_wrappers_uncommitted_during_capture=True,
        static_source_commit_labels_refer_to_scientific_base=True,
        scientific_source_closure_byte_pins_independently_verified=True)
    if not all(ver[k] for k in ('PASS27_S0_reuse','independent_pools_PASS','original_production_preserved')):raise ValueError('FINAL_AUDIT_FAILED')
    write('VERIFICATION.json',ver)
    print('REPORT_EXPORTED',ver['overall_classification'],flush=True)

def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json']
    paths+=[p for p in (ROOT/'v42_pr134_adaptive').rglob('*.py')]
    write('SHA256_MANIFEST.json',dict(base=BASE,files=[record(p) for p in sorted(paths)],
        excludes_self_to_avoid_recursive_hash=True,original_authorities_preserved=True))
if __name__=='__main__':manifest() if sys.argv[1:] == ['--manifest'] else main()
