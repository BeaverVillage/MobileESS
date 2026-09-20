from pathlib import Path
import csv,json,hashlib,math,time
from datetime import datetime,timezone
import numpy as np
OUT=Path(__file__).parent;ROOT=OUT.parent;FOLDER=OUT/'deliverables/IEEE123_2ROUND_PAPER_CSV'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
ex=read(OUT/'EXTRACTION_MANIFEST.json');payload=read(OUT/'EXTRACTED_TABLES.json')['tables'];checks=[];tables={}
for name,data in payload.items():
 path=FOLDER/(name+'.csv')
 with path.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);assert reader.fieldnames==data['columns'];rows=list(reader)
 assert len(rows)==len(data['rows'])
 for i,(saved,original) in enumerate(zip(rows,data['rows'])):
  for col in data['columns']:
   a=saved[col];b=original.get(col)
   if b is None:assert a=='',(name,i,col)
   elif isinstance(b,bool):assert a==str(b).lower()
   elif isinstance(b,(int,float)):assert math.isfinite(float(a)) and float(a)==b,(name,i,col,a,b)
   else:assert a==b,(name,i,col)
 tables[name]=rows
 rules=ex['rules'];specific={
  '01': ['numeric_precision','critical_line','feasible','runtime'],
  '02': ['stage','runtime','changes'], '03':['timestamp','critical_line','original_Actual_selection'],
  '04':['timestamp','numeric_precision'], '05':['timestamp','trajectory'],
  '06':['timestamp','trajectory'], '07':['changes'], '08':['aggregate','runtime']}
 checks.append(dict(filename=name+'.csv',row_count=len(rows),column_count=len(data['columns']),columns=data['columns'],sha256=sha(path),bytes=path.stat().st_size,
  source_artifacts=[dict(path=p,sha256=ex['sources'][p]['sha256']) for p in ex['table_sources'][name]],
  extraction_rule={k:rules[k] for k in specific[name[:2]]},verification='Every CSV cell checked against raw extraction; numeric values round-trip exactly'))
dates=[f'2025-05-{n:02}' for n in range(1,32)]
daily=tables['01_DAILY_1R_VS_2R_SUMMARY'];assert [r['date'] for r in daily]==dates
for name in ['03_ACTUAL_LINE_LOADING_TIMESERIES','04_ACTUAL_VOLTAGE_TIMESERIES']:
 rows=tables[name];assert len(rows)==31*96
 for day in dates:
  selected=[r for r in rows if r['date']==day];assert [int(r['slot']) for r in selected]==list(range(96))
  ts=[datetime.fromisoformat(r['timestamp_AEST']) for r in selected]
  assert all((b-a).total_seconds()==900 for a,b in zip(ts,ts[1:])) and ts[0].hour==0 and ts[-1].hour==23 and ts[-1].minute==45
for d in daily:
 lines=[r for r in tables['03_ACTUAL_LINE_LOADING_TIMESERIES'] if r['date']==d['date']]
 volts=[r for r in tables['04_ACTUAL_VOLTAGE_TIMESERIES'] if r['date']==d['date']]
 for round in ('1R','2R'):
  assert max(float(r[f'B3_{round}_actual_rho_max']) for r in lines)==float(d[f'B3_{round}_Actual_rho_max'])
  assert min(float(r[f'{round}_Vmin']) for r in volts)==float(d[f'{round}_Actual_Vmin'])
  assert max(float(r[f'{round}_Vmax']) for r in volts)==float(d[f'{round}_Actual_Vmax'])
 for phase in ('DA','Fresh','Actual'):
  assert float(d[f'B3_1R_{phase}_rho_max'])-float(d[f'B3_2R_{phase}_rho_max'])==float(d[phase+'_delta_1R_minus_2R'])
