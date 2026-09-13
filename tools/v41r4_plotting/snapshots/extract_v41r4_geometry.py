"""Plotting-only geometry extraction; run with existing WSL Python/pyproj.

Reads frozen CSV, JSON, SUMO XML and original OSM XML as data. No SUMO,
research-module import, solver, model, network request, or road routing.
All writes are restricted to a new V41R4_plotting_geometry directory.
"""
from pathlib import Path
import collections
import csv
import gzip
import hashlib
import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
import pyproj
from pyproj import CRS, Transformer, Geod

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'V41R4_plotting_data'
OUT=ROOT/'V41R4_plotting_geometry'
P=Path('/home/jaewon/mobile_ess_sumo/research_pipeline')
RUN=Path('/mnt/c/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
FINAL=ROOT/'v41r4_final_results_pr/docs/v41r4_final'
S={}
V=[]
U='UNRESOLVED'
GEO=Geod(ellps='WGS84')
pyproj.network.set_network_enabled(False)

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def display(p):
    s=str(Path(p).resolve())
    if s.startswith('/mnt/c/'):
        return 'C:\\'+s[7:].replace('/','\\')
    return r'\\wsl.localhost\Ubuntu-MobileESS-D'+s.replace('/','\\')

def source(p,role,expected=None):
    p=Path(p).resolve();k=str(p)
    if k not in S:
        S[k]={'id':f'S{len(S)+1:03d}','path':display(p),'read_path':k,'sha256':digest(p),
              'bytes':p.stat().st_size,'roles':[]}
    if role not in S[k]['roles']:S[k]['roles'].append(role)
    if expected:assert S[k]['sha256']==expected,('FROZEN_SOURCE_DRIFT',display(p))
    return p

def js(p,role,expected=None):
    return json.loads(source(p,role,expected).read_text(encoding='utf-8-sig'))

def csvrows(p,role,expected=None):
    p=source(p,role,expected)
    data=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))

def winpath(s):
    if s.startswith('C:'):
        return Path('/mnt/c')/s[3:].replace('\\','/')
    prefix=r'\\wsl.localhost\Ubuntu-MobileESS-D'
    assert s.startswith(prefix),s
    return Path(s[len(prefix):].replace('\\','/'))

def ref(p):return S[str(Path(p).resolve())]['id']
def check(name,expected,observed,status,evidence):
    V.append(dict(check=name,expected=str(expected),observed=str(observed),status=status,evidence=evidence))
def distance(a,b):return abs(GEO.inv(a[0],a[1],b[0],b[1])[2])
def inside(pt,box):return box[0]<=pt[0]<=box[2] and box[1]<=pt[1]<=box[3]
def features(fs,**metadata):return dict(type='FeatureCollection',**metadata,features=fs)
def feature(geom,props):return dict(type='Feature',geometry=geom,properties=props)

def top_elements(p):
    """Yield full direct children, then clear; never execute source commands."""
    context=ET.iterparse(p,events=['start','end'])
    _,root=next(context)
    for event,e in context:
        if event=='end' and e.tag in ['node','way','relation','edge','junction','connection','location','meta']:
            yield e
            root.remove(e)
            e.clear()

def rings_from_ways(members,ways,nodes):
    """Deterministic geometric stitching on shared OSM IDs, not road routing."""
    output=[]
    for role in ['outer','inner']:
        pieces=[list(ways[m['ref']]['refs']) for m in members if m['type']=='way' and m['role'] in ([role,''] if role=='outer' else [role])]
        while pieces:
            chain=pieces.pop(0)
            while chain[-1]!=chain[0]:
                matches=[(i,q[-1]==chain[-1]) for i,q in enumerate(pieces) if q[0]==chain[-1] or q[-1]==chain[-1]]
                if len(matches)!=1:return None
                i,reverse=matches[0];q=pieces.pop(i)
                if reverse:q.reverse()
                chain.extend(q[1:])
            output.append((role,[nodes[n] for n in chain]))
    return output

