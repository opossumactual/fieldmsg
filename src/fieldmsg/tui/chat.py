"""Chat view: message thread with compose bar."""

from __future__ import annotations

import time
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static, Input

from fieldmsg.core import Core


STATUS_ICONS = {
    "pending": "...",
    "sent": "->",
    "delivered": "ok",
    "failed": "!!",
}


class MessageBubble(Static):
    """A single message in the chat."""

    DEFAULT_CSS = """
    MessageBubble {
        height: auto;
        padding: 0 1;
    }
    MessageBubble.incoming {
        color: $text;
    }
    MessageBubble.outgoing {
        color: $accent;
    }
    """

    def __init__(self, direction: str, content: str, timestamp: float, status: str):
        super().__init__()
        self.direction = direction
        self.content = content
        self.timestamp = timestamp
        self.status = status
        self.add_class("incoming" if direction == "in" else "outgoing")

    def render(self) -> str:
        ts = datetime.fromtimestamp(self.timestamp).strftime("%H:%M")
        if self.direction == "out":
            icon = STATUS_ICONS.get(self.status, "?")
            return f"[{ts}] You: {self.content}  [{icon}]"
        else:
            return f"[{ts}] > {self.content}"


class ChatView(Vertical):
    """Message thread with compose bar."""

    DEFAULT_CSS = """
    ChatView {
        height: 100%;
    }
    ChatView .chat-title {
        text-style: bold;
        padding: 1;
        color: $accent;
        dock: top;
        height: 3;
    }
    ChatView #message-scroll {
        height: 1fr;
    }
    ChatView #compose-input {
        dock: bottom;
        margin: 0 1;
    }
    ChatView .empty-chat {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, core: Core, peer_hash: str):
        super().__init__()
        self.core = core
        self.peer_hash = peer_hash

    def compose(self) -> ComposeResult:
        contact = self.core.store.get_contact(self.peer_hash)
        name = contact["nickname"] if contact else self.peer_hash[:16]
        yield Static(f"Chat with {name}", classes="chat-title")
        yield ScrollableContainer(id="message-scroll")
        yield Input(placeholder="Type a message...", id="compose-input")

    def on_mount(self) -> None:
        self.core.store.mark_read(self.peer_hash)
        self._load_messages()
        self.query_one("#compose-input", Input).focus()

        # Wire up live message updates for this specific peer
        self._prev_on_message = self.core.on_message
        self._prev_on_status = self.core.on_delivery_status
        self.core.on_message = self._on_new_message
        self.core.on_delivery_status = self._on_status_update

    def on_unmount(self) -> None:
        # Restore previous callbacks
        if hasattr(self, "_prev_on_message"):
            self.core.on_message = self._prev_on_message
        if hasattr(self, "_prev_on_status"):
            self.core.on_delivery_status = self._prev_on_status

    def _load_messages(self) -> None:
        scroll = self.query_one("#message-scroll", ScrollableContainer)
        messages = self.core.store.get_messages(self.peer_hash)
        if not messages:
            scroll.mount(Static(
                "No messages yet. Type below to start the conversation.",
                classes="empty-chat",
            ))
        else:
            for msg in messages:
                scroll.mount(
                    MessageBubble(
                        direction=msg["direction"],
                        content=msg["content"],
                        timestamp=msg["timestamp"],
                        status=msg["status"],
                    )
                )
            scroll.scroll_end(animate=False)

    def _on_new_message(self, msg_id, source_hash, content, timestamp):
        """Called from Reticulum's thread."""
        if source_hash == self.peer_hash:
            self.app.call_from_thread(
                self._append_message, "in", content, timestamp, "delivered"
            )
            self.app.call_from_thread(
                lambda: self.core.store.mark_read(self.peer_hash)
            )
        # Also forward to previous handler (for inbox refresh etc)
        if self._prev_on_message:
            self._prev_on_message(msg_id, source_hash, content, timestamp)

    def _on_status_update(self, msg_id, status):
        """Called from Reticulum's thread."""
        self.app.call_from_thread(self._refresh_messages)
        if self._prev_on_status:
            self._prev_on_status(msg_id, status)

    def _append_message(self, direction, content, timestamp, status):
        scroll = self.query_one("#message-scroll", ScrollableContainer)
        scroll.mount(
            MessageBubble(
                direction=direction,
                content=content,
                timestamp=timestamp,
                status=status,
            )
        )
        scroll.scroll_end(animate=False)

    def _refresh_messages(self):
        try:
            scroll = self.query_one("#message-scroll", ScrollableContainer)
        except Exception:
            return  # ChatView was unmounted, nothing to refresh
        scroll.remove_children()
        self._load_messages()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        # Clear the "no messages" placeholder if present
        try:
            empty = self.query_one(".empty-chat")
            empty.remove()
        except Exception:
            pass

        msg_id = self.core.send_message(self.peer_hash, text)
        if msg_id:
            self._append_message("out", text, time.time(), "pending")
        else:
            # Show the message as failed so the user sees what happened
            self._append_message("out", text, time.time(), "failed")
            self.app.notify("Message failed to send", severity="error")
