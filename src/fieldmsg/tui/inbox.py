"""TUI inbox view — conversation list sorted by most recent message."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label


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
        preview = self.last_message[:40].replace("\n", " ")
        yield Label(f"  {preview}", classes="preview")


class InboxView(Vertical):
    """Conversation list sorted by most recent."""

    BINDINGS = [
        ("d", "delete_conversation", "Delete"),
    ]

    DEFAULT_CSS = """
    InboxView {
        height: 100%;
    }
    InboxView .title {
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    InboxView .preview {
        color: $text-muted;
    }
    InboxView .empty {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Inbox", classes="title")
        if not self.core or not self.core.store:
            yield Static("Initializing...", classes="empty")
            return
        conversations = self.core.store.get_conversations()
        if not conversations:
            yield Static("No conversations yet.\nPress Ctrl+N to start one.", classes="empty")
        else:
            yield ListView(id="inbox-list")

    def on_mount(self) -> None:
        if not self.core or not self.core.store:
            return
        try:
            lv = self.query_one("#inbox-list", ListView)
        except Exception:
            return

        conversations = self.core.store.get_conversations()
        for conv in conversations:
            lv.append(ConversationItem(
                peer_hash=conv["peer_hash"],
                display_name=conv["display_name"],
                last_message=conv["last_message"],
                unread=conv["unread"],
            ))
        if conversations:
            lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, ConversationItem):
            self.app.show_conversation(item.peer_hash)

    def action_delete_conversation(self) -> None:
        try:
            lv = self.query_one("#inbox-list", ListView)
        except Exception:
            return
        if lv.highlighted_child and isinstance(lv.highlighted_child, ConversationItem):
            item = lv.highlighted_child
            name = item.display_name or item.peer_hash[:12]
            self.core.store.delete_conversation(item.peer_hash)
            self.notify(f"Deleted conversation with {name}")
            self.app.action_show_inbox()