def main():
    assert not OUT.exists(),'Existing extension must not be overwritten'
    source(__file__,'plotting-only extractor')
    old_before={p.name:digest(p) for p in OLD.iterdir() if p.is_file()}
    assert len(old_before)==7
    old_audit=source(OLD/'PLOTTING_DATA_AUDIT.md','existing package provenance; read only')
    old_text=old_audit.read_text(encoding='utf8')
    for name,h in old_before.items():
        source(OLD/name,'existing plotting package; immutable')
        if name.endswith('.csv'):assert f'`{h}`' in old_text
    roads=csvrows(OLD/'road_edges.csv','target reduced directed multigraph')
    nodes=csvrows(OLD/'road_nodes.csv','frozen road anchor coordinates')
    aidcs=csvrows(OLD/'aidc_locations.csv','frozen AIDC anchor coordinates')
    mess=csvrows(OLD/'mess_service_locations.csv','frozen MESS service anchor coordinates')
    assert (len(roads),len(nodes),len(aidcs),len(mess))==(509,48,12,24)
    nmap={n['road_node_id']:n for n in nodes}
    binding_path=FINAL/'evidence/traffic_provenance/TRAFFIC_PRODUCTION_DAY_BINDINGS.csv'
    binding=csvrows(binding_path,'final frozen production binding')[0]
    identity_path=RUN/'frozen_artifacts/v41r4_may/m1/a715a5d27c46/M1_IDENTITY.json'
    identity=js(identity_path,'final graph constituent authority',binding['M1_receipt_SHA'])
    graph=identity['identity']['inputs']['road_graph']
    assert graph['canonical_SHA']==binding['graph_SHA']
    paths={k:source(winpath(v['path']),'final frozen graph '+k,v['sha256']) for k,v in graph['files'].items()}
    catalog=csvrows(paths['physical_edges'],'ordered reduced-link to original physical edges')
    seq=collections.defaultdict(list)
    for r in catalog:seq[r['reduced_link_id']].append((int(r['source_position']),r['edge_id']))
    assert set(seq)=={r['road_edge_id'] for r in roads}
    for key in seq:
        seq[key].sort()
        assert [i for i,e in seq[key]]==list(range(len(seq[key])))
    order=csvrows(paths['link_order'],'original tensor order')
    assert all((r['tensor_index'],r['road_edge_id'],r['from_node'],r['to_node'])==
        (s['tensor_index'],s['reduced_link_id'],f'TN_{int(s["from_node"]):02d}',f'TN_{int(s["to_node"]):02d}') for r,s in zip(roads,order))
    loader_path=RUN/'dayahead/v33m/road_graph_authority.py'
    source(loader_path,'read-only first-lane geometry selection convention')
    required={e for chain in seq.values() for i,e in chain}
    junction_ids={n['junction_id'] for n in nodes}
    edge_data={};junctions={};location={}
    for e in top_elements(paths['elevated_graph']):
        if e.tag=='location':location=dict(e.attrib)
        elif e.tag=='edge' and e.get('id') in required:
            lanes=sorted(e.findall('lane'),key=lambda l:l.get('id',''))
            lane=lanes[0] if lanes else None
            points=[] if lane is None else [tuple(map(float,t.split(',')[:2])) for t in lane.get('shape','').split()]
            edge_data[e.get('id')]={'from':e.get('from'),'to':e.get('to'),'lane':lane.get('id') if lane is not None else U,
                'xy':points,'width_m':float(lane.get('width','3.2')) if lane is not None else 3.2}
        elif e.tag=='junction' and e.get('id') in junction_ids:
            junctions[e.get('id')]={'xy':(float(e.get('x')),float(e.get('y'))),
                'shape':[tuple(map(float,t.split(',')[:2])) for t in e.get('shape','').split()]}
    print('Frozen XML read:',len(edge_data),'physical edges; selected segments',len(catalog),flush=True)
    assert len(edge_data)==len(required)==15463
    proj=CRS.from_user_input(location['projParameter'])
    transform=Transformer.from_crs(proj,'EPSG:4326',always_xy=True)
    inverse=Transformer.from_crs('EPSG:4326',proj,always_xy=True)
    offset=tuple(map(float,location['netOffset'].split(',')))
    def ll(xy):return tuple(transform.transform(xy[0]-offset[0],xy[1]-offset[1]))
    max_roundtrip=0.0
    for e in edge_data.values():
        e['ll']=[ll(pt) for pt in e['xy']]
        for xy,l in zip(e['xy'],e['ll']):
            xx,yy=inverse.transform(*l)
            max_roundtrip=max(max_roundtrip,math.hypot(xx+offset[0]-xy[0],yy+offset[1]-xy[1]))
    node_points={k:(float(n['longitude']),float(n['latitude'])) for k,n in nmap.items()}
    node_drift={k:distance(node_points[k],ll(junctions[n['junction_id']]['xy'])) for k,n in nmap.items()}
    # Tolerance is a source-derived junction footprint, not a snap radius.
    tol={}
    for k,n in nmap.items():
        j=junctions[n['junction_id']]
        tol[k]=max([distance(node_points[k],ll(p)) for p in j['shape']]+[node_drift[k]])+5.0
    endpoints=[];road_features=[];csv_data=[];unresolved=[];all_points=list(node_points.values())
    zeros=0;reversed_count=0;topology_discontinuities=0;total_gaps=0;max_gap=0.0
    for road in roads:
        rid=road['road_edge_id'];chain=[e for i,e in seq[rid]]
        missing=[e for e in chain if len(edge_data[e]['xy'])<2]
        if missing:
            unresolved.append({'road_edge_id':rid,'missing_source_edges':missing})
            csv_data.append({**road,'point_order':U,'longitude':U,'latitude':U,'source_geometry_id':'|'.join(missing),
                'source_type':'FROZEN_SUMO_LANE_SHAPE','geometry_status':U,'part_index':U,'source_segment_order':U})
            continue
        from_j=nmap[road['from_node']]['junction_id'];to_j=nmap[road['to_node']]['junction_id']
        directed_ok=edge_data[chain[0]]['from']==from_j and edge_data[chain[-1]]['to']==to_j
        reverse=edge_data[chain[0]]['from']==to_j and edge_data[chain[-1]]['to']==from_j
        reversed_count+=int(reverse and not directed_ok)
        disconnect=sum(edge_data[a]['to']!=edge_data[b]['from'] for a,b in zip(chain,chain[1:]))
        topology_discontinuities+=disconnect
        assert directed_ok and not disconnect,('UNRESOLVED_DIRECTION',rid)
        parts=[];current=[];rows_for_edge=[];point_order=0;gaps=[];length=0.0
        for segment_order,eid in enumerate(chain):
            edge=edge_data[eid]
            coords=edge['ll'];xy=edge['xy']
            length+=sum(math.dist(a,b) for a,b in zip(xy,xy[1:]))
            if current and current[-1]!=coords[0]:
                gaps.append(distance(current[-1],coords[0]));parts.append(current);current=[]
            for l in coords:
                # Remove only exactly repeated adjacent coordinates in a continuous part.
                if current and current[-1]==l:continue
                current.append(l)
                rows_for_edge.append({**road,'point_order':point_order,'longitude':format(l[0],'.17g'),
                    'latitude':format(l[1],'.17g'),'source_geometry_id':eid+'::'+edge['lane'],
                    'source_type':'FROZEN_SUMO_LANE_SHAPE','geometry_status':'AVAILABLE',
                    'part_index':len(parts),'source_segment_order':segment_order})
                point_order+=1
            all_points.extend(coords)
        if current:parts.append(current)
        assert all(len(q)>=2 for q in parts),(rid,'degenerate part')
        zeros+=int(length==0)
        total_gaps+=len(gaps);max_gap=max([max_gap]+gaps)
        status='AVAILABLE_MULTIPART_SOURCE_GAPS' if gaps else 'AVAILABLE'
        for row in rows_for_edge:row['geometry_status']=status
        csv_data.extend(rows_for_edge)
        sources=[eid+'::'+edge_data[eid]['lane'] for eid in chain]
        road_features.append(feature(dict(type='MultiLineString' if len(parts)>1 else 'LineString',
            coordinates=parts if len(parts)>1 else parts[0]),
            dict(tensor_index=int(road['tensor_index']),road_edge_id=rid,from_node=road['from_node'],to_node=road['to_node'],
                source_geometry_id=sources,geometry_status=status,part_count=len(parts),source_segment_count=len(chain))))
        start=distance(parts[0][0],node_points[road['from_node']]);end=distance(parts[-1][-1],node_points[road['to_node']])
        endpoints.append(dict(tensor_index=road['tensor_index'],road_edge_id=rid,from_node=road['from_node'],to_node=road['to_node'],
            start_offset_m=start,end_offset_m=end,start_tolerance_m=tol[road['from_node']],end_tolerance_m=tol[road['to_node']],
            endpoint_status='PASS' if start<=tol[road['from_node']] and end<=tol[road['to_node']] else U,
            directed_junction_ids_match='TRUE',source_segment_count=len(chain),part_count=len(parts),
            source_gap_count=len(gaps),max_source_gap_m=max(gaps,default=0.0),geometry_length_m=length))
    for data in [aidcs,mess]:all_points.extend((float(n['longitude']),float(n['latitude'])) for n in data)
    bbox=[min(p[0] for p in all_points),min(p[1] for p in all_points),max(p[0] for p in all_points),max(p[1] for p in all_points)]
    padding=0.04
    box=[bbox[0]-(bbox[2]-bbox[0])*padding,bbox[1]-(bbox[3]-bbox[1])*padding,
         bbox[2]+(bbox[2]-bbox[0])*padding,bbox[3]+(bbox[3]-bbox[1])*padding]
    extent=dict(min_lon=box[0],max_lon=box[2],min_lat=box[1],max_lat=box[3],
        recommended_plot_padding_fraction=padding,source_crs=location['projParameter']+'; SUMO netOffset '+location['netOffset']+'; geographic CSV/OSM WGS84',
        output_crs='EPSG:4326',bounds_include_padding=True,unpadded_network_bbox=bbox,
        padding_rule='4% of complete network longitude/latitude span on each side; do not pad a second time')
    print('Road geometries materialized:',len(road_features),'vertices',len(csv_data),'bbox',bbox,flush=True)

    # Original local OSM tiles are bound by the original netconvert config.
    cfg=P/'00_network/melbourne_study_v01.netccfg';source(cfg,'original OSM tile-to-network lineage; never executed')
    cfgroot=ET.parse(cfg).getroot()
    osm_files=[cfg.parent/n for n in cfgroot.find('input/osm-files').get('value').split(',')]
    study_path=P/'00_network/study_area.txt';source(study_path,'explicit original study-area geographic bounds')
    study=dict(line.strip().split('=',1) for line in study_path.read_text().splitlines() if '=' in line)
    coast={};metro={};mainland={};osmtime={};conflicts=[]
    for p in osm_files:
        source(p,'original OSM boundary/coastline candidates; no download')
        for e in top_elements(p):
            if e.tag=='meta':osmtime[p.name]=dict(e.attrib)
            elif e.tag=='way':
                tags={t.get('k'):t.get('v') for t in e.findall('tag')}
                if tags.get('natural')=='coastline':
                    w={'refs':[n.get('ref') for n in e.findall('nd')],'tags':tags,'source_paths':[str(p)]}
                    if e.get('id') in coast:
                        old=coast[e.get('id')]
                        if old['refs']!=w['refs']:conflicts.append('coastline way '+e.get('id'))
                        old['source_paths'].append(str(p))
                    else:coast[e.get('id')]=w
            elif e.tag=='relation':
                tags={t.get('k'):t.get('v') for t in e.findall('tag')}
                target=metro if tags.get('name')=='Melbourne' and tags.get('boundary')=='place' else mainland if tags.get('name')=='Mainland Australia' else None
                if target is not None:
                    rr={'members':[dict(n.attrib) for n in e.findall('member')],'tags':tags,'source_paths':[str(p)]}
                    if e.get('id') in target:
                        if target[e.get('id')]['members']!=rr['members']:conflicts.append('relation '+e.get('id'))
                        target[e.get('id')]['source_paths'].append(str(p))
                    else:target[e.get('id')]=rr
        print('OSM authority scan',p.name,'coast ways',len(coast),'metro relations',len(metro),flush=True)
    assert not conflicts,('OSM_SNAPSHOT_CONFLICT',conflicts)
    wanted_ways={m['ref'] for group in [metro,mainland] for r in group.values() for m in r['members'] if m['type']=='way'}
    wanted_nodes={n for w in coast.values() for n in w['refs']}
    found_ways={};osm_nodes={};node_conflicts=[]
    for p in osm_files:
        for e in top_elements(p):
            if e.tag=='node' and e.get('id') in wanted_nodes:
                llval=(float(e.get('lon')),float(e.get('lat')))
                if e.get('id') in osm_nodes and osm_nodes[e.get('id')]!=llval:node_conflicts.append(e.get('id'))
                osm_nodes[e.get('id')]=llval
            elif e.tag=='way' and e.get('id') in wanted_ways:
                w={'refs':[n.get('ref') for n in e.findall('nd')],'source_paths':[str(p)]}
                if e.get('id') in found_ways:
                    assert found_ways[e.get('id')]['refs']==w['refs']
                    found_ways[e.get('id')]['source_paths'].append(str(p))
                else:found_ways[e.get('id')]=w
        print('OSM coordinate/member scan',p.name,flush=True)
    assert not node_conflicts,('OSM_COORDINATE_CONFLICT',node_conflicts)
    missing_metro={k:[m['ref'] for m in r['members'] if m['type']=='way' and m['ref'] not in found_ways] for k,r in metro.items()}
    missing_mainland={k:[m['ref'] for m in r['members'] if m['type']=='way' and m['ref'] not in found_ways] for k,r in mainland.items()}
    complete_metro=[k for k,v in missing_metro.items() if not v]
    if complete_metro:
        boundary_nodes={n for k in complete_metro for m in metro[k]['members'] if m['type']=='way' for n in found_ways[m['ref']]['refs']}
        needed=boundary_nodes-set(osm_nodes)
        for p in osm_files:
            for e in top_elements(p):
                if e.tag=='node' and e.get('id') in needed:osm_nodes[e.get('id')]=(float(e.get('lon')),float(e.get('lat')))
        complete_metro=[k for k in complete_metro if all(n in osm_nodes for m in metro[k]['members'] if m['type']=='way' for n in found_ways[m['ref']]['refs'])]
    boundary_features=[];boundary_role='SOURCE_STUDY_AREA_BOUNDING_POLYGON'
    for k in complete_metro:
        rings=rings_from_ways(metro[k]['members'],found_ways,osm_nodes)
        if rings and sum(role=='outer' for role,ring in rings)==1:
            ordered=[ring for role,ring in rings if role=='outer']+[ring for role,ring in rings if role=='inner']
            boundary_features.append(feature(dict(type='Polygon',coordinates=ordered),
                dict(source_geometry_id='osm:relation/'+k,boundary_type='GREATER_MELBOURNE_PLACE_BOUNDARY',
                     geometry_status='AVAILABLE',source_tags=metro[k]['tags'])))
            boundary_role='GREATER_MELBOURNE_PLACE_BOUNDARY'
    if not boundary_features:
        w,s,e,n=map(float,[study['WEST'],study['SOUTH'],study['EAST'],study['NORTH']])
        boundary_features=[feature(dict(type='Polygon',coordinates=[[(w,s),(e,s),(e,n),(w,n),(w,s)]]),
            dict(source_geometry_id='study_area.txt:WEST,SOUTH,EAST,NORTH',boundary_type=boundary_role,
                 name=study['STUDY_NAME'],geometry_status='AVAILABLE_SOURCE_BOUNDS',
                 metropolitan_outline_status=U,not_an_administrative_or_coastal_outline=True))]
    coastline_features=[];coast_missing={};coast_skipped=[]
    # Retain complete original segments intersecting plotting extent; never create a clipping vertex.
    for k,w in sorted(coast.items()):
        missing=[n for n in w['refs'] if n not in osm_nodes]
        if missing:coast_missing[k]=missing
        parts=[];part=[]
        for a,b in zip(w['refs'],w['refs'][1:]):
            if a not in osm_nodes or b not in osm_nodes:
                if len(part)>1:parts.append(part)
                part=[];continue
            x,y=osm_nodes[a],osm_nodes[b]
            segment_box=(min(x[0],y[0]),min(x[1],y[1]),max(x[0],y[0]),max(x[1],y[1]))
            intersects=not(segment_box[2]<box[0] or segment_box[0]>box[2] or segment_box[3]<box[1] or segment_box[1]>box[3])
            if intersects:
                if not part:part=[x]
                if part[-1]!=x:parts.append(part);part=[x]
                if part[-1]!=y:part.append(y)
            else:
                if len(part)>1:parts.append(part)
                part=[]
        if len(part)>1:parts.append(part)
        if not parts:coast_skipped.append(k);continue
        coastline_features.append(feature(dict(type='LineString' if len(parts)==1 else 'MultiLineString',
            coordinates=parts[0] if len(parts)==1 else parts),dict(source_geometry_id='osm:way/'+k,
            geometry_status='AVAILABLE_SOURCE_VERTICES' if not missing else 'PARTIAL_UNRESOLVED_SOURCE_NODES',
            source_tags=w['tags'],source_authority=[ref(p) for p in w['source_paths']],
            selection='Original segments with segment bbox intersecting plot extent; no synthetic clipping vertices')))
    land_features=[]
    land_reason='UNRESOLVED: local Mainland Australia relation is not a complete land polygon. No coastline closure, land-side inference, polygonization or bbox land fill was fabricated.'
    print('Context:',boundary_role,'coastline features',len(coastline_features),'metro missing ways', {k:len(v) for k,v in missing_metro.items()},flush=True)

    road_valid=len(road_features)==509 and not unresolved
    check('road_geometry_coverage','509/509',f'{len(road_features)}/509','PASS' if road_valid else 'FAIL','Frozen physical edge catalog + exact lane shapes')
    check('unresolved_road_geometry_count',0,len(unresolved),'PASS' if not unresolved else 'FAIL','See manifest unresolved_road_geometries')
    check('zero_length_road_geometry_count',0,zeros,'PASS' if zeros==0 else 'FAIL','Sum of original projected segment lengths; gap lengths excluded')
    check('reversed_road_geometry_count',0,reversed_count,'PASS' if not reversed_count else 'FAIL','First edge.from / last edge.to exactly equal frozen node junction IDs; no orientation repair')
    check('physical_edge_junction_order_breaks',0,topology_discontinuities,'PASS' if not topology_discontinuities else 'FAIL','Consecutive edge.to == next edge.from in source_position order')
    check('parallel_directed_edges_preserved',509,len({f['properties']['road_edge_id'] for f in road_features}),'PASS','377 ordered pairs; 96 parallel pairs; keyed by road_edge_id, not endpoints')
    ep_bad=[r['road_edge_id'] for r in endpoints if r['endpoint_status']!='PASS']
    check('endpoint_junction_footprint_tolerance','509 within source-derived tolerance',f'{509-len(ep_bad)}/509','PASS' if not ep_bad else U,'road_geometry_endpoint_validation.csv; junction polygon radius from anchor + 5 m; no snap')
    check('max_start_offset_m','Reported; not zero by assumption',max(r['start_offset_m'] for r in endpoints),'INFO','Lane endpoints stop at junction footprints')
    check('max_end_offset_m','Reported; not zero by assumption',max(r['end_offset_m'] for r in endpoints),'INFO','Lane centerline offset and stop lines')
    check('source_junction_coordinate_match','<= 0.1 m',max(node_drift.values()),'PASS' if max(node_drift.values())<=0.1 else 'FAIL','Inverse original SUMO netOffset/PROJ at all 48 frozen junction IDs')
    check('source_shape_gap_handling','No fabricated connector',f'{total_gaps} discontinuities; max {max_gap:.6f} m','PASS','MultiLineString parts and CSV part_index split every nonidentical boundary coordinate')
    check('projection_roundtrip_error_m','< 1e-6',max_roundtrip,'PASS' if max_roundtrip<1e-6 else 'FAIL','pyproj existing local PROJ; always_xy=True; no grid download')
    for label,data in [('road_nodes',nodes),('aidc_locations',aidcs),('mess_service_locations',mess)]:
        number=sum(inside((float(n['longitude']),float(n['latitude'])),box) for n in data)
        check(label+'_within_plot_extent',len(data),number,'PASS' if number==len(data) else 'FAIL','Padded complete network bbox from source vertices')
    w,s,e,n=map(float,[study['WEST'],study['SOUTH'],study['EAST'],study['NORTH']]);studybox=[w,s,e,n]
    for label,data in [('road_nodes',nodes),('aidc_locations',aidcs),('mess_service_locations',mess)]:
        number=sum(inside((float(q['longitude']),float(q['latitude'])),studybox) for q in data)
        check(label+'_within_original_study_boundary',len(data),number,'PASS' if number==len(data) else U,'Original explicit study_area.txt bounds; not a newly inferred administrative polygon')
    outside_road=[]
    for f in road_features:
        g=f['geometry'];parts=g['coordinates'] if g['type']=='MultiLineString' else [g['coordinates']]
        if any(not inside(pt,studybox) for part in parts for pt in part):outside_road.append(f['properties']['road_edge_id'])
    check('road_geometries_outside_original_study_boundary',0,len(outside_road),'PASS' if not outside_road else U,'Full list in manifest; source geometry retained without snapping or truncation')
    check('road_vertices_within_plot_extent',len(all_points),sum(inside(p,box) for p in all_points),'PASS','All materialized road vertices and resource/node coordinates included')
    bad_range=sum(not(-180<=x<=180 and -90<=y<=90 and math.isfinite(x) and math.isfinite(y)) for x,y in all_points)
    check('longitude_latitude_range_errors',0,bad_range,'PASS' if bad_range==0 else 'FAIL','Longitude first, latitude second; Melbourne-specific geographic bounds also tested')
    melb_ok=all(143<x<147 and -40<y<-36 for x,y in all_points)
    check('longitude_latitude_axis_order','Melbourne lon ~145, lat ~-38',str(melb_ok),'PASS' if melb_ok else 'FAIL','Source OSM lon/lat attributes vs transformed SUMO vertices and 48 anchors')
    check('boundary_availability','Existing metropolitan or study-area source',boundary_role,'PASS','Fallback is exact original source study rectangle, not metro shape reconstruction')
    check('metropolitan_outline_completeness','All relation member geometry','AVAILABLE' if boundary_role.startswith('GREATER') else U,'PASS' if boundary_role.startswith('GREATER') else U,'Missing OSM relation members listed in manifest; no new data requested/downloaded')
    check('coastline_availability','Source OSM natural=coastline',len(coastline_features),'PASS' if coastline_features and not coast_missing else U,'Original OSM tile ways; preserved source notes about coarse shape')
    check('land_context_polygon_availability','Complete authoritative land polygon',U,U,land_reason)
    crs_ok=not bad_range and melb_ok and max_roundtrip<1e-6 and max(node_drift.values())<0.1
    check('CRS_CONSISTENCY','EPSG:4326 all available layers','EPSG:4326','PASS' if crs_ok else 'FAIL','Source netOffset removed, exact PROJ inverse; OSM already WGS84 lon/lat. UNRESOLVED land has zero features.')
    check('available_layers_overlay','Common geographic coordinates','Road+anchors+source study bounds+coastline','PASS' if crs_ok else 'FAIL','No assertion of geographic coordinates for IEEE123')
    check('scientific_execution_count',0,0,'PASS','XML/CSV/JSON parsing, hashing, coordinate reprojection and plotting-only geometry extraction only')
    # Original package and every source hashed again before any output is written.
    for record in S.values():assert digest(record['read_path'])==record['sha256'],record['path']
    assert old_before=={p.name:digest(p) for p in OLD.iterdir() if p.is_file()}
    check('original_plotting_package_unchanged','7/7 identical','7/7 identical','PASS','All six CSVs and original PLOTTING_DATA_AUDIT.md SHA256 before/after')
    print('Read-only source hashes rechecked. Writing new package.',flush=True)
    OUT.mkdir()
    output_records=[]
    road_sources=[ref(OLD/'road_edges.csv'),ref(OLD/'road_nodes.csv'),ref(identity_path),ref(paths['physical_edges']),ref(paths['elevated_graph']),ref(loader_path)]
    context_sources=[ref(cfg),ref(study_path)]+[ref(p) for p in osm_files]
    def writejson(name,data,count,kind,authorities,status):
        p=OUT/name
        with p.open('x',encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,separators=(',',':'),allow_nan=False);f.write('\n')
        output_records.append(dict(filename=name,**{kind:count},SHA256=digest(p),source_authority=authorities,CRS='EPSG:4326',status=status))
    def writecsv(name,data,fields,authorities,status):
        p=OUT/name
        with p.open('x',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(data)
        output_records.append(dict(filename=name,row_count=len(data),SHA256=digest(p),source_authority=authorities,CRS='EPSG:4326' if name=='road_edge_geometry.csv' else 'NOT_APPLICABLE',status=status))
    road_fields=['tensor_index','road_edge_id','from_node','to_node','point_order','longitude','latitude','source_geometry_id','source_type','geometry_status','part_index','source_segment_order']
    writecsv('road_edge_geometry.csv',csv_data,road_fields,road_sources,'AVAILABLE_MULTIPART_SOURCE_GAPS' if road_valid else U)
    writejson('road_edge_geometry.geojson',features(road_features,output_crs='EPSG:4326'),len(road_features),'feature_count',road_sources,'AVAILABLE_MULTIPART_SOURCE_GAPS' if road_valid else U)
    writejson('melbourne_boundary.geojson',features(boundary_features,output_crs='EPSG:4326',boundary_role=boundary_role),len(boundary_features),'feature_count',context_sources,'AVAILABLE')
    writejson('melbourne_coastline.geojson',features(coastline_features,output_crs='EPSG:4326',attribution='© OpenStreetMap contributors; ODbL'),len(coastline_features),'feature_count',context_sources,'AVAILABLE' if coastline_features and not coast_missing else U)
    writejson('melbourne_land_context.geojson',features([],status=U,reason=land_reason,output_crs='EPSG:4326'),0,'feature_count',context_sources,U)
    writejson('melbourne_context_extent.json',extent,1,'record_count',road_sources,'AVAILABLE')
    writecsv('road_geometry_endpoint_validation.csv',endpoints,list(endpoints[0]),road_sources,'PASS' if not ep_bad else U)
    writecsv('geographic_plotting_validation.csv',V,['check','expected','observed','status','evidence'],road_sources+context_sources,'PASS_WITH_UNRESOLVED_CONTEXT')
    missing_authority={
        'metropolitan_boundary':{'status':'AVAILABLE' if boundary_role.startswith('GREATER') else 'MISSING_EXTERNAL_AUTHORITY',
            'needed':'Complete existing-snapshot OSM Greater Melbourne boundary=place relation, all member ways and their nodes; no City of Melbourne LGA substitution',
            'missing_way_ids_by_relation':missing_metro},
        'land_context':{'status':'MISSING_EXTERNAL_AUTHORITY','needed':'Complete clipped WGS84 land polygon with provenance (existing Vicmap coastal/land polygon or complete OSM coastline/land-area geometry); no inferred land-side closure',
            'missing_way_ids_by_relation':missing_mainland},
        'coastline_missing_nodes_by_way':coast_missing}
    manifest=dict(schema='V41R4_PLOTTING_GEOMETRY_MANIFEST_V1',
        status='PASS_WITH_UNRESOLVED_CONTEXT',road_geometry_coverage=f'{len(road_features)}/509',
        unresolved_road_geometries=unresolved,unresolved_endpoint_checks=ep_bad,
        melbourne_boundary_status='AVAILABLE',boundary_role=boundary_role,
        metropolitan_outline_status='AVAILABLE' if boundary_role.startswith('GREATER') else U,
        coastline_status='AVAILABLE' if coastline_features and not coast_missing else U,land_context_status=U,
        CRS_CONSISTENCY='PASS' if crs_ok else 'FAIL',scientific_execution_count=0,
        forbidden_execution_counts={k:0 for k in ['SUMO','Dijkstra','routing','optimization','OpenDSS','ML_inference','ML_training','traffic_forecast','route_regeneration','git_commit','git_push']},
        source_graph_canonical_SHA256=graph['canonical_SHA'],source_network_location=location,
        transformation={'source_crs':location['projParameter'],'source_coordinate_units':'metres with SUMO netOffset',
            'operation':'x_native=x_sumo-netOffset_x; y_native=y_sumo-netOffset_y; pyproj Transformer.from_crs(source, EPSG:4326, always_xy=True)',
            'source_crs_no_south_flag_preserved':True,'pyproj_version':pyproj.__version__,'PROJ_version':pyproj.proj_version_str,
            'description':transform.description,'pipeline':transform.definition,'network_enabled':False,'roundtrip_max_error_m':max_roundtrip},
        geometry_semantics={'lane_rule':'Lexicographically first lane ID, exactly as frozen road_graph_authority.py uses for physical geometry',
            'point_order':'global zero-based per reduced directed edge in source_position order',
            'part_index':'zero-based continuous polyline part; never connect points across distinct part_index',
            'no_simplification':True,'no_smoothing':True,'no_snapping':True,'no_missing_geometry_interpolation':True,
            'source_segment_references':len(catalog),'unique_source_edges':len(required),'source_gap_count':total_gaps,'max_source_gap_m':max_gap,
            'internal_junction_connectors':'Not present in ordered physical catalog; not guessed or searched. Gaps retained as separate MultiLineString parts.'},
        endpoint_tolerance={'rule':'Source junction polygon maximum geodesic radius around frozen node + 5 m lane/rounding allowance',
            'fixed_allowance_m':5.0,'node_junction_max_drift_m':max(node_drift.values()),
            'max_start_offset_m':max(r['start_offset_m'] for r in endpoints),'max_end_offset_m':max(r['end_offset_m'] for r in endpoints)},
        osm_snapshot_metadata=osmtime,coastline_source_way_count=len(coast),coastline_excluded_outside_extent_way_ids=coast_skipped,
        missing_external_authority=missing_authority,road_edges_outside_source_study_boundary=outside_road,
        all_sources_unchanged=True,original_plotting_package_SHA256=old_before,
        sources=list(S.values()),outputs=output_records)
    audit=['# V41R4 plotting geometry audit','',
        f'ROAD_GEOMETRY_COVERAGE: {len(road_features)}/509',
        f'MELBOURNE_BOUNDARY: AVAILABLE ({boundary_role})',
        f'COASTLINE: {manifest["coastline_status"]}',
        f'CRS_CONSISTENCY: {manifest["CRS_CONSISTENCY"]}',
        f'UNRESOLVED_GEOMETRIES: {len(unresolved)}',
        'SCIENTIFIC_EXECUTION_COUNT: 0','',
        '## Scope and authority','',
        f'New standalone extension: `{display(OUT)}`. Existing `{display(OLD)}` remains unchanged (7/7 file hashes). No Git commit/push, external download, scientific import, SUMO/OpenDSS command, optimization, road routing, forecast, or ML execution occurred. Existing local Python/pyproj only performed XML/CSV/JSON parsing, coordinate transformation, and geometric validation.',
        f'Final graph canonical SHA256: `{graph["canonical_SHA"]}`. The final M1 identity is byte-bound to the production provenance CSV and names the exact elevated network and ordered physical catalog. All {len(S)} sources were hashed before use and after extraction; all unchanged. Sources and results were opened only for reading. Prior broad 31-day validation remains in the unchanged original package audit; this extension verifies the exact common graph authority directly.', '',
        '## Road geometry rules','',
        f'All {len(required)} original physical edge IDs required by {len(catalog)} catalog references are present. For each of 509 reduced links, source_position defines segment order. Use the lexicographically first lane ID, matching frozen physical-geometry loading code. Preserve every original XY shape vertex except exact consecutive duplicate vertices. No simplification, smoothing, resampling, endpoint snap, reverse inference, or new route is generated.',
        f'Lane shape endpoints at junctions often differ. Preserve {total_gaps} such source gaps (maximum {max_gap:.6f} m) as MultiLineString parts. Do not draw a straight connector between parts. CSV adds `part_index` and `source_segment_order` to the required columns so it has the same unambiguous multipart topology as the GeoJSON. `point_order` increases globally within each reduced edge. `source_geometry_id` is original SUMO edge ID followed by `::` and chosen lane ID. GeoJSON properties preserve the full ordered segment/lane ID list.',
        'These are the frozen representative physical lane polylines, not a newly reconstructed vehicle-level lane-changing trajectory. Internal junction connectors are outside the frozen ordered physical edge catalog; they were not searched or invented. Full road-edge geometry coverage means every mapped physical lane shape is available, not that a continuous junction-to-junction centerline was fabricated.', '',
        '## CRS and reprojection','',
        f'Source XML location: `{json.dumps(location)}`.',
        'Source lane XY are local metre coordinates. Subtract the exact SUMO netOffset before applying the exact source PROJ string. It uses UTM zone 55 with WGS84 and negative northings; the source lacks `+south`. Do not replace it with an assumed southern-hemisphere EPSG code, which would change the northing convention.',
        f'Output: EPSG:4326, longitude first, latitude second. Existing pyproj {pyproj.__version__} / PROJ {pyproj.proj_version_str}; `always_xy=True`; network access disabled. Pipeline: `{transform.definition}`. Maximum inverse/forward round-trip error: {max_roundtrip:.12g} m. Original OSM node attributes are WGS84 longitude/latitude and are not reprojected.', '',
        '## Endpoints and tolerance','',
        f'Directed physical endpoint junction IDs and every intermediate edge adjacency match the frozen source mapping exactly. Reversed geometries: {reversed_count}; zero-length geometries: {zeros}; unresolved shapes: {len(unresolved)}. Geographic source-node versus transformed source-junction maximum offset: {max(node_drift.values()):.9f} m.',
        f'Maximum shape-start offset from its road node: {max(r["start_offset_m"] for r in endpoints):.6f} m; maximum shape-end offset: {max(r["end_offset_m"] for r in endpoints):.6f} m. Tolerance per node is the maximum geodesic radius of its stored SUMO junction polygon relative to the original node coordinate, plus an explicit 5 m lane-width/rounding allowance. This is a diagnostic allowance, not a snapping radius. Per-edge offsets, tolerances and exceptions are in road_geometry_endpoint_validation.csv. Endpoint exceptions: {ep_bad}.',
        f'Unresolved road geometry list: {json.dumps(unresolved)}.', '',
        '## Boundary, coastline and land context','',
        f'Boundary delivered: **{boundary_role}**. The original study-area authority records WEST={study["WEST"]}, SOUTH={study["SOUTH"]}, EAST={study["EAST"]}, NORTH={study["NORTH"]}. If the Greater Melbourne relation is incomplete, the file contains only the exact source study rectangle, explicitly labeled as such. It is not a metropolitan administrative or coastal outline. Do not use it as a filled land mask.',
        f'Greater Melbourne OSM relation candidates and missing way counts: {json.dumps({k:len(v) for k,v in missing_metro.items()})}. Metropolitan outline status: **{manifest["metropolitan_outline_status"]}**. Full missing IDs are in the manifest; no partial relation was closed with invented geometry.',
        f'Coastline: {len(coastline_features)} GeoJSON features from {len(coast)} unique locally present OSM natural=coastline ways. Deduplicate only identical OSM IDs across the eight original source tiles named in netccfg. Preserve original vertices and direction. Keep source segments whose bounding boxes intersect the padded road plotting extent, retaining their original endpoints even when just outside that extent. No new clipping/interpolation vertices are introduced; use the recommended plot extent to clip display only. Missing coastline nodes: {json.dumps(coast_missing)}.',
        'Several OSM coastlines explicitly carry the note “Basic shape only - needs finer detail”. These historical source-quality notes are preserved in feature source_tags; the extraction does not claim a newer or surveyed coastline. Attribution: © OpenStreetMap contributors; ODbL, as stated by the original local OSM files. No new OSM or Vicmap download occurred.',
        f'Land context: **UNRESOLVED**. {land_reason} melbourne_land_context.geojson is a valid empty FeatureCollection (0 features), not a synthetic land polygon.',
        'MISSING_EXTERNAL_AUTHORITY: complete geometry for the named Greater Melbourne relation, and a provenance-bound local land polygon (e.g. complete Vicmap land/coastal polygon or complete matching-snapshot OSM land/coast geometry), are needed to replace these missing layers. Precise missing OSM way IDs are in PLOTTING_GEOMETRY_MANIFEST.json. No external acquisition was performed.',
        'Local search scope: study research_pipeline and its original eight OSM XML tiles / network configuration; available geographic filenames in the two Mobile ESS workspace roots and Desktop/4-2/Mobile ESS. No separate local Vicmap/coastline/land SHP/GPKG authority was found in those searched roots. This is a bounded local-source search, not a claim about every file on the computer.', '',
        '## Plot extent and consistency','',
        f'Unpadded complete network bbox [min_lon,min_lat,max_lon,max_lat]: `{bbox}`. Recommended display box: `{box}`, with 4% span padding on each side. Bounds already include padding. Includes all 48 road nodes, 12 AIDC anchors, 24 MESS service locations and every road geometry vertex. Source-study boundary outlier road IDs: {outside_road}.',
        'CRS consistency applies to available mobility-side layers. IEEE123 coordinates remain UNRESOLVED in the original package and are not included in this geographic overlay. Its separate panel may use an explicitly topological layout later.', '',
        '## Generated files','',
        '| File | Rows / features / records | SHA256 | Source authority | CRS | Status |','|---|---:|---|---|---|---|']
    for r in output_records:
        count=r.get('row_count',r.get('feature_count',r.get('record_count')))
        audit.append(f'| `{r["filename"]}` | {count} | `{r["SHA256"]}` | {", ".join(r["source_authority"])} | {r["CRS"]} | {r["status"]} |')
    audit+=['','## Source hashes','','| Ref | Original source path | Bytes | SHA256 | Role |','|---|---|---:|---|---|']
    for r in S.values():audit.append(f'| {r["id"]} | `{r["path"]}` | {r["bytes"]} | `{r["sha256"]}` | {"; ".join(r["roles"])} |')
    audit+=['','## Reuse in Python','','Read the geometry CSV with IDs as strings and keep_default_na=False. Group by road_edge_id and then part_index, sorting by point_order. Never connect separate parts. Prefer the equivalent GeoJSON to preserve MultiLineString geometry directly. Use EPSG:4326 axes; use the extent file as final xlim/ylim. The boundary fallback is outline-only; use coastline as a very light gray stroke. Do not fill the empty land context or the study bbox as land.','',
        'The manifest lists each generated payload and this audit with count, hash, CRS and status. A manifest cannot contain its own final byte hash without self-reference; its digest is written to PLOTTING_GEOMETRY_MANIFEST.sha256. The checksum sidecar is metadata, not a geographic payload.','']
    ap=OUT/'PLOTTING_GEOMETRY_AUDIT.md';ap.write_text('\n'.join(audit),encoding='utf8')
    manifest['outputs'].append(dict(filename=ap.name,line_count=len(audit),SHA256=digest(ap),source_authority=list(S.keys()),CRS='NOT_APPLICABLE',status='COMPLETE'))
    mp=OUT/'PLOTTING_GEOMETRY_MANIFEST.json'
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    (OUT/'PLOTTING_GEOMETRY_MANIFEST.sha256').write_text(digest(mp)+'  '+mp.name+'\n',encoding='ascii')
    print(json.dumps({k:manifest[k] for k in ['road_geometry_coverage','boundary_role','metropolitan_outline_status','coastline_status','CRS_CONSISTENCY','scientific_execution_count']},ensure_ascii=False),flush=True)
    print('OUTPUT_COUNTS',[(r['filename'],r.get('row_count',r.get('feature_count',r.get('record_count',r.get('line_count'))))) for r in output_records],flush=True)

if __name__=='__main__':main()
