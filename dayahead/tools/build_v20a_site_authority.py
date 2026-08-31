"""Build V20A evidence-only Melbourne site-scale authority artifacts.

This module deliberately refuses mixed-boundary aggregation.  It reuses the
frozen April-2025 source registry and records the stricter V20 interpretation.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"
OLD = ROOT / "dayahead" / "artifacts" / "melbourne_aidc_april2025_scale"
PUE = 1.30


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(site_name: str, operator: str, address: str, status: str, value: object,
        unit: str | None, boundary: str, effective: str | None, published: str | None,
        commissioning: str, url: str, title: str, source_type: str, grade: str,
        applicable: object, harmonizable: bool, confidence: str, notes: str) -> dict[str, object]:
    return {
        "site_name": site_name, "operator": operator, "address": address,
        "April_2025_operational_status": status, "reported_value": value,
        "reported_unit": unit, "boundary_type": boundary, "effective_date": effective,
        "publication_date": published, "commissioning_status": commissioning,
        "source_url": url, "source_title": title, "source_type": source_type,
        "source_quality_grade": grade, "April_2025_applicable": applicable,
        "directly_harmonizable_to_IT_MW": harmonizable, "confidence": confidence,
        "notes": notes,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sites = [
        row("Equinix ME4", "Equinix", "2 Davis Court, Derrimut VIC 3026",
            "OPERATIONAL_DURING_APRIL_2025", None, None, "UNKNOWN", None, None,
            "OPERATING", "https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me4",
            "ME4 Melbourne data center", "OPERATOR_OFFICIAL", "A", True, False, "B",
            "Official operation/location support; no April-qualified MW is published."),
        row("Micron21", "Micron21", "7 Eastspur Court, Kilsyth South VIC 3137",
            "OPERATIONAL_DURING_APRIL_2025", 2.0, "MW", "BUILD_CAPACITY", None, None,
            "OPERATING", "https://www.datacentermap.com/australia/melbourne/micron21-melbourne-datacentre/specs/",
            "Micron21 Melbourne datacentre specifications", "COMMERCIAL_DIRECTORY", "E", "uncertain", False, "C",
            "Directory says fully-built-out power; neither April operating state nor IT boundary is established."),
        row("Fujitsu Noble Park", "Fujitsu", "3-5 Summit Road, Noble Park North VIC 3174",
            "OPERATIONAL_DURING_APRIL_2025", "2 x 4", "MVA", "MVA", None, "2014-11-06",
            "OPERATING", "https://www.fujitsu.com/au/Images/Fujitsu-Data-Centre-Noble-Park-Fact-Sheet.pdf",
            "Noble Park data centre fact sheet", "OPERATOR_OFFICIAL", "A", True, False, "B",
            "Main-feed component rating; not IT MW and not converted without a source PF/boundary relation."),
        row("AAPT / TPG Richmond", "TPG Telecom / AAPT", "180 Burnley Street, Richmond VIC 3121",
            "OPERATIONAL_DURING_APRIL_2025", 2.5, "MVA", "MVA", None, None,
            "OPERATING", "https://inflect.com/building/180-burnley-street-richmond/tpg-telecom/datacenter/aapt-richmond-melbourne",
            "AAPT Richmond Melbourne", "COMMERCIAL_DIRECTORY", "E", "uncertain", False, "C",
            "Third-party power capacity; no source PF and no IT boundary."),
        row("NEXTDC M2", "NEXTDC", "75 Sharps Road, Tullamarine VIC 3043",
            "OPERATIONAL_DURING_APRIL_2025", 42.0, "MW", "OPERATING_CAPACITY", "2024-12-31", "2025-02-25",
            "OPERATING", "https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf",
            "NEXTDC 1H25 Results Presentation", "OPERATOR_OFFICIAL_FILING", "A", True, False, "A",
            "Official built capacity at 31-Dec-2024; V20 does not silently relabel built capacity as IT load."),
        row("NEXTDC M3", "NEXTDC", "25 Indwe Street, West Footscray VIC 3012",
            "OPERATIONAL_DURING_APRIL_2025", 13.5, "MW", "OPERATING_CAPACITY", "2024-12-31", "2025-02-25",
            "OPERATING", "https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf",
            "NEXTDC 1H25 Results Presentation", "OPERATOR_OFFICIAL_FILING", "A", True, False, "A",
            "Official built capacity; the additional 13.5MW was in progress and is excluded."),
        row("Vocus Mitcham", "Vocus", "28 Thornton Crescent, Mitcham VIC 3132",
            "OPERATIONAL_DURING_APRIL_2025", 9.0, "MW", "BUILD_CAPACITY", None, None,
            "OPERATING", "https://www.datacentermap.com/australia/melbourne/mitcham/specs/",
            "Vocus Mitcham specifications", "COMMERCIAL_DIRECTORY", "E", "uncertain", False, "C",
            "Fully-built-out directory value; no April operating or IT-boundary proof."),
        row("NEXTDC M1", "NEXTDC", "826-846 Lorimer Street, Port Melbourne VIC 3207",
            "OPERATIONAL_DURING_APRIL_2025", 15.0, "MW", "OPERATING_CAPACITY", "2024-12-31", "2025-02-25",
            "OPERATING", "https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf",
            "NEXTDC 1H25 Results Presentation", "OPERATOR_OFFICIAL_FILING", "A", True, False, "B",
            "15MW is the documented Victorian built-capacity residual and agrees with the operator target-IT specification; retained as operating-capacity boundary."),
        row("Equinix ME5", "Equinix", "22-36 Walsh Street, West Melbourne VIC 3003",
            "OPERATIONAL_DURING_APRIL_2025", 4.175, "MW", "GENERATOR_NAMEPLATE", None, None,
            "OPERATING", "https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me5",
            "ME5 Melbourne data center", "OPERATOR_OFFICIAL", "A", "uncertain", False, "C",
            "Sum of listed generator nameplates only; explicitly prohibited as IT/facility capacity."),
        row("CDC Brooklyn BK1", "CDC Data Centres", "Brooklyn, VIC",
            "OPERATIONAL_DURING_APRIL_2025", None, None, "UNKNOWN", "2024", "2024",
            "OPERATING", "https://cdc.com/media/y0nbxbdf/cdc-sustainability-report-2024.pdf",
            "CDC Sustainability Report 2024", "OPERATOR_OFFICIAL_REPORT", "A", True, False, "B",
            "Official report identifies BK1 as operational; 350MW/780MW campus-region future totals are not BK1 April capacity."),
        row("IBM MEL01", "IBM", "1279 Nepean Highway, Cheltenham VIC 3192",
            "APRIL_2025_STATUS_UNCERTAIN", None, None, "UNKNOWN", None, "2020-07-07",
            "UNCERTAIN", "https://www.ibm.com/support/pages/sites/default/files/inline-files/anz_27k_ver2.pdf",
            "IBM ISO 27001 certificate appendix", "OPERATOR_OFFICIAL_CERTIFICATE", "B", "uncertain", False, "D",
            "Certificate establishes a managed-service site in 2020, not April-2025 operation or MW."),
        row("STACK MEL01A", "STACK Infrastructure", "399 Palmers Road, Truganina VIC 3029",
            "OPERATIONAL_DURING_APRIL_2025", 36.0, "MW", "OPERATING_CAPACITY", "2023-08-22", "2023-08-22",
            "COMMISSIONED", "https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-delivers-first-data-center-in-australia-launching-a-robust-apac-portfolio/",
            "STACK delivers first data center in Australia", "OPERATOR_OFFICIAL", "A", True, False, "A",
            "Opened 36MW building; 72MW campus is future context. Boundary is not relabeled IT MW."),
    ]

    csv_name = "V20A_MELBOURNE_12SITE_CAPACITY_EVIDENCE.csv"
    with (OUT / csv_name).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sites[0]))
        writer.writeheader(); writer.writerows(sites)

    registry = {
        "artifact_id": "V20A_SITE_CAPACITY_SOURCE_REGISTRY_V1", "access_date": str(date.today()),
        "reference_period": "2025-04-01/2025-04-30 AEST", "sources": sites,
        "prior_registry": {"path": str((OLD / "MELBOURNE_AIDC_APRIL2025_SCALE_SOURCE_REGISTRY.json").relative_to(ROOT)),
                           "sha256": sha(OLD / "MELBOURNE_AIDC_APRIL2025_SCALE_SOURCE_REGISTRY.json")},
        "source_priority_applied": "operator > owner/investor > government/utility > trade press > directory",
    }
    write_json("V20A_SITE_CAPACITY_SOURCE_REGISTRY.json", registry)

    sets = {"DIRECT_IT_MW_SET": [], "OPERATING_CAPACITY_MW_SET": [],
            "FACILITY_INCOMING_POWER_SET": [], "MVA_ONLY_SET": []}
    for s in sites:
        if s["boundary_type"] in {"IT_LOAD", "IT_CAPACITY", "CRITICAL_IT"} and s["directly_harmonizable_to_IT_MW"]:
            sets["DIRECT_IT_MW_SET"].append(s["site_name"])
        elif s["boundary_type"] == "OPERATING_CAPACITY":
            sets["OPERATING_CAPACITY_MW_SET"].append(s["site_name"])
        elif s["boundary_type"] in {"FACILITY_POWER", "INCOMING_POWER"}:
            sets["FACILITY_INCOMING_POWER_SET"].append(s["site_name"])
        elif s["boundary_type"] == "MVA":
            sets["MVA_ONLY_SET"].append(s["site_name"])
    op_values = {s["site_name"]: float(s["reported_value"]) for s in sites if s["boundary_type"] == "OPERATING_CAPACITY"}
    op_total = sum(op_values.values())
    harmonization = {
        "artifact_id": "V20A_CAPACITY_BOUNDARY_HARMONIZATION_V1", "sets": sets,
        "set_totals": {"DIRECT_IT_MW_SET": None, "OPERATING_CAPACITY_MW_SET": op_total,
                       "FACILITY_INCOMING_POWER_SET": None, "MVA_ONLY_SET": "NOT_SUMMED_AS_MW"},
        "mixed_boundary_silent_aggregation_count": 0, "MVA_to_MW_unsupported_conversion_count": 0,
        "unknown_to_zero_count": 0, "facility_power_divided_by_PUE_count": 0,
        "PUE_1_30_role": "CASE_STUDY_PCC_CONVERSION_ONLY_NOT_REAL_CAPACITY_HARMONIZER",
    }
    write_json("V20A_CAPACITY_BOUNDARY_HARMONIZATION.json", harmonization)

    numerator = {
        "artifact_id": "V20A_REALWORLD_AIDC_NUMERATOR_REVIEW_V1",
        "DIRECT_IT_MW_SET": {"total_MW": None, "coverage_sites": 0, "status": "NOT_IDENTIFIABLE"},
        "OPERATING_CAPACITY_MW_SET": {"total_MW": op_total, "coverage_sites": 4, "sites": op_values,
                                      "authority": "PARTIAL_COVERAGE_COMMON_BOUNDARY"},
        "FACILITY_INCOMING_POWER_SET": {"total_MW": None, "coverage_sites": 0},
        "MVA_ONLY_SET": {"total_MVA": None, "reason": "heterogeneous component/facility MVA values are not summed into MW"},
        "twelve_site_common_boundary_complete": False,
        "primary_realworld_AIDC_numerator_MW": None,
        "diagnostic_partial_operating_capacity_MW": op_total,
    }
    write_json("V20A_REALWORLD_AIDC_NUMERATOR_REVIEW.json", numerator)

    prior_packet = json.loads((OLD / "MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET.json").read_text(encoding="utf-8"))
    denominators = prior_packet["April_denominator_variants"]
    denom = {
        "artifact_id": "V20A_HOST_GRID_DENOMINATOR_REVIEW_V1",
        "unique_host_rule": True, "host_count": len(prior_packet["unique_host_set"]),
        "candidates": denominators,
        "primary_candidate_id": "D_APRIL_2025_FORECAST_PEAK_MW",
        "primary_candidate_reason": "100% unique-host coverage, MW demand boundary, April-2025-applicable forecast vintage",
        "primary_candidate_value_MW": 567.9513000000001,
        "firm_normal_caveat": "75% host coverage; sensitivity only",
        "MVA_to_MW_rule": "Only prior rows with explicitly documented source PF are retained; no new conversion.",
        "grid_benefit_based_selection_calls": 0,
    }
    write_json("V20A_HOST_GRID_DENOMINATOR_REVIEW.json", denom)

    ieee = json.loads((OLD / "IEEE123_CURRENT_AIDC_SCALE_INVENTORY.json").read_text(encoding="utf-8"))
    d_ieee = ieee["background_operational_MW"]["peak"]
    diagnostic = {
        "LOW": {"denominator": "D_APRIL_NORMAL_MW", "denominator_MW": 804.2664},
        "PRIMARY": {"denominator": "D_APRIL_2025_FORECAST_PEAK_MW", "denominator_MW": 567.9513},
        "HIGH": {"denominator": "D_APRIL_FIRM_MW", "denominator_MW": 531.9662},
    }
    for v in diagnostic.values():
        v["partial_operating_capacity_numerator_MW"] = op_total
        v["rho"] = op_total / v["denominator_MW"]
        v["IEEE123_background_peak_MW"] = d_ieee
        v["IEEE123_equivalent_AIDC_MW"] = v["rho"] * d_ieee
        v["authority"] = "PARTIAL_COVERAGE_DIAGNOSTIC_NOT_FINAL_SCALE"
    scale = {
        "artifact_id": "V20A_IEEE123_EQUIVALENT_SCALE_CANDIDATES_V1",
        "final_scale": None, "classification": "A4_BOUNDARY_HETEROGENEITY_BLOCKS_FINAL_SCALE",
        "diagnostic_candidates": diagnostic, "target_value_fitting": False,
        "prior_0_71_0_90_1_21_targets_used": False,
    }
    write_json("V20A_IEEE123_EQUIVALENT_SCALE_CANDIDATES.json", scale)

    partial_weights = {name: value / op_total for name, value in op_values.items()}
    all_sites = [s["site_name"] for s in sites]
    weights = {
        "artifact_id": "V20A_SITE_SPECIFIC_POWER_WEIGHT_AUTHORITY_V1",
        "FINAL_SITE_WEIGHT": {name: None for name in all_sites},
        "DIRECT_AUTHORITY_SITE_WEIGHT": {name: None for name in all_sites},
        "PARTIAL_COVERAGE_WEIGHT": {name: partial_weights.get(name) for name in all_sites},
        "ASSUMPTION_SENSITIVITY_WEIGHT": None,
        "reason": "12/12 common-boundary direct site MW not available",
    }
    write_json("V20A_SITE_SPECIFIC_POWER_WEIGHT_AUTHORITY.json", weights)
    write_json("V20A_SITE_GPU_WEIGHT_AUTHORITY_GAP.json", {
        "artifact_id": "V20A_SITE_GPU_WEIGHT_AUTHORITY_GAP_V1",
        "GPU_weight": {name: None for name in all_sites},
        "GPU_weight_authority_class": "NOT_IDENTIFIABLE",
        "power_weight_equals_GPU_weight_assumption_count": 0,
        "existing_spatial_allocation_role": "ENGINEERING_GPU_ALLOCATION_ONLY",
        "systemwide_GPU_h_facility_scale_multiplier_calls": 0,
    })

    pcc = {
        "artifact_id": "V20A_PCC_TRANSFORMER_INTERFACE_AUDIT_V1", "sites": [],
        "source": "dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_CONTRACT_V2.json",
    }
    for i, name in enumerate(all_sites, 1):
        pcc["sites"].append({"site_id": f"AIDC{i:02d}", "site_name": name,
                             "modeled_transformer_kVA": 1500.0, "PCC_limit_kVA": 1500.0,
                             "PF_assumption": None, "modeled_load_peak_MW": None,
                             "REAL_DNSP_RATING": False,
                             "authority": "FROZEN_SYNTHETIC_ENGINEERING_PCC_SCENARIO"})
    pcc["rating_adjustment_calls"] = 0
    write_json("V20A_PCC_TRANSFORMER_INTERFACE_AUDIT.json", pcc)

    review = {
        "artifact_id": "V20A_FINAL_SCALE_REVIEW_V1", "classification": "A4_BOUNDARY_HETEROGENEITY_BLOCKS_FINAL_SCALE",
        "SITE_SCALE_AUTHORITY_READY": False, "final_realworld_numerator_MW": None,
        "final_model_AIDC_peak_MW": None, "final_site_weights": None,
        "partial_common_boundary": {"boundary": "OPERATING_CAPACITY", "sites": 4, "MW": op_total},
        "diagnostic_candidates": diagnostic,
        "unresolved": ["No direct/common IT MW for 12/12 sites", "No actual DNSP interconnection rating per site",
                       "No site-specific GPU capacity authority", "IBM April-2025 operation unresolved"],
        "firewall": harmonization | {"grid_benefit_based_scale_selection_count": 0},
    }
    write_json("V20A_FINAL_SCALE_REVIEW.json", review)
    lines = ["# V20A Melbourne 12-site scale review", "", "## 결론", "",
             "**A4 — BOUNDARY_HETEROGENEITY_BLOCKS_FINAL_SCALE**", "",
             "12개 시설 중 동일한 `OPERATING_CAPACITY` 경계로 확보된 곳은 4개(합계 106.5 MW)뿐이다. 이는 부분 범위 진단이며 12개 전체의 IT MW가 아니다.", "",
             "서로 다른 IT/운영/시설/인입/MVA/발전기 경계를 섞지 않았고, 미확인 값을 0으로 채우지 않았다. 따라서 최종 site weight와 최종 IEEE123 AIDC scale은 null이다.", "",
             "LOW/PRIMARY/HIGH 수치는 모두 부분 범위 산술 진단이며 최종 규모 권한이 아니다."]
    (OUT / "V20A_FINAL_SCALE_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
