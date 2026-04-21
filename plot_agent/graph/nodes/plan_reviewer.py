"""Plan reviewer: high-level architecture critique of the TechPlan.

Runs between ``planner`` and the executor subgraph.  If the plan is weak, the pipeline
loops back to ``planner`` with this review's feedback instead of burning ~10 LLM calls
elaborating a flawed foundation.  The review is intentionally coarse-grained:
component-level critique is the job of the post-executor ``reviewer`` (design reviewer).
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from plot_agent.llm import call_structured
from plot_agent.schemas import PlanReviewReport
from plot_agent.state import MultiAgentState

AGENT_NAME = "plan_reviewer"
MAX_PLAN_REVIEW_ROUNDS = 2

SYSTEM_PROMPT = """You are a principal architect doing a high-level review of a proposed
solution plan BEFORE the team starts elaborating individual components.  Your job is to
catch architectural mistakes early, not to audit component-level details.

Evaluate the plan on these axes:
- BRD fit            : do the tech choices match the BRD's real constraints
                       (cloud hint, scale, latency, compliance, team skills)?
- Stack coherence    : do the frontend / backend / data / runtime / deployment pieces
                       compose cleanly, or are there obvious misfits?
- Runtime pragmatism : is the chosen compute model (serverless vs container vs managed
                       platform) right-sized, or overkill / underkill?
- Integration model  : are the sync/async patterns sensible for the workload?
- Missing concerns   : did the plan omit something important the BRD implies
                       (identity / DR / cost / observability / data residency / SLO)?
- Open questions     : are the questions the right ones, or do they dodge real risks?

Do NOT critique at the resource-name level (catalog names, SKU choices, VNet layout,
exact API paths).  That is the design reviewer's job later in the pipeline.

Respond with ONLY a single JSON object, NO prose:
{
  "ok": true | false,
  "score": 0.0-1.0,
  "issues": ["<architectural problem>", ...],
  "suggestions": ["<concrete course correction>", ...],
  "missing_concerns": ["<top-level concern absent from the plan>", ...]
}

Set ok=true only if the plan is a sound foundation the team can safely elaborate.
If score < 0.7 or there are high-impact issues, set ok=false so the planner revises."""


def plan_reviewer_node(state: MultiAgentState) -> dict[str, Any]:
    brd = state.get("brd", "")
    plan = state.get("plan", {})

    report = call_structured(
        PlanReviewReport,
        SYSTEM_PROMPT,
        f"BRD:\n{brd}\n\nProposed plan:\n{plan}",
        model_env="CRITIC_MODEL",
    )
    rounds = state.get("plan_review_rounds", 0) + 1
    msg = AIMessage(
        content=(
            f"[{AGENT_NAME}] ok={report.ok} score={report.score:.2f} "
            f"issues={len(report.issues)} missing={len(report.missing_concerns)}"
        ),
        name=AGENT_NAME,
    )
    return {
        "plan_review": report.model_dump(),
        "plan_review_rounds": rounds,
        "messages": [msg],
        "trace": [
            f"{AGENT_NAME}: round={rounds} ok={report.ok} "
            f"score={report.score:.2f} issues={len(report.issues)}"
        ],
    }
