# V35R3E final review

Classification: `V35R3E_TOPK_MIPSTART_REGRESSION`.

Apr-01 proves that the deterministic S4 screen requires adaptive expansion: K0=200 is not certified, while K=800 recalls all eight exact restricted best candidates with zero regret. All eight Top-K trajectories are accepted as MIPStarts by the unchanged unrestricted multi-MOVE MILP. Fresh is either reused for byte-identical trajectories or run only ex post when trajectory SHAs differ; it never enters selection. Production readiness is NO under the frozen adaptive fallback contract.
