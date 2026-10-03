"""Independently reconcile downstream device sums against passive terminal nets."""
from .common import *
from .diagnose import diagnose_day

def main():
    if not (OUT/'REG1A_CURRENT_RATING_AUTHORITY.json').exists():raise ValueError('SEQUENTIAL_PRIMARY_AUDIT_REQUIRED')
    if (OUT/'NETWORK_PHASE_CONSERVATION.csv').exists():raise ValueError('SEALED_NETWORK_AUDIT_EXISTS')
    rows=[]
    for day in DAYS:rows.extend(diagnose_day(day,network_check=True))
    emit_csv('NETWORK_PHASE_CONSERVATION.csv',rows)
    error=max(abs(r[k]) for r in rows for k in ('P_conservation_error_kW','Q_conservation_error_kvar'))
    write(OUT,'NETWORK_CONSERVATION_RECEIPT.json',dict(PASS=error<1e-7,maximum_absolute_error_kW_kvar=error,
        phases_reconciled=len(rows),second_pass_slots=384,physical_interventions=0,
        note='Per-phase passive terminal nets include actual losses and any phase transfer in delta transformers. Across ABC their sum is total network complex loss; no loss-free P/3 approximation.'))
    if error>=1e-7:raise ValueError('NETWORK_PHASE_CONSERVATION_FAILURE')

if __name__=='__main__':main()
