"""Interfaces view — shows active Reticulum interfaces with status and stats."""

from __future__ import annotations

import RNS
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static

from fieldmsg.core import Core


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.1f} GB"


def _format_speed(bps: float) -> str:
    if bps < 1000:
        return f"{bps:.0f} bps"
    if bps < 1_000_000:
        return f"{bps / 1000:.1f} kbps"
    return f"{bps / 1_000_000:.1f} Mbps"


def _mode_name(mode) -> str:
    names = {
        0x01: "Full",
        0x02: "Point-to-Point",
        0x03: "Access Point",
        0x04: "Roaming",
        0x05: "Boundary",
        0x06: "Gateway",
    }
    return names.get(mode, "Unknown")


class InterfaceRow(Static):
    """Single-line display for a Reticulum interface."""

    DEFAULT_CSS = """
    InterfaceRow {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, iface) -> None:
        super().__init__()
        self.iface = iface

    def render(self) -> str:
        i = self.iface
        status = "[green]ON[/]" if i.online else "[red]OFF[/]"
        name = i.name
        rx = _format_bytes(i.rxb)
        tx = _format_bytes(i.txb)
        rate = _format_speed(i.bitrate)

        flags = ""
        for f in ("IN", "OUT", "FWD", "RPT"):
            if getattr(i, f, False):
                flags += f[0]

        return f"{status} [b]{name}[/b]  {rate}  rx:{rx} tx:{tx}  {flags}"


class InterfacesView(Vertical):
    """Shows all active Reticulum interfaces."""

    DEFAULT_CSS = """
    InterfacesView {
        height: 100%;
    }
    InterfacesView .title {
        text-style: bold;
        padding: 1;
        color: $accent;
    }
    InterfacesView .empty {
        padding: 2;
        text-align: center;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, core: Core):
        super().__init__()
        self.core = core

    def compose(self) -> ComposeResult:
        yield Static("Interfaces", classes="title")
        yield ScrollableContainer(id="iface-scroll")

    def on_mount(self) -> None:
        self._refresh()
        # Auto-refresh every 5 seconds
        self.set_interval(5, self._refresh)

    def action_refresh(self) -> None:
        self._refresh()
        self.app.notify("Refreshed")

    def _refresh(self) -> None:
        try:
            scroll = self.query_one("#iface-scroll", ScrollableContainer)
        except Exception:
            return
        scroll.remove_children()

        interfaces = RNS.Transport.interfaces
        if not interfaces:
            scroll.mount(Static("No interfaces available.", classes="empty"))
            return

        for iface in interfaces:
            # Skip detached interfaces
            if getattr(iface, "detached", False):
                continue
            # Skip child interfaces (show parents only)
            if getattr(iface, "parent_interface", None) is not None:
                continue
            scroll.mount(InterfaceRow(iface))
