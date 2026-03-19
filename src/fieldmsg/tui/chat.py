"""Stub chat view (placeholder for Task 9)."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ChatView(Vertical):
    """Single-conversation message view."""

    def __init__(self, core, peer_hash: str):
        super().__init__()
        self.core = core
        self.peer_hash = peer_hash

    def compose(self) -> ComposeResult:
        yield Static(f"Chat with {self.peer_hash[:16]}...")
