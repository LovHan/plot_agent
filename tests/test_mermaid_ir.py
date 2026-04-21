"""Unit tests for MermaidIR rendering: colours, link styles, and icons."""

from __future__ import annotations

from plot_agent.schemas import DEFAULT_CLASSDEFS, MermaidEdge, MermaidIR, MermaidNode


def test_classdef_emitted_for_used_classes():
    ir = MermaidIR(
        nodes=[
            MermaidNode(id="a", label="A", style_class="internal"),
            MermaidNode(id="b", label="B", style_class="database"),
            MermaidNode(id="c", label="C"),  # no style_class -> no classDef emitted
        ],
    )
    text = ir.to_mermaid()
    assert "classDef internal " in text
    assert "classDef database " in text
    assert "classDef external " not in text  # unused class must not leak
    assert "class a internal" in text
    assert "class b database" in text


def test_link_style_matches_edge_style():
    ir = MermaidIR(
        nodes=[MermaidNode(id="a", label="A"), MermaidNode(id="b", label="B")],
        edges=[
            MermaidEdge(src="a", dst="b", label="sync", style="solid"),
            MermaidEdge(src="a", dst="b", label="evt", style="dashed"),
            MermaidEdge(src="a", dst="b", label="hot", style="thick"),
            MermaidEdge(src="a", dst="b", label="opt", style="dotted"),
        ],
    )
    text = ir.to_mermaid()
    assert "a -->|sync| b" in text
    assert "a -.->|evt| b" in text
    assert "a ==>|hot| b" in text
    assert "linkStyle 1 stroke:#666" in text
    assert "linkStyle 2 stroke:#000" in text
    assert "linkStyle 3 stroke:#999" in text
    # solid has no linkStyle override
    assert "linkStyle 0 " not in text


def test_icon_embeds_iconify_img_with_bounded_size():
    ir = MermaidIR(
        nodes=[MermaidNode(id="db", label="Postgres", shape="cyl", icon="logos:postgresql")],
    )
    text = ir.to_mermaid()
    assert "api.iconify.design/logos/postgresql.svg" in text
    assert "<img" in text
    # both width AND height pinned so mismatched iconify viewBoxes don't blow up the layout
    assert 'width="28"' in text and 'height="28"' in text
    assert "object-fit:contain" in text
    assert "Postgres" in text


def test_unknown_edge_style_falls_back_to_solid():
    ir = MermaidIR(
        nodes=[MermaidNode(id="a", label="A"), MermaidNode(id="b", label="B")],
        edges=[MermaidEdge(src="a", dst="b", style="wavy")],  # invalid
    )
    text = ir.to_mermaid()
    assert "a --> b" in text


def test_default_palette_contains_expected_categories():
    required = {"external", "internal", "database", "cache", "queue", "compute", "secret"}
    assert required <= set(DEFAULT_CLASSDEFS)
