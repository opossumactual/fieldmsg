"""Textual TUI application shell for fieldmsg."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static
from textual import work

from fieldmsg.config import Config
from fieldmsg.core import Core


class Sidebar(Vertical):
    """Navigation sidebar with view links."""

    def compose(self) -> ComposeResult:
        yield Static("[b]fieldmsg[/b]", id="sidebar-title")
        yield Static("")
        yield Static("[b]> Inbox[/b]", id="nav-inbox", classes="nav-item nav-active")
        yield Static("  Announces", id="nav-announces", classes="nav-item")
        yield Static("  Contacts", id="nav-contacts", classes="nav-item")


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
    ]

    current_view: reactive[str] = reactive("inbox")

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.core: Core | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Sidebar(id="sidebar"),
            MainPanel(id="main-panel"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.core = Core(self.config)
        self.core.on_message = self._on_message_received
        self.core.on_announce = self._on_announce_received
        self.core.on_delivery_status = self._on_delivery_status
        self._setup_core()

    @work(thread=True)
    def _setup_core(self) -> None:
        """Initialise the Core on a background thread."""
        self.core.setup()
        self.call_from_thread(self._on_core_ready)

    def _on_core_ready(self) -> None:
        """Called on the main thread once Core.setup() finishes."""
        self.sub_title = self.core.get_own_hash()[:16]
        self._show_inbox()

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
        pass  # will be enhanced when chat view exists

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

    def action_new_message(self) -> None:
        pass  # Task 12

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
        """Switch to the chat view for a specific peer."""
        from fieldmsg.tui.chat import ChatView

        panel = self.query_one("#main-panel", MainPanel)
        panel.remove_children()
        panel.mount(ChatView(self.core, peer_hash))
        self.current_view = "chat"

    def _update_nav(self, active: str) -> None:
        """Highlight the active navigation item in the sidebar."""
        labels = {
            "inbox": "nav-inbox",
            "announces": "nav-announces",
            "contacts": "nav-contacts",
        }
        for key, widget_id in labels.items():
            widget = self.query_one(f"#{widget_id}", Static)
            name = key.capitalize()
            if key == active:
                widget.update(f"[b]> {name}[/b]")
            else:
                widget.update(f"  {name}")

    def action_quit(self) -> None:
        if self.core:
            self.core.shutdown()
        self.exit()
