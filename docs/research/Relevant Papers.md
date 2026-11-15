# Relevant Papers

Related proposal: [[Research Proposal]]

Yes. I’d organize the literature by **direct relevance to the three RQs**, with a separate cross-cutting group for context management, agent orchestration, and communication.

| RQ / Role | Paper / System | Why it matters to us |
|---|---|---|
| **RQ1 — Debugging & Vulnerability Detection** | **RepoAudit: An Autonomous LLM-Agent for Repository-Level Code Auditing** | One of the closest baselines. Handles large-repository auditing through on-demand exploration, memory, data-flow reasoning, and validation. Directly relevant to our repository-scale context problem. [Proceedings of Machine Learning Research](https://proceedings.mlr.press/v267/guo25n.html?utm_source=chatgpt.com) |
| **RQ1** | **TraceCoder: A Trace-Driven Multi-Agent Framework for Automated Debugging of LLM-Generated Code** | Multi-agent debugging using runtime traces, causal analysis, historical learning, and rollback. Important comparison for our execution/reproduction loop and multi-agent debugging architecture. [arXiv](https://arxiv.org/abs/2602.06875?utm_source=chatgpt.com) |
| **RQ1** | **RepoLens: Extracting Conceptual Knowledge to Locate Software Issues** | Directly tackles issue localization in large repositories where relevant logic is scattered across files or tangled inside functions. Very relevant to our context construction layer. [alphaXiv](https://www.alphaxiv.org/abs/2509.21427v2?utm_source=chatgpt.com) |
| **RQ1** | **ProtocolGuard: Detecting Protocol Non-compliance Bugs via LLM-guided Static Analysis and Dynamic Verification** | Not a protocol-focused baseline for us, but architecturally important: program slicing → LLM semantic reasoning → executable/dynamic verification. [NDSS Symposium](https://www.ndss-symposium.org/ndss-paper/protocolguard-detecting-protocol-non-compliance-bugs-via-llm-guided-static-analysis-and-dynamic-verification/?utm_source=chatgpt.com) |
| **RQ1 / baseline** | **SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering** | General repository-level software-engineering agent. Useful baseline for navigation, editing, test execution, and agent-tool interfaces. [NeurIPS Papers](https://papers.nips.cc/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html?utm_source=chatgpt.com) |
| **RQ1 / baseline** | **OpenHands: An Open Platform for AI Software Developers as Generalist Agents** | General coding-agent platform supporting repository interaction, sandboxed execution, benchmarks, and agent coordination. Likely useful as a baseline or implementation platform. [ICLR Proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/a4b6ad6b48850c0c331d1259fc66a69c-Abstract-Conference.html?utm_source=chatgpt.com) |
| **RQ2 — Code Optimization** | **PerfAgent: Profiler-Guided Iterative Refinement for Repository-Level Code Optimization** | Probably the most important RQ2 architecture baseline. Uses profiling evidence, iterative refinement, and verifier feedback to find and improve repository-level performance bottlenecks. [arXiv](https://arxiv.org/abs/2607.19653?utm_source=chatgpt.com) |
| **RQ2** | **ACCLAIM / Agentic Code Optimization via Compiler-LLM Cooperation** | Multi-agent optimization system with specialized optimization agents, compiler tools, test generation, and a guiding LLM. Important direct comparison for our optimization-agent architecture. [arXiv](https://arxiv.org/abs/2604.04238?utm_source=chatgpt.com) |
| **RQ2 — evaluation** | **SWE-Perf: Can Language Models Optimize Code Performance on Real-World Repositories?** | Repository-level performance benchmark with 140 optimization tasks. Useful for evaluating whether our framework improves performance optimization. [Proceedings of Machine Learning Research](https://proceedings.mlr.press/v306/he26y.html?utm_source=chatgpt.com) |
| **RQ2 — evaluation / gap evidence** | **SWE-fficiency: Can Language Models Optimize Real-World Repositories on Real Workloads?** | Especially important because it shows agents struggle with bottleneck localization, cross-function execution reasoning, and maintaining correctness—direct support for our context-management hypothesis. [Proceedings of Machine Learning Research](https://proceedings.mlr.press/v306/ma26l.html?utm_source=chatgpt.com) |
| **RQ3 — Concurrency & Race Conditions** | **ConFixAgent: An End-to-End Approach for Fixing Concurrency Bugs via SHB-Based Context Extractor** | The main RQ3 baseline. Uses Static Happens-Before graphs to extract concurrency-relevant context before asking the LLM to repair bugs. Extremely close to our idea of constructing task-specific views over a repository. [arXiv](https://arxiv.org/abs/2604.05753?utm_source=chatgpt.com) |
| **RQ3 — evaluation / execution** | **Spaghetti Bench / Fray** | Relevant benchmark and execution infrastructure for testing coding agents on concurrency bugs, especially thread interleavings and real concurrency failures. |
| **Cross-cutting architecture** | **OpenHands** | Relevant across all three RQs because it provides the general coding-agent execution environment and can support multi-agent coordination. [arXiv](https://arxiv.org/abs/2407.16741?utm_source=chatgpt.com) |
| **Cross-cutting architecture** | **SWE-agent** | Relevant across all three because it demonstrates how agent interfaces affect repository navigation and tool use. [arXiv](https://arxiv.org/abs/2405.15793?utm_source=chatgpt.com) |
| **Cross-cutting multi-agent communication / safety** | **Maris: A Formally Verifiable Privacy Policy Enforcement Paradigm for Multi-Agent Collaboration Systems** | Not a QA paper, but relevant to how structured inter-agent message flow and controlled information exchange can be designed. [alphaXiv](https://www.alphaxiv.org/abs/2505.04799?utm_source=chatgpt.com) |
| **Cross-cutting agent control** | **AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM Agents** | Useful for understanding structured runtime constraints and enforcement around agent actions/tool use. [arXiv](https://arxiv.org/abs/2503.18666?utm_source=chatgpt.com) |
| **Cross-cutting agent security** | **LlamaFirewall: An Open Source Guardrail System for Building Secure AI Agents** | Relevant mainly if we consider secure execution/tool use or protecting an agentic coding framework; not central to any one RQ. [ArxivLens](https://arxivlens.com/paperview/details/llamafirewall-an-open-source-guardrail-system-for-building-secure-ai-agents-9261-9a6c0550?utm_source=chatgpt.com) |
| **Cross-cutting communication** | **NLIP specification / implementation** | Core communication substrate we are considering for structured agent-to-agent messaging and passing repository/evidence references. |
| **Cross-cutting tool interface** | **MCP** | Not a research baseline for the three RQs, but potentially the interface through which agents access repository-analysis, profiling, debugging, testing, and concurrency tools. |

### The papers I would prioritize first

If we want to understand architectures before building anything, I would read these **eight first**, in roughly this order:

1. **RepoAudit** — RQ1, repository context/navigation.
2. **TraceCoder** — RQ1, multi-agent debugging + runtime traces.
3. **RepoLens** — RQ1, large-repository context/localization.
4. **PerfAgent** — RQ2, profiler-guided repository optimization.
5. **ACCLAIM** — RQ2, explicit multi-agent optimization architecture.
6. **SWE-fficiency** — RQ2, evidence for where current optimization agents fail.
7. **ConFixAgent** — RQ3, task-specific concurrency context construction.
8. **Spaghetti Bench / Fray** — RQ3, reproducibility and evaluation.

Then we study **NLIP + MCP + OpenHands** to determine how to implement the common communication/tool layer.

The most important comparison for our architecture will probably become:

> **RepoAudit / RepoLens → debugging context**  
> **PerfAgent / ACCLAIM → optimization context**  
> **ConFixAgent → concurrency context**  
> **TraceCoder → multi-agent iterative reasoning**  
> **NLIP → structured exchange between those specialized reasoning components**

That gives us a much cleaner path to the final architecture.
