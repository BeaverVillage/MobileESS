"""Read-only snapshot/optional local geometry verification; stdlib only."""
import argparse
import ast
import collections
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / 'docs/v41r4_plotting'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Snapshot path escapes root: ' + relative)
    return path


def verify_record(path, entry):
    assert path.stat().st_size == entry['bytes'], path
    assert sha(path) == entry['sha256'], path
    if 'row_count' in entry:
        assert len(rows(path)) == entry['row_count'], path
    if 'feature_count' in entry:
        assert len(read(path)['features']) == entry['feature_count'], path


def verify_small():
    base = DOC / 'evidence/V41R4_plotting_data'
    geometry = DOC / 'evidence/V41R4_plotting_geometry'
    nodes = {r['road_node_id']: r for r in rows(base / 'road_nodes.csv')}
    edges = rows(base / 'road_edges.csv')
    assert len(nodes) == 48 and len(edges) == 509
    assert len({r['road_edge_id'] for r in edges}) == 509
    assert [int(r['tensor_index']) for r in edges] == list(range(509))
    pairs = collections.Counter((r['from_node'], r['to_node']) for r in edges)
    assert (len(pairs), sum(n > 1 for n in pairs.values()), max(pairs.values())) == (377, 96, 5)
    assert all(r['from_node'] in nodes and r['to_node'] in nodes for r in edges)
    topology = {r['element_id']: r for r in rows(base / 'ieee123_topology.csv')}
    assert len(topology) == 170
    assert len({r[k] for r in topology.values() for k in ('from_bus', 'to_bus')}) == 168
    assert all(r[k] == 'UNRESOLVED' for r in topology.values()
               for k in ('from_x', 'from_y', 'to_x', 'to_y'))
    resources = rows(base / 'resource_grid_mapping.csv')
    assert len(resources) == 36
    for r in resources:
        edge = topology[r['transformer_id']]
        assert (r['host_bus'], r['pcc_bus']) == (edge['from_bus'], edge['to_bus'])
        assert r['road_node_id'] in nodes
    for name, count in [('aidc_locations.csv', 12), ('mess_service_locations.csv', 24)]:
        data = rows(base / name)
        assert len(data) == count
        for r in data:
            n = nodes[r['road_node_id']]
            assert (r['longitude'], r['latitude']) == (n['longitude'], n['latitude'])
    manifest_path = geometry / 'PLOTTING_GEOMETRY_MANIFEST.json'
    manifest = read(manifest_path)
    assert (geometry / 'PLOTTING_GEOMETRY_MANIFEST.sha256').read_text().split()[0] == sha(manifest_path)
    assert manifest['road_geometry_coverage'] == '509/509'
    assert manifest['scientific_execution_count'] == 0
    assert manifest['CRS_CONSISTENCY'] == 'PASS'
    assert not manifest['unresolved_road_geometries'] and not manifest['unresolved_endpoint_checks']
    assert manifest['boundary_role'] == 'SOURCE_STUDY_AREA_BOUNDING_POLYGON'
    assert manifest['metropolitan_outline_status'] == 'UNRESOLVED'
    assert read(geometry / 'melbourne_land_context.geojson')['features'] == []
    assert len(read(geometry / 'melbourne_coastline.geojson')['features']) == 17
    assert all(r['status'] != 'FAIL' for r in rows(geometry / 'geographic_plotting_validation.csv'))
    for r in manifest['outputs']:
        if r['filename'] not in ('road_edge_geometry.csv', 'road_edge_geometry.geojson'):
            assert sha(contained(geometry, r['filename'])) == r['SHA256']


def verify_geometry(local_root):
    package = local_root / 'V41R4_plotting_geometry'
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    order = collections.Counter()
    with (package / 'road_edge_geometry.csv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = row['road_edge_id']
            assert int(row['point_order']) == order[key]
            order[key] += 1
            grouped[key][int(row['part_index'])].append([float(row['longitude']), float(row['latitude'])])
    assert len(grouped) == 509 and sum(order.values()) == 219430
    extent = read(package / 'melbourne_context_extent.json')
    for feature in read(package / 'road_edge_geometry.geojson')['features']:
        key = feature['properties']['road_edge_id']
        geom = feature['geometry']
        parts = geom['coordinates'] if geom['type'] == 'MultiLineString' else [geom['coordinates']]
        assert sorted(grouped[key]) == list(range(len(parts)))
        assert [grouped[key][i] for i in range(len(parts))] == parts
        for part in parts:
            assert len(part) >= 2
            for lon, lat in part:
                assert extent['min_lon'] <= lon <= extent['max_lon']
                assert extent['min_lat'] <= lat <= extent['max_lat']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-root', type=Path)
    args = parser.parse_args()
    index = read(DOC / 'SOURCE_SNAPSHOT.json')
    included = local = parsed = 0
    for entry in index['files']:
        if entry['included_in_git']:
            path = contained(ROOT, entry['repository_path'])
            verify_record(path, entry)
            included += 1
            if path.suffix == '.py':
                ast.parse(path.read_text(encoding='utf-8'))
                parsed += 1
        if args.local_root:
            verify_record(contained(args.local_root, entry['local_relative_path']), entry)
            local += 1
    assert included == 18 and parsed == 2
    verify_small()
    if args.local_root:
        assert local == 20
        verify_geometry(args.local_root)
    print(json.dumps(dict(status='PASS', included_hashes_verified=included,
        extraction_sources_parsed_not_executed=parsed, local_hashes_verified=local,
        full_geometry_readback='PASS' if args.local_root else 'NOT_REQUESTED',
        scientific_execution_count=0)))


if __name__ == '__main__':
    main()
