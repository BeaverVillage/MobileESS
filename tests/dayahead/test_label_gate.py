from dayahead.aidc_labels import LabelOrigin, TargetLineage, dependency_firewall


def lineage(target: str, system: str = "NLR_KESTREL_SCHEDULER") -> TargetLineage:
    return TargetLineage(
        target=target,
        label_origin=LabelOrigin.SOURCE_DERIVED,
        depends_on=(),
        derivation_rule="transparent source-field aggregation",
        source_file_sha256=("a" * 64,),
        source_system_id=system,
        timestamp_axis_id="NLR_MOUNTAIN_TO_FIXED_AEST_15MIN_V1",
        first_timestamp="2023-08-10T00:00:00-06:00",
        last_timestamp="2025-06-30T23:59:59-06:00",
    )


def test_joint_gate_passes_only_for_one_source_system_and_axis() -> None:
    p = lineage("P_IT_REF", "NLR_ESIF_FACILITY_POWER")
    result = dependency_firewall((p, lineage("G_REF"), lineage("W_F")))
    assert result["status"] == "PASS"
    assert result["resource_coupling_claim_eligible"] is True


def test_joint_gate_fails_cross_system_and_short_p_coverage() -> None:
    p = TargetLineage(
        target="P_IT_REF",
        label_origin=LabelOrigin.OBSERVED_RAW,
        depends_on=(),
        derivation_rule="15-minute mean of observed ESIF IT power",
        source_file_sha256=("b" * 64,),
        source_system_id="NLR_ESIF_FACILITY_POWER",
        timestamp_axis_id="ESIF_LOCAL_UNRESOLVED_TO_FIXED_AEST_15MIN_V1",
        first_timestamp="2015-11-10T03:00:01",
        last_timestamp="2025-08-29T04:35:08.461000",
    )
    result = dependency_firewall((p, lineage("G_REF"), lineage("W_F")))
    assert result["status"] == "FAIL"
    assert "FAIL_AIDC_P_REF_LABEL" in result["failures"]
    assert "FAIL_AIDC_JOINT_LABEL_ALIGNMENT" in result["failures"]


def test_model_derived_target_is_never_main_target() -> None:
    g = TargetLineage(
        **{**lineage("G_REF").__dict__, "label_origin": LabelOrigin.MODEL_DERIVED}
    )
    result = dependency_firewall((lineage("P_IT_REF", "NLR_ESIF_FACILITY_POWER"), g, lineage("W_F")))
    assert result["status"] == "FAIL"
    assert "FAIL_AIDC_G_REF_LABEL" in result["failures"]
