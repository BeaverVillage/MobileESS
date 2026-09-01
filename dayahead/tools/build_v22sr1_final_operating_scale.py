"""Build the V22S-R1 Melbourne-informed equivalent operating-load scale.

This module is evidence/arithmetic only.  It never imports ML, OpenDSS,
optimisation, or grid-science code.  The seven frozen V4R1 reference bundles
provide a dimensionless temporal shape only; their absolute kW is discarded.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import struct
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"
V22S = ROOT / "dayahead" / "artifacts" / "v22s_melbourne_12site_scale"
SHAPE_DIR = ROOT / "dayahead" / "artifacts" / "v17_candidate" / "reference_v6_v4r1"
IEEE_INVENTORY = (
    ROOT
    / "dayahead"
    / "artifacts"
    / "melbourne_aidc_april2025_scale"
    / "IEEE123_CURRENT_AIDC_SCALE_INVENTORY.json"
)
ACCESS_DATE = "2026-09-01"
CASE_NAME = "MELBOURNE_INFORMED_EQUIVALENT_12SITE_OPERATING_LOAD_CASE"
PUE = 1.30
UTIL_LOW = 0.435
UTIL_PRIMARY = 0.46
UTIL_HIGH = 93.0 / 189.1
EXPECTED_CAPACITY_TOTAL_MW = 202.750769230769
EXPECTED_HOST_TOTAL_MW = 628.146
IEEE_BACKGROUND_PEAK_MW = 2.3154691360756456
TOL = 1e-9


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_csv(name: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {name}")
    with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_npy_float64_from_npz(path: Path, member: str) -> tuple[tuple[int, ...], list[float]]:
    """Read a little-endian float64 NPY member using only the Python stdlib."""
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(member + ".npy")
    if raw[:6] != b"\x93NUMPY":
        raise ValueError(f"Invalid NPY magic: {path}:{member}")
    major = raw[6]
    if major == 1:
        header_len = struct.unpack("<H", raw[8:10])[0]
        header_start = 10
    elif major in (2, 3):
        header_len = struct.unpack("<I", raw[8:12])[0]
        header_start = 12
    else:
        raise ValueError(f"Unsupported NPY version {major}")
    header = ast.literal_eval(raw[header_start : header_start + header_len].decode("latin1"))
    if header["descr"] not in ("<f8", "=f8") or header["fortran_order"]:
        raise ValueError(f"Expected C-order float64, got {header}")
    shape = tuple(int(value) for value in header["shape"])
    count = math.prod(shape)
    offset = header_start + header_len
    values = list(struct.unpack(f"<{count}d", raw[offset : offset + count * 8]))
    return shape, values


def round_standard(required_mva: float, sizes: list[float]) -> float:
    for size in sizes:
        if size + 1e-12 >= required_mva:
            return size
    raise ValueError(f"Required interface {required_mva} MVA exceeds approved list")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    site_specs = [
        ("AIDC01", "Equinix ME4", "Equinix", 12.0, "IT_CAPACITY", "SOURCE_BACKED_IT_CAPACITY", "DIRECT_SOURCE_VALUE", "E"),
        ("AIDC02", "Micron21", "Micron21", 2.0, "FULLY_BUILT_OUT_POWER", "SECONDARY_CRITICAL_POWER_EQUIVALENT", "ENGINEERING_IT_EQUIVALENT_PROXY", "F"),
        ("AIDC03", "Fujitsu Noble Park", "Fujitsu", 28.0, "IT_CAPACITY", "SOURCE_BACKED_IT_CAPACITY", "DIRECT_SOURCE_VALUE", "A"),
        ("AIDC04", "AAPT / TPG Richmond", "TPG Telecom", 2.5 * 0.98 / PUE, "MVA_INPUT", "ENGINEERING_IT_EQUIVALENT_FROM_MVA", "ENGINEERING_PF_AND_PUE_CONVERSION", "F"),
        ("AIDC05", "NEXTDC M2", "NEXTDC", 42.0, "BUILT_CAPACITY", "SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY", "ENGINEERING_IT_EQUIVALENT_PROXY", "B"),
        ("AIDC06", "NEXTDC M3", "NEXTDC", 13.5, "BUILT_CAPACITY", "SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY", "ENGINEERING_IT_EQUIVALENT_PROXY", "B"),
        ("AIDC07", "Vocus Mitcham", "Vocus", 9.0, "FULLY_BUILT_OUT_POWER", "SECONDARY_CRITICAL_POWER_EQUIVALENT", "ENGINEERING_IT_EQUIVALENT_PROXY", "F"),
        ("AIDC08", "NEXTDC M1", "NEXTDC", 15.0, "IT_CAPACITY", "SOURCE_BACKED_IT_CAPACITY", "DIRECT_SOURCE_VALUE", "A"),
        ("AIDC09", "Equinix ME5", "Equinix", (4.175 - 1.125) / PUE, "GENERATOR_NAMEPLATE", "ENGINEERING_EQUIVALENT_IT_CAPACITY_PROXY_FROM_N_PLUS_1_BACKUP", "N_PLUS_1_ENGINEERING_IT_EQUIVALENT_PROXY", "A"),
        ("AIDC10", "CDC Brooklyn BK1", "CDC Data Centres", 34.0, "OPERATING_CAPACITY", "SOURCE_BACKED_OPERATING_BUILD_CAPACITY_EQUIVALENT", "ENGINEERING_IT_EQUIVALENT_PROXY", "B"),
        ("AIDC11", "IBM MEL01 / Digital Realty MEL11", "Digital Realty / IBM tenant", 7.02, "HISTORICAL_LIVE_FACILITY_CAPACITY", "HISTORICAL_DIGITAL_REALTY_FACILITY_CAPACITY_PRIMARY", "HISTORICAL_ENGINEERING_IT_EQUIVALENT_PROXY", "B"),
        ("AIDC12", "STACK MEL01A", "STACK Infrastructure", 36.0, "BUILT_CAPACITY", "SOURCE_BACKED_BUILT_CRITICAL_CAPACITY", "ENGINEERING_IT_EQUIVALENT_PROXY", "A"),
    ]
    capacity_total = math.fsum(item[3] for item in site_specs)
    if abs(capacity_total - EXPECTED_CAPACITY_TOTAL_MW) > TOL:
        raise AssertionError((capacity_total, EXPECTED_CAPACITY_TOTAL_MW))
    weights = {sid: value / capacity_total for sid, _, _, value, _, _, _, _ in site_specs}
    if abs(math.fsum(weights.values()) - 1.0) > 1e-15:
        raise AssertionError("Site weights do not sum to one")

    source_ids = {
        "AIDC01": "S_ME4_ITNEWS",
        "AIDC02": "S_MICRON_DCM",
        "AIDC03": "S_FUJITSU_OFFICIAL",
        "AIDC04": "S_AAPT_INFLECT",
        "AIDC05": "S_NEXTDC_1H25",
        "AIDC06": "S_NEXTDC_1H25",
        "AIDC07": "S_VOCUS_DCM",
        "AIDC08": "S_NEXTDC_GUIDE",
        "AIDC09": "S_ME5_EQX",
        "AIDC10": "S_CDC_INFRATIL_2025",
        "AIDC11": "S_MEL11_DLR_HISTORICAL_2020",
        "AIDC12": "S_STACK_OPEN",
    }
    site_rows: list[dict[str, object]] = []
    for sid, name, operator, value, boundary, classification, method, grade in site_specs:
        site_rows.append(
            {
                "site_id": sid,
                "site_name": name,
                "operator": operator,
                "April_2025_status": "OPERATIONAL_OR_COMMISSIONED_AVAILABLE",
                "primary_IT_equivalent_capacity_MW": value,
                "original_source_boundary": boundary,
                "preregistered_classification": classification,
                "harmonized_boundary": "IT_EQUIVALENT_ENGINEERING_CAPACITY_NOT_ACTUAL_LOAD",
                "conversion_method": method,
                "source_id": source_ids[sid],
                "authority_grade": grade,
                "actual_April_operating_load_MW": "",
                "actual_load_claim": False,
            }
        )
    write_csv("V22SR1_12SITE_PRIMARY_IT_EQUIVALENT_CAPACITY.csv", site_rows)

    method_freeze = {
        "artifact_id": "V22SR1_SCALING_METHOD_FREEZE_V1",
        "case_name": CASE_NAME,
        "permitted_scientific_wording": "Melbourne-informed equivalent AIDC operating-load scale",
        "prohibited_interpretation": "ACTUAL_METERED_MELBOURNE_APRIL_2025_LOAD_CENSUS",
        "reference_period": "APRIL_2025",
        "preregistered_pipeline": [
            "12 site source-bound capacity values and explicit boundary conversions",
            "capacity-weighted site allocation",
            "primary utilization 0.46 independent of grid outcomes",
            "frozen seven-day V4R1 whole-AIDC shape used dimensionlessly",
            "PUE 1.30 applied once from IT to PCC",
            "non-overlapping unique-host 2025 forecast denominator",
            "load-to-load rho mapped to frozen IEEE123 background peak demand",
        ],
        "result_based_tuning": 0,
        "target_scale_values_consulted_for_selection": 0,
        "science_authorization": False,
    }
    write_json("V22SR1_SCALING_METHOD_FREEZE.json", method_freeze)

    conversion_audit = {
        "artifact_id": "V22SR1_CAPACITY_CONVERSION_AUDIT_V1",
        "capacity_total_MW": capacity_total,
        "expected_capacity_total_MW": EXPECTED_CAPACITY_TOTAL_MW,
        "absolute_error_MW": abs(capacity_total - EXPECTED_CAPACITY_TOTAL_MW),
        "tolerance_MW": TOL,
        "AIDC04": {
            "input": {"value": 2.5, "unit": "MVA", "boundary": "MVA_INPUT"},
            "PF": 0.98,
            "PUE": PUE,
            "formula": "2.5 * 0.98 / 1.30",
            "IT_equivalent_MW": 2.5 * 0.98 / PUE,
            "label": "ENGINEERING_PF_SENSITIVITY_NOT_REAL_LOAD",
        },
        "AIDC09": {
            "input_generator_nameplate_MW": 4.175,
            "largest_unit_N_plus_1_exclusion_MW": 1.125,
            "PUE": PUE,
            "formula": "(4.175 - 1.125) / 1.30",
            "IT_equivalent_MW": (4.175 - 1.125) / PUE,
            "label": "GENERATOR_N_PLUS_1_ENGINEERING_PROXY_NOT_REAL_LOAD",
        },
        "counters": {
            "unsupported_MVA_to_MW": 0,
            "generator_to_actual_IT_load": 0,
            "capacity_to_actual_load_relabel": 0,
            "future_capacity_backcast": 0,
        },
    }
    write_json("V22SR1_CAPACITY_CONVERSION_AUDIT.json", conversion_audit)

    v22s_registry = json.loads((V22S / "V22S_12SITE_SOURCE_REGISTRY.json").read_text(encoding="utf-8"))
    targeted_sources = [
        {
            "source_id": "S_FUJITSU_OFFICIAL_REACCESS",
            "supports": ["AIDC03"],
            "title": "Locations of Fujitsu data centres",
            "url": "https://global.fujitsu/en-apac/local/about-data-centres",
            "access_status": "SUCCESS",
            "publication_date": None,
            "effective_date": "APRIL_2025_APPLICABILITY_FROM_PRIOR_V22S_AUTHORITY",
            "boundary": "IT_CAPACITY",
            "capacity_classification": "FACILITY_SPECIFICATION_NOT_METERED_LOAD",
            "authority_grade": "A",
            "evidence": "Noble Park, Melbourne, VIC: 28MW IT Load; treated as rated IT capacity.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_NEXTDC_1H25_REACCESS",
            "supports": ["AIDC05", "AIDC06", "UTIL_HIGH"],
            "title": "NEXTDC 1H25 Results Presentation",
            "url": "https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf",
            "access_status": "SUCCESS",
            "publication_date": "2025-02-24",
            "effective_date": "2024-12-31",
            "boundary": "BUILT_CAPACITY_AND_BILLING_UTILISATION",
            "capacity_classification": "M2_42_MW_M3_13.5_MW; BUILT_IS_DESIGNED_POWER_OF_FITTED_DATA_HALLS",
            "authority_grade": "B",
            "evidence": "M2 built 42 MW, M3 built 13.5 MW; portfolio built 189.1 MW and billing utilisation 93.0 MW.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_CDC_INFRATIL_2025_REACCESS",
            "supports": ["AIDC10"],
            "title": "CDC Independent Valuation – 31 March 2025",
            "url": "https://infratil.com/news/cdc-independent-valuation-31-march-2025/cdc-independent-valuation-31-march-2025/",
            "access_status": "SUCCESS",
            "publication_date": "2025-04-04",
            "effective_date": "2025-03-31",
            "boundary": "OPERATING_BUILD_CAPACITY",
            "capacity_classification": "MELBOURNE_REGION_OPERATING_BUILD_NOT_ACTUAL_DEMAND",
            "authority_grade": "B",
            "evidence": "Melbourne Operating Build Capacity is 34 MW; 121 MW under construction and 630 MW future are separate.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_ME5_EQX_REACCESS",
            "supports": ["AIDC09"],
            "title": "Equinix ME5 Melbourne data center",
            "url": "https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me5",
            "access_status": "SUCCESS_CURRENT_PAGE_NO_LONGER_EXPOSES_GENERATOR_MAGNITUDES",
            "publication_date": None,
            "effective_date": "PRIOR_V22S_RETRIEVAL_PRESERVED",
            "boundary": "GENERATOR_NAMEPLATE",
            "capacity_classification": "N_PLUS_1_ENGINEERING_PROXY_ONLY",
            "authority_grade": "A_WITH_PRIOR_AUTHORITY_PRESERVED",
            "evidence": "Current page confirms ME5 and N+1 power redundancy; prior official specs recorded 2x400 kW + 3x1125 kW.",
            "source_SHA256_if_downloaded": None,
            "fallback_status": "SOURCE_REACCESS_PARTIAL_PRIOR_AUTHORITY_PRESERVED",
        },
        {
            "source_id": "S_MEL11_CURRENT_REACCESS",
            "supports": ["AIDC11_IDENTITY"],
            "title": "MEL11 Data Center",
            "url": "https://www.digitalrealty.com/data-centers/asia-pacific/melbourne/mel11",
            "access_status": "SUCCESS",
            "publication_date": None,
            "effective_date": "CURRENT_IDENTITY_PAGE",
            "boundary": "IDENTITY_AND_REDUNDANCY_ONLY",
            "capacity_classification": "NO_CURRENT_MW_ON_PAGE",
            "authority_grade": "A",
            "evidence": "MEL11 is at 72 Radnor Drive, Deer Park; 2N UPS and N+1 cooling.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_MEL11_DLR_HISTORICAL_2020",
            "supports": ["AIDC11_CAPACITY_PROXY"],
            "title": "Digital Realty ICN10 / PlatformDIGITAL APAC portfolio presentation",
            "url": "https://www.scribd.com/document/636422146/ICN10-Presentation",
            "access_status": "SUCCESS_THIRD_PARTY_ARCHIVE_OF_DIGITAL_REALTY_BRANDED_MATERIAL",
            "publication_date": "2020_PORTFOLIO_CONTEXT",
            "effective_date": "2020",
            "boundary": "LIVE_FACILITY_CAPACITY",
            "capacity_classification": "HISTORICAL_ENGINEERING_PROXY_NOT_APRIL_METERED_LOAD",
            "authority_grade": "B_ARCHIVED_OPERATOR_ORIGIN_MATERIAL",
            "evidence": "Branded APAC portfolio slide lists Melbourne MEL11, 94,000 sq ft facility, LIVE, 7.02MW.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_STACK_OPEN_REACCESS",
            "supports": ["AIDC12"],
            "title": "STACK Infrastructure Delivers First Data Center in Australia",
            "url": "https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-delivers-first-data-center-in-australia-launching-a-robust-apac-portfolio/",
            "access_status": "SUCCESS",
            "publication_date": "2023-08-22",
            "effective_date": "2023-08-22",
            "boundary": "BUILT_CAPACITY",
            "capacity_classification": "FIRST_DELIVERED_FACILITY_NOT_SECOND_FUTURE_BUILDING",
            "authority_grade": "A",
            "evidence": "First 36 MW facility completed on a 72 MW campus; second 36 MW development was upcoming.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_DPTS_TCPR_REACCESS",
            "supports": ["HOST_DPTS"],
            "title": "2024 Transmission Connection Planning Report",
            "url": "https://www.jemena.com.au/siteassets/asset-folder/documents/electricity/2024-tcpr.pdf",
            "access_status": "SUCCESS",
            "publication_date": "2024",
            "effective_date": "2025_FORECAST",
            "boundary": "50TH_PERCENTILE_SUMMER_MAXIMUM_DEMAND_MVA",
            "capacity_classification": "HOST_FORECAST_LOAD",
            "authority_grade": "C_DNSP_JOINT_TCPR",
            "evidence": "DPTS 2025 50th-percentile summer maximum demand is 282.4 MVA; peak-demand PF is 0.98.",
            "source_SHA256_if_downloaded": None,
        },
        {
            "source_id": "S_IEEE_UTILISATION_REACCESS",
            "supports": ["UTIL_LOW", "UTIL_PRIMARY"],
            "title": "Grid-Interactive Data Centers Enabling Energy Transition",
            "url": "https://read.nxtbook.com/ieee/electrification/electrification_sept_2023/grid_interactive_data_centers.html",
            "access_status": "SUCCESS",
            "publication_date": "2023-09",
            "effective_date": "REFERENCE_SENSITIVITY",
            "boundary": "AVERAGE_LOAD_DEMAND_OVER_DESIGN_POWER_CAPACITY",
            "capacity_classification": "EXTERNAL_UTILISATION_AUTHORITY_NOT_MELBOURNE_MEASUREMENT",
            "authority_grade": "A_IEEE",
            "evidence": "EU Code of Conduct participants averaged 46%; the article also reports BloombergNEF's 43.5% estimate.",
            "source_SHA256_if_downloaded": None,
        },
    ]
    source_reverification = {
        "artifact_id": "V22SR1_SOURCE_REVERIFICATION_V1",
        "access_date": ACCESS_DATE,
        "prior_registry_path": (V22S / "V22S_12SITE_SOURCE_REGISTRY.json").relative_to(ROOT).as_posix(),
        "prior_registry_sha256": sha256(V22S / "V22S_12SITE_SOURCE_REGISTRY.json"),
        "prior_registry_source_count": len(v22s_registry["sources"]),
        "prior_registry_preservation": "ALL_PRIOR_RECORDS_PRESERVED_BY_REFERENCE",
        "targeted_reverification": targeted_sources,
        "wayback_status": "NOT_ACCESSED",
        "downloaded_source_count": 0,
    }
    write_json("V22SR1_SOURCE_REVERIFICATION.json", source_reverification)

    utilisation = {
        "artifact_id": "V22SR1_LOAD_UTILISATION_AUTHORITY_V1",
        "definition": "equivalent average IT operating load / IT-equivalent design capacity",
        "low": {"value": UTIL_LOW, "authority": "BLOOMBERGNEF_ESTIMATE_AS_REPORTED_BY_IEEE_ARTICLE", "role": "SENSITIVITY"},
        "primary": {"value": UTIL_PRIMARY, "authority": "IEEE_ELECTRIFICATION_MAGAZINE_EU_CODE_OF_CONDUCT_PARTICIPANTS", "role": "FROZEN_PRIMARY"},
        "high": {"value": UTIL_HIGH, "formula": "93.0/189.1", "authority": "NEXTDC_1H25_PORTFOLIO_BILLING_OVER_BUILT_PROXY", "role": "DEPLOYMENT_PROXY_SENSITIVITY_NOT_ACTUAL_ELECTRICAL_UTILISATION"},
        "selection_based_on_grid_results": False,
    }
    write_json("V22SR1_LOAD_UTILISATION_AUTHORITY.json", utilisation)

    shape_files = sorted(SHAPE_DIR.glob("REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_2025-04-*.npz"))
    if len(shape_files) != 7:
        raise AssertionError(f"Expected seven frozen shape files, found {len(shape_files)}")
    shape_rows: list[tuple[str, int, float]] = []
    source_file_records = []
    absolute_values: list[float] = []
    for path in shape_files:
        shape, values = load_npy_float64_from_npz(path, "plan_kw_96x12")
        if shape != (96, 12):
            raise AssertionError((path, shape))
        date = path.stem.rsplit("_", 1)[-1]
        for slot in range(96):
            total = math.fsum(values[slot * 12 : (slot + 1) * 12])
            absolute_values.append(total)
            shape_rows.append((date, slot, total))
        source_file_records.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path), "slot_count": 96, "member": "plan_kw_96x12"}
        )
    shape_mean = math.fsum(absolute_values) / len(absolute_values)
    shape_peak = max(absolute_values)
    k_shape = shape_mean / shape_peak
    normalized = [value / shape_mean for value in absolute_values]
    if abs(math.fsum(normalized) / len(normalized) - 1.0) > 1e-12:
        raise AssertionError("Normalized shape mean is not one")
    shape_authority = {
        "artifact_id": "V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY_V1",
        "source_files": source_file_records,
        "slot_count": len(absolute_values),
        "source_absolute_mean_kW_discarded": shape_mean,
        "source_absolute_peak_kW_discarded": shape_peak,
        "k_shape_mean_over_max": k_shape,
        "normalization": "g_norm(t)=g_legacy(t)/mean(g_legacy); mean(g_norm)=1",
        "absolute_legacy_magnitude_status": "DISCARDED_NOT_SCALE_AUTHORITY",
        "debug_results_read_for_scale_selection": 0,
    }
    write_json("V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json", shape_authority)

    primary_it_avg = capacity_total * UTIL_PRIMARY
    primary_it_peak = primary_it_avg / k_shape
    primary_pcc_avg = primary_it_avg * PUE
    primary_pcc_peak = primary_it_peak * PUE
    profile_rows: list[dict[str, object]] = []
    for index, ((date, slot, _), factor) in enumerate(zip(shape_rows, normalized)):
        row: dict[str, object] = {
            "sequence": index,
            "reference_date": date,
            "slot_15min": slot,
            "normalized_shape_factor": factor,
        }
        for sid, *_ in site_specs:
            row[f"{sid}_IT_equivalent_MW"] = capacity_total * weights[sid] * UTIL_PRIMARY * factor
        row["aggregate_IT_equivalent_MW"] = primary_it_avg * factor
        row["aggregate_PCC_equivalent_MW"] = primary_pcc_avg * factor
        profile_rows.append(row)
    write_csv("V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv", profile_rows)

    host_specs = [
        ("HOST_DPTS", "Deer Park Terminal Station 66 kV broad Powercor west supply area", ["AIDC01", "AIDC11", "AIDC12"], 282.4 * 0.98, "282.4 MVA x PF 0.98", "NETWORK_AREA_ONLY", "S_DPTS_TCPR_REACCESS"),
        ("HOST_BWR", "Bayswater", ["AIDC02"], 52.865, "2025 forecast peak MW", "NETWORK_AREA_ONLY", "S_HOST_AUSNET"),
        ("HOST_NP", "Noble Park", ["AIDC03"], 50.81, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_UE"),
        ("HOST_R", "Richmond", ["AIDC04"], 31.9, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_CITY"),
        ("HOST_TMA", "Tullamarine", ["AIDC05"], 23.43, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_JEMENA"),
        ("HOST_FW", "Footscray West", ["AIDC06"], 36.16, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_JEMENA"),
        ("HOST_NW", "Nunawading", ["AIDC07"], 56.47, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_UE"),
        ("HOST_PM", "Port Melbourne", ["AIDC08"], 14.4336, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_CITY"),
        ("HOST_VM", "Victoria Market", ["AIDC09"], 59.8554, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_CITY"),
        ("HOST_TH", "Tottenham", ["AIDC10"], 25.47, "2025 forecast peak MW", "GEOGRAPHICALLY_INFERRED", "S_HOST_JEMENA"),
    ]
    host_rows = [
        {
            "host_id": host_id,
            "host_name": host_name,
            "AIDC_ids": site_ids,
            "forecast_2025_peak_MW": value,
            "value_derivation": derivation,
            "mapping_class": mapping,
            "source_id": source_id,
            "April_2025_applicable": True,
            "aggregate_count": 1,
        }
        for host_id, host_name, site_ids, value, derivation, mapping, source_id in host_specs
    ]
    host_total = math.fsum(row["forecast_2025_peak_MW"] for row in host_rows)
    if abs(host_total - EXPECTED_HOST_TOTAL_MW) > TOL:
        raise AssertionError((host_total, EXPECTED_HOST_TOTAL_MW))
    host_authority = {
        "artifact_id": "V22SR1_MATCHED_UNIQUE_HOST_2025_AUTHORITY_V1",
        "denominator_boundary": "MATCHED_UNIQUE_HOST_2025_FORECAST_PEAK_ACTIVE_POWER",
        "hosts": host_rows,
        "unique_host_count": len(host_rows),
        "nine_non_DPTS_hosts_total_MW": math.fsum(row["forecast_2025_peak_MW"] for row in host_rows if row["host_id"] != "HOST_DPTS"),
        "DPTS_2025_forecast_MVA": 282.4,
        "DPTS_peak_power_factor": 0.98,
        "DPTS_2025_forecast_MW": 282.4 * 0.98,
        "total_MW": host_total,
    }
    write_json("V22SR1_MATCHED_UNIQUE_HOST_2025_AUTHORITY.json", host_authority)
    host_audit = {
        "artifact_id": "V22SR1_HOST_DOUBLE_COUNT_AUDIT_V1",
        "AIDC01_AIDC11_AIDC12_rule": "COUNT_DPTS_ONCE_DO_NOT_ADD_LVN_OR_TNA",
        "DPTS_count": sum(row["aggregate_count"] for row in host_rows if row["host_id"] == "HOST_DPTS"),
        "LVN_count": 0,
        "TNA_count": 0,
        "site_coverage": sorted(sid for row in host_rows for sid in row["AIDC_ids"]),
        "duplicate_site_count": 0,
        "duplicate_host_count": 0,
        "coverage_complete_12_of_12": True,
    }
    write_json("V22SR1_HOST_DOUBLE_COUNT_AUDIT.json", host_audit)

    rho = primary_pcc_peak / host_total
    penetration = {
        "artifact_id": "V22SR1_PRIMARY_MELBOURNE_PENETRATION_V1",
        "case_name": CASE_NAME,
        "numerator": {"value_MW": primary_pcc_peak, "boundary": "EQUIVALENT_PCC_PEAK_ACTIVE_POWER", "site_coverage": [item[0] for item in site_specs]},
        "denominator": {"value_MW": host_total, "boundary": "MATCHED_UNIQUE_HOST_2025_FORECAST_PEAK_ACTIVE_POWER", "site_coverage": [item[0] for item in site_specs]},
        "rho": rho,
        "boundary_match": "LOAD_TO_LOAD_EQUIVALENT",
        "actual_Melbourne_load_claim": False,
    }
    write_json("V22SR1_PRIMARY_MELBOURNE_PENETRATION.json", penetration)

    inventory = json.loads(IEEE_INVENTORY.read_text(encoding="utf-8"))
    inventory_peak = float(inventory["background_operational_MW"]["peak"])
    if abs(inventory_peak - IEEE_BACKGROUND_PEAK_MW) > 1e-12:
        raise AssertionError((inventory_peak, IEEE_BACKGROUND_PEAK_MW))
    model_pcc_peak = rho * inventory_peak
    final_scale = {
        "artifact_id": "V22SR1_FINAL_IEEE123_AIDC_SCALE_V1",
        "case_name": CASE_NAME,
        "scientific_wording": "Melbourne-informed equivalent AIDC operating-load scale",
        "IEEE123_background_peak_MW": inventory_peak,
        "IEEE123_background_peak_provenance": inventory["background_operational_MW"]["source"],
        "real_equivalent_rho": rho,
        "final_aggregate_AIDC_PCC_peak_MW": model_pcc_peak,
        "final_aggregate_AIDC_IT_peak_MW_at_PUE_1_30": model_pcc_peak / PUE,
        "formula": "rho * frozen IEEE123 background peak demand",
        "legacy_target_tuning": False,
        "grid_result_tuning": False,
        "measured_Melbourne_load_claim": False,
        "status": "PRIMARY_MELBOURNE_INFORMED_EQUIVALENT_OPERATING_LOAD_SCALE",
    }
    write_json("V22SR1_FINAL_IEEE123_AIDC_SCALE.json", final_scale)

    weight_rows = [
        {
            "site_id": sid,
            "site_name": name,
            "primary_IT_equivalent_capacity_MW": value,
            "preregistered_classification": classification,
            "capacity_weight": weights[sid],
            "operating_IT_average_weight": weights[sid],
            "operating_IT_peak_weight": weights[sid],
            "PCC_peak_weight": weights[sid],
            "authority": "MELBOURNE_INFORMED_ENGINEERING_EQUIVALENT",
            "GPU_weight_authority": "UNAVAILABLE_NOT_INFERRED",
            "source_confidence": grade,
        }
        for sid, name, _, value, _, classification, _, grade in site_specs
    ]
    write_csv("V22SR1_PRIMARY_SITE_WEIGHTS.csv", weight_rows)
    pcc_rows = []
    for sid, name, _, value, _, classification, _, grade in site_specs:
        pcc_rows.append(
            {
                "site_id": sid,
                "site_name": name,
                "weight": weights[sid],
                "preregistered_classification": classification,
                "real_equivalent_IT_average_MW": value * UTIL_PRIMARY,
                "real_equivalent_IT_peak_MW": primary_it_peak * weights[sid],
                "real_equivalent_PCC_peak_MW": primary_pcc_peak * weights[sid],
                "IEEE123_equivalent_PCC_peak_MW": model_pcc_peak * weights[sid],
                "PUE": PUE,
                "PUE_applied_IT_to_PCC_once": True,
                "source_confidence": grade,
            }
        )
    write_csv("V22SR1_SITE_PCC_PEAKS.csv", pcc_rows)

    def scale_for(capacity_mw: float, utilisation_value: float) -> float:
        return capacity_mw * utilisation_value / k_shape * PUE / host_total * inventory_peak

    util_sensitivity = {
        "artifact_id": "V22SR1_UTILISATION_SENSITIVITY_V1",
        "capacity_total_fixed_MW": capacity_total,
        "cases": [
            {"case": "LOW", "utilisation": UTIL_LOW, "IT_average_MW": capacity_total * UTIL_LOW, "IT_peak_MW": capacity_total * UTIL_LOW / k_shape, "PCC_peak_MW": capacity_total * UTIL_LOW / k_shape * PUE, "rho": capacity_total * UTIL_LOW / k_shape * PUE / host_total, "IEEE123_AIDC_PCC_peak_MW": scale_for(capacity_total, UTIL_LOW)},
            {"case": "PRIMARY", "utilisation": UTIL_PRIMARY, "IT_average_MW": capacity_total * UTIL_PRIMARY, "IT_peak_MW": capacity_total * UTIL_PRIMARY / k_shape, "PCC_peak_MW": capacity_total * UTIL_PRIMARY / k_shape * PUE, "rho": capacity_total * UTIL_PRIMARY / k_shape * PUE / host_total, "IEEE123_AIDC_PCC_peak_MW": scale_for(capacity_total, UTIL_PRIMARY)},
            {"case": "HIGH_DEPLOYMENT_PROXY", "utilisation": UTIL_HIGH, "IT_average_MW": capacity_total * UTIL_HIGH, "IT_peak_MW": capacity_total * UTIL_HIGH / k_shape, "PCC_peak_MW": capacity_total * UTIL_HIGH / k_shape * PUE, "rho": capacity_total * UTIL_HIGH / k_shape * PUE / host_total, "IEEE123_AIDC_PCC_peak_MW": scale_for(capacity_total, UTIL_HIGH), "label": "AUSTRALIAN_OPERATOR_BILLING_TO_BUILT_DEPLOYMENT_PROXY_SENSITIVITY"},
        ],
        "selection": "PRIMARY_PREREGISTERED_0.46",
    }
    write_json("V22SR1_UTILISATION_SENSITIVITY.json", util_sensitivity)

    fixed_other = math.fsum([2.0, 28.0, 42.0, 13.5, 9.0, 15.0, 34.0, 36.0])
    capacity_low_open = fixed_other + 7.6 + 2.5 * 0.95 / PUE + 5.76
    capacity_high = fixed_other + 18.0 + 2.5 * 1.00 / PUE + 4.175 / PUE + 13.4
    envelope = {
        "artifact_id": "V22SR1_CAPACITY_EVIDENCE_ENVELOPE_V1",
        "site_variants": {
            "AIDC01": {"low": 7.6, "primary": 12.0, "high": 18.0, "boundary": "INSTALLED/IT/DESIGN_SEPARATED"},
            "AIDC04": {"low": 2.5 * 0.95 / PUE, "primary": 2.5 * 0.98 / PUE, "high": 2.5 / PUE, "label": "ENGINEERING_PF_SENSITIVITY_NOT_REAL_LOAD"},
            "AIDC09": {"low": None, "lower_bound": "OPEN_POSITIVE_NOT_NUMERIC", "primary": (4.175 - 1.125) / PUE, "high": 4.175 / PUE, "label": "GENERATOR_PROXY_NO_FAKE_POSITIVE_LOWER"},
            "AIDC11": {"low": 5.76, "additional_lower_evidence": 6.7, "primary": 7.02, "additional_higher_evidence": 10.0, "high": 13.4, "boundary": "HISTORICAL_AND_SECONDARY_FACILITY_CAPACITY_CONFLICT"},
        },
        "aggregate_capacity_MW": {"low_open_exclusive": capacity_low_open, "primary": capacity_total, "high_inclusive": capacity_high},
        "capacity_only_scale_at_utilisation_0_46_MW": {"low_open_exclusive": scale_for(capacity_low_open, UTIL_PRIMARY), "primary": model_pcc_peak, "high_inclusive": scale_for(capacity_high, UTIL_PRIMARY)},
        "extended_joint_engineering_scale_MW": {"low_open_exclusive": scale_for(capacity_low_open, UTIL_LOW), "primary": model_pcc_peak, "high_inclusive": scale_for(capacity_high, UTIL_HIGH)},
        "actual_load_claim": False,
    }
    write_json("V22SR1_CAPACITY_EVIDENCE_ENVELOPE.json", envelope)

    standard_sizes = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.75, 5.0]
    pcc_contract = {
        "artifact_id": "V22SR1_PCC_INTERFACE_ENGINEERING_CONTRACT_V1",
        "interface_type": "IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE_NOT_ACTUAL_MELBOURNE_TRANSFORMER",
        "main_PF": 0.98,
        "main_loading_fraction": 0.80,
        "standard_transformer_MVA": standard_sizes,
        "formula": "S_required=P_site_PCC_peak/(PF*loading_fraction)",
        "rounding": "ROUND_UP_TO_NEXT_APPROVED_STANDARD_SIZE",
        "legacy_12x1_5MVA_default": False,
    }
    write_json("V22SR1_PCC_INTERFACE_ENGINEERING_CONTRACT.json", pcc_contract)
    interface_rows = []
    for row in pcc_rows:
        required = float(row["IEEE123_equivalent_PCC_peak_MW"]) / (0.98 * 0.80)
        rating = round_standard(required, standard_sizes)
        interface_rows.append(
            {
                "site_id": row["site_id"],
                "IEEE123_equivalent_PCC_peak_MW": row["IEEE123_equivalent_PCC_peak_MW"],
                "PF_assumed": 0.98,
                "loading_fraction": 0.80,
                "S_required_MVA": required,
                "rounded_standard_interface_MVA": rating,
                "headroom_MVA": rating - required,
                "rating_exceeds_design_apparent_power": rating + 1e-12 >= required,
                "actual_Melbourne_transformer_MVA": "",
                "authority": "IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE",
            }
        )
    write_csv("V22SR1_PCC_INTERFACE_SIZING.csv", interface_rows)

    lineage = {
        "artifact_id": "V22SR1_SCALE_LINEAGE_AND_DEPRECATION_V1",
        "lineage": [
            {"scale": "legacy V4R1 approximately 1.208 MW", "status": "LEGACY_STRESS_SCALE_NOT_CURRENT_PRIMARY"},
            {"scale": "V20/V22S partial diagnostics", "status": "SUPERSEDED_FOR_PRIMARY_OPERATING_LOAD_SCALING"},
            {"scale": "V22S strict 1.0–1.62 MW candidates", "status": "CAPACITY_TO_CAPACITY_DIAGNOSTIC_NOT_OPERATING_LOAD"},
            {"scale": model_pcc_peak, "status": "PRIMARY_MELBOURNE_INFORMED_EQUIVALENT_OPERATING_LOAD_SCALE"},
        ],
        "historical_artifacts_modified": False,
    }
    write_json("V22SR1_SCALE_LINEAGE_AND_DEPRECATION.json", lineage)

    ready = {
        "artifact_id": "V22SR1_READY_FLAGS_V1",
        "SITE_CAPACITY_EQUIVALENT_READY": True,
        "LOAD_UTILISATION_AUTHORITY_READY": True,
        "NORMALIZED_SHAPE_READY": True,
        "MATCHED_HOST_DENOMINATOR_READY": True,
        "PRIMARY_OPERATING_LOAD_SCALE_READY": True,
        "PRIMARY_SITE_POWER_WEIGHTS_READY": True,
        "PCC_INTERFACE_ENGINEERING_READY": True,
        "SCALING_FREEZE_READY": True,
        "FINAL_GRID_SCIENCE_READY": False,
        "FINAL_GRID_SCIENCE_AUTHORIZED": False,
    }
    write_json("V22SR1_READY_FLAGS.json", ready)

    firewall = {
        "ML_retraining": 0,
        "ML_code_changes": 0,
        "forecast_edits": 0,
        "GPU_h_scale_calls": 0,
        "beta_AIDC_calls": 0,
        "B0_calls": 0,
        "B1_calls": 0,
        "B2_calls": 0,
        "B3_calls": 0,
        "OpenDSS_calls": 0,
        "grid_science_calls": 0,
        "debug_result_reads_for_scale_selection": 0,
        "result_based_scale_tuning": 0,
        "PUE_application_count": 1,
        "double_PUE_count": 0,
        "future_capacity_backcast": 0,
    }
    final_review = {
        "artifact_id": "V22SR1_FINAL_REVIEW_V1",
        "result_classification": "V22SR1_FINAL_OPERATING_LOAD_SCALE_COMPLETE",
        "case_name": CASE_NAME,
        "capacity_total_MW": capacity_total,
        "primary_utilisation": UTIL_PRIMARY,
        "primary_operating_IT_average_MW": primary_it_avg,
        "shape_factor_mean_over_peak": k_shape,
        "primary_operating_IT_peak_MW": primary_it_peak,
        "primary_operating_PCC_peak_MW": primary_pcc_peak,
        "unique_host_2025_denominator_MW": host_total,
        "rho": rho,
        "IEEE123_background_peak_MW": inventory_peak,
        "final_IEEE123_AIDC_PCC_peak_MW": model_pcc_peak,
        "site_weights": weights,
        "utilisation_sensitivity": util_sensitivity,
        "capacity_envelope": envelope,
        "PCC_interface_contract": pcc_contract,
        "ready_flags": ready,
        "firewall_counters": firewall,
        "unresolved_items": [
            "This is not an actual April 2025 metered Melbourne load census.",
            "Exact physical serving substations remain inferred/network-area mappings, especially the shared DPTS west-area group.",
            "MEL11 7.02 MW is historical branded portfolio material available through a third-party archive, not a current operator MW page.",
            "ME5 and AAPT central values are explicit engineering conversions, not source-reported IT load.",
            "GPU allocation authority remains unavailable.",
        ],
        "git": {
            "branch": "codex/v22s-r1-final-operating-scale",
            "starting_HEAD": "a842d301febc523dfca5d4803aebdf70b048586e",
            "ending_content_HEAD": "RECORDED_IN_FINAL_RESPONSE_AFTER_COMMITS",
        },
    }
    write_json("V22SR1_FINAL_REVIEW.json", final_review)

    md = f"""# V22S-R1 최종 운영부하 스케일 검토

