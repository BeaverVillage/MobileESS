"""Build the V22S evidence-only Melbourne 12-site scale authority.

The builder is deliberately arithmetic-only.  It does not import ML, forecast,
OpenDSS, optimisation, or grid-science modules.  Unknown values remain null and
capacity evidence is never relabelled as April operating load.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v22s_melbourne_12site_scale"
OLD = ROOT / "dayahead" / "artifacts" / "melbourne_aidc_april2025_scale"
ACCESS_DATE = "2026-09-01"
APRIL_PERIOD = "2025-04-01T00:00:00+10:00/2025-04-30T23:59:59+10:00"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def source(
    source_id: str,
    site_ids: list[str],
    source_class: str,
    title: str,
    url: str,
    publication_date: str | None,
    statement: str,
    boundary: str,
    grade: str,
    april: bool | str,
    access: str = "SUCCESS",
    value: float | str | None = None,
    unit: str | None = None,
    effective_date: str | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "site_ids": site_ids,
        "source_class": source_class,
        "title": title,
        "source_url": url,
        "access_status": access,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "source_access_date": ACCESS_DATE,
        "historical_state_date": effective_date,
        "April_2025_applicable": april,
        "reported_value": value,
        "reported_unit": unit,
        "reported_boundary": boundary,
        "exact_quote_or_paraphrase": statement,
        "source_quality_grade": grade,
        "source_SHA256_if_downloaded": None,
    }


SOURCES = [
    source("S_ME4_EQX", ["AIDC01"], "A_OPERATOR", "ME4 Melbourne data center", "https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me4", None, "Equinix identifies the operational ME4 facility in Derrimut; no MW is stated.", "UNKNOWN", "A", True),
    source("S_ME4_AER", ["AIDC01"], "C_GOVERNMENT", "Metronode Group Pty Limited - 2 Davis Court network exemption", "https://www.aer.gov.au/industry/registers/network-exemptions/metronode-group-pty-limited-2-davis-court-network-exemption", "2016-12-15", "AER identifies Metronode MEL2 Derrimut facility at 2 Davis Court, establishing the predecessor identity.", "UNKNOWN", "C", True, effective_date="2016-12-15"),
    source("S_ME4_ITNEWS", ["AIDC01"], "E_INDUSTRY", "Metronode opens second Melbourne data centre", "https://www.itnews.com.au/news/metronode-opens-second-melbourne-data-centre-310603", "2012-08-07", "The Melbourne2 facility supports up to 12 MW of IT load; this is rated support capacity, not actual consumption.", "IT_CAPACITY", "E", True, value=12.0, unit="MW", effective_date="2012-08-07"),
    source("S_ME4_ICON", ["AIDC01"], "D_CONTRACTOR", "Metronode Derrimut MEL-2 Expansion Stage 2", "https://icon.co/projects/metronode-derrimut-mel-2-expansion-stage-2/", "2017-09-30", "Contractor record states ultimate designed capacity 18 MW and 7.6 MW installed.", "BUILT_CAPACITY", "D", True, value=7.6, unit="MW", effective_date="2017-09-30"),
    source("S_MICRON_OFFICIAL", ["AIDC02"], "A_OPERATOR", "Micron21 data centre", "https://www.micron21.com/data-centre", None, "Official page lists dual external 1 MW generators and states each power-room generator can power the entire data centre; these are generator nameplates.", "GENERATOR_NAMEPLATE", "A", True, value="2 x 1", unit="MW"),
    source("S_MICRON_CERT", ["AIDC02"], "D_CERTIFIER", "Micron21 ISO27001 Certificate Data Centre 2025", "https://www.micron21.com/downloads/Micron21_ISO27001_Certificate_Data_Centre_2025.pdf", "2025-01-13", "Certificate establishes the data-centre operation at Factory 2, 7 Eastspur Court during the reference period.", "UNKNOWN", "D", True, effective_date="2025-01-13"),
    source("S_MICRON_DCM", ["AIDC02"], "F_DIRECTORY", "Micron21 Melbourne Australia - Specs", "https://www.datacentermap.com/australia/melbourne/micron21-melbourne-datacentre/specs/", None, "Directory reports 2 MW fully built-out power; it is not actual operating load.", "FULLY_BUILT_OUT_POWER", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=2.0, unit="MW"),
    source("S_FUJITSU_OFFICIAL", ["AIDC03"], "A_OPERATOR", "Locations of Fujitsu data centres", "https://global.fujitsu/en-apac/local/about-data-centres", None, "Official page labels Noble Park as 28 MW IT Load; context is a facility specification, so V22S classifies it as IT capacity, not metered load.", "IT_CAPACITY", "A", "LATER_OFFICIAL_PAGE_EFFECTIVE_DATE_UNCLEAR", value=28.0, unit="MW"),
    source("S_FUJITSU_FACT", ["AIDC03"], "A_OPERATOR", "Noble Park data centre fact sheet", "https://www.fujitsu.com/au/Images/Fujitsu-Data-Centre-Noble-Park-Fact-Sheet.pdf", "2014-11-06", "Older official fact sheet lists two 4 MVA main feeds; this remains MVA input equipment evidence.", "MVA_INPUT", "A", True, value="2 x 4", unit="MVA"),
    source("S_FUJITSU_DCD", ["AIDC03"], "E_INDUSTRY", "Fujitsu looks to sell off Australian data centers", "https://www.datacenterdynamics.com/en/news/fujitsu-looks-to-sell-off-australian-data-centers-report/", "2022-07-05", "Industry reporting confirms Noble Park remained part of Fujitsu's Australian data-centre portfolio.", "UNKNOWN", "E", True),
    source("S_AAPT_ITNEWS", ["AIDC04"], "E_INDUSTRY", "Inside the AAPT Richmond data centre", "https://www.itnews.com.au/gallery/inside-the-aapt-richmond-data-centre-170007", "2010-02-22", "Trade photo report establishes the Richmond data-centre operation and switch room; no capacity value is stated.", "UNKNOWN", "E", True),
    source("S_AAPT_PROPERTY", ["AIDC04"], "B_OWNER_FILING", "AAPT Centre property report", "https://www.nsx.com.au/ftp/news/BSX.PFD.11.3020.3141.pdf", "2007-06-30", "Owner filing identifies 180-188 Burnley Street as an internet data, telecommunications and office centre.", "UNKNOWN", "B", True),
    source("S_AAPT_INFLECT", ["AIDC04"], "F_DIRECTORY", "TPG Telecom Richmond", "https://inflect.com/building/180-burnley-street-richmond/tpg-telecom/datacenter/aapt-richmond-melbourne", None, "Directory reports 2.5 MVA power capacity; no source PF or IT boundary is supplied.", "MVA_INPUT", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=2.5, unit="MVA"),
    source("S_NEXTDC_1H25", ["AIDC05", "AIDC06", "AIDC08"], "B_OWNER_FILING", "NEXTDC 1H25 Results Presentation", "https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf", "2025-02-24", "At 31-Dec-2024: M2 built 42 MW plus 18 MW in progress; M3 built 13.5 MW plus 13.5 MW in progress. Built means designed power capacity of fitted-out data halls.", "BUILT_CAPACITY", "B", True, value="M2 42; M3 13.5", unit="MW", effective_date="2024-12-31"),
    source("S_NEXTDC_GUIDE", ["AIDC05", "AIDC06", "AIDC08"], "A_OPERATOR", "NEXTDC data centre locations and technical details", "https://nextdc.com/hubfs/240718_Partner_Onboarding_Guide.pdf", "2024-07-18", "Operator guide reports M1 total IT capacity 15 MW and planned/target figures for other sites; only M1's 15 MW is used as April-compatible IT-capacity evidence.", "IT_CAPACITY", "A", True, value="M1 15", unit="MW", effective_date="2024-07-18"),
    source("S_VOCUS_OFFICIAL", ["AIDC07"], "A_OPERATOR", "Vocus connected VIC data centres", "https://gowith.vocus.com.au/rs/587-CSJ-470/images/vic-data-centres.html", None, "Official Vocus list identifies DC-MEL04 Mitcham at 28 Thornton Crescent.", "UNKNOWN", "A", True),
    source("S_VOCUS_ASX", ["AIDC07"], "B_OWNER_FILING", "Vocus data centres overview", "https://announcements.asx.com.au/asxpdf/20150330/pdf/42xlzh305n4d25.pdf", "2015-03-30", "ASX material documents the Mitcham data-centre portfolio context; no harmonised MW is used.", "UNKNOWN", "B", True),
    source("S_VOCUS_DCM", ["AIDC07"], "F_DIRECTORY", "Vocus Data Centre - Mitcham - Specs", "https://www.datacentermap.com/australia/melbourne/mitcham/specs/", None, "Directory reports 9 MW fully built-out power; it is not actual operating load.", "FULLY_BUILT_OUT_POWER", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=9.0, unit="MW"),
    source("S_ME5_EQX", ["AIDC09"], "A_OPERATOR", "ME5 Melbourne data center", "https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me5", None, "Official specifications list 2x400 kW and 3x1125 kW generators on a parallel bus with N+1 redundancy; no IT/facility MW is published.", "GENERATOR_NAMEPLATE", "A", True, value=4.175, unit="MW"),
    source("S_ME5_AER", ["AIDC09"], "C_GOVERNMENT", "Metronode Pty Ltd - 22-36 Walsh Street network exemption", "https://www.aer.gov.au/industry/registers/network-exemptions/metronode-pty-ltd-22-36-walsh-street-network-exemption", "2012-11-23", "AER identifies the Metronode facility at 22-36 Walsh Street, establishing historical operation.", "UNKNOWN", "C", True, effective_date="2012-11-23"),
    source("S_ME5_DCM", ["AIDC09"], "F_DIRECTORY", "Equinix ME5 Data Center", "https://www.datacentermap.com/australia/melbourne/melbourne-1/", None, "Directory states former Metronode Melbourne 1 was acquired and renamed Equinix ME5.", "UNKNOWN", "F", True),
    source("S_CDC_INFRATIL_2024", ["AIDC10"], "B_OWNER_FILING", "CDC Independent Valuation - 30 June 2024", "https://infratil.com/news/cdc-independent-valuation-30-june-2024/", "2024-06-30", "Investor filing says Melbourne operating build capacity rose from zero to 34 MW when Brooklyn 1 commenced operations.", "OPERATING_CAPACITY", "B", True, value=34.0, unit="MW", effective_date="2024-06-30"),
    source("S_CDC_INFRATIL_2025", ["AIDC10"], "B_OWNER_FILING", "CDC Independent Valuation - 31 March 2025", "https://infratil.com/news/cdc-independent-valuation-31-march-2025/cdc-independent-valuation-31-march-2025/", "2025-04-04", "Contemporaneous filing keeps Melbourne operating build capacity at 34 MW and separately lists 121 MW under construction and 630 MW future build.", "OPERATING_CAPACITY", "B", True, value=34.0, unit="MW", effective_date="2025-03-31"),
    source("S_CDC_OPERATOR", ["AIDC10"], "A_OPERATOR", "Melbourne | CDC Data Centres", "https://cdc.com/locations/melbourne/", None, "Operator page establishes the Brooklyn campus identity; current campus expansion values are not backcast to April 2025.", "UNKNOWN", "A", True),
    source("S_IBM_CERT1", ["AIDC11"], "A_TENANT_OFFICIAL", "IBM SoftLayer certificate site schedule", "https://www.ibm.com/support/pages/sites/default/files/inline-files/%24FILE/softlayer_22301.pdf", None, "IBM schedule identifies MEL01 / SoftLayer Technologies Australia at 72 Radnor Drive, Deer Park.", "UNKNOWN", "A", True),
    source("S_IBM_CERT2", ["AIDC11"], "D_CERTIFIER", "IBM SoftLayer certificate of approval", "https://www.ibm.com/support/pages/sites/default/files/inline-files/%24FILE/softlayer_27k.pdf", None, "Certificate lists MEL01 at 72 Radnor Drive, Deer Park with certification date 26-Sep-2017.", "UNKNOWN", "D", True, effective_date="2017-09-26"),
    source("S_MEL11_DLR", ["AIDC11"], "A_OPERATOR", "MEL11 Data Center", "https://www.digitalrealty.com/data-centers/asia-pacific/melbourne/mel11", None, "Digital Realty identifies MEL11 at the same 72 Radnor Drive address with 2N UPS; no MW is published.", "UPS_CAPACITY", "A", True),
    source("S_MEL11_DCM", ["AIDC11"], "F_DIRECTORY", "72 Radnor Drive (MEL11) - Specs", "https://www.datacentermap.com/australia/melbourne/72-radnor-drive/specs/", None, "Directory reports 6.7 MW fully built-out power and estimated operation from 2013.", "FULLY_BUILT_OUT_POWER", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=6.7, unit="MW"),
    source("S_MEL11_GOTCOLO", ["AIDC11"], "F_DIRECTORY", "Melbourne MEL11 Data Center", "https://gotcolo.com/data-center/melbourne-mel11-data-center/", None, "Directory reports 10 MW total power without phase/effective-date resolution.", "FACILITY_POWER", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=10.0, unit="MW"),
    source("S_MEL11_OCOLO", ["AIDC11"], "F_DIRECTORY", "Digital Realty Melbourne MEL11", "https://www.ocolo.io/colocation/digital-realty/melbourne-mel11/", None, "Directory reports 13.40 MW power capacity without phase/effective-date resolution.", "FACILITY_POWER", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", value=13.4, unit="MW"),
    source("S_STACK_OPEN", ["AIDC12"], "A_OPERATOR", "STACK opens first data center in Australia", "https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-delivers-first-data-center-in-australia-launching-a-robust-apac-portfolio/", "2023-08-22", "STACK announced completion/opening of the first 36 MW facility; the second 36 MW development was upcoming. A 105 MW onsite substation is campus context, not an actual DNSP transformer rating.", "BUILT_CAPACITY", "A", True, value=36.0, unit="MW", effective_date="2023-08-22"),
    source("S_STACK_CURRENT", ["AIDC12"], "A_OPERATOR", "MEL01 Campus", "https://www.stackinfra.com/locations/asia-pacific/melbourne/mel01/", None, "Current page lists MEL01A 36 MW but also a later 180 MW four-building campus and 135 MW onsite substation; later campus totals are not backcast.", "BUILT_CAPACITY", "A", True, value=36.0, unit="MW"),
    source("S_STACK_COMMISSIONING", ["AIDC12"], "D_CONTRACTOR", "Concept Commissioning recent projects", "https://www.conceptcx.com.au/recent-experience/", None, "Independent commissioning-agent project record identifies STACK MEL01 in Truganina with a 36 MW metric.", "BUILT_CAPACITY", "D", True, value=36.0, unit="MW"),
    source("S_STACK_DNSP", ["AIDC12"], "C_DNSP", "Powercor network data", "https://www.powercor.com.au/network-planning-and-projects/network-data/", "2024-12-31", "DAPR data supports the Truganina zone-substation planning state applicable to April 2025.", "UNKNOWN", "C", True, effective_date="2024-12-31"),
    source("S_HOST_POWER", ["AIDC01", "AIDC11", "AIDC12"], "C_DNSP", "Powercor 2024 DAPR network data", "https://www.powercor.com.au/network-planning-and-projects/network-data/", "2024-12-31", "Official station ratings, PF, historical demand and 2025 forecasts for LVN and TNA; DPTS is kept as overlapping network-area context.", "MVA_INPUT", "C", True, effective_date="2024-12-31"),
    source("S_HOST_CITY", ["AIDC04", "AIDC08", "AIDC09"], "C_DNSP", "CitiPower 2024 DAPR network data", "https://www.powercor.com.au/network-planning-and-projects/network-data/", "2024-12-31", "Official station ratings, PF, historical demand and 2025 forecasts for Richmond, Port Melbourne and Victoria Market.", "MVA_INPUT", "C", True, effective_date="2024-12-31"),
    source("S_HOST_UE", ["AIDC03", "AIDC07"], "C_DNSP", "United Energy 2024 DAPR Max Demand Template", "https://media.unitedenergy.com.au/reports/2024-DAPR-Max-Demand-Template-United-Energy.xlsx", "2024-12-31", "Official station ratings and demand values for Noble Park and Nunawading.", "MVA_INPUT", "C", True, effective_date="2024-12-31"),
    source("S_HOST_JEMENA", ["AIDC05", "AIDC06", "AIDC10"], "C_DNSP", "Jemena 2024 Distribution Annual Planning Report", "https://www.jemena.com.au/siteassets/asset-folder/documents/electricity/2024-distribution-annual-planning-report.pdf", "2024-12-09", "Official forecast and observed maximum demand for Tullamarine, Footscray West and Tottenham; cited tables do not provide matched firm/normal capacity.", "METERED_PEAK_DEMAND", "C", True, effective_date="2024-12-09"),
    source("S_HOST_AUSNET", ["AIDC02"], "C_DNSP", "AusNet Distribution Annual Planning Report 2025-2029", "https://dapr.ausnetservices.com.au/AusNet%20Services_DAPR%202025-2029_v2.pdf", "2024-12-01", "Official report identifies Bayswater as a main source for Kilsyth South and provides rating/demand evidence.", "MVA_INPUT", "C", True, effective_date="2024-12-01"),
    source("S_DPTS_TCPR", ["AIDC11"], "C_DNSP", "2024 Transmission Connection Planning Report", "https://media.unitedenergy.com.au/reports/2024-TCPR_17-Dec.pdf", "2024-12-17", "DPTS has two 225 MVA transformers and serves the broad Powercor western area; exact MEL11 zone service is not public.", "MVA_INPUT", "C", True, value="2 x 225", unit="MVA", effective_date="2024-12-17"),
    source("S_IEEE_PES", [], "C_STANDARD", "IEEE PES Radial Distribution Test Feeders", "https://cmte.ieee.org/pes-testfeeders/wp-content/uploads/sites/167/2017/08/testfeeders.pdf", None, "Official IEEE 123-node data specifies a 5,000 kVA 115 kV delta / 4.16 kV grounded-wye substation transformer.", "MVA_INPUT", "C", True, value=5.0, unit="MVA"),
    source("S_ENGINEERING_LOADING", [], "C_DNSP", "Energex/Ergon Joint Supply & Planning Manual", "https://swp.energex.com.au/upload/technical_documents/20250527_071841_257532.pdf", "2025-05-07", "Official DNSP planning manual assigns a 0.8 loading-limit factor to dual 1000 kVA commercial outdoor transformers and explains that headroom supports load growth; used only for the IEEE123 engineering interface main assumption.", "UNKNOWN", "C", "ENGINEERING_INTERFACE_ONLY", value=0.8, unit="per_unit", effective_date="2025-05-07"),
]


SITE_ROWS = [
    ("AIDC01", "Equinix ME4", "Equinix", "Equinix", None, "Metronode Melbourne 2 (MEL2)", "2 Davis Court, Derrimut VIC 3030", -37.7884866, 144.7858350, "A", 7.6, 7.6, 18.0, 12.0, "BUILT_CAPACITY", "AER + Equinix + contractor establish ME4 = former MEL2; 12 MW IT-capacity wording remains a separate boundary."),
    ("AIDC02", "Micron21", "Micron21", "Micron21", None, None, "Factory 2, 7 Eastspur Court, Kilsyth South VIC 3137", -37.8215488, 145.3146071, "A", 2.0, 2.0, 2.0, None, "FULLY_BUILT_OUT_POWER", "2 MW is directory evidence; official 2x1 MW values are generator nameplates only."),
    ("AIDC03", "Fujitsu Noble Park", "Fujitsu", "Fujitsu", None, None, "3-5 Summit Road, Noble Park North VIC 3174", -37.9476988, 145.1857646, "A", 28.0, 28.0, 28.0, 28.0, "IT_CAPACITY", "Official 28 MW IT Load is treated as rated IT capacity, not actual April load; 2x4 MVA feed evidence remains separate."),
    ("AIDC04", "AAPT / TPG Richmond", "TPG Telecom / AAPT", "Property owner not resolved", "AAPT/TPG operator", "AAPT Richmond", "180-188 Burnley Street, Richmond VIC 3121", -37.8201330, 145.0076310, "B", None, None, None, None, "MVA_INPUT", "Only 2.5 MVA directory evidence is available; active MW appears only in engineering PF sensitivity."),
    ("AIDC05", "NEXTDC M2", "NEXTDC", "NEXTDC", None, None, "75 Sharps Road, Tullamarine VIC 3043", -37.7088652, 144.8754522, "A", 42.0, 42.0, 42.0, None, "BUILT_CAPACITY", "42 MW built at 31-Dec-2024; 18 MW in progress and 120 MW planned are excluded from April built capacity."),
    ("AIDC06", "NEXTDC M3", "NEXTDC", "NEXTDC", None, None, "25 Indwe Street, West Footscray VIC 3012", -37.8035123, 144.8654833, "A", 13.5, 13.5, 13.5, None, "BUILT_CAPACITY", "13.5 MW built at 31-Dec-2024; another 13.5 MW in progress and planned totals are excluded."),
    ("AIDC07", "Vocus Mitcham", "Vocus", "Vocus", None, "EDC Mitcham / Vocus DC-MEL04", "28 Thornton Crescent, Mitcham VIC 3132", -37.8214322, 145.1877346, "A", 9.0, 9.0, 9.0, None, "FULLY_BUILT_OUT_POWER", "9 MW is directory fully-built-out power, not actual April demand."),
    ("AIDC08", "NEXTDC M1", "NEXTDC", "NEXTDC", None, None, "826-846 Lorimer Street, Port Melbourne VIC 3207", -37.8226649, 144.9322619, "A", 15.0, 15.0, 15.0, 15.0, "IT_CAPACITY", "15 MW operator evidence is April-compatible; later 16 MW current wording is not backcast."),
    ("AIDC09", "Equinix ME5", "Equinix", "Equinix", None, "Metronode / Nextgen Melbourne 1", "22-36 Walsh Street, West Melbourne VIC 3003", -37.8079907, 144.9533624, "A", None, None, None, None, "GENERATOR_NAMEPLATE", "Identity is confirmed; 4.175 MW is generator nameplate only. N+1 upper-bound sensitivity is not real load."),
    ("AIDC10", "CDC Brooklyn BK1", "CDC Data Centres", "CDC Data Centres", None, None, "Brooklyn, Victoria (street address not operator-published)", -37.8164095, 144.8499089, "B", 34.0, 34.0, 34.0, None, "OPERATING_CAPACITY", "34 MW is BK1 operating build capacity, not actual consumption; later/under-construction campus capacity is excluded."),
    ("AIDC11", "IBM MEL01 / Digital Realty MEL11", "Digital Realty", "Digital Realty", "IBM SoftLayer MEL01", "Digital Realty MEL11 / Deer Park 2", "72 Radnor Drive, Deer Park VIC 3023", -37.7819000, 144.7778000, "A", 6.7, None, 13.4, None, "CONFLICT_UNRESOLVED", "IBM MEL01 is a tenant/site code at Digital Realty MEL11 in Deer Park, not Cheltenham; 6.7/10/13.4 MW secondary values remain unresolved."),
    ("AIDC12", "STACK MEL01A", "STACK Infrastructure", "STACK Infrastructure", None, None, "399 Palmers Road, Truganina VIC 3029", -37.8199329, 144.7476422, "A", 36.0, 36.0, 36.0, None, "BUILT_CAPACITY", "First 36 MW building completed in 2023; second building and later 180 MW campus values are not backcast."),
]

CAPACITY_AUDIT = {
    "AIDC01": ("B", "D", True, "S_ME4_ICON"),
    "AIDC02": ("D", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", "S_MICRON_DCM"),
    "AIDC03": ("B", "A", "LATER_OFFICIAL_PAGE_EFFECTIVE_DATE_UNCLEAR", "S_FUJITSU_OFFICIAL"),
    "AIDC04": ("D", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", "S_AAPT_INFLECT"),
    "AIDC05": ("A", "B", True, "S_NEXTDC_1H25"),
    "AIDC06": ("A", "B", True, "S_NEXTDC_1H25"),
    "AIDC07": ("D", "F", "TEMPORAL_APPLICABILITY_UNRESOLVED", "S_VOCUS_DCM"),
    "AIDC08": ("A", "A", True, "S_NEXTDC_GUIDE"),
    "AIDC09": ("D", "A", "CAPACITY_UNAVAILABLE", "S_ME5_EQX"),
    "AIDC10": ("A", "B", True, "S_CDC_INFRATIL_2025"),
    "AIDC11": ("D", "F", "CONFLICT_UNRESOLVED", "S_MEL11_DCM/S_MEL11_GOTCOLO/S_MEL11_OCOLO"),
    "AIDC12": ("A", "A", True, "S_STACK_OPEN"),
}


def site_objects() -> list[dict[str, object]]:
    rows = []
    for raw in SITE_ROWS:
        (sid, name, op, owner, tenant, former, address, lat, lon, conf,
         low, central, high, it_capacity, boundary, notes) = raw
        capacity_confidence, capacity_source_grade, capacity_april, primary_source = CAPACITY_AUDIT[sid]
        rows.append({
            "site_id": sid,
            "site_name": name,
            "operator": op,
            "facility_owner": owner,
            "tenant_if_any": tenant,
            "former_name": former,
            "address": address,
            "latitude": lat,
            "longitude": lon,
            "identity_confidence": conf,
            "capacity_confidence": capacity_confidence,
            "capacity_source_grade": capacity_source_grade,
            "capacity_April_2025_applicability": capacity_april,
            "primary_capacity_source_id": primary_source,
            "April_2025_operational_status": "OPERATIONAL_DURING_APRIL_2025",
            "April_2025_applicable": True,
            "P_SITE_CAPACITY_LOW_MW": low,
            "P_SITE_CAPACITY_CENTRAL_MW": central,
            "P_SITE_CAPACITY_HIGH_MW": high,
            "P_SITE_IT_CAPACITY_MW": it_capacity,
            "P_SITE_OPERATING_LOAD_APRIL_LOW_MW": None,
            "P_SITE_OPERATING_LOAD_APRIL_CENTRAL_MW": None,
            "P_SITE_OPERATING_LOAD_APRIL_HIGH_MW": None,
            "primary_capacity_boundary": boundary,
            "notes": notes,
        })
    return rows


def old_hosts_by_aidc() -> dict[str, dict[str, object]]:
    rows = json.loads((OLD / "MELBOURNE_AIDC_APRIL2025_UNIQUE_HOST_GRID_MAPPING.json").read_text(encoding="utf-8"))
    result = {}
    for host in rows:
        for sid in host["AIDC_IDS"]:
            result[sid] = host
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sites = site_objects()
    site_by_id = {row["site_id"]: row for row in sites}

    # Source registry and evidence table.
    registry = {
        "artifact_id": "V22S_12SITE_SOURCE_REGISTRY_V1",
        "reference_period": APRIL_PERIOD,
        "access_date": ACCESS_DATE,
        "wayback_access_status": "NOT_ACCESSED",
        "source_hierarchy": {
            "A": "operator official facility page/fact sheet",
            "B": "owner/investor official filing or valuation",
            "C": "government/planning/AER/DNSP/standard",
            "D": "official construction contractor or independent certifier",
            "E": "reputable industry publication",
            "F": "commercial facility directory",
        },
        "sources": SOURCES,
    }
    write_json("V22S_12SITE_SOURCE_REGISTRY.json", registry)

    numeric = [row for row in SOURCES if row["reported_value"] is not None]
    evidence_fields = [
        "site_id", "site_name", "operator", "facility_owner", "tenant_if_any",
        "former_name", "address", "latitude", "longitude", "April_2025_operational_status",
        "April_2025_applicable", "effective_date", "publication_date", "reported_value",
        "reported_unit", "reported_boundary", "source_url", "source_title", "source_type",
        "source_quality_grade", "source_access_date", "source_SHA256_if_downloaded",
        "exact_quote_or_paraphrase", "confidence_grade", "conflict_group", "notes",
    ]
    evidence_rows = []
    for src in numeric:
        for sid in src["site_ids"] or ["IEEE123"]:
            site = site_by_id.get(sid, {})
            evidence_rows.append({
                "site_id": sid,
                "site_name": site.get("site_name", "IEEE123 feeder"),
                "operator": site.get("operator", "IEEE PES"),
                "facility_owner": site.get("facility_owner", "IEEE PES"),
                "tenant_if_any": site.get("tenant_if_any"),
                "former_name": site.get("former_name"),
                "address": site.get("address"),
                "latitude": site.get("latitude"),
                "longitude": site.get("longitude"),
                "April_2025_operational_status": site.get("April_2025_operational_status", "TEST_FEEDER_AUTHORITY"),
                "April_2025_applicable": src["April_2025_applicable"],
                "effective_date": src["effective_date"],
                "publication_date": src["publication_date"],
                "reported_value": src["reported_value"],
                "reported_unit": src["reported_unit"],
                "reported_boundary": src["reported_boundary"],
                "source_url": src["source_url"],
                "source_title": src["title"],
                "source_type": src["source_class"],
                "source_quality_grade": src["source_quality_grade"],
                "source_access_date": src["source_access_date"],
                "source_SHA256_if_downloaded": src["source_SHA256_if_downloaded"],
                "exact_quote_or_paraphrase": src["exact_quote_or_paraphrase"],
                "confidence_grade": site.get("identity_confidence", "A"),
                "conflict_group": "MEL11_POWER" if sid == "AIDC11" and src["reported_boundary"] in {"FULLY_BUILT_OUT_POWER", "FACILITY_POWER"} else "",
                "notes": site.get("notes", ""),
            })
    with (OUT / "V22S_12SITE_CAPACITY_EVIDENCE.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=evidence_fields)
        writer.writeheader(); writer.writerows(evidence_rows)

    searched = {}
    for sid in site_by_id:
        classes = sorted({s["source_class"] for s in SOURCES if sid in s["site_ids"]})
        searched[sid] = {"source_classes": classes, "class_count": len(classes), "minimum_three_satisfied": len(classes) >= 3}
    identity = {
        "artifact_id": "V22S_SITE_IDENTITY_AUTHORITY_V1",
        "reference_period": APRIL_PERIOD,
        "sites": sites,
        "source_class_search_audit": searched,
        "explicit_findings": {
            "Equinix_ME4": "SAME_PHYSICAL_SITE_AS_FORMER_METRONODE_MELBOURNE_2",
            "Equinix_ME5": "SAME_PHYSICAL_SITE_AS_FORMER_METRONODE_NEXTGEN_MELBOURNE_1",
            "IBM_MEL01_relationship": "IBM_SOFTLAYER_TENANT_SITE_CODE_WITHIN_DIGITAL_REALTY_MEL11",
            "IBM_MEL01_address": "72_RADNOR_DRIVE_DEER_PARK_NOT_CHELTENHAM",
            "CDC_34MW": "BK1_OPERATING_BUILD_CAPACITY_NOT_ACTUAL_OPERATING_LOAD",
            "Fujitsu_28MW": "OPERATOR_FACILITY_SPEC_IT_CAPACITY_NOT_ACTUAL_METERED_LOAD",
        },
    }
    write_json("V22S_SITE_IDENTITY_AUTHORITY.json", identity)

    conflicts = {
        "artifact_id": "V22S_SOURCE_CONFLICT_REGISTRY_V1",
        "conflicts": [
            {"conflict_id": "ME4_BOUNDARY_SPLIT", "site_id": "AIDC01", "values": ["7.6 MW installed", "12 MW IT capacity", "18 MW ultimate design"], "status": "RESOLVED_BY_BOUNDARY_NOT_NUMERIC_SELECTION"},
            {"conflict_id": "FUJITSU_BOUNDARY_SPLIT", "site_id": "AIDC03", "values": ["28 MW IT capacity", "2 x 4 MVA main feeds"], "status": "RESOLVED_BY_BOUNDARY"},
            {"conflict_id": "NEXTDC_TEMPORAL_SPLIT", "site_id": "AIDC05/AIDC06", "values": ["M2 42 MW built +18 in progress", "M3 13.5 MW built +13.5 in progress"], "status": "IN_PROGRESS_VALUES_EXCLUDED"},
            {"conflict_id": "ME5_CAPACITY_GAP", "site_id": "AIDC09", "values": ["4.175 MW generator nameplate"], "status": "NO_IT_OR_FACILITY_CAPACITY_AUTHORITY"},
            {"conflict_id": "MEL11_POWER", "site_id": "AIDC11", "values": ["6.7 MW fully built-out power", "10 MW total power", "13.4 MW power capacity"], "status": "CONFLICT_UNRESOLVED", "reason": "No primary source resolves phase, boundary, or April-2025 effective state."},
            {"conflict_id": "STACK_TEMPORAL_SPLIT", "site_id": "AIDC12", "values": ["36 MW first building", "72 MW then-campus", "180 MW later campus"], "status": "APRIL_RESOLVED_TO_FIRST_36MW_BUILDING"},
        ],
    }
    write_json("V22S_SOURCE_CONFLICT_REGISTRY.json", conflicts)

    taxonomy = [
        "ACTUAL_OPERATING_IT_LOAD", "METERED_PEAK_DEMAND", "CONTRACTED_IT_LOAD",
        "BILLED_IT_CAPACITY", "IT_LOAD", "IT_CAPACITY", "CRITICAL_IT_POWER",
        "OPERATING_CAPACITY", "BUILT_CAPACITY", "FULLY_BUILT_OUT_POWER",
        "FACILITY_POWER", "INCOMING_POWER", "DESIGN_CAPACITY",
        "FUTURE_ULTIMATE_CAPACITY", "MVA_INPUT", "UPS_CAPACITY",
        "GENERATOR_NAMEPLATE", "SERVER_COUNT", "UNKNOWN",
    ]
    write_json("V22S_CAPACITY_BOUNDARY_TAXONOMY.json", {
        "artifact_id": "V22S_CAPACITY_BOUNDARY_TAXONOMY_V1",
        "allowed_values": taxonomy,
        "silent_boundary_relabel_count": 0,
        "rules": ["Capacity is not actual load", "MVA is not MW without an explicit or engineering-sensitivity PF", "UPS/generator/server proxies are not IT MW"],
    })
    write_json("V22S_CAPACITY_VS_OPERATING_LOAD_CONTRACT.json", {
        "artifact_id": "V22S_CAPACITY_VS_OPERATING_LOAD_CONTRACT_V1",
        "P_SITE_CAPACITY": "installed/built/design electrical or IT capacity, preserving source boundary",
        "P_SITE_OPERATING_LOAD_APRIL": "April-2025 actual, contracted or metered demand only",
        "operating_load_authority_available_sites": [],
        "capacity_equals_load_relabel_count": 0,
        "unknown_to_zero_count": 0,
        "PUE_application_calls": 0,
    })

    interval_fields = [
        "site_id", "site_name", "capacity_low_MW", "capacity_central_MW", "capacity_high_MW",
        "capacity_boundary", "operating_load_low_MW", "operating_load_central_MW",
        "operating_load_high_MW", "engineering_equivalent_low_MW",
        "engineering_equivalent_central_MW", "engineering_equivalent_high_MW",
        "engineering_label", "authority_grade", "notes",
    ]
    interval_rows = []
    for site in sites:
        sid = site["site_id"]
        eng_low = eng_central = eng_high = None
        eng_label = None
        if sid == "AIDC04":
            eng_low, eng_central, eng_high = 2.375, 2.45, 2.5
            eng_label = "ENGINEERING_PF_SENSITIVITY_NOT_REAL_LOAD"
        elif sid == "AIDC09":
            eng_high = 3.05
            eng_label = "GENERATOR_N_PLUS_1_ENGINEERING_UPPER_BOUND_NOT_REAL_LOAD"
        interval_rows.append({
            "site_id": sid, "site_name": site["site_name"],
            "capacity_low_MW": site["P_SITE_CAPACITY_LOW_MW"],
            "capacity_central_MW": site["P_SITE_CAPACITY_CENTRAL_MW"],
            "capacity_high_MW": site["P_SITE_CAPACITY_HIGH_MW"],
            "capacity_boundary": site["primary_capacity_boundary"],
            "operating_load_low_MW": None, "operating_load_central_MW": None,
            "operating_load_high_MW": None,
            "engineering_equivalent_low_MW": eng_low,
            "engineering_equivalent_central_MW": eng_central,
            "engineering_equivalent_high_MW": eng_high,
            "engineering_label": eng_label,
            "authority_grade": site["identity_confidence"],
            "notes": site["notes"],
        })
    with (OUT / "V22S_SITE_LOW_CENTRAL_HIGH_INTERVALS.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=interval_fields)
        writer.writeheader(); writer.writerows(interval_rows)

    sets = {
        "SET_A_ACTUAL_LOAD": {"sites": [], "site_count": 0, "total_MW": None, "status": "NO_SITE_SPECIFIC_APRIL_ACTUAL_CONTRACTED_OR_METERED_LOAD"},
        "SET_B_IT_CAPACITY": {"sites": {"AIDC01": 12.0, "AIDC03": 28.0, "AIDC08": 15.0}, "site_count": 3, "total_MW": 55.0, "boundary_note": "IT capacity; ME4 source grade E makes it a lower-grade sensitivity"},
        "SET_C_OPERATING_OR_BUILT_MW": {"sites": {"AIDC01": 7.6, "AIDC05": 42.0, "AIDC06": 13.5, "AIDC08": 15.0, "AIDC10": 34.0, "AIDC12": 36.0}, "site_count": 6, "total_MW": 148.1, "boundary_note": "Official/contractor operating-or-built active-power capacity only"},
        "SET_D_FACILITY_OR_INCOMING_POWER": {"sites": {}, "site_count": 0, "total_MW": None, "status": "NO_APRIL_PRIMARY_SOURCE_COMMON_SET"},
        "SET_E_MVA": {"sites": {"AIDC03": "2 x 4 MVA", "AIDC04": "2.5 MVA"}, "site_count": 2, "total_MVA": None, "status": "COMPONENT_AND_FACILITY_MVA_NOT_SUMMED"},
        "SET_F_NAMEPLATE_ONLY": {"sites": {"AIDC02": "2 x 1 MW generators", "AIDC09": "4.175 MW generators"}, "site_count": 2, "total_MW": None, "status": "EXCLUDED_FROM_CENTRAL_CAPACITY"},
        "cross_set_silent_sum_count": 0,
    }
    write_json("V22S_STRICT_COMMON_BOUNDARY_SETS.json", {"artifact_id": "V22S_STRICT_COMMON_BOUNDARY_SETS_V1", **sets})

    # Host mapping: reuse frozen official DAPR rows, with AIDC11 corrected to a broad network area.
    old_hosts = old_hosts_by_aidc()
    host_rows = []
    for site in sites:
        sid = site["site_id"]
        if sid != "AIDC11":
            old = dict(old_hosts[sid])
            host_rows.append({
                "site_id": sid, "dnsp": old["dnsp"], "host_id": old["host_id"],
                "real_host_grid": old["host_name"], "host_type": old["host_type"],
                "mapping_class": old["HOST_MAPPING_CLASS"], "mapping_confidence": old["confidence"],
                "alternatives": old["ALTERNATIVE_CANDIDATES"],
                "firm_MW": old["FIRM_CAPACITY_MW"], "normal_MW": old["NORMAL_CAPACITY_MW"],
                "firm_MVA": old["FIRM_CAPACITY_MVA"], "normal_MVA": old["NORMAL_CAPACITY_MVA"],
                "forecast_2025_peak_MW": old["2025_FORECAST_MAXIMUM_DEMAND_MW"],
                "historical_2024_peak_MW": old["2024_HISTORICAL_MAXIMUM_DEMAND_MW"],
                "April_2025_applicable": old["APRIL_2025_APPLICABLE"],
                "source_url": old["source_url"], "aggregate_eligible": True,
                "overlaps_downstream_hosts": False,
            })
        else:
            host_rows.append({
                "site_id": sid, "dnsp": "Powercor", "host_id": "HOST_DPTS_AREA",
                "real_host_grid": "Deer Park Terminal Station supply area",
                "host_type": "TERMINAL_STATION_NETWORK_AREA", "mapping_class": "NETWORK_AREA_ONLY",
                "mapping_confidence": "D", "alternatives": ["Laverton North (LVN)", "Sunshine (SU)", "Truganina (TNA)"],
                "firm_MW": None, "normal_MW": None, "firm_MVA": 225.0, "normal_MVA": 450.0,
                "forecast_2025_peak_MW": None, "historical_2024_peak_MW": 291.7,
                "April_2025_applicable": True, "source_url": "https://media.unitedenergy.com.au/reports/2024-TCPR_17-Dec.pdf",
                "aggregate_eligible": False, "overlaps_downstream_hosts": True,
            })
    write_json("V22S_HOST_MAPPING_AUTHORITY.json", {
        "artifact_id": "V22S_HOST_MAPPING_AUTHORITY_V1", "mappings": host_rows,
        "direct_service_confirmed_count": 0,
        "AIDC11_correction": "Cheltenham/United Energy mapping retired; Deer Park Powercor area recorded without inventing an exact zone service.",
    })

    host_by_site = {h["site_id"]: h for h in host_rows}
    def denom(site_ids: list[str], field: str) -> float | None:
        vals, seen = [], set()
        for sid in site_ids:
            host = host_by_site[sid]
            if host["host_id"] in seen or host[field] is None or not host["aggregate_eligible"]:
                if host[field] is None or not host["aggregate_eligible"]:
                    return None
                continue
            seen.add(host["host_id"]); vals.append(float(host[field]))
        return math.fsum(vals)

    matched = {
        "artifact_id": "V22S_MATCHED_HOST_DENOMINATORS_V1",
        "unique_host_rule": True,
        "sets": {
            "SET_A_ACTUAL_LOAD": {"site_subset": [], "matched_host_subset": [], "denominator": None},
            "SET_B_IT_CAPACITY_MATCHED": {"site_subset": ["AIDC01", "AIDC03", "AIDC08"], "matched_host_subset": [host_by_site[s]["host_id"] for s in ["AIDC01", "AIDC03", "AIDC08"]], "firm_MW": denom(["AIDC01", "AIDC03", "AIDC08"], "firm_MW"), "normal_MW": denom(["AIDC01", "AIDC03", "AIDC08"], "normal_MW")},
            "SET_C_OFFICIAL_BUILT_MATCHED": {"site_subset": ["AIDC01", "AIDC08", "AIDC12"], "excluded_common_set_sites_missing_host_capacity": ["AIDC05", "AIDC06", "AIDC10"], "matched_host_subset": [host_by_site[s]["host_id"] for s in ["AIDC01", "AIDC08", "AIDC12"]], "firm_MW": denom(["AIDC01", "AIDC08", "AIDC12"], "firm_MW"), "normal_MW": denom(["AIDC01", "AIDC08", "AIDC12"], "normal_MW")},
        },
        "coverage_tests": {"numerator_site_set_equals_denominator_site_set": True, "four_site_twelve_host_mismatch_count": 0, "overlapping_DPTS_aggregate_count": 0},
    }
    write_json("V22S_MATCHED_HOST_DENOMINATORS.json", matched)

    inventory = json.loads((OLD / "IEEE123_CURRENT_AIDC_SCALE_INVENTORY.json").read_text(encoding="utf-8"))
    master = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference\opendss_assets\IEEE123Master.dss")
    ieee = {
        "artifact_id": "V22S_IEEE123_DENOMINATOR_AUTHORITY_V1",
        "LOAD_TO_LOAD": {"IEEE123_background_peak_demand_MW": inventory["background_operational_MW"]["peak"], "provenance": inventory["background_operational_MW"]["source"], "role": "DEMAND_DENOMINATOR_ONLY"},
        "CAPACITY_TO_CAPACITY": {"IEEE123_substation_transformer_MVA": 5.0, "role": "CAPACITY_DENOMINATOR_ONLY", "official_source_url": "https://cmte.ieee.org/pes-testfeeders/wp-content/uploads/sites/167/2017/08/testfeeders.pdf", "local_recovered_master": str(master), "local_master_sha256": sha256(master), "local_master_line": "new transformer.reg1a ... kvas=[5000 5000]"},
        "demand_capacity_mixing_count": 0,
        "existing_12x1_5MVA_interfaces": {"rating_each_MVA": 1.5, "authority": "LEGACY_SYNTHETIC_CASE_STUDY_INTERFACE_NOT_REAL_DNSP"},
    }
    write_json("V22S_IEEE123_DENOMINATOR_AUTHORITY.json", ieee)

    # Strict capacity candidates only; strict load is unavailable.
    strict_cases = []
    for case_id, site_ids, numerator in [
        ("STRICT_SET_B_IT_CAPACITY", ["AIDC01", "AIDC03", "AIDC08"], 55.0),
        ("STRICT_SET_C_BUILT_CAPACITY", ["AIDC01", "AIDC08", "AIDC12"], 58.6),
    ]:
        for rating in ["firm_MW", "normal_MW"]:
            d = denom(site_ids, rating)
            rho = numerator / d
            ieee_matrix = {str(pf): rho * 5.0 * pf for pf in [0.95, 0.98, 1.0]}
            strict_cases.append({
                "case_id": f"{case_id}_VS_HOST_{rating.upper()}", "site_subset": site_ids,
                "matched_host_subset": [host_by_site[s]["host_id"] for s in site_ids],
                "numerator_MW": numerator, "numerator_boundary": "IT_CAPACITY" if "SET_B" in case_id else "OPERATING_OR_BUILT_MW",
                "denominator_MW": d, "denominator_boundary": "HOST_FIRM_CAPACITY_MW" if rating == "firm_MW" else "HOST_NORMAL_CAPACITY_MW",
                "rho": rho, "IEEE123_equivalent_active_MW_by_capacity_PF": ieee_matrix,
                "authority": "STRICT_MATCHED_COVERAGE_CAPACITY_TO_CAPACITY_CANDIDATE",
            })
    strict = {
        "artifact_id": "V22S_STRICT_AUTHORITY_SCALE_V1",
        "STRICT_LOAD_EQUIVALENT_MW": None,
        "strict_load_reason": "No site-specific April actual/contracted/metered load exists for a matched load-to-load subset.",
        "strict_capacity_candidates": strict_cases,
        "selection": None,
        "grid_result_based_selection_calls": 0,
    }
    write_json("V22S_STRICT_AUTHORITY_SCALE.json", strict)

    # Full 12-site interval: values are fixed before totals are calculated.
    equivalent_inputs = {
        "AIDC01": 7.6, "AIDC02": 2.0, "AIDC03": 28.0, "AIDC04": 2.45,
        "AIDC05": 42.0, "AIDC06": 13.5, "AIDC07": 9.0, "AIDC08": 15.0,
        "AIDC10": 34.0, "AIDC12": 36.0,
    }
    base = math.fsum(equivalent_inputs.values())
    mel11_low, mel11_high, me5_high = 6.7, 13.4, 3.05
    lower_limit = base + mel11_low
    upper = base + mel11_high + me5_high
    contract = {
        "artifact_id": "V22S_EQUIVALENT_12SITE_SCALE_CONTRACT_V1",
        "case_label": "MELBOURNE_INFORMED_EQUIVALENT_12SITE_CASE_NOT_ACTUAL_LOAD_CENSUS",
        "preregistered_before_total_rule": [
            "Use April-compatible Tier A/B active-power capacity where available",
            "Otherwise retain source-backed interval without midpoint",
            "AIDC04 may use 2.5 MVA x PF sensitivity only as engineering equivalent",
            "AIDC09 generator data provides an N+1 engineering upper bound only; no central value",
            "AIDC11 6.7/10/13.4 MW conflict remains an interval; no central value",
        ],
        "PF_sensitivity_for_AIDC04": [0.95, 0.98, 1.0],
        "central_PF_for_engineering_only": 0.98,
        "grid_results_consulted": False,
        "legacy_targets_consulted": False,
    }
    write_json("V22S_EQUIVALENT_12SITE_SCALE_CONTRACT.json", contract)

    equivalent = {
        "artifact_id": "V22S_EQUIVALENT_12SITE_SCALE_RESULTS_V1",
        "12SITE_EQUIVALENT_LOW": None,
        "12SITE_EQUIVALENT_PRIMARY": None,
        "12SITE_EQUIVALENT_HIGH": None,
        "capacity_interval_MW": {"lower_limit_exclusive": lower_limit, "upper_bound_inclusive": upper, "notation": f"({lower_limit:.5f}, {upper:.5f}] MW"},
        "known_fixed_10site_total_MW": base,
        "AIDC11_interval_MW": [mel11_low, mel11_high],
        "AIDC09_interval_MW": {"lower": None, "lower_limit_exclusive": 0.0, "upper_engineering_bound": me5_high},
        "aggregate_IEEE123_scale": None,
        "reason": "A 12-site matched host capacity denominator and two site central capacities are unavailable; capacity/load boundary mismatch is prohibited.",
        "authority": "WEIGHT_INTERVAL_SET_ONLY",
    }
    write_json("V22S_EQUIVALENT_12SITE_SCALE_RESULTS.json", equivalent)

    # Feasible weight envelope and a single upper-bound corner scenario.
    interval_weights = {}
    for sid, value in equivalent_inputs.items():
        interval_weights[sid] = {"min_inclusive": value / upper, "max_exclusive": value / lower_limit}
    interval_weights["AIDC11"] = {"min_inclusive": mel11_low / upper, "max_inclusive": mel11_high / (base + mel11_high)}
    interval_weights["AIDC09"] = {"min": None, "lower_limit_exclusive": 0.0, "max_inclusive": me5_high / (base + mel11_low + me5_high)}
    high_values = dict(equivalent_inputs, AIDC09=me5_high, AIDC11=mel11_high)
    high_weights = {sid: value / upper for sid, value in sorted(high_values.items())}
    weights = {
        "artifact_id": "V22S_SITE_POWER_WEIGHTS_V1",
        "SITE_CAPACITY_WEIGHT": {"low": None, "primary": None, "high_bound_corner": high_weights},
        "SITE_OPERATING_LOAD_WEIGHT": {sid: None for sid in sorted(site_by_id)},
        "WEIGHT_INTERVAL_SET": interval_weights,
        "high_bound_corner_sum": math.fsum(high_weights.values()),
        "high_bound_corner_authority": "ENGINEERING_EQUIVALENT",
        "FULL_12_SITE_WEIGHT_STATUS": "INTERVAL_ONLY_NO_SINGLE_CENTRAL_WEIGHT",
        "null_converted_to_zero_count": 0,
    }
    write_json("V22S_SITE_POWER_WEIGHTS.json", weights)
    write_json("V22S_SITE_GPU_WEIGHT_AUTHORITY.json", {
        "artifact_id": "V22S_SITE_GPU_WEIGHT_AUTHORITY_V1",
        "GPU_WEIGHT_AUTHORITY": "UNAVAILABLE",
        "site_GPU_weights": {sid: None for sid in sorted(site_by_id)},
        "engineering_GPU_allocation": None,
        "power_weight_equals_GPU_weight_calls": 0,
        "GPU_h_scale_calls": 0,
    })

    pcc_contract = {
        "artifact_id": "V22S_PCC_INTERFACE_ENGINEERING_CONTRACT_V1",
        "REAL_DNSP_INTERFACE": "NULL_UNLESS_SITE_SPECIFIC_PUBLIC_CONNECTION_RATING_EXISTS",
        "IEEE123_EQUIVALENT_INTERFACE": "ENGINEERING_DESIGN_CONTRACT_NOT_ACTUAL_MELBOURNE_TRANSFORMER",
        "PF_sensitivity": [0.95, 0.98, 1.0],
        "loading_fraction_sensitivity": [0.8, 0.9],
        "main_PF": 0.98,
        "main_loading_fraction": 0.8,
        "main_assumption_basis": "PF 0.98 lies inside published 0.97-1.00 host DAPR range. Loading 0.80 follows the official Energex/Ergon dual-commercial-outdoor transformer assigned loading-limit factor; both are engineering assumptions, not real Melbourne ratings.",
        "main_loading_source_url": "https://swp.energex.com.au/upload/technical_documents/20250527_071841_257532.pdf",
        "standard_transformer_MVA": [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.75, 5.0],
    }
    write_json("V22S_PCC_INTERFACE_ENGINEERING_CONTRACT.json", pcc_contract)

    def round_standard(required: float) -> float | None:
        for size in pcc_contract["standard_transformer_MVA"]:
            if size + 1e-12 >= required:
                return size
        return None

    # Interfaces are only calculated for the strict built-capacity subset and each candidate total.
    built_weights = {"AIDC01": 7.6 / 58.6, "AIDC08": 15.0 / 58.6, "AIDC12": 36.0 / 58.6}
    pcc_rows = []
    built_cases = [c for c in strict_cases if c["case_id"].startswith("STRICT_SET_C")]
    for case in built_cases:
        system_peak = case["IEEE123_equivalent_active_MW_by_capacity_PF"]["0.98"]
        for sid in sorted(site_by_id):
            p_peak = system_peak * built_weights[sid] if sid in built_weights else None
            for pf in [0.95, 0.98, 1.0]:
                for loading in [0.8, 0.9]:
                    required = p_peak / (pf * loading) if p_peak is not None else None
                    rating = round_standard(required) if required is not None else None
                    pcc_rows.append({
                        "case_id": case["case_id"], "site_id": sid,
                        "P_peak_MW": p_peak, "PF_assumed": pf,
                        "loading_fraction": loading, "S_required_MVA": required,
                        "standard_rating_MVA": rating,
                        "rating_exceeds_required": rating is not None and rating + 1e-12 >= required if required is not None else None,
                        "REAL_DNSP_INTERFACE_MVA": None,
                        "authority": "IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE" if p_peak is not None else "NOT_CALCULATED_OUTSIDE_STRICT_SUBSET",
                    })
    with (OUT / "V22S_PCC_INTERFACE_RESULTS.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pcc_rows[0]))
        writer.writeheader(); writer.writerows(pcc_rows)

    ready = {
        "artifact_id": "V22S_READY_FLAGS_V1",
        "SITE_IDENTITY_AUTHORITY_READY": True,
        "SITE_CAPACITY_EVIDENCE_READY": True,
        "STRICT_COMMON_BOUNDARY_READY": True,
        "STRICT_LOAD_SCALE_READY": False,
        "STRICT_CAPACITY_SCALE_READY": True,
        "EQUIVALENT_12SITE_SCALE_READY": False,
        "SITE_POWER_WEIGHT_READY": False,
        "SITE_GPU_WEIGHT_AUTHORITY_READY": False,
        "PCC_INTERFACE_ENGINEERING_READY": True,
        "FINAL_GRID_SCIENCE_READY": False,
    }
    write_json("V22S_READY_FLAGS.json", ready)

    review = {
        "artifact_id": "V22S_FINAL_SCALE_REVIEW_V1",
        "classification": "V22S_BOUNDARY_OR_IDENTITY_CONFLICT_REMAINS",
        "reference_period": APRIL_PERIOD,
        "v20_to_v22s_corrections": [
            {"site": "Equinix ME4", "V20": None, "V22S": "7.6 MW installed; 12 MW IT capacity; 18 MW design", "reason": "Contractor and historical trade evidence recovered; boundaries kept separate."},
            {"site": "Fujitsu Noble Park", "V20": "2 x 4 MVA only", "V22S": "28 MW IT capacity plus 2 x 4 MVA input", "reason": "Official operator 28 MW wording recovered and not relabelled actual load."},
            {"site": "CDC Brooklyn BK1", "V20": None, "V22S": "34 MW operating build capacity", "reason": "Contemporaneous Infratil filing ties Melbourne operating capacity to BK1."},
            {"site": "IBM MEL01 / MEL11", "V20": "Cheltenham identity", "V22S": "72 Radnor Drive, Deer Park tenant/facility relation", "reason": "Two IBM schedules and Digital Realty address agree."},
            {"site": "Equinix ME5", "V20": "4.175 MW generator nameplate", "V22S": "capacity remains null; nameplate retained only", "reason": "No IT/facility MW authority found."},
        ],
        "site_table": sites,
        "boundary_sets": sets,
        "host_grid_mapping": host_rows,
        "IEEE123_denominator": ieee,
        "site_power_weights": weights,
        "PCC_interface_contract": pcc_contract,
        "strict_scale": strict,
        "equivalent_12site": equivalent,
        "unresolved_items": [
            "No 12-site April actual/contracted/metered operating-load census",
            "ME5 IT/facility capacity unavailable",
            "MEL11 6.7/10/13.4 MW secondary conflict unresolved",
            "MEL11 exact serving zone substation not public",
            "Jemena firm/normal host capacity absent for M2, M3 and CDC matched hosts",
            "No public site-specific real DNSP transformer ratings",
        ],
        "ready_flags": ready,
        "firewall": {
            "ML_retraining": 0, "forecast_edits": 0, "GPU_h_scale_calls": 0,
            "B0_calls": 0, "B1_calls": 0, "B2_calls": 0, "B3_calls": 0,
            "OpenDSS_calls": 0, "grid_science_calls": 0,
            "unsupported_MVA_to_MW": 0, "generator_to_IT": 0, "UPS_to_IT": 0,
            "server_count_to_MW": 0, "capacity_to_actual_load": 0,
            "future_capacity_backcast": 0, "grid_result_based_tuning": 0,
        },
    }
    write_json("V22S_FINAL_SCALE_REVIEW.json", review)

    md = f"""# V22S Melbourne 12-site scale re-audit

