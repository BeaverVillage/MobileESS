import csv,json,hashlib,zipfile,datetime
from pathlib import Path
OUT=Path(__file__).resolve().parent.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
x=load(OUT/'_work/tables.json'); authored=load(OUT/'_work/CSV_AUTHORING_VERIFICATION.json'); idx=x['archive_info']; archive=Path(x['archive'])
rawmanifest={r['path']:r for r in load(Path(str(archive)+'_FILE_MANIFEST.json'))}
for n,r in x['sources'].items():assert r['sha256']==rawmanifest[n]['sha256'] and r['bytes']==rawmanifest[n]['bytes'],n
checks=[]
def canon(v):
 if v is True:return 'true'
 if v is False:return 'false'
 return str(v)
for file in authored['files']:
 name=file['filename'];data=x['tables'][name]
 assert sha(OUT/name)==file['sha256']
 with (OUT/name).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
 assert rows[0]==data['headers'] and len(rows)-1==len(data['rows'])
 for r,e in zip(rows[1:],data['rows']):
  assert len(r)==len(e)
  for a,b in zip(r,e):
   if isinstance(b,(int,float)) and not isinstance(b,bool):assert float(a)==float(b),(name,a,b)
   else:assert a==canon(b),(name,a,b)
 checks.append(dict(file=name,status='PASS',row_count=len(rows)-1,sha256=file['sha256']))
unresolved=[c for c in x['checks'] if c['status']=='UNRESOLVED'];fail=[c for c in x['checks'] if c['status']=='FAIL']
status='PASS' if not fail else 'FAIL'
audit=['# IEEE8500 paper extraction audit','',f'IEEE8500 PAPER EXTRACTION: **{status}**',f'Extraction timestamp (UTC): {x["timestamp_utc"]}', 'SCIENTIFIC_EXECUTION_COUNT = 0 (this archive/extraction stage only).', '',f'Input archive: `{archive}`',f'SHA256: `{idx["archive_sha256"]}`',f'Archive bytes: {idx["archive_bytes"]}',f'Archive members: {idx["member_count"]}',f'Raw files: {idx["source_file_count"]}',f'Raw source bytes: {idx["source_bytes"]}',f'Evaluation date: 2025-05-21','', '## Scope and authority','', 'All IEEE8500 workspace directories and matching root files are included, including planning, Day-Ahead, Actual, coefficient matrices, trajectories, logs, checkpoints, input manifests, source, historical failures and diagnostics. External IEEE123/V41R4 repositories and raw SUMO dependencies referenced by manifests are not duplicated wholesale. This archive is not a self-contained relocated execution environment.','', 'The feeder is the canonical unbalanced IEEE8500 source with frozen 36 PCC transformers and declared compatibility adaptation: source1.0400pu, Vreg123.5V, alpha0.50, CAPBank3 OFF. This is not claimed as an unmodified canonical operating-point reproduction.', '', '### Final scope-specific result authorities','']
for scope,k in [('Day-Ahead','final_DA'),('Actual','final_Actual')]:
 for p,n in idx[k].items():audit.append(f'- {scope} {p}: `{n}`')
