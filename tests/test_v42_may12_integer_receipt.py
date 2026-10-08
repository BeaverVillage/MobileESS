from v42_may12_rescue.verify_integer import saved_schedule_equal


def test_native_tuple_and_integer_key_roundtrip_matches_json_without_rounding():
    actual={12:dict(segments=[('site1',0,12)],rho=.6592963546281192)}
    saved={'12':dict(segments=[['site1',0,12]],rho=.6592963546281192)}
    assert actual!=saved
    assert saved_schedule_equal(actual,saved)


def test_changed_schedule_or_numerical_value_is_rejected():
    actual={12:dict(segments=[('site1',0,12)],rho=.6592963546281192)}
    assert not saved_schedule_equal(actual,{'12':dict(segments=[['site1',0,13]],rho=.6592963546281192)})
    assert not saved_schedule_equal(actual,{'12':dict(segments=[['site1',0,12]],rho=.6592963546281193)})
    assert not saved_schedule_equal({12:'one','12':'two'},{'12':'two'})
