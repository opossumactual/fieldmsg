"""Announces view – lists recent peer announcements from the Reticulum network."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label

from fieldmsg.core import Core
from fieldmsg.announces import format_announce


class AnnounceItem(ListItem):
    """A single announce entry in the list."""

    def __init__(self, hash: str, display_name: str | None, hops: int, timestamp: float, interface: str | None):
        super().__init__()
        self.peer_hash = hash
        self.display_name = display_name
        self.hops = hops
        self.timestamp = timestamp
        self.interface = interface

    def compose(self) -> ComposeResult:
        yield Label(format_announce(
            self.peer_hash, self.display_name, self.hops, self.timestamp, self.interface,
        ))


class AnnouncesView(Vertical):
    """Recent network announces view."""

    DEFAULT_CSS = """
    AnnouncesView {
        height: 100%;
    }
    AnnouncesView .title {
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    AnnouncesView .empty {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("a", "add_contact", "Add to Contacts"),
        ("enter", "start_chat", "Chat"),
    ]

    def __init__(self, core: Core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Announces", classes="title")
        yield ListView(id="announce-list")

    def on_mount(self) -> None:
        self._refresh()
        lv = self.query_one("#announce-list", ListView)
        lv.focus()

    def _refresh(self) -> None:
        lv = self.query_one("#announce-list", ListView)
        lv.clear()
        announces = self.core.store.get_announces(limit=50)
        if not announces:
            lv.append(ListItem(Label("No announces received yet.")))
        else:
            for ann in announces:
                lv.append(AnnounceItem(
                    hash=ann["hash"],
                    display_name=ann["display_name"],
                    hops=ann["hops"],
                    timestamp=ann["timestamp"],
                    interface=ann["interface"],
                ))

    def action_add_contact(self) -> None:
        lv = self.query_one("#announce-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, AnnounceItem):
            item = lv.highlighted_child
            name = item.display_name or item.peer_hash[:12]
            self.core.store.save_contact(item.peer_hash, name, item.display_name, item.timestamp)
            self.notify(f"Added {name} to contacts")

    def action_start_chat(self) -> None:
        lv = self.query_one("#announce-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, AnnounceItem):
            item = lv.highlighted_child
            if not self.core.store.get_contact(item.peer_hash):
                name = item.display_name or item.peer_hash[:12]
                self.core.store.save_contact(item.peer_hash, name, item.display_name, item.timestamp)
            self.app.show_conversation(item.peer_hash)
