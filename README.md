# plot-agent

> **BRD → Mermaid architecture diagram.** Hand a Business Requirements Document to a team of LangGraph agents and get back a readable Mermaid flowchart, a Self-Q&A solution summary, and a rendered PNG.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)

![demo](docs/img/databricks_demo.png)

> *Above: a Databricks Lakehouse BRD fed in, ~11 minutes later this diagram is produced end-to-end.*

---

## Why another "AI diagrammer"

Most LLM diagramming projects ask a single model to plan and emit the final artifact in one shot, which compounds errors. **plot-agent** takes a different cut:

1. **Split responsibilities across agents.** A planner produces a tech plan; five executor roles (`frontend / backend / data / devops / security`) iterate in a subgraph, each seeing its peers' decisions; a reviewer gates progress; a `mermaid_maker` emits a structured IR; a `mermaid_renderer` writes `.mmd`, `summary.md`, and a PNG.
2. **Harness engineering, not vibes.** Every agent's input/output is locked by a Pydantic schema. LLM failures go through a repair loop and otherwise raise `LLMCallError`. **There are no hard-coded business fallbacks anywhere in the package** — the open-source repo is free of opinionated defaults pretending to be agent output.
3. **Decouple via a Mermaid IR.** The LLM only emits IR. Text generation and PNG rendering live in plain Python; you can swap in Graphviz / Excalidraw / draw.io backends.
4. **Observable.** State carries an append-only `trace` and one `AIMessage` per agent. Use `app.stream(..., stream_mode="updates")` to watch every agent's reply live.

---

## Pipeline topology

```
    START
      │
      ▼
   planner ─────▶ plan_reviewer ── (PlanReviewReport, ok? missing_concerns?)
      ▲                 │
      │                 ├── ok=false & rounds < N ──▶ back to planner (revise with feedback)
      │                 │
      │                 └── ok=true | plan budget exhausted ──▶ executors subgraph
      │                                                              │
      │                                                              ▼
      │                                                          reviewer ── (ReviewReport, target_role?)
      │                                                              │
      │                                                 ┌────────────┴────────────┐
      │                                                 │ ok=false & rounds < N   │ ok=true | design budget exhausted
      │                                                 ▼                         ▼
      │                                            back to executors        mermaid_maker → mermaid_renderer → END
      │
      (planner reads plan_review.issues when revising)
```

Two review stages, two rubrics:

- **`plan_reviewer`** (high level, before elaboration): does the overall stack fit the BRD?
  Is anything obviously missing (DR, compliance, cost)? Are the open questions the right ones?
  Cheap: one extra LLM call saves ~10 executor calls when the plan needs reshaping.
- **`reviewer`** (low level, after elaboration): are the component designs internally
  consistent? Do `depends_on` relationships close? Does security align with backend interfaces?

| Agent | Job | Output schema |
| --- | --- | --- |
| `planner` | Read the BRD; build a Self-Q&A chain (frontend / backend / runtime / integration / deployment / secrets / database / open questions). Revises when `plan_reviewer` pushes back. | `TechPlan` |
| `plan_reviewer` | High-level architecture critique before elaboration: stack coherence, BRD fit, missing concerns. Bounces the plan back to `planner` when weak. | `PlanReviewReport` |
| `executors/{role}` × 5 | Read the plan, peer designs, and reviewer feedback; refine just this role | `ComponentDesign` |
| `reviewer` | Low-level design review: interface / dependency / deployment consistency; nominate a `target_role` | `ReviewReport` |
| `mermaid_maker` | Designs → colour-coded nodes / semantic edges / subgraph groups, with optional iconify logos | `MermaidIR` |
| `mermaid_renderer` | IR → `.mmd` + `summary.md` (+ optional PNG via Kroki / mmdc) | files |

### Visual language emitted by `mermaid_maker`

The IR carries semantic style hints so the PNG is readable at a glance:

| Concept | Field | Values |
| --- | --- | --- |
| Node category | `style_class` | `external` / `internal` / `database` / `cache` / `queue` / `compute` / `secret` / `observability` / `ai` |
| Official logos | `icon` | iconify key, e.g. `logos:postgresql`, `simple-icons:databricks`, `logos:kubernetes`, `logos:microsoft-azure` (whitelist in the planner prompt) |
| Relationship kind | `style` | `solid` (sync) / `thick` (critical) / `dashed` (async / event) / `dotted` (logical / optional) |
| Grouping | `subgraphs` | role-based clusters, including an `external` cluster for outside-org systems |

`to_mermaid()` auto-emits `classDef` + `linkStyle` blocks so any Mermaid renderer (Kroki, mmdc, mermaid.live) produces the colour-coded output without extra config. Logo fidelity depends on the renderer being able to fetch the iconify CDN at render time; unreachable icons degrade gracefully to a label-only node.

---

## Quickstart

### Install

```bash
git clone https://github.com/LovHan/plot_agent.git
cd plot_agent

poetry install                  # registers the `plot-agent` console script
cp .env.example .env            # then fill in OPENAI_API_KEY
```

Optional extras:

```bash
poetry install -E pdf                     # feed .pdf BRDs directly (adds pypdf)
npm i -g @mermaid-js/mermaid-cli          # offline PNG rendering (otherwise Kroki HTTP is used)
```

