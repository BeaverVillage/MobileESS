from pathlib import Path
import json
H=Path(__file__).resolve().parent
a5=json.loads((H/"ConversationA_R25E_A5_NODE_ARC_EXACT_PROOF_RESULT.json").read_text())
c=json.loads((H/"R25G_A6R3_CONTRACT.json").read_text())
assert a5["PASS"] is True
assert a5["path_to_node_occupancy_injective"] is True
assert c["exactness"]["STAY_binary_is_redundant_integrality_on_R25E_integer_path_set"] is True
assert c["exactness"]["debt_stay_cover_implied"] is True
assert c["exactness"]["soc_stay_cover_implied"] is True
print(json.dumps({"status":"PASS","R25E_path_exactness_inherited":True,"STAY_binary_domain_exact":True,"resource_cover_cuts_exact":True,"long_solver_run":False},indent=2))
