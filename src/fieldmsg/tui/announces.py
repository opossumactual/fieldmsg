"""Stub announces view (placeholder for Task 10)."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class AnnouncesView(Vertical):
    """Recent network announces view."""

    def __init__(self, core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Announces — loading...")
