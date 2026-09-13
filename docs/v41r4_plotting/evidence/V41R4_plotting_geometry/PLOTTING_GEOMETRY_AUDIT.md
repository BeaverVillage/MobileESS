# V41R4 plotting geometry audit

ROAD_GEOMETRY_COVERAGE: 509/509
MELBOURNE_BOUNDARY: AVAILABLE (SOURCE_STUDY_AREA_BOUNDING_POLYGON)
COASTLINE: AVAILABLE
CRS_CONSISTENCY: PASS
UNRESOLVED_GEOMETRIES: 0
SCIENTIFIC_EXECUTION_COUNT: 0

## Scope and authority

New standalone extension: `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_geometry`. Existing `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data` remains unchanged (7/7 file hashes). No Git commit/push, external download, scientific import, SUMO/OpenDSS command, optimization, road routing, forecast, or ML execution occurred. Existing local Python/pyproj only performed XML/CSV/JSON parsing, coordinate transformation, and geometric validation.
Final graph canonical SHA256: `658fb2e56867a50597e9a21899748d8171439deda852e7db4f3339a99f71dd3d`. The final M1 identity is byte-bound to the production provenance CSV and names the exact elevated network and ordered physical catalog. All 25 sources were hashed before use and after extraction; all unchanged. Sources and results were opened only for reading. Prior broad 31-day validation remains in the unchanged original package audit; this extension verifies the exact common graph authority directly.

## Road geometry rules

All 15463 original physical edge IDs required by 50585 catalog references are present. For each of 509 reduced links, source_position defines segment order. Use the lexicographically first lane ID, matching frozen physical-geometry loading code. Preserve every original XY shape vertex except exact consecutive duplicate vertices. No simplification, smoothing, resampling, endpoint snap, reverse inference, or new route is generated.
Lane shape endpoints at junctions often differ. Preserve 49741 such source gaps (maximum 110.221375 m) as MultiLineString parts. Do not draw a straight connector between parts. CSV adds `part_index` and `source_segment_order` to the required columns so it has the same unambiguous multipart topology as the GeoJSON. `point_order` increases globally within each reduced edge. `source_geometry_id` is original SUMO edge ID followed by `::` and chosen lane ID. GeoJSON properties preserve the full ordered segment/lane ID list.
These are the frozen representative physical lane polylines, not a newly reconstructed vehicle-level lane-changing trajectory. Internal junction connectors are outside the frozen ordered physical edge catalog; they were not searched or invented. Full road-edge geometry coverage means every mapped physical lane shape is available, not that a continuous junction-to-junction centerline was fabricated.

## CRS and reprojection

Source XML location: `{"netOffset": "-286139.38,4207361.09", "convBoundary": "15686.17,3512.61,57760.42,34617.44", "origBoundary": "143.932665,-38.143077,145.248280,-37.494643", "projParameter": "+proj=utm +zone=55 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"}`.
Source lane XY are local metre coordinates. Subtract the exact SUMO netOffset before applying the exact source PROJ string. It uses UTM zone 55 with WGS84 and negative northings; the source lacks `+south`. Do not replace it with an assumed southern-hemisphere EPSG code, which would change the northing convention.
Output: EPSG:4326, longitude first, latitude second. Existing pyproj 3.6.1 / PROJ 9.4.0; `always_xy=True`; network access disabled. Pipeline: `proj=pipeline step inv proj=utm zone=55 ellps=WGS84 step proj=unitconvert xy_in=rad xy_out=deg`. Maximum inverse/forward round-trip error: 3.97558350671e-09 m. Original OSM node attributes are WGS84 longitude/latitude and are not reprojected.

## Endpoints and tolerance

Directed physical endpoint junction IDs and every intermediate edge adjacency match the frozen source mapping exactly. Reversed geometries: 0; zero-length geometries: 0; unresolved shapes: 0. Geographic source-node versus transformed source-junction maximum offset: 0.000000000 m.
Maximum shape-start offset from its road node: 48.607663 m; maximum shape-end offset: 47.211140 m. Tolerance per node is the maximum geodesic radius of its stored SUMO junction polygon relative to the original node coordinate, plus an explicit 5 m lane-width/rounding allowance. This is a diagnostic allowance, not a snapping radius. Per-edge offsets, tolerances and exceptions are in road_geometry_endpoint_validation.csv. Endpoint exceptions: [].
Unresolved road geometry list: [].

