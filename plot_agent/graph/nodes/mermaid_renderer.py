"""MermaidRenderer: IR -> mermaid text + summary.md (+ optional PNG).

- Always writes ``diagram.mmd`` and ``summary.md`` (pure Python, no external deps).
- When ``state["render_png"]`` is truthy, calls ``plot_agent.render.png``
  (default: kroki, auto-fallback to mmdc).
  PNG failures are intentionally a soft-fail at the presentation layer: we record the
  error in ``trace`` and let the graph proceed, instead of poisoning the run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from plot_agent.render import RenderError, render_png
from plot_agent.schemas import MermaidIR
from plot_agent.state import MultiAgentState

AGENT_NAME = "mermaid_renderer"


def _build_summary(state: MultiAgentState, mermaid_code: str) -> str:
    plan = state.get("plan", {})
    designs = state.get("designs", {})
    review = state.get("review", {})
    plan_review = state.get("plan_review", {})
    lines = [
        "# Solution Summary",
        "",
        f"**Plan summary**: {plan.get('summary', '')}",
        "",
    ]
    if plan_review:
        lines += [
            f"## Plan Review (round {state.get('plan_review_rounds', 0)})",
            f"- ok: {plan_review.get('ok')}",
            f"- score: {plan_review.get('score')}",
            f"- issues: {plan_review.get('issues', [])}",
            f"- missing_concerns: {plan_review.get('missing_concerns', [])}",
            "",
        ]
    lines += ["## Self-Q&A Chain"]
    for qa in plan.get("qa_chain", []):
        lines += [f"- **Q**: {qa['question']}", f"  - **A**: {qa['answer']}"]
    lines += ["", "## Component Designs"]
    for role, dsn in designs.items():
        lines.append(f"### {role}")
        lines.append(f"- decisions: `{dsn.get('decisions', {})}`")
        lines.append(f"- interfaces: {dsn.get('interfaces', [])}")
        lines.append(f"- depends_on: {dsn.get('depends_on', [])}")
        if dsn.get("notes"):
            lines.append(f"- notes: {dsn['notes']}")
    lines += [
        "",
        f"## Review (round {state.get('review_rounds', 0)})",
        f"- ok: {review.get('ok')}",
        f"- score: {review.get('score')}",
        f"- issues: {review.get('issues', [])}",
        "",
        "## Flowchart",
        "",
        "```mermaid",
        mermaid_code,
        "```",
    ]
    return "\n".join(lines)


def mermaid_renderer_node(state: MultiAgentState) -> dict[str, Any]:
    ir = MermaidIR.model_validate(state.get("mermaid_ir", {}))
    mermaid_code = ir.to_mermaid()
    summary_md = _build_summary(state, mermaid_code)

    out_dir = Path(state.get("out_dir") or "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    mmd_path = out_dir / "diagram.mmd"
    md_path = out_dir / "summary.md"
    mmd_path.write_text(mermaid_code, encoding="utf-8")
    md_path.write_text(summary_md, encoding="utf-8")

    trace = [f"{AGENT_NAME}: wrote {mmd_path}, {md_path}"]
    if state.get("render_png"):
        backend = state.get("png_backend") or "auto"
        png_path = out_dir / "diagram.png"
        try:
            render_png(mermaid_code, png_path, backend=backend)
            trace.append(f"{AGENT_NAME}: wrote {png_path} via {backend}")
        except RenderError as exc:
            trace.append(f"{AGENT_NAME}: PNG render failed ({exc})")

    msg = AIMessage(content=f"[{AGENT_NAME}] rendered to {out_dir}", name=AGENT_NAME)
    return {
        "mermaid_code": mermaid_code,
        "summary_md": summary_md,
        "messages": [msg],
        "trace": trace,
    }
