# References

Each entry is grouped by role. "Repo" links were checked with `git ls-remote` on 2026-11-15. Entries marked **unverified** could not be confirmed online.

## Context dilution and context management
- **MOSAN**: "An autonomous agentic framework for cross-campaign generalization and sensor shift adaptation." https://doi.org/10.1088/2632-2153/ae9fb7. Repo: https://github.com/Docdomee/MOSAN. We adapt its Single Ledger, Decider without chat history, graph memory and ghost nodes.
- **ACE**: Agentic Context Engineering (ICLR 2026). https://arxiv.org/abs/2510.04618. Repo: https://github.com/ace-agent/ace. We adopt its delta-entry updates to avoid context collapse.
- **Sense and Sensitivity**: semantic recall in long-context code reasoning. https://arxiv.org/abs/2505.13353
- **Long-range dependency handling in code LLMs**: https://arxiv.org/abs/2407.21049
- **Hierarchical Context Pruning**: https://arxiv.org/abs/2406.18294
- **SWE-Pruner**: https://arxiv.org/abs/2601.16746
- **Context as a Tool** (CAT): https://arxiv.org/abs/2512.22087
- **On Problems of Implicit Context Compression for SWE Agents**: https://arxiv.org/abs/2605.11051
- **Rivet**: arXiv 2610.34967, cited in the team's .docx plan. **Unverified**: no matching paper was found online.

## Repository graphs and retrieval
- **ARISE**: https://arxiv.org/abs/2605.03117. Repo: https://github.com/FARD-Lab/ARISE
- **LocAgent** (ACL 2025): https://arxiv.org/abs/2503.09089. Repo: https://github.com/gersteinlab/LocAgent
- **RepoScope** (ICSE 2026): https://arxiv.org/abs/2507.14791
- **RepoLens**: https://arxiv.org/abs/2509.21427
- **CodexGraph**, **RepoGraph**: related graph-retrieval systems, still to be read.

## Debugging and vulnerabilities
- **RepoAudit** (ICML 2025): https://arxiv.org/abs/2501.18160. Repo: https://github.com/PurCL/RepoAudit
- **TraceCoder**: https://arxiv.org/abs/2602.06875
- **PracRepair**, **GraphLocator**, **ProtocolGuard**, **VulTriage**, **VulnGym**: see `docs/research/Debugging Architectures/`
- **SWE-agent**: https://github.com/SWE-agent/SWE-agent
- **OpenHands**: https://github.com/OpenHands/OpenHands

## Optimization
- **PerfAgent**: https://arxiv.org/abs/2607.19653
- **ACCLAIM**: https://arxiv.org/abs/2604.04238
- **SWE-Perf**: https://proceedings.mlr.press/v306/he26y.html
- **SWE-fficiency**: https://proceedings.mlr.press/v306/ma26l.html

## Concurrency
- **ConFixAgent**: https://arxiv.org/abs/2604.05753
- **Fray**: https://github.com/cmu-pasta/fray
- **Spaghetti Bench**: https://github.com/cmu-pasta/spaghetti-bench

## Communication
- **NLIP / ECMA-430**: https://github.com/nlip-project
