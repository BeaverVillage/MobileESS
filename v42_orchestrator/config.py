from dataclasses import asdict, dataclass

BASE_SHA = "ce5d30fb9bcb91ab8395d1313e868d24f5fde517"
STAGE_VERSION = "lane-d-mock-v1"


@dataclass(frozen=True)
class Config:
    B0_DAY_WORKERS: int = 4
    B1_DAY_WORKERS: int = 1
    B2_DAY_WORKERS: int = 4
    B3_DAY_WORKERS: int = 1
    B2_INNER_PRICING: int = 1
    B3_INNER_PRICING: int = 4
    GUROBI_THREADS: int = 1
    GLOBAL_SOLVER_SLOTS: int = 4
    RAM_FLOOR_GIB: float = 1
    COMMIT_STOP_PERCENT: float = 95
    MAX_TRANSIENT_RETRIES: int = 2
    ENABLE_PRODUCTION: bool = False

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key.endswith(('WORKERS', 'PRICING', 'THREADS', 'SLOTS')):
                if type(value) is not int or value < 1:
                    raise ValueError(f"Invalid resource count: {key}")
        if self.B1_DAY_WORKERS != 1 or self.B3_DAY_WORKERS != 1:
            raise ValueError("B1/B3 scientific contract permits one day at a time")
        if self.B0_DAY_WORKERS > 4 or self.B2_DAY_WORKERS > 4:
            raise ValueError("B0/B2 current contract caps day workers at four")
        if self.B2_INNER_PRICING != 1 or self.B3_INNER_PRICING > 4:
            raise ValueError("Current contract requires B2 inner1 and B3 inner<=4")
        if self.GUROBI_THREADS != 1:
            raise ValueError("Every future Gurobi solve must use Threads=1")
        if not isinstance(self.RAM_FLOOR_GIB, (int, float)) or not 1 <= self.RAM_FLOOR_GIB < float('inf'):
            raise ValueError("RAM floor must be finite and at least 1 GiB")
        if not 0 < self.COMMIT_STOP_PERCENT <= 95:
            raise ValueError("Commit guard may only be tightened")
        if type(self.MAX_TRANSIENT_RETRIES) is not int or not 0 <= self.MAX_TRANSIENT_RETRIES <= 10:
            raise ValueError("Retries must be bounded")
        if type(self.ENABLE_PRODUCTION) is not bool:
            raise ValueError("ENABLE_PRODUCTION must be an explicit boolean")

    def day_workers(self, arm):
        return getattr(self, f"{arm}_DAY_WORKERS")

    def slots(self, node):
        if node['stage'] in ('M1', 'M2'):
            return min(self.GLOBAL_SOLVER_SLOTS,
                       self.B3_INNER_PRICING if node['arm'] == 'B3' else self.B2_INNER_PRICING)
        return 1 if node['stage'] in ('A1', 'A2') else 0

    def production_guard(self):
        if not self.ENABLE_PRODUCTION:
            raise PermissionError("ENABLE_PRODUCTION=false: real execution blocked")
        raise PermissionError("Lane D has no production adapter; future reviewed integration required")
