"""Read saved historical conditions; never import or run historical solvers."""
from pathlib import Path
import shutil
import numpy as np
from .common import ROOT, REPORT, read, write, table, receipt
from .capacity import FIXED_AIDC


def capture():
    old = ROOT.parent / 'IEEE8500_PAPER_SCALE_ONLY_20260920'
    campaign = old / 'full_production_paper_BG055200_AIDC240_MESS200'
    screen = old / 'controllability_search_20260920/b0_cases/BG_0.55200_AIDC_2.40/RESULT.json'
    audit = read(old / 'FORENSIC_AUTHORITY.json')
    mapping = audit['paper_mapping']
    host_rows = []
    for site, current in FIXED_AIDC.items():
        old_host = mapping['AIDC:' + site]['host_bus']
        host_rows.append(dict(aidc_id=site, historical_paper_AIDC_host=old_host,
            former_v3_host=current, same_host=old_host == current,
            historical_transformer_kVA=mapping['AIDC:' + site]['rating_kva']))
    table(REPORT / 'HISTORICAL_PAPER_VS_V3_AIDC_HOSTS.csv', host_rows)
    z = np.load(campaign / 'MAY01_B0_AIDC_POWER.npz', allow_pickle=False)
    forecast = read(campaign / 'D1_AEMO_VIC1_FORECAST.json')
    rule = read(campaign / 'SCREENING_RULE.json')
    rows = [dict(case='ORIGINAL_STATIC_REPRODUCTION', background=1.0, temporal_shape='NONE_STATIC',
                 PV_multiplier=0, PV_objects=0, AIDC_multiplier=0, AIDC_kW_min=0, AIDC_kW_max=0,
                 source_pu=1.05, feeder_Vreg_V=126.5, downstream_Vreg_V=125.0,
                 CAPBank3='ORIGINAL_ENABLED', original_RegControl_count=12, original_CapControl_count=9,
                 model='ORIGINAL_MASTER_UNBAL_NO_PCC_OVERLAY', rerun=True),
            dict(case='HISTORICAL_BG0552_SCREEN', background=.552,
                 temporal_shape='May01_AEMO_D1_demand_divided_by_daily_max',
                 PV_multiplier=.5, PV_objects='ADDED_PER_ORIGINAL_LOAD', AIDC_multiplier=2.4,
                 AIDC_kW_min=float(z['pcc'].sum(1).min()), AIDC_kW_max=float(z['pcc'].sum(1).max()),
                 source_pu=1.04, feeder_Vreg_V=123.5, downstream_Vreg_V=123.5, CAPBank3='OFF',
                 original_RegControl_count=12, original_CapControl_count=9,
                 model='V41R4_PAPER_PCC_OVERLAY_WITH_36_ADDITIONAL_TRANSFORMERS', rerun=False),
            dict(case='HISTORICAL_BG0552_FINAL_EXACT_ENGINE_SOURCE', background=.552,
                 temporal_shape='May01_AEMO_D1_demand_divided_by_daily_max',
                 PV_multiplier=.552, PV_objects='ADDED_PER_ORIGINAL_LOAD', AIDC_multiplier=2.4,
                 AIDC_kW_min=float(z['pcc'].sum(1).min()), AIDC_kW_max=float(z['pcc'].sum(1).max()),
                 source_pu=1.04, feeder_Vreg_V=123.5, downstream_Vreg_V=123.5, CAPBank3='OFF',
                 original_RegControl_count=12, original_CapControl_count=9,
                 model='SAVED_ENGINE_INPUTS_CODE_VALUE_NOT_SCREENING_RULE_ANNOTATION', rerun=False)]
    table(REPORT / 'ORIGINAL_VS_HISTORICAL_CONDITIONS.csv', rows)
    paths = [screen, old / 'stage_a.py', campaign / 'electrical_engine.py', campaign / 'common8500.py',
             campaign / 'SCREENING_RULE.json', campaign / 'FINAL_VERIFIED_REPORT_20260923.md',
             campaign / 'PCC_OVERLAY_INVENTORY.json', campaign / 'MAY01_B0_AIDC_POWER.npz',
             ROOT.parent / 'IEEE8500_production_compatibility_20260911/screen_compatible_b0.py',
             ROOT.parent / 'IEEE8500_stress_calibration_20260911/overlays/Source_1.0400_Vreg_123.5.dss']
    dest = REPORT / 'historical_read_only_evidence'
    dest.mkdir(exist_ok=True)
    sources = []
    for p in paths:
        sources.append(receipt(p))
        # Exact text evidence only: no old absolute-path launcher is executed.
        if p.suffix.lower() in ('.json', '.md', '.dss', '.py'):
            shutil.copyfile(p, dest / p.name)
    write(REPORT / 'HISTORICAL_CONDITIONS_AUDIT.json', dict(
        source_receipts=sources, historical_scientific_replay_executed=False,
        screen_result=read(screen), historical_rule_annotation=rule,
        source_effective_final_BG=.552, source_effective_final_PV=.552,
        important_annotation_difference='Earlier screen overrides PV to .5; final exact engine calls old.inputs(a=.552), which uses a for both background and PV. Inherited SCREENING_RULE still says BG/PV .5. Distinct scopes are not merged.',
        original_static_vmin_not_a_V42_B0_result=True,
        historical_paper_AIDC_hosts_equal_former_v3=sum(r['same_host'] for r in host_rows),
        source_or_Vreg_changed_in_current_work=False))
    print('Historical BG/PV/control/PCC conditions distinguished without scientific rerun.', flush=True)


if __name__ == '__main__':
    capture()

