"""Frozen V16.2 AIDC PCC transformer asset and contract utilities."""

from __future__ import annotations

import csv
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence


AUTHORITY_ID = "V16_2_DA_AIDC_ICPS_AIDC_PCC_1500KVA"
FREEZE_TOKEN = "V16_2_AIDC_PCC_1500KVA_PREMAY_FREEZE_20260829"
V3_SHA256 = "3c3e27020e266dc8f1c4e28e90d49f298d6ca741ef6b54599e44265882cd747c"
MAPPING_SHA256 = "c3763567f6785f182ab151ca0390918017d4e24c2733f6d72d2304bba416322e"
AIDC_RATING_KVA = 1500.0
MESS_RATING_KVA = 750.0
AUTHORITY_SHA256 = "53392a53ac73930fa1336cfd8daf97497fcb455f0569162bf3608c0459759a2d"


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    temporary.replace(path)


def transformer_records(text: str) -> tuple[dict[str, object], ...]:
    pattern = re.compile(
        r"(?m)^New Transformer\.(?P<name>\S+) Phases=(?P<phases>\d+) Windings=2 "
        r"XHL=(?P<xhl>\S+) %R=(?P<resistance>\S+) %NoLoadLoss=(?P<noload>\S+) %Imag=(?P<imag>\S+)\r?\n"
        r"~ Buses=\[(?P<primary>[^.\s]+)(?:\.1\.2\.3)? (?P<secondary>[^\]]+)\] Conns=\[(?P<connections>[^\]]+)\]\r?\n"
        r"~ kVs=\[(?P<primary_kv>\S+) (?P<secondary_kv>\S+)\] kVAs=\[(?P<primary_kva>\S+) (?P<secondary_kva>\S+)\]"
    )
    rows: list[dict[str, object]] = []
    for match in pattern.finditer(text):
        values = match.groupdict()
        rows.append({
            "name": values["name"],
            "phases": int(values["phases"]),
            "xhl_percent": float(values["xhl"]),
            "resistance_percent": float(values["resistance"]),
            "no_load_loss_percent": float(values["noload"]),
            "imag_percent": float(values["imag"]),
            "primary_host_bus": values["primary"],
            "secondary_pcc_bus": values["secondary"],
            "connections": values["connections"],
            "primary_kv": float(values["primary_kv"]),
            "secondary_kv": float(values["secondary_kv"]),
            "primary_kva": float(values["primary_kva"]),
            "secondary_kva": float(values["secondary_kva"]),
        })
    return tuple(rows)


def generate_v4_bytes(v3_bytes: bytes) -> tuple[bytes, int]:
    if sha256(v3_bytes).hexdigest() != V3_SHA256:
        raise ValueError("GENERATED_THREE_PHASE_PCC_V3_SHA_MISMATCH")
    text = v3_bytes.decode("utf-8-sig")
    pattern = re.compile(
        r"(?m)(^New Transformer\.IDC_IDC\d{2}_TX\b[^\r\n]*\r?\n"
        r"~ Buses=\[[^\]]+\] Conns=\[[^\]]+\]\r?\n"
        r"~ kVs=\[4\.16 0\.48\] kVAs=)\[750 750\]"
    )
    updated, count = pattern.subn(r"\g<1>[1500 1500]", text)
    if count != 12:
        raise ValueError(f"V16_2_AIDC_TRANSFORMER_REPLACEMENT_COUNT:{count}")
    return updated.encode("utf-8"), count


def _host_mapping(records: Sequence[Mapping[str, object]]) -> dict[str, str]:
    return {str(row["name"]): str(row["primary_host_bus"]) for row in records}


def _mapping_rows(path: Path) -> tuple[dict[str, str], ...]:
    if sha256_file(path) != MAPPING_SHA256:
        raise ValueError("PCC_MAPPING_SOURCE_SHA_MISMATCH")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return tuple(dict(row) for row in csv.DictReader(stream))


