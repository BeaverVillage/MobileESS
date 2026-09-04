# V29R1 Jan--Mar external source requirements

No external download was authorized or performed.

## Missing raw data

### NOAA Global Forecast System 0.25-degree operational archive

- Required range: 2025-01-01 through 2025-03-31
- Current local coverage: 0/90 target days
- Missing coverage: all 90 target days
- Required vintage: 06Z D-1; available before D-1 18:00 fixed AEST
- Required resolution: f008-f032 hourly leads; production interpolation to 96x15-minute
- Official source: https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/06/atmos/gfs.t06z.pgrb2.0p25.fNNN
- Trust-cert role: production C1 wet-bulb/RH envelope and AIDC perturbation

### AEMO PREDISPATCHREGIONSUM ALL monthly archives

- Required range: 2025-01-01 through 2025-03-31
- Current local coverage: 30/90 target days (2025-03-02 through 2025-03-31)
- Missing coverage: 2025-01-01 through 2025-03-01
- Required vintage: latest complete VIC1 vintage <= D-1 18:00 fixed AEST
- Required resolution: 48x30-minute raw; production duplication to 96x15-minute MW
- Official source: https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/YYYY/MMSDM_YYYY_MM/MMSDM_Historical_Data_SQLLoader/PREDISP_ALL_DATA/
- Trust-cert role: production feeder Day-Ahead demand background

### AEMO ROOFTOP_PV_FORECAST monthly archives

- Required range: 2025-01-01 through 2025-03-31
- Current local coverage: 30/90 target days (2025-03-02 through 2025-03-31)
- Missing coverage: 2025-01-01 through 2025-03-01
- Required vintage: latest complete VIC1 vintage <= D-1 18:00 fixed AEST
- Required resolution: 48x30-minute raw; production duplication to 96x15-minute MW
- Official source: https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/YYYY/MMSDM_YYYY_MM/MMSDM_Historical_Data_SQLLoader/DATA/
- Trust-cert role: production feeder Day-Ahead rooftop-PV background

## Missing materialization only

After the raw files above are explicitly acquired, the existing April parser must be
generalized by date range and write only to `cache/v29r1_trust_cert_sources/jan_mar_2025/`.
The April production cache must remain unchanged.
