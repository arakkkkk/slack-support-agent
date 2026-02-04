from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from src.config import get_config
from src.prompts import instruction_for, system_prompt


@dataclass
class SupportResult:
    content: str
    model: str
    error: Optional[str] = None


def generate_support(text: str, mode: str, context: Optional[str] = None) -> SupportResult:
    context = context or ""
    mode = mode.lower()
    config = get_config()
    provider = _resolve_provider(config.ai_provider)
    if provider is None:
        return _error_support(
            ["AI providerはopenai/ollamaのいずれかに設定してください。"]
        )
    if provider == "openai":
        result, error = _generate_with_openai(text, mode, context, config)
    else:
        result, error = _generate_with_ollama(text, mode, context, config)
    if result:
        return result
    return _error_support([error] if error else [])


def _resolve_provider(value: str) -> Optional[str]:
    provider = (value or "").strip().lower()
    if provider in {"openai", "ollama"}:
        return provider
    return None


def _generate_with_openai(
    text: str, mode: str, context: str, config
) -> Tuple[Optional[SupportResult], Optional[str]]:
    try:
        from openai import OpenAI
    except Exception:
        return None, "OpenAI SDKの読み込みに失敗しました。"

    api_key = config.openai.api_key
    if not api_key:
        return None, "OpenAI APIキーが未設定です。"

    client = OpenAI(api_key=api_key)
    instruction = instruction_for(mode)
    messages = _build_messages(instruction, context, text)
    try:
        response = client.responses.create(
            model=config.openai.model or "gpt-4o-mini",
            input=messages,
        )
    except Exception as exc:
        return None, f"OpenAI APIエラー: {exc}"

    content = response.output_text.strip() if hasattr(response, "output_text") else ""
    if not content:
        return None, "OpenAI APIの応答が空でした。"
    return SupportResult(content=content, model="openai"), None


def _generate_with_ollama(
    text: str, mode: str, context: str, config
) -> Tuple[Optional[SupportResult], Optional[str]]:
    import json
    import urllib.error
    import urllib.request

    model = config.ollama.model
    if not model:
        return None, "Ollamaのモデルが未設定です。"
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
        with urllib.request.urlopen(req, timeout=100) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        return None, f"Ollama APIがHTTPエラーを返しました (status: {exc.code})。"
    except urllib.error.URLError as exc:
        return None, f"Ollama APIに接続できませんでした ({exc.reason})。"
    except TimeoutError:
        return None, "Ollama APIがタイムアウトしました。"

    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None, "Ollama APIの応答が不正です。"

    content = ""
    if isinstance(parsed, dict):
        content = (
            parsed.get("message", {}).get("content")
            or parsed.get("response", "")
            or ""
        )
    if not content:
        return None, "Ollama APIの応答が空でした。"
    return SupportResult(content=content.strip(), model="ollama"), None


def _build_messages(instruction: str, context: str, text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": _build_user_prompt(instruction, context, text)},
    ]


def _build_user_prompt(instruction: str, context: str, text: str) -> str:
    return f"{instruction}\n\n[コンテキスト]\n{context}\n\n[メッセージ]\n{text}"


def _error_support(errors: list[str]) -> SupportResult:
    if errors:
        detail = "\n".join(f"- {error}" for error in errors)
        message = f"AIサポートの生成に失敗しました。\n{detail}"
    else:
        message = "AIサポートの生成に失敗しました。"
    return SupportResult(content=message, model="error", error=message)
