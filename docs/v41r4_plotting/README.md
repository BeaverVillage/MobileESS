# V41R4 frozen plotting data and geographic geometry

The paper's mobility/distribution figure needs the actual frozen network IDs,
PCC connections and physical road shapes. This snapshot records the completed
read-only projections of the V41R4 final authority in PR #42. It preserves the
48-node/509-directed-link multigraph, 12 AIDC anchors, 24 available MESS service
locations, and the actual augmented IEEE123 topology: 170 elements and 168 buses.
The electrical panel has no authoritative geographic coordinates; they remain
`UNRESOLVED` and are not overlaid on Melbourne.

The geographic extension covers **509/509** reduced directed links, with
**219,430** vertices. It preserves original physical segment order and the
lexicographically first lane shape used by the frozen geometry loader. Parallel
edges remain independent. Junction gaps are separate MultiLineString parts,
also represented by `part_index` in the CSV; connecting those parts with straight
lines would invent geometry. Zero-length, reversed and unresolved road geometry
counts are zero. All 509 endpoint comparisons pass the documented source-junction
footprint tolerance; endpoints were not snapped to node coordinates.

## Context limitations

- `melbourne_boundary.geojson` contains the **original study-area bounding
  rectangle**, not the Greater Melbourne metropolitan outline. OSM relation
  4246124 lacks 138 member ways in the local tiles; its complete outline remains
  `UNRESOLVED` / `MISSING_EXTERNAL_AUTHORITY`.
- Coastline has 17 features from the original local OSM tiles, preserving their
  historical quality notes. Attribution: © OpenStreetMap contributors; ODbL.
  No new external geographic data was downloaded.
- Land context is an explicitly empty FeatureCollection, with `UNRESOLVED`
  status. The study rectangle must not be filled as a land mask.
- All available geographic layers use EPSG:4326, longitude first. Reprojection
  subtracts the exact SUMO netOffset and uses the original PROJ string. Its
  negative northing convention must not be replaced with an assumed `+south`.

## Included evidence and local payloads

[SOURCE_SNAPSHOT.json](SOURCE_SNAPSHOT.json) lists all 20 original inputs to this
review snapshot with exact size, SHA256, count where applicable, current local
path and repository path. Eighteen files are copied byte-for-byte: two extraction
scripts and the small data/audit files from both delivered packages. The two
large road geometry payloads remain local (34,778,860-byte CSV and
10,488,883-byte GeoJSON); neither is uploaded to Git, LFS or release assets.

Current package locations are `D:\ChatGPT\Mobile ESS 2\V41R4_plotting_data` and
`D:\ChatGPT\Mobile ESS 2\V41R4_plotting_geometry`. Historical audits retain their
original C-drive/WSL paths verbatim; these are provenance, not rewritten paths.
The D-drive copies still match their recorded hashes. Original scientific files,
both delivered packages and their audits are unchanged.

Start with [the plotting audit](evidence/V41R4_plotting_data/PLOTTING_DATA_AUDIT.md),
[the geometry audit](evidence/V41R4_plotting_geometry/PLOTTING_GEOMETRY_AUDIT.md)
and [the geometry manifest](evidence/V41R4_plotting_geometry/PLOTTING_GEOMETRY_MANIFEST.json).
The manifest's `outputs` entries bind the locally delivered payloads; missing
large files in this review snapshot are intentional and explicitly indexed.

The scripts in `tools/v41r4_plotting/snapshots/` are archived extraction source,
not portable clean-clone launchers. Their hard-coded original environment and
output-directory assumptions are retained to preserve the audited bytes.
**Do not run them to review this PR.** No extraction or scientific execution is
needed for review. The verifier below uses only the Python standard library;
it never imports or executes these scripts.

## Verification

From the repository root:

```powershell
python tools/v41r4_plotting/verify_snapshot.py
python tools/v41r4_plotting/verify_snapshot.py --local-root "D:/ChatGPT/Mobile ESS 2"
```

The first command verifies all included hashes, source syntax, small payload
counts, ID joins, resource transformers, UNRESOLVED coordinates, geographic
context metadata and original manifest checksum. The optional local check also
verifies all 20 originals, the large geometry hashes, all 509 CSV/GeoJSON
multipart geometries and point order, and complete network extent coverage.
It performs no route search or geometry generation. See
[PR_VALIDATION.json](PR_VALIDATION.json) for the actual PR-preparation results.

Scientific model, optimization, routing, SUMO, OpenDSS, forecast, and ML
inference/training executions in extraction and PR preparation: **0**.