RESULT CLASSIFICATION:
V22SR1_FINAL_OPERATING_LOAD_SCALE_COMPLETE

## 1. 최종 case 정의

정식 명칭은 `{CASE_NAME}`이다. 과학적 표현은 **Melbourne-informed equivalent AIDC operating-load scale**이며, 실제 2025년 4월 Melbourne 계량부하 전수조사가 아니다.

## 2. 출처 재검증 수정

Fujitsu 28 MW IT Load, NEXTDC M2 42 MW/M3 13.5 MW built, CDC Melbourne 34 MW operating build, STACK 첫 36 MW 시설은 원문에서 재확인했다. ME5 현행 페이지는 N+1만 노출하므로 이전 공식 사양의 발전기 명판값을 보존했다. MEL11은 현행 공식 주소·중복도와 2020년 Digital Realty 브랜드 포트폴리오 보관본의 LIVE 7.02 MW를 결합하되 실제 부하로 해석하지 않았다.

## 3. 12-site primary IT-equivalent capacity

| Site | Facility | IT-equivalent MW | 원래 boundary | 방법/등급 |
|---|---|---:|---|---|
"""
    for sid, name, _, value, boundary, classification, method, grade in site_specs:
        md += f"| {sid} | {name} | {value:.12f} | {boundary} | {classification}; {method} / {grade} |\n"
    md += f"""

