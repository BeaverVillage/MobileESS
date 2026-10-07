"""A known accepted integer witness cannot be silently excluded by a proof."""
def conflicts_with_known_witness(node,result,witness):
    return result['LP_status']=='INFEASIBLE' and result.get('exact_infeasibility_PASS',False) and all(witness[j]==v for j,v in node['fixings'])
