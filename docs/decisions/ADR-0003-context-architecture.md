# ADR-0003: Five-layer context architecture against five kinds of dilution

**Status:** accepted for Stages A-C; L2-L5 open to change after C0-C3 (2026-11-15)

**Decision.** Adopt the design in `docs/context_management.md`:
- L1 versioned graph
- L2 ledger with prompts rebuilt each turn and observation masking (adapted from MOSAN SiLA)
- L3 budgeted, ordered bundles
- L4 revision-scoped summaries, strategy memory and ghost hints (adapted from MOSAN OSGM and
  ghost nodes)
- L5 acceptance gate

Each layer targets one named kind of dilution and has its own metric and ladder run (C0-C7).

**Key adaptations from MOSAN.** The ledger is typed and queryable rather than markdown. Ghost
hints are validated by accepted findings, whereas MOSAN drops them without checking. Strategy
memory uses symptom and anchor signatures instead of model-configuration vectors.
