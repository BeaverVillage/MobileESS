"""Shared atomic storage and locks; explicit V7 source authorization."""
from v42_may_campaign_native90.common import *


def verify_manifest(path, require_preflight=True):
    from .policy import verify_policy
    return verify_policy(Path(path).resolve().parent, require_preflight=require_preflight)