### CLI

```bash
plot-agent --help

# Full pipeline: BRD → planner → executors → reviewer → mermaid → PNG
plot-agent generate samples/databricks_brd.txt

# .pdf input (requires the `pdf` extra), skip PNG, write only .mmd + summary.md
plot-agent generate samples/Databricks_Project_BRD.pdf --no-png

# Re-render PNG from an existing .mmd (no LLM tokens, runs in seconds)
plot-agent render out/diagram.mmd
plot-agent render out/diagram.mmd --backend mmdc --out diagram.png
```

Default output goes to `out/`:

```
out/
├── diagram.mmd        # mermaid source
├── diagram.png        # rendered (default: Kroki HTTP; mmdc available too)
└── summary.md         # plan + designs + review + embedded mermaid
```

### Python API

```python
from plot_agent import build_brd_to_mermaid_pipeline
from plot_agent.memory import make_checkpointer, make_store

app = build_brd_to_mermaid_pipeline(
    checkpointer=make_checkpointer(),
    store=make_store(),
)

result = app.invoke(
    {
        "brd": open("samples/databricks_brd.txt").read(),
        "out_dir": "out",
        "render_png": True,
    },
    {"configurable": {"thread_id": "demo"}, "recursion_limit": 50},
)
print(result["mermaid_code"])
```

---

## Project layout

```
plot_agent/
├── cli.py                       # argparse CLI: generate / render
├── llm.py                       # call_structured: LLM→JSON→schema, repair loop, LLMCallError
├── schemas.py                   # TechPlan / ComponentDesign / ReviewReport / MermaidIR
├── state.py                     # MultiAgentState + reducers
├── memory.py                    # InMemorySaver / InMemoryStore factories
├── graph/
│   ├── builder.py               # top-level pipeline assembly
│   ├── nodes/
│   │   ├── planner.py
│   │   ├── reviewer.py
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
└── test_smoke.py                # 4 tests: end-to-end / with memory / interaction proof / failure propagation
samples/
├── databricks_brd.txt
└── Databricks_Project_BRD.pdf
```

---

## Configuration

Variables read from `.env` (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | required |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | any OpenAI-compatible endpoint (Azure OpenAI / vLLM / Ollama-shim) |
| `PLANNER_MODEL` | — | used by planner / executors / mermaid_maker |
| `CRITIC_MODEL` | falls back to PLANNER_MODEL | used by reviewer |
| `OPENAI_MODEL` | last-resort fallback | used when neither of the above is set |
| `KROKI_URL` | `https://kroki.io` | point to a self-hosted Kroki if needed |
| `KROKI_TIMEOUT` | `30` | seconds |

Tunables in code:

| Location | Default | Purpose |
| --- | --- | --- |
| `subgraphs/executors.py::MAX_EXECUTOR_TURNS` | 2 | rounds inside the executor subgraph |
| `nodes/reviewer.py::MAX_REVIEW_ROUNDS` | 2 | how many times reviewer can bounce back to executors |
| `llm.py::_NETWORK_RETRIES` | 3 | exponential backoff on transient LLM network errors |

---

## Tests

```bash
poetry run pytest -q
```

`tests/conftest.py` monkeypatches `_invoke_llm` to return stub JSON keyed by the agent's system prompt. CI needs no API key, and the stub data lives **only in tests** — it never leaks into the `plot_agent/` package.

---

## Harness engineering checklist

| Concern | Implementation |
| --- | --- |
| **Context slicing** | `_role_context()` feeds each executor only the plan, peer designs, scratchpad, and any reviewer feedback addressed to that role |
| **Schema hard contract** | Pydantic schema at every agent boundary; LLM must return JSON |
| **Repair loop** | `call_structured` re-prompts with the validation error on parse failure; raises `LLMCallError` after the budget |
| **Network retry** | `_invoke_llm` retries on `APIConnectionError` / `APITimeoutError` / `RateLimitError` with exponential backoff |
| **Bounded retries** | `MAX_EXECUTOR_TURNS=2` / `MAX_REVIEW_ROUNDS=2`; the graph always terminates |
| **Memory, two tiers** | `InMemorySaver` (per-thread checkpoints) + `InMemoryStore` (project-level long-term memory) |
| **Observability** | Append-only `trace`, one `AIMessage` per agent, and `stream_mode="updates"` for live per-node events |
| **No silent fallback** | Failures always raise `LLMCallError`; nothing in the package fakes agent output |

---

## Roadmap

- [ ] Reviewer feedback re-runs only the `target_role`, not the whole executor subgraph
- [ ] `graph_linter` node: detect dependency cycles in `MermaidIR` and trigger a retry
- [ ] Parallel executors via `Send` API (one round of 5 roles concurrently; ~10 min → ~2 min)
- [ ] `SqliteSaver` checkpointer for resumable runs across processes
- [ ] Human-in-the-loop: pause on reviewer issues and wait for an ack
- [ ] Additional render backends: Graphviz / Excalidraw / draw.io
- [ ] LangSmith / LangFuse tracing integration

PRs and issues welcome.

---

## License

[MIT](./LICENSE)
