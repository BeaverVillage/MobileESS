"""Read-only frozen-file projection. Never import or execute research code.

Only CSV/JSON/text parsing, SHA256 and stored NPZ string-axis reads are used.
Writes exactly six CSVs and one audit to a NEW output directory.
"""
from pathlib import Path
import collections
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
FINAL = ROOT / 'v41r4_final_results_pr/docs/v41r4_final'
WSL = Path(r'\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline')
OUT = ROOT / 'V41R4_plotting_data'
REF = ROOT / 'tmp/c12_exact_sources_repo_cleanup/c12_exact_sources/v2038_parent/Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference'
U = 'UNRESOLVED'
sources = {}
notes = []

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def source(path, role, expected=None):
    path = Path(path).resolve()
    key = str(path)
    if key not in sources:
        sources[key] = dict(id=f'S{len(sources)+1:03d}', path=key,
                            sha256=sha(path), bytes=path.stat().st_size, roles=set())
    record = sources[key]
    record['roles'].add(role)
    if expected is not None:
        assert record['sha256'] == expected, ('SOURCE_HASH_MISMATCH', path, expected, record['sha256'])
        record['roles'].add('matches frozen SHA256')
    return path

def js(path, role, expected=None):
    return json.loads(source(path, role, expected).read_text(encoding='utf-8-sig'))

def rows(path, role, expected=None):
    return list(csv.DictReader(io.StringIO(source(path, role, expected).read_text(encoding='utf-8-sig'))))

def sid(path):
    return sources[str(Path(path).resolve())]['id']

def tn(value):
    return f'TN_{int(str(value).removeprefix("TN_")):02d}'

def resolve_frozen(record, role):
    """Only repair the known legacy workspace prefix, requiring byte identity."""
    p = Path(record['path'])
    if not p.is_file():
        assert 'Mobile ESS 2' in record['path'], record['path']
        tail = record['path'].split('Mobile ESS 2', 1)[1].lstrip('\\/')
        p = ROOT / tail
        notes.append(f'Historical path `{record["path"]}` resolved to `{p}` by workspace-prefix repair; SHA256 verified.')
    return source(p, role, record['sha256'])

def commands(path):
    """Lexical DSS reader: comments and continuation lines only; no DSS engine."""
    result = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.split('!', 1)[0].strip()
        if not line:
            continue
        if line.startswith('~'):
            assert result
            result[-1] += ' ' + line[1:].strip()
        else:
            result.append(line)
    return result

def props(command):
    return {k.lower(): v.strip('[]()\"').lower() for k, v in re.findall(
        r'([%\w]+)\s*=\s*(\[[^\]]*\]|\([^)]*\)|"[^"]*"|[^\s]+)', command)}

def parse_topology(master, pcc, ratings, pv):
    elements = {}
    dss_files = []
    def read(path):
        dss_files.append(path)
        for command in commands(path):
            if re.match(r'(?i)redirect\s+', command):
                read(path.parent / command.split(None, 1)[1].strip('"'))
                continue
            match = re.match(r'(?i)new\s+(line|transformer)\.([^\s]+)\s+(.*)', command)
            if match:
                kind, name, body = match.groups()
                kind, name = kind.lower(), name.lower()
                fields = props(body)
                if 'like' in fields:
                    fields = {**elements[kind + '.' + fields['like']]['fields'], **fields}
                if kind == 'line':
                    terminals = [fields['bus1'], fields['bus2']]
                elif 'buses' in fields:
                    terminals = re.split(r'[\s,]+', fields['buses'].strip())
                else:
                    terminals = re.findall(r'(?i)\bbus\s*=\s*([^\s]+)', body)
                    terminals = [b.lower() for b in terminals]
                assert len(terminals) == 2, (name, terminals)
                identifier = kind + '.' + name
                assert identifier not in elements
                elements[identifier] = dict(kind=kind, terminals=terminals, fields=fields, source=path)
            elif re.match(r'(?i)(edit|open|close|disable|enable)\s+(line|transformer)\.', command):
                # Ratings only may edit NormAmps/EmergAmps. Any topology mutation fails closed.
                assert set(props(command)) <= {'normamps', 'emergamps'}, command
            assert not re.search(r'(?i)\b(buscoords|setbusxy)\b', command), 'Coordinate authority requires explicit extraction'
    read(master)
    read(pcc)
    read(ratings)
    read(pv)
    return elements, dss_files

