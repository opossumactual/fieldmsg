"""fieldmsg - Lightweight LXMF messenger for Reticulum."""

import argparse
import logging
import signal
import sys
import time

from fieldmsg import __version__

log = logging.getLogger(__name__)


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


def _make_core(config):
    """Create a Core instance.  Indirection point for testing."""
    from fieldmsg.core import Core

    return Core(config)


def run_send(args, config) -> int:
    """Send a single message and wait for delivery status."""
    core = _make_core(config)
    core.setup()

    delivered = None

    def on_status(msg_id, status):
        nonlocal delivered
        delivered = status

    core.on_delivery_status = on_status
    msg_id = core.send_message(args.destination, args.message)

    if msg_id is None:
        print("Failed to create message", file=sys.stderr)
        core.shutdown()
        return 1

    print(f"Sending {msg_id[:16]}...")

    # Wait up to 30 seconds for delivery status
    deadline = time.time() + 30
    while time.time() < deadline and delivered is None:
        time.sleep(0.5)

    if delivered == "delivered":
        print("Delivered.")
    elif delivered == "sent":
        print("Sent (delivery not confirmed yet).")
    elif delivered == "failed":
        print("Delivery failed.", file=sys.stderr)
        core.shutdown()
        return 1
    else:
        print("Timed out waiting for delivery status.")

    core.shutdown()
    return 0


def run_daemon(config) -> int:
    """Run as a headless daemon until interrupted."""
    core = _make_core(config)
    core.setup()

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"fieldmsg daemon running \u2014 {core.get_own_hash()}")

    last_sync = 0
    try:
        while running:
            time.sleep(1)
            if config.propagation_node and config.sync_interval > 0:
                if time.time() - last_sync >= config.sync_interval:
                    core.sync_propagation_node()
                    last_sync = time.time()
    except KeyboardInterrupt:
        pass

    print("Shutting down...")
    core.shutdown()
    return 0


def run_tui(config) -> int:
    """Launch the interactive TUI."""
    from fieldmsg.core import Core
    from fieldmsg.tui.app import FieldMsgApp

    # Reticulum registers signal handlers, which requires the main thread.
    # Initialize Core here before Textual takes over the event loop.
    core = Core(config)
    core.setup()

    app = FieldMsgApp(config, core=core)
    app.run()
    core.shutdown()
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.generate_config:
        from fieldmsg.config import generate_example_config

        print(generate_example_config())
        sys.exit(0)

    from fieldmsg.config import load_config

    config = load_config(args.config)
    config.rns_config_dir = args.rnsconfig

    if args.command == "send":
        sys.exit(run_send(args, config))
    elif args.daemon:
        sys.exit(run_daemon(config))
    else:
        sys.exit(run_tui(config))


if __name__ == "__main__":
    main()
