from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import get_config
from prompts import instruction_for, system_prompt


@dataclass
class SupportResult:
    content: str
    model: str


def generate_support(text: str, mode: str, context: Optional[str] = None) -> SupportResult:
    context = context or ""
    mode = mode.lower()
    config = get_config()
    # プロバイダ指定があれば優先し、失敗時は順次フォールバックする
    if config.ai_provider == "openai" and _openai_available(config):
        result = _generate_with_openai(text, mode, context, config)
        if result:
            return result
    if config.ai_provider == "ollama" and _ollama_available(config):
        result = _generate_with_ollama(text, mode, context, config)
        if result:
            return result
    return _fallback_support(text, mode, context)


def _openai_available(config) -> bool:
    return bool(config.openai.api_key)


def _ollama_available(config) -> bool:
    return bool(config.ollama.model)


def _resolve_provider(value: str) -> str:
    # 設定が明示されている場合のみ固定
    provider = (value or "").strip().lower()
    if provider in {"openai", "ollama"}:
        return provider
    return "auto"


def _generate_with_openai(
    text: str, mode: str, context: str, config
) -> Optional[SupportResult]:
    try:
        from openai import OpenAI
    except Exception:
        return None

    api_key = config.openai.api_key
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    instruction = instruction_for(mode)
    messages = _build_messages(instruction, context, text)
    try:
        response = client.responses.create(
            model=config.openai.model or "gpt-4o-mini",
            input=messages,
        )
    except Exception:
        return None

    content = response.output_text.strip() if hasattr(response, "output_text") else ""
    if not content:
        return None
    return SupportResult(content=content, model="openai")


def _generate_with_ollama(
    text: str, mode: str, context: str, config
) -> Optional[SupportResult]:
    import json
    import urllib.error
    import urllib.request

    model = config.ollama.model
    if not model:
        return None
    base_url = (config.ollama.base_url or "http://localhost:11434").rstrip("/")
    instruction = instruction_for(mode)
    messages = _build_messages(instruction, context, text)

    # Ollama の /api/chat 形式に合わせたペイロード
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None

    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    content = ""
    if isinstance(parsed, dict):
        content = (
            parsed.get("message", {}).get("content")
            or parsed.get("response", "")
            or ""
        )
    if not content:
        return None
    return SupportResult(content=content.strip(), model="ollama")


def _fallback_support(text: str, mode: str, context: str) -> SupportResult:
    if mode == "summary":
        content = _simple_summary(text)
        return SupportResult(content=content, model="fallback")
    if mode == "todo":
        content = _simple_todo(text)
        return SupportResult(content=content, model="fallback")
    return SupportResult(content=_simple_reply(text), model="fallback")


def _build_messages(instruction: str, context: str, text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": _build_user_prompt(instruction, context, text)},
    ]


def _build_user_prompt(instruction: str, context: str, text: str) -> str:
    return f"{instruction}\n\n[コンテキスト]\n{context}\n\n[メッセージ]\n{text}"


def _simple_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "内容が空のため要約できません。"
    if len(lines) == 1:
        return f"要点: {lines[0][:120]}"
    summary = " / ".join(lines[:2])
    return f"要点: {summary[:180]}"


def _simple_reply(text: str) -> str:
    return (
        "返信案:\n"
        "ありがとうございます。内容を確認しました。\n"
        "必要であれば詳細や期限を共有いただけますか？\n"
        "こちらで対応方針を整理して返答します。"
    )


def _simple_todo(text: str) -> str:
    return (
        "TODO:\n"
        "- 依頼内容の要点を整理する\n"
        "- 期限・優先度を確認する\n"
        "- 必要な情報や担当者を洗い出す\n"
        "- 返信ドラフトを作成する"
    )
