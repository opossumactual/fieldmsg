"""Stub inbox view (placeholder for Task 8)."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class InboxView(Vertical):
    """Conversation list view."""

    def __init__(self, core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Inbox — loading...")
