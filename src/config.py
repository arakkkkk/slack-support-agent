from __future__ import annotations

from dataclasses import dataclass
import os
import sys
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
class AzureOpenAIConfig:
    api_key: str
    endpoint: str
    deployment: str
    api_version: str


@dataclass
class OllamaConfig:
    base_url: str
    model: str


@dataclass
class AppConfig:
    slack: SlackConfig
    openai: OpenAIConfig
    azure_openai: AzureOpenAIConfig
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
    azure_openai_data = data.get("azure_openai", data.get("azure", {}))
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
    azure_openai = AzureOpenAIConfig(
        api_key=_value(
            azure_openai_data,
            "api_key",
            os.getenv("AZURE_OPENAI_API_KEY", ""),
        ),
        endpoint=_value(
            azure_openai_data,
            "endpoint",
            os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        ),
        deployment=_value(
            azure_openai_data,
            "deployment",
            os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
        ),
        api_version=_value(
            azure_openai_data,
            "api_version",
            os.getenv("AZURE_OPENAI_API_VERSION", ""),
        ),
    )
    ollama = OllamaConfig(
        base_url=_value(
            ollama_data, "base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ),
        model=_value(ollama_data, "model", os.getenv("OLLAMA_MODEL", "")),
    )
    ai_provider = _value(ai_data, "provider", os.getenv("AI_PROVIDER", "ollama"))

    return AppConfig(
        slack=slack,
        openai=openai,
        azure_openai=azure_openai,
        ollama=ollama,
        ai_provider=ai_provider.strip().lower() or "ollama",
    )


def _default_path() -> str:
    override = os.environ.get("SLACK_AGENT_CONFIG")
    if override:
        return override

    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "config", "config.yml")

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