# Independent raw-array spot checks on all days: daily critical identifies its actual raw maximum.
for day in dates:
 p=ROOT/'production_v4_corrected/actual/replays'/day/'B3/ETA95_QSAFE_ACTUAL/OPENDSS_PHASE_ARRAYS.npz'
 with np.load(p,allow_pickle=False) as z:
  mask=z['branch_kinds']=='line';raw=z['phase_current_loading_pu'][:,mask]
  d=next(r for r in daily if r['date']==day);t=int(d['2R_critical_slot'])
  assert raw.max()==float(d['B3_2R_Actual_rho_max']) and raw[t].max()==raw.max()
for name,expected in [('05_MESS_2ROUND_TRAJECTORY',31*96*4),('06_AIDC_2ROUND_TRAJECTORY',31*96*12)]:
 rows=tables[name];assert len(rows)==expected
 entity='MESS_id' if name.startswith('05') else 'AIDC_id';assert len({(r['date'],r['slot'],r[entity]) for r in rows})==expected
for row in tables['07_ROUND2_DECISION_CHANGES']:assert row['before_1R']!=row['after_2R']
aggregate={r['metric']:r for r in tables['08_PAPER_AGGREGATE_METRICS']};tol=ex['equality_tolerance']['absolute_rho']
for phase in ('Actual','DA','Fresh'):
 delta=[float(r[phase+'_delta_1R_minus_2R']) for r in daily];suffix='' if phase=='Actual' else '_'+phase
 counts=[sum(x>tol for x in delta),sum(abs(x)<=tol for x in delta),sum(x<-tol for x in delta)]
 for key,val in zip(['number_of_days_2R_better_than_1R','number_of_days_equal','number_of_days_2R_worse_than_1R'],counts):assert int(aggregate[key+suffix]['B3_2R'])==val
 assert sum(counts)==31
for name,ref in ex['sources'].items():
 p=Path(name);s=p.stat();assert (s.st_size,s.st_mtime_ns)==(ref['bytes'],ref['mtime_ns']) and sha(p)==ref['sha256'],name
manifest=dict(schema='IEEE123_2ROUND_PAPER_CSV_SOURCE_MANIFEST_V1',created_at=datetime.now(timezone.utc).isoformat(),source_authority_consistency='PASS',
 archive_filename='../IEEE123_B3_2ROUND_MAY2025_RAW_RESULTS.tar.gz',campaign_status=ex['campaign_status'],source_roots=ex['source_roots'],
 csv_files=checks,source_artifact_catalog=ex['sources'],equality_tolerance=ex['equality_tolerance'],native_slot_minutes=15,slots_per_day=96,
 missing_or_unsupported=ex['unsupported_fields'],historical_lineage_complete=ex['historical_lineage_complete'],missing_historical_lineage=ex['missing_historical_lineage'],
 source_checks=ex['checks'],all_source_SHA256_rechecked=True,source_files_modified=0,encoding='UTF-8 with BOM; comma delimiter; CRLF; header excluded from row count',
 extractor=dict(path=str(OUT/'extract.py'),sha256=sha(OUT/'extract.py')),csv_author=dict(path=str(OUT/'build_csv.mjs'),sha256=sha(OUT/'build_csv.mjs')),
 verification=dict(status='PASS',exact_float_roundtrip=True,all_cells_verified=True,daily_timeseries_reconciliation=True,raw_arrays_independently_checked=True,
 all_dates_and_slots_complete=True,decision_changes_only=True,aggregate_tolerance_counts_verified=True))
manifest['optional_control_policy_sources']='B0/B1 verified CONTROL_COMMON_BINDING; B2 verified QSAFE, with May31 accepted restoration parent/rule SHA verified. These are final control results of the same pre-resiting V41R4 campaign.'
(FOLDER/'PAPER_CSV_SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'CSV_VERIFIED.json').write_text(json.dumps(dict(status='PASS',files=[{k:r[k] for k in ('filename','row_count','column_count','sha256')} for r in checks],source_count=len(ex['sources'])),indent=2))
print('CSV_VALIDATION_PASS',len(checks),'SOURCES',len(ex['sources']),flush=True)