def validate_v4(v3_path: Path, v4_path: Path, mapping_path: Path) -> dict[str, object]:
    v3_bytes = v3_path.read_bytes()
    v4_bytes = v4_path.read_bytes()
    expected_v4, replacement_count = generate_v4_bytes(v3_bytes)
    if v4_bytes != expected_v4:
        raise ValueError("V4_BYTES_NOT_EXACT_PROSPECTIVE_TRANSFORMATION")
    v3_records = transformer_records(v3_bytes.decode("utf-8-sig"))
    v4_records = transformer_records(v4_bytes.decode("utf-8-sig"))
    if len(v3_records) != 36 or len(v4_records) != 36:
        raise ValueError("PCC_TRANSFORMER_RECORD_COUNT_MISMATCH")
    aidc = tuple(row for row in v4_records if str(row["name"]).startswith("IDC_IDC"))
    mess = tuple(row for row in v4_records if str(row["name"]).startswith("MESS_"))
    if len(aidc) != 12 or len(mess) != 24:
        raise ValueError("V16_2_AIDC_MESS_TRANSFORMER_AXIS_MISMATCH")
    if any(row["primary_kva"] != AIDC_RATING_KVA or row["secondary_kva"] != AIDC_RATING_KVA for row in aidc):
        raise ValueError("V16_2_AIDC_RATING_MISMATCH")
    if any(row["primary_kva"] != MESS_RATING_KVA or row["secondary_kva"] != MESS_RATING_KVA for row in mess):
        raise ValueError("V16_2_MESS_RATING_CHANGED")
    if any(row["phases"] != 3 or row["primary_kv"] != 4.16 or row["secondary_kv"] != 0.48 for row in v4_records):
        raise ValueError("V16_2_PCC_VOLTAGE_OR_PHASE_CHANGED")
    if _host_mapping(v3_records) != _host_mapping(v4_records):
        raise ValueError("V16_2_PCC_HOST_MAPPING_CHANGED")
    mapping = _mapping_rows(mapping_path)
    expected_hosts: dict[str, str] = {}
    for row in mapping:
        service = row["service_node_id"]
        host = row["electrical_host_bus"]
        if service.startswith("IDC"):
            expected_hosts[f"IDC_{service}_TX"] = host
            expected_hosts[f"MESS_{service}_TX"] = host
        elif service.startswith("STA"):
            expected_hosts[f"MESS_{service}_TX"] = host
    if _host_mapping(v4_records) != expected_hosts:
        raise ValueError("V16_2_PCC_MAPPING_SOURCE_BINDING_MISMATCH")
    v3_by_name = {str(row["name"]): row for row in v3_records}
    nonrating_fields = (
        "name", "phases", "xhl_percent", "resistance_percent", "no_load_loss_percent",
        "imag_percent", "primary_host_bus", "secondary_pcc_bus", "connections", "primary_kv", "secondary_kv",
    )
    if any(any(row[field] != v3_by_name[str(row["name"])][field] for field in nonrating_fields) for row in v4_records):
        raise ValueError("V16_2_NONRATING_PCC_PROPERTY_CHANGED")
    return {
        "status": "PASS",
        "v3_sha256": sha256(v3_bytes).hexdigest(),
        "v4_sha256": sha256(v4_bytes).hexdigest(),
        "aidc_transformer_count": len(aidc),
        "mess_transformer_count": len(mess),
        "aidc_ratings_kva": {str(row["name"]): row["primary_kva"] for row in aidc},
        "mess_ratings_kva": {str(row["name"]): row["primary_kva"] for row in mess},
        "primary_secondary_kv": [4.16, 0.48],
        "phases": 3,
        "host_mapping": _host_mapping(v4_records),
        "host_mapping_identity": True,
        "nonrating_electrical_property_identity": True,
        "aidc_rating_replacement_count": replacement_count,
        "mess_pcc_rating_change_count": 0,
        "mapping_source_sha256": MAPPING_SHA256,
    }


def materialize_v4_contract(
    *, v3_path: Path, v4_path: Path, mapping_path: Path, authority_path: Path, contract_path: Path,
) -> dict[str, object]:
    if sha256_file(authority_path) != AUTHORITY_SHA256:
        raise ValueError("V16_2_AUTHORITY_SHA_MISMATCH")
    v4_path.parent.mkdir(parents=True, exist_ok=True)
    v4_bytes, _count = generate_v4_bytes(v3_path.read_bytes())
    temporary = v4_path.with_suffix(v4_path.suffix + ".tmp")
    temporary.write_bytes(v4_bytes)
    temporary.replace(v4_path)
    audit = validate_v4(v3_path, v4_path, mapping_path)
    contract = {
        "artifact_id": "AIDC_PCC_TRANSFORMER_CONTRACT_V2",
        "authority_id": AUTHORITY_ID,
        "authority_path": str(authority_path),
        "authority_sha256": AUTHORITY_SHA256,
        "status": "PASS_FROZEN_V16_2",
        "freeze_token": FREEZE_TOKEN,
        "generated_three_phase_pcc_v3": {"path": str(v3_path), "sha256": audit["v3_sha256"], "role": "HISTORICAL_EVIDENCE_ONLY"},
        "generated_three_phase_pcc_v4": {"path": str(v4_path), "sha256": audit["v4_sha256"], "role": "ACTIVE_V16_2_PCC_ASSET"},
        "aidc_transformer_count": 12,
        "aidc_ratings_kva": audit["aidc_ratings_kva"],
        "mess_transformer_count": 24,
        "mess_ratings_kva": audit["mess_ratings_kva"],
        "mess_pcc_rating_change_count": 0,
        "mess_pcs_rating_kva": 700.0,
        "voltage_ratio_kv": [4.16, 0.48],
        "phases": 3,
        "mapping_source": str(mapping_path),
        "mapping_source_sha256": MAPPING_SHA256,
        "host_mapping_identity_v3_v4": audit["host_mapping_identity"],
        "host_mapping": audit["host_mapping"],
        "nonrating_electrical_property_identity_v3_v4": audit["nonrating_electrical_property_identity"],
        "synthetic_case_study_interface_scenario": True,
        "actual_nameplate_claim": False,
        "hard_constraint_semantics": {
            "transformer_current_loading_max_pu": 1.0,
            "transformer_kva_loading_max_pu": 1.0,
            "rating_fitting_runtime_call_count": 0,
            "transformer_rating_optimization_variable_count": 0,
            "transformer_constraint_slack_variable_count": 0,
            "post_freeze_rating_change_allowed": False,
        },
        "firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
        },
    }
    _write_json(contract_path, contract)
    return {"v4_sha256": audit["v4_sha256"], "contract_sha256": sha256_file(contract_path), "audit": audit}
