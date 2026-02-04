from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional
_FILE_MAP = {
    "system": "system.md",
    "reply": "reply.md",
    "summary": "summary.md",
    "todo": "todo.md",
}

_CACHE: Optional[Dict[str, str]] = None


def instruction_for(mode: str) -> str:
    return _get_prompt(mode)


def system_prompt() -> str:
    return _get_prompt("system")


def _get_prompt(key: str) -> str:
    prompts = _load_prompts()
    if key not in prompts:
        raise FileNotFoundError(f"prompt file not found for key: {key}")
    return prompts[key].strip()


def _load_prompts() -> Dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    _CACHE = {}
    base = _prompt_dir()
    for key, filename in _FILE_MAP.items():
        path = base / filename
        if not path.exists():
            continue
        _CACHE[key] = path.read_text(encoding="utf-8").strip()
    return _CACHE


def _prompt_dir() -> Path:
    override = os.environ.get("SLACK_AGENT_PROMPTS")
    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "prompts"

    root = Path(__file__).resolve().parents[1]
    return root / "prompts"


SYSTEM_PROMPT = system_prompt()
