"""Smoke tests: the pipeline compiles, runs end-to-end against a stubbed LLM, and writes artifacts.

LLM calls are intercepted by the ``stub_llm`` fixture in ``conftest.py`` so no
``OPENAI_API_KEY`` is required.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

from plot_agent import build_brd_to_mermaid_pipeline
from plot_agent.llm import LLMCallError
from plot_agent.memory import make_checkpointer, make_store


BRD_SAMPLE = """
Build a multi-tenant SaaS form platform:
- customers submit form data through the web
- the backend pushes data downstream via webhooks to a CRM
- per-tenant data isolation
- target deployment: Azure
"""


def _state(brd: str, out_dir: Path) -> dict:
    return {
        "brd": brd,
        "messages": [HumanMessage(content=brd)],
        "project_id": "demo",
        "out_dir": str(out_dir),
    }


def test_pipeline_runs_end_to_end(tmp_path):
    app = build_brd_to_mermaid_pipeline()
    out = app.invoke(_state(BRD_SAMPLE, tmp_path))

    assert out["plan"]["qa_chain"], "planner must produce QA chain"
    assert out.get("plan_review"), "plan_reviewer must record a verdict"
    assert out.get("plan_review_rounds", 0) >= 1
    assert {"frontend", "backend", "data", "devops", "security"} <= set(out["designs"].keys())
    assert out["mermaid_code"].startswith("flowchart")
    assert "subgraph" in out["mermaid_code"]
    assert (tmp_path / "diagram.mmd").exists()
    assert (tmp_path / "summary.md").exists()


def test_plan_reviewer_loops_back_to_planner(tmp_path, monkeypatch):
    """When the plan_reviewer reports ok=false, the planner must rerun (budget respected)."""
    import json

    from plot_agent.graph.nodes.plan_reviewer import MAX_PLAN_REVIEW_ROUNDS
    from tests.conftest import _PLAN_JSON, _PLAN_REVIEW_JSON, _REVIEW_JSON

    planner_calls = {"n": 0}
    plan_review_calls = {"n": 0}

    def fake(system: str, user: str, *, model_env: str = "PLANNER_MODEL") -> str:
        s = system.lower()
        if "high-level review" in s:
            plan_review_calls["n"] += 1
            if plan_review_calls["n"] < MAX_PLAN_REVIEW_ROUNDS + 1:
                return json.dumps({**_PLAN_REVIEW_JSON, "ok": False, "issues": ["force revise"]})
            return json.dumps(_PLAN_REVIEW_JSON)
        if "turn the brd into" in s:
            planner_calls["n"] += 1
            return json.dumps(_PLAN_JSON)
        if "principal architect reviewing" in s:
            return json.dumps(_REVIEW_JSON)
        if "mermaid flowchart ir" in s:
            from tests.conftest import _IR_JSON

            return json.dumps(_IR_JSON)
        from tests.conftest import _design_json

        for role in ("frontend", "backend", "data", "devops", "security"):
            if f"you are the {role} architect" in s:
                return json.dumps(_design_json(role))
        raise AssertionError(system[:120])

    monkeypatch.setattr("plot_agent.llm._invoke_llm", fake)
    app = build_brd_to_mermaid_pipeline()
    out = app.invoke(_state(BRD_SAMPLE, tmp_path))

    assert planner_calls["n"] >= 2, "planner must rerun after a failed plan review"
    assert out["plan_review"]["ok"] in (True, False)
    assert out.get("plan_review_rounds", 0) >= 1


def test_pipeline_with_memory(tmp_path):
    app = build_brd_to_mermaid_pipeline(
        checkpointer=make_checkpointer(),
        store=make_store(),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    out = app.invoke(_state(BRD_SAMPLE, tmp_path), cfg)
    assert out["review"]["ok"] in (True, False)
    assert out.get("executor_turn", 0) >= 1
    assert len(out.get("trace", [])) > 0


def test_executor_interaction(tmp_path):
    """Executors leave notes for each other in ``exec_scratch``; this proves they interacted."""
    app = build_brd_to_mermaid_pipeline()
    out = app.invoke(_state(BRD_SAMPLE, tmp_path))
    scratch = out.get("exec_scratch", {})
    for role in ("frontend", "backend", "data", "devops", "security"):
        assert f"note_{role}" in scratch, f"missing scratch note for {role}"


def test_llm_error_propagates(tmp_path, monkeypatch):
    """When the LLM is fully unavailable the pipeline must raise ``LLMCallError``,
    never swallow it with a silent fallback."""

    def boom(*_a, **_kw):
        raise LLMCallError("simulated outage")

    monkeypatch.setattr("plot_agent.llm._invoke_llm", boom)
    app = build_brd_to_mermaid_pipeline()

    try:
        app.invoke(_state(BRD_SAMPLE, tmp_path))
    except LLMCallError:
        return
    except Exception as exc:
        if isinstance(exc.__cause__, LLMCallError) or "simulated outage" in str(exc):
            return
        raise
    raise AssertionError("expected LLMCallError to propagate")
