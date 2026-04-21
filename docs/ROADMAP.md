# Roadmap

Open items, roughly ordered by impact. PRs welcome — pick any, open an issue first if the change is large.

- **Targeted reviewer feedback.** When the design reviewer sets `target_role`, re-run only that one executor instead of the whole round-robin. Cuts per-review cost ~80 %.
- **Dependency-cycle linter.** New `graph_linter` node between `mermaid_maker` and `mermaid_renderer` that detects cycles in `MermaidIR.edges`, nudges the maker to fix, and bounds retries.
- **Parallel executors.** Use the LangGraph `Send` API so one round of 5 roles runs concurrently; should bring total runtime from ~10 min to ~2 min.
- **Persistent checkpointer.** Wire a `SqliteSaver` (or `PostgresSaver`) into `plot_agent.memory.make_checkpointer` so interrupted runs can resume across processes.
- **Human-in-the-loop.** Pause the graph when either reviewer reports `ok=false` with a `severity=high` issue and wait for an explicit human ack before retrying.
- **Additional render backends.** Graphviz / Excalidraw / draw.io modules next to `render/png.py`, each consuming `MermaidIR`.
- **Observability integrations.** LangSmith and LangFuse tracing wired through `call_structured`.
- **Icon inlining.** Optionally pre-fetch iconify SVGs and embed them as data URIs so offline / strict-sandbox renderers (Kroki's headless chromium) render logos deterministically.
