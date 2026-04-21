"""Mermaid -> PNG rendering.

Backend priority:
1. ``kroki``: HTTP POST to https://kroki.io/mermaid/png (default; zero local install, needs network).
2. ``mmdc`` : local ``@mermaid-js/mermaid-cli`` (offline use;
              install with ``npm i -g @mermaid-js/mermaid-cli``).

The ``auto`` mode (default) tries Kroki first and falls back to mmdc;
if both fail, ``RenderError`` is raised.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

log = logging.getLogger("plot_agent.render")

Backend = Literal["auto", "kroki", "mmdc"]

KROKI_URL = os.environ.get("KROKI_URL", "https://kroki.io")
KROKI_TIMEOUT = float(os.environ.get("KROKI_TIMEOUT", "30"))


class RenderError(RuntimeError):
    """PNG rendering failed (every backend was unavailable or returned an error)."""


_UA = "plot-agent/0.1 (+https://github.com/LovHan/archimaid-multi-agent-architecture-diagrams)"


def _render_kroki(mermaid_text: str) -> bytes:
    url = f"{KROKI_URL.rstrip('/')}/mermaid/png"
    req = urllib.request.Request(
        url,
        data=mermaid_text.encode("utf-8"),
        headers={"Content-Type": "text/plain", "User-Agent": _UA, "Accept": "image/png"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=KROKI_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        raise RenderError(f"kroki backend HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RenderError(f"kroki backend failed: {exc}") from exc


def _render_mmdc(mermaid_text: str, out_path: Path) -> bytes:
    if not shutil.which("mmdc"):
        raise RenderError("mmdc not found; install via `npm i -g @mermaid-js/mermaid-cli`")
    src = out_path.with_suffix(".mmd")
    src.write_text(mermaid_text, encoding="utf-8")
    try:
        subprocess.run(
            ["mmdc", "-i", str(src), "-o", str(out_path)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RenderError(f"mmdc failed: {exc}") from exc
    return out_path.read_bytes()


def render_png(mermaid_text: str, out_path: Path, *, backend: Backend = "auto") -> Path:
    """Write ``mermaid_text`` to ``out_path`` as a PNG and return the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if backend in ("kroki", "auto"):
        try:
            data = _render_kroki(mermaid_text)
            out_path.write_bytes(data)
            log.info("rendered via kroki -> %s", out_path)
            return out_path
        except RenderError as exc:
            if backend == "kroki":
                raise
            log.warning("kroki failed (%s); trying mmdc", exc)

    if backend in ("mmdc", "auto"):
        _render_mmdc(mermaid_text, out_path)
        log.info("rendered via mmdc -> %s", out_path)
        return out_path

    raise RenderError(f"unknown backend: {backend}")