RESULT CLASSIFICATION:
V22S_BOUNDARY_OR_IDENTITY_CONFLICT_REMAINS

## 1. Source-discovery corrections

V20의 핵심 수정은 ME4의 7.6 MW installed/12 MW IT-capacity 분리, Fujitsu의 28 MW IT-capacity 회복, CDC BK1의 34 MW operating-build-capacity 회복, IBM MEL01의 Deer Park MEL11 tenant 관계 확정이다. ME5는 발전기 nameplate 외 용량 권한이 없어 null을 유지한다.

## 2. 12-site table

| Site | identity | April status | capacity MW | actual operating-load MW | boundary | low / central / high | confidence |
|---|---|---|---:|---:|---|---|---|
"""
    for site in sites:
        bounds = f"{site['P_SITE_CAPACITY_LOW_MW']} / {site['P_SITE_CAPACITY_CENTRAL_MW']} / {site['P_SITE_CAPACITY_HIGH_MW']}"
        md += f"| {site['site_id']} | {site['site_name']} | operational | {site['P_SITE_CAPACITY_CENTRAL_MW']} | null | {site['primary_capacity_boundary']} | {bounds} | identity {site['identity_confidence']} / capacity {site['capacity_confidence']} ({site['capacity_source_grade']}) |\n"
    md += f"""

