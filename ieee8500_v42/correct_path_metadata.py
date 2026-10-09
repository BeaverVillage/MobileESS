"""Static original-graph metadata correction; never compiles DSS or solves AC."""
from __future__ import annotations
import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from .common import ROOT,DATA,REPORT,read,write,table,receipt,sha

CORRECTION=REPORT/'PATH_METADATA_CORRECTION.json'


def static_original_graph():
    inventory=read(REPORT/'ORIGINAL_FEEDER_INVENTORY.json')
    source=DATA/'feeder'
    files={p.name.lower():p for p in source.iterdir() if p.is_file()}
    active=[];todo=['master-unbal.dss'];seen=set();reactors=[]
    while todo:
        filename=todo.pop(0)
        if filename in seen:continue
        seen.add(filename);p=files[filename]
        if sha(p)!=inventory['source_sha256'][p.name]:raise ValueError('ORIGINAL_FEEDER_STATIC_SHA_DRIFT')
        text=p.read_text(errors='replace');active.append(p)
        # Only active master redirects are followed; commented Generators.dss
        # and its neutral resistor are not added to the compiled graph.
        for line in text.splitlines():
            line=line.split('!')[0].strip()
            if not line or line.startswith('//'):continue
            redirect=re.match(r'(?i)^(?:redirect|include)\s+["\']?([^"\'\s]+)',line)
            if redirect:todo.append(Path(redirect.group(1)).name.lower())
            reactor=re.match(r'(?i)^new\s+reactor\.([^\s]+)\s+(.*)',line)
            if reactor:
                name,properties=reactor.groups();buses=[]
                for key in ('bus1','bus2'):
                    m=re.search(r'(?i)\b'+key+r'\s*=\s*([^\s!]+)',properties)
                    if not m:raise ValueError('ACTIVE_REACTOR_TERMINAL_PARSE_REQUIRED')
                    buses.append(m.group(1))
                enabled=not bool(re.search(r'(?i)\benabled\s*=\s*(?:no|false|0)\b',properties))
                reactors.append(dict(element='Reactor.'+name,buses=buses,enabled=enabled,source_file=p.name))
    if len(reactors)!=1 or reactors[0]['element'].lower()!='reactor.hvmv_sub_hsb':
        raise ValueError('EXACT_ORIGINAL_SOURCE_REACTOR_REQUIRED')
    adjacency=collections.defaultdict(list)
    for r in inventory['lines']+inventory['transformers']+reactors:
        if not r['enabled']:continue
        u=r['buses'][0].split('.')[0].lower()
        for terminal in r['buses'][1:]:
            v=terminal.split('.')[0].lower()
            if u==v:continue
            edge=r['element'].lower();adjacency[u].append((v,edge));adjacency[v].append((u,edge))
    parent={'sourcebus':None};edges={};todo=collections.deque(['sourcebus'])
    while todo:
        u=todo.popleft()
        for v,edge in sorted(adjacency[u]):
            if v not in parent:parent[v]=u;edges[v]=edge;todo.append(v)
    paths={}
    for bus in parent:
        u=bus;path=set()
        while parent[u] is not None:path.add(edges[u]);u=parent[u]
        paths[bus]=path
    original={r['bus'] for r in inventory['buses']}
    if len(paths)!=4876 or set(paths)!=original:raise ValueError('ALL_4876_ORIGINAL_BUSES_MUST_BE_SOURCE_REACHABLE')
    return paths,inventory,reactors,active


