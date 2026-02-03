from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from ai_support import generate_support
from config import get_config
from slack_service import SlackMessage, SlackService


class SlackAgentApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Slack Agent")
        self.root.geometry("980x640")

        self.config = get_config()
        self.slack_service = self._build_slack_service()
        self.messages: list[SlackMessage] = []
        self.message_ranges: list[tuple[str, str]] = []
        self.selected_index: int | None = None
        self.query_var = tk.StringVar(value=self.config.slack.search_query)
        self.support_mode = tk.StringVar(value="reply")
        self.status_text = tk.StringVar(value="準備完了")

        self._build_ui()
        self.refresh_messages()

    def _build_slack_service(self) -> SlackService:
        user_token = self.config.slack.user_token or self.config.slack.token
        if not user_token:
            # 起動は可能だが Slack 取得は失敗するため警告する
            messagebox.showwarning(
                "Slackトークンが未設定です",
                "config/config.yml に Slack トークンを設定してください。",
            )
            user_token = "MISSING"
        return SlackService(user_token=user_token)

    def _build_ui(self) -> None:
        self.root.configure(padx=12, pady=12)

        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(header, text="検索クエリ").pack(side=tk.LEFT)
        ttk.Entry(header, textvariable=self.query_var, width=40).pack(side=tk.LEFT, padx=6)
        ttk.Button(header, text="検索", command=self.refresh_messages).pack(side=tk.LEFT)
        ttk.Button(header, text="更新", command=self.refresh_messages).pack(side=tk.RIGHT)

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        self.list_text = tk.Text(body, height=20, wrap=tk.WORD, state=tk.DISABLED, width=45)
        self.list_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        self.list_text.tag_configure("selected", background="#dceeff")
        self.list_text.bind("<Button-1>", self.on_select_message)

        detail_frame = ttk.Frame(body)
        detail_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        self.detail_text = tk.Text(detail_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.detail_text.pack(fill=tk.BOTH, expand=True)

        support_frame = ttk.LabelFrame(detail_frame, text="AIサポート")
        support_frame.pack(fill=tk.X, pady=(12, 0))

        modes = [
            ("返信を考える", "reply"),
            ("連絡を要約する", "summary"),
            ("TODOを具体化", "todo"),
        ]
        for label, value in modes:
            ttk.Radiobutton(
                support_frame,
                text=label,
                value=value,
                variable=self.support_mode,
            ).pack(side=tk.LEFT, padx=4, pady=4)

        ttk.Button(
            support_frame, text="AIサポートを生成", command=self.on_generate_support
        ).pack(side=tk.RIGHT, padx=6)

        self.output_text = tk.Text(detail_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        status_bar = ttk.Label(self.root, textvariable=self.status_text, anchor="w")
        status_bar.pack(fill=tk.X, pady=(8, 0))

    def refresh_messages(self) -> None:
        if not self._slack_ready():
            return
        self.status_text.set("Slackから取得中...")
        self.root.update_idletasks()
        try:
            # API から最新 10 件を取得
            query = self.query_var.get().strip()
            self.messages = self.slack_service.search_messages(query=query, limit=10)
        except Exception as exc:
            messagebox.showerror("取得に失敗しました", str(exc))
            self.status_text.set("取得に失敗しました")
            return
        self._render_message_list()
        self.status_text.set(f"{len(self.messages)}件の検索結果を表示中")

    def _render_message_list(self) -> None:
        self.list_text.configure(state=tk.NORMAL)
        self.list_text.delete("1.0", tk.END)
        self.message_ranges = []
        for msg in self.messages:
            start = self.list_text.index(tk.END)
            self.list_text.insert(tk.END, self._format_list_item(msg))
            end = self.list_text.index(tk.END)
            self.message_ranges.append((start, end))
            self.list_text.insert(tk.END, "\n")
        self.list_text.configure(state=tk.DISABLED)
        self._clear_detail()

    def _clear_detail(self) -> None:
        self.selected_index = None
        self._set_text(self.detail_text, "")
        self._set_text(self.output_text, "")

    def on_select_message(self, event: tk.Event) -> None:
        index = self._selected_index(event)
        if index is None:
            return
        self.selected_index = index
        self._highlight_message(index)
        msg = self.messages[index]
        self._set_text(self.detail_text, self._build_detail_text(msg))
        self._set_text(self.output_text, "")

    def on_generate_support(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("選択してください", "対象メッセージを選択してください。")
            return
        msg = self.messages[index]
        mode = self.support_mode.get()
        context = f"{msg.user_name} / {msg.channel_name}"
        self.status_text.set("スレッドを取得中...")
        self.root.update_idletasks()
        thread_messages = self._fetch_thread_messages(msg)
        if not thread_messages:
            self.status_text.set("スレッド取得に失敗しました")
            return
        thread_text = self._format_thread_messages(thread_messages)
        self.status_text.set("AIサポートを生成中...")
        self.root.update_idletasks()
        result = generate_support(thread_text, mode=mode, context=context)
        output = result.content
        if result.model == "fallback":
            # API が使えない場合は簡易生成で補う
            output = f"{output}\n\n(ローカル簡易生成)"
        self._set_text(self.output_text, output)
        self.status_text.set("AIサポートを表示しました")

    def _selected_index(self, event: tk.Event | None = None) -> int | None:
        if event is None:
            return self.selected_index
        if not self.message_ranges:
            return None
        click_index = self.list_text.index(f"@{event.x},{event.y}")
        for idx, (start, end) in enumerate(self.message_ranges):
            if self.list_text.compare(click_index, ">=", start) and self.list_text.compare(
                click_index, "<", end
            ):
                return idx
        return None

    def _highlight_message(self, index: int) -> None:
        if index < 0 or index >= len(self.message_ranges):
            return
        start, end = self.message_ranges[index]
        self.list_text.configure(state=tk.NORMAL)
        self.list_text.tag_remove("selected", "1.0", tk.END)
        self.list_text.tag_add("selected", start, end)
        self.list_text.configure(state=tk.DISABLED)

    def _format_ts(self, ts: str) -> str:
        try:
            dt = datetime.utcfromtimestamp(float(ts))
        except Exception:
            return ts
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _format_list_item(self, msg: SlackMessage) -> str:
        preview = msg.text.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:120] + "..."
        return (
            f"from: {msg.user_name}\n"
            f"channel: {msg.channel_name}\n"
            f"message: {preview}"
        )

    def _build_detail_text(self, msg: SlackMessage) -> str:
        detail = (
            f"送信者: {msg.user_name}\n"
            f"チャンネル: {msg.channel_name}\n"
            f"日時: {self._format_ts(msg.ts)} (UTC)\n"
            f"{msg.text}"
        )
        if msg.permalink:
            detail += f"\n\nPermalink: {msg.permalink}"
        return detail

    def _fetch_thread_messages(self, msg: SlackMessage) -> list[SlackMessage]:
        thread_ts = msg.thread_ts or msg.ts
        try:
            return self.slack_service.fetch_thread_messages(
                msg.channel_id, thread_ts, msg.channel_name
            )
        except Exception as exc:
            messagebox.showerror("スレッド取得に失敗しました", str(exc))
            return []

    def _format_thread_messages(self, messages: list[SlackMessage]) -> str:
        lines = []
        for message in messages:
            timestamp = self._format_ts(message.ts)
            lines.append(f"[{timestamp}] {message.user_name}: {message.text}")
        return "\n".join(lines)

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state=tk.DISABLED)

    def _slack_ready(self) -> bool:
        return bool(self.config.slack.user_token or self.config.slack.token)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if os.name == "nt":
        style.theme_use("vista")
    else:
        style.theme_use("clam")
    app = SlackAgentApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
