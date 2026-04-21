"""Conditional routing functions for the pipeline.

- ``route_after_plan_review``: forward to ``executors`` if the plan is good enough,
  else loop back to ``planner`` (bounded by ``MAX_PLAN_REVIEW_ROUNDS``).
- ``route_after_review``: forward to ``mermaid_maker`` if the design is good enough,
  else loop back to ``executors`` (bounded by ``MAX_REVIEW_ROUNDS``).
"""

from __future__ import annotations

from plot_agent.graph.nodes.plan_reviewer import MAX_PLAN_REVIEW_ROUNDS
from plot_agent.graph.nodes.reviewer import MAX_REVIEW_ROUNDS
from plot_agent.state import MultiAgentState


def route_after_plan_review(state: MultiAgentState) -> str:
    review = state.get("plan_review") or {}
    rounds = state.get("plan_review_rounds", 0)
    if review.get("ok"):
        return "executors"
    if rounds >= MAX_PLAN_REVIEW_ROUNDS:
        return "executors"
    return "planner"


def route_after_review(state: MultiAgentState) -> str:
    review = state.get("review") or {}
    rounds = state.get("review_rounds", 0)
    if review.get("ok"):
        return "mermaid_maker"
    if rounds >= MAX_REVIEW_ROUNDS:
        return "mermaid_maker"
    return "executors"
