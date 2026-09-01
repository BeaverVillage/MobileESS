"""Focused deterministic V25M structural tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dayahead.ml.beacon_flex.hazards import conditional_to_absolute
from dayahead.ml.beacon_flex.shape import coherent_tensor


ROOT=Path(__file__).resolve().parents[3]/"artifacts"/"v25m_beacon_flex"


def test_conditional_hazard_order()->None:
    absolute=conditional_to_absolute(np.asarray([[.8,.7,.6,.5,.4]]))
    assert np.all(np.diff(absolute,axis=1)<=0)


def test_exact_mass()->None:
    shape=np.ones((96,6,5)); tensor=coherent_tensor(12345.6789,shape)
    assert abs(tensor.sum()-12345.6789)<1e-10 and tensor.min()>=0


def test_frozen_structural_artifacts()->None:
    recovery=json.loads((ROOT/"V25M_BASELINE_RECOVERY_PROOF_TEST.json").read_text())
    coherence=json.loads((ROOT/"V25M_BASE_COHERENCE_VALIDATION.json").read_text())
    assert recovery["status"]=="PASS" and recovery["max_CDF_error"]<=1e-6
    assert coherence["reconciled_quantile_crossings"]==0
