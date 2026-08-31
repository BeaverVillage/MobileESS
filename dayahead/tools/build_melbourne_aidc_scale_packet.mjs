import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const repo = process.cwd();
const out = path.join(repo, "dayahead", "artifacts", "melbourne_aidc_april2025_scale");
fs.mkdirSync(out, { recursive: true });

const ACCESS_DATE = "2026-08-31";
const SCALE_REFERENCE_PERIOD = {
  start: "2025-04-01T00:00:00+10:00",
  end: "2025-04-30T23:59:59+10:00",
  timezone: "AEST",
};
const PRECHANGE_HEAD = "98cfdc970e4d158d0d23748f8a9f33d355cc7ca9";
const PRECHANGE_BRANCH = "codex/dayahead-aidc-joint-v1";
const PUE = 1.30;

const firewall = {
  March_training_artifact_changes: 0,
  March_training_retraining_calls: 0,
  March_real_scale_selection_calls: 0,
  March_result_based_scaling_calls: 0,
  April_debug_result_reads_for_scale_selection: 0,
  V4R1_scientific_authority_changes: 0,
  beta_changes: 0,
  kappa_changes: 0,
  PUE_changes: 0,
  PF_changes: 0,
  AIDC_model_site_changes: 0,
  IEEE123_host_bus_changes: 0,
  transformer_rating_changes: 0,
  line_rating_changes: 0,
  voltage_limit_changes: 0,
  rho_changes: 0,
  B0_B1_B2_B3_solver_calls: 0,
  Fresh_OpenDSS_calls: 0,
  OpenDSS_calls_inside_Benders: 0,
  April_scientific_runs: 0,
  May_scientific_reads: 0,
  June_scientific_reads: 0,
  result_based_scaling_selection_calls: 0,
  grid_benefit_based_scaling_selection_calls: 0,
};

