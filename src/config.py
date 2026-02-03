from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Optional

import yaml


@dataclass
class SlackConfig:
    user_token: str
    token: str
    search_query: str


@dataclass
class OpenAIConfig:
    api_key: str
    model: str


@dataclass
class OllamaConfig:
    base_url: str
    model: str


@dataclass
class AppConfig:
    slack: SlackConfig
    openai: OpenAIConfig
    ollama: OllamaConfig
    ai_provider: str


_CACHED: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _CACHED
    if _CACHED is None:
        _CACHED = load_config()
    return _CACHED


def load_config(path: Optional[str] = None) -> AppConfig:
    data = _read_yaml(path or _default_path())

    slack_data = data.get("slack", {})
    openai_data = data.get("openai", {})
    ollama_data = data.get("ollama", {})
    ai_data = data.get("ai", {})

    slack = SlackConfig(
        user_token=_value(slack_data, "user_token", os.getenv("SLACK_USER_TOKEN", "")),
        token=_value(slack_data, "token", os.getenv("SLACK_TOKEN", "")),
        search_query=_value(
            slack_data, "search_query", os.getenv("SLACK_SEARCH_QUERY", "from:me")
        ),
    )
    openai = OpenAIConfig(
        api_key=_value(openai_data, "api_key", os.getenv("OPENAI_API_KEY", "")),
        model=_value(openai_data, "model", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
    )
    ollama = OllamaConfig(
        base_url=_value(
            ollama_data, "base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ),
        model=_value(ollama_data, "model", os.getenv("OLLAMA_MODEL", "")),
    )
    ai_provider = _value(ai_data, "provider", os.getenv("AI_PROVIDER", "auto"))

    return AppConfig(
        slack=slack,
        openai=openai,
        ollama=ollama,
        ai_provider=ai_provider.strip().lower() or "auto",
    )


def _default_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base_dir, "config", "config.yml")


def _read_yaml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _value(data: dict[str, Any], key: str, fallback: str) -> str:
    value = data.get(key)
    if value is None:
        return fallback
    return str(value)