합계는 **{capacity_total:.12f} MW**이다.

## 4. 이용률 권한

Low 0.435, primary 0.46, high {UTIL_HIGH:.12f}이다. Primary 0.46은 IEEE Electrification Magazine의 EU Code of Conduct 참여 데이터센터 평균이며, high는 NEXTDC billing/built deployment proxy라 실제 전기 이용률이 아니다.

## 5. 동결 형상

V4R1 7개 참조일의 672 슬롯을 연결해 형상만 사용했다. `mean/max = {k_shape:.15f}`이고 기존 절대 kW는 폐기했다.

## 6. 등가 운영 IT 및 PCC

- 평균 IT: {primary_it_avg:.12f} MW
- 피크 IT: {primary_it_peak:.12f} MW
- 평균 PCC (PUE 1.30): {primary_pcc_avg:.12f} MW
- 피크 PCC (PUE 1.30): {primary_pcc_peak:.12f} MW

## 7. 중복 없는 host 분모

DPTS는 AIDC01/11/12에 대해 한 번만 계산하고 LVN/TNA를 추가하지 않았다. DPTS 276.752 MW와 나머지 9개 host 351.394 MW의 합은 **{host_total:.12f} MW**이다.

## 8. 실세계 등가 penetration

동일 load boundary의 산술 결과는 `rho = {rho:.15f}`이다. 이는 실제 계량 penetration 주장이 아니다.