## Boundary, coastline and land context

Boundary delivered: **SOURCE_STUDY_AREA_BOUNDING_POLYGON**. The original study-area authority records WEST=144.65, SOUTH=-37.99, EAST=145.22, NORTH=-37.66. If the Greater Melbourne relation is incomplete, the file contains only the exact source study rectangle, explicitly labeled as such. It is not a metropolitan administrative or coastal outline. Do not use it as a filled land mask.
Greater Melbourne OSM relation candidates and missing way counts: {"4246124": 138}. Metropolitan outline status: **UNRESOLVED**. Full missing IDs are in the manifest; no partial relation was closed with invented geometry.
Coastline: 17 GeoJSON features from 18 unique locally present OSM natural=coastline ways. Deduplicate only identical OSM IDs across the eight original source tiles named in netccfg. Preserve original vertices and direction. Keep source segments whose bounding boxes intersect the padded road plotting extent, retaining their original endpoints even when just outside that extent. No new clipping/interpolation vertices are introduced; use the recommended plot extent to clip display only. Missing coastline nodes: {}.
Several OSM coastlines explicitly carry the note “Basic shape only - needs finer detail”. These historical source-quality notes are preserved in feature source_tags; the extraction does not claim a newer or surveyed coastline. Attribution: © OpenStreetMap contributors; ODbL, as stated by the original local OSM files. No new OSM or Vicmap download occurred.
Land context: **UNRESOLVED**. UNRESOLVED: local Mainland Australia relation is not a complete land polygon. No coastline closure, land-side inference, polygonization or bbox land fill was fabricated. melbourne_land_context.geojson is a valid empty FeatureCollection (0 features), not a synthetic land polygon.
MISSING_EXTERNAL_AUTHORITY: complete geometry for the named Greater Melbourne relation, and a provenance-bound local land polygon (e.g. complete Vicmap land/coastal polygon or complete matching-snapshot OSM land/coast geometry), are needed to replace these missing layers. Precise missing OSM way IDs are in PLOTTING_GEOMETRY_MANIFEST.json. No external acquisition was performed.
Local search scope: study research_pipeline and its original eight OSM XML tiles / network configuration; available geographic filenames in the two Mobile ESS workspace roots and Desktop/4-2/Mobile ESS. No separate local Vicmap/coastline/land SHP/GPKG authority was found in those searched roots. This is a bounded local-source search, not a claim about every file on the computer.

## Plot extent and consistency

Unpadded complete network bbox [min_lon,min_lat,max_lon,max_lat]: `[144.75252244987706, -37.968034140181786, 145.2179372516211, -37.68573640566619]`. Recommended display box: `[144.73390585780731, -37.97932604956241, 145.23655384369084, -37.67444449628557]`, with 4% span padding on each side. Bounds already include padding. Includes all 48 road nodes, 12 AIDC anchors, 24 MESS service locations and every road geometry vertex. Source-study boundary outlier road IDs: [].
CRS consistency applies to available mobility-side layers. IEEE123 coordinates remain UNRESOLVED in the original package and are not included in this geographic overlay. Its separate panel may use an explicitly topological layout later.

## Generated files

