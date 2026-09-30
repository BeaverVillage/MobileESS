# Actual PR102 root matrix census

Complete 1499-job model, original tie rows included. Counts and nonzeros are measured from the native sparse matrix, not inferred from column counts. See family CSVs for sparse recurrence, routing, payload, tie, Runtime, CC4 and grid contributions. The PR102 single root node and zero incumbent do not demonstrate branch-tree explosion.

[
  {
    "family": "resource_GPU",
    "rows": 3336,
    "nonzeros": 2103359,
    "average_nonzeros_per_row": 630.5032973621103,
    "maximum_nonzeros_per_row": 2004
  },
  {
    "family": "Runtime_completion_risk",
    "rows": 1152,
    "nonzeros": 34923402,
    "average_nonzeros_per_row": 30315.453125,
    "maximum_nonzeros_per_row": 77795
  },
  {
    "family": "resource_WAN",
    "rows": 1800,
    "nonzeros": 872182,
    "average_nonzeros_per_row": 484.54555555555555,
    "maximum_nonzeros_per_row": 1122
  },
  {
    "family": "resource_active_transfers",
    "rows": 120,
    "nonzeros": 62936,
    "average_nonzeros_per_row": 524.4666666666667,
    "maximum_nonzeros_per_row": 1122
  },
  {
    "family": "CC4",
    "rows": 10992,
    "nonzeros": 179408,
    "average_nonzeros_per_row": 16.321688500727802,
    "maximum_nonzeros_per_row": 97
  },
  {
    "family": "Runtime_CC4_reserve_headroom",
    "rows": 2304,
    "nonzeros": 8064,
    "average_nonzeros_per_row": 3.5,
    "maximum_nonzeros_per_row": 4
  },
  {
    "family": "native_grid",
    "rows": 667008,
    "nonzeros": 12146624,
    "average_nonzeros_per_row": 18.210612166570716,
    "maximum_nonzeros_per_row": 25
  },
  {
    "family": "compact_event_service",
    "rows": 2597,
    "nonzeros": 22260,
    "average_nonzeros_per_row": 8.571428571428571,
    "maximum_nonzeros_per_row": 36
  },
  {
    "family": "r0_balance",
    "rows": 980006,
    "nonzeros": 3656321,
    "average_nonzeros_per_row": 3.7309169535696722,
    "maximum_nonzeros_per_row": 5
  },
  {
    "family": "factor_event_logic",
    "rows": 901697,
    "nonzeros": 13221991,
    "average_nonzeros_per_row": 14.663452357055641,
    "maximum_nonzeros_per_row": 2919
  },
  {
    "family": "WAN_payload_dynamics",
    "rows": 1323888,
    "nonzeros": 3893814,
    "average_nonzeros_per_row": 2.9411959319821617,
    "maximum_nonzeros_per_row": 13
  },
  {
    "family": "depart_linking",
    "rows": 778589,
    "nonzeros": 2214563,
    "average_nonzeros_per_row": 2.8443286509313643,
    "maximum_nonzeros_per_row": 13
  },
  {
    "family": "h_balance",
    "rows": 628226,
    "nonzeros": 2450127,
    "average_nonzeros_per_row": 3.900072585343491,
    "maximum_nonzeros_per_row": 4
  },
  {
    "family": "r1_balance",
    "rows": 1150221,
    "nonzeros": 3735358,
    "average_nonzeros_per_row": 3.2475133039650643,
    "maximum_nonzeros_per_row": 4
  },
  {
    "family": "link_bytes_linking",
    "rows": 2632984,
    "nonzeros": 6462085,
    "average_nonzeros_per_row": 2.454281909802718,
    "maximum_nonzeros_per_row": 49
  },
  {
    "family": "tie",
    "rows": 273614,
    "nonzeros": 14503274,
    "average_nonzeros_per_row": 53.006330085448845,
    "maximum_nonzeros_per_row": 133
  }
]
