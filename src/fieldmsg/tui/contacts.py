"""Contacts management view for the fieldmsg TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label, Input
from textual.screen import ModalScreen

from fieldmsg.core import Core
from fieldmsg.announces import _relative_time


class ContactItem(ListItem):
    """A list item representing a single contact."""

    def __init__(self, hash: str, nickname: str, display_name: str | None, last_seen: float | None):
        super().__init__()
        self.peer_hash = hash
        self.nickname = nickname
        self.display_name = display_name
        self.last_seen = last_seen

    def compose(self) -> ComposeResult:
        seen = _relative_time(self.last_seen) if self.last_seen else "never"
        yield Label(f"[b]{self.nickname}[/b]  [{self.peer_hash[:12]}..] last seen: {seen}")


class EditContactScreen(ModalScreen):
    """Modal dialog for editing a contact's nickname."""

    DEFAULT_CSS = """
    EditContactScreen {
        align: center middle;
    }
    #edit-dialog {
        width: 50;
        height: 10;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, hash: str, current_nickname: str):
        super().__init__()
        self.peer_hash = hash
        self.current_nickname = current_nickname

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Static(f"Edit nickname for {self.peer_hash[:12]}...")
            yield Input(value=self.current_nickname, id="edit-nickname")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class ContactsView(Vertical):
    """Contact list view with edit, delete, and chat actions."""

    DEFAULT_CSS = """
    ContactsView {
        height: 100%;
    }
    ContactsView .title {
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    ContactsView .empty {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("enter", "start_chat", "Chat"),
        ("e", "edit_contact", "Edit"),
        ("d", "delete_contact", "Delete"),
    ]

    def __init__(self, core: Core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Contacts", classes="title")
        yield ListView(id="contact-list")

    def on_mount(self) -> None:
        self._refresh()
        lv = self.query_one("#contact-list", ListView)
        lv.focus()

    def _refresh(self) -> None:
        lv = self.query_one("#contact-list", ListView)
        lv.clear()
        contacts = self.core.store.get_contacts()
        if not contacts:
            lv.append(ListItem(Label("No contacts yet. Add peers from the Announces view.")))
        else:
            for c in contacts:
                lv.append(ContactItem(
                    hash=c["hash"],
                    nickname=c["nickname"],
                    display_name=c.get("display_name"),
                    last_seen=c.get("last_seen"),
                ))

    def action_start_chat(self) -> None:
        lv = self.query_one("#contact-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, ContactItem):
            self.app.show_conversation(lv.highlighted_child.peer_hash)

    def action_edit_contact(self) -> None:
        lv = self.query_one("#contact-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, ContactItem):
            item = lv.highlighted_child
            self.app.push_screen(
                EditContactScreen(item.peer_hash, item.nickname),
                self._on_edit_done,
            )

    def _on_edit_done(self, new_nickname: str | None) -> None:
        if new_nickname:
            lv = self.query_one("#contact-list", ListView)
            if lv.highlighted_child and isinstance(lv.highlighted_child, ContactItem):
                item = lv.highlighted_child
                self.core.store.save_contact(item.peer_hash, new_nickname)
                self._refresh()

    def action_delete_contact(self) -> None:
        lv = self.query_one("#contact-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, ContactItem):
            item = lv.highlighted_child
            self.core.store.delete_contact(item.peer_hash)
            self._refresh()
            self.notify(f"Deleted {item.nickname}")
