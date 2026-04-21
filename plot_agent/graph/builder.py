"""Top-level assembly of the BRD -> Mermaid pipeline graph.

Topology::

    START
      |
      v
    planner --> plan_reviewer
      ^              |
      |              +-- ok | budget exhausted --> executors (subgraph) --> reviewer
      |                                                 ^                      |
      +-- not ok & retry (plan_review_rounds < N) <-----|---- not ok & retry --+
                                                        |                      |
                                                        +----- ok | budget ----+
                                                                               |
                                                                               v
                                                              mermaid_maker --> mermaid_renderer --> END

Memory:
- checkpointer: per-thread, resumable runs (optional).
- store:        cross-thread project-level long-term memory, addressed by
                ``MultiAgentState.project_id``.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from plot_agent.graph.nodes.mermaid_maker import mermaid_maker_node
from plot_agent.graph.nodes.mermaid_renderer import mermaid_renderer_node
from plot_agent.graph.nodes.plan_reviewer import plan_reviewer_node
from plot_agent.graph.nodes.planner import planner_node
from plot_agent.graph.nodes.reviewer import reviewer_node
from plot_agent.graph.nodes.routing import route_after_plan_review, route_after_review
from plot_agent.graph.subgraphs.executors import build_executor_subgraph
from plot_agent.state import MultiAgentState


def build_brd_to_mermaid_pipeline(*, checkpointer=None, store=None):
    """Return a compiled pipeline graph.

    Example::

        from plot_agent import build_brd_to_mermaid_pipeline
        from plot_agent.memory import make_checkpointer, make_store

        app = build_brd_to_mermaid_pipeline(
            checkpointer=make_checkpointer(),
            store=make_store(),
        )
        out = app.invoke(
            {"brd": "We are building a multi-tenant SaaS..."},
            {"configurable": {"thread_id": "t1"}},
        )
        print(out["mermaid_code"])
    """
    executor_subgraph = build_executor_subgraph()

    g = StateGraph(MultiAgentState)
    g.add_node("planner", planner_node)
    g.add_node("plan_reviewer", plan_reviewer_node)
    g.add_node("executors", executor_subgraph)
    g.add_node("reviewer", reviewer_node)
    g.add_node("mermaid_maker", mermaid_maker_node)
    g.add_node("mermaid_renderer", mermaid_renderer_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "plan_reviewer")
    g.add_conditional_edges(
        "plan_reviewer",
        route_after_plan_review,
        {"planner": "planner", "executors": "executors"},
    )
    g.add_edge("executors", "reviewer")
    g.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"executors": "executors", "mermaid_maker": "mermaid_maker"},
    )
    g.add_edge("mermaid_maker", "mermaid_renderer")
    g.add_edge("mermaid_renderer", END)

    return g.compile(checkpointer=checkpointer, store=store)


# Backward-compatible alias.
build_multi_agent_graph = build_brd_to_mermaid_pipeline
