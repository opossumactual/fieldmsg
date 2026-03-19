from __future__ import annotations

import time


def format_announce(hash: str, display_name: str | None, hops: int, timestamp: float, interface: str | None) -> str:
    """Format an announce entry for display."""
    name = display_name or hash[:16]
    age = relative_time(timestamp)
    hop_str = f"{hops} hop{'s' if hops != 1 else ''}"
    iface = f" via {interface}" if interface else ""
    return f"{name} [{hash[:12]}..] {hop_str}{iface} ({age})"


def relative_time(ts: float) -> str:
    """Return human-readable relative time string."""
    delta = int(time.time() - ts)
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = delta // 60
        return f"{m}m ago"
    if delta < 86400:
        h = delta // 3600
        return f"{h}h ago"
    d = delta // 86400
    return f"{d}d ago"
