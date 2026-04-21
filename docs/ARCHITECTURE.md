# Architecture

Deep dive on how `plot_agent` is put together. Start with the top-level README for a quick tour, then come here when you need to extend a node, swap a renderer, or understand why a choice was made.

## Project layout

```
plot_agent/
├── cli.py                       # argparse CLI: generate / render
├── llm.py                       # call_structured: LLM→JSON→schema, repair loop, LLMCallError
├── schemas.py                   # TechPlan / ComponentDesign / PlanReviewReport / ReviewReport / MermaidIR
├── state.py                     # MultiAgentState + reducers
├── memory.py                    # InMemorySaver / InMemoryStore factories
├── graph/
│   ├── builder.py               # top-level pipeline assembly
│   ├── nodes/
│   │   ├── planner.py
│   │   ├── plan_reviewer.py     # high-level architecture critique
│   │   ├── reviewer.py          # low-level design critique
│   │   ├── mermaid_maker.py
│   │   ├── mermaid_renderer.py
│   │   └── routing.py
│   └── subgraphs/
│       ├── executors.py         # round-robin executor subgraph
│       └── roles/
│           ├── _common.py       # context slicing + run_role()
│           ├── frontend.py / backend.py / data.py / devops.py / security.py
└── render/
    ├── __init__.py
    └── png.py                   # Kroki HTTP (default) + mmdc fallback
tests/
├── conftest.py                  # stub_llm fixture; CI needs no OPENAI_API_KEY
├── test_smoke.py
└── test_mermaid_ir.py
samples/
├── databricks_brd.txt
└── Databricks_Project_BRD.pdf
```

## Two-review rubric

| Stage | When | Rubric | Schema | Budget |
| --- | --- | --- | --- | --- |
| `plan_reviewer` | after `planner`, before executors | stack coherence, BRD fit, runtime pragmatism, integration model, **missing_concerns** (DR / cost / compliance / SLO), open-question quality | `PlanReviewReport` | `MAX_PLAN_REVIEW_ROUNDS=2` |
| `reviewer` (design) | after the executor subgraph | interface consistency, dependency closure, deployment realism, `target_role` nomination | `ReviewReport` | `MAX_REVIEW_ROUNDS=2` |

Prompts are explicitly scoped so they don't step on each other — `plan_reviewer` is told *not* to critique at the resource-name level; that's the design reviewer's job.

## Visual language emitted by `mermaid_maker`

| Concept | Field | Values |
| --- | --- | --- |
| Node category | `style_class` | `external` / `internal` / `database` / `cache` / `queue` / `compute` / `secret` / `observability` / `ai` |
| Official logos | `icon` | iconify key, e.g. `logos:postgresql`, `simple-icons:databricks`, `logos:kubernetes`, `logos:microsoft-azure` (whitelist lives in the planner prompt) |
| Relationship kind | `style` | `solid` (sync) / `thick` (critical) / `dashed` (async / event) / `dotted` (logical / optional) |
| Grouping | `subgraphs` | role-based clusters, including an `external` cluster for outside-org systems |

`MermaidIR.to_mermaid()` auto-emits `classDef` + `linkStyle` blocks so any Mermaid renderer (Kroki, mmdc, mermaid.live) produces the colour-coded output without extra config. Logo fidelity depends on the renderer being able to fetch the iconify CDN at render time; unreachable icons degrade gracefully to a label-only node.

## Harness engineering checklist

| Concern | Implementation |
| --- | --- |
| Context slicing | `_role_context()` feeds each executor only the plan, peer designs, scratchpad, and any reviewer feedback addressed to that role |
| Schema hard contract | Pydantic schema at every agent boundary; LLM must return JSON |
| Repair loop | `call_structured` re-prompts with the validation error on parse failure; raises `LLMCallError` after the budget |
| Network retry | `_invoke_llm` retries on `APIConnectionError` / `APITimeoutError` / `RateLimitError` with exponential backoff |
| Bounded retries | `MAX_PLAN_REVIEW_ROUNDS=2`, `MAX_EXECUTOR_TURNS=2`, `MAX_REVIEW_ROUNDS=2`; the graph always terminates |
| Memory, two tiers | `InMemorySaver` (per-thread checkpoints) + `InMemoryStore` (project-level long-term memory) |
| Observability | Append-only `trace`, one `AIMessage` per agent, `stream_mode="updates"` for live per-node events |
| No silent fallback | Failures always raise `LLMCallError`; nothing in the package fakes agent output |

## Code-level tunables

| Location | Default | Purpose |
| --- | --- | --- |
| `graph/nodes/plan_reviewer.py::MAX_PLAN_REVIEW_ROUNDS` | 2 | how many times `plan_reviewer` can bounce the plan back to `planner` |
| `graph/subgraphs/executors.py::MAX_EXECUTOR_TURNS` | 2 | rounds inside the executor subgraph |
| `graph/nodes/reviewer.py::MAX_REVIEW_ROUNDS` | 2 | how many times the design reviewer can bounce back to executors |
| `llm.py::_NETWORK_RETRIES` | 3 | exponential backoff on transient LLM network errors |

## Extending the pipeline

- **Add another executor role**: drop a file in `graph/subgraphs/roles/` following the pattern of `frontend.py` (just call `run_role("<name>", state)`), register it in `roles/__init__.py::ROLE_NODES` and in the order tuple inside `subgraphs/executors.py`.
- **Swap the LLM**: rewrite `_invoke_llm` in `plot_agent/llm.py`. Everything else is provider-agnostic.
- **Swap the diagram backend**: add a sibling module next to `plot_agent/render/png.py` (e.g. `drawio.py`) that consumes `MermaidIR` (or its dict) and writes the target format; plug it into `mermaid_renderer.py`.
- **Swap the memory**: inject a `SqliteSaver` / `PostgresSaver` into `build_brd_to_mermaid_pipeline(checkpointer=...)`.