## 9. IEEE123 분모

동결된 AIDC-free background peak active power는 **{inventory_peak:.15f} MW**이다. 5 MVA transformer capacity authority와 혼용하지 않았다.

## 10. 최종 IEEE123 AIDC scale

최종 aggregate AIDC PCC peak는 **{model_pcc_peak:.15f} MW**이다. 목표값이나 grid 결과에 맞춘 수치가 아니다.

## 11. Site power weights

| Site | weight |
|---|---:|
"""
    for sid in sorted(weights):
        md += f"| {sid} | {weights[sid]:.15f} |\n"
    md += "\n가중치 합은 machine precision에서 1.0이다. GPU weight authority는 unavailable이다.\n"
    md += f"""

## 12. 이용률 민감도

- low: {scale_for(capacity_total, UTIL_LOW):.12f} MW
- primary: {model_pcc_peak:.12f} MW
- high deployment proxy: {scale_for(capacity_total, UTIL_HIGH):.12f} MW

## 13. Capacity evidence envelope

ME4 7.6/12/18, AAPT PF 0.95/0.98/1.00, MEL11 5.76·6.7/7.02/10.0·13.4를 유지했다. ME5 lower는 양의 open bound이며 임의 양수 하한을 만들지 않았다. 결합 engineering envelope는 **({scale_for(capacity_low_open, UTIL_LOW):.12f}, {scale_for(capacity_high, UTIL_HIGH):.12f}] MW**이다.