audit+=['', 'All old stopped, pre-binding, failed-primary and excluded diagnostic candidates remain historical. A stale RUNNING status in the stopped r2 folder does not indicate a live run; see r3 STOPPED_PREVIOUS_RUN.json. No historical candidate is promoted by extraction.','', '## Metric and runtime definitions','']+['- '+n for n in x['notes']]
audit+=['','- Final accepted B3 P1 comes from FINAL_AUTHORITY, not the lower-P1 MF trial RESULT. Raw original V41R4 algorithm source/semantics are intentionally reused; final IEEE8500 results are identified by the independent IEEE8500 numerical preflight, common coefficient SHA list, parsed counts and frozen electrical settings. No IEEE123 numerical results are substituted.','- Branch count is4911 distinct bus-to-bus graph corridors. There are3703 line elements and1226 transformer elements (4929 in total); parallel/single-phase bank elements do not equal graph corridors.','- `max_voltage_pu`, `min_voltage_pu`, and feasibility fields in policy summary refer to DAY_AHEAD_AC. Additional Actual fields are explicitly labelled. AC feasibility rows retain both scopes.','- DA violation counts count violating slots; Actual counts are recorded node/line-phase/transformer-row occurrences summed over slots. The units are labelled and not treated as identical counts.','- DA min/max bus-phase witnesses are absent from saved final AC JSON. Their time slots are extractable; bus/phase fields remain NA. Endpoint voltages are not recomputed.','- B3 total algorithm runtime includes reused final B1 runtime once; incremental runtime excludes it. AIDC search budgets are14400s each for B1 and B3 A1, not a14400s total cap on M1/A1/MF. B3 paper A1=raw A0/B1 reuse, paper A2=raw A1, paper M2=raw MF.','- Search time-limit termination and no global certificate are preserved. A local LP/MILP optimum or bound is not a global optimum/bound for the whole policy.','- OBJECTIVE_TIME_TRACE_AVAILABLE = true. Each record labels its clock origin; absent per-neighborhood elapsed times are NA rather than cumulative solver-time approximations.','', '## Unresolved fields','']
audit += ['- '+c['check_id']+': '+c['observed'] for c in unresolved]
audit += ['- Missing saved source: `'+n+'`' for n in x['missing_sources']]
if fail:audit+=['','## Failed scientific evidence checks','']+['- '+c['check_id']+': '+c['observed'] for c in fail]
audit+=['','## CSV outputs and aggregation provenance','','| File | Rows | SHA256 |','|---|---:|---|']
for f in authored['files']:audit.append(f'| {f["filename"]} | {f["row_count"]} | `{f["sha256"]}` |')
for f in authored['files']:
 audit+=['',f'### {f["filename"]}',f['description'],'','Source archive members:']+['- `'+n+'`' for n in f['source_files']]
audit+=['','## Read-only preservation and package verification','','Every archived source file was verified by SHA256, size and original mtime after archive construction. Every tar member was decompressed and checked against its original SHA256. Every CSV cell was compared against extraction tables; every extraction source SHA was matched to the full archive manifest.','CSV authoring used Artifact Tool worksheet ranges and exact public-range readback, then UTF-8 BOM/RFC4180 CSV serialization. No scientific engine was invoked by these scripts.']
auditpath=OUT/'IEEE8500_PAPER_EXTRACTION_AUDIT.md';auditpath.write_text('\n'.join(audit)+'\n',encoding='utf-8')
manifest={'status':status,'scientific_execution_count':0,'archive':str(archive),'archive_sha256':idx['archive_sha256'],'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':authored['files']+[dict(filename=auditpath.name,row_count=None,sha256=sha(auditpath),source_files=sorted(x['sources']),description='Read-only provenance, authority, metric and limitation audit',status=status)],'source_files':x['sources'],'csv_cell_verification':checks,'scientific_evidence_failures':fail,'unresolved_checks':unresolved}
mp=OUT/'IEEE8500_PAPER_CSV_MANIFEST.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
zp=OUT/'IEEE8500_PAPER_CSV_UPLOAD.zip'
with zipfile.ZipFile(zp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for f in authored['files']:z.write(OUT/f['filename'],f['filename'])
 z.write(auditpath,auditpath.name);z.write(mp,mp.name)
with zipfile.ZipFile(zp) as z:
 assert z.testzip() is None
 assert set(z.namelist())=={f['filename'] for f in authored['files']}|{auditpath.name,mp.name}
 for n in z.namelist():assert hashlib.sha256(z.read(n)).hexdigest()==sha(OUT/n)
verification={'status':status,'archive':str(archive),'archive_sha256':idx['archive_sha256'],'zip':str(zp),'zip_sha256':sha(zp),'zip_bytes':zp.stat().st_size,'zip_members':len(authored['files'])+2,'csv_count':len(authored['files']),'cell_verification':'PASS','scientific_execution_count':0}
(OUT/'_work/FINAL_EXPORT_VERIFICATION.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps(verification,ensure_ascii=False))
