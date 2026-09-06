def test_causal_bin_index_strict_parquet_roundtrip_preserves_all_values(tmp_path):
    import pandas as pd
    from dayahead.v41.data import parquet_index
    original=pd.DataFrame({'count':[3,0,4]},index=pd.date_range('2025-04-30',periods=3,freq='30min',tz='UTC',name='arrival_bin'))
    frame=parquet_index(original)
    assert original.index.freq is not None and frame.index.freq is None
    assert frame.index.equals(original.index) and frame.equals(original)
    path=tmp_path/'bins.parquet';frame.to_parquet(path,index=True)
    pd.testing.assert_frame_equal(frame,pd.read_parquet(path),check_exact=True)


def test_mixed_raw_timestamp_units_preserve_instants_in_strict_bin_readback(tmp_path):
    import pandas as pd
    from dayahead.v41.data import parquet_bins
    index=pd.date_range('2025-04-30',periods=3,freq='30min',tz='UTC',name='arrival_bin')
    times=[pd.Timestamp('2025-04-30T00:01:00.123456Z').as_unit('us'),None,
        pd.Timestamp('2025-04-30T01:00:00.123456789Z')]
    original=pd.DataFrame({'max_observed_end':pd.Series(times,index=index,dtype=object),
        'modeled_end_max':pd.Series(times,index=index,dtype=object),'submit_count':[1,0,2]},index=index)
    frame=parquet_bins(original)
    assert original.max_observed_end.dtype==object and original.index.freq is not None
    assert frame.max_observed_end.iloc[0]==times[0] and frame.max_observed_end.iloc[2]==times[2]
    path=tmp_path/'bins.parquet';frame.to_parquet(path)
    pd.testing.assert_frame_equal(frame,pd.read_parquet(path),check_exact=True)
