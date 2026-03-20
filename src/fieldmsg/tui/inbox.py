"""TUI inbox view — 3-column layout: sidebar | conversations | chat."""

from __future__ import annotations

import time
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Static, ListView, ListItem, Label, Input

from fieldmsg.core import Core


STATUS_ICONS = {
    "pending": "...",
    "sent": "->",
    "delivered": "ok",
    "failed": "!!",
}


class ConversationItem(ListItem):
    """A single conversation in the inbox."""

    def __init__(self, peer_hash: str, display_name: str, last_message: str, unread: int):
        super().__init__()
        self.peer_hash = peer_hash
        self.display_name = display_name
        self.last_message = last_message
        self.unread = unread

    def compose(self) -> ComposeResult:
        unread_badge = f" ({self.unread})" if self.unread > 0 else ""
        name = self.display_name or self.peer_hash[:12]
        yield Label(f"[b]{name}[/b]{unread_badge}")
        preview = self.last_message[:30].replace("\n", " ")
        yield Label(f"  {preview}", classes="preview")


class MessageBubble(Static):
    """A single message in the chat pane."""

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


class ConversationList(Vertical):
    """Left pane: list of conversations."""

    DEFAULT_CSS = """
    ConversationList {
        width: 32;
        height: 100%;
        border-right: solid $accent;
    }
    ConversationList .title {
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    ConversationList .preview {
        color: $text-muted;
    }
    ConversationList .empty {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Conversations", classes="title")
        yield ListView(id="convo-list")


class ChatPane(Vertical):
    """Right pane: message thread + compose bar for selected conversation."""

    DEFAULT_CSS = """
    ChatPane {
        width: 1fr;
        height: 100%;
    }
    ChatPane .chat-title {
        text-style: bold;
        padding: 1;
        color: $accent;
        height: 3;
    }
    ChatPane #chat-scroll {
        height: 1fr;
    }
    ChatPane #chat-compose {
        dock: bottom;
        margin: 0 1;
    }
    ChatPane .empty-chat {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Select a conversation", classes="chat-title", id="chat-title")
        yield ScrollableContainer(id="chat-scroll")
        yield Input(placeholder="Type a message...", id="chat-compose", disabled=True)


class InboxView(Horizontal):
    """3-column inbox: sidebar (in app) | conversations | chat."""

    DEFAULT_CSS = """
    InboxView {
        height: 100%;
    }
    """

    BINDINGS = [
        ("d", "delete_conversation", "Delete"),
    ]

    def __init__(self, core: Core):
        super().__init__()
        self.core = core
        self._active_peer: str | None = None

    def compose(self) -> ComposeResult:
        yield ConversationList()
        yield ChatPane()

    def on_mount(self) -> None:
        self._load_conversations()

        # Wire up live message updates
        self._prev_on_message = self.core.on_message
        self._prev_on_status = self.core.on_delivery_status
        self.core.on_message = self._on_new_message
        self.core.on_delivery_status = self._on_status_update

    def on_unmount(self) -> None:
        if hasattr(self, "_prev_on_message"):
            self.core.on_message = self._prev_on_message
        if hasattr(self, "_prev_on_status"):
            self.core.on_delivery_status = self._prev_on_status

    def _load_conversations(self) -> None:
        lv = self.query_one("#convo-list", ListView)
        lv.clear()
        conversations = self.core.store.get_conversations()
        if not conversations:
            lv.append(ListItem(Label("No conversations yet.\nCtrl+N to start one."), classes="empty"))
        else:
            for conv in conversations:
                lv.append(ConversationItem(
                    peer_hash=conv["peer_hash"],
                    display_name=conv["display_name"],
                    last_message=conv["last_message"],
                    unread=conv["unread"],
                ))
        lv.focus()

    # ── Conversation selection ──────────────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted conversation's messages in the chat pane."""
        if event.item and isinstance(event.item, ConversationItem):
            self._show_chat(event.item.peer_hash)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter pressed — focus the compose input."""
        if event.item and isinstance(event.item, ConversationItem):
            self._show_chat(event.item.peer_hash)
            compose = self.query_one("#chat-compose", Input)
            compose.disabled = False
            compose.focus()

    def _show_chat(self, peer_hash: str) -> None:
        self._active_peer = peer_hash
        self.core.store.mark_read(peer_hash)

        # Update title
        contact = self.core.store.get_contact(peer_hash)
        name = contact["nickname"] if contact else peer_hash[:16]
        self.query_one("#chat-title", Static).update(f"Chat with {name}")

        # Enable compose
        compose = self.query_one("#chat-compose", Input)
        compose.disabled = False

        # Load messages
        self._load_chat_messages()

        # Refresh conversation list to clear unread badges
        self._refresh_convo_list_item(peer_hash)

    def _load_chat_messages(self) -> None:
        if not self._active_peer:
            return
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.remove_children()
        messages = self.core.store.get_messages(self._active_peer)
        if not messages:
            scroll.mount(Static(
                "No messages yet. Type below to start the conversation.",
                classes="empty-chat",
            ))
        else:
            for msg in messages:
                scroll.mount(MessageBubble(
                    direction=msg["direction"],
                    content=msg["content"],
                    timestamp=msg["timestamp"],
                    status=msg["status"],
                ))
            scroll.scroll_end(animate=False)

    def _refresh_convo_list_item(self, peer_hash: str) -> None:
        """Update a single conversation's unread badge without full reload."""
        lv = self.query_one("#convo-list", ListView)
        for item in lv.children:
            if isinstance(item, ConversationItem) and item.peer_hash == peer_hash:
                if item.unread > 0:
                    item.unread = 0
                    # Re-render by updating the label
                    labels = list(item.query(Label))
                    if labels:
                        name = item.display_name or item.peer_hash[:12]
                        labels[0].update(f"[b]{name}[/b]")
                break

    # ── Compose ─────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or not self._active_peer:
            return
        event.input.value = ""

        # Clear empty placeholder
        try:
            empty = self.query_one(".empty-chat")
            empty.remove()
        except Exception:
            pass

        msg_id = self.core.send_message(self._active_peer, text)
        if msg_id:
            self._append_chat_message("out", text, time.time(), "pending")
        else:
            self._append_chat_message("out", text, time.time(), "failed")
            self.app.notify("Message failed to send", severity="error")

        # Update conversation list preview
        self._update_convo_preview(self._active_peer, text)

    def _append_chat_message(self, direction, content, timestamp, status):
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.mount(MessageBubble(
            direction=direction,
            content=content,
            timestamp=timestamp,
            status=status,
        ))
        scroll.scroll_end(animate=False)

    def _update_convo_preview(self, peer_hash: str, message: str) -> None:
        lv = self.query_one("#convo-list", ListView)
        for item in lv.children:
            if isinstance(item, ConversationItem) and item.peer_hash == peer_hash:
                labels = list(item.query(Label))
                if len(labels) >= 2:
                    preview = message[:30].replace("\n", " ")
                    labels[1].update(f"  {preview}")
                break

    # ── Live callbacks from LXMF ────────────────────────────────────

    def _on_new_message(self, msg_id, source_hash, content, timestamp):
        self.app.call_from_thread(
            self._handle_incoming, msg_id, source_hash, content, timestamp
        )
        if self._prev_on_message:
            self._prev_on_message(msg_id, source_hash, content, timestamp)

    def _handle_incoming(self, msg_id, source_hash, content, timestamp):
        # If this is the active chat, append inline
        if source_hash == self._active_peer:
            self._append_chat_message("in", content, timestamp, "delivered")
            self.core.store.mark_read(source_hash)
        # Refresh conversation list
        self._load_conversations()
        # Re-select the active peer if we had one
        if self._active_peer:
            self._show_chat(self._active_peer)
        self.app.bell()

    def _on_status_update(self, msg_id, status):
        self.app.call_from_thread(self._handle_status, msg_id, status)
        if self._prev_on_status:
            self._prev_on_status(msg_id, status)

    def _handle_status(self, msg_id, status):
        if self._active_peer:
            try:
                self._load_chat_messages()
            except Exception:
                pass

    # ── Delete ──────────────────────────────────────────────────────

    def action_delete_conversation(self) -> None:
        lv = self.query_one("#convo-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, ConversationItem):
            item = lv.highlighted_child
            name = item.display_name or item.peer_hash[:12]
            self.core.store.delete_conversation(item.peer_hash)
            if self._active_peer == item.peer_hash:
                self._active_peer = None
                self.query_one("#chat-title", Static).update("Select a conversation")
                self.query_one("#chat-scroll", ScrollableContainer).remove_children()
                self.query_one("#chat-compose", Input).disabled = True
            self.notify(f"Deleted conversation with {name}")
            self._load_conversations()
