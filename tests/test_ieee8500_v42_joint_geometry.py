"""Static assignment fixtures only; no port or AC validation claim."""
import unittest
from ieee8500_v42.joint_geometry import dense_rank, solve_assignment, audit_mapping, bitset_csp


class JointGeometryTests(unittest.TestCase):
    def test_dense_ranks_preserve_strict_order_without_minimum_spacing(self):
        self.assertEqual(dense_rank([9.,1.,1.,1.0000000001,4.]),[3,0,0,1,2])

    def test_fixture_preserves_all_pairs_with_shared_transform(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"AIDC01","role":"AIDC","traffic_node":"TN_01","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"STA01","role":"STA","traffic_node":"TN_43","x_east_km":2.,"y_north_km":2.},
                 {"location_id":"AIDC02","role":"AIDC","traffic_node":"TN_02","x_east_km":4.,"y_north_km":1.}]
        candidates=[{"bus":name,"x":x,"y":y} for name,x,y in (("a",0.,0.),("b",2.,2.),("c",4.,1.),("d",-1.,-1.))]
        result=solve_assignment(anchors,candidates,fit,None,5)
        self.assertTrue(result["feasible"])
        self.assertEqual(len({c["bus"] for c in result["selected"].values()}),3)
        self.assertTrue(all(r["pair_pass"] for r in audit_mapping(anchors,result["selected"],fit)))
        csp=bitset_csp(anchors,candidates,fit,50,5)
        self.assertTrue(csp["feasible"])
        self.assertTrue(all(r["pair_pass"] for r in audit_mapping(anchors,csp["selected"],fit)))

    def test_truncated_failure_never_claims_global_infeasibility(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"AIDC01","role":"AIDC","traffic_node":"TN_01","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"STA01","role":"STA","traffic_node":"TN_43","x_east_km":.01,"y_north_km":.01}]
        candidates=[{"bus":"a","x":0.,"y":0.},{"bus":"b","x":2.,"y":2.}]
        result=solve_assignment(anchors,candidates,fit,1,5)
        self.assertFalse(result["feasible"])
        self.assertFalse(result["global_infeasibility_claim"])

    def test_csp_coordinate_tie_cannot_satisfy_strict_axis(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"A","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"S","role":"STA","traffic_node":"T2","x_east_km":1.,"y_north_km":2.}]
        candidates=[{"bus":"a","x":0.,"y":0.},{"bus":"b","x":0.,"y":2.}]
        result=bitset_csp(anchors,candidates,fit,50,5)
        self.assertFalse(result["feasible"])
        self.assertEqual(result["status"],"INFEASIBLE_FROZEN_ORIENTATION_DOMAIN")
        self.assertFalse(result["global_infeasibility_claim"])

    def test_near_pair_exemption_still_requires_distinct_buses(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"A","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"S","role":"STA","traffic_node":"T2","x_east_km":.0001,"y_north_km":.0001}]
        candidates=[{"bus":"a","x":0.,"y":0.},{"bus":"b","x":0.,"y":0.}]
        result=bitset_csp(anchors,candidates,fit,50,5)
        self.assertTrue(result["feasible"])
        self.assertEqual(len({r["bus"] for r in result["selected"].values()}),2)
        restricted=bitset_csp(anchors,candidates,fit,50,5,[[0],[0]])
        self.assertFalse(restricted["feasible"])

    def test_csp_budget_exhaustion_is_unknown(self):
        fit={"u":1.,"v":0.,"translation_x":0.,"translation_y":0.}
        anchors=[{"location_id":"A","role":"AIDC","traffic_node":"T1","x_east_km":0.,"y_north_km":0.},
                 {"location_id":"S","role":"STA","traffic_node":"T2","x_east_km":1.,"y_north_km":1.}]
        candidates=[{"bus":"a","x":0.,"y":0.},{"bus":"b","x":1.,"y":1.}]
        result=bitset_csp(anchors,candidates,fit,node_limit=0,seconds_limit=5)
        self.assertTrue(result["budget_exhausted"])
        self.assertEqual(result["status"],"UNKNOWN_BOUNDED_SEARCH")
        self.assertFalse(result["global_infeasibility_claim"])


if __name__=="__main__":unittest.main()