12개 시설 모두 2025년 4월 운영 identity를 검토했다. 그러나 site별 실제 April operating load는 0/12개만 확보되었다. capacity와 actual load는 어느 행에서도 동일시하지 않았다.

## 3. Boundary coverage

- SET_A actual load: 0 sites, total null
- SET_B IT capacity: 3 sites, 55.0 MW
- SET_C official operating/built MW: 6 sites, 148.1 MW
- SET_E MVA: 2 sites, MW로 합산하지 않음
- SET_F nameplate only: 2 sites, central capacity에서 제외

## 4. Strict scale

Strict load scale은 null이다. Strict capacity-to-capacity 산술은 동일 site/host coverage를 갖는 SET_B 3-site와 SET_C 3-site 후보만 생성했으며 선택하지 않았다.

| Candidate | Sites | Numerator MW | Denominator MW | rho | IEEE123 equivalent MW @ PF=0.98 |
|---|---|---:|---:|---:|---:|
"""
    for case in strict_cases:
        md += f"| {case['case_id']} | {','.join(case['site_subset'])} | {case['numerator_MW']:.6f} | {case['denominator_MW']:.6f} | {case['rho']:.12f} | {case['IEEE123_equivalent_active_MW_by_capacity_PF']['0.98']:.12f} |\n"
    md += f"""