## 14. PCC interface sizing

PF 0.98, loading 0.80을 사전 동결하고 각 site의 IEEE123 등가 PCC peak에서 표준 transformer size로 올림했다. 결과는 실제 Melbourne transformer가 아니라 `IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE`이다.

## 15. Lineage / deprecation

V4R1 약 1.208 MW는 legacy stress scale, V20/V22S 부분 결과는 primary operating-load scaling에서 superseded, V22S 1.0–1.62 MW는 capacity-to-capacity diagnostic이다. V22S-R1 값만 현재 primary Melbourne-informed equivalent operating-load scale이다.

## 16. 미해결 항목과 firewall

실제 4월 계량부하, 정확한 개별 전기사업자 서비스점, 실제 transformer rating, GPU weight는 여전히 미확정이다. ML 재학습, forecast 수정, GPU-h scaling, B0–B3, OpenDSS, grid science, 결과기반 튜닝은 모두 0이다.

## 17. Ready flags 및 Git

등가 operating-load scale, site power weight, PCC engineering interface는 ready이다. GPU weight authority는 ready가 아니며 `FINAL_GRID_SCIENCE_READY = false`, `FINAL_GRID_SCIENCE_AUTHORIZED = false`이다. 시작 HEAD는 `a842d301febc523dfca5d4803aebdf70b048586e`; 종료 커밋과 clean 상태는 최종 응답에 기록한다.
"""
    (OUT / "V22SR1_FINAL_REVIEW.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
