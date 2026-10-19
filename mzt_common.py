#!/usr/bin/env python3
"""Shared helpers for the three experiment scripts.

One place for: API key resolution, endpoint resolution, data paths,
and pypdf text extraction. All scripts behave identically with respect
to configuration precedence:

  key:      MZT_LLM_KEY  >  profile.json key  >  ~/.mzt_demo_key
  endpoint: MZT_LLM_BASE_URL / MZT_LLM_MODEL > profile.json (explicit)

Client material never lives in this repository: scripts read from
`data/` (gitignored) by default, overridable via environment variables.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_URL = ""
DEFAULT_MODEL = ""


def config_path(filename: str) -> Path:
    """MZT_CONFIG_DIR isolates local settings, including during tests."""
    return Path(os.environ.get("MZT_CONFIG_DIR", str(Path.home()))) / filename


def write_private(path: Path, content: str) -> None:
    """Create configuration with restrictive permissions before writing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content)


def load_profile() -> Dict[str, Any]:
    """Non-sensitive profile written by setup_key.py."""
    pf = config_path(".mzt_demo_profile.json")
    if pf.exists():
        try:
            value = json.loads(pf.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}


def read_key() -> Optional[str]:
    key = os.environ.get("MZT_LLM_KEY")
    if key:
        return key.strip()
    profile = load_profile()
    if profile.get("key"):
        return str(profile["key"]).strip()
    key_file = config_path(".mzt_demo_key")
    if key_file.exists():
        stored = key_file.read_text(encoding="utf-8").strip()
        return stored or None
    return None


def resolve_endpoint() -> tuple[str, str]:
    """(base_url, model) with environment > profile > defaults."""
    profile = load_profile()
    base_url = (os.environ.get("MZT_LLM_BASE_URL") or profile.get("base_url")
                or DEFAULT_BASE_URL)
    model = (os.environ.get("MZT_LLM_MODEL") or profile.get("model")
             or DEFAULT_MODEL)
    return str(base_url).strip(), str(model).strip()


def resolve_stage(stage: str) -> Dict[str, Optional[str]]:
    """Per-stage config for decompose / main / vision.

    Precedence per field: MZT_<STAGE>_BASE_URL / _MODEL / _KEY env var
    > profile.stages.<stage> > global profile > defaults. A stage that
    overrides model/base_url but not key inherits the global key.
    """
    profile = load_profile()
    stages = profile.get("stages") or {}
    cfg = stages.get(stage) or {}
    prefix = f"MZT_{stage.upper()}_"
    base_url = (os.environ.get(prefix + "BASE_URL") or cfg.get("base_url")
                or os.environ.get("MZT_LLM_BASE_URL")
                or profile.get("base_url") or DEFAULT_BASE_URL)
    model = (os.environ.get(prefix + "MODEL") or cfg.get("model")
             or os.environ.get("MZT_LLM_MODEL")
             or profile.get("model") or DEFAULT_MODEL)
    key = (os.environ.get(prefix + "KEY") or cfg.get("key") or read_key())
    return {"base_url": str(base_url).strip(), "model": str(model).strip(),
            "key": (key.strip() if isinstance(key, str) else key)}


def data_dir() -> Path:
    """Client-material directory (gitignored). Place your files here."""
    return Path(os.environ.get("MZT_DATA_DIR", str(REPO_ROOT / "data")))


def default_pdf() -> Path:
    """Main annual-report PDF for E1/E3. Override with MZT_PDF."""
    return Path(os.environ.get("MZT_PDF", str(data_dir() / "sample_report.pdf")))


def material_root() -> Path:
    """Unzipped full material package for E2. Override with MZT_MATERIAL_ROOT."""
    return Path(os.environ.get(
        "MZT_MATERIAL_ROOT", str(data_dir() / "sample_attachments")))


def pdf_text(path: Path) -> str:
    """Extract all text from a PDF via pypdf (demo-grade layer-1 parser)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def contained_path(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks outside the configured material directory."""
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path is outside the configured material directory")
    return target