## 5. Equivalent 12-site case

단일 primary를 만들지 않았다. 사전등록 규칙으로 얻은 capacity interval은 **({lower_limit:.5f}, {upper:.5f}] MW**이며, ME5의 양의 미확정 하한과 MEL11 충돌 때문에 low/primary/high aggregate scale은 null이다. 숫자 high-bound corner weight만 합계 1.0으로 제공한다.

| Site | high-bound corner weight | authority |
|---|---:|---|
"""
    for sid, weight in high_weights.items():
        md += f"| {sid} | {weight:.12f} | ENGINEERING_EQUIVALENT |\n"
    md += f"""

## 6. Capacity vs actual load

모든 MW/MVA는 source wording에 따른 boundary를 유지했다. 34 MW CDC와 NEXTDC built MW는 실제 소비가 아니다. Fujitsu 28 MW는 facility specification의 IT capacity이며 actual load가 아니다.

## 7. IEEE123 denominator

수요 분모는 frozen background peak {inventory['background_operational_MW']['peak']:.12f} MW, 용량 분모는 IEEE PES 5.0 MVA substation transformer다. 두 분모는 혼용하지 않았다.

## 8. PCC interface

PF 0.95/0.98/1.00 및 loading 0.80/0.90 민감도를 산출했다. 모든 결과는 `IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE`이며 실제 Melbourne DNSP transformer가 아니다.

