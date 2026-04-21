"""Test fixture: monkeypatch ``plot_agent.llm._invoke_llm`` and route returns by schema.

This way CI does not need ``OPENAI_API_KEY``, and we never bake any business-flavoured
fallback data into the production package.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


_PLAN_JSON: dict[str, Any] = {
    "summary": "test plan",
    "qa_chain": [
        {"question": "frontend?", "answer": "stub"},
        {"question": "backend?", "answer": "stub"},
    ],
    "frontend": "f",
    "backend": "b",
    "devops": "d",
    "data": "x",
    "security": "s",
    "deployment": "dep",
    "integrations": ["rest"],
    "open_questions": ["q?"],
}


def _design_json(role: str) -> dict[str, Any]:
    return {
        "role": role,
        "decisions": {"k": f"v-{role}"},
        "interfaces": [f"{role}-iface"],
        "depends_on": [],
        "notes": f"{role} stub",
    }


_PLAN_REVIEW_JSON: dict[str, Any] = {
    "ok": True,
    "score": 0.9,
    "issues": [],
    "suggestions": [],
    "missing_concerns": [],
}


_REVIEW_JSON: dict[str, Any] = {
    "ok": True,
    "score": 0.9,
    "issues": [],
    "suggestions": [],
    "target_role": None,
}


_IR_JSON: dict[str, Any] = {
    "direction": "LR",
    "nodes": [
        {"id": "user", "label": "User", "shape": "round"},
        {"id": "frontend", "label": "Frontend", "shape": "rect"},
        {"id": "backend", "label": "Backend", "shape": "rect"},
        {"id": "data", "label": "Data", "shape": "cyl"},
        {"id": "devops", "label": "DevOps", "shape": "rect"},
        {"id": "security", "label": "Security", "shape": "rect"},
    ],
    "edges": [{"src": "user", "dst": "frontend", "label": "use"}],
    "subgraphs": {
        "fe": ["frontend"],
        "be": ["backend"],
        "dt": ["data"],
        "dv": ["devops"],
        "sc": ["security"],
    },
}


def _fake_invoke_llm(system: str, user: str, *, model_env: str = "PLANNER_MODEL") -> str:
    """Pick a stub JSON response by spotting agent-specific keywords in the system prompt."""
    s = system.lower()
    if "high-level review" in s:
        return json.dumps(_PLAN_REVIEW_JSON)
    if "turn the brd into" in s:
        return json.dumps(_PLAN_JSON)
    if "principal architect reviewing" in s:
        return json.dumps(_REVIEW_JSON)
    if "mermaid flowchart ir" in s:
        return json.dumps(_IR_JSON)
    # Executor roles: prompts contain "you are the {role} architect".
    for role in ("frontend", "backend", "data", "devops", "security"):
        if f"you are the {role} architect" in s:
            return json.dumps(_design_json(role))
    raise AssertionError(f"unexpected LLM call; system preview: {system[:200]}")


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    """Apply the LLM stub to every test by default; opt out via ``monkeypatch.undo()``."""
    monkeypatch.setattr("plot_agent.llm._invoke_llm", _fake_invoke_llm)
    yield
