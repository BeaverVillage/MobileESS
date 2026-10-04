# Retained model construction prototype

RMPRows and RMPColumn are immutable mathematical registry records. PersistentRMP retains
the Gurobi object, creates fixed coupling/convexity rows once, appends lambda columns with
gp.Column, and calls update. The default build_rmp path builds a fresh model; the persistent
flag reuses a model only when rows and the complete prior registry prefix are exactly equal.
Changed coefficients, row identity, bounds, senses or objectives require reconstruction.
All variables are continuous; production adapters must map master z and lambda coefficients
in their original order. The prototype does not alter the production Master class.

Model.reset(0) precedes EVERY optimization and LPWarmStart=0 is explicit. No VBasis/CBasis
is imported, exported, read, or intentionally selected. Native implementation caches other
than discarded solution state may remain; the experiment measures construction/update
architecture and is not a warm-basis retest. There is no solver parameter sweep.

The representative toy has two MESS convexity equalities, one capacity inequality,
an objective constant and four append iterations. At each iteration, full native identities
are compared: row/column counts, nnz, matrix, names, RHS, senses, bounds, types, coefficients,
constant and model sense. Objective, primal solution and duals agree within absolute 1e-8.
The chosen toy has comparable primal/dual optima; equality of returned primal/dual vectors
is not generally guaranteed for degenerate production LPs, even for identical matrices.

Disk rows/column registry is authoritative and has a canonical SHA integrity binding.
The prior model is disposed, the disk registry reloaded and a new model reconstructed;
matrix identity, objective, primal and dual recovery pass. This is a simulated model/process
restart, not a real process-kill experiment. No in-memory basis is required by the checkpoint.

Timing records separate Python registry reconstruction, native model build, persistent
add-column/update and optimize wall time. Initial persistent build is a separate field.
The resource guard samples before/after native calls; its overhead is in wrapped wall times.
Native Gurobi Runtime is also recorded separately. There are no production extrapolations.