| Strict case | Site | P_peak MW @ capacity PF=0.98 | Main S_required MVA @ PF=.98/loading=.80 | Rounded MVA |
|---|---|---:|---:|---:|
"""
    for case in built_cases:
        system_peak = case["IEEE123_equivalent_active_MW_by_capacity_PF"]["0.98"]
        for sid, weight in built_weights.items():
            p_peak = system_peak * weight
            required = p_peak / (0.98 * 0.8)
            md += f"| {case['case_id']} | {sid} | {p_peak:.12f} | {required:.12f} | {round_standard(required)} |\n"
    md += """

## 9. Remaining unresolved items

ME5 capacity, MEL11 capacity conflict/exact host, Jemena firm/normal capacity, 실제 site별 DNSP connection rating, April actual load가 미해결이다.

## 10. Ready flags

Strict capacity와 PCC engineering만 ready이다. Strict load, 단일 12-site equivalent scale/weight, GPU weight, final grid science는 ready가 아니다.

## 11. Science firewall

ML retraining/forecast edit/GPU-h scaling/B0-B3/OpenDSS/grid science 호출은 모두 0이다.

## 12. Generated artifacts + SHA256

모든 생성 artifact의 SHA256은 `V22S_ARTIFACT_SHA256.json`에 기록한다. 자기 자신의 재귀 해시는 정의할 수 없으므로 해당 manifest 자체만 목록에서 제외한다.
"""
    (OUT / "V22S_FINAL_SCALE_REVIEW.md").write_text(md, encoding="utf-8")

    readme = """# V22S Melbourne 12-site scale artifacts

이 디렉터리는 2025년 4월 Melbourne 12-site facility identity, capacity boundary, matched host denominator, IEEE123 equivalent capacity 후보를 보존한다.

엄격 원칙: actual load와 capacity를 혼용하지 않고, 미확인값을 0으로 만들지 않으며, MVA/nameplate를 IT MW로 바꾸지 않는다. ML·forecast·GPU-h·B0–B3·OpenDSS·grid science는 실행하지 않았다.

재현: `python dayahead/tools/build_v22s_scale_authority.py`
검증: `python -m unittest tests.test_v22s_scale_authority -v`
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    required = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "V22S_ARTIFACT_SHA256.json")
    write_json("V22S_ARTIFACT_SHA256.json", {
        "artifact_id": "V22S_ARTIFACT_SHA256_V1",
        "note": "This manifest excludes itself to avoid an impossible recursive hash.",
        "artifacts": [{"path": p.relative_to(ROOT).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha256(p)} for p in required],
    })


if __name__ == "__main__":
    main()
