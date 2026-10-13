"""Accounting regression; simulated costs are confined to temporary ledgers."""
from v42_integration.budget import IntegrationBudget


def test_independent_accounting_objects_preserve_solver_and_ac_totals(tmp_path):
    path=tmp_path/'UNIT_TEST_ONLY_LEDGER.json'
    first=IntegrationBudget(path)
    second=IntegrationBudget(path)
    first.record_external('UNIT_TEST_SIMULATED_LP',2.5,solver='HIGHS')
    second.record_external('UNIT_TEST_SIMULATED_AC',1.75,solver='AC')
    assert first.used()==2.5
    assert first.document['AC_wall_seconds']==1.75
    assert len(first.document['calls'])==2
    assert second.remaining()==3597.5