def main():
    assert not OUT.exists(), 'Refuse to overwrite an existing package'
    source(__file__, 'plotting-only extraction source; not scientific runtime')
    authority_path = FINAL / 'evidence/final_reaudit/FINAL_PAPER_DATA_AUTHORITY.json'
    js(authority_path, 'final paper authority selection')
    raw_path = FINAL / 'evidence/final_reaudit/RAW_AUTHORITY_BINDINGS.json'
    raw = {r['member']: r for r in js(raw_path, 'archived final-decision SHA256 bindings')['files']}
    production_path = FINAL / 'evidence/traffic_provenance/TRAFFIC_PRODUCTION_DAY_BINDINGS.csv'
    production = rows(production_path, '62 final B2/B3 production bindings')
    assert len(production) == 62
    source(FINAL / 'evidence/traffic_provenance/TRAFFIC_PROVENANCE_RECOVERY.json', 'final graph canonical hash authority')

    all_services = None
    road_records = None
    node_axis = None
    branch_axis = None
    branch_phase_sets = None
    certificates = []
    route_paths = []
    feeder_by_name = {}
    observed_services = set()
    identity_paths = []
    final_paths = []
    electrical_paths = []
    route_seen = set()
    for count, binding in enumerate(production):
        day, policy = binding['day'], binding['policy']
        original_day = RUN / f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/dayahead'
        matches = [member for member, record in raw.items()
                   if member.endswith('/FROZEN_JOINT_DECISION.json')
                   and record['sha256'] == binding['final_decision_SHA']]
        assert len(matches) == 1, (day, policy, matches)
        rel = matches[0]
        fp = RUN / rel
        decision = js(fp, 'archive-bound final decision: static service/axis binding', raw[rel]['sha256'])['decision']
        assert sha(fp) == binding['final_decision_SHA']
        final_paths.append(fp)
        for row in decision['MESS_trajectory']:
            if row['service_id'] and not row['service_id'].startswith('TRANSIT_'):
                observed_services.add(row['service_id'])
        mr = js(original_day / 'M1/M1_RESULT.json', 'final M1 receipt pointer')
        rec = next(r for r in mr['external_search_files'] if r['path'].endswith('M1_IDENTITY.json'))
        assert rec['sha256'] == binding['M1_receipt_SHA']
        ip = resolve_frozen(rec, 'final M1 identity: graph, routing and service authority')
        identity_paths.append(ip)
        identity = js(ip, 'final M1 identity')['identity']
        d = identity['inputs']
        assert d['road_graph']['canonical_SHA'] == binding['graph_SHA'] == '658fb2e56867a50597e9a21899748d8171439deda852e7db4f3339a99f71dd3d'
        rr = d['road_graph']['files']
        hashes = {k: v['sha256'] for k, v in rr.items()}
        if road_records is None:
            road_records = rr
        else:
            assert hashes == {k: v['sha256'] for k, v in road_records.items()}
        if count == 0:
            mapping_path = resolve_frozen(d['MESS_PCC_mapping'], 'resource_grid_mapping / final MESS host mapping')
        else:
            assert d['MESS_PCC_mapping']['sha256'] == sha(mapping_path)
        rrec = d['route_table']['file']
        assert rrec['sha256'] == binding['route_cache_SHA']
        if rrec['sha256'] not in route_seen:
            rp = resolve_frozen(rrec, 'mess_service_locations / frozen usable service domain')
            route_paths.append(rp)
            route = json.loads(gzip.decompress(rp.read_bytes()))
            service_set = set(route['service_ids'])
            assert len(service_set) == 24
            if all_services is None:
                all_services = service_set
            assert all_services == service_set
            # Examine persisted route records only, never search a graph.
            assert {r['origin_service_id'] for r in route['routes']} == all_services
            assert {r['destination_service_id'] for r in route['routes']} == all_services
            assert all(r['route_graph_sha'] == binding['graph_SHA'] for r in route['routes'])
            route_seen.add(rrec['sha256'])
        if policy == 'B2':
            cp = resolve_frozen(decision['electrical'], 'final decision-bound electrical certificate')
            certificates.append(cp)
            cert = js(cp, 'frozen electrical topology/axis evidence')
            inp = cert['input_identity']['identity']['inputs']
            assert inp['V41R4_FINAL_DATE_BINDING']['alpha_BG'] == 1.15
            if not feeder_by_name:
                for fr in inp['feeder_manifest']['files']:
                    p = resolve_frozen(fr, 'final feeder transitive source manifest')
                    assert p.name.lower() not in feeder_by_name
                    feeder_by_name[p.name.lower()] = p
                master = resolve_frozen(inp['OpenDSS_master'], 'ieee123_topology / selected master')
                pcc = resolve_frozen(inp['PCC_mapping'], 'ieee123_topology / selected v4 PCC overlay')
                assert sha(mapping_path) == inp['service_PCC_mapping']['sha256']
            else:
                for fr in inp['feeder_manifest']['files']:
                    assert sha(feeder_by_name[Path(fr['path']).name.lower()]) == fr['sha256']
            vp = resolve_frozen(cert['outputs']['voltage'], 'stored node/branch/control string axes only')
            electrical_paths.append(vp)
            with np.load(vp, allow_pickle=False) as z:
                nodes = set(map(str, z['node_names']))
                branches = set(map(str, z['branch_names']))
                controls = list(map(str, z['control_names']))
            assert controls[:12] == [f'aidc_load_kw[AIDC{i:02d}]' for i in range(1, 13)]
            assert {c[10:-1] for c in controls if c.startswith('mess_p_kw[')} == all_services
            if node_axis is None:
                node_axis, branch_axis = nodes, branches
            assert (node_axis, branch_axis) == (nodes, branches)
        if count % 16 == 0:
            print(f'Frozen bindings checked: {count+1}/62', flush=True)
    assert len(route_paths) == len(certificates) == 31
    assert observed_services <= all_services

    links_path = resolve_frozen(road_records['link_order'], 'road_edges / production 509-link tensor order')
    service_path = resolve_frozen(road_records['service_nodes'], 'aidc_locations + mess_service_locations / fixed road anchor mapping')
    # Verify all four graph constituents; read no traffic labels or checkpoint weights.
    for record in road_records.values():
        resolve_frozen(record, 'frozen graph constituent hash verification only')
    manifest_path = WSL / '04_frozen_topology/v01_reduced48_topology_manifest_final_v2.json'
    manifest = js(manifest_path, 'road_nodes / frozen 48-node and 509-link source hashes')
    package = WSL / '04_frozen_topology/v01_reduced48_final_v2_package'
    nodes_path = package / 'v01_reduced48_nodes_v2.csv'
    rawlinks_path = package / 'v01_reduced48_directed_links_v2.csv'
    nodes = rows(nodes_path, 'road_nodes / exact frozen longitude latitude and junction ID', manifest['source_file_sha256'][nodes_path.name])
    rawlinks = rows(rawlinks_path, 'cross-check all production link IDs/endpoints/junction anchors', manifest['source_file_sha256'][rawlinks_path.name])
    links = rows(links_path, 'road_edges')
    services = rows(service_path, 'final service-to-road mapping')
    mapping = {r['service_node_id']: r for r in rows(mapping_path, 'final service-to-host mapping')}
    node_by_id = {n['transport_node_id']: n for n in nodes}
    assert len(nodes) == len(node_by_id) == 48
    assert len(links) == len(rawlinks) == 509
    assert {r['service_id'] for r in services} == all_services == set(mapping)
    raw_by_id = {r['reduced_link_id']: r for r in rawlinks}
    assert len(raw_by_id) == 509
    for i, link in enumerate(links):
        assert int(link['tensor_index']) == i
        original = raw_by_id[link['reduced_link_id']]
        for end in ['from', 'to']:
            node = tn(link[end + '_node'])
            assert node == original[end + '_transport_node_id']
            assert node_by_id[node]['junction_id'] == original[end + '_junction_id']
    pairs = collections.Counter((r['from_node'], r['to_node']) for r in links)
    assert len(pairs) == 377 and sum(n > 1 for n in pairs.values()) == 96 and max(pairs.values()) == 5

    # CRS metadata only: parse the XML location header; no SUMO API or execution.
    original_net = WSL / '00_network/melbourne_study_v01.net.xml.gz'
    source(original_net, 'geographic CRS metadata only: XML location header')
    with gzip.open(original_net, 'rb') as stream:
        for event, element in ET.iterparse(stream, events=['start']):
            if element.tag == 'location':
                location = dict(element.attrib)
                break
        else:
            location = {'projParameter': U}
    spatial_source = WSL / '03_reduced_graph/export_v01_spatial_inventory.py'
    source(spatial_source, 'read-only coordinate-generation lineage: convertXY2LonLat; never imported')

    ratings = feeder_by_name['generated_planning_line_ratings_u080.dss']
    pv = feeder_by_name['generated_phasepv.dss']
    elements, dss_files = parse_topology(master, pcc, ratings, pv)
    for path in dss_files:
        assert str(path.resolve()) in sources, ('Unbound DSS dependency', path)
    expected_names = {n.split('::')[0] for n in branch_axis}
    assert set(elements) == expected_names, ('DSS / frozen branch mismatch', set(elements) ^ expected_names)
    topology = []
    derived_nodes = set()
    for name, element in elements.items():
        phase_names = {n.split('::')[1] for n in branch_axis if n.split('::')[0] == name}
        terminals = element['terminals']
        normalized = []
        for terminal in terminals:
            fields = terminal.split('.')
            bus = fields[0]
            phases = fields[1:] if len(fields) > 1 else [str('ABC'.index(p)+1) for p in sorted(phase_names)]
            phases = [p for p in phases if p != '0']
            derived_nodes.update(bus + '.' + p for p in phases)
            normalized.append((bus, '.'.join(phases)))
        assert {str('ABC'.index(p)+1) for p in phase_names} == set(normalized[0][1].split('.'))
        topology.append(dict(element_id=name, element_type=element['kind'],
            from_bus=normalized[0][0], to_bus=normalized[1][0],
            from_nodes=normalized[0][1], to_nodes=normalized[1][1],
            from_x=U, from_y=U, to_x=U, to_y=U))
    assert derived_nodes == node_axis, ('DSS / frozen node mismatch', derived_nodes ^ node_axis)
    buses = {n.split('.')[0] for n in node_axis}
    topology.sort(key=lambda r: r['element_id'])

    road_nodes = [dict(road_node_id=n['transport_node_id'], junction_id=n['junction_id'],
                       longitude=n['longitude'], latitude=n['latitude']) for n in nodes]
    road_edges = [dict(tensor_index=r['tensor_index'], road_edge_id=r['reduced_link_id'],
                      from_node=tn(r['from_node']), to_node=tn(r['to_node'])) for r in links]
    aidcs, mess, resources = [], [], []
    for service in services:
        s = service['service_id']
        n = node_by_id[service['traffic_node']]
        host = mapping[s]['electrical_host_bus'].lower()
        tx = 'transformer.mess_' + s.lower() + '_tx'
        pcc_bus = elements[tx]['terminals'][1].split('.')[0]
        assert elements[tx]['terminals'][0].split('.')[0] == host
        assert pcc_bus in buses
        loc = dict(service_id=s, road_node_id=n['transport_node_id'], longitude=n['longitude'], latitude=n['latitude'],
                   pcc_bus=pcc_bus, host_bus=host)
        mess.append(loc)
        resources.append(dict(resource_type='MESS_SERVICE', resource_id=s, service_id=s, road_node_id=n['transport_node_id'],
                              pcc_bus=pcc_bus, host_bus=host, transformer_id=tx))
        if service['service_type'] == 'IDC':
            number = int(s.removeprefix('IDC'))
            assert n['model_idc_id'] == f'IDC_{number:02d}'
            a = f'AIDC{number:02d}'
            tx = 'transformer.idc_' + s.lower() + '_tx'
            pcc_bus = elements[tx]['terminals'][1].split('.')[0]
            assert elements[tx]['terminals'][0].split('.')[0] == host
            aidcs.append(dict(aidc_id=a, **{**loc, 'pcc_bus': pcc_bus}))
            resources.append(dict(resource_type='AIDC', resource_id=a, service_id=s, road_node_id=n['transport_node_id'],
                                  pcc_bus=pcc_bus, host_bus=host, transformer_id=tx))
    assert len(aidcs) == 12 and len(mess) == 24 and len(resources) == 36
    mapping_code = RUN / 'dayahead/v28r2/opendss_mapping.py'
    source(mapping_code, 'AIDC ordinal-to-load and MESS service-to-injection source, read only')
    source(RUN / 'dayahead/v39d/evaluate.py', 'stored PCC array sort by slot,AIDC; read only')
    source(RUN / 'dayahead/full_ieee123_g11_v16_1.py', 'compile-chain interpretation source, read only')

    # All output data is ready in memory. Rehash every source before writing.
    print(f'Rechecking {len(sources)} read-only source hashes', flush=True)
    for record in sources.values():
        assert sha(record['path']) == record['sha256'], ('SOURCE_CHANGED', record['path'])
    OUT.mkdir()
    tables = {'road_nodes.csv': road_nodes, 'road_edges.csv': road_edges, 'aidc_locations.csv': aidcs,
              'mess_service_locations.csv': mess, 'ieee123_topology.csv': topology, 'resource_grid_mapping.csv': resources}
    for name, data in tables.items():
        with (OUT / name).open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(data)
        with (OUT / name).open(encoding='utf-8', newline='') as f:
            actual = list(csv.DictReader(f))
        assert actual == [{k: str(v) for k, v in r.items()} for r in data]

    source_refs = {
        'road_nodes.csv': [nodes_path, manifest_path, rawlinks_path, links_path],
        'road_edges.csv': [links_path, rawlinks_path, manifest_path],
        'aidc_locations.csv': [nodes_path, service_path, mapping_path, pcc, mapping_code, electrical_paths[0]],
        'mess_service_locations.csv': [nodes_path, service_path, mapping_path, pcc, *route_paths],
        'ieee123_topology.csv': list(dict.fromkeys([*dss_files, *certificates, *electrical_paths])),
        'resource_grid_mapping.csv': [service_path, mapping_path, pcc, mapping_code, electrical_paths[0]],
    }
    rules = {
        'road_nodes.csv': 'Exactly 48 frozen transport nodes, retaining source longitude/latitude strings and junction IDs. No re-snapping, clustering, geocoding, or coordinate averaging.',
        'road_edges.csv': 'Exactly 509 production tensor-order directed links. Normalize integer node labels to TN_XX using the source loader convention. Verify every ID and endpoint against the manifest-hashed frozen reduced graph, including junction IDs. Preserve all parallel and opposite-direction links; no pair deduplication and no route search.',
        'aidc_locations.csv': 'Join the 12 IDC service IDs to their actual final road anchors. AIDC01..12 follows the frozen control-array order and the source ordinal IDC_IDC01..12 load mapping. Export each AIDC dedicated low-voltage PCC bus and its actual host bus from selected v4 DSS transformer terminals. Coordinates describe access anchors, not building centroids.',
        'mess_service_locations.csv': 'Use exactly the service_ids domain in all 31 final production routing caches (62 B2/B3 bindings), intersected and verified equal to the final road-service and electrical mappings. Include IDC01..12 and STA01..12. Export MESS dedicated PCC buses, which differ from AIDC PCCs at a shared location. These are available service locations, not individual vehicles or only visited locations. No TRANSIT location is exported.',
        'ieee123_topology.csv': 'Static parse of the actual frozen master, its Redirect dependencies, and selected v4 PCC overlay; line-rating/PV redirects are also checked. Preserve one row per two-terminal Line/Transformer, including separate regulator phases. Expand DSS continuation and explicit LIKE inheritance only. Preserve bus suffixes and phase-terminal connectivity; strip node suffixes only into the separate from_nodes/to_nodes columns. Compare exact element set, branch-phase set and bus-phase set with all 31 stored V41R4 electrical artifacts. No OpenDSS import, Compile, Solve, CalcVoltageBases or API invocation. Source command text is data only.',
        'resource_grid_mapping.csv': 'One row for each of 12 AIDC connections and 24 MESS service connections. Join resource/service/road IDs with the actual dedicated PCC transformer and feeder host. MESS_SERVICE rows are connection points, not extra MESS vehicles. No electrical/geographic alignment or host selection is computed.',
    }
    lines = ['# V41R4 plotting-only data audit', '',
        'Status: **PASS — frozen topology and mapping projection; grid coordinates UNRESOLVED**.', '',
        'Generated from existing local frozen artifacts and source bytes only. Scientific model execution, optimization, routing/route search, SUMO, OpenDSS simulation/compilation, ML inference and training: **0**. No research module was imported. NumPy was used only to read existing NPZ string axes with `allow_pickle=False`.', '',
        f'Authority: `{authority_path}` ({sid(authority_path)}). Archive member bindings: {sid(raw_path)}. Production bindings: {sid(production_path)}. The compressed raw archive was not reread or rehashed in this task; archived-member hashes recorded by the final authority were checked against the existing frozen workspace files. Every source in the manifest below was SHA256-hashed before use and rehashed after extraction; all unchanged. Sources were never written.', '',
        '## Static validation', '',
        '- 62 final B2/B3 decisions match archived final member hashes and production provenance; 62 external M1 identity receipts match their frozen SHA256.',
        '- All 31 route-cache service domains are identical (24 sites); graph constituent hashes are identical across all 62 policy-day identities.',
        '- Road: 48 nodes, 509 distinct directed links, 377 distinct ordered pairs, 96 pairs with parallel links, maximum 5 parallel links per pair.',
        f'- Electrical: {len(topology)} distinct two-terminal elements; {len(buses)} bus IDs; {len(node_axis)} bus-phase IDs; {len(branch_axis)} branch-phase IDs. Exact DSS-vs-frozen string-axis equality, consistent across all 31 daily electrical artifacts.',
        f'- Resources: 12 AIDCs; 24 available MESS service points; 36 dedicated resource/PCC connections. Final trajectories visit {len(observed_services)} distinct service points, which is a subset of the available domain.',
        '- All CSV rows round-trip exactly as UTF-8 strings. ID uniqueness, endpoint references, service membership and PCC/host joins validated.', '',
        '## Coordinate systems and UNRESOLVED items', '',
        '- Road/AIDC/MESS: original longitude, latitude in decimal degrees (X=longitude, Y=latitude). Coordinate source code uses `convertXY2LonLat`; it was inspected only. No coordinate transformation was executed.',
        f'- Source SUMO network XML location metadata: `{json.dumps(location, ensure_ascii=False)}`. The node CSV itself does not declare an EPSG code; explicit EPSG identifier is **UNRESOLVED**. Preserve its published geographic coordinate values.',
        '- IEEE123: all from_x/from_y/to_x/to_y values are **UNRESOLVED**. The consumed frozen DSS dependency chain provides electrical bus connections but no Buscoords/SetBusXY coordinate authority. No standard IEEE123 coordinate file, invented layout, copied host coordinate or Melbourne overlay was substituted. Coordinate units, CRS and physical feeder geolocation are **UNRESOLVED**.',
        '- The road CSV is a reduced directed multigraph for a node-link figure. Physical lane polylines are intentionally outside this minimal package; drawing straight segments or display curves does not claim actual street geometry.',
        '- Grid and road are separate domains linked by resource mappings; bus number proximity does not imply spatial proximity. An IEEE123 schematic layout may later be chosen as an explicitly illustrative plotting step, but it is not frozen coordinate data.',
        '- `300_open` and `94_open` are literal distinct modeled buses. Keep the encoded branches (including sw7/sw8); do not connect them to bus 300/94 or infer an open terminal from their names. Native source switch comments describe open-point modeling, while the frozen branch axes include these stubs.',
        '- Native feeder, regulators, and 36 resource PCC transformers are retained; the final augmented model is not forced to have exactly 123 bus IDs. Source slack bus is `150`. Shunt loads, capacitors and PV do not add bus-to-bus edges and are excluded from this topology figure data.', '',
        '## Output CSVs', '', '| CSV | Rows (excluding header) | SHA256 |', '|---|---:|---|']
    for name, data in tables.items():
        lines.append(f'| `{name}` | {len(data)} | `{sha(OUT/name)}` |')
    for name, data in tables.items():
        lines += ['', f'### {name}', '', f'Columns: `{", ".join(data[0])}`.', '', rules[name], '',
                  'Source references (full paths, SHA256 and sizes below): ' + ', '.join(sid(p) for p in source_refs[name]) + '.', '',
                  ('Coordinates: UNRESOLVED, CRS/units UNRESOLVED.' if name == 'ieee123_topology.csv' else
                   'Coordinates: none; IDs join to the coordinate-bearing files.' if name in ['road_edges.csv', 'resource_grid_mapping.csv'] else
                   'Coordinates: source geographic longitude/latitude, decimal degrees; no resampling.')]
    lines += ['', '## Python plotting contract', '',
        'Read CSV IDs as strings (`pandas.read_csv(path, dtype=str, keep_default_na=False)`). Convert only longitude/latitude to float. Use a directed multigraph and `road_edge_id` as the edge key so 509 links are retained. Grid edges join `from_bus` to `to_bus`; preserve `element_id` as edge key to retain single-phase regulator branches. `from_nodes`/`to_nodes` are dot-separated terminal phase numbers, not extra bus IDs. Do not coerce UNRESOLVED coordinates to zero. For resource connectors, join `road_node_id` to road nodes and `pcc_bus`/`host_bus` to grid buses; use `transformer_id` to locate the exact PCC edge.', '',
        '## Source manifest', '',
        'All SHA256 values below were freshly verified in this task. Roles distinguish direct CSV data from validation/lineage evidence. NPZ numerical arrays were not regenerated or evaluated.', '',
        '| Ref | Absolute source path | Bytes | SHA256 | Role |', '|---|---|---:|---|---|']
    for record in sources.values():
        lines.append(f'| {record["id"]} | `{record["path"]}` | {record["bytes"]} | `{record["sha256"]}` | {"; ".join(sorted(record["roles"]))} |')
    lines += ['', '## Historical path resolution', '', *sorted(set(notes)), '',
              '## Reproduction', '', f'Extractor: `{Path(__file__).resolve()}` ({sid(__file__)}). It refuses to overwrite an existing output directory. Its only writes are the six CSVs and this audit in the new package directory. It never invokes any scientific entry point.', '']
    (OUT / 'PLOTTING_DATA_AUDIT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(output=str(OUT), rows={k:len(v) for k,v in tables.items()},
        grid_buses=len(buses), bus_phases=len(node_axis), branch_phases=len(branch_axis),
        source_hashes_unchanged=len(sources), source_network_location=location), ensure_ascii=True), flush=True)

if __name__ == '__main__':
    main()