| File | Rows / features / records | SHA256 | Source authority | CRS | Status |
|---|---:|---|---|---|---|
| `road_edge_geometry.csv` | 219430 | `6f2d959a42b7d94a9224612cb0a44021eaffc4b4fbe6277601d1e3edae6ab12c` | S007, S008, S010, S013, S011, S015 | EPSG:4326 | AVAILABLE_MULTIPART_SOURCE_GAPS |
| `road_edge_geometry.geojson` | 509 | `4c275e249364c6917c388d7a3f4e80222a68197433ab9475f2063d129db36946` | S007, S008, S010, S013, S011, S015 | EPSG:4326 | AVAILABLE_MULTIPART_SOURCE_GAPS |
| `melbourne_boundary.geojson` | 1 | `879244c7748bc14e1ce5f8a696cb3c47fd16b0cabb24cc5d6032cae02f078b74` | S016, S017, S018, S019, S020, S021, S022, S023, S024, S025 | EPSG:4326 | AVAILABLE |
| `melbourne_coastline.geojson` | 17 | `48290b27d98cdb78dae59bd3eb698ec381ee355b85fec02e7a9f2d095ae2b564` | S016, S017, S018, S019, S020, S021, S022, S023, S024, S025 | EPSG:4326 | AVAILABLE |
| `melbourne_land_context.geojson` | 0 | `37993517a26e248b9a383664a5872a723a3fdd41bc1f5bb4a473b8b16f9134a4` | S016, S017, S018, S019, S020, S021, S022, S023, S024, S025 | EPSG:4326 | UNRESOLVED |
| `melbourne_context_extent.json` | 1 | `47baf0dcc976e5d646b00e55ab2623efcf280e6cf5a250aaa25669d2b62d75e4` | S007, S008, S010, S013, S011, S015 | EPSG:4326 | AVAILABLE |
| `road_geometry_endpoint_validation.csv` | 509 | `68198257752ccbeeed85fbe4c7d7b7eb1c3d891813458cc135fc8831a80d0c75` | S007, S008, S010, S013, S011, S015 | NOT_APPLICABLE | PASS |
| `geographic_plotting_validation.csv` | 30 | `4dc3917a2db681e736392a6675ca6f07e419056475902392d69e8dac4f3a2127` | S007, S008, S010, S013, S011, S015, S016, S017, S018, S019, S020, S021, S022, S023, S024, S025 | NOT_APPLICABLE | PASS_WITH_UNRESOLVED_CONTEXT |

## Source hashes

