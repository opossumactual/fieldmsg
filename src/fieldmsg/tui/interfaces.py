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


class InterfaceCard(Static):
    """Display block for a single Reticulum interface."""

    DEFAULT_CSS = """
    InterfaceCard {
        height: auto;
        padding: 1 2;
        margin: 0 0 1 0;
        border: solid $accent;
    }
    """

    def __init__(self, iface) -> None:
        super().__init__()
        self.iface = iface

    def render(self) -> str:
        i = self.iface
        status = "[green]ONLINE[/]" if i.online else "[red]OFFLINE[/]"
        itype = i.__class__.__name__
        name = i.name

        lines = [
            f"[b]{name}[/b]  {status}",
            f"  Type: {itype}",
            f"  Bitrate: {_format_speed(i.bitrate)}",
            f"  RX: {_format_bytes(i.rxb)}  TX: {_format_bytes(i.txb)}",
        ]

        rx_speed = getattr(i, "current_rx_speed", 0)
        tx_speed = getattr(i, "current_tx_speed", 0)
        if rx_speed > 0 or tx_speed > 0:
            lines.append(f"  Speed: RX {_format_speed(rx_speed)}  TX {_format_speed(tx_speed)}")

        mode = getattr(i, "mode", None)
        if mode is not None:
            lines.append(f"  Mode: {_mode_name(mode)}")

        flags = []
        if i.IN:
            flags.append("IN")
        if i.OUT:
            flags.append("OUT")
        if i.FWD:
            flags.append("FWD")
        if i.RPT:
            flags.append("RPT")
        if flags:
            lines.append(f"  Flags: {' '.join(flags)}")

        return "\n".join(lines)


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
            scroll.mount(InterfaceCard(iface))