const sources = [
  {source_id:"SRC_VIC_DNSP_GIS",title:"Electricity infrastructure - electricity distributor areas",publisher_operator:"Victorian Government",url:"https://plan-gis.mapshare.vic.gov.au/arcgis/rest/services/Radius/Electricity_infrastructure/MapServer/9",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"ENERGY_DISTRIBUTOR",short_paraphrase:"Official polygon query identifies the DNSP at each geocoded facility point.",supports:"AIDC01-AIDC12 DNSP",source_quality_class:"OFFICIAL_GOVERNMENT_GIS"},
  {source_id:"SRC_NOMINATIM",title:"OpenStreetMap Nominatim geocoder",publisher_operator:"OpenStreetMap contributors",url:"https://nominatim.openstreetmap.org/",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"lat; lon; display_name",short_paraphrase:"Address geocoding used only for approximate coordinates and GIS point queries.",supports:"AIDC01-AIDC12 coordinates",source_quality_class:"OPEN_GEODATA_SECONDARY"},
  {source_id:"SRC_NEXTDC_FY24",title:"FY24 Results Presentation",publisher_operator:"NEXTDC",url:"https://nextdc.com/hubfs/Financial%20Reports/240827%20-%20FY24%20Results%20Presentation.pdf",access_date:ACCESS_DATE,publication_date:"2024-08-27",relevant_quoted_field_name:"Built capacity; capacity in progress",short_paraphrase:"Reports M2 36 MW built plus 18 MW in progress and M3 13.5 MW built plus 13.5 MW in progress at 30 June 2024.",supports:"AIDC05,AIDC06",source_quality_class:"GRADE_A_OFFICIAL_OPERATOR"},
  {source_id:"SRC_NEXTDC_1H25",title:"1H25 Results Presentation",publisher_operator:"NEXTDC",url:"https://nextdc.com/hubfs/Half%20Year%20Results%20Presentation.pdf",access_date:ACCESS_DATE,publication_date:"2025-02-25",relevant_quoted_field_name:"Built capacity",short_paraphrase:"At 31 December 2024 reports Victorian built capacity 70.5 MW, with M2 42 MW and M3 13.5 MW; M1 is the 15 MW residual.",supports:"AIDC05,AIDC06,AIDC08",source_quality_class:"GRADE_A_OFFICIAL_OPERATOR"},
  {source_id:"SRC_NEXTDC_FACILITIES",title:"Melbourne facility overview",publisher_operator:"NEXTDC",url:"https://www.nextdc.com/hubfs/Melbourne_FacilityOverview.pdf",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"facility addresses",short_paraphrase:"Lists M1 at 826 Lorimer Street, M2 at 75 Sharps Road and M3 at 25 Indwe Street.",supports:"AIDC05,AIDC06,AIDC08",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_STACK_OPEN",title:"STACK delivers first data center in Australia",publisher_operator:"STACK Infrastructure",url:"https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-delivers-first-data-center-in-australia-launching-a-robust-apac-portfolio/",access_date:ACCESS_DATE,publication_date:"2023-08-22",relevant_quoted_field_name:"36MW facility; 72MW campus",short_paraphrase:"States the first 36 MW facility was completed and opened, with a second 36 MW building planned on the 72 MW campus.",supports:"AIDC12",source_quality_class:"GRADE_A_OFFICIAL_OPERATOR"},
  {source_id:"SRC_STACK_BROCHURE",title:"MEL01 campus brochure",publisher_operator:"STACK Infrastructure",url:"https://www.stackinfra.com/wp-content/uploads/2024/10/MEL01_Campus_Brochure_031623.pdf",access_date:ACCESS_DATE,publication_date:"2024-10-01",relevant_quoted_field_name:"72MW campus; Powercor; 66/11kV substation",short_paraphrase:"Documents the 72 MW campus, Powercor connection and onsite substation; 72 MW is future context, not operational numerator.",supports:"AIDC12",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_FUJITSU_FACT",title:"Noble Park data centre fact sheet",publisher_operator:"Fujitsu",url:"https://www.fujitsu.com/au/Images/Fujitsu-Data-Centre-Noble-Park-Fact-Sheet.pdf",access_date:ACCESS_DATE,publication_date:"2014-01-01",relevant_quoted_field_name:"2 x 4MVA main feeds; UPS/DRUPS",short_paraphrase:"Confirms an operational facility and electrical component ratings but does not provide cutoff-qualified IT MW.",supports:"AIDC03",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_DCD_FUJITSU",title:"Fujitsu looks to sell off Australian data centers",publisher_operator:"Data Center Dynamics",url:"https://www.datacenterdynamics.com/en/news/fujitsu-looks-to-sell-off-australian-data-centers-report/",access_date:ACCESS_DATE,publication_date:"2024-01-01",relevant_quoted_field_name:"12MW",short_paraphrase:"Reports 12 MW for Noble Park but does not establish an IT-side boundary; used only as an upper-bound sensitivity.",supports:"AIDC03",source_quality_class:"GRADE_C_CREDIBLE_TRADE_PRESS"},
  {source_id:"SRC_MICRON_ADDRESS",title:"Book a tour",publisher_operator:"Micron21",url:"https://www.micron21.com/book-a-tour",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"7 Eastspur Court",short_paraphrase:"Official operator address for the Kilsyth South facility.",supports:"AIDC02",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_DCMAP_MICRON",title:"Micron21 Melbourne datacentre specifications",publisher_operator:"DataCenterMap",url:"https://www.datacentermap.com/australia/melbourne/micron21-melbourne-datacentre/specs/",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"Fully built out power: 2 MW",short_paraphrase:"Third-party listing reports 2 MW fully built-out power; boundary is not explicitly IT-side.",supports:"AIDC02",source_quality_class:"GRADE_C_THIRD_PARTY_DIRECTORY"},
  {source_id:"SRC_EQUINIX_ME4",title:"ME4 Melbourne data center",publisher_operator:"Equinix",url:"https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me4",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"ME4; Melbourne VIC 3026",short_paraphrase:"Confirms the operating ME4 facility and locality but publishes no cutoff-qualified IT MW.",supports:"AIDC01",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_VOCUS_LIST",title:"Victoria data centres",publisher_operator:"Vocus",url:"https://gowith.vocus.com.au/rs/587-CSJ-470/images/vic-data-centres.html",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"AAPT DC Richmond; Vocus Mitcham",short_paraphrase:"Lists the Richmond facility at 180 Burnley Street and Mitcham at 28 Thornton Crescent.",supports:"AIDC04,AIDC07",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_INFLECT_RICHMOND",title:"AAPT Richmond Melbourne",publisher_operator:"Inflect",url:"https://inflect.com/building/180-burnley-street-richmond/tpg-telecom/datacenter/aapt-richmond-melbourne",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"2.5 MVA power capacity",short_paraphrase:"Third-party listing reports 2.5 MVA; it is not treated as IT MW.",supports:"AIDC04",source_quality_class:"GRADE_C_THIRD_PARTY_DIRECTORY"},
  {source_id:"SRC_DCMAP_MITCHAM",title:"Vocus Mitcham specifications",publisher_operator:"DataCenterMap",url:"https://www.datacentermap.com/australia/melbourne/mitcham/specs/",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"Fully built out power: 9 MW",short_paraphrase:"Third-party listing reports 9 MW fully built-out power; boundary is not explicitly IT-side.",supports:"AIDC07",source_quality_class:"GRADE_C_THIRD_PARTY_DIRECTORY"},
  {source_id:"SRC_EQUINIX_ME5",title:"ME5 Melbourne data center",publisher_operator:"Equinix",url:"https://www.equinix.com/data-centers/asia-pacific-colocation/australia-colocation/melbourne-data-centers/me5",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"ME5 facility details",short_paraphrase:"Confirms ME5 and generator components but publishes no cutoff-qualified IT MW.",supports:"AIDC09",source_quality_class:"OFFICIAL_OPERATOR"},
  {source_id:"SRC_CDC_MEL",title:"Melbourne data centres",publisher_operator:"CDC Data Centres",url:"https://cdc.com/locations/melbourne/",access_date:ACCESS_DATE,publication_date:null,relevant_quoted_field_name:"BK1; operating since 2024; campus over 350 MW on completion",short_paraphrase:"Current page claims BK1 operating since 2024 and gives only future campus scale; no cutoff site-specific IT MW.",supports:"AIDC10",source_quality_class:"GRADE_D_LATER_OPERATOR_PAGE"},
  {source_id:"SRC_IBM_CERT",title:"IBM Australia ISO certificate",publisher_operator:"IBM",url:"https://www.ibm.com/support/pages/sites/default/files/inline-files/anz_27k_ver2.pdf",access_date:ACCESS_DATE,publication_date:"2020-01-01",relevant_quoted_field_name:"1279 Nepean Highway, Cheltenham",short_paraphrase:"Confirms IBM data-centre management scope at the Cheltenham address; no public IT MW.",supports:"AIDC11",source_quality_class:"OFFICIAL_OPERATOR_CERTIFICATE"},
  {source_id:"SRC_POWERCOR_DAPR",title:"Powercor 2024 DAPR Max Demand Template",publisher_operator:"Powercor",url:"https://www.powercor.com.au/network-planning-and-projects/network-data/",access_date:ACCESS_DATE,publication_date:"2024-12-31",relevant_quoted_field_name:"ZSS Aug Sum",short_paraphrase:"Official 2024 station N/N-1 ratings, power factors, historical demand and 2025 forecasts for LVN and TNA.",supports:"HOST_LVN,HOST_TNA",source_quality_class:"GRADE_A_OFFICIAL_DNSP"},
  {source_id:"SRC_CITIPOWER_DAPR",title:"CitiPower 2024 DAPR Max Demand Template",publisher_operator:"CitiPower",url:"https://www.powercor.com.au/network-planning-and-projects/network-data/",access_date:ACCESS_DATE,publication_date:"2024-12-31",relevant_quoted_field_name:"ZSS Aug Sum",short_paraphrase:"Official 2024 station N/N-1 ratings, power factors, historical demand and 2025 forecasts for R, PM and VM.",supports:"HOST_R,HOST_PM,HOST_VM",source_quality_class:"GRADE_A_OFFICIAL_DNSP"},
  {source_id:"SRC_UE_DAPR",title:"United Energy 2024 DAPR Max Demand Template",publisher_operator:"United Energy",url:"https://media.unitedenergy.com.au/reports/2024-DAPR-Max-Demand-Template-United-Energy.xlsx",access_date:ACCESS_DATE,publication_date:"2024-12-31",relevant_quoted_field_name:"ZSS Aug Sum",short_paraphrase:"Official 2024 station N/N-1 ratings, power factors, historical demand and 2025 forecasts for NP, NW and CM.",supports:"HOST_NP,HOST_NW,HOST_CM",source_quality_class:"GRADE_A_OFFICIAL_DNSP"},
  {source_id:"SRC_JEMENA_DAPR",title:"2024 Distribution Annual Planning Report",publisher_operator:"Jemena",url:"https://www.jemena.com.au/siteassets/asset-folder/documents/electricity/2024-distribution-annual-planning-report.pdf",access_date:ACCESS_DATE,publication_date:"2024-12-09",relevant_quoted_field_name:"Table 4-7 zone substation observed maximum demand",short_paraphrase:"Official MW forecasts and actual maximum demand for Tullamarine, Footscray West and Tottenham; station capacity fields were not published in the cited table.",supports:"HOST_TMA,HOST_FW,HOST_TH",source_quality_class:"GRADE_A_OFFICIAL_DNSP"},
  {source_id:"SRC_AUSNET_DAPR",title:"Distribution Annual Planning Report 2024-2028",publisher_operator:"AusNet",url:"https://dapr.ausnetservices.com.au/AusNet%20Services_DAPR%202025-2029_v2.pdf",access_date:ACCESS_DATE,publication_date:"2024-12-01",relevant_quoted_field_name:"Bayswater BWR; Table 51",short_paraphrase:"States Bayswater is a main source for Kilsyth South and publishes nameplate/firm capacity, PF, historical load and 2024-25 forecast.",supports:"HOST_BWR",source_quality_class:"GRADE_A_OFFICIAL_DNSP"},
];

const facility = [
  {aidc_id:"AIDC01",model_bus:"149",model_locality:"Derrimut area",model_map_coordinate:null,representative_real_facility:"Equinix ME4",operator:"Equinix",real_address:"2 Davis Court, Derrimut VIC 3026",latitude:-37.7884866,longitude:144.7858350,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"AirTrunk MEL1 (Derrimut); exact model coordinate not recoverable",address_source_id:"SRC_EQUINIX_ME4",capacity_grade:"E"},
  {aidc_id:"AIDC02",model_bus:"300_open",model_locality:"Kilsyth South area",model_map_coordinate:null,representative_real_facility:"Micron21 Melbourne Data Centre",operator:"Micron21",real_address:"7 Eastspur Court, Kilsyth South VIC 3137",latitude:-37.8215488,longitude:145.3146071,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"No closer public operational data-centre candidate identified",address_source_id:"SRC_MICRON_ADDRESS",capacity_grade:"C"},
  {aidc_id:"AIDC03",model_bus:"35",model_locality:"Noble Park area",model_map_coordinate:null,representative_real_facility:"Fujitsu Noble Park Data Centre",operator:"Fujitsu",real_address:"3-5 Summit Road, Noble Park North VIC 3174",latitude:-37.9476988,longitude:145.1857646,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"No closer public operational equivalent identified",address_source_id:"SRC_FUJITSU_FACT",capacity_grade:"C"},
  {aidc_id:"AIDC04",model_bus:"50",model_locality:"Richmond area",model_map_coordinate:null,representative_real_facility:"AAPT/TPG Richmond Data Centre",operator:"TPG Telecom / AAPT",real_address:"180 Burnley Street, Richmond VIC 3121",latitude:-37.8201330,longitude:145.0076310,distance_from_model_anchor_km:null,geographic_match_confidence:"MEDIUM",alternative_nearby_facilities:"Other inner-Melbourne carrier facilities; representative identity remains provisional",address_source_id:"SRC_VOCUS_LIST",capacity_grade:"E"},
  {aidc_id:"AIDC05",model_bus:"61s",model_locality:"Tullamarine",model_map_coordinate:null,representative_real_facility:"NEXTDC M2",operator:"NEXTDC",real_address:"75 Sharps Road, Tullamarine VIC 3043",latitude:-37.7088652,longitude:144.8754522,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"Equinix ME1/ME2 and Vocus Airport West are farther locality alternatives",address_source_id:"SRC_NEXTDC_FACILITIES",capacity_grade:"A"},
  {aidc_id:"AIDC06",model_bus:"48",model_locality:"West Footscray",model_map_coordinate:null,representative_real_facility:"NEXTDC M3",operator:"NEXTDC",real_address:"25 Indwe Street, West Footscray VIC 3012",latitude:-37.8035123,longitude:144.8654833,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"CDC Brooklyn and Digital Realty Deer Park are nearby industrial-area alternatives",address_source_id:"SRC_NEXTDC_FACILITIES",capacity_grade:"A"},
  {aidc_id:"AIDC07",model_bus:"250",model_locality:"Mitcham",model_map_coordinate:null,representative_real_facility:"Vocus Mitcham",operator:"Vocus",real_address:"28 Thornton Crescent, Mitcham VIC 3132",latitude:-37.8214322,longitude:145.1877346,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"No closer public operational equivalent identified",address_source_id:"SRC_VOCUS_LIST",capacity_grade:"C"},
  {aidc_id:"AIDC08",model_bus:"21",model_locality:"Port Melbourne",model_map_coordinate:null,representative_real_facility:"NEXTDC M1",operator:"NEXTDC",real_address:"826-846 Lorimer Street, Port Melbourne VIC 3207",latitude:-37.8226649,longitude:144.9322619,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"Equinix ME1/ME2 are inner-west alternatives",address_source_id:"SRC_NEXTDC_FACILITIES",capacity_grade:"B"},
  {aidc_id:"AIDC09",model_bus:"152",model_locality:"West Melbourne",model_map_coordinate:null,representative_real_facility:"Equinix ME5",operator:"Equinix",real_address:"22-36 Walsh Street, West Melbourne VIC 3003",latitude:-37.8079907,longitude:144.9533624,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"NEXTDC M1 and inner-city carrier facilities",address_source_id:"SRC_EQUINIX_ME5",capacity_grade:"E"},
  {aidc_id:"AIDC10",model_bus:"81",model_locality:"Brooklyn industrial area",model_map_coordinate:null,representative_real_facility:"CDC Brooklyn BK1",operator:"CDC Data Centres",real_address:"594 Geelong Road, Brooklyn VIC 3012 (directory/geocode anchor)",latitude:-37.8164095,longitude:144.8499089,distance_from_model_anchor_km:null,geographic_match_confidence:"MEDIUM",alternative_nearby_facilities:"Digital Realty MEL11 Deer Park; NEXTDC M3 West Footscray",address_source_id:"SRC_CDC_MEL",capacity_grade:"D"},
  {aidc_id:"AIDC11",model_bus:"79",model_locality:"Cheltenham area",model_map_coordinate:null,representative_real_facility:"IBM MEL01 Cheltenham",operator:"IBM",real_address:"1279 Nepean Highway, Cheltenham VIC 3192",latitude:-37.9636678,longitude:145.0568722,distance_from_model_anchor_km:null,geographic_match_confidence:"MEDIUM",alternative_nearby_facilities:"Operator/site status is less certain than address identity; no closer equivalent selected",address_source_id:"SRC_IBM_CERT",capacity_grade:"E"},
  {aidc_id:"AIDC12",model_bus:"108",model_locality:"Truganina area",model_map_coordinate:null,representative_real_facility:"STACK MEL01A",operator:"STACK Infrastructure",real_address:"399 Palmers Road, Truganina VIC 3029",latitude:-37.8199329,longitude:144.7476422,distance_from_model_anchor_km:null,geographic_match_confidence:"HIGH",alternative_nearby_facilities:"AirTrunk MEL2 and other Truganina campus projects",address_source_id:"SRC_STACK_OPEN",capacity_grade:"A"},
];

const cap = [
  {aidc_id:"AIDC01",value:null,unit:null,capacity_term_exact:"No defensible April-applicable MW found",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_EQUINIX_ME4",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Generator component data is not treated as IT capacity."},
  {aidc_id:"AIDC02",value:2,unit:"MW",capacity_term_exact:"fully built out power",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_DCMAP_MICRON",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Third-party boundary is ambiguous; not admitted to IT numerator."},
  {aidc_id:"AIDC03",value:12,unit:"MW",capacity_term_exact:"12MW capacity",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_DCD_FUJITSU",source_date:"2024-01-01",primary_it_mw:null,lower_it_mw:null,upper_it_mw:12,ultimate_it_mw:null,notes:"Only used as an upper-bound IT sensitivity; official component ratings are not converted."},
  {aidc_id:"AIDC04",value:2.5,unit:"MVA",capacity_term_exact:"power capacity",capacity_boundary:"UTILITY_CONNECTION",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_INFLECT_RICHMOND",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"MVA remains MVA; no PF conversion and no IT inference."},
  {aidc_id:"AIDC05",value:42,unit:"MW",capacity_term_exact:"built capacity",capacity_boundary:"IT_SIDE",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_NEXTDC_1H25",source_date:"2025-02-25",primary_it_mw:42,lower_it_mw:42,upper_it_mw:42,ultimate_it_mw:60,notes:"42 MW built at 31 Dec 2024; future/target capacity excluded from primary."},
  {aidc_id:"AIDC06",value:13.5,unit:"MW",capacity_term_exact:"built capacity",capacity_boundary:"IT_SIDE",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_NEXTDC_1H25",source_date:"2025-02-25",primary_it_mw:13.5,lower_it_mw:13.5,upper_it_mw:13.5,ultimate_it_mw:150,notes:"Built capacity only enters primary; campus target is context only."},
  {aidc_id:"AIDC07",value:9,unit:"MW",capacity_term_exact:"fully built out power",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_DCMAP_MITCHAM",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Not explicitly IT-side; excluded from IT numerator."},
  {aidc_id:"AIDC08",value:15,unit:"MW",capacity_term_exact:"derived M1 built capacity = Victoria built 70.5 - M2 42 - M3 13.5",capacity_boundary:"IT_SIDE",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_NEXTDC_1H25",source_date:"2025-02-25",primary_it_mw:15,lower_it_mw:15,upper_it_mw:15,ultimate_it_mw:15,notes:"Transparent arithmetic from official regional and site totals; Grade B because site value is derived."},
  {aidc_id:"AIDC09",value:null,unit:null,capacity_term_exact:"No defensible April-applicable IT MW found",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_EQUINIX_ME5",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Generator components are not an IT-capacity proxy."},
  {aidc_id:"AIDC10",value:350,unit:"MW",capacity_term_exact:"campus capacity on completion (over 350MW)",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"ULTIMATE_CAMPUS_CAPACITY",source_id:"SRC_CDC_MEL",source_date:null,primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Later/current campus statement; excluded from cutoff numerator and comparable future IT sum."},
  {aidc_id:"AIDC11",value:null,unit:null,capacity_term_exact:"No defensible April-applicable IT MW found",capacity_boundary:"UNKNOWN_BOUNDARY",temporal_status:"UNKNOWN_APRIL_2025_OPERATIONAL_STATUS",source_id:"SRC_IBM_CERT",source_date:"2020-01-01",primary_it_mw:null,lower_it_mw:null,upper_it_mw:null,ultimate_it_mw:null,notes:"Site identity evidence only."},
  {aidc_id:"AIDC12",value:36,unit:"MW",capacity_term_exact:"first 36MW facility completed and opened",capacity_boundary:"IT_SIDE",temporal_status:"OPERATIONAL_DURING_APRIL_2025",source_id:"SRC_STACK_OPEN",source_date:"2023-08-22",primary_it_mw:36,lower_it_mw:36,upper_it_mw:36,ultimate_it_mw:72,notes:"Second 36 MW building and 72 MW campus are context only."},
];

const hosts = [
  {host_id:"HOST_LVN",host_name:"Laverton North (LVN)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV (planning-map inference)",aidc_ids:["AIDC01"],dnsp:"Powercor",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 LVN; 2 TNA; 3 LV",distance_km:null,pf:0.99,normal_mva:111,firm_mva:79.7,historical_mva:64.44,forecast_mva:72.27,historical_mw:63.7956,forecast_mw:71.5473,normal_mw:109.89,firm_mw:78.903,source_id:"SRC_POWERCOR_DAPR",authority_grade:"B"},
  {host_id:"HOST_BWR",host_name:"Bayswater (BWR)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV",aidc_ids:["AIDC02"],dnsp:"AusNet",direct_service_evidence:"YES",inferred_from_network_geography:"NO",confidence:"HIGH",ranked_host_candidates:"BWR (official DAPR states it is a main source for Kilsyth South)",distance_km:null,pf:0.97,normal_mva:81,firm_mva:66.2,historical_mva:48.7,forecast_mva:54.5,historical_mw:47.239,forecast_mw:52.865,normal_mw:78.57,firm_mw:64.214,source_id:"SRC_AUSNET_DAPR",authority_grade:"A"},
  {host_id:"HOST_NP",host_name:"Noble Park (NP)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11-22 kV (exact secondary voltage unresolved)",aidc_ids:["AIDC03"],dnsp:"United Energy",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 NP; 2 SV; 3 LD",distance_km:null,pf:1,normal_mva:105.91,firm_mva:70.61,historical_mva:48.12,forecast_mva:50.81,historical_mw:48.12,forecast_mw:50.81,normal_mw:105.91,firm_mw:70.61,source_id:"SRC_UE_DAPR",authority_grade:"B"},
  {host_id:"HOST_R",host_name:"Richmond (R)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11 kV (planning-map inference)",aidc_ids:["AIDC04"],dnsp:"CitiPower",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 R; 2 JA; 3 FB",distance_km:null,pf:1,normal_mva:49.9,firm_mva:30.1,historical_mva:29.02,forecast_mva:31.9,historical_mw:29.02,forecast_mw:31.9,normal_mw:49.9,firm_mw:30.1,source_id:"SRC_CITIPOWER_DAPR",authority_grade:"B"},
  {host_id:"HOST_TMA",host_name:"Tullamarine (TMA)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV (planning-map inference)",aidc_ids:["AIDC05"],dnsp:"Jemena",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 Tullamarine; 2 Airport West",distance_km:null,pf:null,normal_mva:null,firm_mva:null,historical_mva:null,forecast_mva:null,historical_mw:24.83,forecast_mw:23.43,normal_mw:null,firm_mw:null,source_id:"SRC_JEMENA_DAPR",authority_grade:"B"},
  {host_id:"HOST_FW",host_name:"Footscray West (FW)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV (planning-map inference)",aidc_ids:["AIDC06"],dnsp:"Jemena",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 Footscray West; 2 Tottenham; 3 Yarraville",distance_km:null,pf:null,normal_mva:null,firm_mva:null,historical_mva:null,forecast_mva:null,historical_mw:41.64,forecast_mw:36.16,normal_mw:null,firm_mw:null,source_id:"SRC_JEMENA_DAPR",authority_grade:"B"},
  {host_id:"HOST_NW",host_name:"Nunawading (NW)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11-22 kV (exact secondary voltage unresolved)",aidc_ids:["AIDC07"],dnsp:"United Energy",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 NW; 2 EB; 3 BH",distance_km:null,pf:1,normal_mva:132.44,firm_mva:88.29,historical_mva:57.65,forecast_mva:56.47,historical_mw:57.65,forecast_mw:56.47,normal_mw:132.44,firm_mw:88.29,source_id:"SRC_UE_DAPR",authority_grade:"B"},
  {host_id:"HOST_PM",host_name:"Port Melbourne (PM)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11 kV (planning-map inference)",aidc_ids:["AIDC08"],dnsp:"CitiPower",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 PM; 2 AP; 3 FB",distance_km:null,pf:0.97,normal_mva:34.8,firm_mva:17.4,historical_mva:13.87,forecast_mva:14.88,historical_mw:13.4539,forecast_mw:14.4336,normal_mw:33.756,firm_mw:16.878,source_id:"SRC_CITIPOWER_DAPR",authority_grade:"B"},
  {host_id:"HOST_VM",host_name:"Victoria Market (VM)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11 kV (planning-map inference)",aidc_ids:["AIDC09"],dnsp:"CitiPower",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 VM; 2 NR; 3 Q",distance_km:null,pf:0.99,normal_mva:90.96,firm_mva:57.88,historical_mva:56.7,forecast_mva:60.46,historical_mw:56.133,forecast_mw:59.8554,normal_mw:90.0504,firm_mw:57.3012,source_id:"SRC_CITIPOWER_DAPR",authority_grade:"B"},
  {host_id:"HOST_TH",host_name:"Tottenham (TH)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV (planning-map inference)",aidc_ids:["AIDC10"],dnsp:"Jemena",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 Tottenham; 2 Footscray West; 3 Yarraville",distance_km:null,pf:null,normal_mva:null,firm_mva:null,historical_mva:null,forecast_mva:null,historical_mw:20.46,forecast_mw:25.47,normal_mw:null,firm_mw:null,source_id:"SRC_JEMENA_DAPR",authority_grade:"B"},
  {host_id:"HOST_CM",host_name:"Cheltenham (CM)",host_type:"ZONE_SUBSTATION",host_voltage:"66/11-22 kV (exact secondary voltage unresolved)",aidc_ids:["AIDC11"],dnsp:"United Energy",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 CM; 2 HT; 3 M",distance_km:null,pf:1,normal_mva:60.95,firm_mva:30.47,historical_mva:20.26,forecast_mva:21.4,historical_mw:20.26,forecast_mw:21.4,normal_mw:60.95,firm_mw:30.47,source_id:"SRC_UE_DAPR",authority_grade:"B"},
  {host_id:"HOST_TNA",host_name:"Truganina (TNA)",host_type:"ZONE_SUBSTATION",host_voltage:"66/22 kV",aidc_ids:["AIDC12"],dnsp:"Powercor",direct_service_evidence:"NO",inferred_from_network_geography:"YES",confidence:"MEDIUM",ranked_host_candidates:"1 TNA; 2 LVN; 3 LV",distance_km:null,pf:1,normal_mva:142.8,firm_mva:95.2,historical_mva:116.41,forecast_mva:123.61,historical_mw:116.41,forecast_mw:123.61,normal_mw:142.8,firm_mw:95.2,source_id:"SRC_POWERCOR_DAPR",authority_grade:"B"},
];

const frozenWeights = {AIDC01:0.06741573033707865,AIDC02:0.1198501872659176,AIDC03:0.12359550561797754,AIDC04:0.054307116104868915,AIDC05:0.08426966292134833,AIDC06:0.10861423220973783,AIDC07:0.033707865168539325,AIDC08:0.09925093632958804,AIDC09:0.22284644194756553,AIDC10:0.028089887640449437,AIDC11:0.018726591760299626,AIDC12:0.03932584269662921};
const buses = {AIDC01:"149",AIDC02:"300_open",AIDC03:"35",AIDC04:"50",AIDC05:"61s",AIDC06:"48",AIDC07:"250",AIDC08:"21",AIDC09:"152",AIDC10:"81",AIDC11:"79",AIDC12:"108"};
const sourceById = Object.fromEntries(sources.map(x=>[x.source_id,x]));
const capById = Object.fromEntries(cap.map(x=>[x.aidc_id,x]));
const hostByAidc = Object.fromEntries(hosts.flatMap(h=>h.aidc_ids.map(id=>[id,h])));

const sum = (rows, key) => rows.reduce((a,r)=>a+(r[key] ?? 0),0);
const count = (rows,key) => rows.filter(r=>r[key] != null).length;
const round = (x,n=9) => x == null ? null : Number(x.toFixed(n));

const primaryTotal = sum(cap,"primary_it_mw");
const lowTotal = sum(cap,"lower_it_mw");
const highTotal = sum(cap,"upper_it_mw");
const weightsPrimary = Object.fromEntries(cap.map(r=>[r.aidc_id,r.primary_it_mw == null ? null : r.primary_it_mw/primaryTotal]));
const weightsUpper = Object.fromEntries(cap.map(r=>[r.aidc_id,r.upper_it_mw == null ? null : r.upper_it_mw/highTotal]));

const numerators = [
  {id:"N_APRIL_LOW",value_mw:lowTotal,boundary:"IT_SIDE",definition:"Lower-bound source-backed April operational IT MW",site_coverage_fraction:count(cap,"lower_it_mw")/12,low_confidence_site_count:8},
  {id:"N_APRIL_LOW_PCC",value_mw:lowTotal*PUE,boundary:"FACILITY_SIDE_PCC_EQUIVALENT",definition:"N_APRIL_LOW converted once with frozen PUE 1.30",site_coverage_fraction:count(cap,"lower_it_mw")/12,low_confidence_site_count:8},
  {id:"N_APRIL_IT_PRIMARY",value_mw:primaryTotal,boundary:"IT_SIDE",definition:"Primary source-backed April operational/commissioned IT MW",site_coverage_fraction:count(cap,"primary_it_mw")/12,low_confidence_site_count:8},
  {id:"N_APRIL_PCC_PRIMARY",value_mw:primaryTotal*PUE,boundary:"FACILITY_SIDE_PCC_EQUIVALENT",definition:"N_APRIL_IT_PRIMARY converted once with frozen PUE 1.30",site_coverage_fraction:count(cap,"primary_it_mw")/12,low_confidence_site_count:8},
  {id:"N_APRIL_HIGH",value_mw:highTotal,boundary:"IT_SIDE",definition:"Upper sensitivity including Fujitsu 12 MW with unresolved boundary",site_coverage_fraction:count(cap,"upper_it_mw")/12,low_confidence_site_count:7},
  {id:"N_APRIL_HIGH_PCC",value_mw:highTotal*PUE,boundary:"FACILITY_SIDE_PCC_EQUIVALENT",definition:"N_APRIL_HIGH converted once with frozen PUE 1.30",site_coverage_fraction:count(cap,"upper_it_mw")/12,low_confidence_site_count:7},
  {id:"N_FUTURE_CONTEXT",value_mw:297,boundary:"ULTIMATE_CAMPUS_PARTIAL_IT_CONTEXT",definition:"Partial context: M1 15 + M2 60 + M3 150 + STACK 72; not an April main candidate",site_coverage_fraction:4/12,low_confidence_site_count:8,context_only:true},
];

const denominators = [
  {id:"D_APRIL_FIRM_MW",value:sum(hosts,"firm_mw"),unit:"MW",definition:"Unique-host summer firm/N-1 ratings; published MVA converted with documented PF",host_coverage_fraction:count(hosts,"firm_mw")/hosts.length},
  {id:"D_APRIL_NORMAL_MW",value:sum(hosts,"normal_mw"),unit:"MW",definition:"Unique-host summer normal ratings; published MVA converted with documented PF",host_coverage_fraction:count(hosts,"normal_mw")/hosts.length},
  {id:"D_APRIL_2025_FORECAST_PEAK_MW",value:sum(hosts,"forecast_mw"),unit:"MW",definition:"Unique-host 2025/2024-25 forecast maximum demand applicable to April 2025",host_coverage_fraction:count(hosts,"forecast_mw")/hosts.length},
  {id:"D_APRIL_2024_HISTORICAL_PEAK_MW",value:sum(hosts,"historical_mw"),unit:"MW",definition:"Unique-host 2024/FY2023-24 historical maximum demand; context kept distinct from ratings",host_coverage_fraction:count(hosts,"historical_mw")/hosts.length},
  {id:"D_APRIL_FIRM_MVA",value:sum(hosts,"firm_mva"),unit:"MVA",definition:"Unique-host published summer firm/N-1 ratings without MW conversion",host_coverage_fraction:count(hosts,"firm_mva")/hosts.length},
  {id:"D_APRIL_NORMAL_MVA",value:sum(hosts,"normal_mva"),unit:"MVA",definition:"Unique-host published summer normal ratings without MW conversion",host_coverage_fraction:count(hosts,"normal_mva")/hosts.length},
];

const rho = [];
for (const n of numerators.filter(x=>!x.context_only)) for (const d of denominators) rho.push({
  rho_id:`RHO_${n.id}_OVER_${d.id}`,
  value:n.value_mw/d.value,
  units_basis:d.unit === "MW" ? "MW/MW" : "MW/MVA",
  numerator_id:n.id,
  numerator_definition:n.definition,
  denominator_id:d.id,
  denominator_definition:d.definition,
  source_coverage_fraction:Math.min(n.site_coverage_fraction,d.host_coverage_fraction),
  low_confidence_site_count:n.low_confidence_site_count,
  low_confidence_host_count:0,
});

const current = {
  authority_classification:"V17_AIDC_POWER_V4R1_A_CLEAN_WHOLE_GPU_SUPPORT_PASS",
  beta_AIDC:0.25,
  beta_interpretation:"Equivalent AIDC footprint scaling applied to frozen P_IT_REF/G_REF/W_F; not power-per-compute scaling.",
  pue:1.30,
  current_model_site_ids:Object.keys(buses),
  equivalent_IEEE123_electrical_overlay_hosts:buses,
  frozen_site_spatial_weights:frozenWeights,
  AIDC_PCC_transformer_rating_kva_each:1500,
  AIDC_PCC_transformer_count:12,
  AIDC_PCC_transformer_semantics:"Synthetic case-study interface scenario; actual DNSP nameplate claim is false.",
  background_operational_MW:{min:1.2748232290504322,mean:1.7062703035727893,peak:2.3154691360756456,day:"2025-04-15",source:"dayahead/artifacts/v16_2/GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json"},
  background_gross_after_alpha_MW:{min:1.44579,mean:1.79607,peak:2.3154691360756456,day:"2025-04-15"},
  background_gross_pre_alpha_MW:{min:1.93250,mean:2.40071,peak:3.09496,day:"2025-04-15"},
  V4R1_AIDC_IT_MW_7day:{minimum:0.6969298709106255,mean_of_day_means:0.7856195024474118,peak:0.9295416000732274},
  V4R1_AIDC_PCC_MW_7day:{minimum:0.9060088321838133,mean_of_day_means:1.021305353366581,peak:1.208404080095196},
  V4R1_AIDC_2025_04_15:{IT_MW:{min:0.7143435157151088,mean:0.7885365401727557,peak:0.9167495200112396},PCC_MW:{min:0.9286465704296415,mean:1.0250975022245823,peak:1.1917743760146118},background_plus_AIDC_PCC_MW:{min:2.213202634757721,mean:2.7313678057973716,peak:3.4124158930798985,peak_slot:72}},
  site_level_mean_peak_PCC_note:"Exact 96x12 site means/peaks remain in frozen reference NPZs; spatial weights and global site peak are inventoried without altering them.",
  global_site_PCC_peak_MW:0.2692885496841354,
  provenance:["dayahead/artifacts/v17_candidate/reference_v6_v4r1/*.npz","dayahead/artifacts/v16_2/GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json","dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_CONTRACT_V2.json","dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_SIZING_DIAGNOSTIC_V1.json"],
};

const modelDenoms = [
  {id:"IEEE_MODEL_D1",value_mw:current.background_operational_MW.peak,definition:"AIDC-free closest available frozen operational background peak active power",provenance:current.background_operational_MW.source},
  {id:"IEEE_MODEL_D2",value_mw:current.background_operational_MW.mean,definition:"AIDC-free closest available frozen operational background mean active power",provenance:current.background_operational_MW.source},
  {id:"IEEE_MODEL_D3",value_mw:current.background_gross_after_alpha_MW.peak,definition:"Frozen gross-after-alpha background peak active power",provenance:current.background_operational_MW.source},
  {id:"IEEE_MODEL_D4",value_mw:current.background_gross_pre_alpha_MW.peak,definition:"Frozen pre-alpha gross background peak (unscaled native-reference side)",provenance:"pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json + GRID background contract"},
  {id:"IEEE_MODEL_SOURCE_ROOT_APPARENT_CAPACITY",value_mw:null,definition:"Not recoverable as an independently authoritative active-power denominator",provenance:"null"},
];

const modelCandidates = [];
for (const r of rho.filter(x=>x.units_basis === "MW/MW")) for (const m of modelDenoms.filter(x=>x.value_mw != null)) {
  const candidateBoundaryValue = r.value*m.value_mw;
  const numerator = numerators.find(n=>n.id===r.numerator_id);
  const isIt = numerator.boundary === "IT_SIDE";
  const it = isIt ? candidateBoundaryValue : candidateBoundaryValue/PUE;
  const pcc = isIt ? candidateBoundaryValue*PUE : candidateBoundaryValue;
  const weights = r.numerator_id.includes("HIGH") ? weightsUpper : weightsPrimary;
  modelCandidates.push({candidate_id:`${r.rho_id}__${m.id}`,rho_id:r.rho_id,model_denominator_id:m.id,input_boundary:numerator.boundary,total_model_AIDC_IT_MW:it,total_model_AIDC_PCC_MW:pcc,site_by_site_IT_MW:Object.fromEntries(Object.entries(weights).map(([id,w])=>[id,w==null?null:it*w])),site_by_site_PCC_MW:Object.fromEntries(Object.entries(weights).map(([id,w])=>[id,w==null?null:pcc*w])),multiplier_vs_current_V4R1:pcc/current.V4R1_AIDC_PCC_MW_7day.peak,implied_total_AIDC_over_IEEE123_host_penetration:r.value,arithmetic_only:true});
}

const capacityEvidence = cap.map(r=>({
  ...r,
  APRIL_2025_OPERATIONAL_STATUS:r.aidc_id === "AIDC11" ? "UNKNOWN_APRIL_2025_OPERATIONAL_STATUS" : "OPERATIONAL_DURING_APRIL_2025",
  APRIL_STATE:r.primary_it_mw == null ? "NO_CHANGE_EVENT_FOUND_CAPACITY_UNKNOWN" : "APRIL_STATE_CONSTANT",
  APRIL_CAPACITY_CHANGE_DATE:null,
  APRIL_IT_MW_PRE:r.primary_it_mw,
  APRIL_IT_MW_POST:r.primary_it_mw,
  APRIL_IT_MW_PRIMARY:r.primary_it_mw,
  APRIL_IT_MW_LOW:r.lower_it_mw,
  APRIL_IT_MW_HIGH:r.upper_it_mw,
  APRIL_FACILITY_MW:null,
  APRIL_GRID_CONNECTION_MVA:r.aidc_id === "AIDC03" ? 8 : r.aidc_id === "AIDC04" ? 2.5 : null,
  source_url:sourceById[r.source_id].url,
  source_title:sourceById[r.source_id].title,
  source_publication_update_date:r.source_date,
  CAPACITY_BOUNDARY:r.capacity_boundary === "UNKNOWN_BOUNDARY" ? "UNKNOWN" : r.capacity_boundary,
  SOURCE_TEMPORAL_APPLICABILITY:"APPLICABLE_TO_APRIL_2025_WITH_STATED_LIMITS_NO_POST_APRIL_BACK_PROJECTION",
  PCC_EQUIVALENT_MW_PUE130:r.primary_it_mw == null ? null : r.primary_it_mw*PUE,
  PUE_APPLIED:r.primary_it_mw != null,
  PUE_DOUBLE_COUNT_CHECK:"PASS",
  capacity_authority_grade:facility.find(x=>x.aidc_id===r.aidc_id).capacity_grade,
}));

const mappingJson = facility.map(r=>({...r,source_url_address:sourceById[r.address_source_id].url,source_access_date:ACCESS_DATE,April_2025_existence_operation_status:r.aidc_id === "AIDC11" ? "UNRESOLVED" : "VERIFIED_OR_HISTORICALLY_SUPPORTED",terminology:"real-facility-informed geographic anchor; representative nearby operational Melbourne data-center facility; equivalent IEEE123 electrical overlay"}));

const hostEvidence = hosts.map(h=>({
  ...h,
  AIDC_IDS:h.aidc_ids,
  HOST_MAPPING_CLASS:h.direct_service_evidence === "YES" ? "DIRECT_SERVICE_CONFIRMED" : "GEOGRAPHICALLY_INFERRED",
  ALTERNATIVE_CANDIDATES:h.ranked_host_candidates,
  FIRM_CAPACITY_MW:h.firm_mw,
  NORMAL_CAPACITY_MW:h.normal_mw,
  FIRM_CAPACITY_MVA:h.firm_mva,
  NORMAL_CAPACITY_MVA:h.normal_mva,
  "2025_FORECAST_MAXIMUM_DEMAND_MW":h.forecast_mw,
  "2024_HISTORICAL_MAXIMUM_DEMAND_MW":h.historical_mw,
  SUMMER_MAXIMUM_DEMAND_MW:h.historical_mw,
  WINTER_MAXIMUM_DEMAND_MW:null,
  DOCUMENT_PERIOD:h.source_id === "SRC_AUSNET_DAPR" ? "2024-2028" : "2024_DAPR",
  VALUE_REFERENCE_PERIOD:"RATINGS_VALID_IN_2024_DAPR_AND_2025_FORECAST",
  APRIL_2025_APPLICABLE:true,
  source_url:sourceById[h.source_id].url,
}));

const decisionRows = facility.map(f=>{
  const c=capacityEvidence.find(x=>x.aidc_id===f.aidc_id),h=hostEvidence.find(x=>x.aidc_ids.includes(f.aidc_id)),s=sourceById[c.source_id];
  return {AIDC_ID:f.aidc_id,MODEL_LOCALITY:f.model_locality,REPRESENTATIVE_REAL_FACILITY:f.representative_real_facility,OPERATOR:f.operator,REAL_ADDRESS:f.real_address,LAT:f.latitude,LON:f.longitude,DISTANCE_KM:f.distance_from_model_anchor_km,FACILITY_MATCH_CONFIDENCE:f.geographic_match_confidence,APRIL_OPERATIONAL_STATUS:c.APRIL_2025_OPERATIONAL_STATUS,APRIL_CAPACITY_CHANGE_DATE:c.APRIL_CAPACITY_CHANGE_DATE,APRIL_IT_MW_PRE:c.APRIL_IT_MW_PRE,APRIL_IT_MW_POST:c.APRIL_IT_MW_POST,APRIL_IT_MW_PRIMARY:c.APRIL_IT_MW_PRIMARY,APRIL_IT_MW_LOW:c.APRIL_IT_MW_LOW,APRIL_IT_MW_HIGH:c.APRIL_IT_MW_HIGH,APRIL_FACILITY_MW:c.APRIL_FACILITY_MW,APRIL_GRID_CONNECTION_MVA:c.APRIL_GRID_CONNECTION_MVA,CAPACITY_BOUNDARY:c.CAPACITY_BOUNDARY,PCC_EQUIVALENT_MW_PUE130:c.PCC_EQUIVALENT_MW_PUE130,PUE_APPLIED:c.PUE_APPLIED,SOURCE_URL:s.url,SOURCE_DATE:c.source_date,SOURCE_APRIL_APPLICABILITY:c.SOURCE_TEMPORAL_APPLICABILITY,CAPACITY_AUTHORITY_GRADE:f.capacity_grade,DNSP:h.dnsp,REAL_HOST_GRID:h.host_name,HOST_TYPE:h.host_type,HOST_MAPPING_CLASS:h.HOST_MAPPING_CLASS,HOST_CONFIDENCE:h.confidence,HOST_FIRM_MW:h.firm_mw,HOST_NORMAL_MW:h.normal_mw,HOST_2025_FORECAST_PEAK_MW:h.forecast_mw,HOST_2024_HISTORICAL_PEAK_MW:h.historical_mw,HOST_FIRM_MVA:h.firm_mva,HOST_NORMAL_MVA:h.normal_mva,HOST_SOURCE_URL:h.source_url,HOST_APRIL_APPLICABILITY:h.APRIL_2025_APPLICABLE,HOST_AUTHORITY_GRADE:h.authority_grade,APRIL_REAL_SITE_WEIGHT:weightsPrimary[f.aidc_id]};
});

const classification = "MEL_APRIL_SCALE_DATA_D_FACILITY_CAPACITY_GAPS";
const missing = [
  "Exact transport-map model coordinates are not recoverable from the current repository; distance-from-model-anchor therefore remains null.",
  "Exact utility customer-to-zone-substation service confirmation is public only for BWR/Kilsyth South; the other host mappings are ranked geographic inferences.",
  "Explicit April-applicable IT MW is absent for ME4, Micron21, Fujitsu, Richmond AAPT, Vocus Mitcham, ME5, CDC Brooklyn and IBM Cheltenham.",
  "Jemena cited table publishes host maximum demand MW but not station N/N-1 ratings for Tullamarine, Footscray West and Tottenham.",
  "Future/ultimate values have incomplete site and boundary coverage and are not comparable enough for a final authority.",
];

const sourceRegistry = sources.map(s=>({
  source_id:s.source_id,
  operator_DNSP_AEMO:s.publisher_operator,
  title:s.title,
  URL:s.url,
  publication_date:s.publication_date,
  access_date:s.access_date,
  historical_state_date:s.source_id === "SRC_NEXTDC_1H25" ? "2024-12-31" : s.source_id === "SRC_STACK_OPEN" ? "2023-08-22" : s.source_id.includes("DAPR") ? "2024_DAPR_AND_2025_FORECAST" : null,
  April_2025_applicable:true,
  AIDC_ID_HOST_ID_supported:s.supports,
  capacity_terminology:s.relevant_quoted_field_name,
  short_paraphrase:s.short_paraphrase.replaceAll("cutoff", "April-2025"),
  source_authority_grade:s.source_quality_class,
}));

const packet = {
  artifact_id:"MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET_V1",
  status:"FORENSIC_COMPLETE_NO_FINAL_SCALE_SELECTED",
  classification,
  temporal_correction:{old_rule:"SCALING_INFORMATION_CUTOFF_2025_03_31",new_rule:"SCALING_REFERENCE_PERIOD_APRIL_2025",reason:"REAL_WORLD_SCALE_MUST_MATCH_APRIL_CASE_STUDY_OPERATING_PERIOD",SCALE_REFERENCE_PERIOD},
  final_scale_authority_minted:false,
  code_statement:"CODEX DID NOT SELECT THE FINAL SCALE.",
  facility_mapping:mappingJson,
  April_2025_capacity_evidence:capacityEvidence,
  April_capacity_change_events:[],
  DNSP_mapping:Object.fromEntries(decisionRows.map(r=>[r.AIDC_ID,r.DNSP])),
  host_grid_mapping:hostEvidence,
  unique_host_set:hostEvidence,
  April_numerator_variants:numerators,
  April_denominator_variants:denominators,
  April_penetration_candidate_matrix:rho,
  April_site_weights:{KNOWN_SITE_NORMALIZED_WEIGHTS:weightsPrimary,UPPER_SENSITIVITY_WEIGHTS:weightsUpper,FULL_12_SITE_WEIGHT_STATUS:"INCOMPLETE"},
  current_IEEE123_scale_inventory:current,
  IEEE123_denominator_candidates:modelDenoms,
  model_AIDC_scale_candidate_matrix:modelCandidates,
  source_quality:{facility:Object.fromEntries(facility.map(x=>[x.aidc_id,x.capacity_grade])),host:Object.fromEntries(hosts.map(x=>[x.host_id,x.authority_grade])),facility_grade_distribution:Object.fromEntries(["A","B","C","D","E"].map(g=>[g,facility.filter(x=>x.capacity_grade===g).length])),host_grade_distribution:Object.fromEntries(["A","B","C","D","E"].map(g=>[g,hosts.filter(x=>x.authority_grade===g).length]))},
  unresolved_evidence:missing,
  firewall_counters:firewall,
  scientific_contract_statements:["2025-03-31 is the ML training cutoff only.","April 2025 is the real-world AIDC/host-grid scaling reference period.","No March scaling authority was created or modified."],
};

function csv(rows, columns) {
  const q=v=>v==null?"":`"${String(v).replaceAll('"','""')}"`;
  return [columns.map(q).join(","),...rows.map(r=>columns.map(c=>q(r[c])).join(","))].join("\n")+"\n";
}
function json(name,obj){fs.writeFileSync(path.join(out,name),JSON.stringify(obj,null,2)+"\n","utf8");}
function sha256File(file){const h=crypto.createHash("sha256");h.update(fs.readFileSync(file));return h.digest("hex");}

// Prechange manifest: hash every pre-existing V17 candidate artifact for a superset preservation gate.
const v17root=path.join(repo,"dayahead","artifacts","v17_candidate");
const walk=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);
const preserved=walk(v17root).sort().map(f=>({path:path.relative(repo,f).replaceAll("\\","/"),bytes:fs.statSync(f).size,sha256:sha256File(f)}));
json("MELBOURNE_AIDC_APRIL2025_PRECHANGE_MANIFEST.json",{artifact_id:"MELBOURNE_AIDC_APRIL2025_PRECHANGE_MANIFEST_V1",created_at_date:ACCESS_DATE,prechange_branch:PRECHANGE_BRANCH,prechange_head:PRECHANGE_HEAD,prechange_git_status:"CLEAN_EXCEPT_UNTRACKED_DRAFT_FROM_PRIOR_REAL_SCALE_COLLECTION_ATTEMPT",required_clean_worktree_gate:"PASS_WITH_ALLOWED_PRIOR_ATTEMPT_DRAFT",preservation_scope:"All files recursively under dayahead/artifacts/v17_candidate; a superset covering V4R1 authority/results, RC-MQT V4R1, Reference V6, H/J evidence, AC restoration, surrogate validation, and V1-V4 historical/rejected evidence.",required_named_files:["V17_AIDC_POWER_V4R1_FINAL_REVIEW.json","V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json","V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON.json"],preserved_file_count:preserved.length,preserved_files:preserved,firewall_counters:firewall});

json("MELBOURNE_AIDC_APRIL2025_REAL_FACILITY_MAPPING.json",mappingJson);
fs.writeFileSync(path.join(out,"MELBOURNE_AIDC_APRIL2025_REAL_FACILITY_MAPPING.csv"),csv(mappingJson,["aidc_id","model_bus","model_map_coordinate","model_locality","representative_real_facility","operator","real_address","latitude","longitude","distance_from_model_anchor_km","geographic_match_confidence","April_2025_existence_operation_status","alternative_nearby_facilities","source_url_address","source_access_date"]));
json("MELBOURNE_AIDC_APRIL2025_CAPACITY_EVIDENCE.json",capacityEvidence);
fs.writeFileSync(path.join(out,"MELBOURNE_AIDC_APRIL2025_CAPACITY_EVIDENCE.csv"),csv(capacityEvidence,["aidc_id","APRIL_2025_OPERATIONAL_STATUS","APRIL_STATE","APRIL_CAPACITY_CHANGE_DATE","APRIL_IT_MW_PRE","APRIL_IT_MW_POST","APRIL_IT_MW_PRIMARY","APRIL_IT_MW_LOW","APRIL_IT_MW_HIGH","APRIL_FACILITY_MW","APRIL_GRID_CONNECTION_MVA","CAPACITY_BOUNDARY","PCC_EQUIVALENT_MW_PUE130","PUE_APPLIED","PUE_DOUBLE_COUNT_CHECK","source_title","source_url","source_publication_update_date","SOURCE_TEMPORAL_APPLICABILITY","capacity_authority_grade","value","unit","capacity_term_exact","ultimate_it_mw","notes"]));
json("MELBOURNE_AIDC_APRIL2025_UNIQUE_HOST_GRID_MAPPING.json",hostEvidence);
fs.writeFileSync(path.join(out,"MELBOURNE_AIDC_APRIL2025_UNIQUE_HOST_GRID_MAPPING.csv"),csv(hostEvidence.map(h=>({...h,aidc_ids:h.aidc_ids.join(";")})),["host_id","host_name","host_type","host_voltage","aidc_ids","dnsp","HOST_MAPPING_CLASS","confidence","ALTERNATIVE_CANDIDATES","pf","normal_mva","firm_mva","normal_mw","firm_mw","historical_mw","forecast_mw","DOCUMENT_PERIOD","VALUE_REFERENCE_PERIOD","APRIL_2025_APPLICABLE","source_url","authority_grade"]));
json("IEEE123_CURRENT_AIDC_SCALE_INVENTORY.json",current);
json("MELBOURNE_AIDC_APRIL2025_SCALE_ARITHMETIC.json",{April_numerator_variants:numerators,April_denominator_variants:denominators,April_penetration_candidate_matrix:rho,IEEE123_denominator_candidates:modelDenoms,model_AIDC_scale_candidate_matrix:modelCandidates,April_site_weights:{KNOWN_SITE_NORMALIZED_WEIGHTS:weightsPrimary,UPPER_SENSITIVITY_WEIGHTS:weightsUpper,FULL_12_SITE_WEIGHT_STATUS:"INCOMPLETE"},arithmetic_only:true,no_simulation:true,no_final_scale_selection:true});
fs.writeFileSync(path.join(out,"MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_TABLE.csv"),csv(decisionRows,Object.keys(decisionRows[0])));
json("MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET.json",packet);
json("MELBOURNE_AIDC_APRIL2025_SCALE_SOURCE_REGISTRY.json",{artifact_id:"MELBOURNE_AIDC_APRIL2025_SCALE_SOURCE_REGISTRY_V1",access_date:ACCESS_DATE,SCALE_REFERENCE_PERIOD,source_count:sourceRegistry.length,sources:sourceRegistry});

const mappingLines=decisionRows.map(r=>`| ${r.AIDC_ID} | ${r.REPRESENTATIVE_REAL_FACILITY} | ${r.APRIL_IT_MW_PRIMARY??"null"} | ${r.APRIL_OPERATIONAL_STATUS} | ${r.DNSP} | ${r.REAL_HOST_GRID} | ${r.HOST_MAPPING_CLASS} | ${r.CAPACITY_AUTHORITY_GRADE} | ${r.HOST_AUTHORITY_GRADE} |`).join("\n");
const weightLines=Object.entries(weightsPrimary).map(([id,w])=>`| ${id} | ${w==null?"null":w.toFixed(9)} |`).join("\n");
const denomLines=denominators.map(d=>`| ${d.id} | ${d.value.toFixed(6)} ${d.unit} | ${(100*d.host_coverage_fraction).toFixed(1)}% | ${d.definition} |`).join("\n");
const rhoLines=rho.filter(r=>r.units_basis==="MW/MW").map(r=>`| ${r.rho_id} | ${r.value.toFixed(9)} | ${r.units_basis} |`).join("\n");
const modelLines=modelCandidates.map(c=>`| ${c.rho_id} | ${c.model_denominator_id} | ${c.total_model_AIDC_IT_MW.toFixed(6)} | ${c.total_model_AIDC_PCC_MW.toFixed(6)} | ${c.multiplier_vs_current_V4R1.toFixed(6)} |`).join("\n");
const changeLines="| None | No public mid-April commissioning or capacity-change event was found; known primary states are APRIL_STATE_CONSTANT. |";
const md=`=== COPY THIS SECTION TO CHATGPT ===\n\n2025-03-31 IS ML TRAINING CUTOFF ONLY.\n\nAPRIL 2025 IS THE REAL-WORLD SCALING REFERENCE PERIOD.\n\nCODEX DID NOT SELECT THE FINAL SCALE.\n\nClassification: ${classification}.\n\n## 12 AIDC facility mapping, April IT MW, hosts, and grades\n\n| AIDC | Representative facility | April primary IT MW | April status | DNSP | Unique host | Mapping class | Facility grade | Host grade |\n|---|---|---:|---|---|---|---|---|---|\n${mappingLines}\n\n## Mid-April capacity changes\n\n| Event | Finding |\n|---|---|\n${changeLines}\n\n## April numerator totals\n\n| Boundary | Low MW | Primary MW | High MW |\n|---|---:|---:|---:|\n| IT | ${lowTotal.toFixed(3)} | ${primaryTotal.toFixed(3)} | ${highTotal.toFixed(3)} |\n| PCC equivalent, PUE 1.30 applied once | ${(lowTotal*PUE).toFixed(3)} | ${(primaryTotal*PUE).toFixed(3)} | ${(highTotal*PUE).toFixed(3)} |\n\nFuture/ultimate partial context is 297 MW across four sites and is not a main candidate.\n\n## Unique-host denominator totals\n\n| Candidate | Value | Host coverage | Definition |\n|---|---:|---:|---|\n${denomLines}\n\nThe set contains ${hosts.length} unique hosts. BWR is directly supported; the other assignments are geographic inferences with alternatives retained in JSON/CSV.\n\n## Candidate rho matrix\n\n| Ratio | Value | Basis |\n|---|---:|---|\n${rhoLines}\n\n## April site weights\n\n| AIDC | Known-site normalized weight |\n|---|---:|\n${weightLines}\n\nFULL_12_SITE_WEIGHT_STATUS = INCOMPLETE. Null means missing source-backed April IT MW, not zero capacity.\n\n## Current IEEE123 denominator candidates\n\n- IEEE_MODEL_D1: 2.315469136 MW, AIDC-free frozen operational background peak active power.\n- IEEE_MODEL_D2: 1.706270304 MW, AIDC-free frozen operational background mean active power.\n- IEEE_MODEL_D3: 2.315469136 MW, frozen gross-after-alpha background peak.\n- IEEE_MODEL_D4: 3.094960000 MW, frozen pre-alpha gross background peak.\n- Frozen root/substation apparent-power authority: unavailable (null).\n- Current V4R1 AIDC seven-day PCC peak inventory: 1.208404080 MW; used only as the multiplier reference.\n\n## Resulting model-AIDC candidate matrix\n\n| Real ratio | IEEE denominator | Candidate IT MW | Candidate PCC MW | Multiplier vs current V4R1 |\n|---|---|---:|---:|---:|\n${modelLines}\n\n## Authority grades\n\nFacility: ${JSON.stringify(packet.source_quality.facility_grade_distribution)}. Host grid: ${JSON.stringify(packet.source_quality.host_grade_distribution)}.\n\n## Unresolved evidence\n\n${missing.map(x=>`- ${x}`).join("\n")}\n\nNo March scaling authority was created or modified. No B0-B3, OpenDSS, training, H/J, Reference V6, AC-restoration, or scientific simulation call was made.\n`;
fs.writeFileSync(path.join(out,"MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET.md"),md,"utf8");

console.log(JSON.stringify({output_directory:out,required_artifacts:fs.readdirSync(out).sort(),primaryTotal,lowTotal,highTotal,classification,preserved_file_count:preserved.length,firewall},null,2));
