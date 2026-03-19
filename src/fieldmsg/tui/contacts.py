"""Stub contacts view (placeholder for Task 11)."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ContactsView(Vertical):
    """Contact list view."""

    def __init__(self, core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Contacts — loading...")
