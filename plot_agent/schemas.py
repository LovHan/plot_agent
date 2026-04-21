"""Pydantic schemas: strict harness contracts for LLM output, with mild softening.

Strategy:
- Prefer plain string fields; if the LLM returns a dict/list, ``field_validator`` losslessly
  serializes it to JSON to preserve information.
- ``qa_chain`` items accept QAPair / dict / plain string; we normalize.
- ``summary`` is allowed to be empty (the model often forgets it during the repair pass).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except TypeError:
        return str(v)


# ---------- Planner ----------
class QAPair(BaseModel):
    question: str
    answer: str

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        if isinstance(v, str):
            if ":" in v:
                q, a = v.split(":", 1)
                return {"question": q.strip(), "answer": a.strip()}
            if "?" in v:
                q, _, a = v.partition("?")
                return {"question": q.strip() + "?", "answer": a.strip()}
            return {"question": v.strip(), "answer": ""}
        return v


class TechPlan(BaseModel):
    summary: str = ""
    qa_chain: list[QAPair] = Field(default_factory=list)
    frontend: str = ""
    backend: str = ""
    devops: str = ""
    data: str = ""
    security: str = ""
    deployment: str = ""
    integrations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @field_validator("frontend", "backend", "devops", "data", "security", "deployment", mode="before")
    @classmethod
    def _coerce_scalar(cls, v: Any) -> str:
        return _stringify(v)

    @field_validator("integrations", "open_questions", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [_stringify(x) for x in v]
        return [_stringify(v)]


# ---------- Executors ----------
class ComponentDesign(BaseModel):
    role: str
    decisions: dict[str, str] = Field(default_factory=dict)
    interfaces: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("decisions", mode="before")
    @classmethod
    def _coerce_decisions(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if isinstance(v, list):
            return {f"item_{i}": _stringify(x) for i, x in enumerate(v)}
        if isinstance(v, dict):
            return {k: _stringify(val) for k, val in v.items()}
        return {"value": _stringify(v)}

    @field_validator("interfaces", "depends_on", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [_stringify(x) for x in v]
        return [_stringify(v)]

    @field_validator("notes", mode="before")
    @classmethod
    def _coerce_notes(cls, v: Any) -> str:
        return _stringify(v)


# ---------- Reviewers ----------
def _coerce_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [_stringify(x) for x in v]
    return [_stringify(v)]


def _coerce_ok(v: Any) -> bool:
    if isinstance(v, str):
        return v.lower() in ("true", "yes", "1", "ok", "pass")
    return bool(v)


class PlanReviewReport(BaseModel):
    """High-level architecture review produced before the executor subgraph runs."""

    ok: bool = True
    score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_concerns: list[str] = Field(
        default_factory=list,
        description="Top-level concerns absent from the plan (e.g. DR, cost, compliance, observability).",
    )

    @field_validator("issues", "suggestions", "missing_concerns", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("ok", mode="before")
    @classmethod
    def _coerce_ok(cls, v: Any) -> bool:
        return _coerce_ok(v)


class ReviewReport(BaseModel):
    """Low-level design review produced after executors elaborate each component."""

    ok: bool = True
    score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    target_role: str | None = None

    @field_validator("issues", "suggestions", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("ok", mode="before")
    @classmethod
    def _coerce_ok(cls, v: Any) -> bool:
        return _coerce_ok(v)


# ---------- Mermaid IR ----------

# Palette mapping semantic style class -> Mermaid classDef rule.
# Colours follow the draw.io semantic palette, which reads well on white and dark backgrounds.
DEFAULT_CLASSDEFS: dict[str, str] = {
    "external":      "fill:#fff2cc,stroke:#d6b656,stroke-width:2px,color:#222",
    "internal":      "fill:#dae8fc,stroke:#6c8ebf,stroke-width:1.5px,color:#222",
    "database":      "fill:#d5e8d4,stroke:#82b366,stroke-width:1.5px,color:#222",
    "cache":         "fill:#e1d5e7,stroke:#9673a6,stroke-width:1.5px,color:#222",
    "queue":         "fill:#e1d5e7,stroke:#9673a6,stroke-width:1.5px,color:#222",
    "compute":       "fill:#dae8fc,stroke:#6c8ebf,stroke-width:1.5px,color:#222",
    "secret":        "fill:#f8cecc,stroke:#b85450,stroke-width:1.5px,color:#222",
    "observability": "fill:#f5f5f5,stroke:#666666,stroke-width:1px,color:#222",
    "ai":            "fill:#ffe6cc,stroke:#d79b00,stroke-width:1.5px,color:#222",
}

# Link styling.  The arrow glyph alone does not carry colour, so we emit `linkStyle` entries
# for any non-default style to differentiate sync / async / critical / optional edges.
_ARROW_BY_STYLE: dict[str, str] = {
    "solid":  "-->",
    "dashed": "-.->",   # Mermaid dashed
    "thick":  "==>",    # Mermaid thick
    "dotted": "-.->",   # same arrow as dashed; linkStyle adds a lighter colour
}
_LINK_STYLE_RULE: dict[str, str | None] = {
    "solid":  None,
    "dashed": "stroke:#666,stroke-width:1.5px,stroke-dasharray:6 4",
    "thick":  "stroke:#000,stroke-width:3px",
    "dotted": "stroke:#999,stroke-width:1px,stroke-dasharray:2 3",
}

# Iconify endpoint used to embed a logo inside a node label.
_ICONIFY_ENDPOINT = "https://api.iconify.design"


def _iconify_url(icon: str) -> str:
    """Translate ``"logos:databricks"`` -> ``"https://api.iconify.design/logos/databricks.svg"``."""
    return f"{_ICONIFY_ENDPOINT}/{icon.replace(':', '/')}.svg"


class MermaidNode(BaseModel):
    id: str
    label: str
    shape: str = "rect"                       # rect | round | diamond | cyl | cloud
    style_class: str | None = None            # key in DEFAULT_CLASSDEFS (or custom classDef)
    icon: str | None = None                   # iconify key, e.g. "logos:databricks"


class MermaidEdge(BaseModel):
    src: str
    dst: str
    label: str | None = None
    style: str = "solid"                      # solid | dashed | thick | dotted

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "src" not in v and "from" in v:
                v["src"] = v.pop("from")
            if "dst" not in v and "to" in v:
                v["dst"] = v.pop("to")
        return v

    @field_validator("style", mode="before")
    @classmethod
    def _normalize_style(cls, v: Any) -> str:
        if not isinstance(v, str):
            return "solid"
        s = v.lower().strip()
        return s if s in _ARROW_BY_STYLE else "solid"


class MermaidIR(BaseModel):
    direction: str = "LR"
    nodes: list[MermaidNode] = Field(default_factory=list)
    edges: list[MermaidEdge] = Field(default_factory=list)
    subgraphs: dict[str, list[str]] = Field(default_factory=dict)
    # Optional overrides; merged over DEFAULT_CLASSDEFS.  Lets the LLM introduce a new category.
    classdefs: dict[str, str] = Field(default_factory=dict)

    def _effective_classdefs(self) -> dict[str, str]:
        merged = dict(DEFAULT_CLASSDEFS)
        merged.update(self.classdefs or {})
        return merged

    def _node_label(self, n: MermaidNode) -> str:
        """Embed an iconify logo above the label when ``icon`` is set."""
        if n.icon:
            return f'<img src="{_iconify_url(n.icon)}" width="28"/><br/>{n.label}'
        return n.label

    def to_mermaid(self) -> str:
        shape_fmt = {
            "rect": "{id}[{label}]",
            "round": "{id}({label})",
            "diamond": "{id}{{{label}}}",
            "cyl": "{id}[({label})]",
            "cloud": "{id}>{label}]",
        }
        lines = [f"flowchart {self.direction}"]

        classdefs = self._effective_classdefs()
        used_classes = sorted({n.style_class for n in self.nodes if n.style_class and n.style_class in classdefs})
        for cls in used_classes:
            lines.append(f"  classDef {cls} {classdefs[cls]}")

        in_group: set[str] = set()
        for grp, ids in self.subgraphs.items():
            safe_grp = grp.replace(" ", "_")
            lines.append(f"  subgraph {safe_grp}")
            for n in self.nodes:
                if n.id in ids:
                    tpl = shape_fmt.get(n.shape, shape_fmt["rect"])
                    lines.append("    " + tpl.format(id=n.id, label=self._node_label(n)))
                    in_group.add(n.id)
            lines.append("  end")
        for n in self.nodes:
            if n.id in in_group:
                continue
            tpl = shape_fmt.get(n.shape, shape_fmt["rect"])
            lines.append("  " + tpl.format(id=n.id, label=self._node_label(n)))

        # class <id> <class> assignments
        for n in self.nodes:
            if n.style_class and n.style_class in classdefs:
                lines.append(f"  class {n.id} {n.style_class}")

        # Edges
        for e in self.edges:
            arrow = _ARROW_BY_STYLE.get(e.style, "-->")
            if e.label:
                lines.append(f"  {e.src} {arrow}|{e.label}| {e.dst}")
            else:
                lines.append(f"  {e.src} {arrow} {e.dst}")

        # linkStyle for any non-default edge style
        for i, e in enumerate(self.edges):
            rule = _LINK_STYLE_RULE.get(e.style)
            if rule:
                lines.append(f"  linkStyle {i} {rule}")

        return "\n".join(lines)


__all__ = [
    "QAPair",
    "TechPlan",
    "ComponentDesign",
    "PlanReviewReport",
    "ReviewReport",
    "MermaidNode",
    "MermaidEdge",
    "MermaidIR",
]


def plan_to_dict(p: TechPlan) -> dict[str, Any]:
    return p.model_dump()


def design_to_dict(d: ComponentDesign) -> dict[str, Any]:
    return d.model_dump()
