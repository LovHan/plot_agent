"""Shared graph state for the BRD -> Mermaid pipeline.

Harness rule: state is the single source of truth across nodes; every field has a clear owner.

- brd:           raw BRD text supplied by the caller.
- plan:          TechPlan dict produced by the planner agent (includes a self-Q&A CoT).
- designs:       role -> ComponentDesign dict, iteratively updated by the executor subgraph.
- exec_scratch:  shared scratchpad inside the executor subgraph so roles can see each
                 other's notes (the "interaction" surface).
- review:        ReviewReport dict.  review_rounds: how many review rounds have run.
- mermaid_ir / mermaid_code / summary_md: final artifacts.
- trace:         append-only observability log lines.
- thread_id / project_id: memory dimensions
                          (thread = a single conversation, project = cross-thread long-term memory).
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def _merge_dict(old: dict | None, new: dict | None) -> dict:
    """Reducer: shallow-merge dict fields like designs / scratchpad."""
    return {**(old or {}), **(new or {})}


def _append_list(old: list | None, new: list | None) -> list:
    return (old or []) + (new or [])


class MultiAgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]

    brd: str
    plan: dict[str, Any]
    plan_review: dict[str, Any]
    plan_review_rounds: int

    designs: Annotated[dict[str, dict[str, Any]], _merge_dict]
    exec_scratch: Annotated[dict[str, Any], _merge_dict]

    review: dict[str, Any]
    review_rounds: int
    executor_turn: int

    mermaid_ir: dict[str, Any]
    mermaid_code: str
    summary_md: str

    trace: Annotated[list[str], _append_list]

    thread_id: str
    project_id: str
    out_dir: str
    render_png: bool
    png_backend: str
