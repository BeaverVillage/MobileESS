import itertools
import unittest
from collections import Counter,defaultdict,deque

from ieee8500_v42.geometry import pair_sign,traffic_xy,transform
from ieee8500_v42_joint.selection import ROOT,REPORT,read,rows,regional_propagation,sha


class DispersedPlacementTests(unittest.TestCase):
    def test_original_candidate_rosters_and_port_limits(self):
        A=rows(REPORT/'AIDC_MV_CANDIDATES.csv');S=rows(REPORT/'STA_MV_LV_CANDIDATES.csv')
        self.assertEqual(len(A),606);self.assertEqual(len(S),1783)
        self.assertEqual(len({r['candidate_bus'] for r in S}),1783)
        self.assertEqual(Counter(r['connection_mode'] for r in S),{'MV_3PH':606,'LV_SPLIT_240':1177})
        self.assertTrue(all(r['phase_nodes']=='1,2,3' for r in A))
        for r in S:
            if r['connection_mode']=='LV_SPLIT_240':
                self.assertEqual(float(r['engineered_port_Pmax_kw']),5)
                self.assertEqual(float(r['engineered_port_Smax_kva']),6)
                self.assertEqual(float(r['engineered_port_current_limit_A']),27)
                self.assertTrue(r['support_triplex_lines'])
            else:
                self.assertEqual(float(r['new_dedicated_MV_transformer_kva']),750)
                self.assertFalse(r['original_service_transformer'])

    def test_all_eight_regions_are_connected_source_tree_components(self):
        tree=read(REPORT/'ELECTRICAL_REGION_SOURCE_TREE.json')
        membership=tree['ABC_region_membership'];parent=tree['ABC_tree_parent'];graph=defaultdict(set)
        self.assertEqual(len(parent),647);self.assertEqual(len(membership),647)
        self.assertEqual(len(set(membership.values())),8)
        self.assertFalse(tree['AC_score_used_to_construct_regions'])
        for b,a in parent.items():
            if a is not None:graph[a].add(b);graph[b].add(a)
        for region in set(membership.values()):
            group={b for b,r in membership.items() if r==region};seen={next(iter(group))};queue=deque(seen)
            while queue:
                for b in graph[queue.popleft()]&group-seen:seen.add(b);queue.append(b)
            self.assertEqual(seen,group)

    def test_role_region_cap_uses_forced_region_not_only_fixed_bus(self):
        # Candidate0 and1 both lie in R1; a two-bus domain still forces R1.
        masks={'R1':3,'R2':12,'R3':48}
        hard={'role_max_per_region':2,'combined_max_per_region':4,'each_role_min_regions':1,'combined_min_regions':1}
        propagated=regional_propagation([3,3,15,16],['AIDC','AIDC','AIDC','STA'],masks,hard)
        self.assertEqual(propagated[2],12)
        self.assertIsNone(regional_propagation([3,3,3,16],['AIDC','AIDC','AIDC','STA'],masks,hard))

    def test_combined_region_cap_and_coverage_are_hard(self):
        masks={'R1':3,'R2':12,'R3':48}
        hard={'role_max_per_region':3,'combined_max_per_region':2,'each_role_min_regions':1,'combined_min_regions':2}
        self.assertIsNone(regional_propagation([3,3,3],['AIDC','STA','STA'],masks,hard))
        self.assertIsNone(regional_propagation([3,3],['AIDC','STA'],masks,hard))
        self.assertIsNotNone(regional_propagation([3,12],['AIDC','STA'],masks,hard))

    def test_role_coverage_forces_sole_support_and_rejects_cross_role_shortcut(self):
        masks={'R1':1,'R2':2,'R3':4}
        hard={'role_max_per_region':3,'combined_max_per_region':4,'each_role_min_regions':3,'combined_min_regions':3}
        roles=['AIDC']*3+['STA']*3
        propagated=regional_propagation([1,3,6,1,2,4],roles,masks,hard)
        self.assertEqual(propagated,[1,2,4,1,2,4])
        # STA covers R3 but cannot satisfy AIDC's own three-region requirement.
        self.assertIsNone(regional_propagation([1,3,3,1,2,4],roles,masks,hard))

    def test_saved_witnesses_have_552_axes_and_actual_original_phase_paths(self):
        for case in ('C1','C2'):
            folder=REPORT/(case+'_GEOMETRY_ONLY')
            axes=rows(folder/'RELATIVE_POSITION_552AXIS_AUDIT.csv')
            self.assertEqual(len(axes),552)
            self.assertEqual(len({(r['location_a'],r['location_b'],r['axis']) for r in axes}),552)
            self.assertTrue(all(r['axis_PASS']=='True' for r in axes))
            paths=rows(folder/'ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv')
            self.assertEqual(len({r['location_id'] for r in paths}),24)
            self.assertTrue(all(r['required_phase_path_PASS']=='True' for r in paths))
            self.assertTrue(all(r['new_primary_conductor_added']=='False' for r in paths))
            self.assertTrue(all(r['source_path_is_field_installation_approval']=='False' for r in paths))
            for r in paths:
                required=set(r['requested_primary_phase_nodes'].split(','))
                available=set(r['original_available_primary_phase_nodes'].split(','))
                self.assertLessEqual(required,available)
                if r['connection_mode']=='MV_3PH':self.assertEqual(required,{'1','2','3'})
            laterals=rows(folder/'ORIGINAL_PRIMARY_LATERAL_AUDIT.csv')
            self.assertEqual(len(laterals),24)
            self.assertTrue(all(r['electrical_region_is_independent_feeder_lateral']=='False' for r in laterals))

    def test_C1_C2_geometry_witnesses_have_complete_hard_dispersion(self):
        for case,mv,lv in [('C1',6,6),('C2',12,0)]:
            folder=REPORT/(case+'_GEOMETRY_ONLY');result=read(folder/'SELECTION_RESULT.json')
            self.assertTrue(result['feasible']);self.assertTrue(result['all_directions_PASS'])
            self.assertTrue(result['all_region_caps_coverage_PASS'])
            self.assertEqual(result['distinct_buses'],24)
            self.assertEqual((result['STA_MV_count'],result['STA_LV_count']),(mv,lv))
            audit=rows(folder/'RELATIVE_POSITION_276PAIR_AUDIT.csv')
            self.assertEqual(len(audit),276)
            self.assertTrue(all(r['x_pass']=='True' and r['y_pass']=='True' for r in audit))
            dispersion=rows(folder/'ELECTRICAL_REGION_DISPERSION_AUDIT.csv')
            self.assertTrue(all(r['region_cap_PASS']=='True' and r['coverage_PASS']=='True' for r in dispersion))
            self.assertFalse(result['Production_installation_PASS'])

    def test_scored_witness_reconstructed_directions_and_preregistered_caps(self):
        anchors={r['location_id']:r for r in read(ROOT/'ieee8500_v42/data/geometry/STATIC_24_TRAFFIC_ANCHORS.json')}
        candidate={r['candidate_id']:r for r in rows(REPORT/'STA_MV_LV_CANDIDATES.csv')}
        for case in ('C1','C2'):
            folder=REPORT/(case+'_SCORED');selection=rows(folder/'JOINT_LOCATION_SELECTION.csv')
            result=read(folder/'SELECTION_RESULT.json');fit=result['proper_common_transform'];points={}
            self.assertEqual(len(selection),24)
            self.assertEqual(len({r['candidate_bus'] for r in selection}),24)
            self.assertEqual(sha(folder/'JOINT_LOCATION_SELECTION.csv'),result['witness_sha256'])
            role_counts={'AIDC':Counter(),'STA':Counter()};combined=Counter()
            for r in selection:
                original=candidate[r['candidate_id']]
                point=transform((float(original['source_or_proxy_x']),float(original['source_or_proxy_y'])),fit)
                self.assertAlmostEqual(point[0],float(r['common_frame_x_km']),places=8)
                self.assertAlmostEqual(point[1],float(r['common_frame_y_km']),places=8)
                self.assertEqual(r['traffic_node_id'],anchors[r['location_id']]['traffic_node'])
                points[r['location_id']]=point
                region=original['electrical_region'];role_counts[r['role']][region]+=1;combined[region]+=1
                if r['role']=='AIDC' or case=='C2' or int(r['location_id'][3:])%2==0:
                    self.assertEqual(r['connection_mode'],'MV_3PH')
                else:self.assertEqual(r['connection_mode'],'LV_SPLIT_240')
            for a,b in itertools.combinations(selection,2):
                na,nb=a['location_id'],b['location_id']
                for axis in (0,1):
                    expected=pair_sign(traffic_xy(anchors[na]),traffic_xy(anchors[nb]),axis)
                    actual=points[nb][axis]-points[na][axis]
                    if expected:self.assertGreater(actual*expected,0)
            for counts in role_counts.values():
                self.assertGreaterEqual(len(counts),4);self.assertLessEqual(max(counts.values()),4)
            self.assertGreaterEqual(len(combined),6);self.assertLessEqual(max(combined.values()),6)

    def test_scored_mapping_input_freeze_and_overlap_do_not_claim_AIDC_dispatch(self):
        frozen=read(REPORT/'FINAL_CANDIDATE_SCORE_FREEZE.json');score=REPORT/'FINAL_JOINT_CANDIDATE_SCORES.csv'
        self.assertEqual(sha(score),frozen['score']['sha256'])
        values={(r['location_id'],r['candidate_id']):float(r['score']) for r in rows(score)}
        for case in ('C1','C2'):
            folder=REPORT/(case+'_SCORED');receipt=read(folder/'SEARCH_INPUT_FREEZE.json')
            self.assertEqual(list(receipt['score_source_sha256'].values()),[sha(score)])
            for r in rows(folder/'JOINT_LOCATION_SELECTION.csv'):
                self.assertEqual(float(r['source_sensitivity_score']),values[(r['location_id'],r['candidate_id'])])
            overlap=rows(folder/'JOINT_CONTROL_OVERLAP_AUDIT.csv')
            self.assertEqual(len(overlap),276)
            self.assertTrue(all(r['certified_AIDC_pair_response_cosine']=='' for r in overlap))
            self.assertTrue(all(r['realized_joint_AIDC_MESS_complementarity']=='UNPROVEN' for r in overlap))
            self.assertTrue(all(r['overlap_audited_not_optimized']=='True' for r in overlap))
            self.assertTrue(all(r['response_bound_is_simultaneous_physical_dispatch_certificate']=='False' for r in overlap))

    def test_preregistration_and_historical_scope_preserved(self):
        policy=read(REPORT/'JOINT_PLACEMENT_PREREGISTRATION.json')
        self.assertEqual(policy['dispersion_hard_constraints'],{'role_max_per_region':4,'combined_max_per_region':6,
                                                               'each_role_min_regions':4,'combined_min_regions':6})
        self.assertTrue(policy['topology_regions_frozen_before_current_AC_scores'])
        self.assertFalse(policy['B1_B2_B3_outcomes_used'])
        self.assertFalse(policy['common_transform']['reflection'])
        self.assertFalse(policy['common_transform']['per_site_rotation'])
        self.assertEqual(policy['C1']['STA_even_IDs'],'MV_3PH')
        self.assertEqual(policy['C1']['STA_odd_IDs'],'LV_SPLIT_240')


if __name__=='__main__':unittest.main()
