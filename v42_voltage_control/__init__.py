"""Autonomous capacitor/SVR infrastructure, independent of AIDC/MESS decisions."""
VERSION = "V42_CAPCONTROL_SVR_SOURCE_EPOCH_V1"
VOLTAGE_BAND_PU = (.95, 1.05)
DAYS = tuple(f"2025-05-{i:02d}" for i in range(1,32))
POLICY_ORDER = ("B0", "B2", "B1", "B3")
WORKERS = {"B0":1, "B2":3, "B1":1, "B3":1}
