"""Textual TUI application shell for fieldmsg."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Footer, Header, Input, Static

from fieldmsg.config import Config
from fieldmsg.core import Core

BLACKOUT_THEME = Theme(
    name="blackout",
    primary="#ffffff",
    secondary="#888888",
    accent="#00ff00",
    warning="#ffff00",
    error="#ff0000",
    success="#00ff00",
    background="#000000",
    surface="#000000",
    panel="#000000",
    boost="#111111",
    dark=True,
)


class NewMessageScreen(ModalScreen):
    """Prompt for destination hash or contact nickname."""

    DEFAULT_CSS = """
    NewMessageScreen {
        align: center middle;
    }
    #new-msg-dialog {
        width: 60;
        height: 8;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="new-msg-dialog"):
            yield Static("Enter contact nickname or destination hash:")
            yield Input(placeholder="nickname or 32-char hex hash...", id="dest-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class SearchScreen(ModalScreen):
    """Search conversations."""

    DEFAULT_CSS = """
    SearchScreen {
        align: center middle;
    }
    #search-dialog {
        width: 60;
        height: 8;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Static("Search conversations:")
            yield Input(placeholder="search...", id="search-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class NavItem(Static):
    """A navigation item in the sidebar."""

    DEFAULT_CSS = """
    NavItem {
        height: 1;
        padding: 0 1;
    }
    NavItem:hover {
        background: $boost;
    }
    NavItem.-highlighted {
        background: $boost;
        text-style: bold;
    }
    """

    def __init__(self, label: str, view: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self.view = view

    def on_click(self) -> None:
        sidebar = self.parent
        if isinstance(sidebar, Sidebar):
            sidebar._select_view(self.view)


class Sidebar(Vertical, can_focus=True):
    """Navigation sidebar — Tab to focus, arrows to move, Enter to select."""

    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("enter", "activate", "Select"),
    ]

    NAV_VIEWS = ["inbox", "announces", "contacts"]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cursor = 0  # index into NAV_VIEWS

    def compose(self) -> ComposeResult:
        yield Static("[b]fieldmsg[/b]", id="sidebar-title")
        yield Static("")
        yield NavItem("[b]> Inbox[/b]", "inbox", id="nav-inbox")
        yield NavItem("  Announces", "announces", id="nav-announces")
        yield NavItem("  Contacts", "contacts", id="nav-contacts")

    def on_focus(self) -> None:
        self._update_highlight()

    def on_blur(self) -> None:
        # Remove highlight when sidebar loses focus
        for item in self.query(NavItem):
            item.remove_class("-highlighted")

    def action_move_up(self) -> None:
        self._cursor = max(0, self._cursor - 1)
        self._update_highlight()

    def action_move_down(self) -> None:
        self._cursor = min(len(self.NAV_VIEWS) - 1, self._cursor + 1)
        self._update_highlight()

    def action_activate(self) -> None:
        self._select_view(self.NAV_VIEWS[self._cursor])

    def _select_view(self, view: str) -> None:
        if view in self.NAV_VIEWS:
            self._cursor = self.NAV_VIEWS.index(view)
        if view == "inbox":
            self.app.action_show_inbox()
        elif view == "announces":
            self.app.action_show_announces()
        elif view == "contacts":
            self.app.action_show_contacts()

    def _update_highlight(self) -> None:
        items = list(self.query(NavItem))
        for i, item in enumerate(items):
            if i == self._cursor:
                item.add_class("-highlighted")
            else:
                item.remove_class("-highlighted")


class MainPanel(Vertical):
    """Main content area that hosts the active view."""

    pass


class FieldMsgApp(App):
    """The fieldmsg TUI application."""

    TITLE = "fieldmsg"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+i", "show_inbox", "Inbox", show=True),
        Binding("ctrl+a", "show_announces", "Announces", show=True),
        Binding("ctrl+o", "show_contacts", "Contacts", show=True),
        Binding("ctrl+n", "new_message", "New Msg", show=True),
        Binding("slash", "search", "Search", show=True),
        Binding("ctrl+r", "announce", "Announce", show=True),
    ]

    current_view: reactive[str] = reactive("inbox")

    def __init__(self, config: Config, core: Core | None = None):
        super().__init__()
        self.config = config
        self.core = core
        self.register_theme(BLACKOUT_THEME)
        self.theme = "blackout"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Sidebar(id="sidebar"),
            MainPanel(id="main-panel"),
        )
        yield Footer()

    def on_mount(self) -> None:
        if self.core is None:
            # Fallback: create core here (won't work if Reticulum needs signals)
            self.core = Core(self.config)
            self.core.setup()

        self.core.on_message = self._on_message_received
        self.core.on_announce = self._on_announce_received
        self.core.on_delivery_status = self._on_delivery_status
        self._on_core_ready()

    def _on_core_ready(self) -> None:
        """Called on the main thread once Core.setup() finishes."""
        self.sub_title = self.core.get_own_hash()[:16]
        self._show_inbox()

        # Periodic announce
        if self.config.announce_interval > 0:
            self.set_interval(self.config.announce_interval, self._periodic_announce)

        # Periodic propagation sync
        if self.config.propagation_node and self.config.sync_interval > 0:
            self.set_interval(self.config.sync_interval, self._periodic_sync)

    def _periodic_announce(self) -> None:
        self.core.announce()

    def _periodic_sync(self) -> None:
        self.core.sync_propagation_node()

    # ── LXMF callback bridges (called from Reticulum threads) ──────

    def _on_message_received(self, msg_id, source_hash, content, timestamp):
        self.call_from_thread(
            self._handle_incoming, msg_id, source_hash, content, timestamp
        )

    def _handle_incoming(self, msg_id, source_hash, content, timestamp):
        if self.current_view == "inbox":
            self._show_inbox()
        self.bell()

    def _on_announce_received(self, hex_hash, display_name, hops):
        self.call_from_thread(self._handle_announce, hex_hash, display_name, hops)

    def _handle_announce(self, hex_hash, display_name, hops):
        if self.current_view == "announces":
            self._show_announces()

    def _on_delivery_status(self, msg_id, status):
        self.call_from_thread(self._handle_status, msg_id, status)

    def _handle_status(self, msg_id, status):
        pass  # Chat view handles its own status updates when active

    # ── View switching ─────────────────────────────────────────────

    def action_show_inbox(self) -> None:
        self.current_view = "inbox"
        self._show_inbox()

    def action_show_announces(self) -> None:
        self.current_view = "announces"
        self._show_announces()

    def action_show_contacts(self) -> None:
        self.current_view = "contacts"
        self._show_contacts()

    def action_announce(self) -> None:
        if self.core:
            self.core.announce()
            self.notify("Announced on network")

    def action_new_message(self) -> None:
        self.push_screen(NewMessageScreen(), self._on_new_message_dest)

    def _on_new_message_dest(self, dest: str | None) -> None:
        if not dest:
            return
        # Try contact lookup first
        contact = self.core.store.find_contact_by_nickname(dest)
        if contact:
            self.show_conversation(contact["hash"])
        elif len(dest) == 32 and all(c in "0123456789abcdef" for c in dest.lower()):
            self.show_conversation(dest.lower())
        else:
            self.notify(f"Unknown destination: {dest}", severity="error")

    def action_search(self) -> None:
        self.push_screen(SearchScreen(), self._on_search)

    def _on_search(self, query: str | None) -> None:
        if not query:
            return
        # Search contacts by nickname
        contact = self.core.store.find_contact_by_nickname(query)
        if contact:
            self.show_conversation(contact["hash"])
            return
        # Search conversations for content match
        convos = self.core.store.get_conversations()
        for c in convos:
            if query.lower() in c["display_name"].lower() or query.lower() in c["last_message"].lower():
                self.show_conversation(c["peer_hash"])
                return
        self.notify(f"No results for: {query}", severity="warning")

    def _show_inbox(self) -> None:
        from fieldmsg.tui.inbox import InboxView

        panel = self.query_one("#main-panel", MainPanel)
        panel.remove_children()
        panel.mount(InboxView(self.core))
        self._update_nav("inbox")

    def _show_announces(self) -> None:
        from fieldmsg.tui.announces import AnnouncesView

        panel = self.query_one("#main-panel", MainPanel)
        panel.remove_children()
        panel.mount(AnnouncesView(self.core))
        self._update_nav("announces")

    def _show_contacts(self) -> None:
        from fieldmsg.tui.contacts import ContactsView

        panel = self.query_one("#main-panel", MainPanel)
        panel.remove_children()
        panel.mount(ContactsView(self.core))
        self._update_nav("contacts")

    def show_conversation(self, peer_hash: str) -> None:
        """Switch to inbox and open a specific conversation with compose focused."""
        from fieldmsg.tui.inbox import InboxView

        self.current_view = "inbox"
        panel = self.query_one("#main-panel", MainPanel)
        panel.remove_children()
        inbox = InboxView(self.core)
        panel.mount(inbox)
        self._update_nav("inbox")

        def _open_and_focus():
            inbox._show_chat(peer_hash)
            try:
                compose = inbox.query_one("#chat-compose", Input)
                compose.disabled = False
                compose.focus()
            except Exception:
                pass

        self.call_later(_open_and_focus)

    def _update_nav(self, active: str) -> None:
        """Highlight the active navigation item in the sidebar."""
        labels = {
            "inbox": "nav-inbox",
            "announces": "nav-announces",
            "contacts": "nav-contacts",
        }
        for key, widget_id in labels.items():
            widget = self.query_one(f"#{widget_id}", NavItem)
            name = key.capitalize()
            if key == active:
                widget.update(f"[b]> {name}[/b]")
            else:
                widget.update(f"  {name}")

    def action_quit(self) -> None:
        self.exit()
