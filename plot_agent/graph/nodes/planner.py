"""Planner agent: BRD -> Self-Q&A chain-of-thought -> TechPlan.

Revision mode: if ``state.plan_review`` contains an ok=false report, this node treats
that feedback as the primary instruction and revises the previous plan accordingly.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from plot_agent.llm import call_structured
from plot_agent.schemas import TechPlan, plan_to_dict
from plot_agent.state import MultiAgentState

AGENT_NAME = "planner"

SYSTEM_PROMPT = """You are a senior solution architect. Turn the BRD into a concise technology plan.
You MUST produce a self-questioning chain-of-thought in `qa_chain`, covering at minimum:
frontend / backend / runtime (AKS vs App Service vs serverless) / integration (API or webhook) /
deployment target / secret management / database / open questions.

If a "Plan review feedback" section is supplied, the review was unsatisfied with a previous
plan.  Treat the issues, suggestions, and missing_concerns as MUST-ADDRESS instructions, and
produce a revised plan that directly resolves them without losing good decisions from the
prior version.

Respond with ONLY a single JSON object, NO prose, matching EXACTLY this shape (all string fields are plain strings, not nested objects):
{
  "summary": "<one sentence tech solution>",
  "qa_chain": [
    {"question": "What is the frontend?", "answer": "..."},
    {"question": "Backend?", "answer": "..."}
  ],
  "frontend": "<plain text>",
  "backend":  "<plain text>",
  "devops":   "<plain text>",
  "data":     "<plain text>",
  "security": "<plain text>",
  "deployment": "<plain text>",
  "integrations": ["..."],
  "open_questions": ["..."]
}"""


def _build_user_prompt(state: MultiAgentState) -> str:
    brd = state.get("brd", "")
    review = state.get("plan_review") or {}
    previous = state.get("plan") or {}
    if previous and review and not review.get("ok", True):
        return (
            f"BRD:\n{brd}\n\n"
            f"Previous plan (to revise):\n{previous}\n\n"
            f"Plan review feedback (MUST address):\n"
            f"- issues: {review.get('issues', [])}\n"
            f"- suggestions: {review.get('suggestions', [])}\n"
            f"- missing_concerns: {review.get('missing_concerns', [])}\n"
        )
    return f"BRD:\n{brd}"


def planner_node(state: MultiAgentState) -> dict[str, Any]:
    plan = call_structured(
        TechPlan,
        SYSTEM_PROMPT,
        _build_user_prompt(state),
        model_env="PLANNER_MODEL",
    )
    revision = bool(state.get("plan_review")) and not (state.get("plan_review") or {}).get("ok", True)
    verb = "revised" if revision else "produced"
    msg = AIMessage(content=f"[{AGENT_NAME}] plan {verb}: {plan.summary}", name=AGENT_NAME)
    return {
        "plan": plan_to_dict(plan),
        "messages": [msg],
        "trace": [f"{AGENT_NAME}: {verb} TechPlan with {len(plan.qa_chain)} QA steps"],
    }
