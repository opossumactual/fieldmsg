"""fieldmsg - Lightweight LXMF messenger for Reticulum."""

import argparse
import sys

from fieldmsg import __version__

EXAMPLE_CONFIG = """\
[identity]
display_name = "Field Unit Alpha"
# identity is auto-generated on first run and stored at ~/.fieldmsg/identity

[lxmf]
propagation_node = ""       # destination hash of preferred propagation node
sync_interval = 300         # seconds between propagation syncs
announce_at_start = true    # announce on startup
announce_interval = 600     # periodic re-announce interval, 0 to disable

[storage]
db_path = "~/.fieldmsg/messages.db"
max_age_days = 90           # auto-cleanup old messages, 0 to disable
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldmsg",
        description="Lightweight LXMF messenger for Reticulum",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"fieldmsg {__version__}",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="path to fieldmsg config file",
    )
    parser.add_argument(
        "--rnsconfig",
        metavar="PATH",
        help="path to Reticulum config directory",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="run headless without TUI",
    )
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="print example config to stdout and exit",
    )

    subparsers = parser.add_subparsers(dest="command")

    send_parser = subparsers.add_parser("send", help="send a message")
    send_parser.add_argument(
        "destination",
        help="destination identity hash (hex)",
    )
    send_parser.add_argument(
        "message",
        help="message text to send",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.generate_config:
        sys.stdout.write(EXAMPLE_CONFIG)
        raise SystemExit(0)

    if args.command == "send":
        print(f"[stub] Would send to {args.destination}: {args.message}")
        raise SystemExit(0)

    config_path = args.config or "~/.fieldmsg/config.toml"
    rns_config = args.rnsconfig or "~/.reticulum"
    mode = "daemon" if args.daemon else "TUI"

    print(f"[stub] fieldmsg {__version__}")
    print(f"[stub] config:    {config_path}")
    print(f"[stub] rnsconfig: {rns_config}")
    print(f"[stub] mode:      {mode}")
    print("[stub] Not yet implemented.")


if __name__ == "__main__":
    main()
