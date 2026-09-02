"""Frozen prospective authorities for V29R1.

This module contains only decisions that must exist before any April
development result can be inspected.  In particular, the trust-region
candidate set and source-authority failure status are immutable here.
"""

from __future__ import annotations

from datetime import date, timedelta


PRODUCTION_BASE_HEAD = "2bcfe7d48046c5c3f9f1bc43b6d35805e3ed589f"
POSTCARRYIN_FORENSIC_HEAD = "f238ea2c593609b4c69f037264dcbc3c8238ac9e"
PREAPRIL_CENSUS_HEAD = "77317258dee89f43af90fc160253e250629d6906"
V29R1_BRANCH = "codex/v29r1-reliability-calibrated-noregret"

CANDIDATE_RHOS = (0.10, 0.25, 0.50, 1.00)
CERTIFICATION_START = date(2025, 1, 1)
CERTIFICATION_END = date(2025, 3, 31)
CERTIFICATION_DAYS = tuple(
    (CERTIFICATION_START + timedelta(days=offset)).isoformat()
    for offset in range((CERTIFICATION_END - CERTIFICATION_START).days + 1)
)

BLOCKED_SOURCE_STATUS = "V29R1_BLOCKED_TRUST_CERT_SOURCE_AUTHORITY_INSUFFICIENT"
BLOCKED_TOLERANCE_STATUS = "V29R1_BLOCKED_TRUST_CERT_TOLERANCE_AUTHORITY_MISSING"

# Frozen before any April development evaluation.
RELIABILITY_TARGET = 0.90
Q_SCENARIOS = ("S_NOM", "S_LOW", "S_ZERO_CARRY")
