# ADR-0002: Earlier systems as pinned manifests plus a fetch script

**Status:** accepted (2026-11-15)

**Decision.** Each earlier system has `testing/prior_work/<area>/<system>/manifest.toml` (URL,
full commit SHA, license, status), a reproduction README, an adapter and a results parser.
`scripts/fetch_prior_work.py` clones into the gitignored `testing/prior_work/_upstream/`.
Upstream code is never copied into this repository.

**Why not submodules or copied code.** Submodules are awkward across long-lived branches and
make clones heavy. Copying code raises a license question for each project. Manifests keep the
exact pins and stay small.
