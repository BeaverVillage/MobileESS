"""Modeled-study domain and role-preference checks; no field/AC certificate."""
import unittest
from pathlib import Path

from ieee8500_v42.joint_geometry import bitset_csp, audit_mapping
from ieee8500_v42.joint_geometry_v3 import load_candidates, common_transform, score_guided_exchanges


class MixedGeometryStudyTests(unittest.TestCase):
    def test_mv_aidc_domain_and_lv_sta_priority_both_preserve_strict_orders(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"AIDC01","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"STA01","role":"STA","traffic_node":"T2","x_east_km":2.,"y_north_km":2.}]
        candidates=[{"bus":"mv1","x":0.,"y":0.},{"bus":"mv2","x":2.,"y":2.},{"bus":"lv1","x":3.,"y":3.}]
        allowed=[[0],[1,2]];priority=[{0:(0,)},{1:(1,),2:(0,)}]
        result=bitset_csp(anchors,candidates,fit,50,5,allowed,priority)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["selected"]["AIDC01"]["bus"],"mv1")
        self.assertEqual(result["selected"]["STA01"]["bus"],"lv1")
        self.assertTrue(all(r["pair_pass"] for r in audit_mapping(anchors,result["selected"],fit)))

    def test_declared_transform_is_shared_positive_scale_proper_rotation(self):
        policy={"uniform_scale":.5,"common_source_center":[10.,20.],"common_target_center":[0.,0.]}
        transform=common_transform(policy,90.)
        self.assertAlmostEqual(transform["u"],0.)
        self.assertAlmostEqual(transform["v"],.5)
        self.assertAlmostEqual(transform["determinant"],.25)
        self.assertAlmostEqual(transform["translation_x"],10.)
        self.assertAlmostEqual(transform["translation_y"],-5.)

    def test_source_domain_has606_mv1177_loaded_customer_lv_and_no_assumed_allowed_power(self):
        root=Path(__file__).resolve().parents[1]
        candidates,inputs=load_candidates(root)
        self.assertEqual(sum(c["mode"]=="MV_MODELED_PORT" for c in candidates),606)
        lv=[c for c in candidates if c["mode"].startswith("LV")]
        self.assertEqual(len(lv),1177)
        self.assertTrue(all(c["original_topology_customer_side"] for c in lv))
        self.assertTrue(all(c["coordinate_authority"].startswith("upstream_primary_proxy") for c in lv))
        self.assertTrue(all(c["terminal_240v"].endswith(".1.2") for c in lv))
        self.assertTrue(all("modeled_allowed_P_kw" not in c for c in candidates))
        self.assertEqual(set(inputs),{"MV","LV","Buscoords","traffic_anchors"})

    def test_joint_two_site_exchange_improves_where_single_moves_cannot(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"AIDC01","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"STA01","role":"STA","traffic_node":"T2","x_east_km":1.,"y_north_km":1.}]
        candidates=[{"bus":f"b{j}","x":float(j),"y":float(j)} for j in range(4)]
        seed={"AIDC01":candidates[0],"STA01":candidates[1]}
        scores=[{0:5.,2:6.},{1:5.,3:4.5}]
        result=score_guided_exchanges(anchors,candidates,fit,seed,scores,[[0,2],[1,3]])
        self.assertAlmostEqual(result["selected_joint_score"],10.5)
        self.assertEqual(result["selected"]["AIDC01"]["bus"],"b2")
        self.assertEqual(result["selected"]["STA01"]["bus"],"b3")
        self.assertEqual(len(result["exchanges"][0]["changes"]),2)
        self.assertTrue(result["one_two_site_local_optimum"])
        self.assertFalse(result["global_optimality_claim"])

    def test_score_exchange_budget_does_not_claim_global_optimality(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"AIDC01","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"STA01","role":"STA","traffic_node":"T2","x_east_km":1.,"y_north_km":1.}]
        candidates=[{"bus":f"b{j}","x":float(j),"y":float(j)} for j in range(4)]
        seed={"AIDC01":candidates[0],"STA01":candidates[1]}
        result=score_guided_exchanges(anchors,candidates,fit,seed,[{0:5.,2:6.},{1:5.,3:4.5}],[[0,2],[1,3]],pair_evaluation_limit=0)
        self.assertTrue(result["budget_exhausted"])
        self.assertFalse(result["global_optimality_claim"])
        self.assertTrue(result["feasible"])


if __name__=="__main__":unittest.main()
