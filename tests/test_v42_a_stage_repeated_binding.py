from types import SimpleNamespace
from v42_pr134_b1 import native
DAY='original'
def constructor(certificate):return (DAY,certificate)
def original_timestamp(bundle):return '2025-05-01T00:00:00+10:00'
def test_date_route_is_idempotent_and_reads_current_bundle():
    routed=native.date_route(original_timestamp)
    assert native.date_route(routed) is routed
    assert routed({'day':'2025-05-17'})=='2025-05-17T00:00:00+10:00'
    assert routed({'day':'2025-05-10'})=='2025-05-10T00:00:00+10:00'
def test_repeated_binding_retains_original_date_constructor(monkeypatch):
    monkeypatch.setattr(native,'_coefficient_constructor',None)
    source=SimpleNamespace(native_coefficients=constructor)
    first=native.original_coefficients_for_day(source,'same-frozen-certificate','2025-05-17')
    cached=first
    source.native_coefficients=lambda certificate:cached
    second=native.original_coefficients_for_day(source,'same-frozen-certificate','2025-05-17')
    third=native.original_coefficients_for_day(source,'same-frozen-certificate','2025-05-10')
    assert second==first==('2025-05-17','same-frozen-certificate')
    assert third==('2025-05-10','same-frozen-certificate')
