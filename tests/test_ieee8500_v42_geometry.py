"""Static geometry tests; passing does not certify AC or physical port readiness."""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from ieee8500_v42.geometry import (
    AIDC_BUSES, POLICY, affine_anchor_certificate, enumerate_lv_candidates,
    fit_similarity, pair_sign, projection_intervals, read_coords, read_csv,
    relative_audit, select_sta_candidates, sha256, traffic_xy, transform,
)

ROOT = Path(__file__).resolve().parents[1]
FEEDER = ROOT / "ieee8500_v42/data/feeder"
GEOMETRY = ROOT / "ieee8500_v42/data/geometry"


class GeometryContractTests(unittest.TestCase):
    def test_global_fit_recovers_rotation_scale_and_translation(self):
        points=[(0.,0.),(2.,0.),(0.,3.),(4.,5.)]
        angle=0.7;scale=3.5
        expected={"u":scale*math.cos(angle),"v":scale*math.sin(angle),
                  "translation_x":2.,"translation_y":-9.}
        mapped=[transform(p,expected) for p in points]
        fitted=fit_similarity(points,mapped)
        self.assertGreater(fitted["determinant"],0)
        for p,q in zip(points,mapped):
            self.assertLess(math.dist(transform(p,fitted),q),1e-12)

    def test_convex_origin_certificate_proves_projection_impossible(self):
        # Analytic three half-plane counterexample; any two alone are feasible.
        vectors=[(1.,0.),(-0.5,math.sqrt(3)/2),(-0.5,-math.sqrt(3)/2)]
        constraints=[{"signed_grid_delta":v} for v in vectors]
        self.assertEqual(projection_intervals(constraints),[])
        for i in range(3):
            self.assertTrue(projection_intervals(constraints[:i]+constraints[i+1:]))
        self.assertAlmostEqual(sum(v[0] for v in vectors),0)
        self.assertAlmostEqual(sum(v[1] for v in vectors),0)

    def test_frozen_tolerance_only_exempts_predefined_near_relations(self):
        self.assertEqual(pair_sign((0.,0.),(0.0001,0.0001),0),0)
        self.assertEqual(pair_sign((0.,0.),(0.0005,2.),0),0)
        self.assertEqual(pair_sign((0.,0.),(0.002,2.),0),1)
        self.assertEqual(POLICY["traffic_pair_distance_tolerance_km"],0.001)
        self.assertFalse(POLICY["direction_relaxation_allowed"])

    def test_geometry_feasibility_never_approves_an_undocumented_port(self):
        grid={aid:(float(i),float(i)) for i,aid in enumerate(sorted(AIDC_BUSES))}
        anchors=[{"location_id":aid,"role":"AIDC","x_east_km":p[0],"y_north_km":p[1]}
                 for aid,p in grid.items()]
        fit=fit_similarity(list(grid.values()),list(grid.values()))
        candidate={"physical_eligibility":"STOP_NO_APPROVED_CONNECTION_PORT"}
        result=select_sta_candidates(anchors,grid,[candidate],fit)
        self.assertEqual(result["status"],"STOP_NO_APPROVED_LV_PORTS")
        self.assertEqual(result["selected"],{})

    def test_approved_fixture_allocation_preserves_sta_pairs_and_unique_buses(self):
        grid={aid:(float(i),float(i)) for i,aid in enumerate(sorted(AIDC_BUSES))}
        anchors=[{"location_id":aid,"role":"AIDC","x_east_km":p[0],"y_north_km":p[1]}
                 for aid,p in grid.items()]
        anchors.extend([{"location_id":"STA01","role":"STA","x_east_km":5.8,"y_north_km":5.8},
                        {"location_id":"STA02","role":"STA","x_east_km":5.3,"y_north_km":5.3}])
        fit=fit_similarity(list(grid.values()),list(grid.values()))
        candidates=[{"physical_eligibility":"PASS","candidate_bus":name,"proxy_x":x,"proxy_y":x}
                    for name,x in (("sx_low",5.2),("sx_high",5.7))]
        result=select_sta_candidates(anchors,grid,candidates,fit)
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["selected"]["STA01"]["candidate_bus"],"sx_high")
        self.assertEqual(result["selected"]["STA02"]["candidate_bus"],"sx_low")


class OriginalSourceGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anchors=json.loads((GEOMETRY/"STATIC_24_TRAFFIC_ANCHORS.json").read_text())
        cls.original=read_csv(GEOMETRY/"ORIGINAL_24_LOCATION_ELECTRICAL_MAPPING.csv")
        xy=read_coords(FEEDER/"Buscoords.dss")
        cls.grid={r["location_id"]:xy[r["ieee8500_bus"].lower()] for r in cls.original}
        cls.traffic={a["location_id"]:traffic_xy(a) for a in cls.anchors}
        ids=sorted(AIDC_BUSES)
        cls.fit=fit_similarity([cls.grid[a] for a in ids],[cls.traffic[a] for a in ids])

    def test_actual_fixed_anchor_certificate_has_positive_weights(self):
        certificate=affine_anchor_certificate(sorted(AIDC_BUSES),self.traffic,self.grid)
        self.assertTrue(certificate["infeasible_even_for_affine"])
        for axis in ("east_west","north_south"):
            entry=certificate[axis]
            self.assertEqual(entry["constraint_count"],66)
            self.assertEqual(entry["feasible_intervals_radians"],[])
            self.assertEqual(len(entry["irreducible_witness"]),3)
            self.assertTrue(all(w>0 for w in entry["positive_convex_weights"]))
            self.assertLess(math.hypot(*entry["weighted_vector_residual"]),1e-8)

    def test_all_276_pairs_use_exactly_one_positive_determinant_fit(self):
        audit=relative_audit(self.anchors,self.grid,self.fit)
        self.assertEqual(len(audit),276)
        for category,count in (("AIDC-AIDC",66),("AIDC-STA",144),("STA-STA",66)):
            self.assertEqual(sum(r["role_pair"]==category for r in audit),count)
        self.assertGreater(self.fit["determinant"],0)
        self.assertTrue(any(not r["pair_pass"] for r in audit if r["role_pair"]=="AIDC-AIDC"))

    def test_full_topology_enumeration_is_customer_side_and_fail_closed(self):
        hashes_before={p.name:sha256(p) for p in FEEDER.iterdir() if p.is_file()}
        candidates=enumerate_lv_candidates(FEEDER)
        self.assertEqual(len(candidates),1177)
        self.assertEqual(len({c["candidate_bus"] for c in candidates}),1177)
        self.assertTrue(all(c["topology_customer_side"] for c in candidates))
        self.assertTrue(all(c["customer_terminal_degree"]==1 for c in candidates))
        self.assertTrue(all(c["candidate_bus"].startswith("sx") for c in candidates))
        self.assertTrue(all(c["injection_terminal_240v"].endswith(".1.2") for c in candidates))
        self.assertTrue(all(c["triplex_min_normal_amps"]>0 for c in candidates))
        self.assertTrue(all(c["allowed_pcc_p_kw"]=="" for c in candidates))
        self.assertTrue(all(c["physical_eligibility"]!="PASS" for c in candidates))
        self.assertEqual(hashes_before,{p.name:sha256(p) for p in FEEDER.iterdir() if p.is_file()})
        selection=select_sta_candidates(self.anchors,self.grid,candidates,self.fit)
        self.assertEqual(selection["status"],"STOP_FIXED_AIDC_GEOMETRY_INFEASIBLE")
        self.assertEqual(selection["selected"],{})
        self.assertEqual(selection["search_nodes"],0)

    def test_original_fixed_bus_and_service_identity_preserved(self):
        registry={r["location_id"]:r for r in self.original}
        self.assertEqual(len(registry),24)
        for aid,bus in AIDC_BUSES.items():
            self.assertEqual(registry[aid]["ieee8500_bus"].lower(),bus)
        sta=[a for a in self.anchors if a["role"]=="STA"]
        self.assertEqual(len(sta),12)
        self.assertEqual(len({a["traffic_node"] for a in sta}),12)


if __name__ == "__main__":
    unittest.main()
