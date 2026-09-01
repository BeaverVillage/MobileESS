from dayahead.thermal.gfs_idx import parse_idx, select_messages


def test_idx_range_parser_inclusive_boundaries() -> None:
    text = "1:0:d=x:TMP:2 m above ground:x\n2:100:d=x:RH:2 m above ground:x\n3:250:d=x:PRES:surface:x\n"
    parsed = parse_idx(text, 400)
    assert [(x.start, x.end, x.byte_count) for x in parsed] == [(0, 99, 100), (100, 249, 150), (250, 399, 150)]
    selected = select_messages(parsed, {"TMP": "2 m above ground", "PRES": "surface"})
    assert selected["TMP"].range_header == "bytes=0-99"


def test_idx_rejects_missing_required_message() -> None:
    parsed = parse_idx("1:0:d=x:TMP:2 m above ground:x\n", 10)
    try:
        select_messages(parsed, {"DPT": "2 m above ground"})
    except ValueError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("missing variable must fail")