def numeric_signature(rows,fields,metadata_field):
    # Original string spelling is retained for every non-metadata cell, not only
    # float values after parsing; this catches silent rounding or row reordering.
    text=json.dumps([[r[k] for k in fields if k!=metadata_field] for r in rows],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(text.encode()).hexdigest()


def refresh_csv(path,paths):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
    field=next((name for name in ('original_source_to_PCC_path_contains_line','path_contains_line','path_contains_target') if name in fields),None)
    if field is None:raise ValueError('REQUESTED_METADATA_FIELD_ABSENT:'+str(path))
    before=receipt(path);signature=numeric_signature(rows,fields,field);changed=0;true_before=0;true_after=0
    for row in rows:
        bus=row['bus'].split('.')[0].lower();line=row['line'].lower()
        if bus not in paths:raise ValueError('SOURCE_PATH_CANDIDATE_UNREACHABLE:'+bus)
        old=row[field]=='True';new=line in paths[bus]
        true_before+=old;true_after+=new;changed+=old!=new;row[field]=str(new)
    table(path,rows,fields)
    with path.open(encoding='utf8',newline='') as stream:after_rows=list(csv.DictReader(stream))
    aftersignature=numeric_signature(after_rows,fields,field)
    if signature!=aftersignature:raise ValueError('AC_NUMERIC_OR_NONMETADATA_CELL_CHANGED')
    return dict(before=before,after=receipt(path),metadata_field=field,rows=len(rows),changed_cells=changed,
        true_before=true_before,true_after=true_after,all_nonmetadata_strings_SHA256=signature,
        all_nonmetadata_strings_unchanged=True)


def fix_references(value,updates):
    if isinstance(value,dict):
        if 'path' in value and 'sha256' in value:
            key=str(Path(value['path']).resolve()).lower()
            if key in updates:return updates[key]
        return {k:fix_references(v,updates) for k,v in value.items()}
    if isinstance(value,list):return [fix_references(v,updates) for v in value]
    return value


def run():
    if CORRECTION.exists():raise ValueError('PATH_METADATA_CORRECTION_ALREADY_RECORDED; do not overwrite historical before-SHA')
    paths,inventory,reactors,active=static_original_graph()
    files=[REPORT/'SENSITIVITY_RESULTS.csv',REPORT/'joint_selection_v2/witness_response/TOP20_RESPONSE.csv']
    files+=sorted((REPORT/'joint_selection_v2/sensitivity').glob('TOP20_RESPONSE_SLOT_*.csv'))
    files+=sorted((REPORT/'joint_selection_v3/mv_sensitivity').glob('TOP20_RESPONSE*.csv'))
    receipts=[REPORT/'joint_selection_v2/sensitivity/RECEIPT.json',
        REPORT/'joint_selection_v2/witness_response/RECEIPT.json',
        REPORT/'joint_selection_v3/mv_sensitivity/RECEIPT.json',
        REPORT/'joint_selection_v3/selection_scores/RECEIPT.json']
    before_receipts={str(p.relative_to(ROOT)):receipt(p) for p in receipts}
    numerics=[]
    for folder in (REPORT/'joint_selection_v2/sensitivity',REPORT/'joint_selection_v2/witness_response',
                   REPORT/'joint_selection_v3/mv_sensitivity'):
        for p in folder.iterdir():
            if p.is_file() and (p.suffix=='.npz' or 'SUMMARY' in p.name or 'VALIDATION' in p.name):numerics.append(p)
    before_numeric={str(p):sha(p) for p in numerics}
    records={str(p.relative_to(ROOT)):refresh_csv(p,paths) for p in files}
    if before_numeric!={str(p):sha(p) for p in numerics}:raise ValueError('UNRELATED_AC_NUMERIC_ARTIFACT_CHANGED')
    write(CORRECTION,dict(status='CORRECTED_ORIGINAL_SOURCE_PATH_METADATA_ONLY',
        cause='Original source series Reactor missing from prior inventory-only path traversal',
        method='independent static parsing of active Master redirects plus original line/transformer inventory; no DSS context',
        sourcebus_reachable_buses=len(paths),original_bus_count=len(inventory['buses']),reactors=reactors,
        graph_example_path_counts={bus:len(paths[bus]) for bus in ('l3234149','sx2748781a')},
        csv_files=records,prior_receipts=before_receipts,unchanged_numeric_artifacts_SHA256=before_numeric,
        original_source_inventory=receipt(REPORT/'ORIGINAL_FEEDER_INVENTORY.json'),
        active_source_files={p.name:receipt(p) for p in active},auditor_source=receipt(Path(__file__)),
        all_AC_numeric_cells_and_original_source_unchanged=True,AC_solves=0,Native_calls=0,full_model_builds=0))
    updates={str(Path(r['after']['path']).resolve()).lower():r['after'] for r in records.values()}
    for p in receipts:
        result=fix_references(read(p),updates)
        result['path_metadata_post_correction']=receipt(CORRECTION)
        result['AC_numerics_unchanged_by_metadata_correction']=True
        write(p,result)
    print('Path metadata corrected',len(files),'CSV files; reachable original buses',len(paths),flush=True)
    return read(CORRECTION)


if __name__=='__main__':run()
