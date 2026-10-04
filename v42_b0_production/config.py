from dataclasses import asdict, dataclass
from v42_orchestrator.config import Config

BASE = '0760b8f56398344e55d938b175d88761d19ff657'
VERSION = 'B0_PRODUCTION_V1'
STAGES = ('B0_PLANNING', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE')


@dataclass(frozen=True)
class B0Config(Config):
    ENABLE_B0_PRODUCTION: bool = False
    ENABLE_B1_PRODUCTION: bool = False
    ENABLE_B2_PRODUCTION: bool = False
    ENABLE_B3_PRODUCTION: bool = False
    AUTO_ADVANCE_TO_B1: bool = False
    SAMPLE_SECONDS: float = 1
    CATASTROPHIC_PAGES_INPUT_PER_SECOND: float = 8192
    CATASTROPHIC_PAGING_SUSTAINED_SECONDS: float = 30

    def __post_init__(self):
        super().__post_init__()
        if any((self.ENABLE_B1_PRODUCTION, self.ENABLE_B2_PRODUCTION,
                self.ENABLE_B3_PRODUCTION, self.AUTO_ADVANCE_TO_B1)):
            raise ValueError('This authority cannot enable B1/B2/B3 or auto advance')
        if not 0 < self.SAMPLE_SECONDS <= 2:
            raise ValueError('Production telemetry must sample at <=2 seconds')
        if self.CATASTROPHIC_PAGES_INPUT_PER_SECOND <= 0 or self.CATASTROPHIC_PAGING_SUSTAINED_SECONDS <= 0:
            raise ValueError('Explicit sustained paging thresholds required')

    def authorize(self, arm, stage=None):
        if arm != 'B0' or not (self.ENABLE_PRODUCTION and self.ENABLE_B0_PRODUCTION):
            raise PermissionError('EXPLICIT_B0_ONLY_PRODUCTION_AUTHORIZATION_REQUIRED')
        if stage is not None and stage not in STAGES:
            raise PermissionError('B0_CANNOT_EXECUTE_A1_M1_A2_M2_OR_OTHER_ARM_STAGES')


def explicit_config():
    return B0Config(ENABLE_PRODUCTION=True, ENABLE_B0_PRODUCTION=True)
