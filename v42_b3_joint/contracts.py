"""Immutable, content-addressed software interfaces; no scientific equations."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def require_sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "SHA256_REQUIRED")


def seal_json(value, name):
    require(isinstance(value, str), name + "_CANONICAL_JSON_REQUIRED")
    data = json.loads(value, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    require(isinstance(data, dict) and bool(data), name + "_NONEMPTY_OBJECT_REQUIRED")
    return canonical(data)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "FINITE_NUMBER_REQUIRED")
    return value


def matrix(value, rows, cols, *, strings=False):
    result = tuple(tuple(row) for row in value)
    require(len(result) == rows and all(len(row) == cols for row in result), "INTERFACE_AXIS_MISMATCH")
    for row in result:
        for cell in row:
            if strings:
                require(isinstance(cell, str) and bool(cell), "LOCATION_ID_REQUIRED")
            else:
                number(cell)
    return result


@dataclass(frozen=True)
class Authority:
    day: str
    input_sha: str
    grid_sha: str
    pcc_mapping_sha: str
    physical_domain_sha: str
    forecast_sha: str
    runtime_sha: str
    source_sha: str
    planning_cutoff: str
    forecast_available_at: str
    pcc_ids: tuple
    mess_ids: tuple
    slots: tuple = tuple(range(96))
    actual_observations_used: bool = False

    def __post_init__(self):
        require(date.fromisoformat(self.day).isoformat() == self.day, "ISO_DAY_REQUIRED")
        for key in ("input_sha", "grid_sha", "pcc_mapping_sha", "physical_domain_sha", "forecast_sha", "runtime_sha", "source_sha"):
            require_sha(getattr(self, key))
        for key in ("pcc_ids", "mess_ids", "slots"):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        require(self.slots == tuple(range(96)) and all(type(x) is int for x in self.slots), "96_SLOT_AXIS_REQUIRED")
        require(len(self.pcc_ids) == 12 and len(set(self.pcc_ids)) == 12, "12_DISTINCT_PCC_REQUIRED")
        require(len(self.mess_ids) > 0 and len(set(self.mess_ids)) == len(self.mess_ids), "DISTINCT_MESS_REQUIRED")
        require(all(isinstance(x, str) and x for x in self.pcc_ids + self.mess_ids), "PHYSICAL_AXIS_IDS_REQUIRED")
        cutoff = datetime.fromisoformat(self.planning_cutoff)
        available = datetime.fromisoformat(self.forecast_available_at)
        require(cutoff.utcoffset() is not None and available.utcoffset() is not None, "TIMEZONE_AWARE_CAUSAL_AUTHORITY_REQUIRED")
        operating_cutoff = cutoff.astimezone(timezone(timedelta(hours=9)))
        require(available <= cutoff and operating_cutoff.date() < date.fromisoformat(self.day), "PLANNING_FUTURE_INFORMATION_FORBIDDEN")
        require(self.actual_observations_used is False, "ACTUAL_FUTURE_OBSERVATIONS_FORBIDDEN")

    def to_dict(self):
        return asdict(self)

    @property
    def sha(self):
        return digest(self.to_dict())


@dataclass(frozen=True)
class AIDCDecision:
    jobs_json: str
    it_power: tuple
    pcc_p: tuple
    pcc_q: tuple
    gpu_runtime_json: str
    variables_json: str

    def __post_init__(self):
        for key in ("jobs_json", "gpu_runtime_json", "variables_json"):
            object.__setattr__(self, key, seal_json(getattr(self, key), key))
        require({"known_job_actions", "unknown_arrival_policy"} <= set(json.loads(self.jobs_json)), "CAUSAL_JOB_POLICY_REQUIRED")
        require({"gpu", "rack", "wan", "qos", "runtime"} <= set(json.loads(self.gpu_runtime_json)), "AIDC_RESOURCE_STATE_REQUIRED")
        for key in ("it_power", "pcc_p", "pcc_q"):
            object.__setattr__(self, key, matrix(getattr(self, key), 12, 96))

    def to_dict(self):
        return asdict(self)

    @property
    def sha(self):
        return digest(self.to_dict())


@dataclass(frozen=True)
class MESSDecision:
    routes: tuple
    location: tuple
    charge_p: tuple
    discharge_p: tuple
    q: tuple
    soc: tuple
    initial_final_json: str
    move_energy: tuple
    variables_json: str

    def __post_init__(self):
        routes = tuple(tuple(row) for row in self.routes)
        require(len(routes) > 0 and all(row and all(isinstance(x, str) and x for x in row) for row in routes), "ALL_MESS_ROUTES_REQUIRED")
        n_mess = len(routes)
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "location", matrix(self.location, n_mess, 96, strings=True))
        for key in ("charge_p", "discharge_p", "q", "move_energy"):
            object.__setattr__(self, key, matrix(getattr(self, key), n_mess, 96))
        object.__setattr__(self, "soc", matrix(self.soc, n_mess, 97))
        for key in ("initial_final_json", "variables_json"):
            object.__setattr__(self, key, seal_json(getattr(self, key), key))
        require({"initial", "final"} <= set(json.loads(self.initial_final_json)), "INITIAL_FINAL_MESS_STATE_REQUIRED")
        require({"movement", "charge_mode", "route", "P", "Q", "SOC"} <= set(json.loads(self.variables_json)), "FULL_MESS_DECISION_FAMILIES_REQUIRED")

    def to_dict(self):
        return asdict(self)

    @property
    def sha(self):
        return digest(self.to_dict())


@dataclass(frozen=True)
class Certificate:
    stage: str
    authority_sha: str
    fixed_input_sha: str
    decision_sha: str
    lower_bound: str | None
    upper_bound: str | None
    global_domain_sha: str
    verifier_source_sha: str
    original_global_bound_verified: bool
    evidence_kind: str
    bound_scope: str = "STAGE_FIXED_INPUT_GLOBAL"
    objective: str = "min rho_max"
    p2_calls: int = 0
    original_model_sha: str = ""


@dataclass(frozen=True)
class PhysicalReceipt:
    stage: str
    authority_sha: str
    fixed_input_sha: str
    decision_sha: str
    replay_sha: str
    verifier_source_sha: str
    original_integer_physical_verified: bool
    evidence_kind: str
    original_model_sha: str = ""


@dataclass(frozen=True)
class WarmStartCandidate:
    authority_sha: str
    fixed_aidc_sha: str
    mess: MESSDecision
    eligible: bool
    feasibility_verified: bool
    reason: str

    def __post_init__(self):
        require_sha(self.authority_sha)
        require_sha(self.fixed_aidc_sha)
        require(isinstance(self.mess, MESSDecision), "TYPED_WARM_START_MESS_REQUIRED")
        require(type(self.eligible) is bool and type(self.feasibility_verified) is bool, "WARM_START_BOOLEAN_EVIDENCE_REQUIRED")
        require(isinstance(self.reason, str) and bool(self.reason), "WARM_START_REASON_REQUIRED")


@dataclass(frozen=True)
class StageRequest:
    stage: str
    authority: Authority
    fixed_aidc: AIDCDecision | None = None
    fixed_mess: MESSDecision | None = None
    warm_start: WarmStartCandidate | None = None

    def __post_init__(self):
        from .policy import STAGES
        require(self.stage in STAGES[:4], "OPTIMIZATION_STAGE_REQUIRED")
        require(isinstance(self.authority, Authority), "FROZEN_AUTHORITY_REQUIRED")
        require((self.fixed_aidc is not None) == self.stage.startswith("M"), "M_STAGE_FIXED_AIDC_REQUIRED")
        require((self.fixed_mess is not None) == (self.stage == "A2"), "A2_FIXED_MESS_REQUIRED_A1_MESS_OFF")
        require(self.fixed_aidc is None or isinstance(self.fixed_aidc, AIDCDecision), "TYPED_AIDC_REQUIRED")
        require(self.fixed_mess is None or isinstance(self.fixed_mess, MESSDecision), "TYPED_MESS_REQUIRED")
        require(self.fixed_mess is None or len(self.fixed_mess.routes) == len(self.authority.mess_ids), "FIXED_MESS_AUTHORITY_AXIS")
        if self.warm_start is not None:
            require(self.stage == "M2" and isinstance(self.warm_start, WarmStartCandidate), "M2_WARM_START_ONLY")
            require(self.warm_start.authority_sha == self.authority.sha, "WARM_START_AUTHORITY_DRIFT")
            if self.warm_start.eligible:
                require(self.warm_start.feasibility_verified is True and self.warm_start.fixed_aidc_sha == self.fixed_aidc.sha, "WARM_START_NEW_ANCHOR_FEASIBILITY_REQUIRED")

    @property
    def fixed_input_sha(self):
        return digest({"stage": self.stage, "authority_sha": self.authority.sha,
                       "fixed_aidc_sha": self.fixed_aidc.sha if self.fixed_aidc else None,
                       "fixed_mess_sha": self.fixed_mess.sha if self.fixed_mess else None,
                       "MESS_optimization_off": self.stage == "A1"})

    @property
    def request_sha(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class StageResult:
    stage: str
    authority: Authority
    aidc: AIDCDecision | None
    mess: MESSDecision | None
    certificate: Certificate
    physical: PhysicalReceipt
    native_receipt: str
    fixed_input_sha: str

    def __post_init__(self):
        require(isinstance(self.authority, Authority), "RESULT_AUTHORITY_REQUIRED")
        require(isinstance(self.native_receipt, str), "SEALED_NATIVE_RECEIPT_REQUIRED")
        object.__setattr__(self, "native_receipt", seal_json(self.native_receipt, "NATIVE_RECEIPT"))

    @property
    def decision_sha(self):
        return digest({"aidc": self.aidc.to_dict() if self.aidc else None,
                       "mess": self.mess.to_dict() if self.mess else None})


def request_from_dict(value):
    data = dict(value)
    data["authority"] = Authority(**data["authority"])
    for key, cls in (("fixed_aidc", AIDCDecision), ("fixed_mess", MESSDecision)):
        if data[key] is not None:
            data[key] = cls(**data[key])
    if data["warm_start"] is not None:
        warm = dict(data["warm_start"])
        warm["mess"] = MESSDecision(**warm["mess"])
        data["warm_start"] = WarmStartCandidate(**warm)
    return StageRequest(**data)


def result_from_dict(value):
    data = dict(value)
    data["authority"] = Authority(**data["authority"])
    if data["aidc"] is not None:
        data["aidc"] = AIDCDecision(**data["aidc"])
    if data["mess"] is not None:
        data["mess"] = MESSDecision(**data["mess"])
    data["certificate"] = Certificate(**data["certificate"])
    data["physical"] = PhysicalReceipt(**data["physical"])
    return StageResult(**data)
