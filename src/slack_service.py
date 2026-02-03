from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


@dataclass
class SlackMessage:
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    text: str
    ts: str
    permalink: Optional[str] = None
    thread_ts: Optional[str] = None


class SlackService:
    def __init__(self, user_token: str) -> None:
        self.client = WebClient(token=user_token)

    def search_messages(self, query: str, limit: int = 10) -> list[SlackMessage]:
        if not query.strip():
            raise ValueError("検索クエリが空です。")
        try:
            resp = self.client.search_messages(query=query, sort="timestamp", count=limit)
        except SlackApiError as exc:
            raise RuntimeError(f"Slack検索に失敗しました: {exc}") from exc

        matches = resp.get("messages", {}).get("matches", [])
        results: list[SlackMessage] = []
        for match in matches:
            message = self._to_message(match)
            if message:
                results.append(message)
        return results

    def _to_message(self, match: dict) -> Optional[SlackMessage]:
        channel = match.get("channel", {})
        channel_id = channel.get("id") or ""
        if not channel_id:
            return None
        user_id = match.get("user") or ""
        text = (match.get("text") or "").strip()
        if not user_id or not text:
            return None
        channel_name = self._channel_name(channel_id, channel)
        user_name = self._resolve_match_user_name(match, user_id)
        return SlackMessage(
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            user_name=user_name,
            text=text,
            ts=match.get("ts") or match.get("timestamp") or "0",
            permalink=match.get("permalink"),
            thread_ts=match.get("thread_ts") or match.get("ts") or match.get("timestamp"),
        )

    def _channel_name(self, channel_id: str, channel: dict) -> str:
        return channel.get("name") or channel_id

    def fetch_thread_messages(
        self, channel_id: str, thread_ts: str, channel_name: str
    ) -> list[SlackMessage]:
        messages: list[SlackMessage] = []
        cursor: Optional[str] = None
        while True:
            try:
                resp = self.client.conversations_replies(
                    channel=channel_id, ts=thread_ts, cursor=cursor, limit=200
                )
            except SlackApiError as exc:
                raise RuntimeError(f"スレッド取得に失敗しました: {exc}") from exc
            for message in resp.get("messages", []) or []:
                converted = self._to_thread_message(message, channel_id, channel_name)
                if converted:
                    messages.append(converted)
            cursor = (resp.get("response_metadata", {}) or {}).get("next_cursor")
            if not cursor:
                break
        return messages

    def _to_thread_message(
        self, message: dict, channel_id: str, channel_name: str
    ) -> Optional[SlackMessage]:
        text = (message.get("text") or "").strip()
        if not text:
            return None
        user_id = message.get("user") or message.get("bot_id") or "unknown"
        user_name = self._resolve_thread_user_name(message, user_id)
        ts = message.get("ts") or "0"
        return SlackMessage(
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            user_name=user_name,
            text=text,
            ts=ts,
            thread_ts=message.get("thread_ts") or ts,
        )

    def _resolve_match_user_name(self, match: dict, user_id: str) -> str:
        return match.get("username") or user_id

    def _resolve_thread_user_name(self, message: dict, user_id: str) -> str:
        return (
            message.get("username")
            or (message.get("bot_profile", {}) or {}).get("name")
            or user_id
        )
