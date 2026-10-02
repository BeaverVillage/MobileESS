"""Read-only, whole-root inventory. No raw payload is copied to the repository.

May is hashed/listed only for inventory; its job values/results are not read.
Metadata coverage is explicitly distinguished from observed row coverage.
"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pyarrow.parquet as pq

RAW_ROOT=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터')
OUT=Path(__file__).parent/'APRIL_V42_SOURCE_RECOVERY'
GPU=re.compile(r'gpu|(?<![a-z])(?:ReqGRES|ReqTRES|RegTRES|AllocTRES|GRES|TRES)(?![a-z])',re.I)
IDENTITY=re.compile(r'job|submit|submission|slurm|scheduler|accounting|kestrel',re.I)
TIME=re.compile(r'(?:^|[._])(?:date|time|timestamp|datetime|submit_time|start_time|end_time)(?:$|[._])',re.I)
STRUCTURED={'.csv','.tsv','.json','.jsonl','.parquet','.db','.xlsx'}


def native(path):
    value=os.path.abspath(path)
    return '\\\\?\\'+value if os.name=='nt' and not value.startswith('\\\\?\\') else value


def coverage(name):
    dates=sorted(set(re.findall(r'20\d{2}[-_]\d{2}[-_]\d{2}',name)))
    months=sorted(set(re.findall(r'20\d{2}[-_]\d{2}',name)))
    partition=re.search(r'year=(\d{4})/month=(\d{1,2})',name.replace('\\','/'))
    return dict(status='PATH_METADATA_ONLY' if dates or months or partition else 'NOT_DECLARED',
                dates=dates,months=months,partition=partition.group(0) if partition else None)


def json_fields(value,prefix=''):
    fields=set()
    if isinstance(value,dict):
        for k,v in value.items():
            key=prefix+str(k);fields.add(key)
            fields.update(json_fields(v,key+'.'))
    elif isinstance(value,list):
        # Schema discovery scans every object, not just a first-row sample.
        for v in value:fields.update(json_fields(v,prefix+'[].'))
    return fields


def xlsx_headers(path):
    """Standard-library schema read; no macros, formulas or workbook execution."""
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    result={}
    with zipfile.ZipFile(native(path)) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        for name in z.namelist():
            if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):continue
            with z.open(name) as f:
                for event,e in ET.iterparse(f,events=['end']):
                    if e.tag!=f"{{{ns['s']}}}row":continue
                    cells=[]
                    for c in e:
                        v=c.find('s:v',ns)
                        if c.get('t')=='s' and v is not None:cells.append(shared[int(v.text)])
                        elif c.get('t')=='inlineStr':cells.append(''.join(c.itertext()))
                        elif v is not None:cells.append(v.text)
                    if cells:result[name]=cells;break
    return result


def schema(stream,name):
    ext=Path(name).suffix.lower();result=dict(format=ext.lstrip('.') or 'no_extension',columns=[],date_coverage=coverage(name))
    if ext=='.parquet':
        p=pq.ParquetFile(stream);result['columns']=p.schema.names
        result['schema']=str(p.schema_arrow);result['rows']=p.metadata.num_rows
        dates={}
        for i in range(p.metadata.num_columns):
            field=p.schema.column(i)
            if not TIME.search(field.path):continue
            lows=[];highs=[]
            for g in range(p.metadata.num_row_groups):
                s=p.metadata.row_group(g).column(i).statistics
                if s is not None and s.has_min_max:lows.append(str(s.min));highs.append(str(s.max))
            if lows:dates[field.path]=dict(min=min(lows),max=max(highs),authority='PARQUET_ROW_GROUP_STATISTICS')
        if dates:result['date_coverage']=dates
    elif ext in {'.csv','.tsv'}:
        text=io.TextIOWrapper(stream,encoding='utf-8-sig',errors='replace',newline='')
        reader=csv.reader(text,delimiter='\t' if ext=='.tsv' else ',')
        first=[]
        for _ in range(12):
            try:first.append(next(reader))
            except StopIteration:break
        # Preserve schema, not sample raw data rows. AEMO uses I header records.
        headers=[r for r in first if r and r[0]=='I']
        result['columns']=list(dict.fromkeys(v for r in headers for v in r)) if headers else (first[0] if first else [])
        text.detach()
    elif ext in {'.json','.jsonl'}:
        if ext=='.json':value=json.load(stream)
        else:
            fields=set();rows=0
            for line in stream:
                if line.strip():fields.update(json_fields(json.loads(line)));rows+=1
            result['columns']=sorted(fields);result['rows']=rows;return result
        result['columns']=sorted(json_fields(value))
    result['GPU_related_fields']=[c for c in result['columns'] if GPU.search(str(c))]
    result['identity_fields']=[c for c in result['columns'] if IDENTITY.search(str(c))]
    return result


def inspect_file(path):
    absolute=os.path.abspath(path);name=str(path.relative_to(RAW_ROOT));ext=path.suffix.lower()
    row=dict(absolute_path=absolute,filename=path.name,size=None,SHA256=None,format=ext.lstrip('.') or 'no_extension',
             columns=[],date_coverage=coverage(name),status='READABLE',errors=[],archive_members=[])
    try:
        stat=os.stat(native(path));row['size']=stat.st_size
        h=hashlib.sha256()
        with open(native(path),'rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
        row['SHA256']=h.hexdigest()
        if ext in STRUCTURED- {'.db','.xlsx'}:
            with open(native(path),'rb') as f:row.update(schema(f,name))
        elif ext=='.db':
            # URI mode=ro plus immutable prevents creation of journal files.
            with sqlite3.connect(Path(absolute).as_uri()+'?mode=ro&immutable=1',uri=True) as db:
                tables=db.execute("select name from sqlite_master where type='table'").fetchall()
                row['columns']={t:[r[1] for r in db.execute('pragma table_info("'+t.replace('"','""')+'")')] for t, in tables}
        elif ext=='.xlsx':
            row['columns']=xlsx_headers(path)
        elif ext=='.zip':
            with zipfile.ZipFile(native(path)) as archive:
                for member in archive.infolist():
                    if member.is_dir():continue
                    item=dict(member=member.filename,size=member.file_size,format=Path(member.filename).suffix.lower(),
                              date_coverage=coverage(member.filename),columns=[],status='LISTED')
                    # No scientific holdout data values. Parquet schema/statistics
                    # are metadata, independently of the member's month.
                    suffix=Path(member.filename).suffix.lower()
                    inspect=suffix in STRUCTURED- {'.db','.xlsx'}
                    holdout=bool(re.search(r'2025[-_/]05|year=2025/month=5/',member.filename))
                    if inspect and (not holdout or suffix=='.parquet'):
                        try:
                            with archive.open(member) as f:item.update(schema(f,member.filename))
                            item['status']='SCHEMA_READ'
                        except Exception as e:item['status']='SCHEMA_ERROR';item['error']=str(e)
                    elif holdout:item['status']='HOLDOUT_LISTING_ONLY'
                    row['archive_members'].append(item)
        elif ext in {'.tgz','.bz2','.gz'} and tarfile.is_tarfile(native(path)):
            with tarfile.open(native(path),'r:*') as archive:
                for member in archive:
                    if not member.isfile():continue
                    item=dict(member=member.name,size=member.size,format=Path(member.name).suffix.lower(),
                              date_coverage=coverage(member.name),columns=[],status='LISTED')
                    if Path(member.name).suffix.lower() in STRUCTURED- {'.db','.xlsx','.parquet'}:
                        try:
                            with archive.extractfile(member) as f:item.update(schema(f,member.name))
                            item['status']='SCHEMA_READ'
                        except Exception as e:item['status']='SCHEMA_ERROR';item['error']=str(e)
                    row['archive_members'].append(item)
        # Search all textual scripts/logs/docs for resource declarations and UID
        # evidence, preserving only field names/counts, never the raw contents.
        if ext in {'.sh','.slurm','.txt','.log','.out','.yml','.yaml','.md','.html','.py','.json','.csv','.tsv','.jsonl',''} and stat.st_size<100*1024*1024:
            names=set();id_count=0
            with open(native(path),'r',encoding='utf8',errors='replace') as f:
                for line in f:
                    names.update(re.findall(r'(?i)ReqGRES|ReqTRES|RegTRES|AllocTRES|gpus_requested|gpu_nodes_occupied|GRES|--gpus(?:-per-node|-per-task)?|requested_gpus|GPU[_ ]count',line))
                    id_count+=len(re.findall(r'\b(?:7\d{6}|8\d{6})\b',line))
            row['text_resource_tokens']=sorted(names);row['April_UID_pattern_count']=id_count
        row['GPU_related_fields']=[str(c) for c in row['columns'] if GPU.search(str(c))]
        row['identity_fields']=[str(c) for c in row['columns'] if IDENTITY.search(str(c))]
    except Exception as e:
        row['errors'].append(dict(type=type(e).__name__,message=str(e)))
        row['status']='READ_ERROR' if row['SHA256'] is None else 'SCHEMA_ERROR'
    return row


def enumerate_files():
    files=[];walk_errors=[]
    for base,dirs,names in os.walk(native(RAW_ROOT),followlinks=False,onerror=lambda e:walk_errors.append(str(e))):
        dirs.sort()
        if base.startswith('\\\\?\\'):base=base[4:]
        files.extend(Path(base)/name for name in sorted(names))
    return files,walk_errors


def save_inventory(inventory,walk_errors):
    inventory=sorted(inventory,key=lambda r:r['absolute_path'])
    (OUT/'EXTERNAL_RAW_INVENTORY.json').write_text(json.dumps(inventory,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    with (OUT/'EXTERNAL_RAW_INVENTORY.csv').open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['absolute_path','filename','size','SHA256','format','columns','date_coverage','status','errors'])
        writer.writeheader()
        for row in inventory:
            writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],(list,dict)) else row[k] for k in writer.fieldnames})
    candidates=[r for r in inventory if IDENTITY.search(r['filename']) or r.get('GPU_related_fields') or r.get('text_resource_tokens') or
                any(m.get('GPU_related_fields') or m.get('identity_fields') or IDENTITY.search(m['member']) for m in r['archive_members'])]
    summary=dict(raw_root=str(RAW_ROOT),read_only=True,files_scanned=len(inventory),
      bytes_hashed=sum(r['size'] or 0 for r in inventory if r['SHA256']),files_hashed=sum(bool(r['SHA256']) for r in inventory),
      format_counts=dict(Counter(r['format'] for r in inventory)),status_counts=dict(Counter(r['status'] for r in inventory)),
      walk_errors=walk_errors,source_candidates=len(candidates),May_scientific_use=False,
      raw_files_copied_to_Git=0,coverage_note='Parquet row-group statistics or explicit path metadata. Unknown coverage remains NOT_DECLARED.',
      errors=[dict(path=r['absolute_path'],errors=r['errors']) for r in inventory if r['errors']])
    (OUT/'EXTERNAL_RAW_CANDIDATES.json').write_text(json.dumps(candidates,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
    (OUT/'EXTERNAL_RAW_SCAN_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary


def main():
    OUT.mkdir(parents=True,exist_ok=True);files,walk_errors=enumerate_files()
    inventory=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(inspect_file,files)):
            inventory.append(row)
            if (i+1)%1000==0:print(json.dumps(dict(scanned=i+1,total=len(files))),flush=True)
    summary=save_inventory(inventory,walk_errors)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'errors','format_counts'}},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
