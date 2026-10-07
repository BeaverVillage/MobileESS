"""Explicit new-authority binding, available for later authorized runs only."""
from .domain import prepare_active


def build(context, frozen_s0_data, kind='F2-CRA'):
    if kind!='F2-CRA':
        raise ValueError('V2_UNPROVEN_NATIVE_FORMULATION')
    from v42_root.native import build as inherited_build
    data, domains = prepare_active(frozen_s0_data)
    result = inherited_build(context, data, kind)
    model = result[0]
    model._aidc_domain_authority_v2 = data[7]
    return result, data, domains