| Ref | Original source path | Bytes | SHA256 | Role |
|---|---|---:|---|---|
| S001 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\tools\extract_v41r4_geometry.py` | 43537 | `674f140db2a00f44d5b0d5c9bda9814a2dc7969e46014fb1fcb6655f32ad6f3a` | plotting-only extractor |
| S002 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\PLOTTING_DATA_AUDIT.md` | 112249 | `8babf4492c83761e0edaa563d8c0be854f5e0a8093e5d3275d7ee2b3babac11a` | existing package provenance; read only; existing plotting package; immutable |
| S003 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\aidc_locations.csv` | 969 | `ac20a1095fdad1a32f9664019d122632b5b2938e93364df2011194854a408396` | existing plotting package; immutable; frozen AIDC anchor coordinates |
| S004 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\ieee123_topology.csv` | 13985 | `df10efdecaec3e14de42f2a4b4c77435a46c616a7e53df5941998f216d0e5d1d` | existing plotting package; immutable |
| S005 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\mess_service_locations.csv` | 1706 | `de509ab0189e4f6a176145828ccde98fe6edc5050ed9b72641825e2056b95182` | existing plotting package; immutable; frozen MESS service anchor coordinates |
| S006 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\resource_grid_mapping.csv` | 2697 | `376851305ceee1120367eb0d53c0b64d993577963df6168bd5011d1e0c370367` | existing plotting package; immutable |
| S007 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\road_edges.csv` | 14186 | `b8df39b3529ebed027f8734dfc1471c56be78008a7fe67bd3298acc854101d77` | existing plotting package; immutable; target reduced directed multigraph |
| S008 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\V41R4_plotting_data\road_nodes.csv` | 3469 | `16d79c98233d671ea07d69193bf18271e10ffb0de71a4f2fae5c31b0b79c53f5` | existing plotting package; immutable; frozen road anchor coordinates |
| S009 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\ChatGPT\Mobile ESS 2\v41r4_final_results_pr\docs\v41r4_final\evidence\traffic_provenance\TRAFFIC_PRODUCTION_DAY_BINDINGS.csv` | 63886 | `92d77e5afb41311020ad505f297ce16aa21260fecd5df122c6efea6cad0ac10c` | final frozen production binding |
| S010 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\frozen_artifacts\v41r4_may\m1\a715a5d27c46\M1_IDENTITY.json` | 31139 | `41adaaa3a79a23077a4ad4bbf33bf01d8dede3bb077622365ac65d54c02301f0` | final graph constituent authority |
| S011 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile\network\network_elevated_conditioned.net.xml` | 134326711 | `11b9ce688f2c4fd0d90022a16798c3ae7ebeba879ecac0cac1a1654048f9a61d` | final frozen graph elevated_graph |
| S012 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\10_ml_stage1_multires_traffic_v1\graph\link_order_509.csv` | 24230 | `fed107185a874d5aed78252b4a9fb7a205fc15460e38b31f335cabf945e62ef1` | final frozen graph link_order; original tensor order |
| S013 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\24c_energy_stage_e1r_canonical_physical_route_library_v1_1_metric_repair\library\reduced_link_physical_edge_congestion_catalog.csv.gz` | 2047623 | `e9ea7a4a268fa08a48ba521d2df298dbe4cd7d8756592171bee531c7315055d3` | final frozen graph physical_edges; ordered reduced-link to original physical edges |
| S014 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1\freeze_assets\stage8\optimizer_interface\final_service_nodes_24.csv` | 1443 | `30d3100ebdee70ee13025209794e3a890206b5ed8104465c55c4bbf33b91bf79` | final frozen graph service_nodes |
| S015 | `\\wsl.localhost\Ubuntu-MobileESS-D\mnt\d\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v33m\road_graph_authority.py` | 9019 | `f8c76386d2c0971c18bb33adc80969f38dd5b594fb10bb70c5ebbaad8f412aff` | read-only first-lane geometry selection convention |
| S016 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v01.netccfg` | 1426 | `c5c4e5ef7d9e497d36dc3e8acf343b02d9724063e156de237f8ecfd24b7fb2be` | original OSM tile-to-network lineage; never executed |
| S017 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\study_area.txt` | 81 | `0820713f5f498a6d243cd6a04c0c1c15e89fb87df3f58f2800511f27107f0427` | explicit original study-area geographic bounds |
| S018 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v010_8.osm.xml` | 51981655 | `2115027cab878249dc6cb8d491693e496f6f353a6a871069abae4c6457412c88` | original OSM boundary/coastline candidates; no download |
| S019 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v011_8.osm.xml` | 97628207 | `87a5ffb6f69fc4e8fc73b8ef85a05daf7431167e4f4116142c08f391210ac347` | original OSM boundary/coastline candidates; no download |
| S020 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v012_8.osm.xml` | 84949554 | `51510af13552e246b59a810ea3ff6e2b9e0e5e537dbf816f71449fce625a528a` | original OSM boundary/coastline candidates; no download |
| S021 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v013_8.osm.xml` | 119269883 | `3cea61739002987f624912d0ed6a5d68ac4460e94088744ae2f17b50400efa15` | original OSM boundary/coastline candidates; no download |
| S022 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v014_8.osm.xml` | 173548158 | `49a3381e60f50dcf7b45ac9fdf6ae9eab78ea276ef8c4c86da7d00e75031faf1` | original OSM boundary/coastline candidates; no download |
| S023 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v015_8.osm.xml` | 166035939 | `59e953cf31f2c1482465fc4195258653a00f3da60e716bf08da5979bbbf75f7a` | original OSM boundary/coastline candidates; no download |
| S024 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v016_8.osm.xml` | 163993016 | `3cf7c299134338313c1a99da01ee09982798f531669a75463364ef4ac8eee12a` | original OSM boundary/coastline candidates; no download |
| S025 | `\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline\00_network\melbourne_study_v017_8.osm.xml` | 109697297 | `05471f077584baaeb17cfe26ea15bed6c8638e8cb98e92df3c84664f68928ebe` | original OSM boundary/coastline candidates; no download |

## Reuse in Python

Read the geometry CSV with IDs as strings and keep_default_na=False. Group by road_edge_id and then part_index, sorting by point_order. Never connect separate parts. Prefer the equivalent GeoJSON to preserve MultiLineString geometry directly. Use EPSG:4326 axes; use the extent file as final xlim/ylim. The boundary fallback is outline-only; use coastline as a very light gray stroke. Do not fill the empty land context or the study bbox as land.

The manifest lists each generated payload and this audit with count, hash, CRS and status. A manifest cannot contain its own final byte hash without self-reference; its digest is written to PLOTTING_GEOMETRY_MANIFEST.sha256. The checksum sidecar is metadata, not a geographic payload.
